# -*- coding: utf-8 -*-
"""
🎭 MATRIX - PARALEL TÜR ÜRETİCİ  |  SABİT TÜR LİSTESİ SÜRÜMÜ
------------------------------------------------------------------
AI çıktısı NE OLURSA OLSUN, sonuç sadece şu 9 türden oluşur:
  Aksiyon & Macera / Animasyon / Komedi / Suç / Belgesel /
  Dram / Aile / Gizem / Bilim Kurgu & Fantastik

DB'ye YAZMAZ (read-only) → fragman scriptiyle aynı anda çalışır.
Sonuç: tur_havuzu.json  →  sonra: python tur_yukleyici.py
------------------------------------------------------------------
"""

import os
import sys
import json
import time
import re
import sqlite3
import unicodedata
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

# ═══════════════════════ AYARLAR ═══════════════════════
DB_PATH      = "katalog.db"
TABLE_NAME   = "filmler"
ID_COLUMN    = "id"
TITLE_COLUMN = "isim"
YEAR_COLUMN  = "yil"
GENRE_COLUMN = "turler"          # ← HEDEF KOLON
POOL_JSON    = "tur_havuzu.json"

MAX_GENRES   = 2                 # film başına max tür (2 önerilir)
FALLBACK     = "Dram"            # AI hiçbir şey veremezse yazılacak tür
# ═══════════════════════════════════════════════════════


# ─── 1) İZİN VERİLEN TEK GERÇEK LİSTE ────────────────────────────
ALLOWED_GENRES = [
    "Aksiyon & Macera",
    "Animasyon",
    "Komedi",
    "Suç",
    "Belgesel",
    "Dram",
    "Aile",
    "Gizem",
    "Bilim Kurgu & Fantastik",
]

