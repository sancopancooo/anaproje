# -*- coding: utf-8 -*-
"""
==============================================================================
🚀 DİZİMIBUL / FİLMİMİBUL — DEVASA KATALOG TARAYICI BOTU (VS CODE İÇİN)
==============================================================================
Netflix, Disney+, Amazon Prime Video, Apple TV+ ve HBO Max platformlarındaki
ON BİNLERCE DİZİ VE FİLMİ TMDB API üzerinden canlı yüzde, ilerleme çubuğu ve
detaylı terminal logları ile çeker!

Çalıştırma Komutu (VS Code Terminalinde):
    python dev_katalog_tarayici.py
    python dev_katalog_tarayici.py --pages 30
==============================================================================
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"
REGION = "TR"
LANGUAGE = "tr-TR"

DB_MOVIES = "katalog.db"
DB_SHOWS = "katalog.db"

PROVIDERS = {
    8: "Netflix",
    337: "Disney+",
    119: "Amazon Prime Video",
    350: "Apple TV+",
    1899: "HBO Max"
}

def get_existing_ids():
    conn_m = sqlite3.connect(DB_MOVIES)
    c_m = conn_m.cursor()
    c_m.execute("SELECT tmdb_id FROM filmler WHERE tmdb_id IS NOT NULL")
    existing_m_tmdb = set(r[0] for r in c_m.fetchall() if r[0])
    c_m.execute("SELECT id FROM filmler")
    existing_m_id = set(r[0] for r in c_m.fetchall() if r[0])
    conn_m.close()

    conn_s = sqlite3.connect(DB_SHOWS)
    c_s = conn_s.cursor()
    c_s.execute("SELECT id FROM diziler")
    existing_s_id = set(r[0] for r in c_s.fetchall() if r[0])
    c_s.execute("SELECT isim FROM diziler")
    existing_s_names = set((r[0] or "").lower().strip() for r in c_s.fetchall() if r[0])
    conn_s.close()

    return existing_m_tmdb, existing_m_id, existing_s_id, existing_s_names

def generate_custom_why_watch(title, genres_str, summary, rating):
    g_low = (genres_str or "").lower()
    r_val = float(rating or 7.5)

    m1 = f"{title}, özgün kurgusal yapısı ve sürükleyici atmosferiyle öne çıkan bir yapım."
    if "bilim" in g_low or "fantastik" in g_low:
        m1 = f"{title}, hayal gücünü zorlayan evren tasarımı ve zihin bükücü kurgusuyla dikkat çekiyor."
    elif "aksiyon" in g_low or "macera" in g_low:
        m1 = f"{title}, soluksuz temposu ve yüksek adrenalinli aksiyon sahneleriyle izleyiciyi büyülüyor."
    elif "suç" in g_low or "gerilim" in g_low or "gizem" in g_low:
        m1 = f"{title}, adım adım tırmanan psikolojik gerilimi ve gizemli olay zinciriyle ekran başına kilitliyor."
    elif "komedi" in g_low:
        m1 = f"{title}, kahkaha dolu durum komedileri ve neşeli temposuyla keyifli bir seyir sunuyor."
    elif "dram" in g_low:
        m1 = f"{title}, insani duyguların derinliklerini ve karakter ilişkilerini etkileyici bir dille anlatıyor."

    m2 = "Güçlü karakter gelişimi, dengeli oyuncu performansları ve inandırıcı sahne mizansenleri."
    if r_val >= 8.0:
        m2 = "Başrol oyuncularının usta işi performansları ve yüksek izleyici beğenisi kazanan sahne kimyası."

    m3 = "Sinematik dokusu, sahnelerle uyumlu müzik kullanımı ve izleyicide bıraktığı kalıcı etki."
    return [m1, m2, m3]

def fetch_movie_details(tmdb_id, provider_name):
    try:
        url = f"{BASE_URL}/movie/{tmdb_id}?api_key={API_KEY}&language={LANGUAGE}&append_to_response=videos,credits"
        r = requests.get(url, timeout=8)
        if r.status_code != 200: return None
        d = r.json()

        title = d.get("title") or d.get("original_title")
        if not title: return None

        poster_path = d.get("poster_path")
        backdrop_path = d.get("backdrop_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500"
        backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1280"

        genres = [g.get("name") for g in d.get("genres", []) if g.get("name")]
        genres_str = ", ".join(genres) if genres else "Dram, Sinema"

        summary = d.get("overview") or f"{title} filminin sürükleyici hikayesi izleyicilerle buluşuyor."
        runtime = d.get("runtime") or 110
        vote_avg = round(d.get("vote_average", 7.5), 1)
        vote_cnt = d.get("vote_count", 500)
        release_date = d.get("release_date") or "2023-01-01"
        slogan = d.get("tagline") or ""
        budget = d.get("budget") or 0
        revenue = d.get("revenue") or 0

        credits = d.get("credits", {})
        directors = [c.get("name") for c in credits.get("crew", []) if c.get("job") == "Director"]
        director_str = ", ".join(directors[:2]) if directors else "Bilinmiyor"
        cast_names = [c.get("name") for c in credits.get("cast", [])[:4]]
        cast_str = ", ".join(cast_names) if cast_names else "Bilinmiyor"

        videos = d.get("videos", {}).get("results", [])
        trailer_url = None
        for v in videos:
            if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                trailer_url = f"https://www.youtube.com/embed/{v.get('key')}"
                break
        if not trailer_url:
            trailer_url = "https://www.youtube.com/embed/vVJeYMRam0o"

        why_watch = generate_custom_why_watch(title, genres_str, summary, vote_avg)

        return {
            "tmdb_id": tmdb_id,
            "isim": title,
            "orijinal_isim": d.get("original_title") or title,
            "vizyon_tarihi": release_date,
            "sure": f"{runtime} dk",
            "turler": genres_str,
            "ozet": summary,
            "poster_url": poster_url,
            "fragman_url": trailer_url,
            "platformlar": provider_name,
            "puan": vote_avg,
            "oy_sayisi": vote_cnt,
            "trailer_dub_url": trailer_url,
            "trailer_sub_url": trailer_url,
            "neden_izlemeli": json.dumps(why_watch, ensure_ascii=False),
            "backdrop_url": backdrop_url,
            "slogan": slogan,
            "yonetmen": director_str,
            "oyuncular": cast_str,
            "butce": budget,
            "hasilat": revenue
        }
    except Exception:
        return None

def fetch_tv_details(tmdb_id, provider_name):
    try:
        url = f"{BASE_URL}/tv/{tmdb_id}?api_key={API_KEY}&language={LANGUAGE}&append_to_response=videos,credits"
        r = requests.get(url, timeout=8)
        if r.status_code != 200: return None
        d = r.json()

        title = d.get("name") or d.get("original_name")
        if not title: return None

        poster_path = d.get("poster_path")
        backdrop_path = d.get("backdrop_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500"
        backdrop_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}" if backdrop_path else "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1280"

        genres = [g.get("name") for g in d.get("genres", []) if g.get("name")]
        genres_str = ", ".join(genres) if genres else "Dram, Dizi"

        summary = d.get("overview") or f"{title} dizisinin heyecan dolu tüm sezonları izleyicilerle buluşuyor."
        num_seasons = d.get("number_of_seasons") or 1
        num_episodes = d.get("number_of_episodes") or 10
        vote_avg = round(d.get("vote_average", 8.0), 1)
        vote_cnt = d.get("vote_count", 600)
        first_air_date = d.get("first_air_date") or "2022-01-01"
        status = "Bitmiş / Final Yapmış" if d.get("status") == "Ended" else "Devam Ediyor"

        cast = d.get("credits", {}).get("cast", [])
        cast_names = [c.get("name") for c in cast[:4]]
        cast_str = ", ".join(cast_names) if cast_names else "Bilinmiyor"

        videos = d.get("videos", {}).get("results", [])
        trailer_url = None
        for v in videos:
            if v.get("site") == "YouTube" and v.get("type") in ["Trailer", "Teaser"]:
                trailer_url = f"https://www.youtube.com/embed/{v.get('key')}"
                break
        if not trailer_url:
            trailer_url = "https://www.youtube.com/embed/vVJeYMRam0o"

        why_watch = generate_custom_why_watch(title, genres_str, summary, vote_avg)

        return {
            "id": int(tmdb_id),
            "isim": title,
            "ozet": summary,
            "puan_ortalamasi": vote_avg,
            "oy_sayisi": vote_cnt,
            "sezon_sayisi": num_seasons,
            "toplam_bolum_sayisi": num_episodes,
            "gercek_bolum_sureleri": 45,
            "cikis_tarihi": str(first_air_date)[:4],
            "tur": genres_str,
            "afis_url": poster_url,
            "durum": status,
            "platformlar": provider_name,
            "backdrop_url": backdrop_url,
            "oyuncular_gercek": cast_str,
            "neden_izlemeli": json.dumps(why_watch, ensure_ascii=False),
            "trailer_tr_url": trailer_url,
            "trailer_original_url": trailer_url
        }
    except Exception:
        return None

def start_dev_scan(start_page=1, end_page=30):
    print("=" * 80)
    print(f"🚀 DİZİMIBUL / FİLMİMİBUL — DEVASA KATALOG TARAYICI BOTU (Sayfa {start_page} -> {end_page})")
    print("=" * 80)

    existing_m_tmdb, existing_m_id, existing_s_id, existing_s_names = get_existing_ids()

    print(f"📊 Mevcut Film Kaydı : {len(existing_m_id):,}")
    print(f"📊 Mevcut Dizi Kaydı : {len(existing_s_id):,}")
    print("=" * 80)

    total_added_movies = 0
    total_added_shows = 0

    conn_m = sqlite3.connect(DB_MOVIES, timeout=60.0)
    c_m = conn_m.cursor()

    conn_s = sqlite3.connect(DB_SHOWS, timeout=60.0)
    c_s = conn_s.cursor()

    start_time = time.time()
    total_pages_count = (end_page - start_page + 1)

    for provider_id, provider_name in PROVIDERS.items():
        print(f"\n🌐 [{provider_name}] Kataloğu Taranıyor (Sayfa {start_page} -> {end_page})...")
        
        # 🎬 1. MOVIE DISCOVERY
        for p in range(start_page, end_page + 1):
            try:
                url = f"{BASE_URL}/discover/movie?api_key={API_KEY}&with_watch_providers={provider_id}&watch_region={REGION}&language={LANGUAGE}&page={p}&sort_by=popularity.desc"
                res = requests.get(url, timeout=10).json()
                results = res.get("results", [])
                
                for item in results:
                    t_id = item.get("id")
                    if t_id and t_id not in existing_m_tmdb:
                        existing_m_tmdb.add(t_id)
                        m = fetch_movie_details(t_id, provider_name)
                        if m:
                            c_m.execute("""
                                INSERT OR IGNORE INTO filmler 
                                (tmdb_id, isim, orijinal_isim, vizyon_tarihi, sure, turler, ozet, poster_url, fragman_url, platformlar, puan, oy_sayisi, trailer_dub_url, trailer_sub_url, neden_izlemeli, backdrop_url, slogan, yonetmen, oyuncular, butce, hasilat)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                m["tmdb_id"], m["isim"], m["orijinal_isim"], m["vizyon_tarihi"], m["sure"], m["turler"], m["ozet"],
                                m["poster_url"], m["fragman_url"], m["platformlar"], m["puan"], m["oy_sayisi"], m["trailer_dub_url"],
                                m["trailer_sub_url"], m["neden_izlemeli"], m["backdrop_url"], m["slogan"], m["yonetmen"], m["oyuncular"],
                                m["butce"], m["hasilat"]
                            ))
                            conn_m.commit()
                            total_added_movies += 1
                            curr_idx = (p - start_page + 1)
                            pct = round((curr_idx / total_pages_count) * 100, 1)
                            print(f"  🎬 [{total_added_movies}] (%{pct}) {m['isim']} ({provider_name}) -> Eklendi ✅")
                time.sleep(0.15)
            except Exception as e:
                pass

        # 📺 2. TV SHOW DISCOVERY
        for p in range(start_page, end_page + 1):
            try:
                url = f"{BASE_URL}/discover/tv?api_key={API_KEY}&with_watch_providers={provider_id}&watch_region={REGION}&language={LANGUAGE}&page={p}&sort_by=popularity.desc"
                res = requests.get(url, timeout=10).json()
                results = res.get("results", [])
                
                for item in results:
                    t_id = item.get("id")
                    t_name = (item.get("name") or "").lower().strip()
                    if t_id and t_id not in existing_s_id and t_name not in existing_s_names:
                        existing_s_id.add(t_id)
                        existing_s_names.add(t_name)
                        s = fetch_tv_details(t_id, provider_name)
                        if s:
                            c_s.execute("""
                                INSERT OR IGNORE INTO diziler
                                (id, isim, ozet, puan_ortalamasi, oy_sayisi, sezon_sayisi, toplam_bolum_sayisi, gercek_bolum_sureleri, cikis_tarihi, tur, afis_url, durum, platformlar, backdrop_url, oyuncular_gercek, neden_izlemeli, trailer_tr_url, trailer_original_url)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                s["id"], s["isim"], s["ozet"], s["puan_ortalamasi"], s["oy_sayisi"], s["sezon_sayisi"], s["toplam_bolum_sayisi"],
                                s["gercek_bolum_sureleri"], s["cikis_tarihi"], s["tur"], s["afis_url"], s["durum"], s["platformlar"],
                                s["backdrop_url"], s["oyuncular_gercek"], s["neden_izlemeli"], s["trailer_tr_url"], s["trailer_original_url"]
                            ))
                            conn_s.commit()
                            total_added_shows += 1
                            curr_idx = (p - start_page + 1)
                            pct = round((curr_idx / total_pages_count) * 100, 1)
                            print(f"  📺 [{total_added_shows}] (%{pct}) {s['isim']} ({provider_name}) -> Eklendi ✅")
                time.sleep(0.15)
            except Exception as e:
                pass

    conn_m.close()
    conn_s.close()

    elapsed = round(time.time() - start_time, 1)
    print("\n" + "=" * 80)
    print(f"🎉 DEVASA TARAMA BİTTİ ({elapsed} sn)!")
    print(f"✨ Eklenen Yeni Film Sayısı : {total_added_movies:,}")
    print(f"✨ Eklenen Yeni Dizi Sayısı : {total_added_shows:,}")
    print("=" * 80)
    print("📌 ŞİMDİ SİTEYE AKTARMAK İÇİN TERMINALDE ŞU KOMUTU ÇALIŞTIRIN:")
    print("👉 python export_data_store.py")
    print("=" * 80)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Devasa Katalog Tarayıcı Botu")
    parser.add_argument("--start-page", type=int, default=1, help="Taramaya kaçıncı sayfadan başlansın (Varsayılan: 1)")
    parser.add_argument("--end-page", type=int, default=30, help="Taramaya kaçıncı sayfada bitsin (Varsayılan: 30)")
    args = parser.parse_args()
    start_dev_scan(start_page=args.start_page, end_page=args.end_page)
