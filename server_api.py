import os
import sys
import json
import sqlite3
import re
import hashlib
import hmac
import time
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI

def _load_env_file(path):
    if not os.path.exists(path):
        return
    try:
        for line in open(path, encoding='utf-8'):
            if line.strip() and not line.startswith('#') and '=' in line:
                k, v = line.strip().split('=', 1)
                # Boş / placeholder ezmesin; gerçek key öncelikli kalsın
                val = v.strip().strip('"').strip("'")
                if not val or val == 'your_openai_api_key_here':
                    continue
                if k not in os.environ or not os.environ.get(k) or os.environ.get(k) == 'your_openai_api_key_here':
                    os.environ[k] = val
    except Exception:
        pass

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_load_env_file(os.path.join(_BASE_DIR, '.env'))
_load_env_file(os.path.join(_BASE_DIR, 'backend', '.env'))
_load_env_file('.env')
_load_env_file(os.path.join('backend', '.env'))

sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__)

# GitHub Pages + yerel geliştirme CORS
_cors_raw = os.environ.get(
    'CORS_ORIGINS',
    'https://sancopancooo.github.io,http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000,http://127.0.0.1:3000'
)
_cors_origins = [o.strip() for o in _cors_raw.split(',') if o.strip()]
if os.environ.get('CORS_ALLOW_ALL', '').strip() in ('1', 'true', 'True', 'yes'):
    CORS(app)
else:
    CORS(app, resources={r'/api/*': {'origins': _cors_origins}}, supports_credentials=True)

PORT = int(os.environ.get('PORT', 4000))
MIN_SIMILARITY_THRESHOLD = float(os.environ.get('MIN_SIMILARITY_THRESHOLD', 0.05))
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
SECRET_KEY = os.environ.get('SERVER_SECRET_KEY', 'dizimibul_super_secret_key_2026')
EMBEDDING_MODEL = 'text-embedding-3-small'

# Yönetici kullanıcı adları — yalnızca sunucu env (frontend'e sızmaz)
_ADMIN_RAW = os.environ.get('ADMIN_USERNAMES', 'sancopancoo')
ADMIN_USERNAMES = {u.strip().lower() for u in _ADMIN_RAW.split(',') if u.strip()}


def is_admin_user(username):
    if not username:
        return False
    return str(username).strip().lower() in ADMIN_USERNAMES


def require_admin_request(req):
    ok, username = validate_user_token(req)
    if not ok or not is_admin_user(username):
        return False, None
    return True, username

try:
    from db_paths import (
        EMBEDDINGS_DB_PATH as _EMB_PATH,
        RUNTIME_CACHE_DB_PATH,
        USER_DB_PATH,
        ensure_runtime_cache_schema,
        ensure_user_ops_schema,
        migrate_split_databases,
        resolve_embeddings_path,
    )
    EMBEDDINGS_DB_PATH = resolve_embeddings_path()
    ensure_runtime_cache_schema(RUNTIME_CACHE_DB_PATH)
    ensure_user_ops_schema(USER_DB_PATH)
    try:
        _split_report = migrate_split_databases(
            embeddings_path=EMBEDDINGS_DB_PATH,
            cache_path=RUNTIME_CACHE_DB_PATH,
            user_path=USER_DB_PATH,
            vacuum_embeddings=False,
        )
        if not _split_report.get('skipped'):
            print(f"[+] embeddings.db ayrıldı (motor / cache / kullanıcı): {_split_report}")
        else:
            print(f"[+] DB ayrımı OK ({_split_report.get('reason', 'temiz')})")
    except Exception as _split_err:
        print(f"[!] DB ayrım uyarısı: {_split_err}")
except Exception as e:
    print(f"[!] db_paths yüklenemedi, legacy yollar: {e}")
    EMBEDDINGS_DB_PATH = os.path.join(_BASE_DIR, 'embeddings.db')
    if not os.path.exists(EMBEDDINGS_DB_PATH):
        EMBEDDINGS_DB_PATH = 'embeddings.db'
    RUNTIME_CACHE_DB_PATH = os.path.join(_BASE_DIR, 'runtime_cache.db')
    USER_DB_PATH = os.path.join(_BASE_DIR, 'kullanicilar1.db')

    def ensure_user_ops_schema(path=None):
        return None

    def ensure_runtime_cache_schema(path=None):
        return None

# 🔑 Auth Utils Köprüsü (Veritabanı Kimlik Doğrulama)
try:
    import auth_utils
    auth_utils.init_auth_db()
    HAS_AUTH_UTILS = True
    try:
        from user_db import user_db_backend_name

        print(f"[+] auth_utils veritabanı köprüsü aktif ({user_db_backend_name()}).")
    except Exception:
        print("[+] auth_utils veritabanı köprüsü aktif.")
except Exception as e:
    HAS_AUTH_UTILS = False
    print(f"[!] auth_utils köprü uyarısı: {e}")

# 👥 Sosyal / arkadaşlık + füzyon istekleri
try:
    import db_utils as social_db
    HAS_SOCIAL_DB = True
    print("[+] Sosyal katman (db_utils) aktif.")
except Exception as e:
    social_db = None
    HAS_SOCIAL_DB = False
    print(f"[!] Sosyal katman yüklenemedi: {e}")

