"""
==============================================================================
🍿 HIZLI PARALEL FRAGMAN DOLDURUCU (CANLI İLERLEME LOGLU)
==============================================================================
Veritabanlarındaki fragmanı olmayan tüm film ve dizileri TMDB API üzerinden
10 eşzamanlı kanaldan paralel tatar, YouTube fragman linklerini bulup kaydeder!

Kullanım:
python yeni_fragman_taramasi.py
==============================================================================
"""

import sqlite3
import json
import urllib.request
import urllib.parse
import sys
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TMDB_KEY = '802b2c4b88ea1183e50e6b285a27696e'
headers = {'User-Agent': 'Mozilla/5.0'}

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        return None

def process_single_movie(row):
    db_id, tmdb_id, title = row
    if not tmdb_id:
        return db_id, title, None

    url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_KEY}&language=tr-TR"
    data = fetch_json(url)
    results = data.get('results', []) if data else []

    if not results:
        url_en = f"https://api.themoviedb.org/3/movie/{tmdb_id}/videos?api_key={TMDB_KEY}&language=en-US"
        data_en = fetch_json(url_en)
        results = data_en.get('results', []) if data_en else []

    yt_link = None
    for vid in results:
        if vid.get('site') == 'YouTube' and vid.get('type') in ['Trailer', 'Teaser']:
            key = vid.get('key')
            if key:
                yt_link = f"https://www.youtube.com/embed/{key}"
                break

    return db_id, title, yt_link

def scan_movies():
    print("\n--- 🎬 FİLMLER İÇİN FRAGMAN TARAMASI BAŞLATILIYOR ---")
    conn = sqlite3.connect('katalog.db', timeout=60.0)
    c = conn.cursor()
    c.execute('SELECT id, tmdb_id, isim FROM filmler WHERE tmdb_id IS NOT NULL AND tmdb_id != "" AND (fragman_url IS NULL OR fragman_url = "")')
    rows = c.fetchall()
    total = len(rows)

    print(f"📦 Fragmanı eksik {total} adet film bulundu. 10 paralel kanaldan taranıyor...\n")
    
    updated_count = 0
    completed_idx = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_single_movie, r) for r in rows]
        for future in as_completed(futures):
            completed_idx += 1
            db_id, title, yt_link = future.result()
            pct = (completed_idx / total) * 100
            
            if yt_link:
                c.execute('''
                    UPDATE filmler 
                    SET fragman_url = ?, trailer_dub_url = ?, trailer_sub_url = ? 
                    WHERE id = ?
                ''', (yt_link, yt_link, yt_link, db_id))
                updated_count += 1
                print(f"[{completed_idx}/{total}] (%{pct:.1f}) 🎬 {title[:30]:<30} -> Fragman Eklendi ✅")
            else:
                print(f"[{completed_idx}/{total}] (%{pct:.1f}) 🎬 {title[:30]:<30} -> Fragman Yok ❌")

            if completed_idx % 20 == 0:
                conn.commit()

    conn.commit()
    conn.close()
    print(f"\n✅ {updated_count} film için YouTube fragman bağlantısı başarıyla eklendi!")

def process_single_show(row):
    # Dizilerde PK = TMDB id — isim aramasına düşmeden doğrudan kullan (Mother/Father, Avatar karışması önlenir)
    if len(row) >= 3:
        db_id, title, year = row[0], row[1], (row[2] or "")[:4]
    else:
        db_id, title, year = row[0], row[1], ""

    tmdb_id = db_id
    v_url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/videos?api_key={TMDB_KEY}&language=tr-TR"
    v_data = fetch_json(v_url)
    results = v_data.get('results', []) if v_data else []

    if not results:
        v_url_en = f"https://api.themoviedb.org/3/tv/{tmdb_id}/videos?api_key={TMDB_KEY}&language=en-US"
        v_data_en = fetch_json(v_url_en)
        results = v_data_en.get('results', []) if v_data_en else []

    yt_link = None
    for vid in results:
        if vid.get('site') == 'YouTube' and vid.get('type') in ['Trailer', 'Teaser']:
            key = vid.get('key')
            if key:
                yt_link = f"https://www.youtube.com/embed/{key}"
                break

    return db_id, title, yt_link

def scan_shows():
    print("\n--- 📺 DİZİLER İÇİN FRAGMAN TARAMASI BAŞLATILIYOR ---")
    conn = sqlite3.connect('katalog.db', timeout=60.0)
    c = conn.cursor()
    c.execute('SELECT id, isim, cikis_tarihi FROM diziler WHERE (trailer_tr_url IS NULL OR trailer_tr_url = "")')
    rows = c.fetchall()
    total = len(rows)

    print(f"📦 Fragmanı eksik {total} adet dizi bulundu. 10 paralel kanaldan taranıyor...\n")
    
    updated_count = 0
    completed_idx = 0
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(process_single_show, r) for r in rows]
        for future in as_completed(futures):
            completed_idx += 1
            db_id, title, yt_link = future.result()
            pct = (completed_idx / total) * 100

            if yt_link:
                c.execute('''
                    UPDATE diziler 
                    SET trailer_tr_url = ?, trailer_original_url = ? 
                    WHERE id = ?
                ''', (yt_link, yt_link, db_id))
                updated_count += 1
                print(f"[{completed_idx}/{total}] (%{pct:.1f}) 📺 {title[:30]:<30} -> Fragman Eklendi ✅")
            else:
                print(f"[{completed_idx}/{total}] (%{pct:.1f}) 📺 {title[:30]:<30} -> Fragman Yok ❌")

            if completed_idx % 20 == 0:
                conn.commit()

    conn.commit()
    conn.close()
    print(f"\n✅ {updated_count} dizi için YouTube fragman bağlantısı başarıyla eklendi!")

if __name__ == '__main__':
    print("========================================================================")
    print("🚀 PARALEL DİZİ VE FİLM FRAGMAN TARAMA BOTU BAŞLATILIYOR...")
    print("========================================================================\n")
    scan_movies()
    scan_shows()

    print("\n--- 💾 data_store.js YENİDEN AKTARILIYOR ---")
    try:
        subprocess.run([sys.executable, 'export_data_store.py'], check=True)
        print("✅ data_store.js tüm fragmanlarla güncellendi!")
    except Exception as e:
        print(f"⚠️ export_data_store.py uyarısı: {e}")
