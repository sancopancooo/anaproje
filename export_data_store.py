# -*- coding: utf-8 -*-
"""
==========================================================================
🎬 DIZI & FILM VERİ DÖNÜŞTÜRÜCÜ (export_data_store.py)
==========================================================================
Açıklama: 'katalog.db' (diziler + filmler tek SQLite) veritabanından
tüm gerçek dizi ve film verilerini (fragmanlarıyla birlikte) 
data_store.js dosyasına aktarır.
==========================================================================
"""

import os
import json
import sqlite3
import re

try:
    from db_paths import series_db_path, movies_db_path
    DB_PATH = series_db_path()
    MOVIES_DB_PATH = movies_db_path()
except Exception:
    DB_PATH = "katalog.db"
    MOVIES_DB_PATH = "katalog.db"
MOVIES_JSON_PATH = "movies_dataset.json"
JS_OUTPUT_PATH = "data_store.js"

def clean_text(text):
    if not text or not isinstance(text, str):
        return ""
    text = str(text).replace('\\', '').replace('"', "'").replace('\r', '').replace('\n', ' ').strip()
    return text

def clean_url(url):
    if url and isinstance(url, str) and ("youtube.com" in url or "youtu.be" in url):
        return url.strip()
    return ""

def is_inappropriate_content(name, genres, keywords, summary=""):
    full_text = f"{name} {genres} {keywords} {summary}".lower()
    forbidden = ['erotik', 'erotizm', 'adult', '+18', 'porno', 'hentai', '女教師日記']
    return any(f in full_text for f in forbidden)

def get_real_series(limit=None):
    if not os.path.exists(DB_PATH):
        return []
    
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    if limit and limit > 0:
        cursor.execute("""
            SELECT * FROM diziler 
            WHERE afis_url IS NOT NULL AND afis_url != ''
            ORDER BY oy_sayisi DESC, puan_ortalamasi DESC 
            LIMIT ?
        """, (limit,))
    else:
        cursor.execute("""
            SELECT * FROM diziler 
            WHERE afis_url IS NOT NULL AND afis_url != ''
            ORDER BY oy_sayisi DESC, puan_ortalamasi DESC
        """)
    
    rows = cursor.fetchall()
    series_list = []
    
    for r in rows:
        d = dict(r)
        
        title_str = clean_text(d.get("isim")) or "İsimsiz Dizi"
        genre_raw = clean_text(d.get("tur")) or "Dram"
        kw_str = clean_text(d.get("anahtar_kelimeler")) or ""
        sum_str = clean_text(d.get("ozet")) or ""
        
        if is_inappropriate_content(title_str, genre_raw, kw_str, sum_str):
            continue
        
        duo_str = clean_text(d.get("efsanevi_ikili"))
        duo_name = ""
        duo_desc = ""
        if duo_str and "|" in duo_str:
            parts = duo_str.split("|")
            duo_name = parts[0].strip()
            duo_desc = parts[2].strip() if len(parts) > 2 else (parts[1].strip() if len(parts) > 1 else "")
        elif duo_str:
            duo_name = duo_str.strip()

        why_watch_raw = d.get("neden_izlemeli") or "[]"
        why_watch_list = []
        try:
            parsed = json.loads(why_watch_raw)
            if isinstance(parsed, list):
                why_watch_list = [clean_text(str(x)) for x in parsed]
        except Exception:
            if isinstance(why_watch_raw, str) and why_watch_raw.strip():
                why_watch_list = [clean_text(why_watch_raw)]

        cikis = str(d.get("cikis_tarihi") or "2020")
        year_val = 1990
        try:
            year_val = int(cikis[:4])
        except Exception:
            year_val = 1990

        if year_val < 1990:
            continue

        harita_raw = str(d.get("sezon_bolum_haritasi") or "10")
        season_episodes_map = []
        for x in harita_raw.split(","):
            x_str = x.strip()
            if x_str.isdigit() and int(x_str) > 0:
                season_episodes_map.append(int(x_str))
        if not season_episodes_map:
            season_episodes_map = [10]

        total_seasons = int(d.get("sezon_sayisi") or len(season_episodes_map))
        total_episodes = sum(season_episodes_map)
        ep_duration = int(d.get("gercek_bolum_sureleri") or 45)

        raw_puan = float(d.get('puan_ortalamasi') or 0)
        rating_num = round(raw_puan, 1) if raw_puan > 0 else 0.0
        votes_num = int(d.get('oy_sayisi') or 0)

        series_item = {
            "id": f"series_{d.get('id')}",
            "title": title_str,
            "rating": f"{rating_num:.1f}",
            "rating_num": rating_num,
            "seasons": f"{total_seasons} Sezon ({total_episodes} Bölüm)",
            "seasons_num": total_seasons,
            "season_episodes_map": season_episodes_map,
            "total_episodes": total_episodes,
            "ep_duration": ep_duration,
            "votes_num": votes_num,
            "runtime": f"{ep_duration} dk",
            "platform": clean_text(d.get("platformlar")) or "Diğer Platformlar",
            "status": clean_text(d.get("durum")) or "Final Yapmış",
            "genres": [clean_text(t) for t in (d.get("tur") or "Dram").split(",") if clean_text(t)],
            "summary": clean_text(d.get("ozet")) or "Özet bulunamadı.",
            "duo": duo_name,
            "duo_desc": duo_desc,
            "why_watch": [clean_text(w) for w in why_watch_list if clean_text(w)],
            "poster_url": d.get("afis_url"),
            "backdrop_url": d.get("backdrop_url") or "",
            "age_rating": clean_text(d.get("icerik_derecelendirme")) or "",
            "countries": json.loads(d.get("yapim_ulkeleri") or "[]") if isinstance(d.get("yapim_ulkeleri"), str) and d.get("yapim_ulkeleri").startswith("[") else [],
            "networks": json.loads(d.get("yayin_aglari") or "[]") if isinstance(d.get("yayin_aglari"), str) and d.get("yayin_aglari").startswith("[") else [],
            "companies": json.loads(d.get("yapim_sirketleri") or "[]") if isinstance(d.get("yapim_sirketleri"), str) and d.get("yapim_sirketleri").startswith("[") else [],
            "language": clean_text(d.get("orijinal_dil")) or "en",
            "trailer_dub_url": clean_url(d.get("trailer_tr_url")),
            "trailer_sub_url": clean_url(d.get("trailer_original_url")),
            "keywords": clean_text(d.get("anahtar_kelimeler")) or "",
            "year": year_val
        }
        series_list.append(series_item)
        
    conn.close()
    return series_list


