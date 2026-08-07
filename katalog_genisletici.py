# -*- coding: utf-8 -*-
"""
==============================================================================
🚀 DİZİMİBUL / FİLMİMİBUL — DEVASA KATALOG GENİŞLETİCİ BOTU (v1.0)
==============================================================================
Netflix, Disney+, Amazon Prime Video ve HBO Max üzerindeki binlerce güncel
dizi ve filmi TMDB API üzerinden çeker; Afiş, Backdrop, Fragman, Bölüm/Süre
ve Özgün "Neden İzlemelisin?" maddeleriyle veritabanına mühürler!

Çalıştırma:
    python katalog_genisletici.py
    python katalog_genisletici.py --pages 10
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

GENRE_MAP = {
    28: "Aksiyon", 12: "Macera", 16: "Animasyon", 35: "Komedi", 80: "Suç",
    99: "Belgesel", 18: "Dram", 10751: "Aile", 14: "Fantastik", 36: "Tarih",
    27: "Korku", 10402: "Müzik", 9648: "Gizem", 10749: "Romantik", 878: "Bilim-Kurgu",
    10770: "TV Filmi", 53: "Gerilim", 10752: "Savaş", 37: "Vahşi Batı",
    10759: "Aksiyon & Macera", 10762: "Çocuk", 10763: "Haber", 10764: "Reality",
    10765: "Bilim-Kurgu & Fantastik", 10766: "Pembe Dizi", 10767: "Talk Show", 10768: "Savaş & Politika"
}

def get_existing_movie_ids():
    conn = sqlite3.connect(DB_MOVIES)
    c = conn.cursor()
    c.execute("SELECT tmdb_id FROM filmler WHERE tmdb_id IS NOT NULL")
    tmdb_ids = set(r[0] for r in c.fetchall() if r[0])
    c.execute("SELECT id FROM filmler")
    db_ids = set(r[0] for r in c.fetchall() if r[0])
    conn.close()
    return tmdb_ids, db_ids

def get_existing_show_names():
    conn = sqlite3.connect(DB_SHOWS)
    c = conn.cursor()
    c.execute("SELECT isim FROM diziler")
    names = set((r[0] or "").lower().strip() for r in c.fetchall() if r[0])
    conn.close()
    return names

def generate_custom_why_watch(title, genres_str, summary, rating):
    g_low = genres_str.lower()
    sum_text = (summary or "").strip()
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
        r = requests.get(url, timeout=10)
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

        summary = d.get("overview") or f"{title} filminin sürükleyici hikayesi sinemaseverlerle buluşuyor."
        runtime = d.get("runtime") or 110
        vote_avg = round(d.get("vote_average", 7.5), 1)
        vote_cnt = d.get("vote_count", 500)
        release_date = d.get("release_date") or "2023-01-01"
        slogan = d.get("tagline") or ""
        budget = d.get("budget") or 0
        revenue = d.get("revenue") or 0

        # Directors & Cast
        credits = d.get("credits", {})
        crew = credits.get("crew", [])
        cast = credits.get("cast", [])
        directors = [c.get("name") for c in crew if c.get("job") == "Director"]
        director_str = ", ".join(directors[:2]) if directors else "Bilinmiyor"
        cast_names = [c.get("name") for c in cast[:4]]
        cast_str = ", ".join(cast_names) if cast_names else "Bilinmiyor"

        # Trailer
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
    except Exception as e:
        return None

def fetch_tv_details(tmdb_id, provider_name):
    try:
        url = f"{BASE_URL}/tv/{tmdb_id}?api_key={API_KEY}&language={LANGUAGE}&append_to_response=videos,credits"
        r = requests.get(url, timeout=10)
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
    except Exception as e:
        return None

def run_importer(max_pages=5):
    print("=" * 75)
    print("🚀 DİZİMIBUL / FİLMİMİBUL KATALOG GENİŞLETİCİ BOTU BAŞLATILIYOR...")
    print("=" * 75)

    existing_tmdb_movies, existing_db_movies = get_existing_movie_ids()
    existing_show_names = get_existing_show_names()

    print(f"📊 Mevcut Film Kaydı : {len(existing_db_movies):,}")
    print(f"📊 Mevcut Dizi Kaydı : {len(existing_show_names):,}")
    print("=" * 75)

    new_movies = []
    new_shows = []

    for provider_id, provider_name in PROVIDERS.items():
        print(f"\n🌐 [{provider_name}] kataloğu taranıyor (Maksimum {max_pages} sayfa)...")
        
        # 1. DISCOVER MOVIES
        for p in range(1, max_pages + 1):
            try:
                url = f"{BASE_URL}/discover/movie?api_key={API_KEY}&with_watch_providers={provider_id}&watch_region={REGION}&language={LANGUAGE}&page={p}&sort_by=popularity.desc"
                res = requests.get(url, timeout=10).json()
                results = res.get("results", [])
                
                for item in results:
                    t_id = item.get("id")
                    if t_id and t_id not in existing_tmdb_movies:
                        existing_tmdb_movies.add(t_id)
                        movie_data = fetch_movie_details(t_id, provider_name)
                        if movie_data:
                            new_movies.append(movie_data)
                            print(f"  🎬 [{len(new_movies)}] Film Eklendi: {movie_data['isim']} ({provider_name}) ✅")
                time.sleep(0.2)
            except Exception:
                pass

        # 2. DISCOVER SHOWS
        for p in range(1, max_pages + 1):
            try:
                url = f"{BASE_URL}/discover/tv?api_key={API_KEY}&with_watch_providers={provider_id}&watch_region={REGION}&language={LANGUAGE}&page={p}&sort_by=popularity.desc"
                res = requests.get(url, timeout=10).json()
                results = res.get("results", [])
                
                for item in results:
                    t_id = item.get("id")
                    t_name = (item.get("name") or "").lower().strip()
                    if t_name and t_name not in existing_show_names:
                        existing_show_names.add(t_name)
                        tv_data = fetch_tv_details(t_id, provider_name)
                        if tv_data:
                            new_shows.append(tv_data)
                            print(f"  📺 [{len(new_shows)}] Dizi Eklendi: {tv_data['isim']} ({provider_name}) ✅")
                time.sleep(0.2)
            except Exception:
                pass

    # SAVE TO MOVIES DATABASE
    if new_movies:
        conn = sqlite3.connect(DB_MOVIES)
        c = conn.cursor()
        for m in new_movies:
            c.execute("""
                INSERT OR IGNORE INTO filmler 
                (tmdb_id, isim, orijinal_isim, vizyon_tarihi, sure, turler, ozet, poster_url, fragman_url, platformlar, puan, oy_sayisi, trailer_dub_url, trailer_sub_url, neden_izlemeli, backdrop_url, slogan, yonetmen, oyuncular, butce, hasilat)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                m["tmdb_id"], m["isim"], m["orijinal_isim"], m["vizyon_tarihi"], m["sure"], m["turler"], m["ozet"],
                m["poster_url"], m["fragman_url"], m["platformlar"], m["puan"], m["oy_sayisi"], m["trailer_dub_url"],
                m["trailer_sub_url"], m["neden_izlemeli"], m["backdrop_url"], m["slogan"], m["yonetmen"], m["oyuncular"],
                m["butce"], m["hasilat"]
            ))
        conn.commit()
        conn.close()

    # SAVE TO SHOWS DATABASE
    if new_shows:
        conn = sqlite3.connect(DB_SHOWS)
        c = conn.cursor()
        for s in new_shows:
            c.execute("""
                INSERT OR IGNORE INTO diziler
                (id, isim, ozet, puan_ortalamasi, oy_sayisi, sezon_sayisi, toplam_bolum_sayisi, gercek_bolum_sureleri, cikis_tarihi, tur, afis_url, durum, platformlar, backdrop_url, oyuncular_gercek, neden_izlemeli, trailer_tr_url, trailer_original_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                s["id"], s["isim"], s["ozet"], s["puan_ortalamasi"], s["oy_sayisi"], s["sezon_sayisi"], s["toplam_bolum_sayisi"],
                s["gercek_bolum_sureleri"], s["cikis_tarihi"], s["tur"], s["afis_url"], s["durum"], s["platformlar"],
                s["backdrop_url"], s["oyuncular_gercek"], s["neden_izlemeli"], s["trailer_tr_url"], s["trailer_original_url"]
            ))
        conn.commit()
        conn.close()

    print("\n" + "=" * 75)
    print(f"🎉 KATALOG GENİŞLETME TAMAMLANDI!")
    print(f"✨ Toplam Eklenen Yeni Film : {len(new_movies):,}")
    print(f"✨ Toplam Eklenen Yeni Dizi : {len(new_shows):,}")
    print("=" * 75)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Katalog Genişletici Botu")
    parser.add_argument("--pages", type=int, default=3, help="Platform başına kaç sayfa taransın (Varsayılan: 3)")
    args = parser.parse_args()
    run_importer(max_pages=args.pages)