# Analytics / GPT cache → runtime_cache.db (yeniden üretilebilir)
def init_analytics_db():
    try:
        conn = sqlite3.connect(RUNTIME_CACHE_DB_PATH)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                item_id TEXT,
                username TEXT,
                rec_source TEXT,
                timestamp REAL
            )
        ''')
        conn.commit()
        conn.close()
        print("[+] Analytics tablosu aktif (runtime_cache.db / analytics_events).")
    except Exception as err:
        print(f"[!] Analytics db uyarısı: {err}")

init_analytics_db()

# --------------------------------------------------------------------------
# İçerik hata bildirimleri → kullanıcı DB (yerel kullanicilar1.db veya Turso)
# --------------------------------------------------------------------------
ERROR_REPORTS_JSON_PATH = os.path.join(_BASE_DIR, 'json_data', 'error_reports.json')
ERROR_REPORT_ALLOWED_FIELDS = {
    'poster', 'title', 'slogan', 'rating', 'year', 'platform', 'status',
    'genres', 'summary', 'why_watch', 'trailer', 'seasons', 'episodes',
    'ep_duration', 'duration', 'other'
}


def _user_db_conn():
    """Hesap / feedback / error reports — Turso varsa oraya, yoksa kullanicilar1.db."""
    try:
        from user_db import connect_user_db

        return connect_user_db(timeout=30.0)
    except Exception:
        conn = sqlite3.connect(USER_DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn


def init_error_reports_store():
    try:
        os.makedirs(os.path.dirname(ERROR_REPORTS_JSON_PATH), exist_ok=True)
        if not os.path.exists(ERROR_REPORTS_JSON_PATH):
            with open(ERROR_REPORTS_JSON_PATH, 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)

        ensure_user_ops_schema(USER_DB_PATH)
        try:
            from user_db import user_db_backend_name

            print(f"[+] Error reports / feedback deposu aktif ({user_db_backend_name()} + json_data/error_reports.json).")
        except Exception:
            print("[+] Error reports / feedback deposu aktif (kullanıcı DB + json_data/error_reports.json).")
    except Exception as err:
        print(f"[!] Error reports store uyarısı: {err}")


def _append_error_report_json(entry):
    try:
        os.makedirs(os.path.dirname(ERROR_REPORTS_JSON_PATH), exist_ok=True)
        reports = []
        if os.path.exists(ERROR_REPORTS_JSON_PATH):
            with open(ERROR_REPORTS_JSON_PATH, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                if isinstance(raw, list):
                    reports = raw
        reports.insert(0, entry)
        reports = reports[:2000]
        with open(ERROR_REPORTS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(reports, f, ensure_ascii=False, indent=2)
    except Exception as err:
        print(f"[!] error_reports.json yazılamadı: {err}")


init_error_reports_store()

# Ağırlıklar (Dinamik Config)
REC_GRAPH_WEIGHT = float(os.environ.get('REC_GRAPH_WEIGHT', 0.70))
REC_VECTOR_WEIGHT = float(os.environ.get('REC_VECTOR_WEIGHT', 0.30))

# 24 Saatlik Sorgu Önbelleği (Query Hash Cache)
QUERY_CACHE = {} # { hash: { 'timestamp': float, 'data': dict } }

# Dataset Metadata Cache for fast genre/keyword negation lookup
DATASET_METADATA_CACHE = {}

openai_client = None
if OPENAI_API_KEY and OPENAI_API_KEY != 'your_openai_api_key_here':
    openai_client = OpenAI(api_key=OPENAI_API_KEY)
    print(f"[+] OpenAI API Key aktif. Model: {EMBEDDING_MODEL} (key ...{OPENAI_API_KEY[-4:]})")
else:
    print(f"[!] OPENAI_API_KEY tanımlı değil. Çevrimdışı yerel vektör motoru çalışıyor.")

try:
    from gpt_enrichment import (
        init_gpt_tables,
        check_ip_search_allowed,
        enrich_with_gpt_notes,
        compose_unique_search_note,
        select_strong_search_targets,
        expand_search_query_concepts,
        is_obvious_nonsense_query,
    )
    init_gpt_tables(RUNTIME_CACHE_DB_PATH)
    HAS_GPT_ENRICH = True
    print("[+] GPT-4o-mini token koruma katmanı aktif (cache + kota + otomatik sorgu genişletme).")
except Exception as e:
    HAS_GPT_ENRICH = False
    compose_unique_search_note = None
    select_strong_search_targets = None
    expand_search_query_concepts = None
    is_obvious_nonsense_query = None
    print(f"[!] GPT enrichment katmanı yüklenemedi: {e}")

def generate_signed_token(username):
    """
    🔐 HMAC-SHA256 İMZALI İSTEMCİ TOKEN ÜRETİCİSİ
    """
    sig = hmac.new(SECRET_KEY.encode('utf-8'), username.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{username}.{sig}"

def validate_user_token(req):
    """
    🔒 SUNUCU TARAFLI GERÇEK İMZALI YETKİLENDİRME (SERVER-SIDE AUTH)
    Sahte Bearer token'ları HMAC-SHA256 imzasıyla doğrular.
    """
    auth_header = req.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1].strip()
        if '.' in token:
            parts = token.split('.', 1)
            username, sig = parts[0], parts[1]
            expected_sig = hmac.new(SECRET_KEY.encode('utf-8'), username.encode('utf-8'), hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig, expected_sig):
                return True, username
        # Development fallback token check
        elif len(token) >= 8 and token.startswith('user_auth_token_'):
            username = token.replace('user_auth_token_', '', 1)
            try:
                from urllib.parse import unquote
                username = unquote(username)
            except Exception:
                pass
            if username and username.lower() not in ('guest', 'kullanıcı', 'kullanici'):
                return True, username
    return False, None

def resolve_gpt_member(req):
    """
    GPT yalnızca HMAC imzalı token ile açılır (bot / sahte Bearer koruması).
    Zayıf user_auth_token_* GPT hakkını açmaz; cosine sistemi yine çalışır.
    """
    auth_header = req.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False, None
    token = auth_header.split(' ', 1)[1].strip()
    if '.' not in token or token.startswith('user_auth_token_'):
        return False, None
    username, sig = token.split('.', 1)
    if not username or username.lower() in ('guest', 'kullanıcı', 'kullanici'):
        return False, None
    expected_sig = hmac.new(SECRET_KEY.encode('utf-8'), username.encode('utf-8'), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected_sig):
        return True, username
    return False, None

def _client_ip(req):
    forwarded = req.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return (req.remote_addr or 'unknown').strip()

def _parse_id_list(raw):
    """JSON dizi veya kırık/string ID listesini güvenli parse eder."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        out = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out
    s = str(raw).strip()
    if not s:
        return []
    try:
        parsed = json.loads(s)
        if isinstance(parsed, list):
            return _parse_id_list(parsed)
    except Exception:
        pass
    return [int(x) for x in re.findall(r'\d+', s)]


def get_item_metadata(item_id, media_type):
    """
    🗄️ SQLite Veritabanından Yapımın Tür, Afiş, Özet, Puan ve Detaylarını Getirir
    """
    if item_id in DATASET_METADATA_CACHE:
        return DATASET_METADATA_CACHE[item_id]

    raw_id = item_id.split('_')[-1]
    try:
        from db_paths import series_db_path, movies_db_path
        db_path = series_db_path() if media_type == 'SERIES' else movies_db_path()
    except Exception:
        db_path = 'katalog.db'
    table_name = 'diziler' if media_type == 'SERIES' else 'filmler'
    tur_col = 'tur' if media_type == 'SERIES' else 'turler'
    puan_col = 'puan_ortalamasi' if media_type == 'SERIES' else 'puan'
    poster_col = 'afis_url' if media_type == 'SERIES' else 'poster_url'
    year_col = 'cikis_tarihi' if media_type == 'SERIES' else 'vizyon_tarihi'
    duration_col = 'sezon_sayisi' if media_type == 'SERIES' else 'sure'
    trailer_dub_col = 'trailer_tr_url' if media_type == 'SERIES' else 'trailer_dub_url'
    trailer_sub_col = 'trailer_original_url' if media_type == 'SERIES' else 'trailer_sub_url'

    meta = {
        'genres': '',
        'keywords': '',
        'title': '',
        'original_title': '',
        'primary_genre': '',
        'rating': 7.0,
        'votes': 500,
        'poster_url': '',
        'summary': '',
        'platform': 'Netflix',
        'year': '',
        'duration_or_seasons': '1 Sezon' if media_type == 'SERIES' else '110 dk',
        'trailer_dub_url': '',
        'trailer_sub_url': '',
        'director': '',
        'tmdb_id': '',
        'onerilen_ids': [],
        'benzer_ids': [],
        'status': '',
    }

    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            if media_type == 'SERIES':
                query = (
                    f"SELECT isim, {tur_col}, anahtar_kelimeler, {puan_col}, oy_sayisi, {poster_col}, "
                    f"ozet, platformlar, {year_col}, {duration_col}, {trailer_dub_col}, {trailer_sub_col}, "
                    f"onerilen_idleri, benzer_idleri, durum FROM {table_name} WHERE id = ?"
                )
                c.execute(query, (raw_id,))
                row = c.fetchone()
                conn.close()
                if row:
                    meta['title'] = str(row[0] or '')
                    meta['original_title'] = meta['title']
                    meta['genres'] = str(row[1] or '')
                    meta['keywords'] = str(row[2] or '')
                    meta['poster_url'] = str(row[5] or '')
                    meta['summary'] = str(row[6] or '')
                    meta['platform'] = str(row[7] or 'Netflix')
                    meta['year'] = str(row[8] or '')[:4]
                    dur_val = row[9]
                    meta['duration_or_seasons'] = f"{dur_val} Sezon" if dur_val else "1 Sezon"
                    meta['trailer_dub_url'] = str(row[10] or '')
                    meta['trailer_sub_url'] = str(row[11] or '')
                    meta['tmdb_id'] = str(raw_id)
                    meta['onerilen_ids'] = _parse_id_list(row[12])
                    meta['benzer_ids'] = _parse_id_list(row[13])
                    meta['status'] = str(row[14] or '')
            else:
                query = (
                    f"SELECT isim, orijinal_isim, {tur_col}, anahtar_kelimeler, {puan_col}, oy_sayisi, "
                    f"{poster_col}, ozet, platformlar, {year_col}, {duration_col}, {trailer_dub_col}, "
                    f"{trailer_sub_col}, yonetmen, tmdb_id, onerilen_idleri, benzer_idleri "
                    f"FROM {table_name} WHERE id = ?"
                )
                c.execute(query, (raw_id,))
                row = c.fetchone()
                conn.close()
                if row:
                    meta['title'] = str(row[0] or '')
                    meta['original_title'] = str(row[1] or row[0] or '')
                    meta['genres'] = str(row[2] or '')
                    meta['keywords'] = str(row[3] or '')
                    meta['poster_url'] = str(row[6] or '')
                    meta['summary'] = str(row[7] or '')
                    meta['platform'] = str(row[8] or 'Netflix')
                    meta['year'] = str(row[9] or '')[:4]
                    dur_val = row[10]
                    meta['duration_or_seasons'] = f"{dur_val} dk" if dur_val else "110 dk"
                    meta['trailer_dub_url'] = str(row[11] or '')
                    meta['trailer_sub_url'] = str(row[12] or '')
                    meta['director'] = str(row[13] or '').strip()
                    meta['tmdb_id'] = str(row[14] or '').strip()
                    meta['onerilen_ids'] = _parse_id_list(row[15])
                    meta['benzer_ids'] = _parse_id_list(row[16])
                    try:
                        meta['rating'] = float(row[4]) if row[4] is not None else 7.0
                    except (ValueError, TypeError):
                        meta['rating'] = 7.0
                    try:
                        meta['votes'] = int(row[5]) if row[5] is not None else 500
                    except (ValueError, TypeError):
                        meta['votes'] = 500

            if media_type == 'SERIES' and row:
                try:
                    meta['rating'] = float(row[3]) if row[3] is not None else 7.0
                except (ValueError, TypeError):
                    meta['rating'] = 7.0
                try:
                    meta['votes'] = int(row[4]) if row[4] is not None else 500
                except (ValueError, TypeError):
                    meta['votes'] = 500

            if meta['title']:
                g_list = [g.strip() for g in meta['genres'].split(',') if g.strip()]
                meta['primary_genre'] = g_list[0] if g_list else ''
        except Exception as e:
            print(f"[!] Metadata fetch error for {item_id}: {e}")

    DATASET_METADATA_CACHE[item_id] = meta
    return meta

def extract_negations(query_text):
    """
    🚫 REGEX NEGATİF SÜZGEÇ (NEGATION FILTER)
    "aksiyon olsun ama komedi olmasın", "korku hariç", "dram olmasın"
    """
    lowered = query_text.lower()
    negated_terms = []
    
    patterns = [
        r'(\w+)\s+(?:olmasın|istemiyorum|hariç|değil|dışında|olmadan)',
        r'(?:ne\s+de|hiç)\s+(\w+)'
    ]
    for p in patterns:
        matches = re.findall(p, lowered)
        for m in matches:
            if len(m) > 2:
                negated_terms.append(m)
                
    return list(set(negated_terms))


# ─── TEMA SÖZLÜĞÜ: yalnız yumuşak zenginleştirme (zorunlu değil) ───
# Asıl kapı open-vocabulary intent ile çalışır; burası bilinen temalara ekstra
# embedding/lexical boost verir. Yeni senaryolar için sözlüğe eklemek ZORUNLU DEĞİL.
THEME_EXPAND = {
    'ortaçağ': ['medieval', 'feodal', 'şövalye', 'knight', 'period drama', 'dark ages'],
    'ortacag': ['medieval', 'feodal', 'şövalye', 'knight', 'period drama'],
    'uzay': ['space', 'galaxy', 'alien', 'spaceship', 'sci-fi', 'bilimkurgu'],
    'uzay yolculuğu': ['space travel', 'spaceship', 'astronaut', 'nasa', 'galaxy', 'interstellar'],
    'uzay yolculugu': ['space travel', 'spaceship', 'astronaut', 'galaxy'],
    # 'undead' bilerek expand'te yok — başlık tuzağı (Undead Unluck). Embedding'e
    # zombie/apocalypse yeter; soft-expand title hit'i ayrıca zayıflatılıyor.
    'zombi': ['zombie', 'apocalypse', 'walking dead', 'walkers', 'enfekte', 'salgın'],
    'zombie': ['zombi', 'apocalypse', 'walking dead', 'walkers', 'enfekte'],
    'vampir': ['vampire', 'gothic', 'immortal'],
    'hapishane': [
        'prison', 'cezaevi', 'mahkum', 'inmate', 'penitentiary', 'warden',
        'koğuş', 'hücre', 'parmaklık', 'gardiyan',
        'prison break', 'vis a vis', 'orange is the new black', 'wentworth', 'oz',
    ],
    'cezaevi': ['hapishane', 'prison', 'mahkum', 'inmate', 'prison break', 'vis a vis'],
    'prison': ['hapishane', 'cezaevi', 'mahkum', 'inmate', 'prison break'],
    'casus': ['spy', 'espionage', 'ajan', 'cia', 'fbi'],
    'vahşi batı': ['western', 'cowboy', 'wild west', 'frontier'],
    'vahsi bati': ['western', 'cowboy', 'wild west'],
    'western': ['vahşi batı', 'cowboy', 'frontier'],
    'zeki': ['intellectual', 'genius', 'mastermind', 'mind games', 'strategist'],
    'bilimkurgu': ['sci-fi', 'science fiction', 'uzay', 'distopya'],
    'bilim kurgu': ['sci-fi', 'science fiction'],
    # Tema soft-expand (film+dizi): "beyin yakan" -> dragon/ejderha sizmasin
    'beyin yakan': [
        'mind-bending', 'mind bending', 'nonlinear', 'non-linear', 'time travel',
        'time paradox', 'zihin bükücü', 'karmaşık kurgu', 'reality bending',
        'psychological puzzle', 'twist ending', 'inception', 'tenet', 'başlangıç',
        'prestij', 'memento', 'akıl defteri', 'dövüş kulübü', 'shutter island',
    ],
    'beyinyakan': ['mind-bending', 'nonlinear', 'time travel', 'zihin bükücü', 'başlangıç', 'tenet'],
    'zihin bükücü': ['mind-bending', 'mind bending', 'nonlinear', 'beyin yakan', 'time travel', 'paradoks'],
    'zihin bukucu': ['mind-bending', 'nonlinear', 'beyin yakan', 'time travel'],
    'kafa karıştıran': ['mind-bending', 'confusing plot', 'nonlinear', 'beyin yakan', 'paradoks'],
    'kafa karistiran': ['mind-bending', 'nonlinear', 'beyin yakan'],
    'mind bending': ['beyin yakan', 'zihin bükücü', 'nonlinear', 'time travel', 'başlangıç'],
    'mind-bending': ['beyin yakan', 'zihin bükücü', 'nonlinear', 'time travel', 'başlangıç'],
    'zaman yolculuğu': ['time travel', 'time loop', 'time paradox', 'temporal', 'tenet', 'looper'],
    'zaman yolculugu': ['time travel', 'time loop', 'time paradox'],
}

HYBRID_VECTOR_WEIGHT = 0.46
HYBRID_LEXICAL_WEIGHT = 0.22
HYBRID_INTENT_WEIGHT = 0.12
HYBRID_GRAPH_WEIGHT = 0.13
HYBRID_DIRECTOR_WEIGHT = 0.07
MIN_HYBRID_SCORE = 0.28
RELATIVE_GAP_RATIO = 0.55
SEARCH_SAFETY_CAP = 800
# Kullanıcıya dönen liste tavanı (iç skorlama daha geniş havuzda kalır)
# Niyetli/tema aramalarda SEARCH_SAFETY_CAP'e kadar TÜM eşleşmeler döner (GPT notu ayrı, max 10)
SEARCH_RETURN_CAP = 40
UNTHEMED_SEARCH_CAP = 48
MAX_SAME_DIRECTOR_IN_TOP = 2
ANCHOR_VECTOR_BLEND = 0.55
GRAPH_SEED_VECTOR_BLEND = 0.15
ANCHOR_GAP_RATIO = 0.50
INTENT_SEMANTIC_FLOOR = 0.28
# Embedding-first: sözlük/soft-expand OLMADAN da bu cosine ile kapı açılır
INTENT_COSINE_BYPASS = 0.32
GPT_SEARCH_NOTE_MAX = 10
# En iyi sonuç bile bundan zayıfsa → anlamsız / alakasız sorgu
SEARCH_MIN_TOP_COSINE = 0.30
SEARCH_MIN_TOP_HYBRID = 0.22
# AI Tavsiyeler: en az bu kadar kitaplık öğesi olmadan kişiselleştirme anlamsız
MIN_LIBRARY_FOR_AI = 5
AI_VISIBLE_SLOTS = 15
AI_OVERFLOW_CAP = 40

# Hapishane teması — yan bahis (Avengers hapishane kaçışı) gürültüsünü kes
_PRISON_TITLE_HINTS = (
    'prison break', 'vis a vis', 'orange is the new black', 'wentworth', 'oz',
    'banshee', 'papillon', 'shawshank', 'escape plan', 'locked up',
)
_PRISON_STRONG = (
    'cezaevi', 'mahkum', 'koğuş', 'hücre', 'parmaklık', 'inmate', 'penitentiary',
    'gardiyan', 'warden', 'hapis cezası', 'prison break', 'vis a vis',
    'orange is the new black', 'wentworth',
)
_PRISON_NOISE = (
    'avengers', "earth's mightiest", 'marvel animation', 'süper kahraman',
    'superhero', 'dc comics',
)

# Zombi teması — "Undead Unluck" gibi yalnız başlıkta undead geçenleri ele
_ZOMBIE_TITLE_HINTS = (
    'the walking dead', 'fear the walking dead', 'the last of us', 'last of us',
    'z nation', 'i zombie', 'izombie', 'dead set', 'train to busan',
    'world war z', '28 days later', '28 weeks later', 'dawn of the dead',
    'night of the living dead', 'army of the dead', 'all of us are dead',
    'kingdom', 'sweet home', '#alive', 'peninsula', 'shaun of the dead',
)
_ZOMBIE_STRONG = (
    'zombi', 'zombie', 'zombies', 'walking dead', 'walkers', 'ölü yürüyen',
    'zombie apocalypse', 'zombi salgın', 'undead horde', 'living dead',
)
# Soft-expand / lexical: yalnız başlıkta geçince yüksek puan vermesin
_TITLE_WEAK_SOFT_TOKENS = frozenset({
    'undead', 'dead', 'alive', 'good', 'bad', 'new', 'last', 'first', 'next',
    'house', 'home', 'world', 'war', 'night', 'day', 'man', 'boy', 'girl',
    'love', 'dark', 'power', 'force', 'legend', 'legacy', 'origin', 'origins',
    'kingdom', 'place', 'doctor', 'office', 'black', 'white', 'red', 'blue',
    'big', 'little', 'one', 'two', 'life', 'death', 'city', 'land', 'story',
    'game', 'games', 'star', 'stars', 'true', 'real', 'american', 'secret',
})

_SEARCH_STOP = {
    'bir', 've', 'ile', 'icin', 'için', 'olan', 'olarak', 'gibi', 'cok', 'çok',
    'da', 'de', 'ki', 'bu', 'su', 'şu', 'o', 'ben', 'sen', 'biz', 'siz',
    'dizi', 'dizisi', 'diziler', 'film', 'filmi', 'filmler', 'izlemek', 'istiyorum', 'isterim',
    'arıyorum', 'ariyorum', 'ara', 'ne', 'tur', 'tür', 'gecen', 'geçen', 'olsun',
    'bana', 'lutfen', 'lütfen', 'the', 'a', 'an', 'of', 'in', 'on',
    'bas', 'baş', 'rol', 'rolu', 'rolü', 'basrol', 'başrol', 'yapim', 'yapım', 'yapimlar', 'yapımlar',
    'benzeri', 'tarzi', 'tarzı', 'ayari', 'ayarı', 'temali', 'temalı', 'hakkinda', 'hakkında',
    'var', 'mi', 'mı', 'musun', 'misin', 'öner', 'oner', 'oneri', 'öneri',
    'konulu', 'atmosferli', 'tarzinda', 'tarzında', 'seklinde', 'şeklinde', 'modu', 'modunda'
}

_TITLE_INDEX = {}  # media_type -> [{id, title, original, title_norm, tokens}]
_TMDB_TO_ITEM = {}  # media_type -> {tmdb_id_str: item_id}
_INTENT_VEC_CACHE = {}  # phrase -> embedding


def _normalize_tr(text):
    t = str(text or '').lower()
    for a, b in [('ı', 'i'), ('ğ', 'g'), ('ü', 'u'), ('ş', 's'), ('ö', 'o'), ('ç', 'c'), ('İ', 'i')]:
        t = t.replace(a, b)
    return t


def _word_boundary_hit(haystack_norm, token_norm):
    if not token_norm or not haystack_norm:
        return False
    if len(token_norm) <= 3:
        return re.search(rf'(?<![a-z0-9]){re.escape(token_norm)}(?![a-z0-9])', haystack_norm) is not None
    return token_norm in haystack_norm


def _text_has_token(haystack, token):
    if not token or not haystack:
        return False
    h = haystack.lower()
    t = token.lower()
    h_norm = _normalize_tr(h)
    t_norm = _normalize_tr(t)
    if ' ' in t or ' ' in t_norm:
        return t in h or t_norm in h_norm
    # Kısa kökler: "dahi"⊂"dahil", "bas"⊂"baslangic" tuzağını kes
    if len(t_norm) <= 5:
        return _word_boundary_hit(h_norm, t_norm) or _word_boundary_hit(_normalize_tr(h), t_norm)
    if t in h or t_norm in h_norm:
        return True
    return False


def tokenize_query(query_text):
    parts = re.split(r'[^\wığüşöçİĞÜŞÖÇ0-9]+', str(query_text or '').lower())
    out = []
    for w in parts:
        w = w.strip()
        if len(w) < 2:
            continue
        if w in _SEARCH_STOP or _normalize_tr(w) in _SEARCH_STOP:
            continue
        if len(_normalize_tr(w)) <= 2:
            continue
        out.append(w)
    return out


def _soft_expand_terms(phrases, tokens):
    """Bilinen temalara opsiyonel synonym boost — bilinmeyenler için no-op."""
    extra = []
    corpus = ' '.join(list(phrases) + list(tokens)).lower()
    corpus_n = _normalize_tr(corpus)
    for key, values in THEME_EXPAND.items():
        k = key.lower()
        if k in corpus or _normalize_tr(k) in corpus_n:
            for v in values:
                if v not in extra:
                    extra.append(v)
    return extra


def extract_open_intent(text):
    """
    Açık kelime dağarcığı niyet çıkarıcı.
    'zeki', 'ortaçağ', 'vahşi batı', 'uzay bilim', 'steampunk'... hepsi aynı yoldan geçer.
    Sözlüğe eklemek zorunda değilsin.
    """
    raw = str(text or '').strip()
    if not raw:
        return {'phrases': [], 'tokens': [], 'embed_text': '', 'soft_expand': []}

    phrases = []
    patterns = [
        r'(.+?)\s+temal[ıi]',
        r'(.+?)\s+konulu',
        r'(.+?)\s+atmosferli',
        r'(.+?)\s+tarz[ıi]',
        r'(.+?)\s+modunda',
        r'baş\s*rol[uüye]*\s+(.+?)(?=\s+olan|\s+film|\s+dizi|\s+yapım|$)',
        r'bas\s*rol[uye]*\s+(.+?)(?=\s+olan|\s+film|\s+dizi|\s+yapim|$)',
        r'(.+?)\s+olan\s+(?:film|dizi|yapım|yapim)',
        r'(.+?)\s+ge[cç]en',
        r'(.+?)\s+(?:filmler|diziler|film|dizi|yapımlar|yapimlar)\b',
        r'(.+?)\s+istiyorum',
    ]
    for p in patterns:
        for m in re.finditer(p, raw, flags=re.IGNORECASE):
            phrase = re.sub(r'\s+', ' ', m.group(1).strip(' .,!?:;'))
            # Stop-word ağırlıklı artık parçaları temizle
            toks = tokenize_query(phrase)
            if toks:
                cleaned = ' '.join(toks)
                if cleaned and cleaned not in phrases:
                    phrases.append(cleaned)

    tokens = tokenize_query(raw)

    # Kalıp yoksa: tüm ayırt edici token'lar tek niyet birimi + bigram'lar
    if not phrases and tokens:
        phrases.append(' '.join(tokens))
        if len(tokens) >= 2:
            for i in range(len(tokens) - 1):
                bigram = f"{tokens[i]} {tokens[i + 1]}"
                if bigram not in phrases:
                    phrases.append(bigram)

    # Çok uzun phrase'leri budama
    phrases = [p for p in phrases if 1 <= len(p) <= 60][:6]
    soft = _soft_expand_terms(phrases, tokens)
    embed_text = raw
    if phrases:
        embed_text = f"{raw} | niyet: {', '.join(phrases)}"
    if soft:
        embed_text = f"{embed_text} | kavramlar: {', '.join(soft[:16])}"

    return {
        'phrases': phrases,
        'tokens': tokens,
        'embed_text': embed_text,
        'soft_expand': soft,
    }


def expand_query_for_embedding(query_text, extra_terms=None):
    intent = extract_open_intent(query_text)
    extra = list(intent.get('soft_expand') or [])
    for w in (extra_terms or []):
        w = str(w).strip()
        if w and w not in extra:
            extra.append(w)
    base = intent.get('embed_text') or query_text
    if not extra:
        return base
    return f"{base} | temalar: {', '.join(extra[:40])}"


def detect_themes(query_text):
    """Geriye dönük uyumluluk: open intent phrase anahtarlarını döndürür."""
    intent = extract_open_intent(query_text)
    return [{'key': p, 'expand': intent.get('soft_expand') or [], 'gate_strong': [], 'gate_combo_a': [], 'gate_combo_b': []} for p in intent['phrases']]


def get_intent_embedding(phrase):
    key = (phrase or '').strip().lower()
    if not key:
        return None
    if key in _INTENT_VEC_CACHE:
        return _INTENT_VEC_CACHE[key]
    soft = _soft_expand_terms([phrase], tokenize_query(phrase))
    text = phrase if not soft else f"{phrase} | {', '.join(soft[:10])}"
    vec = get_query_embedding(text)
    _INTENT_VEC_CACHE[key] = vec
    return vec


def intent_lexical_coverage(title, keywords, genres, summary, intent):
    """Niyet birimlerinin meta üzerinde lexical kapsaması (0..1). Keyword/tür öncelikli."""
    if not intent or (not intent.get('phrases') and not intent.get('tokens')):
        return 0.0
    title_s = title or ''
    kw_scope = f"{title_s} {keywords or ''} {genres or ''}".lower()
    full = f"{kw_scope} {summary or ''}".lower()
    score = 0.0
    checks = 0

    for phrase in intent.get('phrases') or []:
        checks += 1
        parts = [t for t in phrase.split() if len(t) > 1]
        if _text_has_token(kw_scope, phrase):
            score += 1.0
        elif parts and all(_text_has_token(kw_scope, t) for t in parts):
            score += 0.9
        elif _text_has_token(full, phrase):
            score += 0.45
        elif parts and all(_text_has_token(full, t) for t in parts):
            score += 0.35

    # Çok kelimeli niyet varsa tekil token'ları atla ("beyin" → yanlış pozitif)
    phrase_tok_skip = set()
    for phrase in intent.get('phrases') or []:
        parts = [t for t in phrase.split() if len(t) > 1]
        if len(parts) >= 2:
            phrase_tok_skip.update(parts)

    for tok in intent.get('tokens') or []:
        if tok in phrase_tok_skip:
            continue
        checks += 0.35
        if _text_has_token(kw_scope, tok):
            score += 0.35
        elif _text_has_token(full, tok):
            score += 0.12

    for soft in intent.get('soft_expand') or []:
        checks += 0.25
        in_title = _text_has_token(title_s, soft)
        in_kw = _text_has_token(kw_scope, soft)
        in_full = _text_has_token(full, soft)
        weak = _is_title_weak_soft_token(soft)
        if in_title and weak and not _text_has_token(f"{keywords or ''} {genres or ''} {summary or ''}", soft):
            # Undead Unluck / The Good Place: yalnız başlık soft-hit → cılız puan
            score += 0.12
        elif in_title:
            score += 0.95
        elif in_kw:
            score += 0.55
        elif in_full:
            score += 0.22

    if checks <= 0:
        return 0.0
    return min(1.0, score / max(1.0, min(checks, 3.0)))


def intent_semantic_coverage(item_vec, intent_vecs):
    if not intent_vecs or item_vec is None:
        return 0.0
    best = 0.0
    hits = 0
    for iv in intent_vecs:
        sim = cosine_similarity(iv, item_vec)
        best = max(best, sim)
        if sim >= INTENT_SEMANTIC_FLOOR:
            hits += 1
    return min(1.0, (0.65 * best) + (0.35 * (hits / max(1, len(intent_vecs)))))


def passes_open_intent_gate(
    title, keywords, genres, summary, intent, item_vec, intent_vecs,
    cosine_main, graph_hit=False, director_hit=False
):
    """
    Embedding-first açık niyet kapısı.
    THEME_EXPAND sözlüğü ZORUNLU DEĞİL — bilinmeyen cümleler (beyin yakan,
    steampunk, folk horror...) asıl olarak query↔item cosine ile geçer.
    Soft-expand varsa ekstra lexical boost; yoksa semantik yeter.
    """
    phrases = (intent or {}).get('phrases') or []
    tokens = (intent or {}).get('tokens') or []
    if not phrases and not tokens:
        return True
    if graph_hit or director_hit:
        return True
    # Ana yol: sorgu vektörü yeterince yakınsa sözlüğe bakmadan geç
    if cosine_main >= INTENT_COSINE_BYPASS:
        return True

    soft_list = (intent or {}).get('soft_expand') or []
    scope = f"{title or ''} {keywords or ''} {genres or ''}"
    body = f"{keywords or ''} {genres or ''} {summary or ''}"
    full = f"{scope} {summary or ''}"
    for soft in soft_list:
        weak = _is_title_weak_soft_token(soft)
        # Zayıf token yalnız başlıkta → kapı açma (Undead Unluck / Good Place)
        if weak and _text_has_token(title or '', soft) and not _text_has_token(body, soft):
            continue
        if _text_has_token(title or '', soft) or _text_has_token(scope, soft):
            return True
        if _text_has_token(full, soft) and cosine_main >= 0.22:
            return True

    lex = intent_lexical_coverage(title, keywords, genres, summary, intent)
    if lex >= 0.32:
        return True

    sem = intent_semantic_coverage(item_vec, intent_vecs)
    if sem >= 0.34 and cosine_main >= 0.18:
        return True
    if sem >= 0.48:
        return True

    if lex >= 0.16 and sem >= 0.28 and cosine_main >= 0.18:
        return True
    return False


def inject_theme_graph_neighbors(
    scored, emb_lookup, media_type, query_vec, intent, intent_vecs,
    exclude_set, anchor_ids=None, max_seeds=15, max_inject=60
):
    """
    Tema aramasında üst sonuçların TMDb onerilen/benzer komşularını enjekte eder.
    Örn. Fear/TWD → Daryl Dixon, World Beyond (embedding varsa).
    """
    if not scored:
        return scored
    have = {str(s['id']) for s in scored}
    exclude = set(exclude_set or set())
    anchors = set(anchor_ids or set())
    neighbor_ids = []
    seen_n = set()

    for seed in scored[:max_seeds]:
        meta = get_item_metadata(seed['id'], media_type)
        for tid in (meta.get('onerilen_ids') or []) + (meta.get('benzer_ids') or []):
            for nid in resolve_graph_item_ids([tid], media_type):
                if nid in seen_n or nid in have or nid in exclude or nid in anchors:
                    continue
                seen_n.add(nid)
                neighbor_ids.append(nid)

    injected = []
    for nid in neighbor_ids:
        if len(injected) >= max_inject:
            break
        packed = emb_lookup.get(nid)
        if not packed:
            continue
        cand_vec = packed['vec']
        cosine = cosine_similarity(query_vec, cand_vec)
        if cosine < (MIN_SIMILARITY_THRESHOLD * 0.25):
            continue
        meta = get_item_metadata(nid, media_type)
        title = meta.get('title') or packed.get('title') or ''
        keywords = meta.get('keywords') or ''
        genres = meta.get('genres') or ''
        summary = meta.get('summary') or ''
        intent_cov = 0.0
        if intent and (intent.get('phrases') or intent.get('tokens')):
            intent_cov = max(
                intent_lexical_coverage(title, keywords, genres, summary, intent),
                intent_semantic_coverage(cand_vec, intent_vecs)
            )
        soft_title = any(
            _text_has_token(title, soft)
            for soft in ((intent or {}).get('soft_expand') or [])
        )
        if not soft_title and intent_cov < 0.18 and cosine < 0.28:
            continue
        hybrid = (
            (HYBRID_VECTOR_WEIGHT * cosine)
            + (HYBRID_INTENT_WEIGHT * intent_cov)
            + (HYBRID_GRAPH_WEIGHT * 1.0)
            + (0.08 if soft_title else 0.0)
        )
        hybrid = max(hybrid, 0.36)
        injected.append({
            'id': nid,
            'title': title,
            'director': (meta.get('director') or '').strip(),
            'rawSimilarity': round(cosine, 4),
            'hybridScore': hybrid,
            'lexical': 0.0,
            'intentCoverage': round(max(intent_cov, 0.55 if soft_title else intent_cov), 4),
            'graphHit': True,
            'directorHit': False,
        })
        have.add(nid)

    if not injected:
        return scored
    merged = list(scored) + injected
    merged.sort(key=lambda x: x['hybridScore'], reverse=True)
    return merged


def lexical_score(meta_text, title_text, themes, query_tokens, bonus_terms=None, intent=None):
    full = f"{title_text or ''} {meta_text or ''}".lower()
    title = (title_text or '').lower()
    body = (meta_text or '').lower()
    raw = 0.0
    hits = 0

    def score_token(token, w_title, w_body):
        nonlocal raw, hits
        if not token or len(token) < 2:
            return
        in_title = _text_has_token(title, token)
        in_body = _text_has_token(body, token)
        if in_title and not in_body and _is_title_weak_soft_token(token):
            # The Good / Undead gibi zayıf başlık kelimeleri tek başına şişirmesin
            raw += min(w_title, w_body) * 0.35
            hits += 0.25
        elif in_title:
            raw += w_title
            hits += 1
        elif _text_has_token(full, token):
            raw += w_body
            hits += 1

    for t in (query_tokens or []):
        score_token(t, 0.12, 0.06)
    # themes artık open-intent uyumluluk listesi olabilir
    for th in themes or []:
        for t in th.get('expand', []) or []:
            score_token(t, 0.16, 0.10)
    if intent:
        for p in intent.get('phrases') or []:
            score_token(p, 0.22, 0.16)
            for t in p.split():
                score_token(t, 0.14, 0.09)
        for t in intent.get('soft_expand') or []:
            score_token(t, 0.14, 0.10)
    for t in (bonus_terms or []):
        score_token(t, 0.18, 0.12)

    if hits == 0:
        return 0.0
    return min(1.0, raw)


def passes_hard_gate(meta_text, title_text, themes, keywords_text=''):
    """Eski imza — open intent yoksa no-op; varsa themes phrase'lerini yumuşak kontrol."""
    if not themes:
        return True
    # Open-vocabulary'ye bırak: burada reddetme
    return True


def _is_prison_theme_query(query_text):
    q = _normalize_tr(query_text or '')
    keys = ('hapishane', 'cezaevi', 'prison', 'mahkum', 'parmaklik', 'koğuş', 'kogus')
    return any(k in q for k in keys)


def _is_zombie_theme_query(query_text):
    q = _normalize_tr(query_text or '')
    keys = ('zombi', 'zombie', 'zombies', 'olu yuruyen', 'walking dead', 'undead')
    return any(k in q for k in keys)


def _is_title_weak_soft_token(token):
    t = _normalize_tr(str(token or '').strip().lower())
    if not t:
        return True
    if ' ' in t:
        # Çok kelimeli soft (walking dead) güçlü sayılır
        return False
    return t in _TITLE_WEAK_SOFT_TOKENS or len(t) <= 3


def _title_hint_hit(title, hints, *, exact_only_short=False):
    t = (title or '').lower().strip()
    tn = _normalize_tr(t)
    for hint in hints:
        h = (hint or '').lower().strip()
        if not h:
            continue
        if t == h or tn == _normalize_tr(h):
            return True
        if len(h) <= 3:
            if re.search(rf'(?<![a-z0-9]){re.escape(_normalize_tr(h))}(?![a-z0-9])', tn):
                return True
        elif exact_only_short and len(h.split()) == 1 and len(h) <= 10:
            # "kingdom" ⊂ "the last kingdom" tuzağı — tek kelimelik kısa hint yalnız tam başlık
            continue
        elif h in t or _normalize_tr(h) in tn:
            return True
    return False


def passes_prison_theme_filter(title, summary, keywords='', genres=''):
    """Hapishane sorgusunda Avengers vb. yan bahisleri ele; Vis a Vis / OITNB'yi geçir."""
    title_s = title or ''
    full = f"{title_s} {summary or ''} {keywords or ''} {genres or ''}".lower()
    full_n = _normalize_tr(full)

    if _title_hint_hit(title_s, _PRISON_TITLE_HINTS):
        return True

    if any(n in full or _normalize_tr(n) in full_n for n in _PRISON_NOISE):
        # Süper kahraman gürültüsü: gerçek hapishane kanıtı yoksa red
        if not any(_text_has_token(full, s) for s in _PRISON_STRONG):
            return False

    if any(_text_has_token(full, s) for s in _PRISON_STRONG):
        return True

    # Zayıf tekil "hapishane" + kaçış yan bahsi yetmez
    has_hapishane = _text_has_token(full, 'hapishane') or _text_has_token(full, 'prison') or _text_has_token(full, 'hapis')
    has_core = any(_text_has_token(full, s) for s in ('mahkum', 'cezaevi', 'koğuş', 'hücre', 'parmaklık', 'gardiyan', 'inmate'))
    return bool(has_hapishane and has_core)


def passes_zombie_theme_filter(title, summary, keywords='', genres=''):
    """Zombi sorgusunda başlık-yalnız 'undead' tuzağını (Undead Unluck) ele."""
    title_s = title or ''
    body = f"{summary or ''} {keywords or ''} {genres or ''}".lower()
    full = f"{title_s} {body}".lower()

    # Tek kelimelik kısa hint'ler (kingdom, peninsula) yalnız tam başlık eşleşsin
    if _title_hint_hit(title_s, _ZOMBIE_TITLE_HINTS, exact_only_short=True):
        return True

    if any(_text_has_token(full, s) for s in _ZOMBIE_STRONG):
        return True

    # 'undead' yalnız başlıkta → red; özet/keyword'de salgın/apokalips ile birlikte → geç
    if _text_has_token(full, 'undead'):
        if _text_has_token(body, 'undead') and any(
            _text_has_token(full, s) for s in ('salgın', 'apocalypse', 'enfekte', 'outbreak', 'horde', 'walker')
        ):
            return True
        return False

    has_salgin = any(_text_has_token(full, s) for s in ('salgın', 'apocalypse', 'outbreak', 'enfekte', 'infected'))
    has_survival = any(_text_has_token(full, s) for s in ('hayatta kalma', 'survival', 'kıyamet', 'post-apocalyptic'))
    return bool(has_salgin and has_survival)


def _blend_vectors(base_vec, extra_vecs, weights):
    if not extra_vecs:
        return base_vec
    a = np.array(base_vec, dtype=np.float32)
    acc = a * float(weights[0] if weights else 1.0)
    w_sum = float(weights[0] if weights else 1.0)
    for i, v in enumerate(extra_vecs):
        w = float(weights[i + 1]) if weights and len(weights) > i + 1 else (1.0 / (len(extra_vecs) + 1))
        b = np.array(v, dtype=np.float32)
        if b.shape != a.shape:
            continue
        acc = acc + b * w
        w_sum += w
    if w_sum <= 0:
        return base_vec
    acc = acc / w_sum
    n = float(np.linalg.norm(acc)) or 1.0
    return (acc / n).tolist()


def _ensure_title_index(media_type):
    if media_type in _TITLE_INDEX:
        return _TITLE_INDEX[media_type]
    entries = []
    tmdb_map = {}

    try:
        from db_paths import series_db_path, movies_db_path
        db_path = series_db_path() if media_type == 'SERIES' else movies_db_path()
    except Exception:
        db_path = 'katalog.db'
    if not os.path.exists(db_path):
        _TITLE_INDEX[media_type] = entries
        _TMDB_TO_ITEM[media_type] = tmdb_map
        return entries

    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        if media_type == 'SERIES':
            c.execute(
                'SELECT id, isim, anahtar_kelimeler, onerilen_idleri, benzer_idleri FROM diziler'
            )
            rows = c.fetchall()
            for rid, isim, keywords, onerilen, benzer in rows:
                item_id = f'series_{rid}'
                title = str(isim or '')
                norms = []
                n = _normalize_tr(title)
                n = re.sub(r'[^a-z0-9\s]+', ' ', n)
                n = re.sub(r'\s+', ' ', n).strip()
                if n:
                    norms.append(n)
                tokens = set(t for t in (n.split() if n else []) if len(t) > 1 and t not in _SEARCH_STOP)
                onerilen_ids = _parse_id_list(onerilen)
                benzer_ids = _parse_id_list(benzer)
                entries.append({
                    'id': item_id,
                    'title': title,
                    'original': title,
                    'norms': norms,
                    'tokens': tokens,
                    'director': '',
                    'keywords': str(keywords or ''),
                    'onerilen_ids': onerilen_ids,
                    'benzer_ids': benzer_ids,
                    'tmdb_id': str(rid),
                })
                tmdb_map[str(rid)] = item_id
        else:
            c.execute(
                'SELECT id, isim, orijinal_isim, yonetmen, tmdb_id, anahtar_kelimeler, '
                'onerilen_idleri, benzer_idleri FROM filmler'
            )
            rows = c.fetchall()
            for rid, isim, orijinal, yonetmen, tmdb_id, keywords, onerilen, benzer in rows:
                item_id = f'movies_{rid}'
                title = str(isim or '')
                original = str(orijinal or isim or '')
                norms = []
                for cand in (title, original):
                    n = _normalize_tr(cand)
                    n = re.sub(r'[^a-z0-9\s]+', ' ', n)
                    n = re.sub(r'\s+', ' ', n).strip()
                    if n and n not in norms:
                        norms.append(n)
                tokens = set()
                for n in norms:
                    tokens.update(t for t in n.split() if len(t) > 1 and t not in _SEARCH_STOP)
                onerilen_ids = _parse_id_list(onerilen)
                benzer_ids = _parse_id_list(benzer)
                director = str(yonetmen or '').strip()
                tid = str(tmdb_id or '').strip()
                entries.append({
                    'id': item_id,
                    'title': title,
                    'original': original,
                    'norms': norms,
                    'tokens': tokens,
                    'director': director,
                    'keywords': str(keywords or ''),
                    'onerilen_ids': onerilen_ids,
                    'benzer_ids': benzer_ids,
                    'tmdb_id': tid,
                })
                if tid:
                    tmdb_map[tid] = item_id
                tmdb_map[str(rid)] = item_id
        conn.close()
    except Exception as e:
        print(f"[!] Title index build error ({media_type}): {e}")

    _TITLE_INDEX[media_type] = entries
    _TMDB_TO_ITEM[media_type] = tmdb_map
    print(f"[+] Title index hazır: {media_type} → {len(entries)} yapım")
    return entries


def _extract_anchor_phrases(query_text):
    q = str(query_text or '').strip()
    if not q:
        return [], q, False
    phrases = []
    remainder = q
    explicit_like = False
    patterns = [
        r'["“‘\']([^"”’\']+)["”’\']',
        r'(.+?)\s+(?:gibi|benzeri|tarzı|tarzi|ayarı|ayari|tipi)\b',
    ]
    for p in patterns:
        for m in re.finditer(p, q, flags=re.IGNORECASE):
            phrase = m.group(1).strip(' .,!?:;')
            if len(phrase) >= 2:
                phrases.append(phrase)
                remainder = remainder.replace(m.group(0), ' ')
                if re.search(r'(?:gibi|benzeri|tarzı|tarzi|ayarı|ayari|tipi)\b', m.group(0), re.I):
                    explicit_like = True
    remainder = re.sub(r'\s+', ' ', remainder).strip()
    # Tekil başlık adayı: "tenet", "prison break" — tema sorgularını eleme
    if not phrases:
        compact = re.sub(r'\s+', ' ', q).strip()
        tokens = tokenize_query(compact)
        attr_hints = (
            'olan', 'istiyorum', 'izle', 'temalı', 'temali', 'başrol', 'basrol', 'hikaye',
            'atmosfer', 'konulu', 'tarz', 'modunda', 'geçen', 'gecen', 'setinde', 'dünyası', 'dunyas'
        )
        q_low = compact.lower()
        q_norm = _normalize_tr(q_low)
        looks_thematic = any(h in q_low or _normalize_tr(h) in q_norm for h in attr_hints)
        # "vahşi batı" / "uzay bilim" gibi kısa tema sorguları başlık sanılmasın
        if len(tokens) <= 4 and not looks_thematic:
            phrases.append(compact)
    uniq = []
    seen = set()
    for p in phrases:
        key = _normalize_tr(p)
        if key and key not in seen:
            seen.add(key)
            uniq.append(p)
    return uniq, remainder, explicit_like


def _score_title_match(phrase_norm, entry):
    best = 0.0
    p_tokens = [t for t in phrase_norm.split() if len(t) > 1]
    for n in entry['norms']:
        if phrase_norm == n:
            best = max(best, 1.0)
            continue
        if phrase_norm in n or n in phrase_norm:
            longer = max(len(phrase_norm), len(n))
            shorter = min(len(phrase_norm), len(n))
            if shorter < 4:
                continue
            coverage = shorter / max(1, longer)
            # "vahsi bati" ⊂ "yeni baslayanlar icin vahsi bati" → düşük skor
            if coverage >= 0.85:
                best = max(best, 0.96)
            elif coverage >= 0.65:
                best = max(best, 0.90)
            else:
                best = max(best, 0.72)
        if p_tokens and entry['tokens']:
            inter = len(set(p_tokens) & entry['tokens'])
            union = len(set(p_tokens) | entry['tokens'])
            if union:
                jacc = inter / union
                if inter == len(p_tokens) and inter >= 1 and jacc >= 0.8:
                    best = max(best, 0.94)
                elif inter == len(p_tokens) and inter >= 2:
                    best = max(best, 0.88)
                else:
                    best = max(best, jacc * 0.80)
    return best


def resolve_title_anchors(query_text, media_type, min_score=0.82):
    phrases, remainder, explicit_like = _extract_anchor_phrases(query_text)
    index = _ensure_title_index(media_type)
    # "gibi" yoksa neredeyse birebir başlık iste — tema sorguları open-intent'e düşsün
    effective_min = min_score if explicit_like else 0.94
    anchors = []
    for phrase in phrases:
        p_norm = _normalize_tr(phrase)
        p_norm = re.sub(r'[^a-z0-9\s]+', ' ', p_norm)
        p_norm = re.sub(r'\s+', ' ', p_norm).strip()
        if len(p_norm) < 2:
            continue
        ranked = []
        for entry in index:
            sc = _score_title_match(p_norm, entry)
            if sc >= effective_min:
                ranked.append((sc, entry))
        ranked.sort(key=lambda x: x[0], reverse=True)
        if ranked:
            anchors.append({
                'phrase': phrase,
                'score': ranked[0][0],
                'entry': ranked[0][1],
            })
            remainder = re.sub(re.escape(phrase), ' ', remainder, flags=re.IGNORECASE)
        elif not explicit_like:
            # Başlık tutmadı → tüm sorgu niyet olarak kalsın
            remainder = query_text
    remainder = re.sub(r'\s+', ' ', remainder).strip()
    return anchors, remainder


def resolve_graph_item_ids(tmdb_ids, media_type):
    _ensure_title_index(media_type)
    mapping = _TMDB_TO_ITEM.get(media_type) or {}
    out = set()
    for tid in tmdb_ids or []:
        key = str(tid).strip()
        item_id = mapping.get(key)
        if item_id:
            out.add(item_id)
    return out


def diversify_by_director(scored, max_same=MAX_SAME_DIRECTOR_IN_TOP):
    """Aynı yönetmeni arka arkaya/yığılmayı kes; skoru bozmadan seç."""
    if not scored:
        return scored
    remaining = list(scored)
    result = []
    director_counts = {}

    def can_take(item, relax_streak=False):
        director = (item.get('director') or '').strip().lower()
        if not director:
            return True
        if director_counts.get(director, 0) >= max_same:
            return False
        if not relax_streak and result:
            prev = (result[-1].get('director') or '').strip().lower()
            if prev and prev == director:
                return False
        return True

    while remaining:
        picked = None
        for item in remaining:
            if can_take(item, relax_streak=False):
                picked = item
                break
        if picked is None:
            for item in remaining:
                if can_take(item, relax_streak=True):
                    picked = item
                    break
        if picked is None:
            picked = remaining[0]
        remaining.remove(picked)
        director = (picked.get('director') or '').strip().lower()
        if director:
            director_counts[director] = director_counts.get(director, 0) + 1
        result.append(picked)
    return result


def cosine_similarity(vec_a, vec_b):
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))

def get_query_embedding(text):
    if openai_client:
        try:
            res = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text[:8000])
            return res.data[0].embedding
        except Exception as e:
            print(f"[!] Query embedding error: {e}")

    dim = 128
    vector = [0.0] * dim
    words = text.lower().split()
    for w in words:
        h = 0
        for ch in w:
            h = (h * 31 + ord(ch)) % dim
        vector[abs(h)] += 1.0
    norm = sum(v * v for v in vector) ** 0.5 or 1.0
    return [v / norm for v in vector]

def calibrate_score(raw_sim, rank=0):
    """
    🎯 GERÇEKÇİ COSINE SKOR KALİBRASYONU (%50 - %96)
    Rank cezası yumuşak: hassasiyet 50 iken onlarca sonuç görünsün diye
    alt banda (48) gömülüp slider tarafından silinmesin.
    """
    if raw_sim >= 0.75:
        base = int(90 + min(6, (raw_sim - 0.75) * 24))
    elif raw_sim >= 0.60:
        base = int(82 + (raw_sim - 0.60) * 50)
    elif raw_sim >= 0.45:
        base = int(74 + (raw_sim - 0.45) * 53)
    elif raw_sim >= 0.30:
        base = int(66 + (raw_sim - 0.30) * 53)
    else:
        base = int(max(50, 58 + (raw_sim - 0.10) * 40))

    # Yumuşak rank düşüşü (eski 1.8 çok agresifti → 10-15 sonuçta kesiliyordu)
    final_score = max(50, base - int(rank * 0.55))
    return min(96, final_score)

def normalize_title_root(title):
    """
    🔤 SIKI BAŞLIK KÖKÜ NORMALLERİ (Franchise & Sequel Detection)
    "Dexter: New Blood" -> "dexter", "Cars 2" -> "cars", "The Office" -> "office"
    """
    if not title:
        return ""
    t = str(title).lower().strip()
    if t.startswith("the "):
        t = t[4:]
    t = re.split(r'[:\-–]', t)[0].strip()
    t = re.sub(r'\s+(?:season|sezon|\d+|part|bölüm|chapter)\b.*$', '', t, flags=re.IGNORECASE).strip()
    return t

def normalize_item_id(item_id, media_type):
    """
    🆔 ID FORMATI NORMALLERİ
    movie_122 / movies_122 / 122 / series_1399 → kanonik movies_122 / series_1399
    """
    if not item_id:
        return ""
    sid = str(item_id).strip()
    lower = sid.lower()

    # Bilinen prefixleri soy
    for pfx in ('movies_', 'movie_', 'series_'):
        if lower.startswith(pfx):
            sid = sid[len(pfx):]
            break

    prefix = 'movies_' if media_type == 'MOVIES' else 'series_'
    return f"{prefix}{sid}"


def is_ongoing_status(status_text):
    """Yayın durumu: devam eden yapım mı?"""
    s = str(status_text or '').lower().replace('ı', 'i').replace('İ', 'i')
    if not s:
        return False
    if ('bitmis' in s) or ('bitmiş' in s) or ('final' in s):
        return False
    return ('devam' in s) or ('ongoing' in s) or ('returning' in s)


def is_ended_status(status_text):
    """Yayın durumu: bitmiş / final yapmış mı?"""
    s = str(status_text or '').lower().replace('ı', 'i').replace('İ', 'i')
    if not s:
        return False
    return ('bitmis' in s) or ('bitmiş' in s) or ('final' in s) or ('ended' in s) or ('canceled' in s) or ('cancelled' in s)


def compute_lib_item_weight(item):
    """
    Kullanıcı sinyallerinden kütüphane ağırlığı:
    frontend weight + user_rating(1-5) + favori/beğeni + izleme durumu
    """
    if not isinstance(item, dict):
        return 1.0

    status = str(item.get('status') or '').lower()
    if any(tok in status for tok in ('yarıda', 'yarida', 'dropped', 'bırakt', 'birakt')):
        return -0.6

    try:
        explicit = float(item['weight']) if item.get('weight') is not None else None
    except (TypeError, ValueError):
        explicit = None

    try:
        user_rating = float(item.get('user_rating') or 0)
    except (TypeError, ValueError):
        user_rating = 0.0

    liked = item.get('liked') is True
    favorite = item.get('favorite') is True

    if explicit is not None and explicit < 0:
        return explicit

    if explicit is not None and explicit > 0:
        base = explicit
    else:
        base = 1.0
        if 'izliyorum' in status:
            base = 0.7
        elif any(tok in status for tok in ('izledim', 'completed', 'bitmiş', 'bitmis', 'final')):
            base = 1.2

    if user_rating >= 5:
        base = max(base, 1.65)
    elif user_rating >= 4:
        base = max(base, 1.45)
    elif user_rating >= 3:
        base = max(base, 1.15)
    elif user_rating == 2:
        base = min(base, 0.75)
    elif user_rating == 1:
        return -0.35

    if liked:
        base = max(base, 1.5)
    if favorite:
        base = max(base, 1.35)

    return float(base)


def _keyword_set(raw_keywords):
    out = set()
    for part in re.split(r'[,;/|]', str(raw_keywords or '')):
        tok = part.strip().lower()
        if len(tok) >= 3:
            out.add(tok)
    return out


def cluster_pair_score(item1, item2):
    """
    Küme eşleşme skoru. None = bu çift kümelenemez.
    Ortak tür + cosine + TMDb graph + anahtar kelime overlap.
    Tek ortak 'Dram' + zayıf graph bağı yeterli DEĞİL.
    """
    common_genres = item1['genres'] & item2['genres']
    n_common = len(common_genres)
    sim = cosine_similarity(item1['vec'], item2['vec'])
    graph_linked = (
        item2['id'] in item1.get('graph_ids', set())
        or item1['id'] in item2.get('graph_ids', set())
    )
    kw_overlap = len(item1.get('keywords', set()) & item2.get('keywords', set()))

    if n_common == 0 and not graph_linked:
        return None

    eligible = (
        (n_common >= 3 and sim >= 0.48)
        or (n_common >= 2 and sim >= 0.56)
        or (n_common >= 1 and sim >= 0.64)
        or (graph_linked and n_common >= 2 and sim >= 0.52)
        or (graph_linked and n_common >= 1 and sim >= 0.60)
    )
    if not eligible:
        return None

    return (
        sim
        + (0.07 * min(n_common, 3))
        + (0.12 if graph_linked else 0.0)
        + (0.02 * min(kw_overlap, 5))
    )


def build_taste_clusters(valid_lib_items):
    """
    En yüksek skorlu eşleşmelerden başlayan sıkı greedy kümeleme.
    Her yeni üye, kümedeki mevcut üyelerin HEPSİ ile eligible olmalı
    (geçişli union-find ile alakasız üçüncü yapımların sızmasını engeller).
    """
    n = len(valid_lib_items)
    if n < 2:
        return []

    # Güçlü sinyaller (yüksek ağırlık) tohum olsun
    order = sorted(range(n), key=lambda i: valid_lib_items[i]['weight'], reverse=True)
    used = set()
    clusters = []

    for seed_pos, i in enumerate(order):
        if i in used:
            continue
        group = [valid_lib_items[i]]
        used.add(i)

        companions = []
        for j in order:
            if j in used:
                continue
            score = cluster_pair_score(valid_lib_items[i], valid_lib_items[j])
            if score is not None:
                companions.append((score, j))
        companions.sort(key=lambda x: x[0], reverse=True)

        for score, j in companions:
            item2 = valid_lib_items[j]
            if all(cluster_pair_score(m, item2) is not None for m in group):
                group.append(item2)
                used.add(j)

        if len(group) < 2:
            # Tohum yalnız kaldıysa used'dan geri alma — başka kümeye girebilsin
            used.discard(i)
            continue

        vec_matrix = np.array([x['vec'] for x in group], dtype=np.float32)
        weights_matrix = np.array([x['weight'] for x in group], dtype=np.float32).reshape(-1, 1)
        centroid = np.sum(vec_matrix * weights_matrix, axis=0)
        norm = np.linalg.norm(centroid)
        if norm <= 0:
            for m in group:
                # id bazlı used temizliği zor; index ile tutuyoruz
                pass
            continue
        centroid = (centroid / norm).tolist()

        shared_genres = set(group[0]['genres'])
        for m in group[1:]:
            shared_genres &= m['genres']

        ranked = sorted(group, key=lambda x: x['weight'], reverse=True)
        ref_names = ", ".join([x['title'].title() for x in ranked[:2]])
        graph_union = set()
        for m in group:
            graph_union |= m.get('graph_ids', set())

        clusters.append({
            'items': group,
            'centroid': centroid,
            'size': len(group),
            'ref_names': ref_names,
            'shared_genres': shared_genres,
            'graph_ids': graph_union,
        })

    clusters.sort(key=lambda c: (c['size'], sum(x['weight'] for x in c['items'])), reverse=True)
    return clusters


def pick_diverse_library_ref(cand_vec, lib_items, usage_counts, near_margin=0.045, max_same=3):
    """
    Aday için en yakın kitaplık referansını seçer; aynı dizinin (Oz vb.)
    tüm gerekçelerde tekelleşmesini engeller.
    """
    if not lib_items or cand_vec is None:
        return None, 0.0

    scored = []
    for li in lib_items:
        try:
            sim = cosine_similarity(li['vec'], cand_vec)
        except Exception:
            continue
        scored.append((sim, li))
    if not scored:
        return None, 0.0

    scored.sort(key=lambda x: x[0], reverse=True)
    best_sim = scored[0][0]
    near = [x for x in scored if x[0] >= (best_sim - near_margin)]

    def sort_key(pair):
        sim, li = pair
        uid = str(li.get('id') or '')
        used = int(usage_counts.get(uid, 0))
        # Kotayı aşmış referansları en sona at
        over = 1 if used >= max_same else 0
        return (over, used, -sim)

    near.sort(key=sort_key)
    sim, chosen = near[0]
    uid = str(chosen.get('id') or '')
    if uid:
        usage_counts[uid] = int(usage_counts.get(uid, 0)) + 1
    return chosen, float(sim)


@app.route('/api/auth/register', methods=['POST'])
def api_auth_register():
    """Kayıt + imzalı token (GPT üyelik kapısı). E-posta opsiyonel."""
    try:
        data = request.get_json() or {}
        username = str(data.get('username') or '').strip()
        password = str(data.get('password') or '')
        email = str(data.get('email') or '').strip()
        if not username or not password:
            return jsonify({'ok': False, 'error': 'Eksik alan'}), 400
        # E-posta boşsa benzersiz placeholder (DB UNIQUE constraint için)
        if not email:
            email = f'{username.lower()}@local.dizimibul'
        if not HAS_AUTH_UTILS:
            token = generate_signed_token(username)
            return jsonify({'ok': True, 'token': token, 'username': username, 'warning': 'auth_utils yok, yerel token'})
        ok, msg = auth_utils.kayit_ol(username, password, email)
        if not ok:
            return jsonify({'ok': False, 'error': msg}), 400
        return jsonify({'ok': True, 'token': generate_signed_token(username), 'username': username, 'message': msg})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """Giriş + imzalı token. GPT yalnızca bu token ile açılır."""
    try:
        data = request.get_json() or {}
        username = str(data.get('username') or '').strip()
        password = str(data.get('password') or '')
        if not username or not password:
            return jsonify({'ok': False, 'error': 'Eksik alan'}), 400
        if HAS_AUTH_UTILS:
            if not auth_utils.kullanici_kontrol_et(username, password):
                # Yerel localStorage hesabını DB'ye bir kez köprüle (GPT token için)
                email = str(data.get('email') or f'{username.lower()}@local.dizimibul').strip()
                try:
                    auth_utils.kayit_ol(username, password, email)
                except Exception:
                    pass
                if not auth_utils.kullanici_kontrol_et(username, password):
                    return jsonify({'ok': False, 'error': 'Geçersiz kimlik'}), 401
        token = generate_signed_token(username)
        return jsonify({
            'ok': True,
            'token': token,
            'username': username,
            'isAdmin': is_admin_user(username)
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/auth/session', methods=['GET'])
def api_auth_session():
    """İmzalı token ile oturum bilgisi (admin bayrağı dahil)."""
    ok, username = validate_user_token(request)
    if not ok:
        return jsonify({'ok': False, 'error': 'Yetkisiz'}), 401
    return jsonify({
        'ok': True,
        'username': username,
        'isAdmin': is_admin_user(username)
    })


@app.route('/api/auth/user-exists', methods=['GET'])
def api_auth_user_exists():
    """Arkadaş ekleme: kullanıcı adının sunucu DB'sinde var olup olmadığını kontrol eder."""
    try:
        username = str(request.args.get('username') or '').strip()
        if not username:
            return jsonify({'ok': False, 'exists': False, 'error': 'username gerekli'}), 400

        if HAS_AUTH_UTILS and hasattr(auth_utils, 'kullanici_adi_var_mi'):
            exists, canonical = auth_utils.kullanici_adi_var_mi(username)
            return jsonify({
                'ok': True,
                'exists': bool(exists),
                'username': canonical or username
            })

        # auth_utils yoksa bilinemiyor — frontend yerel yedeklere düşer
        return jsonify({'ok': True, 'exists': False, 'username': username, 'warning': 'auth_unavailable'})
    except Exception as e:
        return jsonify({'ok': False, 'exists': False, 'error': str(e)}), 500


@app.route('/api/search', methods=['POST'])
def api_search():
    """
    🔍 HİBRİT KEŞFET ARAMASI
    vektör cosine + kelime kapısı + başlık anchor (gibi) +
    TMDb onerilen/benzer graph boost + yönetmen soft-boost (çeşitlendirilmiş)
    """
    try:
        # Bot / spam: IP başına dakikalık arama tavanı (GPT olmasa da embedding maliyeti)
        if HAS_GPT_ENRICH and not check_ip_search_allowed(_client_ip(request)):
            return jsonify({
                'results': [],
                'count': 0,
                'usedAI': False,
                'error': 'rate_limited'
            }), 429

        data = request.get_json() or {}
        query = str(data.get('query') or data.get('queryText') or '').strip()
        media_type = str(data.get('mediaType') or data.get('userUniverse') or 'MOVIES').upper()
        if media_type not in ('MOVIES', 'SERIES'):
            media_type = 'MOVIES'
        # Üyelik yalnızca sunucu token'ından — body.isMember yok sayılır (bot bypass engeli)
        is_member, _member_name = validate_user_token(request)
        gpt_member, gpt_username = resolve_gpt_member(request)
        _ = is_member  # arama herkese açık; GPT ayrı kapıdan (gpt_member)

        raw_lib_ids = data.get('libraryItemIds') or data.get('libraryItems') or []
        exclude_set = set()
        for raw in raw_lib_ids:
            rid = raw.get('id') if isinstance(raw, dict) else raw
            if not rid:
                continue
            sid = str(rid).strip()
            exclude_set.add(sid)
            if sid.startswith('series_') or sid.startswith('movies_'):
                exclude_set.add(sid.split('_', 1)[-1])
            else:
                exclude_set.add(f'series_{sid}')
                exclude_set.add(f'movies_{sid}')

        if not query:
            return jsonify({'results': [], 'count': 0, 'usedAI': False})

        # Anlamsız / hakaret / spam — sonuç yok (sözlük gerekmez)
        if HAS_GPT_ENRICH and is_obvious_nonsense_query and is_obvious_nonsense_query(query):
            return jsonify({
                'results': [],
                'count': 0,
                'usedAI': False,
                'isNonsense': True,
                'message': 'Anlamlı bir film/dizi teması algılanamadı.'
            })

        # 1) Başlık anchor: "prison break gibi...", "tenet"
        anchors, remainder = resolve_title_anchors(query, media_type)
        user_intent = (remainder or '').strip() if anchors else query

        bonus_terms = []
        for a in anchors:
            for kw in re.split(r'[,;/|]', a['entry'].get('keywords') or ''):
                kw = kw.strip()
                if kw and kw.lower() not in {b.lower() for b in bonus_terms}:
                    bonus_terms.append(kw)

        # Open-vocabulary niyet: zeki / ortaçağ / vahşi batı / uzay bilim / steampunk...
        auto_concepts = []
        used_query_expand = False
        if anchors and not user_intent:
            titles = ', '.join(a['entry']['title'] for a in anchors)
            embed_intent = f"{titles} benzeri yapımlar"
            intent = {'phrases': [], 'tokens': [], 'embed_text': embed_intent, 'soft_expand': []}
            query_tokens = tokenize_query(' '.join(bonus_terms[:8]))
            themes = []
        else:
            intent = extract_open_intent(user_intent or query)
            # Otomatik kavram genişletme: sözlüğe elle eklemeye gerek yok
            # "beyin yakan", "folk horror", "yavaş yanmalı gerilim"... GPT+cache ile açılır
            if HAS_GPT_ENRICH and expand_search_query_concepts and openai_client:
                meaningful, auto_concepts, used_query_expand = expand_search_query_concepts(
                    openai_client,
                    user_intent or query,
                    media_type=media_type,
                    db_path=RUNTIME_CACHE_DB_PATH,
                )
                if not meaningful:
                    return jsonify({
                        'results': [],
                        'count': 0,
                        'usedAI': False,
                        'isNonsense': True,
                        'message': 'Anlamlı bir film/dizi teması algılanamadı.'
                    })
                if auto_concepts:
                    merged = list(intent.get('soft_expand') or [])
                    for c in auto_concepts:
                        if c not in merged:
                            merged.append(c)
                    intent['soft_expand'] = merged[:24]
                    intent['embed_text'] = (
                        f"{intent.get('embed_text') or (user_intent or query)} "
                        f"| kavramlar: {', '.join(auto_concepts[:16])}"
                    )
            embed_intent = intent.get('embed_text') or (user_intent or query)
            query_tokens = intent.get('tokens') or tokenize_query(user_intent or query)
            themes = detect_themes(user_intent or query)
            # detect_themes soft_expand'i yeniden çıkarır; otomatik kavramları koru
            if auto_concepts:
                for th in themes:
                    for c in auto_concepts:
                        if c not in th['expand']:
                            th['expand'].append(c)

        has_open_intent = bool(intent.get('phrases') or intent.get('tokens'))
        zombie_query = _is_zombie_theme_query(user_intent or query)
        prison_query = _is_prison_theme_query(user_intent or query)
        negated = extract_negations(query)

        # Anchor anahtar kelimeleri + graph komşuları
        graph_ids = set()
        anchor_ids = set()
        anchor_directors = set()
        anchor_vecs = []
        seed_vecs = []

        emb_lookup = {}
        conn = sqlite3.connect(EMBEDDINGS_DB_PATH)
        c = conn.cursor()
        c.execute(
            'SELECT item_id, item_title, embedding_json FROM item_embeddings WHERE media_type = ?',
            (media_type,)
        )
        rows = c.fetchall()
        conn.close()

        if not rows:
            return jsonify({
                'results': [],
                'count': 0,
                'message': 'Henüz vektör kataloğu oluşturulmamış.'
            })

        for item_id, item_title, emb_json in rows:
            try:
                emb_lookup[str(item_id)] = {
                    'title': item_title,
                    'vec': json.loads(emb_json)
                }
            except Exception:
                continue

        for a in anchors:
            entry = a['entry']
            aid = entry['id']
            anchor_ids.add(aid)
            exclude_set.add(aid)
            exclude_set.add(str(aid).split('_')[-1])
            if entry.get('director'):
                anchor_directors.add(entry['director'].strip().lower())
            graph_ids |= resolve_graph_item_ids(entry.get('onerilen_ids') or [], media_type)
            graph_ids |= resolve_graph_item_ids(entry.get('benzer_ids') or [], media_type)
            if aid in emb_lookup:
                anchor_vecs.append(emb_lookup[aid]['vec'])

        for gid in list(graph_ids)[:8]:
            if gid in emb_lookup:
                seed_vecs.append(emb_lookup[gid]['vec'])

        anchor_blend = ANCHOR_VECTOR_BLEND if anchor_vecs else 0.0
        seed_blend = GRAPH_SEED_VECTOR_BLEND
        if anchors and not anchor_vecs and seed_vecs:
            seed_blend = min(0.45, GRAPH_SEED_VECTOR_BLEND + 0.25)

        expanded = expand_query_for_embedding(embed_intent, bonus_terms)
        if anchors:
            anchor_titles = ', '.join(a['entry']['title'] for a in anchors)
            dirs = ', '.join(sorted({a['entry']['director'] for a in anchors if a['entry'].get('director')}))
            expanded = f"{expanded} | benzer yapımlar: {anchor_titles}"
            if dirs:
                expanded = f"{expanded} | yönetmen: {dirs}"
        query_vec = get_query_embedding(expanded)

        # Her niyet birimi için ayrı vektör (bilinmeyen temalar dahil)
        intent_vecs = []
        for phrase in (intent.get('phrases') or [])[:4]:
            iv = get_intent_embedding(phrase)
            if iv:
                intent_vecs.append(iv)

        blend_extras = []
        blend_weights = [max(0.15, 1.0 - anchor_blend - (seed_blend if seed_vecs else 0.0))]
        if anchor_vecs:
            avg_a = np.mean(np.array(anchor_vecs, dtype=np.float32), axis=0)
            n = float(np.linalg.norm(avg_a)) or 1.0
            blend_extras.append((avg_a / n).tolist())
            blend_weights.append(anchor_blend)
        if seed_vecs:
            avg_s = np.mean(np.array(seed_vecs, dtype=np.float32), axis=0)
            n = float(np.linalg.norm(avg_s)) or 1.0
            blend_extras.append((avg_s / n).tolist())
            blend_weights.append(seed_blend)
        if blend_extras:
            wsum = sum(max(0.0, w) for w in blend_weights) or 1.0
            blend_weights = [max(0.0, w) / wsum for w in blend_weights]
            query_vec = _blend_vectors(query_vec, blend_extras, blend_weights)

        scored = []
        for item_id, item_title, emb_json in rows:
            sid = str(item_id)
            bare = sid.split('_', 1)[-1] if ('_' in sid) else sid
            if sid in exclude_set or bare in exclude_set:
                continue
            if sid in anchor_ids:
                continue

            packed = emb_lookup.get(sid)
            if not packed:
                continue
            cand_vec = packed['vec']

            cosine = cosine_similarity(query_vec, cand_vec)
            min_cos = (MIN_SIMILARITY_THRESHOLD * 0.35) if sid in graph_ids else (MIN_SIMILARITY_THRESHOLD * 0.5)
            if cosine < min_cos:
                continue

            meta = get_item_metadata(item_id, media_type)
            title = meta.get('title') or item_title or ''
            keywords = meta.get('keywords') or ''
            genres = meta.get('genres') or ''
            summary = meta.get('summary') or ''
            body = ' '.join([
                summary, genres, keywords,
                meta.get('director') or '',
                meta.get('original_title') or ''
            ])

            if negated:
                body_l = f"{title} {body}".lower()
                if any(n in body_l for n in negated):
                    continue

            if zombie_query and not passes_zombie_theme_filter(
                title, summary, keywords, genres
            ):
                continue

            if prison_query and not passes_prison_theme_filter(
                title, summary, keywords, genres
            ):
                continue

            graph_boost = 1.0 if sid in graph_ids else 0.0
            director = (meta.get('director') or '').strip()
            same_director = (
                1.0 if (director and director.lower() in anchor_directors) else 0.0
            )

            if has_open_intent and not passes_open_intent_gate(
                title, keywords, genres, summary, intent, cand_vec, intent_vecs,
                cosine_main=cosine,
                graph_hit=bool(graph_boost),
                director_hit=bool(same_director),
            ):
                continue

            lex = lexical_score(
                body, title, themes, query_tokens,
                bonus_terms=bonus_terms, intent=intent
            )
            intent_cov = 0.0
            if has_open_intent:
                intent_cov = max(
                    intent_lexical_coverage(title, keywords, genres, summary, intent),
                    intent_semantic_coverage(cand_vec, intent_vecs)
                )

            dir_w = HYBRID_DIRECTOR_WEIGHT * (1.35 if (anchors and not anchor_vecs) else 1.0)
            hybrid = (
                (HYBRID_VECTOR_WEIGHT * cosine)
                + (HYBRID_LEXICAL_WEIGHT * lex)
                + (HYBRID_INTENT_WEIGHT * intent_cov)
                + (HYBRID_GRAPH_WEIGHT * graph_boost)
                + (dir_w * same_director)
            )

            if has_open_intent:
                floor = MIN_HYBRID_SCORE * (0.85 if graph_boost else 1.0)
                # intent_cov düşük olsa bile makul cosine'ı tamamen kesme
                if hybrid < floor and not graph_boost and intent_cov < 0.22 and cosine < 0.32:
                    continue
            elif anchors:
                if not graph_boost and not same_director and hybrid < 0.32:
                    continue
            else:
                floor = max(0.28, MIN_SIMILARITY_THRESHOLD * 0.85)
                if hybrid < floor and cosine < MIN_SIMILARITY_THRESHOLD:
                    continue

            scored.append({
                'id': item_id,
                'title': title,
                'director': director,
                'rawSimilarity': round(cosine, 4),
                'hybridScore': hybrid,
                'lexical': lex,
                'intentCoverage': round(intent_cov, 4),
                'graphHit': bool(graph_boost),
                'directorHit': bool(same_director),
            })

        scored.sort(key=lambda x: x['hybridScore'], reverse=True)

        # Gap: açık niyet yoksa şişmeyi kes
        if scored and not has_open_intent:
            top1 = scored[0]['hybridScore']
            ratio = ANCHOR_GAP_RATIO if anchors else RELATIVE_GAP_RATIO
            gap_floor = top1 * ratio
            scored = [
                s for s in scored
                if s['hybridScore'] >= gap_floor
                or s.get('graphHit')
                or (s.get('directorHit') and s['hybridScore'] >= gap_floor * 0.75)
            ]
        elif scored and has_open_intent:
            # Niyetli aramada relative gap (daha gevşek — spin-off'lar kesilmesin)
            top1 = scored[0]['hybridScore']
            gap_floor = top1 * 0.32
            scored = [
                s for s in scored
                if s['hybridScore'] >= gap_floor
                or s.get('graphHit')
                or (s.get('intentCoverage') or 0) >= 0.40
            ]

        # Tema araması: üst sonuçların TMDb komşularını enjekte et (Daryl Dixon vb.)
        if has_open_intent and scored:
            scored = inject_theme_graph_neighbors(
                scored, emb_lookup, media_type, query_vec, intent, intent_vecs,
                exclude_set=exclude_set, anchor_ids=anchor_ids,
            )

        # Zayıf sinyal: en iyi eşleşme bile alakasızsa boş dön (anlamsız sorgu koruması)
        if scored and has_open_intent and not anchors:
            top_cos = float(scored[0].get('rawSimilarity') or 0)
            top_hyb = float(scored[0].get('hybridScore') or 0)
            if top_cos < SEARCH_MIN_TOP_COSINE and top_hyb < SEARCH_MIN_TOP_HYBRID:
                return jsonify({
                    'results': [],
                    'count': 0,
                    'usedAI': True,
                    'isNonsense': True,
                    'message': 'Aramanızla yeterince örtüşen yapım bulunamadı.',
                    'usedQueryExpand': used_query_expand,
                    'autoConcepts': auto_concepts[:12],
                })

        # Anchor yönetmen filmlerini üst sıralara taşı / enjekte et (max 2, aralıklı)
        if anchors and anchor_directors and media_type == 'MOVIES':
            have_ids = {str(s['id']) for s in scored}
            dir_candidates = [s for s in scored if s.get('directorHit')]
            for entry in _ensure_title_index(media_type):
                sid = str(entry['id'])
                if sid in have_ids or sid in anchor_ids:
                    continue
                director = (entry.get('director') or '').strip()
                if not director or director.lower() not in anchor_directors:
                    continue
                packed = emb_lookup.get(sid)
                if not packed:
                    continue
                cos = cosine_similarity(query_vec, packed['vec'])
                dir_candidates.append({
                    'id': sid,
                    'title': entry.get('title') or packed.get('title') or '',
                    'director': director,
                    'rawSimilarity': round(cos, 4),
                    'hybridScore': max(0.40, (HYBRID_VECTOR_WEIGHT * cos) + (HYBRID_DIRECTOR_WEIGHT * 1.5)),
                    'lexical': 0.0,
                    'graphHit': sid in graph_ids,
                    'directorHit': True,
                })
                have_ids.add(sid)
            dir_candidates.sort(key=lambda x: x['hybridScore'], reverse=True)
            promote = dir_candidates[:MAX_SAME_DIRECTOR_IN_TOP]
            if promote:
                promote_ids = {str(p['id']) for p in promote}
                scored = [s for s in scored if str(s['id']) not in promote_ids]
                slots = [1, 3]
                for i, item in enumerate(promote):
                    pos = slots[i] if i < len(slots) else min(2 * i + 1, len(scored))
                    pos = min(pos, len(scored))
                    scored.insert(pos, item)

        # Yönetmen çeşitliliği (Tenet → tüm Nolan sıraya dizilmesin)
        if anchors and media_type == 'MOVIES':
            scored = diversify_by_director(scored, max_same=MAX_SAME_DIRECTOR_IN_TOP)

        total_matched = len(scored)
        score_cap = SEARCH_SAFETY_CAP if (has_open_intent or anchors) else UNTHEMED_SEARCH_CAP
        ranked_pool = scored[:score_cap]
        # Niyetli / "gibi" aramalarda eşleşen TÜM yapımlar döner (liste kısıtlanmaz).
        # GPT notu ayrı kapıdan, en fazla 10 güçlü sonuca yazılır.
        if has_open_intent or anchors:
            top = ranked_pool
        else:
            top = ranked_pool[:SEARCH_RETURN_CAP]

        results = []
        for rank, item in enumerate(top):
            match_score = calibrate_score(
                item.get('hybridScore') or item.get('rawSimilarity') or 0.35,
                rank=rank
            )
            meta = get_item_metadata(item['id'], media_type)
            genres = (meta.get('genres') or '').strip()
            keywords = (meta.get('keywords') or '').strip()
            summary_full = (meta.get('summary') or '').strip()
            summary_hint = summary_full[:140]

            results.append({
                'id': item['id'],
                'title': item['title'],
                'rawSimilarity': item['rawSimilarity'],
                'hybridScore': round(item['hybridScore'], 4),
                'aiMatchScore': match_score,
                'graphHit': item.get('graphHit', False),
                'directorHit': item.get('directorHit', False),
                'intentCoverage': item.get('intentCoverage', 0),
                'genres': genres,
                'keywords': keywords[:80],
                'summary': summary_hint,
                # Not yalnız güçlü eşleşmelere — aşağıda doldurulur
                'aiReason': '',
            })

        used_member_llm = False
        gpt_note_count = 0
        # GPT / yerel not: yalnızca en güçlü max 10 eşleşmeye (liste boyutu değişmez)
        note_targets = []
        if results:
            if HAS_GPT_ENRICH and select_strong_search_targets:
                note_targets = select_strong_search_targets(
                    results, max_n=GPT_SEARCH_NOTE_MAX
                )
            else:
                note_targets = results[: min(GPT_SEARCH_NOTE_MAX, len(results))]

            # Yerel fallback not (GPT yok / kota / üye değil)
            for it in note_targets:
                meta = get_item_metadata(it['id'], media_type)
                summary_full = (meta.get('summary') or '').strip()
                # GPT'ye daha uzun özet verilsin diye geçici alan
                it['summary'] = summary_full[:400] if summary_full else it.get('summary', '')
                if HAS_GPT_ENRICH and compose_unique_search_note:
                    it['aiReason'] = compose_unique_search_note(
                        query,
                        it['title'],
                        it.get('genres') or '',
                        it.get('keywords') or '',
                        summary_full,
                    )
                else:
                    genres = (it.get('genres') or '').strip() or 'Dram'
                    hint = (summary_full[:110] + '…') if len(summary_full) > 110 else summary_full
                    if hint:
                        it['aiReason'] = (
                            f'{it["title"]} · {genres}: {hint} '
                            f'(%{it.get("aiMatchScore", "")} uyum)'
                        )
                    else:
                        it['aiReason'] = (
                            f'{it["title"]} ({genres}), "{query}" aramanızdaki temaya '
                            f'özgü atmosferiyle öne çıkıyor.'
                        )

            # İmzalı üye: hikâye odaklı GPT notları (yalnız note_targets, max 10)
            if gpt_member and gpt_username and HAS_GPT_ENRICH and openai_client and note_targets:
                used_member_llm = enrich_with_gpt_notes(
                    openai_client,
                    note_targets,
                    feature='search',
                    context=query,
                    username=gpt_username,
                    db_path=RUNTIME_CACHE_DB_PATH,
                )
                if used_member_llm:
                    print(
                        f"[+] GPT eşleşme notları yazıldı "
                        f"({gpt_username}, {len(note_targets)}/{len(results)} yapım)"
                    )
                else:
                    print(
                        f"[!] GPT not yazılamadı — özgün yerel notlar kullanıldı "
                        f"({gpt_username}, {len(note_targets)} aday)"
                    )

            gpt_note_count = sum(1 for it in note_targets if (it.get('aiReason') or '').strip())
            # Kartlarda kısa özet kalsın (GPT için uzattığımız alanı geri al)
            for it in note_targets:
                meta = get_item_metadata(it['id'], media_type)
                it['summary'] = (meta.get('summary') or '').strip()[:140]

        return jsonify({
            'results': results,
            'count': len(results),
            'totalMatched': total_matched,
            'gptNotesCount': gpt_note_count,
            'poolMode': (
                'anchor_graph' if anchors else
                ('open_intent' if has_open_intent else 'unthemed_capped')
            ),
            'usedAI': True,
            'usedMemberLLM': used_member_llm,
            'usedQueryExpand': used_query_expand,
            'autoConcepts': (auto_concepts or [])[:12],
            'themes': intent.get('phrases') or [t['key'] for t in themes],
            'intent': {
                'phrases': intent.get('phrases') or [],
                'tokens': intent.get('tokens') or [],
                'softExpand': (intent.get('soft_expand') or [])[:12],
            },
            'anchors': [
                {
                    'phrase': a['phrase'],
                    'title': a['entry']['title'],
                    'id': a['entry']['id'],
                    'score': round(a['score'], 3),
                    'graphNeighbors': len(resolve_graph_item_ids(
                        (a['entry'].get('onerilen_ids') or []) + (a['entry'].get('benzer_ids') or []),
                        media_type
                    ))
                }
                for a in anchors
            ]
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[!] Search API Exception: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommendations', methods=['POST'])
def api_recommendations():
    """
    🧬 AKILLI ÖNERİ MOTORU & SIKI KÜMELEME + FRANCHISE KUYRUĞU
    v2.2: min 15 slot + kitaplık eşiği + temalı userQuery filtresi (hapishane vb.)
    """
    try:
        data = request.get_json() or {}
        raw_lib = data.get('libraryItems', data.get('libraryItemIds', []))
        hidden_ids = set([normalize_item_id(x, data.get('userUniverse', 'MOVIES')) for x in data.get('hiddenItemIds', [])])
        user_universe = str(data.get('userUniverse', 'MOVIES')).upper()
        user_query = str(data.get('userQuery', '')).strip()

        # Devam edenleri dahil et? (SERIES). False => sadece bitmiş / final
        include_ongoing = data.get('includeOngoing')
        if include_ongoing is None:
            include_ongoing = data.get('preferEndedOnly') is not True
        # JSON false / "false" / 0 hepsini doğru yorumla
        if isinstance(include_ongoing, str):
            include_ongoing = include_ongoing.strip().lower() not in ('0', 'false', 'no', 'hayir', 'hayır')
        include_ongoing = bool(include_ongoing)
        prefer_ended_only = (user_universe == 'SERIES' and not include_ongoing)

        # Eski metadata cache'te status yoksa devam filtresi kırılır — temizle
        if prefer_ended_only:
            DATASET_METADATA_CACHE.clear()

        is_member, user_token = validate_user_token(request)
        gpt_member, gpt_username = resolve_gpt_member(request)

        # Kitaplıkta en az MIN_LIBRARY_FOR_AI yapım yoksa öneri üretme
        lib_count_raw = 0
        for item in (raw_lib or []):
            raw_id = item.get('id') if isinstance(item, dict) else item
            if raw_id:
                lib_count_raw += 1
        if lib_count_raw < MIN_LIBRARY_FOR_AI:
            return jsonify({
                'visible': [],
                'overflowQueue': [],
                'recommendations': [],
                'count': 0,
                'meta': {
                    'clustersDetected': 0,
                    'franchiseGroupsMatched': 0,
                    'libraryMatched': lib_count_raw,
                    'libraryRequired': MIN_LIBRARY_FOR_AI,
                    'blockedReason': 'min_library',
                    'engineVersion': '2.2',
                    'message': f'AI tavsiye için kitaplıkta en az {MIN_LIBRARY_FOR_AI} yapım olmalı.',
                }
            })

        conn = sqlite3.connect(EMBEDDINGS_DB_PATH)
        c = conn.cursor()
        c.execute('SELECT item_id, item_title, embedding_json FROM item_embeddings WHERE media_type = ?', (user_universe,))
        rows = c.fetchall()
        conn.close()

        if not rows:
            return jsonify({
                'visible': [],
                'overflowQueue': [],
                'meta': {'clustersDetected': 0, 'franchiseGroupsMatched': 0, 'cacheKey': 'empty', 'engineVersion': '2.2'}
            })

        all_vecs = {}
        for r_id, r_title, r_vec_json in rows:
            try:
                all_vecs[r_id] = (r_title, json.loads(r_vec_json))
            except Exception:
                continue

        prison_query = _is_prison_theme_query(user_query)
        zombie_query = _is_zombie_theme_query(user_query)
        query_vec = None
        if user_query:
            try:
                query_vec = get_query_embedding(expand_query_for_embedding(user_query))
            except Exception:
                query_vec = None

        # 1. Kütüphanedeki Elemanları, Türlerini ve Ağırlıklarını İşle
        lib_weights = {}
        lib_set = set()
        lib_item_map = {}
        lib_roots = {}  # root -> item_dict

        for item in raw_lib:
            raw_id = item.get('id') if isinstance(item, dict) else item
            if not raw_id:
                continue

            norm_id = normalize_item_id(raw_id, user_universe)
            i_id = norm_id if norm_id in all_vecs else (str(raw_id) if str(raw_id) in all_vecs else None)
            if not i_id:
                continue

            w = compute_lib_item_weight(item if isinstance(item, dict) else {'id': raw_id})

            title, vec = all_vecs[i_id]
            meta = get_item_metadata(i_id, user_universe)
            genres_set = set([g.strip().lower() for g in meta['genres'].split(',') if g.strip()])
            keywords_set = _keyword_set(meta.get('keywords'))
            graph_ids = resolve_graph_item_ids(meta.get('onerilen_ids') or [], user_universe)
            graph_ids |= resolve_graph_item_ids(meta.get('benzer_ids') or [], user_universe)

            root = normalize_title_root(title)

            lib_weights[i_id] = w
            lib_set.add(i_id)
            item_obj = {
                'id': i_id,
                'title': title,
                'vec': vec,
                'weight': w,
                'root': root,
                'genres': genres_set,
                'keywords': keywords_set,
                'graph_ids': graph_ids,
                'status': meta.get('status') or '',
            }
            lib_item_map[i_id] = item_obj
            if len(root) >= 3:
                lib_roots[root] = item_obj

        # Embedding eşleşmesi sonrası da eşik kontrolü
        if len(lib_set) < MIN_LIBRARY_FOR_AI:
            return jsonify({
                'visible': [],
                'overflowQueue': [],
                'recommendations': [],
                'count': 0,
                'meta': {
                    'clustersDetected': 0,
                    'franchiseGroupsMatched': 0,
                    'libraryMatched': len(lib_set),
                    'libraryRequired': MIN_LIBRARY_FOR_AI,
                    'blockedReason': 'min_library',
                    'engineVersion': '2.2',
                    'message': f'AI tavsiye için kitaplıkta en az {MIN_LIBRARY_FOR_AI} yapım olmalı.',
                }
            })

        exclude_set = lib_set.union(hidden_ids)
        candidates = {r_id: (r_title, r_vec) for r_id, (r_title, r_vec) in all_vecs.items() if r_id not in exclude_set}

        # Tercih: devam edenleri ele (SERIES)
        if prefer_ended_only:
            filtered = {}
            for c_id, packed in candidates.items():
                c_meta = get_item_metadata(c_id, user_universe)
                if is_ongoing_status(c_meta.get('status')):
                    continue
                filtered[c_id] = packed
            candidates = filtered

        # Temalı sorgu (hapishane / zombi): alakasız adayları ele
        if prison_query or zombie_query:
            filtered = {}
            for c_id, (c_title, c_vec) in candidates.items():
                c_meta = get_item_metadata(c_id, user_universe)
                ok = True
                if prison_query:
                    ok = passes_prison_theme_filter(
                        c_title,
                        c_meta.get('summary') or '',
                        c_meta.get('keywords') or '',
                        c_meta.get('genres') or '',
                    )
                if ok and zombie_query:
                    ok = passes_zombie_theme_filter(
                        c_title,
                        c_meta.get('summary') or '',
                        c_meta.get('keywords') or '',
                        c_meta.get('genres') or '',
                    )
                if ok:
                    filtered[c_id] = (c_title, c_vec)
            candidates = filtered

        def _title_false_friend_penalty(lib_title, cand_title, lib_genres, cand_genres):
            """The Good Doctor ↔ The Good Place gibi isim benzerliğini cezalandır."""
            la = set(tokenize_query(lib_title or ''))
            lb = set(tokenize_query(cand_title or ''))
            # "the/a" zaten tokenize'da düşer; weak token'ları da düş
            la = {t for t in la if not _is_title_weak_soft_token(t)}
            lb = {t for t in lb if not _is_title_weak_soft_token(t)}
            if not la or not lb:
                # Kalan kelimeler yalnızca weak ise (Good/Place) → güçlü ceza
                raw_a = set(tokenize_query(lib_title or ''))
                raw_b = set(tokenize_query(cand_title or ''))
                shared_weak = raw_a & raw_b
                if shared_weak and not (la & lb):
                    ga = set(g.strip().lower() for g in (lib_genres or set()) if g) if isinstance(lib_genres, set) else set()
                    gb = set(g.strip().lower() for g in (cand_genres or set()) if g) if isinstance(cand_genres, set) else set()
                    if not (ga & gb):
                        return 0.18
                    return 0.10
                return 0.0
            shared = la & lb
            if not shared:
                return 0.0
            # Ortak anlamlı kelime az + tür örtüşmesi yok → isim tuzağı
            ga = lib_genres if isinstance(lib_genres, set) else set()
            gb = cand_genres if isinstance(cand_genres, set) else set()
            if shared and not (ga & gb):
                return 0.12
            return 0.0

        def _query_boost(cand_id, cand_title, cand_vec):
            """userQuery varsa semantik + başlık boost'u."""
            boost = 0.0
            if query_vec is not None:
                boost += 0.55 * cosine_similarity(query_vec, cand_vec)
            if user_query and prison_query and _title_hint_hit(cand_title, _PRISON_TITLE_HINTS):
                boost += 0.25
            elif user_query and zombie_query and _title_hint_hit(cand_title, _ZOMBIE_TITLE_HINTS):
                boost += 0.25
            elif user_query:
                qn = _normalize_tr(user_query)
                tn = _normalize_tr(cand_title or '')
                if any(tok in tn for tok in qn.split() if len(tok) > 3 and not _is_title_weak_soft_token(tok)):
                    boost += 0.08
            return boost

        # ─── KANAL 1: SIKI FRANCHISE & DEVAM YAPIMLARI (Dexter, Cars, Spin-off) ───
        franchise_recs = []

        for c_id, (c_title, c_vec) in candidates.items():
            c_root = normalize_title_root(c_title)
            if not c_root:
                continue

            ref_item = None
            if c_root in lib_roots:
                ref_item = lib_roots[c_root]

            if ref_item:
                if ref_item['title'].lower().strip() != c_title.lower().strip():
                    # Tek kelimelik zayıf kökler (good, dark…) franchise sayılmasın
                    root_parts = [p for p in c_root.split() if not _is_title_weak_soft_token(p)]
                    if not root_parts and len(c_root.split()) <= 2:
                        continue
                    raw_sim = cosine_similarity(ref_item['vec'], c_vec)
                    # İsim benzeri ama farklı yapım: daha yüksek cosine iste
                    if raw_sim >= 0.72:
                        franchise_recs.append({
                            'id': c_id,
                            'title': c_title,
                            'rawSimilarity': round(raw_sim, 4),
                            'aiMatchScore': calibrate_score(raw_sim + 0.10, rank=len(franchise_recs)),
                            'aiReason': f'🎬 <strong>{ref_item["title"].title()}</strong> izlediğin için devam/spin-off yapımı önerildi.',
                            'root': c_root,
                            'channel': 'FRANCHISE'
                        })

        # ─── KANAL 2: SIKI OTOMATİK KÜMELEME (tür + cosine + graph) ───
        valid_lib_items = [item for item in lib_item_map.values() if item['weight'] > 0]
        clusters = build_taste_clusters(valid_lib_items)

        total_lib_count = max(1, len(lib_set))
        cluster_recs = []

        for c_idx, cl in enumerate(clusters):
            slot_share = max(1, min(3, int(6 * (cl['size'] / total_lib_count))))
            cl_candidates = []
            for cand_id, (cand_title, cand_vec) in candidates.items():
                cand_meta = get_item_metadata(cand_id, user_universe)
                cand_genres = set([g.strip().lower() for g in cand_meta['genres'].split(',') if g.strip()])

                if cl['shared_genres'] and not (cand_genres & cl['shared_genres']):
                    continue

                sim = cosine_similarity(cl['centroid'], cand_vec)
                graph_hit = cand_id in cl.get('graph_ids', set())
                # Küme referanslarına göre isim tuzağı cezası
                name_pen = 0.0
                for ref_name in (cl.get('ref_names') or [])[:4]:
                    name_pen = max(
                        name_pen,
                        _title_false_friend_penalty(ref_name, cand_title, cl.get('shared_genres') or set(), cand_genres)
                    )
                adj_sim = sim + (0.08 if graph_hit else 0.0) + _query_boost(cand_id, cand_title, cand_vec) - name_pen

                if adj_sim >= (0.38 if user_query else 0.45):
                    cl_candidates.append({
                        'id': cand_id,
                        'title': cand_title,
                        'rawSimilarity': round(min(0.99, adj_sim), 4),
                        'channel': 'CLUSTER',
                        'cluster_idx': c_idx,
                        'cluster_items': cl.get('items') or [],
                        'ref_names': cl['ref_names'],
                        'graphHit': graph_hit,
                        'cand_vec': cand_vec,
                    })

            cl_candidates.sort(key=lambda x: x['rawSimilarity'], reverse=True)
            cluster_recs.extend(cl_candidates[:slot_share * 4])

        # ─── KANAL 3: BİREYSEL COSINE & KEŞİF (Small Library / Fallback) ───
        general_recs = []
        if valid_lib_items:
            vec_matrix = np.array([x['vec'] for x in valid_lib_items], dtype=np.float32)
            w_matrix = np.array([x['weight'] for x in valid_lib_items], dtype=np.float32).reshape(-1, 1)
            user_taste_vec = np.sum(vec_matrix * w_matrix, axis=0)
            norm = np.linalg.norm(user_taste_vec)
            if norm > 0:
                user_taste_vec = (user_taste_vec / norm).tolist()

            # Temalı istek varsa zevk profilini sorgu ile harmanla
            if query_vec is not None:
                user_taste_vec = _blend_vectors(user_taste_vec, [query_vec], [0.35, 0.65])

            lib_graph_union = set()
            for li in valid_lib_items:
                lib_graph_union |= li.get('graph_ids', set())

            for cand_id, (cand_title, cand_vec) in candidates.items():
                sim = cosine_similarity(user_taste_vec, cand_vec)
                if cand_id in lib_graph_union:
                    sim = min(0.99, sim + 0.05)
                sim = min(0.99, sim + _query_boost(cand_id, cand_title, cand_vec) * 0.5)

                # Geçici en yakın ref (çeşitlilik final gerekçede uygulanır)
                best_ref = None
                best_ref_sim = -1.0
                for li in valid_lib_items:
                    s_ref = cosine_similarity(li['vec'], cand_vec)
                    if s_ref > best_ref_sim:
                        best_ref_sim = s_ref
                        best_ref = li

                if best_ref:
                    cand_meta = get_item_metadata(cand_id, user_universe)
                    cand_genres = set(
                        g.strip().lower() for g in (cand_meta.get('genres') or '').split(',') if g.strip()
                    )
                    sim = max(
                        0.0,
                        sim - _title_false_friend_penalty(
                            best_ref.get('title'), cand_title,
                            best_ref.get('genres') or set(), cand_genres
                        )
                    )

                reason_q = ''
                if user_query:
                    reason_q = f' · "{user_query}" teması'

                general_recs.append({
                    'id': cand_id,
                    'title': cand_title,
                    'rawSimilarity': round(sim, 4),
                    'channel': 'DISCOVERY',
                    'ref_names': (best_ref['title'].title() if best_ref else ''),
                    'refSim': round(best_ref_sim, 4) if best_ref else 0.0,
                    'queryHint': reason_q,
                    'cand_vec': cand_vec,
                })
            general_recs.sort(key=lambda x: x['rawSimilarity'], reverse=True)

        if not general_recs and candidates:
            for cand_id, (cand_title, cand_vec) in candidates.items():
                cand_meta = get_item_metadata(cand_id, user_universe)
                rating = cand_meta.get('rating', 7.0)
                sim = 0.50 + min(0.35, (rating / 10.0) * 0.35)
                if query_vec is not None:
                    sim = min(0.99, 0.35 * sim + 0.65 * cosine_similarity(query_vec, cand_vec))
                general_recs.append({
                    'id': cand_id,
                    'title': cand_title,
                    'rawSimilarity': round(sim, 4),
                    'channel': 'DISCOVERY'
                })
            general_recs.sort(key=lambda x: x['rawSimilarity'], reverse=True)

        # ─── VISIBLE SLOT + OVERFLOW QUEUE HARMANLAMA & SKOR KALİBRASYONU ───
        visible = []
        overflow_queue = []
        used_ids = set()
        visible_cap = AI_VISIBLE_SLOTS
        overflow_cap = AI_OVERFLOW_CAP

        franchise_roots_in_visible = set()
        for f_item in franchise_recs:
            if len(visible) >= 3:
                break
            if f_item['id'] not in used_ids and f_item['root'] not in franchise_roots_in_visible:
                f_item['aiMatchScore'] = calibrate_score(f_item['rawSimilarity'], rank=len(visible))
                visible.append(f_item)
                used_ids.add(f_item['id'])
                franchise_roots_in_visible.add(f_item['root'])

        for f_item in franchise_recs:
            if f_item['id'] not in used_ids:
                f_item['aiMatchScore'] = calibrate_score(f_item['rawSimilarity'], rank=len(visible) + len(overflow_queue))
                overflow_queue.append(f_item)
                used_ids.add(f_item['id'])

        seen_cluster_indices = set()
        cluster_visible_cap = max(8, visible_cap - 2)
        ref_usage_counts = {}  # final gerekçelerde Oz tekelliğini kır

        def _assign_diverse_reason(item, pool_items, score_rank, *, overflow=False):
            """Nihai listede çeşitlendirilmiş tek referans + aiReason yazar."""
            item['aiMatchScore'] = calibrate_score(
                item['rawSimilarity'],
                rank=score_rank
            )
            cand_vec = item.pop('cand_vec', None)
            cluster_pool = item.pop('cluster_items', None)
            pool = cluster_pool if cluster_pool else pool_items
            best_ref, best_ref_sim = pick_diverse_library_ref(
                cand_vec, pool or valid_lib_items, ref_usage_counts, max_same=3
            )
            if best_ref:
                item['ref_names'] = str(best_ref.get('title') or '').title()
                item['refSim'] = round(best_ref_sim, 4)
            graph_note = ' · TMDb benzer/önerilen bağı' if item.get('graphHit') else ''
            theme_note = f' · "{user_query}"' if (user_query and not overflow) else ''
            qh = item.get('queryHint') or ''
            if item.get('channel') == 'CLUSTER':
                item['aiReason'] = (
                    f'🔥 Kütüphanendeki <strong>{item.get("ref_names") or "favorilerin"}</strong> ile aynı temada '
                    f'(%{item["aiMatchScore"]} semantik uyum{graph_note}{theme_note}).'
                )
            elif item.get('ref_names') and (item.get('refSim') or 0) >= 0.35:
                item['aiReason'] = (
                    f'🎯 Kütüphanendeki <strong>{item["ref_names"]}</strong> ile '
                    f'%{item["aiMatchScore"]} semantik uyum gösteriyor{qh}.'
                )
            else:
                item['aiReason'] = (
                    f'🎯 İzleme geçmişine %{item["aiMatchScore"]} genel semantik uyum gösteriyor{qh}.'
                )

        for cl_item in cluster_recs:
            if len(visible) >= cluster_visible_cap:
                break
            c_idx = cl_item.get('cluster_idx')
            allow_dup_cluster = bool(user_query)
            if cl_item['id'] not in used_ids and (allow_dup_cluster or c_idx not in seen_cluster_indices):
                _assign_diverse_reason(cl_item, valid_lib_items, len(visible))
                visible.append(cl_item)
                used_ids.add(cl_item['id'])
                seen_cluster_indices.add(c_idx)

        for cl_item in cluster_recs:
            if cl_item['id'] not in used_ids:
                _assign_diverse_reason(
                    cl_item, valid_lib_items, len(visible) + len(overflow_queue), overflow=True
                )
                overflow_queue.append(cl_item)
                used_ids.add(cl_item['id'])

        for g_item in general_recs:
            if len(visible) >= visible_cap:
                break
            if g_item['id'] not in used_ids:
                _assign_diverse_reason(g_item, valid_lib_items, len(visible))
                visible.append(g_item)
                used_ids.add(g_item['id'])

        for g_item in general_recs:
            if len(overflow_queue) >= overflow_cap:
                break
            if g_item['id'] not in used_ids:
                _assign_diverse_reason(
                    g_item, valid_lib_items, len(visible) + len(overflow_queue), overflow=True
                )
                overflow_queue.append(g_item)
                used_ids.add(g_item['id'])

        for item in visible + overflow_queue:
            # JSON yanıtında vektör sızmasın
            item.pop('cand_vec', None)
            item.pop('cluster_items', None)
            meta_info = get_item_metadata(item['id'], user_universe)
            item['poster_url'] = meta_info.get('poster_url', '')
            item['summary'] = meta_info.get('summary', '')
            item['genres'] = meta_info.get('genres', '')
            item['rating'] = meta_info.get('rating', 7.0)
            item['platform'] = meta_info.get('platform', 'Netflix')
            item['year'] = meta_info.get('year', '')
            item['duration_or_seasons'] = meta_info.get('duration_or_seasons', '')
            item['trailer_dub_url'] = meta_info.get('trailer_dub_url', '')
            item['trailer_sub_url'] = meta_info.get('trailer_sub_url', '')
            item['status'] = meta_info.get('status', '')

        cache_key = hashlib.md5(
            f"{user_universe}_{len(lib_set)}_{len(hidden_ids)}_{int(prefer_ended_only)}_{user_query}".encode('utf-8')
        ).hexdigest()

        used_member_llm = False
        if gpt_member and gpt_username and HAS_GPT_ENRICH and openai_client and visible:
            ref_titles = [lib_item_map[i]['title'] for i in list(lib_set)[:5] if i in lib_item_map]
            ctx = user_query or (', '.join(ref_titles) if ref_titles else 'kişisel izleme geçmişi')
            used_member_llm = enrich_with_gpt_notes(
                openai_client,
                visible,
                feature='recommendations',
                context=ctx,
                username=gpt_username,
                db_path=RUNTIME_CACHE_DB_PATH,
            )

        return jsonify({
            'visible': visible,
            'overflowQueue': overflow_queue,
            'recommendations': visible,
            'count': len(visible),
            'meta': {
                'clustersDetected': len(clusters),
                'franchiseGroupsMatched': len(franchise_roots_in_visible),
                'libraryMatched': len(lib_set),
                'cacheKey': cache_key,
                'engineVersion': '2.3',
                'preferEndedOnly': prefer_ended_only,
                'includeOngoing': include_ongoing,
                'usedMemberLLM': used_member_llm,
                'prisonFilter': prison_query,
                'zombieFilter': zombie_query,
                'visibleCap': visible_cap,
                'refDiversity': True,
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[!] Recommendations API Exception: {e}")
        return jsonify({'error': str(e)}), 500


def _normalize_exclusion_ids(ids):
    """
    Exclusion set'ini ID format varyantlarıyla genişletir:
    bare numeric + series_ / movies_ / movie_ — kütüphanedeki her format eşleşsin.
    """
    out = set()
    for raw in ids or []:
        s = str(raw or '').strip()
        if not s:
            continue
        out.add(s)
        lower = s.lower()
        bare = s
        for pfx in ('movies_', 'movie_', 'series_'):
            if lower.startswith(pfx):
                bare = s[len(pfx):]
                break
        bare = str(bare).strip()
        if not bare:
            continue
        out.add(bare)
        out.add(f'series_{bare}')
        out.add(f'movies_{bare}')
        out.add(f'movie_{bare}')
    return out


def _titles_for_ids(ids, title_by_id):
    titles = []
    for raw in ids or []:
        sid = str(raw or '').strip()
        if not sid:
            continue
        title = title_by_id.get(sid)
        if not title:
            bare = sid
            lower = sid.lower()
            for pfx in ('movies_', 'movie_', 'series_'):
                if lower.startswith(pfx):
                    bare = sid[len(pfx):]
                    break
            for key in (sid, bare, f'movies_{bare}', f'movie_{bare}', f'series_{bare}'):
                if key in title_by_id:
                    title = title_by_id[key]
                    break
        if title:
            titles.append(str(title))
    return titles


def _compute_fusion_recommendations(
    user_a_selected,
    user_b_selected,
    user_a_full,
    user_b_full,
    user_universe,
    *,
    is_member=False,
    gpt_member=False,
    gpt_username=None,
    limit=None,
    user_a_name=None,
    user_b_name=None,
):
    """
    Ortak zevk füzyonu: iki kullanıcının seçim vektörlerinden skorla,
    kütüphane exclusion + metadata enrich + isteğe bağlı GPT notları.
    Returns dict: recommendations, count, usedMemberLLM, message (optional).
    """
    user_universe = str(user_universe or 'MOVIES').upper()
    a_sel = [str(x).strip() for x in (user_a_selected or []) if str(x).strip()]
    b_sel = [str(x).strip() for x in (user_b_selected or []) if str(x).strip()]
    a_full = list(user_a_full) if user_a_full is not None else list(a_sel)
    b_full = list(user_b_full) if user_b_full is not None else list(b_sel)
    name_a = (str(user_a_name).strip() if user_a_name else '') or 'birinci kullanıcı'
    name_b = (str(user_b_name).strip() if user_b_name else '') or 'ikinci kullanıcı'

    conn = sqlite3.connect(EMBEDDINGS_DB_PATH)
    c = conn.cursor()
    c.execute(
        'SELECT item_id, item_title, embedding_json FROM item_embeddings WHERE media_type = ?',
        (user_universe,),
    )
    rows = c.fetchall()
    conn.close()

    if not rows:
        return {'recommendations': [], 'count': 0, 'usedMemberLLM': False}

    title_by_id = {r_id: r_title for r_id, r_title, _ in rows}
    a_sel_set = _normalize_exclusion_ids(a_sel)
    b_sel_set = _normalize_exclusion_ids(b_sel)
    combined_exclusion_set = _normalize_exclusion_ids(a_full).union(_normalize_exclusion_ids(b_full))
    combined_exclusion_set |= a_sel_set | b_sel_set

    vecs_a = []
    vecs_b = []
    for r_id, _r_title, r_vec in rows:
        try:
            if r_id in a_sel_set:
                vecs_a.append(np.array(json.loads(r_vec), dtype=np.float32))
            if r_id in b_sel_set:
                vecs_b.append(np.array(json.loads(r_vec), dtype=np.float32))
        except Exception:
            continue

    if not vecs_a or not vecs_b:
        return {
            'recommendations': [],
            'count': 0,
            'usedMemberLLM': False,
            'message': 'İki kullanıcının da seçim verisi gerekli.',
        }

    taste_vec_a = np.mean(vecs_a, axis=0)
    taste_vec_b = np.mean(vecs_b, axis=0)

    scored = []
    for r_id, r_title, r_vec_json in rows:
        if r_id in combined_exclusion_set:
            continue
        try:
            item_vec = json.loads(r_vec_json)
            sim_a = cosine_similarity(taste_vec_a, item_vec)
            sim_b = cosine_similarity(taste_vec_b, item_vec)
            min_fusion_sim = min(sim_a, sim_b)
            if min_fusion_sim >= MIN_SIMILARITY_THRESHOLD:
                scored.append({
                    'id': r_id,
                    'title': r_title,
                    'rawSimilarity': min_fusion_sim,
                    'simA': sim_a,
                    'simB': sim_b,
                })
        except Exception:
            continue

    scored.sort(key=lambda x: x['rawSimilarity'], reverse=True)
    if limit is None:
        limit = 15 if is_member else 8
    top_scored = scored[:int(limit)]

    recommendations = []
    for item in top_scored:
        match_pct = calibrate_score(item['rawSimilarity'])
        rec = {
            'id': item['id'],
            'title': item['title'],
            'rawSimilarity': round(item['rawSimilarity'], 4),
            'aiMatchScore': match_pct,
            'aiReason': '',
        }
        try:
            meta = get_item_metadata(item['id'], user_universe) or {}
            rec['poster_url'] = meta.get('poster_url', '')
            rec['summary'] = meta.get('summary', '')
            rec['genres'] = meta.get('genres', '')
            rec['platform'] = meta.get('platform', 'Netflix')
            rec['rating'] = meta.get('rating', 7.0)
            rec['year'] = meta.get('year', '')
            rec['backdrop_url'] = meta.get('backdrop_url', '')
            rec['trailer_dub_url'] = meta.get('trailer_dub_url', '')
            rec['trailer_sub_url'] = meta.get('trailer_sub_url', '')
            rec['status'] = meta.get('status', '')
            if meta.get('title') and not rec.get('title'):
                rec['title'] = meta.get('title')
        except Exception:
            pass
        recommendations.append(rec)

    titles_a = _titles_for_ids(a_sel, title_by_id)
    titles_b = _titles_for_ids(b_sel, title_by_id)
    gpt_context = (
        f"ortak zevk füzyonu | names: {name_a}||{name_b} | "
        f"{name_a} seçimleri: {', '.join(titles_a) if titles_a else '—'} "
        f"| {name_b} seçimleri: {', '.join(titles_b) if titles_b else '—'}"
    )

    used_member_llm = False
    if gpt_member and gpt_username and HAS_GPT_ENRICH and openai_client and recommendations:
        used_member_llm = enrich_with_gpt_notes(
            openai_client,
            recommendations,
            feature='social',
            context=gpt_context,
            username=gpt_username,
            db_path=RUNTIME_CACHE_DB_PATH,
        )
    if not used_member_llm:
        for rec in recommendations:
            if not (rec.get('aiReason') or '').strip():
                rec['aiReason'] = ''

    return {
        'recommendations': recommendations,
        'count': len(recommendations),
        'usedMemberLLM': used_member_llm,
    }


@app.route('/api/social_recommendations', methods=['POST'])
def api_social_recommendations():
    """
    👥 SOSYAL / ORTAK ZEVK FÜZYONU (SOCIAL MULTI-USER FUSION)
    """
    try:
        data = request.get_json() or {}
        user_a_selected = data.get('userASelected5', data.get('userALibrary', []))
        user_a_full = data.get('userAFullLibrary', user_a_selected)

        user_b_selected = data.get('userBSelected5', data.get('userBLibrary', []))
        user_b_full = data.get('userBFullLibrary', user_b_selected)

        user_universe = str(data.get('userUniverse', 'MOVIES')).upper()
        user_a_name = data.get('userAName') or data.get('from') or ''
        user_b_name = data.get('userBName') or data.get('to') or ''

        is_member, user_token = validate_user_token(request)
        gpt_member, gpt_username = resolve_gpt_member(request)

        result = _compute_fusion_recommendations(
            user_a_selected,
            user_b_selected,
            user_a_full,
            user_b_full,
            user_universe,
            is_member=bool(is_member),
            gpt_member=bool(gpt_member),
            gpt_username=gpt_username,
            user_a_name=user_a_name,
            user_b_name=user_b_name,
        )

        payload = {
            'recommendations': result.get('recommendations') or [],
            'count': result.get('count', 0),
            'usedAI': True,
            'usedMemberLLM': result.get('usedMemberLLM', False),
        }
        if result.get('message'):
            payload['message'] = result['message']
        return jsonify(payload)

    except Exception as e:
        print(f"[!] Social Recommendations API Exception: {e}")
        return jsonify({'error': str(e)}), 500


def _require_auth_user():
    is_member, username = validate_user_token(request)
    if not is_member or not username:
        return None
    if str(username).lower() in ('guest', 'kullanıcı', 'kullanici'):
        return None
    return username


@app.route('/api/friends', methods=['GET'])
def api_friends_list():
    """Onaylanmış arkadaş listesi."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        friends = social_db.arkadas_listesini_getir(username)
        return jsonify({'ok': True, 'friends': friends})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/friends/request', methods=['POST'])
def api_friends_request():
    """Arkadaşlık isteği gönder."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        data = request.get_json(silent=True) or {}
        target = str(data.get('username') or data.get('to') or '').strip()
        ok, msg = social_db.arkadaslik_istegi_gonder(username, target)
        code = 200 if ok else 400
        return jsonify({'ok': ok, 'message': msg}), code
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/friends/incoming', methods=['GET'])
def api_friends_incoming():
    """Gelen arkadaşlık istekleri."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        pending = social_db.bekleyen_istekleri_getir(username)
        return jsonify({'ok': True, 'requests': pending})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/friends/respond', methods=['POST'])
def api_friends_respond():
    """Arkadaşlık isteğini kabul/reddet."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        data = request.get_json(silent=True) or {}
        req_id = int(data.get('requestId') or data.get('id') or 0)
        accept = bool(data.get('accept', True))
        ok, msg = social_db.istek_yanitla(req_id, accept, username)
        friends = social_db.arkadas_listesini_getir(username) if ok else []
        code = 200 if ok else 400
        return jsonify({'ok': ok, 'message': msg, 'friends': friends}), code
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/friends/remove', methods=['POST'])
def api_friends_remove():
    """Arkadaşlıktan çıkar."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        data = request.get_json(silent=True) or {}
        target = str(data.get('username') or data.get('friend') or '').strip()
        ok, msg = social_db.arkadas_sil(username, target)
        friends = social_db.arkadas_listesini_getir(username)
        return jsonify({'ok': ok, 'message': msg, 'friends': friends})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/friends/rehydrate', methods=['POST'])
def api_friends_rehydrate():
    """
    Render free disk silinince sunucu arkadaş listesi boşalır.
    İstemci localStorage'daki listeyi sunucuya geri yazar (merge).
    """
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        data = request.get_json(silent=True) or {}
        friends_in = data.get('friends') or data.get('friendList') or []
        if not isinstance(friends_in, list):
            return jsonify({'ok': False, 'error': 'friends listesi gerekli'}), 400
        ok, msg, merged = social_db.arkadasliklari_birlestir(username, friends_in)
        return jsonify({
            'ok': ok,
            'message': msg,
            'friends': merged,
            'rehydrated': True,
            'count': len(merged),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/fusion/invite', methods=['POST'])
def api_fusion_invite():
    """Ortak zevk füzyonu isteği gönder (5 seçim ile)."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        data = request.get_json(silent=True) or {}
        target = str(data.get('friend') or data.get('to') or '').strip()
        universe = str(data.get('universe') or data.get('userUniverse') or 'MOVIES').upper()
        selections = data.get('selections') or data.get('selectedIds') or []
        library = data.get('library') or data.get('fullLibrary') or []
        ok, msg, invite = social_db.fuzyon_istegi_olustur(
            username, target, universe, selections, kitaplik=library
        )
        code = 200 if ok else 400
        return jsonify({'ok': ok, 'message': msg, 'invite': invite}), code
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/fusion/incoming', methods=['GET'])
def api_fusion_incoming():
    """Gelen füzyon istekleri."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        pending = social_db.bekleyen_fuzyon_istekleri(username)
        return jsonify({'ok': True, 'requests': pending})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/fusion/outgoing', methods=['GET'])
def api_fusion_outgoing():
    """Giden / tamamlanan füzyon istekleri (gönderen)."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        outgoing = social_db.giden_fuzyon_istekleri(username)
        completed = social_db.tamamlanan_fuzyonlar(username)
        return jsonify({'ok': True, 'outgoing': outgoing, 'completed': completed})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/fusion/respond', methods=['POST'])
def api_fusion_respond():
    """Füzyon isteğini reddet veya 5 seçimle kabul et; kabulde sonuçları hesapla."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        data = request.get_json(silent=True) or {}
        req_id = int(data.get('requestId') or data.get('id') or 0)
        accept = bool(data.get('accept', True))
        selections = data.get('selections') or data.get('selectedIds') or []
        library = data.get('library') or data.get('fullLibrary') or []
        ok, msg, invite = social_db.fuzyon_istegi_yanitla(
            req_id, username, accept, selections, kitaplik=library
        )

        if ok and invite and invite.get('status') == 'tamamlandi':
            try:
                sel_a = invite.get('senderSelections') or []
                sel_b = invite.get('receiverSelections') or []
                lib_a = invite.get('senderLibrary') or []
                lib_b = invite.get('receiverLibrary') or []
                full_a = lib_a if lib_a else sel_a
                full_b = lib_b if lib_b else sel_b
                # Kütüphane + seçimler exclusion (lib boşsa seçimlere düşer)
                excl_a = list(full_a) + list(sel_a)
                excl_b = list(full_b) + list(sel_b)

                is_member, _tok = validate_user_token(request)
                gpt_member, gpt_username = resolve_gpt_member(request)
                computed = _compute_fusion_recommendations(
                    sel_a,
                    sel_b,
                    excl_a,
                    excl_b,
                    invite.get('universe') or 'MOVIES',
                    is_member=bool(is_member),
                    gpt_member=bool(gpt_member),
                    gpt_username=gpt_username,
                    user_a_name=invite.get('from') or '',
                    user_b_name=invite.get('to') or '',
                )
                recs = computed.get('recommendations') or []
                if recs:
                    sok, smsg, updated = social_db.fuzyon_sonuclari_kaydet(
                        invite['id'], username, recs
                    )
                    if sok and updated:
                        invite = updated
            except Exception as compute_err:
                print(f"[!] Fusion auto-compute uyarısı: {compute_err}")

        payload = {
            'ok': ok,
            'message': msg,
            'invite': invite,
            'overlap': (invite or {}).get('overlap') if invite else None,
            'results': (invite or {}).get('results') if invite else None,
        }
        code = 200 if ok else 400
        return jsonify(payload), code
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/fusion/<int:invite_id>/results', methods=['POST'])
def api_fusion_save_results(invite_id):
    """İstemci hesaplı füzyon sonuçlarını kaydet (katılımcılar)."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        data = request.get_json(silent=True) or {}
        recommendations = data.get('recommendations') or data.get('results') or []
        if not isinstance(recommendations, list):
            return jsonify({'ok': False, 'error': 'recommendations listesi gerekli'}), 400
        ok, msg, invite = social_db.fuzyon_sonuclari_kaydet(
            invite_id, username, recommendations
        )
        code = 200 if ok else 400
        return jsonify({'ok': ok, 'message': msg, 'invite': invite}), code
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/fusion/<int:invite_id>', methods=['GET'])
def api_fusion_get(invite_id):
    """Tek füzyon isteği detayı (katılımcılar)."""
    if not HAS_SOCIAL_DB:
        return jsonify({'ok': False, 'error': 'social_unavailable'}), 503
    username = _require_auth_user()
    if not username:
        return jsonify({'ok': False, 'error': 'auth_required'}), 401
    try:
        invite = social_db.fuzyon_istegi_getir(invite_id, username)
        if not invite:
            return jsonify({'ok': False, 'error': 'not_found'}), 404
        return jsonify({'ok': True, 'invite': invite})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/analytics/rec_click', methods=['POST'])
def track_rec_click():
    """
    📊 ÖNERİ TIKLAMA VE CTR ANALİTİK KAYDI
    """
    try:
        data = request.get_json() or {}
        item_id = str(data.get('itemId', ''))
        rec_source = str(data.get('recSource', 'hybrid'))
        is_member, username = validate_user_token(request)
        username = username or 'guest'

        conn = sqlite3.connect(RUNTIME_CACHE_DB_PATH)
        c = conn.cursor()
        c.execute('INSERT INTO analytics_events (event_type, item_id, username, rec_source, timestamp) VALUES (?, ?, ?, ?, ?)',
                  ('rec_click', item_id, username, rec_source, time.time()))
        conn.commit()
        conn.close()
        return jsonify({'status': 'ok', 'logged': True})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/item/<item_id>', methods=['GET'])
def get_item_by_id_api(item_id):
    """
    🔍 TEKİL YAPIM DETAY LOOKUP ENDPOINT
    """
    try:
        media_type = 'SERIES' if str(item_id).startswith('series_') else 'MOVIES'
        meta = get_item_metadata(str(item_id), media_type)
        return jsonify(meta)
    except Exception as e:
        return jsonify({'error': str(e)}), 404


@app.route('/api/error-reports', methods=['POST'])
def create_error_report():
    """Kartlardan gelen içerik hata bildirimlerini SQLite + JSON dosyasına yazar (UI'da listelenmez)."""
    try:
        data = request.get_json(silent=True) or {}
        item_id = str(data.get('itemId') or '').strip()
        if not item_id:
            return jsonify({'error': 'itemId zorunlu.'}), 400

        media = str(data.get('mediaType') or 'SERIES').upper()
        media = 'MOVIES' if media == 'MOVIES' else 'SERIES'
        fields_raw = data.get('fields') or []
        selected = []
        if isinstance(fields_raw, list):
            for f in fields_raw:
                key = str(f).strip()
                if key in ERROR_REPORT_ALLOWED_FIELDS and key not in selected:
                    selected.append(key)
        if not selected:
            return jsonify({'error': 'En az bir hata alanı seçilmeli.'}), 400

        item_title = str(data.get('itemTitle') or '').strip()[:200]
        note = str(data.get('note') or '').strip()[:300]
        username = str(data.get('username') or '').strip()[:80] or None

        conn = _user_db_conn()
        c = conn.cursor()
        c.execute(
            '''INSERT INTO content_error_reports
               (item_id, item_title, media_type, fields_json, note, username)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (item_id[:120], item_title, media, json.dumps(selected, ensure_ascii=False), note or None, username)
        )
        report_id = c.lastrowid
        conn.commit()
        conn.close()

        entry = {
            'id': report_id,
            'itemId': item_id[:120],
            'itemTitle': item_title,
            'mediaType': media,
            'fields': selected,
            'note': note or None,
            'username': username,
            'status': 'open',
            'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S')
        }
        _append_error_report_json(entry)
        return jsonify({'ok': True, 'id': report_id, 'message': 'Hata bildirimi kaydedildi.'})
    except Exception as e:
        return jsonify({'error': 'Hata bildirimi kaydedilemedi.', 'detail': str(e)}), 500


