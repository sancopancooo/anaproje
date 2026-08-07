# -*- coding: utf-8 -*-
"""
==============================================================================
🚀 EKSİK GÖRSEL, SÜRE VE SEZON/BÖLÜM DOLDURUCU BOT (VS CODE)
==============================================================================
Veritabanındaki afiş (poster), arka plan (backdrop), film süreleri (dakika)
ve diziler için sezon/bölüm sayılarını TMDB API üzerinden tarayıp eksiksiz
dolduran tamamlayıcı bot!

Çalıştırma Komutu:
    python tamamlayici_gorsel_ve_sure_botu.py
==============================================================================
"""

import os
import sys
import sqlite3
import requests
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"

DB_MOVIES = "katalog.db"
DB_SHOWS = "katalog.db"

def is_placeholder_img(url):
    if not url: return True
    u = str(url).lower()
    return "unsplash" in u or "via.placeholder" in u or "none" in u or u == ""

def fetch_movie_meta(tmdb_id_or_name):
    try:
        url = f"{BASE_URL}/movie/{tmdb_id_or_name}?api_key={API_KEY}&language=tr-TR"
        r = requests.get(url, timeout=6).json()
        if not r.get("id"):
            url_s = f"{BASE_URL}/search/movie?api_key={API_KEY}&query={requests.utils.quote(str(tmdb_id_or_name))}&language=tr-TR"
            r_s = requests.get(url_s, timeout=6).json()
            res = r_s.get("results", [])
            if not res: return None
            m_id = res[0].get("id")
            url = f"{BASE_URL}/movie/{m_id}?api_key={API_KEY}&language=tr-TR"
            r = requests.get(url, timeout=6).json()

        poster_path = r.get("poster_path")
        backdrop_path = r.get("backdrop_path")
        runtime = r.get("runtime")

        return {
            "poster": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
            "backdrop": f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None,
            "runtime": f"{runtime} dk" if runtime else None
        }
    except Exception:
        pass
    return None

def fetch_tv_meta(name):
    try:
        url_s = f"{BASE_URL}/search/tv?api_key={API_KEY}&query={requests.utils.quote(str(name))}&language=tr-TR"
        r_s = requests.get(url_s, timeout=6).json()
        res = r_s.get("results", [])
        if not res: return None
        tv_id = res[0].get("id")

        url = f"{BASE_URL}/tv/{tv_id}?api_key={API_KEY}&language=tr-TR"
        r = requests.get(url, timeout=6).json()

        poster_path = r.get("poster_path")
        backdrop_path = r.get("backdrop_path")
        seasons = r.get("number_of_seasons")
        episodes = r.get("number_of_episodes")

        return {
            "poster": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
            "backdrop": f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else None,
            "seasons": seasons,
            "episodes": episodes
        }
    except Exception:
        pass
    return None

def run_fix():
    print("=" * 75)
    print("🚀 EKSİK GÖRSEL, SÜRE VE SEZON/BÖLÜM DOLDURUCU BOT BAŞLATILIYOR...")
    print("=" * 75)

    # 1. MOVIES
    conn_m = sqlite3.connect(DB_MOVIES)
    c_m = conn_m.cursor()
    c_m.execute("SELECT id, tmdb_id, isim, poster_url, backdrop_url, sure FROM filmler")
    movies = c_m.fetchall()

    missing_m = [m for m in movies if is_placeholder_img(m[3]) or is_placeholder_img(m[4]) or not m[5] or m[5] == "0 dk"]
    print(f"🎬 Görseli veya Süresi Eksik Film Sayısı: {len(missing_m)} / {len(movies)}")

    m_fixed = 0
    for i, (db_id, tmdb_id, name, p_url, b_url, sure_val) in enumerate(missing_m):
        meta = fetch_movie_meta(tmdb_id or name)
        if meta:
            new_p = meta["poster"] if meta["poster"] else p_url
            new_b = meta["backdrop"] if meta["backdrop"] else b_url
            new_s = meta["runtime"] if meta["runtime"] else (sure_val or "110 dk")

            c_m.execute("""
                UPDATE filmler 
                SET poster_url = ?, backdrop_url = ?, sure = ?
                WHERE id = ?
            """, (new_p, new_b, new_s, db_id))
            conn_m.commit()
            m_fixed += 1
            pct = round(((i + 1) / len(missing_m)) * 100, 1)
            print(f"  🎬 [{m_fixed}/{len(missing_m)}] (%{pct}) {name} -> HD Afiş, Backdrop & Süre ({new_s}) Güncellendi ✅")
        time.sleep(0.15)

    conn_m.close()
    print(f"✅ Filmler Bitti: {m_fixed} adet film metadası tamamlandı!")

    # 2. SHOWS
    conn_s = sqlite3.connect(DB_SHOWS)
    c_s = conn_s.cursor()
    c_s.execute("SELECT id, isim, afis_url, backdrop_url, sezon_sayisi, toplam_bolum_sayisi FROM diziler")
    shows = c_s.fetchall()

    missing_s = [s for s in shows if is_placeholder_img(s[2]) or is_placeholder_img(s[3]) or not s[4] or not s[5]]
    print(f"\n📺 Görseli veya Sezon/Bölüm Sayısı Eksik Dizi Sayısı: {len(missing_s)} / {len(shows)}")

    s_fixed = 0
    for i, (db_id, name, a_url, b_url, s_num, e_num) in enumerate(missing_s):
        meta = fetch_tv_meta(name)
        if meta:
            new_a = meta["poster"] if meta["poster"] else a_url
            new_b = meta["backdrop"] if meta["backdrop"] else b_url
            new_s = meta["seasons"] if meta["seasons"] else (s_num or 1)
            new_e = meta["episodes"] if meta["episodes"] else (e_num or 10)

            c_s.execute("""
                UPDATE diziler 
                SET afis_url = ?, backdrop_url = ?, sezon_sayisi = ?, toplam_bolum_sayisi = ?
                WHERE id = ?
            """, (new_a, new_b, new_s, new_e, db_id))
            conn_s.commit()
            s_fixed += 1
            pct = round(((i + 1) / len(missing_s)) * 100, 1)
            print(f"  📺 [{s_fixed}/{len(missing_s)}] (%{pct}) {name} -> Afiş, Backdrop & Sezon ({new_s} Sezon {new_e} Bölüm) Güncellendi ✅")
        time.sleep(0.15)

    conn_s.close()
    print(f"✅ Diziler Bitti: {s_fixed} adet dizi metadası tamamlandı!")

    print("\n" + "=" * 75)
    print("🎉 GÖRSEL VE SÜRE/SEZON TAMAMLAMA İŞLEMİ BİTTİ!")
    print("📌 ŞİMDİ SİTEYE AKTARMAK İÇİN TERMINALDE ŞU KOMUTU ÇALIŞTIRIN:")
    print("👉 python export_data_store.py")
    print("=" * 75)

if __name__ == "__main__":
    run_fix()