def clean_movie_genres(raw_genres):
    clean = []
    if isinstance(raw_genres, list):
        for g in raw_genres:
            if not g: continue
            parts = re.split(r'\s*[\&,/\+]\s*', str(g))
            for p in parts:
                p_str = p.strip()
                if p_str == "Bilimkurgu": p_str = "Bilim-Kurgu"
                if p_str and p_str not in clean:
                    clean.append(p_str)
    elif isinstance(raw_genres, str):
        for p in re.split(r'\s*[\&,/\+]\s*', raw_genres):
            p_str = p.strip()
            if p_str == "Bilimkurgu": p_str = "Bilim-Kurgu"
            if p_str and p_str not in clean:
                clean.append(p_str)
    return clean or ["Aksiyon", "Dram"]

def get_movie_rating_and_votes(m):
    """JSON fallback: gerçek TMDB puan/oy varsa kullan, yoksa 0 (filtre eler)."""
    raw_rating = m.get('vote_average')
    raw_votes = m.get('vote_count')
    if raw_rating is None:
        raw_rating = m.get('puan') or m.get('rating') or 0
    if raw_votes is None:
        raw_votes = m.get('oy_sayisi') or m.get('votes') or 0
    try:
        rating_val = round(float(raw_rating or 0), 1)
    except (TypeError, ValueError):
        rating_val = 0.0
    try:
        votes_val = int(raw_votes or 0)
    except (TypeError, ValueError):
        votes_val = 0
    return rating_val, votes_val