@app.route('/api/error-reports', methods=['GET'])
def list_error_reports():
    """Yalnızca yönetici — hata bildirimleri."""
    admin_ok, _admin = require_admin_request(request)
    if not admin_ok:
        return jsonify({'error': 'Yetkisiz'}), 403
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = max(1, min(100, limit or 50))
        status = request.args.get('status')
        conn = _user_db_conn()
        try:
            if isinstance(conn, sqlite3.Connection):
                conn.row_factory = sqlite3.Row
        except Exception:
            pass
        c = conn.cursor()
        if status:
            rows = c.execute(
                '''SELECT id, item_id, item_title, media_type, fields_json, note, username, status, created_at
                   FROM content_error_reports WHERE status = ? ORDER BY created_at DESC LIMIT ?''',
                (str(status), limit)
            ).fetchall()
        else:
            rows = c.execute(
                '''SELECT id, item_id, item_title, media_type, fields_json, note, username, status, created_at
                   FROM content_error_reports ORDER BY created_at DESC LIMIT ?''',
                (limit,)
            ).fetchall()
        conn.close()

        reports = []
        for r in rows:
            try:
                fields = json.loads(r['fields_json'] or '[]')
            except Exception:
                fields = []
            reports.append({
                'id': r['id'],
                'itemId': r['item_id'],
                'itemTitle': r['item_title'],
                'mediaType': r['media_type'],
                'fields': fields,
                'note': r['note'],
                'username': r['username'],
                'status': r['status'],
                'createdAt': r['created_at']
            })
        return jsonify({'reports': reports, 'count': len(reports)})
    except Exception as e:
        return jsonify({'error': 'Hata bildirimleri okunamadı.', 'detail': str(e)}), 500