# ─── 2) HER TÜRLÜ ÇIKTIYI BU 9 KOVAYA EŞLEYEN HARİTA ─────────────
#     (anahtarlar küçük harf + aksansız yazılır, otomatik normalize edilir)
GENRE_MAP = {
    # ── Aksiyon & Macera ──
    "aksiyon": "Aksiyon & Macera", "action": "Aksiyon & Macera",
    "macera": "Aksiyon & Macera", "adventure": "Aksiyon & Macera",
    "aksiyon & macera": "Aksiyon & Macera", "aksiyon macera": "Aksiyon & Macera",
    "aksiyon-macera": "Aksiyon & Macera", "action & adventure": "Aksiyon & Macera",
    "savas": "Aksiyon & Macera", "war": "Aksiyon & Macera",
    "western": "Aksiyon & Macera", "kovboy": "Aksiyon & Macera",
    "dovus": "Aksiyon & Macera", "martial arts": "Aksiyon & Macera",
    "casusluk": "Aksiyon & Macera", "spy": "Aksiyon & Macera",
    "spor": "Aksiyon & Macera", "sport": "Aksiyon & Macera", "sports": "Aksiyon & Macera",
    "super kahraman": "Aksiyon & Macera", "superhero": "Aksiyon & Macera",

    # ── Animasyon ──
    "animasyon": "Animasyon", "animation": "Animasyon", "animated": "Animasyon",
    "anime": "Animasyon", "cizgi film": "Animasyon", "cartoon": "Animasyon",
    "cizgi": "Animasyon",

    # ── Komedi ──
    "komedi": "Komedi", "comedy": "Komedi", "sitcom": "Komedi",
    "kara komedi": "Komedi", "black comedy": "Komedi", "dark comedy": "Komedi",
    "romantik komedi": "Komedi", "romantic comedy": "Komedi", "rom-com": "Komedi",
    "parodi": "Komedi", "stand-up": "Komedi", "stand up": "Komedi",
    "guldürü": "Komedi", "guldürü": "Komedi",

    # ── Suç ──
    "suc": "Suç", "crime": "Suç", "polisiye": "Suç", "mafya": "Suç",
    "gangster": "Suç", "heist": "Suç", "soygun": "Suç",
    "kara film": "Suç", "film-noir": "Suç", "film noir": "Suç", "noir": "Suç",
    "hukuk": "Suç", "legal": "Suç", "mahkeme": "Suç",

    # ── Belgesel ──
    "belgesel": "Belgesel", "documentary": "Belgesel", "docuseries": "Belgesel",
    "biyografi": "Belgesel", "biography": "Belgesel", "biopic": "Belgesel",
    "haber": "Belgesel", "news": "Belgesel",
    "reality": "Belgesel", "realite": "Belgesel", "reality tv": "Belgesel",
    "talk show": "Belgesel", "yarisma": "Belgesel", "game show": "Belgesel",
    "doga": "Belgesel", "nature": "Belgesel",

    # ── Dram ──
    "dram": "Dram", "drama": "Dram", "melodram": "Dram",
    "romantik": "Dram", "romance": "Dram", "romantizm": "Dram", "ask": "Dram",
    "muzik": "Dram", "music": "Dram", "muzikal": "Dram", "musical": "Dram",
    "tarih": "Dram", "history": "Dram", "historical": "Dram", "tarihi": "Dram",
    "donem": "Dram", "period": "Dram", "epik": "Dram", "epic": "Dram",
    "psikolojik": "Dram", "toplumsal": "Dram", "kisisel gelisim": "Dram",

    # ── Aile ──
    "aile": "Aile", "family": "Aile", "cocuk": "Aile", "kids": "Aile",
    "children": "Aile", "genclik": "Aile", "teen": "Aile", "okul": "Aile",
    "egitici": "Aile", "masal": "Aile",

    # ── Gizem ──
    "gizem": "Gizem", "mystery": "Gizem",
    "gerilim": "Gizem", "thriller": "Gizem", "psikolojik gerilim": "Gizem",
    "korku": "Gizem", "horror": "Gizem", "dehset": "Gizem",
    "supernatural korku": "Gizem", "slasher": "Gizem",
    "dedektif": "Gizem", "detective": "Gizem", "suspense": "Gizem",
    "gerilim/korku": "Gizem", "korku/gerilim": "Gizem",

    # ── Bilim Kurgu & Fantastik ──
    "bilim kurgu": "Bilim Kurgu & Fantastik", "bilimkurgu": "Bilim Kurgu & Fantastik",
    "bilim-kurgu": "Bilim Kurgu & Fantastik", "sci-fi": "Bilim Kurgu & Fantastik",
    "scifi": "Bilim Kurgu & Fantastik", "science fiction": "Bilim Kurgu & Fantastik",
    "fantastik": "Bilim Kurgu & Fantastik", "fantasy": "Bilim Kurgu & Fantastik",
    "fantezi": "Bilim Kurgu & Fantastik",
    "bilim kurgu & fantastik": "Bilim Kurgu & Fantastik",
    "bilim kurgu ve fantastik": "Bilim Kurgu & Fantastik",
    "distopya": "Bilim Kurgu & Fantastik", "dystopia": "Bilim Kurgu & Fantastik",
    "uzay": "Bilim Kurgu & Fantastik", "space": "Bilim Kurgu & Fantastik",
    "dogaustu": "Bilim Kurgu & Fantastik", "supernatural": "Bilim Kurgu & Fantastik",
    "buyu": "Bilim Kurgu & Fantastik", "magic": "Bilim Kurgu & Fantastik",
    "zombi": "Bilim Kurgu & Fantastik", "vampir": "Bilim Kurgu & Fantastik",
    "kiyamet": "Bilim Kurgu & Fantastik", "apocalypse": "Bilim Kurgu & Fantastik",
    "siberpunk": "Bilim Kurgu & Fantastik", "cyberpunk": "Bilim Kurgu & Fantastik",
}


def _norm_key(s: str) -> str:
    """Küçük harf + Türkçe aksan temizliği → harita anahtarı üretir."""
    s = s.strip().lower()
    s = (s.replace("ı", "i").replace("ş", "s").replace("ğ", "g")
           .replace("ü", "u").replace("ö", "o").replace("ç", "c").replace("İ", "i"))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).strip(" .,;:!?-–—*•\"'()[]")
    return s


# ═══════════════════════ AI BAĞLANTISI ═══════════════════════
load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY") or ""

try:
    from openai import OpenAI
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=API_KEY)
    AI_AVAILABLE = True
except ImportError:
    print("⚠️ 'pip install openai python-dotenv' çalıştırın.")
    AI_AVAILABLE = False


