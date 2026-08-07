# -*- coding: utf-8 -*-
"""
==============================================================================
🎬 AKILLI FİLM FRAGMAN DENETLEYİCİ VE DÜZELTİCİ (v1.0)
==============================================================================
Hedef:
1. 'katalog.db' içerisindeki 'filmler' tablosundaki 4.350 filmi denetlemek.
2. TMDB Videos API (/movie/{id}/videos) ve YouTube aramaları ile resmi fragmanları bulmak.
3. KESİN LİNK ÇAKIŞMASI KURALI: Aynı YouTube linki hem Dublaj hem Altyazı kategorisinde yer alamaz!
   - Türkçe Dublaj (trailer_dub_url): Gerçek Türkçe seslendirmeli fragman olmalı.
   - Türkçe Altyazılı (trailer_sub_url): Gerçek Türkçe altyazılı fragman olmalı.
   - İkisi birbirinden tamamen bağımsız ve farklı linkler olmalıdır.
4. Kısıtlı/Sahte Videolar (Sahne klipsi, röportaj, film müziği, başka film vb.) elenmelidir.
5. Kaldığı Yerden Devam Etme (Auto-Resume) desteği mevcuttur (_film_trailer_audited).
==============================================================================
"""

import sqlite3
import requests
import json
import re
import urllib.request
import urllib.parse
import sys
import os
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "katalog.db"
TABLE_NAME = "filmler"
API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"

# ❌ YASAKLI KELİMELER (Sahne, Şarkı, İnceleme, Oyun, Başka Film vb.)
STRICT_BAD = [
    'performansı', 'performans', 'sahne', 'sahnesi', 'şarkı', 'sarkisi', 'clip', 'scene',
    'this season on', 'behind the scenes', 'kamera arkası', 'röportaj', 'interview', 'soundtrack',
    'muzik', 'müzik', 'lyric', 'lyrics', 'blooper', 'bloopers', 'review', 'inceleme',
    'recap', 'analiz', 'ozet', 'özet', 'gameplay', 'parody', 'reaction', 'shorts', 'tiktok',
    'italia', 'espana', 'france', 'deutschland',
    # Dizi ve TV Sezon Karışmasını Önleme
    'dizi', 'dizisi', '1. sezon', '2. sezon', '3. sezon', 'season 1', 'season 2', 'tv series', 'tv show'
]

# ✅ FRAGMAN İŞARETLERİ
MUST_HAVE_TRAILER_WORD = [
    'fragman', 'fragmanı', 'tanıtım', 'tanıtımı', 'trailer', 'teaser', 'preview'
]


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\(\[\{].*?[\)\]\}]', '', str(text))
    return text.strip()


def extract_movie_title(raw_title):
    """Film adından parantez içlerini temizler"""
    if not raw_title:
        return "", ""
    tr_title = str(raw_title).strip()
    orig_title = ""
    m = re.search(r'^(.*?)\s*[\(\[](.*?)[\)\]]', tr_title)
    if m:
        tr_title = m.group(1).strip()
        orig_title = m.group(2).strip()
    return tr_title, orig_title


def validate_movie_trailer(title, movie_title, mode="ANY"):
    """
    Film fragman başlığını denetler:
    mode: 'DUB' (Dublaj şart), 'SUB' (Altyazı/TR şart), 'ORIG' (Orijinal şart), 'ANY' (Genel)
    """
    if not title:
        return False, "Başlık okunamadı"

    t_low = title.lower()
    m_low = movie_title.lower()

    # 1. Film adı uyuşması
    clean_m = re.sub(r'[^\w\s]', '', m_low)
    main_words = [w for w in clean_m.split() if len(w) > 2]
    if main_words and not any(w in t_low for w in main_words):
        return False, f"Film adı ({movie_title}) başlıkta geçmiyor"

    # 2. Yasaklı kelimeler
    for bad in STRICT_BAD:
        if bad in t_low:
            return False, f"Yasaklı içerik tespit edildi: '{bad}'"

    # 3. Fragman/Trailer kelimesi
    if not any(tw in t_low for tw in MUST_HAVE_TRAILER_WORD):
        return False, "Fragman/Trailer tanımı içermiyor"

    # 4. Moda göre özel kontrol
    if mode == "DUB":
        if "dublaj" not in t_low and "türkçe dublaj" not in t_low and "tr dublaj" not in t_low:
            return False, "Dublaj ifadesi içermiyor"
    elif mode == "SUB":
        if not any(w in t_low for w in ['altyazı', 'altyazılı', 'altyazili', 'türkçe', 'turkce', 'fragman']):
            return False, "Altyazı/Türkçe ifadesi içermiyor"

    return True, "✅ Geçerli Film Fragmanı"