@app.route('/api/error-reports/<int:report_id>', methods=['PATCH'])
def update_error_report_status(report_id):
    admin_ok, _admin = require_admin_request(request)
    if not admin_ok:
        return jsonify({'error': 'Yetkisiz'}), 403
    try:
        data = request.get_json(silent=True) or {}
        status = str(data.get('status') or '').strip().lower()
        if status not in ('open', 'resolved', 'ignored'):
            return jsonify({'error': 'Geçersiz status.'}), 400
        conn = _user_db_conn()
        c = conn.cursor()
        info = c.execute('UPDATE content_error_reports SET status = ? WHERE id = ?', (status, report_id))
        conn.commit()
        updated = info.rowcount
        conn.close()
        if not updated:
            return jsonify({'error': 'Kayıt bulunamadı.'}), 404
        return jsonify({'ok': True, 'id': report_id, 'status': status})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/feedback', methods=['POST'])
def create_user_feedback():
    """Genel geri bildirim kutusu — SQLite'a yazar."""
    try:
        data = request.get_json(silent=True) or {}
        message = str(data.get('message') or '').strip()
        if not message:
            return jsonify({'error': 'Mesaj boş olamaz.'}), 400
        username = str(data.get('username') or '').strip()[:80] or None
        media = str(data.get('mediaType') or '').strip().upper() or None
        conn = _user_db_conn()
        c = conn.cursor()
        c.execute(
            'INSERT INTO user_feedback (username, message, media_type) VALUES (?, ?, ?)',
            (username, message[:2000], media)
        )
        fid = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'id': fid})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/feedback', methods=['GET'])
