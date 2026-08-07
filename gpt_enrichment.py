# -*- coding: utf-8 -*-
"""
GPT-4o-mini token-dostu zenginleştirme katmanı.
Cosine sonuçları bozulmaz; kota/cache aşımında sessizce şablon gerekçeler kalır.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Tuple

GPT_MODEL = 'gpt-4o-mini'
GPT_MAX_ITEMS = {
    'search': 10,          # Keşfet: yalnızca en güçlü eşleşmelere not (liste kısıtlanmaz)
    'recommendations': 6,
    'social': 5,
}
GPT_DAILY_LIMITS = {
    'search': 8,
    'recommendations': 5,
    'social': 3,
}
GPT_PER_MINUTE = {
    'search': 3,
    'recommendations': 2,
    'social': 2,
}
GPT_CACHE_TTL_SEC = 14 * 24 * 3600  # 14 gün
GPT_GLOBAL_DAILY_CAP = 500
GPT_MAX_OUTPUT_TOKENS = 520
SEARCH_IP_PER_MINUTE = 25  # Keşfet bot koruması (embedding dahil)
# Keşfet GPT not eşiği: zayıf/yan temaslı sonuçlara (ör. Banshee↔hapishane) not yazılmaz
SEARCH_NOTE_INTENT_FLOOR = 0.42
SEARCH_NOTE_HYBRID_RATIO = 0.58
# Otomatik sorgu kavram genişletme (sözlük yerine — her cümle için)
QUERY_EXPAND_CACHE_TTL_SEC = 30 * 24 * 3600
QUERY_EXPAND_GLOBAL_DAILY = 350
QUERY_EXPAND_MAX_TOKENS = 180

try:
    from db_paths import RUNTIME_CACHE_DB_PATH as _DEFAULT_GPT_DB
except Exception:
    _DEFAULT_GPT_DB = 'runtime_cache.db'

_NONSENSE_EXACT = {
    'mal', 'malım', 'malim', 'salak', 'aptal', 'gerizekalı', 'gerizekali',
    'asdasd', 'asdf', 'qwerty', 'test', 'deneme', 'aaaa', 'bbbb', 'xxx',
    'amk', 'aq', 'sik', 'siktir', 'oç', 'oc',
}
_MEDIA_HINTS = (
    'film', 'dizi', 'yapım', 'yapim', 'izle', 'öner', 'oner', 'tavsiye',
    'temalı', 'temali', 'konulu', 'tarz', 'gibi', 'benzer', 'atmosfer',
    'korku', 'komedi', 'aksiyon', 'romantik', 'gerilim', 'bilim', 'uzay',
    'movie', 'series', 'show', 'watch',
)

_minute_buckets: Dict[str, deque] = defaultdict(deque)
_ip_search_buckets: Dict[str, deque] = defaultdict(deque)


def init_gpt_tables(db_path: str = None) -> None:
    db_path = db_path or _DEFAULT_GPT_DB
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS gpt_notes_cache (
            cache_key TEXT PRIMARY KEY,
            notes_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS gpt_usage_daily (
            day_key TEXT NOT NULL,
            username TEXT NOT NULL,
            feature TEXT NOT NULL,
            call_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (day_key, username, feature)
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS gpt_global_daily (
            day_key TEXT PRIMARY KEY,
            call_count INTEGER NOT NULL DEFAULT 0
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS gpt_query_expand_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def is_obvious_nonsense_query(query: str) -> bool:
    """
    Ucuz yerel filtre: hakaret / spam / boş niyet.
    True → arama yapılmamalı. Şüphede False (embedding/GPT karar verir).
    """
    q = re.sub(r'\s+', ' ', (query or '').strip().lower())
    if len(q) < 2:
        return True
    # Çok tekrarlı karakter / klavye spam
    compact = q.replace(' ', '')
    if re.fullmatch(r'(.)\1{4,}', compact):
        return True

    def _bad_tok(t: str) -> bool:
        if t in _NONSENSE_EXACT:
            return True
        for root in ('mal', 'salak', 'aptal', 'gerizekal', 'gerizekali'):
            if t.startswith(root):
                return True
        return False

    toks = [t for t in re.split(r'[^\wığüşöç0-9]+', q) if len(t) >= 2]
    if not toks:
        return True
    if all(_bad_tok(t) for t in toks):
        return True
    # "ben malım", "ben salağım" vb.
    if len(toks) <= 3 and any(_bad_tok(t) for t in toks):
        if not any(h in q for h in _MEDIA_HINTS):
            return True
    if re.fullmatch(r'[a-zığüşöç]{1,3}(\s+[a-zığüşöç]{1,3}){0,2}', q) and not any(h in q for h in _MEDIA_HINTS):
        if toks and all(_bad_tok(t) or len(t) <= 2 for t in toks):
            return True
    return False


def _query_expand_cache_key(query: str, media_type: str) -> str:
    raw = f'expand_v1|{(media_type or "").upper()}|{(query or "").strip().lower()}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def _get_expand_cached(db_path: str, cache_key: str) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        'SELECT payload_json, created_at FROM gpt_query_expand_cache WHERE cache_key = ?',
        (cache_key,)
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    payload_json, created_at = row
    if time.time() - float(created_at) > QUERY_EXPAND_CACHE_TTL_SEC:
        return None
    try:
        data = json.loads(payload_json)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _set_expand_cached(db_path: str, cache_key: str, payload: Dict[str, Any]) -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        '''
        INSERT INTO gpt_query_expand_cache (cache_key, payload_json, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
          payload_json = excluded.payload_json,
          created_at = excluded.created_at
        ''',
        (cache_key, json.dumps(payload, ensure_ascii=False), time.time())
    )
    conn.commit()
    conn.close()


def expand_search_query_concepts(
    openai_client,
    query: str,
    *,
    media_type: str = 'MOVIES',
    db_path: str = None,
) -> Tuple[bool, List[str], bool]:
    """
    Herhangi bir kullanıcı cümlesini otomatik kavram listesine çevirir.
    Sözlüğe elle eklemeye gerek kalmaz (beyin yakan, steampunk, korku-komedi...).

    Returns:
      (is_meaningful, concepts, used_llm)
      is_meaningful=False → anlamsız sorgu, sonuç dönme
      concepts=[] + meaningful=True → GPT yok/kota; embedding-only devam
    """
    db_path = db_path or _DEFAULT_GPT_DB
    q = (query or '').strip()
    if not q:
        return False, [], False
    if is_obvious_nonsense_query(q):
        return False, [], False

    cache_key = _query_expand_cache_key(q, media_type)
    cached = _get_expand_cached(db_path, cache_key)
    if cached is not None:
        ok = cached.get('ok') is not False
        concepts = cached.get('concepts') if isinstance(cached.get('concepts'), list) else []
        clean = [str(c).strip() for c in concepts if str(c).strip()][:16]
        return bool(ok), clean, False

    if not openai_client:
        return True, [], False

    # Global günlük tavan (not kotasından ayrı, sistem genişletme)
    if _get_global_daily(db_path) >= GPT_GLOBAL_DAILY_CAP:
        return True, [], False
    # Expand özel sayaç: aynı gpt_usage_daily tablosu, feature=query_expand
    if _get_daily_count(db_path, '__system__', 'query_expand') >= QUERY_EXPAND_GLOBAL_DAILY:
        return True, [], False

    media_tr = 'film' if str(media_type).upper() == 'MOVIES' else 'dizi'
    system = (
        "Sen sinema/dizi arama niyet çevirmenisin. "
        "Kullanıcı cümlesini kısa arama kavramlarına aç. "
        "Hakaret, spam, anlamsız (ör. 'ben malım', 'asdasd') ise ok=false. "
        "Anlamlıysa 6-14 kavram ver (Türkçe ve/veya İngilizce). "
        "Sözlük ezberleme — yeni/bilinmeyen temaları da aç (steampunk, beyin yakan, folk horror...). "
        'Strict JSON: {"ok": true, "concepts": ["..."]}'
    )
    user = (
        f'Medya: {media_tr}\n'
        f'Sorgu: "{q}"\n'
        f'Örnek iyi: "beyin yakan filmler" → '
        f'["mind-bending","nonlinear","time travel","zihin bükücü","psychological puzzle"]'
    )

    try:
        _bump_usage(db_path, '__system__', 'query_expand')
        completion = openai_client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user},
            ],
            max_tokens=QUERY_EXPAND_MAX_TOKENS,
            temperature=0.3,
            response_format={'type': 'json_object'},
        )
        raw = completion.choices[0].message.content or '{}'
        data = json.loads(raw)
        if not isinstance(data, dict):
            return True, [], True
        ok = data.get('ok') is not False
        concepts = data.get('concepts') if isinstance(data.get('concepts'), list) else []
        clean = []
        for c in concepts:
            s = str(c).strip()
            if 1 < len(s) <= 48 and s not in clean:
                clean.append(s)
            if len(clean) >= 16:
                break
        payload = {'ok': bool(ok), 'concepts': clean}
        _set_expand_cached(db_path, cache_key, payload)
        return bool(ok), clean, True
    except Exception as err:
        print(f'[!] Query expand sessiz fallback: {err}')
        return True, [], False


def _day_key(now: Optional[float] = None) -> str:
    return time.strftime('%Y-%m-%d', time.localtime(now or time.time()))


def _prune_bucket(bucket: deque, window_sec: float = 60.0) -> None:
    cutoff = time.time() - window_sec
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def compose_unique_search_note(query: str, title: str, genres: str = '', keywords: str = '', summary: str = '') -> str:
    """
    Her yapım için özgün eşleşme notu (GPT yokken / fallback).
    Özet + anahtar kelime + arama niyetinden yapım-özel cümle üretir.
    """
    q = (query or '').strip() or 'aramanız'
    title = (title or 'Bu yapım').strip()
    genres = genres or ''
    keywords = keywords or ''
    summary = re.sub(r'\s+', ' ', (summary or '')).strip()
    blob = f'{keywords} {summary} {genres}'.lower()
    q_l = q.lower()

    intent_hooks = {
        'polisiye': ['polis', 'dedektif', 'cinayet', 'soruşturma', 'komiser', 'suç', 'fbi', 'katil', 'otoyol', 'trafik', 'adli'],
        'suç': ['suç', 'mafya', 'çete', 'cinayet', 'organize', 'gangster', 'kartel'],
        'dedektif': ['dedektif', 'soruşturma', 'cinayet', 'gizem', 'ipucu'],
        'gerilim': ['gerilim', 'süspans', 'kaçak', 'tehlike', 'psikolojik'],
        'korku': ['korku', 'dehşet', 'hayalet', 'doğaüstü', 'canavar'],
        'zombi': ['zombi', 'zombie', 'salgın', 'apocalypse', 'enfekte', 'walking dead', 'hayatta kalma'],
        'romantik': ['aşk', 'ilişki', 'romantik', 'sevgi'],
        'bilim': ['uzay', 'robot', 'yapay zeka', 'gelecek', 'distopya'],
        'komedi': ['komedi', 'mizah', 'komik', 'güldürü'],
        'savaş': ['savaş', 'asker', 'ordu', 'cephe'],
        'fantastik': ['büyü', 'sihir', 'ejderha', 'mitoloji', 'doğaüstü'],
        'hapishane': ['hapishane', 'cezaevi', 'mahkum', 'kaçış'],
        'casus': ['ajan', 'casus', 'istihbarat', 'gizli'],
        'ortaçağ': ['ortaçağ', 'medieval', 'şövalye', 'krallık', 'feodal'],
    }

    bag = []
    for key, hooks in intent_hooks.items():
        if key in q_l or any(h in q_l for h in hooks[:4]):
            bag.extend(hooks)
    if not bag:
        bag = re.findall(r'[a-zA-ZğüşıöçĞÜŞİÖÇ]{3,}', q_l)

    found = []
    for h in bag:
        if h in blob and h not in found:
            found.append(h)
        if len(found) >= 2:
            break

    snippet = ''
    if summary:
        parts = [p.strip() for p in re.split(r'[.!?]+', summary) if p and len(p.strip()) >= 28]
        for s in parts:
            if found and any(f in s.lower() for f in found):
                snippet = s
                break
        if not snippet and parts:
            snippet = parts[0]
        elif not snippet:
            snippet = summary
        if len(snippet) > 105:
            snippet = snippet[:102].rsplit(' ', 1)[0] + '…'

    genre_list = [g.strip() for g in genres.split(',') if g.strip()]
    pick_genre = None
    prefer = ('suç', 'gizem', 'aksiyon', 'gerilim', 'macera', 'korku')
    for g in genre_list:
        if any(p in g.lower() for p in prefer):
            pick_genre = g
            break
    if not pick_genre and genre_list:
        # "Dram" tek başına yanıltıcı olabilir — son çare
        non_drama = [g for g in genre_list if 'dram' not in g.lower()]
        pick_genre = (non_drama or genre_list)[0]

    if found and snippet:
        return (
            f'"{q}" aramanız için {title} önerildi: '
            f'{", ".join(found)} izleri taşıyor — {snippet}'
        )
    if snippet:
        return f'"{q}" aramanız için {title} önerildi çünkü: {snippet}'
    if pick_genre and found:
        return (
            f'"{q}" aramanız için {title} seçildi; '
            f'{pick_genre} + {found[0]} dokusu aramanızla örtüşüyor.'
        )
    if pick_genre:
        return (
            f'"{q}" aramanız için {title} seçildi; '
            f'{pick_genre} atmosferi aradığınız temaya yakın duruyor.'
        )
    return f'"{q}" aramanız için {title} önerildi; semantik olarak aradığınız temaya yakın.'


def check_ip_search_allowed(ip: str, limit: int = SEARCH_IP_PER_MINUTE) -> bool:
    """Keşfet için IP başına dakikalık istek tavanı. Aşımda False."""
    key = (ip or 'unknown').strip() or 'unknown'
    bucket = _ip_search_buckets[key]
    _prune_bucket(bucket)
    if len(bucket) >= limit:
        return False
    bucket.append(time.time())
    return True


def _minute_allowed(username: str, feature: str) -> bool:
    key = f'{feature}:{username}'
    bucket = _minute_buckets[key]
    _prune_bucket(bucket)
    limit = GPT_PER_MINUTE.get(feature, 2)
    if len(bucket) >= limit:
        return False
    return True


def _record_minute(username: str, feature: str) -> None:
    _minute_buckets[f'{feature}:{username}'].append(time.time())


def _get_daily_count(db_path: str, username: str, feature: str) -> int:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        'SELECT call_count FROM gpt_usage_daily WHERE day_key = ? AND username = ? AND feature = ?',
        (_day_key(), username, feature)
    )
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def _get_global_daily(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT call_count FROM gpt_global_daily WHERE day_key = ?', (_day_key(),))
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def _bump_usage(db_path: str, username: str, feature: str) -> None:
    day = _day_key()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        '''
        INSERT INTO gpt_usage_daily (day_key, username, feature, call_count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(day_key, username, feature)
        DO UPDATE SET call_count = call_count + 1
        ''',
        (day, username, feature)
    )
    c.execute(
        '''
        INSERT INTO gpt_global_daily (day_key, call_count)
        VALUES (?, 1)
        ON CONFLICT(day_key)
        DO UPDATE SET call_count = call_count + 1
        ''',
        (day,)
    )
    conn.commit()
    conn.close()
    _record_minute(username, feature)


def can_consume_gpt(db_path: str, username: str, feature: str) -> bool:
    if not username or username.lower() in ('guest', 'kullanıcı', 'kullanici'):
        return False
    if _get_global_daily(db_path) >= GPT_GLOBAL_DAILY_CAP:
        return False
    daily_limit = GPT_DAILY_LIMITS.get(feature, 3)
    if _get_daily_count(db_path, username, feature) >= daily_limit:
        return False
    if not _minute_allowed(username, feature):
        return False
    return True


def make_cache_key(feature: str, context: str, item_ids: List[str]) -> str:
    # v4: arama niyetine göre şekillenen eşleşme notları (zombi/undead tuzağı sonrası)
    raw = f'v4|{feature}|{context.strip().lower()}|{"|".join(item_ids)}'
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def get_cached_notes(db_path: str, cache_key: str) -> Optional[Dict[str, str]]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('SELECT notes_json, created_at FROM gpt_notes_cache WHERE cache_key = ?', (cache_key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    notes_json, created_at = row
    if time.time() - float(created_at) > GPT_CACHE_TTL_SEC:
        return None
    try:
        data = json.loads(notes_json)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def set_cached_notes(db_path: str, cache_key: str, notes: Dict[str, str]) -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute(
        '''
        INSERT INTO gpt_notes_cache (cache_key, notes_json, created_at)
        VALUES (?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET notes_json = excluded.notes_json, created_at = excluded.created_at
        ''',
        (cache_key, json.dumps(notes, ensure_ascii=False), time.time())
    )
    conn.commit()
    conn.close()


def select_strong_search_targets(
    items: List[Dict[str, Any]],
    *,
    max_n: int = 10,
    intent_floor: float = SEARCH_NOTE_INTENT_FLOOR,
    hybrid_ratio: float = SEARCH_NOTE_HYBRID_RATIO,
) -> List[Dict[str, Any]]:
    """
    Keşfet listesinden GPT notu yazılacak güçlü eşleşmeleri seçer.
    Liste kısaltılmaz; yalnızca not adayları süzülür (max 10).
    Zayıf yan temaslar (kısa hapishane sahnesi vb.) elenir.
    """
    if not items:
        return []
    max_n = max(1, min(int(max_n or 10), GPT_MAX_ITEMS.get('search', 10)))
    top_hybrid = float(items[0].get('hybridScore') or items[0].get('rawSimilarity') or 0.0)
    floor_hybrid = top_hybrid * float(hybrid_ratio) if top_hybrid > 0 else 0.0

    strong = []
    for it in items:
        intent = float(it.get('intentCoverage') or 0.0)
        hybrid = float(it.get('hybridScore') or it.get('rawSimilarity') or 0.0)
        graph = bool(it.get('graphHit'))
        # Güçlü niyet VEYA (üst banda yakın hybrid + en az orta niyet) VEYA graph + orta niyet
        if intent >= intent_floor and hybrid >= floor_hybrid * 0.85:
            strong.append(it)
        elif hybrid >= max(floor_hybrid, top_hybrid * 0.72) and intent >= (intent_floor * 0.75):
            strong.append(it)
        elif graph and intent >= (intent_floor * 0.7) and hybrid >= floor_hybrid * 0.75:
            strong.append(it)
        if len(strong) >= max_n:
            break

    # Hiçbiri eşiği geçmediyse: en azından en üstteki birkaçına not (min 1, max 5)
    if not strong:
        fallback_n = min(5, max_n, len(items))
        strong = list(items[:fallback_n])
    return strong[:max_n]


def _build_prompt(feature: str, context: str, compact: List[Dict[str, str]]) -> Tuple[str, str]:
    q = (context or '').strip() or 'kullanıcı araması'
    if feature == 'search':
        system = (
            "Sen DizimiBul platformunun sinema/dizi uzmanısın. "
            "Görevin: kullanıcının YAZDIĞI arama cümlesine göre her yapım için kısa Türkçe eşleşme notu yazmak. "
            "Her not 1–2 cümle, max 42 kelime. "
            "ZORUNLU: Not, kullanıcının arama niyetini doğal dilde yansıtmalı "
            "(ör. zombi / hapishane / ortaçağ arıyorsa o temayı bağla). "
            "Üslup: kısa konu kancası + NEDEN bu aramaya uyuyor. "
            "Örnek (zombi araması): 'The Last of Us'ta salgın sonrası hayatta kalma ve enfekte tehdidi "
            "ön planda; zombi temalı aramanla birebir örtüşüyor.' "
            "Örnek (hapishane): 'Prison Break'te Michael, abisini hapishaneden kurtarmak için "
            "kendini bilerek içeri attırır; hapishane kaçış gerilimi aramanla örtüşüyor.' "
            "YASAK: soyut skor, 'semantik uyum', 'hibrit uyum', 'vektör', yüzde kalıpları, "
            "yalnızca genel özet cümlesi kopyalamak, aramayla alakasız gerekçe. "
            "Arama kelimesini doğal kullan. JSON anahtarları item id olmalı. "
            'Strict JSON: {"item_id": "not"}'
        )
        user = (
            f'Kullanıcı araması (notu BUNA göre şekillendir): "{q}"\n'
            f'Her yapım için: (1) kısa konu kancası (2) bu aramaya NEDEN uyduğu.\n'
            f'Arama temasına uymayan gerekçe yazma.\n'
            f'Yalnızca verilen listede not yaz (en fazla {len(compact)}).\n'
            f'Yapımlar: {json.dumps(compact, ensure_ascii=False)}'
        )
    elif feature == 'social':
        # context: "ortak zevk | names: Ali||Veli | A seçimleri: ... | B seçimleri: ..."
        name_a, name_b = 'birinci kullanıcı', 'ikinci kullanıcı'
        m = re.search(r'names:\s*([^|]+)\|\|([^|]+)', q, flags=re.I)
        if m:
            name_a = (m.group(1) or '').strip() or name_a
            name_b = (m.group(2) or '').strip() or name_b
        system = (
            "Sen DizimiBul platformunun sinema/dizi uzmanısın. "
            "İki arkadaşın ortak zevk füzyonu için her yapımda Türkçe 1–2 cümle yaz (max 42 kelime). "
            f"ZORUNLU üslup: {name_a}'nın seçtiği bir yapım + {name_b}'nın seçtiği bir yapım ile bağ kur "
            f"(ör. '{name_a} Prison Break izlediği, {name_b} Mr. Robot seçtiği için bu kaçış/gerilim temalı öneriyi sundum'). "
            f"Kullanıcı adlarını ({name_a}, {name_b}) doğal şekilde kullan; asla yalnızca 'A' veya 'B' yazma. "
            "Kısa konu kancası + NEDEN ikisine birden uygun. "
            "Skor / semantik uyum / cosine / yüzde / 'X aramanız' kalıpları YASAK. "
            "JSON anahtarları item id olmalı. "
            'Strict JSON: {"item_id": "gerekçe"}'
        )
        user = (
            f'İki kullanıcının ortak zevk bağlamı: "{q}"\n'
            f'Her öneri için: {name_a} ve {name_b} seçimlerine dayanan özgün gerekçe yaz. '
            f'Adları kullan ({name_a}, {name_b}); A/B yazma.\n'
            f'Yapımlar: {json.dumps(compact, ensure_ascii=False)}'
        )
    else:
        system = (
            "Sen DizimiBul platformunun sinema/dizi uzmanısın. "
            "Her yapım için Türkçe 1 cümle yaz (max 28 kelime). "
            f'Doğrudan kullanıcının bağlamına bağla: "{q}". '
            "Asla 'X aramanız' yazma. JSON anahtarları item id olmalı. "
            'Strict JSON: {"item_id": "gerekçe"}'
        )
        user = (
            f'Kullanıcı zevki/sorgu: "{q}"\n'
            f'Öneriler: {json.dumps(compact, ensure_ascii=False)}'
        )
    return system, user


def _sanitize_note(text: str, context: str) -> str:
    t = (text or '').strip()
    q = (context or '').strip()
    if not t:
        return t
    if q:
        t = t.replace('X aramanız', f'"{q}" aramanız').replace('x aramanız', f'"{q}" aramanız')
        t = t.replace("'X'", f'"{q}"').replace('"X"', f'"{q}"')
        # Sosyal füzyon: A/B → gerçek kullanıcı adları
        m = re.search(r'names:\s*([^|]+)\|\|([^|]+)', q, flags=re.I)
        if m:
            name_a = (m.group(1) or '').strip()
            name_b = (m.group(2) or '').strip()
            if name_a:
                t = re.sub(r"\bA'nın\b", f"{name_a}'nın", t)
                t = re.sub(r"\bA'ya\b", f"{name_a}'ya", t)
                t = re.sub(r"(?<![\wçğıöşüÇĞİÖŞÜ])A(?![\wçğıöşüÇĞİÖŞÜ])", name_a, t)
            if name_b:
                t = re.sub(r"\bB'nin\b", f"{name_b}'nın", t)
                t = re.sub(r"\bB'ya\b", f"{name_b}'ya", t)
                t = re.sub(r"(?<![\wçğıöşüÇĞİÖŞÜ])B(?![\wçğıöşüÇĞİÖŞÜ])", name_b, t)
    t = re.sub(r'AI\s*Cosine\s*Uyum', 'Yapay Zeka Uyumu', t, flags=re.I)
    t = re.sub(r'Cosine\s*Uyum', 'Yapay Zeka Uyumu', t, flags=re.I)
    t = re.sub(r'Cosine\s*Similarity', 'Yapay Zeka', t, flags=re.I)
    return t.strip()


def _apply_notes_to_items(targets, notes, id_field, title_field, reason_field, context) -> bool:
    id_to_item = {str(it.get(id_field)): it for it in targets}
    title_to_item = {
        str(it.get(title_field) or '').strip().lower(): it
        for it in targets if it.get(title_field)
    }
    applied = False
    for key, raw_note in (notes or {}).items():
        note = _sanitize_note(str(raw_note), context)
        if not note:
            continue
        it = id_to_item.get(str(key))
        if not it:
            raw_id = str(key).replace('series_', '').replace('movies_', '')
            for cand_id, cand in id_to_item.items():
                if cand_id.endswith(raw_id) or cand_id.replace('series_', '').replace('movies_', '') == raw_id:
                    it = cand
                    break
        if not it:
            it = title_to_item.get(str(key).strip().lower())
        if it:
            it[reason_field] = note
            applied = True
    return applied


def enrich_with_gpt_notes(
    openai_client,
    items: List[Dict[str, Any]],
    *,
    feature: str,
    context: str,
    username: str,
    db_path: str = None,
    id_field: str = 'id',
    title_field: str = 'title',
    reason_field: str = 'aiReason',
) -> bool:
    """
    Üye + kota + cache uygunsa GPT notlarını yazar.
    Başarısızlık/kota: False (mevcut aiReason dokunulmaz — sessiz fallback).
    """
    db_path = db_path or _DEFAULT_GPT_DB
    if not openai_client or not items or not username:
        return False

    max_n = GPT_MAX_ITEMS.get(feature, 6)
    targets = items[:max_n]
    item_ids = [str(it.get(id_field, '')) for it in targets if it.get(id_field)]
    if not item_ids:
        return False

    cache_key = make_cache_key(feature, context or '', item_ids)
    cached = get_cached_notes(db_path, cache_key)
    if cached:
        applied = _apply_notes_to_items(targets, cached, id_field, title_field, reason_field, context)
        if applied:
            return True

    if not can_consume_gpt(db_path, username, feature):
        return False

    compact = []
    for it in targets:
        if not it.get(id_field):
            continue
        genres = str(it.get('genres') or it.get('tur') or '')[:70]
        # Keşfet notları için biraz daha uzun özet → hikâye kancası kaliteli olur
        hint_len = 220 if feature == 'search' else 110
        hint = str(it.get('summary') or it.get('hint') or '')[:hint_len]
        keywords = str(it.get('keywords') or '')[:80]
        row = {
            'id': str(it.get(id_field)),
            'title': str(it.get(title_field) or '')[:80],
            'tur': genres,
            'ipuclari': hint,
        }
        if keywords:
            row['anahtar'] = keywords
        compact.append(row)
    if not compact:
        return False
    system, user = _build_prompt(feature, context or '', compact)

    try:
        _bump_usage(db_path, username, feature)
        completion = openai_client.chat.completions.create(
            model=GPT_MODEL,
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user},
            ],
            max_tokens=GPT_MAX_OUTPUT_TOKENS,
            temperature=0.55,
            response_format={'type': 'json_object'},
        )
        raw = completion.choices[0].message.content or '{}'
        notes = json.loads(raw)
        if not isinstance(notes, dict):
            return False

        # Bazen model {"notes": {...}} veya title key döner
        if len(notes) == 1 and isinstance(next(iter(notes.values())), dict):
            notes = next(iter(notes.values()))

        clean = {}
        for k, v in notes.items():
            if not v:
                continue
            clean[str(k)] = _sanitize_note(str(v), context)
        if not clean:
            return False

        set_cached_notes(db_path, cache_key, clean)
        return _apply_notes_to_items(targets, clean, id_field, title_field, reason_field, context)
    except Exception as err:
        print(f'[!] GPT enrich ({feature}) sessiz fallback: {err}')
        return False