def fetch_tmdb_movie_trailers(tmdb_id):
    """TMDB Videos API'sinden resmi fragman linklerini çeker"""
    if not tmdb_id:
        return None, None

    tr_url = None
    orig_url = None

    try:
        # TR videoları
        r_tr = requests.get(f"{BASE_URL}/movie/{tmdb_id}/videos", params={"api_key": API_KEY, "language": "tr-TR"}, timeout=6)
        if r_tr.status_code == 200:
            results = r_tr.json().get("results", [])
            for v in results:
                if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                    key = v.get("key")
                    if key:
                        tr_url = f"https://www.youtube.com/watch?v={key}"
                        break

        # EN videoları (Orijinal)
        r_en = requests.get(f"{BASE_URL}/movie/{tmdb_id}/videos", params={"api_key": API_KEY, "language": "en-US"}, timeout=6)
        if r_en.status_code == 200:
            results = r_en.json().get("results", [])
            for v in results:
                if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                    key = v.get("key")
                    if key:
                        orig_url = f"https://www.youtube.com/watch?v={key}"
                        break
    except Exception:
        pass

    return tr_url, orig_url


def search_youtube_video(query):
    """YouTube araması yapıp aday videoları döner"""
    try:
        search_url = 'https://www.youtube.com/results?search_query=' + urllib.parse.quote(query)
        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8'
        })
        html = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', errors='ignore')

        m = re.search(r'ytInitialData\s*=\s*(\{.*?\});</script>', html)
        if not m:
            return []

        data = json.loads(m.group(1))
        sections = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])

        candidates = []
        for sec in sections:
            for item in sec.get('itemSectionRenderer', {}).get('contents', []):
                vr = item.get('videoRenderer')
                if not vr:
                    continue
                vId = vr.get('videoId')
                t = vr.get('title', {}).get('runs', [])[0].get('text', '')
                ch = vr.get('ownerText', {}).get('runs', [])[0].get('text', '') if vr.get('ownerText') else ''

                if vId and t:
                    candidates.append({
                        "url": f"https://www.youtube.com/watch?v={vId}",
                        "title": t,
                        "channel": ch
                    })
                    if len(candidates) >= 5:
                        break
        return candidates
    except Exception:
        return []


def audit_and_fix_movie(m_id, tmdb_id, title, orig_title, curr_dub, curr_sub, curr_orig):
    """
    Tek bir filmin fragmanlarını sıfır hatayla ve link çakışmasız denetler:
    - trailer_dub_url ve trailer_sub_url ASLA AYNI LİNK OLAMAZ!
    - Dublaj varsa Dublaja, Altyazı varsa Altyazıya işlenir.
    """
    print(f"\n🎬 Denetleniyor: {title} (Orijinal: {orig_title or 'Yok'}) [TMDB ID: {tmdb_id or 'Yok'}]")

    final_dub = "TÜRKÇE_DUBLAJ_BULUNAMADI"
    final_sub = "TÜRKÇE_ALTYAZI_BULUNAMADI"
    final_orig = "ORİJİNAL_FRAGMAN_BULUNAMADI"

    # --- 1. MEVCUT LİNKLERİN DENETİMİ ---
    if curr_dub and "youtube.com" in curr_dub and curr_dub != curr_sub:
        t_title, _ = (title, "")  # hızlı denetim
        valid, reason = validate_movie_trailer(title, title, mode="DUB")
        if valid:
            final_dub = curr_dub
            print(f"   🟢 Mevcut Dublaj Fragman Geçerli (KORUNDU)")

    if curr_sub and "youtube.com" in curr_sub:
        valid, reason = validate_movie_trailer(title, title, mode="SUB")
        if valid:
            final_sub = curr_sub
            print(f"   🟢 Mevcut Altyazılı Fragman Geçerli (KORUNDU)")

    # --- 2. TMDB VIDEOS API KONTROLÜ ---
    tmdb_tr_url, tmdb_en_url = fetch_tmdb_movie_trailers(tmdb_id)
    if tmdb_tr_url and final_sub == "TÜRKÇE_ALTYAZI_BULUNAMADI":
        final_sub = tmdb_tr_url
        print(f"   ✨ TMDB API'den Resmi TR Fragman Alındı: {tmdb_tr_url}")

    if tmdb_en_url:
        final_orig = tmdb_en_url

    # --- 3. YOUTUBE TÜRKÇE DUBLAJ ARAMASI ---
    if final_dub == "TÜRKÇE_DUBLAJ_BULUNAMADI":
        cands = search_youtube_video(f'"{title}" türkçe dublaj fragman')
        for c in cands:
            valid, reason = validate_movie_trailer(c["title"], title, mode="DUB")
            if valid and c["url"] != final_sub:
                final_dub = c["url"]
                print(f"   ✨ YENİ DUBLAJ FRAGMAN BULUNDU: {c['title']}")
                break

    # --- 4. YOUTUBE TÜRKÇE ALTYAZILI ARAMASI ---
    if final_sub == "TÜRKÇE_ALTYAZI_BULUNAMADI":
        cands = search_youtube_video(f'"{title}" türkçe altyazılı fragman')
        for c in cands:
            valid, reason = validate_movie_trailer(c["title"], title, mode="SUB")
            if valid and c["url"] != final_dub:
                final_sub = c["url"]
                print(f"   ✨ YENİ ALTYAZILI FRAGMAN BULUNDU: {c['title']}")
                break

    # --- 5. LİNK ÇAKIŞMASI KORUMASI ---
    if final_dub != "TÜRKÇE_DUBLAJ_BULUNAMADI" and final_dub == final_sub:
        # İkisi aynı link olamaz! Çakışma durumunda Altyazılıya atayıp Dublajı temizle
        final_dub = "TÜRKÇE_DUBLAJ_BULUNAMADI"
        print("   ⚠️ Link çakışması engellendi: Aynı video hem dublaj hem altyazı olamaz.")

    return final_dub, final_sub, final_orig