def get_real_movies(limit=None):
    if os.path.exists(MOVIES_DB_PATH):
        try:
            conn = sqlite3.connect(MOVIES_DB_PATH, timeout=60.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT * FROM filmler WHERE poster_url IS NOT NULL AND poster_url != '' ORDER BY oy_sayisi DESC, puan DESC"
            if limit and limit > 0:
                query += " LIMIT ?"
                cursor.execute(query, (limit,))
            else:
                cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            if rows:
                movies_list = []
                for r in rows:
                    m = dict(r)
                    director = clean_text(m.get("yonetmen")) or "Bilinmiyor"
                    cast_str = clean_text(m.get("oyuncular")) or ""
                    duo_text = cast_str if cast_str else f"Yönetmen: {director}"

                    release = str(m.get("vizyon_tarihi") or "2020")
                    year_val = 2020
                    try:
                        year_val = int(release[:4])
                    except Exception:
                        year_val = 2020

                    m_title = clean_text(m.get("isim")) or clean_text(m.get("orijinal_isim")) or "İsimsiz Film"
                    clean_genres = clean_movie_genres(m.get("turler"))
                    kw_str = clean_text(m.get("anahtar_kelimeler")) or ""
                    sum_str = clean_text(m.get("ozet")) or ""

                    if is_inappropriate_content(m_title, " ".join(clean_genres), kw_str, sum_str):
                        continue

                    raw_sure = str(m.get('sure') or '120')
                    runtime_mins = 120
                    try:
                        m_match = re.search(r'\d+', raw_sure)
                        if m_match:
                            runtime_mins = int(m_match.group(0))
                    except Exception:
                        runtime_mins = 120
                    raw_puan = float(m.get('puan') or 0)
                    rating_num = round(raw_puan, 1) if raw_puan > 0 else 0.0
                    votes_num = int(m.get('oy_sayisi') or 0)
                    plat_str = clean_text(m.get("platformlar")) or "Sinema"
                    plat_list = [p.strip() for p in plat_str.split(",") if p.strip()] or ["Sinema"]

                    why_raw = m.get("neden_izlemeli") or ""
                    why_list = []
                    if why_raw:
                        try:
                            if isinstance(why_raw, list):
                                why_list = why_raw
                            elif isinstance(why_raw, str) and why_raw.strip().startswith("["):
                                why_list = json.loads(why_raw)
                            else:
                                why_list = [s.strip() + "." for s in re.split(r'[\.\!\?]\s+', str(why_raw)) if len(s.strip()) > 5]
                        except Exception:
                            why_list = [str(why_raw)]

                    if not isinstance(why_list, list) or len(why_list) == 0:
                        dir_lead = f"{director} yönetmenliğinde öne çıkan etkileyici sinematik yapım." if (director and director != "Bilinmiyor") else "Derinlikli kurgusu ve yüksek görsel kalitesiyle öne çıkan sinematik yapım."
                        why_list = [
                            dir_lead,
                            "Yüksek görsel kalite, sürükleyici atmosfer ve tempolu sinematik anlatım."
                        ]

                    movies_item = {
                        "id": f"movie_{m.get('id')}",
                        "title": clean_text(m.get("isim")) or clean_text(m.get("orijinal_isim")) or "İsimsiz Film",
                        "rating": f"{rating_num:.1f}",
                        "rating_num": rating_num,
                        "seasons": "Sinema Filmi",
                        "seasons_num": 1,
                        "season_episodes_map": [1],
                        "total_episodes": 1,
                        "ep_duration": runtime_mins,
                        "votes_num": votes_num,
                        "runtime": f"{runtime_mins} dk",
                        "platform": plat_str,
                        "platforms": plat_list,
                        "status": "Vizyon Filmi",
                        "genres": clean_genres,
                        "summary": clean_text(m.get("ozet")) or "Özet henüz eklenmedi.",
                        "duo": duo_text,
                        "duo_desc": f"Yönetmen: {director}",
                        "why_watch": why_list,
                        "poster_url": m.get("poster_url"),
                        "backdrop_url": m.get("backdrop_url") or "",
                        "slogan": clean_text(m.get("slogan")) or "",
                        "collection": clean_text(m.get("koleksiyon")) or "",
                        "budget": int(m.get("butce") or 0),
                        "revenue": int(m.get("hasilat") or 0),
                        "companies": json.loads(m.get("yapim_sirketleri") or "[]") if isinstance(m.get("yapim_sirketleri"), str) and m.get("yapim_sirketleri").startswith("[") else [],
                        "countries": json.loads(m.get("yapim_ulkeleri") or "[]") if isinstance(m.get("yapim_ulkeleri"), str) and m.get("yapim_ulkeleri").startswith("[") else [],
                        "language": clean_text(m.get("orijinal_dil")) or "en",
                        "trailer_url": clean_url(m.get("fragman_url")) or clean_url(m.get("trailer_dub_url")) or clean_url(m.get("trailer_sub_url")),
                        "trailer_type": "tr" if clean_url(m.get("trailer_dub_url")) else "sub",
                        "trailer_dub_url": clean_url(m.get("trailer_dub_url")),
                        "trailer_sub_url": clean_url(m.get("trailer_sub_url")),
                        "keywords": clean_text(m.get("anahtar_kelimeler")) or "",
                        "year": year_val
                    }
                    movies_list.append(movies_item)
                return movies_list
        except Exception as e:
            print(f"[!] SQLite filmler okunurken hata: {e}, JSON dosyasına geçiliyor.")

    if not os.path.exists(MOVIES_JSON_PATH):
        return []
    
    with open(MOVIES_JSON_PATH, "r", encoding="utf-8") as f:
        movies_data = json.load(f)
        
    movies_list = []
    items_to_export = movies_data[:limit] if (limit and limit > 0) else movies_data
    for m in items_to_export:
        director = clean_text(m.get("director")) or "Bilinmiyor"
        cast_members = [clean_text(c.get("name")) for c in m.get("cast", []) if isinstance(c, dict) and c.get("name")][:2]
        duo_text = " & ".join(cast_members) if cast_members else f"Yönetmen: {director}"
        
        release = str(m.get("release_date") or "2020")
        year_val = 2020
        try:
            year_val = int(release[:4])
        except Exception:
            year_val = 2020

        runtime_mins = int(m.get('runtime_minutes') or 120)
        rating_num, votes_num = get_movie_rating_and_votes(m)
        clean_genres = clean_movie_genres(m.get("genres"))

        movies_item = {
            "id": f"movie_{m.get('id')}",
            "title": clean_text(m.get("title")) or clean_text(m.get("original_title")) or "İsimsiz Film",
            "rating": f"{rating_num:.1f}/10",
            "rating_num": rating_num,
            "seasons": "Sinema Filmi",
            "seasons_num": 1,
            "season_episodes_map": [1],
            "total_episodes": 1,
            "ep_duration": runtime_mins,
            "votes_num": votes_num,
            "runtime": f"{runtime_mins} dk",
            "platform": (m.get("streaming_platforms") or ["Netflix"])[0] if m.get("streaming_platforms") else "Sinema",
            "platforms": m.get("streaming_platforms") or ["Netflix"],
            "status": "Vizyon Filmi",
            "genres": clean_genres,
            "summary": clean_text(m.get("summary")) or "Özet henüz eklenmedi.",
            "duo": duo_text,
            "duo_desc": f"Başrol Oyuncuları ve {director} Sinematografisi.",
            "why_watch": [
                f"{director} tarafından yönetilen epik sinematik eser.",
                "Yüksek görsel kalite ve etkileyici ses tasarımı."
            ],
            "poster_url": m.get("poster_url"),
            "trailer_url": clean_url(m.get("trailer_url")),
            "trailer_type": m.get("trailer_type") or "tr",
            "trailer_dub_url": clean_url(m.get("trailer_dub_url")),
            "trailer_sub_url": clean_url(m.get("trailer_sub_url")),
            "year": year_val
        }
        movies_list.append(movies_item)
        
    return movies_list


def sanitize_obj(obj):
    if isinstance(obj, str):
        return obj.replace('\\', '').replace('"', "'").replace('\r', '').replace('\n', ' ').strip()
    elif isinstance(obj, list):
        return [sanitize_obj(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: sanitize_obj(v) for k, v in obj.items()}
    return obj

def main(limit=None):
    print("[+] Gercek dizi ve film verileri isleniyor...")
    series = sanitize_obj(get_real_series(limit=limit))
    movies = sanitize_obj(get_real_movies(limit=limit))

    with open(JS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("const REAL_SERIES_DATA = ")
        json.dump(series, f, ensure_ascii=False, indent=2)
        f.write(";\n\nconst REAL_MOVIES_DATA = ")
        json.dump(movies, f, ensure_ascii=False, indent=2)
        f.write(";\n")

    print(f"[OK] Basariyla aktarildi: {len(series)} Dizi ve {len(movies)} Film -> {JS_OUTPUT_PATH}")

if __name__ == "__main__":
    main()