def list_user_feedback():
    """Yalnızca yönetici — genel geri bildirim mesajları."""
    admin_ok, _admin = require_admin_request(request)
    if not admin_ok:
        return jsonify({'error': 'Yetkisiz'}), 403
    try:
        limit = request.args.get('limit', 50, type=int)
        limit = max(1, min(100, limit or 50))
        conn = _user_db_conn()
        try:
            if isinstance(conn, sqlite3.Connection):
                conn.row_factory = sqlite3.Row
        except Exception:
            pass
        c = conn.cursor()
        rows = c.execute(
            '''SELECT id, username, message, media_type, status, created_at
               FROM user_feedback ORDER BY created_at DESC LIMIT ?''',
            (limit,)
        ).fetchall()
        conn.close()
        feedback = [{
            'id': r['id'],
            'username': r['username'],
            'message': r['message'],
            'mediaType': r['media_type'],
            'status': r['status'],
            'createdAt': r['created_at']
        } for r in rows]
        return jsonify({'feedback': feedback, 'count': len(feedback)})
    except Exception as e:
        return jsonify({'error': 'Geri bildirimler okunamadı.', 'detail': str(e)}), 500


@app.route('/api/tmdb-image', methods=['GET', 'HEAD', 'OPTIONS'])
def tmdb_image_proxy():
    """TMDB afiş proxy — istemci engellerini aşmak için (TR vb.). CDN dostu cache."""
    import requests
    from flask import Response

    if request.method == 'OPTIONS':
        resp = app.make_response(('', 204))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp

    img_path = request.args.get('path', '')
    size = request.args.get('size', 'w342')
    allowed_sizes = {'w92', 'w154', 'w185', 'w342', 'w500', 'w780', 'original'}
    if size not in allowed_sizes:
        size = 'w342'

    if not img_path:
        return "Missing 'path' parameter", 400

    if not img_path.startswith('/'):
        img_path = '/' + img_path

    if not re.match(r'^/[a-zA-Z0-9_\-\./]+$', img_path):
        return "Invalid path format", 400

    tmdb_url = f"https://image.tmdb.org/t/p/{size}{img_path}"

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
        }
        res = requests.get(tmdb_url, headers=headers, timeout=12)
        if res.status_code != 200:
            return f"Failed to fetch image from TMDB: status {res.status_code}", res.status_code

        content_type = res.headers.get('Content-Type', 'image/jpeg')
        response_headers = {
            'Content-Type': content_type,
            'Cache-Control': 'public, max-age=31536000, immutable',
            'Access-Control-Allow-Origin': '*',
            'Cross-Origin-Resource-Policy': 'cross-origin',
        }
        if request.method == 'HEAD':
            return Response(b'', headers=response_headers)
        return Response(res.content, headers=response_headers)
    except Exception as e:
        return f"Proxy error: {str(e)}", 500


@app.route('/', methods=['GET', 'HEAD'])
def root():
    return jsonify({
        'ok': True,
        'service': 'dizimibul-api',
        'health': '/api/health',
        'hint': 'Bu bir API. Arayüz GitHub Pages üzerinde çalışır.',
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    emb_ok = os.path.exists(EMBEDDINGS_DB_PATH)
    user_backend = 'unknown'
    try:
        from user_db import user_db_backend_name

        user_backend = user_db_backend_name()
    except Exception:
        pass
    return jsonify({
        'ok': True,
        'embeddings_db': emb_ok,
        'openai': bool(openai_client),
        'auth': HAS_AUTH_UTILS,
        'social': HAS_SOCIAL_DB,
        'user_db': user_backend,
    })


if __name__ == '__main__':
    print("==========================================================================")
    print(f"🚀 DIZIMIBUL SEMANTIC BACKEND SERVER RUNNING ON HTTP://LOCALHOST:{PORT}")
    print("==========================================================================")
    app.run(host='0.0.0.0', port=PORT, debug=False)