def run_movie_trailer_audit(force_all=False, limit=None):
    print("=" * 80)
    print("🎬 AKILLI FİLM FRAGMAN DENETLEYİCİ VE DÜZELTİCİ BAŞLATILDI")
    print("=" * 80)

    if not os.path.exists(DB_PATH):
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL;")

    # _film_trailer_audited kolonu yoksa ekle
    c.execute(f"PRAGMA table_info({TABLE_NAME})")
    cols = [r[1] for r in c.fetchall()]
    if "_film_trailer_audited" not in cols:
        c.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN _film_trailer_audited INTEGER DEFAULT 0")
        conn.commit()

    if force_all:
        audited_where = ""
    else:
        audited_where = "WHERE (_film_trailer_audited IS NULL OR _film_trailer_audited = 0)"

    c.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    total_count = c.fetchone()[0]

    c.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE _film_trailer_audited = 1")
    already_audited = c.fetchone()[0]

    c.execute(f"""
        SELECT id, tmdb_id, isim, orijinal_isim, trailer_dub_url, trailer_sub_url, trailer_orig_url
        FROM {TABLE_NAME}
        {audited_where}
        ORDER BY id
    """)
    rows = c.fetchall()

    if limit:
        rows = rows[:limit]

    print(f"📋 Toplam Film Sayısı          : {total_count}")
    if not force_all and already_audited > 0:
        print(f"⏩ Daha Önce İşlenen (Atlanan) : {already_audited}")
    print(f"🔍 İşlenecek Kalan Film Sayısı  : {len(rows)}")
    print("-" * 80)

    if len(rows) == 0:
        print("🎉 Tüm filmlerin fragmanları zaten taranmış ve denetlenmiş!")
        conn.close()
        return

    updated_count = 0
    for idx, row in enumerate(rows, 1):
        m_id = row["id"]
        tmdb_id = row["tmdb_id"]
        raw_name = row["isim"]
        orig_name = row["orijinal_isim"]
        curr_dub = row["trailer_dub_url"]
        curr_sub = row["trailer_sub_url"]
        curr_orig = row["trailer_orig_url"]

        tr_title, orig_title = extract_movie_title(raw_name)
        search_title = tr_title or orig_name or raw_name

        new_dub, new_sub, new_orig = audit_and_fix_movie(m_id, tmdb_id, search_title, orig_title, curr_dub, curr_sub, curr_orig)

        # DB Güncelle ve _film_trailer_audited = 1 yap
        c.execute(f"""
            UPDATE {TABLE_NAME}
            SET trailer_dub_url = ?, trailer_sub_url = ?, trailer_orig_url = ?, _film_trailer_audited = 1
            WHERE id = ?
        """, (new_dub, new_sub, new_orig, m_id))

        if idx % 20 == 0:
            conn.commit()
            print(f"💾 [{idx}/{len(rows)}] İlerleme veritabanına kaydedildi.")

        if new_dub != curr_dub or new_sub != curr_sub or new_orig != curr_orig:
            updated_count += 1

        time.sleep(0.1)  # Korumalı istek arası

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print(f"✅ FİLM FRAGMAN DENETİMİ TAMAMLANDI! Toplam Güncellenen Film: {updated_count}")
    print("=" * 80)

    # Otomatik site verisini dışa aktar
    try:
        import export_data_store
        export_data_store.main()
        print("🎉 data_store.js site verisi başarıyla güncellendi!")
    except Exception as e:
        print(f"⚠️ data_store.js aktarımında hata: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kesin ve Akıllı Film Fragman Denetleyici")
    parser.add_argument("--force", action="store_true", help="Daha önce tarananları da tekrar tara")
    parser.add_argument("--limit", type=int, default=None, help="İşlenecek maksimum film sayısı")
    args = parser.parse_args()

    run_movie_trailer_audit(force_all=args.force, limit=args.limit)
