# -*- coding: utf-8 -*-
"""
==============================================================================
🚀 ULTRA HIZLI FRAGMAN BOTU (MULTITHREADED - 50X DAHA HIZLI)
==============================================================================
25 Paralel İş Parçacığı (Threads) kullanarak TMDB API üzerinden fragmanları
saniyeler içinde tarar ve veritabanına doğrudan işler!

Çalıştırma Komutu:
    python tamamlayici_fragman_botu.py
==============================================================================
"""

import os
import sys
import sqlite3
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"

DB_MOVIES = "katalog.db"
DB_SHOWS = "katalog.db"

def is_valid_url(url):
    if not url: return False
    u = str(url).lower()
    return "youtube.com" in u or "youtu.be" in u

def process_single_movie(movie_tuple):
    db_id, tmdb_id, name, cur_tr = movie_tuple
    if not tmdb_id and not name: return None

    # Try by TMDB ID
    if tmdb_id:
        try:
            url = f"{BASE_URL}/movie/{tmdb_id}/videos?api_key={API_KEY}&language=tr-TR"
            r = requests.get(url, timeout=5).json()
            for v in r.get("results", []):
                if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                    return (db_id, name, f"https://www.youtube.com/embed/{v.get('key')}")

            url_en = f"{BASE_URL}/movie/{tmdb_id}/videos?api_key={API_KEY}&language=en-US"
            r_en = requests.get(url_en, timeout=5).json()
            for v in r_en.get("results", []):
                if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                    return (db_id, name, f"https://www.youtube.com/embed/{v.get('key')}")
        except Exception:
            pass

    # Search Fallback
    try:
        url_s = f"{BASE_URL}/search/movie?api_key={API_KEY}&query={requests.utils.quote(str(name))}&language=tr-TR"
        res = requests.get(url_s, timeout=5).json().get("results", [])
        if res:
            m_id = res[0].get("id")
            url_v = f"{BASE_URL}/movie/{m_id}/videos?api_key={API_KEY}&language=en-US"
            r_v = requests.get(url_v, timeout=5).json()
            for v in r_v.get("results", []):
                if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                    return (db_id, name, f"https://www.youtube.com/embed/{v.get('key')}")
    except Exception:
        pass

    return None

def process_single_show(show_tuple):
    db_id, name, cur_tr = show_tuple
    if not name: return None

    try:
        # Dizilerde PK = TMDB id — isim araması Mother/Father, Avatar karışmasına yol açıyordu
        tv_id = db_id
        url_v = f"{BASE_URL}/tv/{tv_id}/videos?api_key={API_KEY}&language=tr-TR"
        r_v = requests.get(url_v, timeout=5).json()
        for v in r_v.get("results", []):
            if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                return (db_id, name, f"https://www.youtube.com/embed/{v.get('key')}")

        url_ven = f"{BASE_URL}/tv/{tv_id}/videos?api_key={API_KEY}&language=en-US"
        r_ven = requests.get(url_ven, timeout=5).json()
        for v in r_ven.get("results", []):
            if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                return (db_id, name, f"https://www.youtube.com/embed/{v.get('key')}")
    except Exception:
        pass

    return None

def run_fix():
    print("=" * 75)
    print("🚀 ULTRA HIZLI FRAGMAN BOTU (25 PARALEL THREAD) BAŞLATILIYOR...")
    print("=" * 75)

    start_t = time.time()

    # 1. MOVIES
    conn_m = sqlite3.connect(DB_MOVIES)
    c_m = conn_m.cursor()
    c_m.execute("SELECT id, tmdb_id, isim, fragman_url FROM filmler")
    movies = c_m.fetchall()

    missing_m = [m for m in movies if not is_valid_url(m[3])]
    total_m = len(missing_m)
    print(f"🎬 Fragmanı Eksik Film Sayısı: {total_m} / {len(movies)}")

    m_fixed = 0
    if total_m > 0:
        with ThreadPoolExecutor(max_workers=25) as executor:
            future_to_movie = {executor.submit(process_single_movie, m): m for m in missing_m}
            for future in as_completed(future_to_movie):
                res = future.result()
                if res:
                    db_id, name, t_url = res
                    c_m.execute("""
                        UPDATE filmler 
                        SET fragman_url = ?, trailer_dub_url = ?, trailer_sub_url = ?
                        WHERE id = ?
                    """, (t_url, t_url, t_url, db_id))
                    conn_m.commit()
                    m_fixed += 1
                    pct = round((m_fixed / total_m) * 100, 1)
                    print(f"  🎬 [{m_fixed}/{total_m}] (%{pct}) {name} -> Fragman Bulundu ✅")

    conn_m.close()
    print(f"✅ Filmler Bitti: {m_fixed} adet filme yeni fragman eklendi!")

    # 2. SHOWS
    conn_s = sqlite3.connect(DB_SHOWS)
    c_s = conn_s.cursor()
    c_s.execute("SELECT id, isim, trailer_tr_url FROM diziler")
    shows = c_s.fetchall()

    missing_s = [s for s in shows if not is_valid_url(s[2])]
    total_s = len(missing_s)
    print(f"\n📺 Fragmanı Eksik Dizi Sayısı: {total_s} / {len(shows)}")

    s_fixed = 0
    if total_s > 0:
        with ThreadPoolExecutor(max_workers=25) as executor:
            future_to_show = {executor.submit(process_single_show, s): s for s in missing_s}
            for future in as_completed(future_to_show):
                res = future.result()
                if res:
                    db_id, name, t_url = res
                    c_s.execute("""
                        UPDATE diziler 
                        SET trailer_tr_url = ?, trailer_original_url = ?
                        WHERE id = ?
                    """, (t_url, t_url, db_id))
                    conn_s.commit()
                    s_fixed += 1
                    pct = round((s_fixed / total_s) * 100, 1)
                    print(f"  📺 [{s_fixed}/{total_s}] (%{pct}) {name} -> Fragman Bulundu ✅")

    conn_s.close()
    print(f"✅ Diziler Bitti: {s_fixed} adet diziye yeni fragman eklendi!")

    elapsed = round(time.time() - start_t, 1)
    print("\n" + "=" * 75)
    print(f"🎉 ULTRA HIZLI FRAGMAN TARAMASI BİTTİ ({elapsed} sn)!")
    print("📌 ŞİMDİ SİTEYE AKTARMAK İÇİN TERMINALDE ŞU KOMUTU ÇALIŞTIRIN:")
    print("👉 python export_data_store.py")
    print("=" * 75)

if __name__ == "__main__":
    run_fix()