# ═══════════════════════ HAVUZ ═══════════════════════
def load_pool():
    if os.path.exists(POOL_JSON):
        try:
            with open(POOL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("⚠️ Havuz bozuk, sıfırdan başlanıyor.")
    return {}


def save_pool(pool):
    tmp = POOL_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
    os.replace(tmp, POOL_JSON)      # atomik yazma


# ═══════════════════════ DB OKUMA (READ-ONLY) ═══════════════════════
def get_missing_genres_readonly():
    uri = f"file:{DB_PATH}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(f"PRAGMA table_info({TABLE_NAME})")
    cols = [r[1] for r in cur.fetchall()]
    print(f"📋 Tablo kolonları: {cols}\n")

    if GENRE_COLUMN not in cols:
        conn.close()
        raise ValueError(f"❌ '{GENRE_COLUMN}' kolonu yok! Mevcut: {cols}")

    id_col   = ID_COLUMN if ID_COLUMN in cols else "rowid"
    year_sel = f", {YEAR_COLUMN} AS _year" if YEAR_COLUMN in cols else ", NULL AS _year"

    cur.execute(f"""
        SELECT {id_col} AS _id, {TITLE_COLUMN} AS _title {year_sel}
        FROM {TABLE_NAME}
        WHERE {GENRE_COLUMN} IS NULL
           OR TRIM({GENRE_COLUMN}) = ''
           OR TRIM({GENRE_COLUMN}) IN ('-','N/A','null','None','Bilinmiyor','Sinema')
        ORDER BY _id
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ═══════════════════════ NORMALİZASYON (KİLİT NOKTA) ═══════════════════════
def normalize_genres(raw_text):
    """AI ne yazarsa yazsın → sadece ALLOWED_GENRES içinden sonuç döndürür."""
    if not raw_text:
        return None

    txt = raw_text.strip()
    txt = re.sub(r'^\s*(türler?|turler?|genres?|tür|tur|cevap|answer)\s*[:\-]\s*',
                 '', txt, flags=re.I)
    txt = txt.replace("\n", ",").replace("|", ",").replace(";", ",")
    txt = txt.replace(" ve ", ",").replace(" and ", ",")
    # "&" ayırıcı DEĞİL (Aksiyon & Macera bozulmasın) → sadece "/" ve "," ayırıcı
    txt = txt.replace("/", ",")

    parts = [p for p in txt.split(",") if p.strip()]
    result = []

    for p in parts:
        key = _norm_key(p)
        if not key or len(key) > 40:
            continue

        hit = GENRE_MAP.get(key)

        # Tam eşleşme yoksa → içerik bazlı arama
        if not hit:
            for k, v in GENRE_MAP.items():
                if len(k) >= 4 and (k in key or key in k):
                    hit = v
                    break

        if hit and hit not in result:
            result.append(hit)
        if len(result) >= MAX_GENRES:
            break

    # Güvenlik: sonuç kesinlikle izinli listede mi?
    result = [g for g in result if g in ALLOWED_GENRES]
    return ", ".join(result) if result else None


# ═══════════════════════ AI ÜRETİM ═══════════════════════
def generate_genre_with_ai(title, year=None):
    if not AI_AVAILABLE:
        return None

    liste = "\n".join(f"- {g}" for g in ALLOWED_GENRES)
    system_prompt = (
        "Sen bir film/dizi tür sınıflandırma motorusun.\n"
        "Sana verilen yapıt için AŞAĞIDAKİ LİSTEDEN en uygun 1 veya 2 türü seç:\n\n"
        f"{liste}\n\n"
        "KESİN KURALLAR:\n"
        "1. SADECE yukarıdaki listedeki ifadeleri, birebir aynı yazımla kullan.\n"
        "2. Liste dışında HİÇBİR tür yazma (Korku, Gerilim, Romantik, Savaş vb. YASAK).\n"
        "   → Korku/Gerilim varsa 'Gizem' yaz.\n"
        "   → Romantik/Tarihi/Biyografi/Müzikal varsa 'Dram' yaz.\n"
        "   → Savaş/Western/Spor/Süper kahraman varsa 'Aksiyon & Macera' yaz.\n"
        "3. Cevabın SADECE tür isimlerinden oluşsun, virgülle ayır.\n"
        "4. Açıklama, tırnak, madde işareti, giriş cümlesi YAZMA.\n"
        "5. En baskın türü başa koy. En fazla 2 tür.\n\n"
        "Örnek çıktı: Aksiyon & Macera, Bilim Kurgu & Fantastik"
    )

    y = f" ({year})" if year else ""
    user_prompt = f"Yapıt: {title}{y}"

    models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
    ]

    for model in models:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt},
                          {"role": "user",   "content": user_prompt}],
                temperature=0.1,      # tutarlılık için çok düşük
                max_tokens=40,
            )
            cleaned = normalize_genres(resp.choices[0].message.content)
            if cleaned:
                return cleaned
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate_limit" in err:
                print(f" (⚠️{model} limit→next)", end="", flush=True)
                time.sleep(1.5)
                continue
            print(f"\n⚠️ Hata ({model}): {e}")
            continue
    return None


# ═══════════════════════ ANA AKIŞ ═══════════════════════
def run(max_to_process=None, save_every=5, use_fallback=True):
    print("=" * 76)
    print("🎭 MATRIX — TÜR ÜRETİCİ  |  SABİT LİSTE MODU  |  READ-ONLY (DB'ye yazmaz)")
    print("=" * 76)
    print("📌 İzinli türler: " + " · ".join(ALLOWED_GENRES))
    print("=" * 76)

    if not os.path.exists(DB_PATH):
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        return

    pool = load_pool()
    print(f"💾 Havuzdaki kayıt: {len(pool)}")

    try:
        missing = get_missing_genres_readonly()
    except Exception as e:
        print(f"❌ DB okuma hatası: {e}")
        return

    todo = [m for m in missing if str(m["_id"]) not in pool]
    print(f"📊 Türü eksik (DB) : {len(missing):,}")
    print(f"🎯 İşlenecek       : {len(todo):,}")
    print("=" * 76)

    if not todo:
        print("🎉 Hepsi hazır! → python tur_yukleyici.py")
        return

    limit = max_to_process or len(todo)
    ok = fb = fail = 0
    stats = {g: 0 for g in ALLOWED_GENRES}
    start = time.time()

    for i, film in enumerate(todo[:limit]):
        fid   = str(film["_id"])
        title = film["_title"] or f"Film#{fid}"
        year  = film.get("_year")
        ytxt  = f" ({year})" if year else ""

        print(f"[{i+1}/{limit}] 🎬 {title[:48]}{ytxt} ...", end="", flush=True)
        genres = generate_genre_with_ai(title, year)

        if not genres and use_fallback:
            genres = FALLBACK
            fb += 1
            tag = "🟡 FALLBACK"
        elif genres:
            ok += 1
            tag = "✅"
        else:
            fail += 1
            print(" ❌ BAŞARISIZ")
            genres = None

        if genres:
            pool[fid] = {"id": film["_id"], "title": title,
                         "yil": year, "turler": genres, "ts": int(time.time())}
            for g in genres.split(", "):
                if g in stats:
                    stats[g] += 1
            print(f" {tag}  →  {genres}")

        if (i + 1) % save_every == 0:
            save_pool(pool)
            el = time.time() - start
            rate = (i + 1) / el if el else 0
            print(f"    💾 kaydedildi | {rate:.2f} film/sn | kalan ~{(limit-i-1)/rate/60:.1f} dk")

        time.sleep(0.35)

    save_pool(pool)
    el = round(time.time() - start, 1)
    print("=" * 76)
    print(f"🎉 BİTTİ ({el}s) | AI: {ok} | Fallback: {fb} | Hata: {fail} | Havuz: {len(pool)}")
    print("\n📊 TÜR DAĞILIMI:")
    for g, c in sorted(stats.items(), key=lambda x: -x[1]):
        if c:
            bar = "█" * min(int(c / max(1, max(stats.values())) * 30), 30)
            print(f"   {g:<26} {c:>4}  {bar}")
    print(f"\n📁 {POOL_JSON}")
    print("👉 Fragman bitince: python tur_yukleyici.py --dry-run")
    print("=" * 76)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="AI Tür Üretici (Sabit Liste)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--save-every", type=int, default=5)
    p.add_argument("--no-fallback", action="store_true",
                   help="AI başarısızsa Dram yazma, boş bırak")
    a = p.parse_args()
    run(max_to_process=a.limit, save_every=a.save_every,
        use_fallback=not a.no_fallback)