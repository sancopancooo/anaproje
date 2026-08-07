# -*- coding: utf-8 -*-
"""
Ana 4 platform (Netflix, Amazon, Disney+, HBO Max) için
kaliteli / bilinen yapımları doldurur — tüm kataloğu değil.

Kriter: vote_count.gte (default 1000) + watch_region=TR
Sıralama: vote_count.desc → klasik / niş ama bilinenler önce gelir.
Ayrıca mevcut kayıtlara eksik platform etiketini ekler.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEYS = [
    "92051c06137fc349cd7e1fc16291b607",
    "802b2c4b88ea1183e50e6b285a27696e",
    "3fd2be69067701ae820e7b94e17a4670",
    "fa155f635119344d33fcb84fb807649b",
]
BASE = "https://api.themoviedb.org/3"
REGION = "TR"
LANG = "tr-TR"

DB_MOVIES = "katalog.db"
DB_SHOWS = "katalog.db"

PROVIDERS = {
    8: "Netflix",
    119: "Amazon Prime",
    337: "Disney+",
    1899: "HBO Max",
}

_key_idx = 0


def fetch(url_without_key):
    global _key_idx
    last = None
    for _ in range(len(API_KEYS)):
        key = API_KEYS[_key_idx % len(API_KEYS)]
        _key_idx += 1
        url = f"{url_without_key}{'&' if '?' in url_without_key else '?'}api_key={key}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last = e
            time.sleep(0.4)
    raise RuntimeError(f"TMDB fail: {last}")


def clean_platforms(plat_str):
    if not plat_str:
        return ""
    parts = [p.strip() for p in str(plat_str).split(",") if p.strip()]
    seen = []
    for p in parts:
        name = p
        pl = p.lower()
        if "amazon" in pl or "prime" in pl:
            name = "Amazon Prime"
        elif "disney" in pl:
            name = "Disney+"
        elif "netflix" in pl:
            name = "Netflix"
        elif "hbo" in pl or pl.strip() == "max" or "hbo max" in pl:
            name = "HBO Max"
        elif "apple" in pl:
            name = "Apple TV+"
        elif "diğer" in pl:
            name = "Diğer Platform"
        if name not in seen:
            seen.append(name)
    if len(seen) > 1 and "Diğer Platform" in seen:
        seen.remove("Diğer Platform")
    return ", ".join(seen)


def merge_platform(existing, new_name):
    merged = clean_platforms(f"{existing or ''}, {new_name}")
    return merged


def why_watch(title, genres_str, rating):
    g = (genres_str or "").lower()
    r = float(rating or 7.0)
    m1 = f"{title}, özgün kurgusu ve atmosferiyle öne çıkan bir yapım."
    if "bilim" in g or "fantastik" in g:
        m1 = f"{title}, hayal gücünü zorlayan evreni ve kurgusuyla dikkat çekiyor."
    elif "aksiyon" in g or "macera" in g:
        m1 = f"{title}, temposu ve aksiyon sahneleriyle izleyiciyi peşinden sürüklüyor."
    elif "suç" in g or "gerilim" in g or "gizem" in g:
        m1 = f"{title}, gerilimi ve gizemiyle ekran başına kilitliyor."
    elif "komedi" in g:
        m1 = f"{title}, temposu ve mizahıyla keyifli bir seyir sunuyor."
    elif "dram" in g:
        m1 = f"{title}, karakter ilişkilerini etkileyici bir dille anlatıyor."
    m2 = (
        "Başrol performansları ve yüksek izleyici beğenisi."
        if r >= 8.0
        else "Güçlü karakterler, dengeli tempo ve inandırıcı sahne dili."
    )
    m3 = "Sinematik dokusu ve izleyicide bıraktığı kalıcı etki."
    return [m1, m2, m3]


def related_ids(media, tmdb_id, kind):
    """kind: recommendations | similar"""
    try:
        data = fetch(f"{BASE}/{media}/{tmdb_id}/{kind}?language={LANG}")
        return [r["id"] for r in (data.get("results") or [])[:12] if r.get("id")]
    except Exception:
        return []


def movie_details(tmdb_id, provider_name):
    d = fetch(
        f"{BASE}/movie/{tmdb_id}?language={LANG}"
        f"&append_to_response=videos,credits,keywords"
    )
    title = d.get("title") or d.get("original_title")
    if not title:
        return None
    poster = d.get("poster_path")
    backdrop = d.get("backdrop_path")
    if not poster:
        return None
    genres = [g["name"] for g in d.get("genres", []) if g.get("name")]
    genres_str = ", ".join(genres) if genres else "Dram"
    vote_avg = round(float(d.get("vote_average") or 0), 1)
    vote_cnt = int(d.get("vote_count") or 0)
    credits = d.get("credits", {})
    directors = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
    cast_names = [c["name"] for c in credits.get("cast", [])[:4]]
    videos = d.get("videos", {}).get("results", [])
    trailer = ""
    for v in videos:
        if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser"):
            trailer = f"https://www.youtube.com/embed/{v.get('key')}"
            break
    kw = d.get("keywords", {})
    kw_list = kw.get("keywords") or kw.get("results") or []
    keywords = ", ".join([k["name"] for k in kw_list[:20] if k.get("name")])
    companies = json.dumps(
        [c["name"] for c in d.get("production_companies", []) if c.get("name")],
        ensure_ascii=False,
    )
    countries = json.dumps(
        [c["iso_3166_1"] for c in d.get("production_countries", []) if c.get("iso_3166_1")],
        ensure_ascii=False,
    )
    collection = ""
    if isinstance(d.get("belongs_to_collection"), dict):
        collection = d["belongs_to_collection"].get("name") or ""
    rec_ids = related_ids("movie", tmdb_id, "recommendations")
    sim_ids = related_ids("movie", tmdb_id, "similar")
    return {
        "tmdb_id": str(tmdb_id),
        "isim": title,
        "orijinal_isim": d.get("original_title") or title,
        "vizyon_tarihi": d.get("release_date") or "",
        "sure": f"{d.get('runtime') or 110} dk",
        "turler": genres_str,
        "ozet": d.get("overview") or f"{title} filmi.",
        "poster_url": f"https://image.tmdb.org/t/p/w500{poster}",
        "fragman_url": trailer,
        "platformlar": provider_name,
        "anahtar_kelimeler": keywords,
        "puan": vote_avg,
        "oy_sayisi": vote_cnt,
        "trailer_dub_url": trailer,
        "trailer_sub_url": trailer,
        "neden_izlemeli": json.dumps(why_watch(title, genres_str, vote_avg), ensure_ascii=False),
        "backdrop_url": f"https://image.tmdb.org/t/p/w1280{backdrop}" if backdrop else "",
        "slogan": d.get("tagline") or "",
        "koleksiyon": collection,
        "yonetmen": ", ".join(directors[:2]) if directors else "Bilinmiyor",
        "oyuncular": ", ".join(cast_names) if cast_names else "Bilinmiyor",
        "butce": d.get("budget") or 0,
        "hasilat": d.get("revenue") or 0,
        "yapim_sirketleri": companies,
        "yapim_ulkeleri": countries,
        "orijinal_dil": d.get("original_language") or "en",
        "onerilen_idleri": json.dumps(rec_ids),
        "benzer_idleri": json.dumps(sim_ids),
    }


def tv_details(tmdb_id, provider_name):
    d = fetch(
        f"{BASE}/tv/{tmdb_id}?language={LANG}"
        f"&append_to_response=videos,credits,keywords"
    )
    title = d.get("name") or d.get("original_name")
    if not title:
        return None
    poster = d.get("poster_path")
    backdrop = d.get("backdrop_path")
    if not poster:
        return None
    genres = [g["name"] for g in d.get("genres", []) if g.get("name")]
    genres_str = ", ".join(genres) if genres else "Dram"
    vote_avg = round(float(d.get("vote_average") or 0), 1)
    vote_cnt = int(d.get("vote_count") or 0)
    ep_dur = d.get("episode_run_time") or [45]
    ep_dur = ep_dur[0] if ep_dur else 45
    status = "Bitmiş / Final Yapmış" if d.get("status") == "Ended" else "Devam Ediyor"
    videos = d.get("videos", {}).get("results", [])
    trailer = ""
    for v in videos:
        if v.get("site") == "YouTube" and v.get("type") in ("Trailer", "Teaser"):
            trailer = f"https://www.youtube.com/embed/{v.get('key')}"
            break
    cast_names = [c["name"] for c in d.get("credits", {}).get("cast", [])[:4]]
    kw = d.get("keywords", {})
    kw_list = kw.get("results") or kw.get("keywords") or []
    keywords = ", ".join([k["name"] for k in kw_list[:20] if k.get("name")])
    companies = json.dumps(
        [c["name"] for c in d.get("production_companies", []) if c.get("name")],
        ensure_ascii=False,
    )
    countries = json.dumps(
        [c["iso_3166_1"] for c in d.get("production_countries", []) if c.get("iso_3166_1")],
        ensure_ascii=False,
    )
    networks = ", ".join([n["name"] for n in d.get("networks", []) if n.get("name")])
    rec_ids = related_ids("tv", tmdb_id, "recommendations")
    sim_ids = related_ids("tv", tmdb_id, "similar")
    return {
        "id": int(tmdb_id),
        "isim": title,
        "ozet": d.get("overview") or f"{title} dizisi.",
        "puan_ortalamasi": vote_avg,
        "oy_sayisi": vote_cnt,
        "sezon_sayisi": d.get("number_of_seasons") or 1,
        "toplam_bolum_sayisi": d.get("number_of_episodes") or 10,
        "gercek_bolum_sureleri": ep_dur,
        "cikis_tarihi": d.get("first_air_date") or "",
        "tur": genres_str,
        "afis_url": f"https://image.tmdb.org/t/p/w500{poster}",
        "durum": status,
        "platformlar": provider_name,
        "backdrop_url": f"https://image.tmdb.org/t/p/w1280{backdrop}" if backdrop else "",
        "oyuncular_gercek": ", ".join(cast_names) if cast_names else "",
        "anahtar_kelimeler": keywords,
        "neden_izlemeli": json.dumps(why_watch(title, genres_str, vote_avg), ensure_ascii=False),
        "trailer_tr_url": trailer,
        "trailer_original_url": trailer,
        "yapim_ulkeleri": countries,
        "yayin_aglari": networks or provider_name,
        "yapim_sirketleri": companies,
        "orijinal_dil": d.get("original_language") or "en",
        "onerilen_idleri": json.dumps(rec_ids),
        "benzer_idleri": json.dumps(sim_ids),
    }


def load_existing_movies(conn):
    c = conn.cursor()
    c.execute("SELECT id, tmdb_id, isim, orijinal_isim, platformlar FROM filmler")
    by_tmdb = {}
    by_title = {}
    for row in c.fetchall():
        _id, tmdb_id, isim, orig, plats = row
        info = {"id": _id, "tmdb_id": str(tmdb_id) if tmdb_id else None, "platforms": plats or ""}
        if tmdb_id:
            by_tmdb[str(tmdb_id)] = info
        for t in (isim, orig):
            if t:
                by_title[t.strip().lower()] = info
    return by_tmdb, by_title


def load_existing_shows(conn):
    c = conn.cursor()
    # tmdb id is stored as id for many shows
    cols = [r[1] for r in c.execute("PRAGMA table_info(diziler)").fetchall()]
    c.execute("SELECT id, isim, platformlar FROM diziler")
    by_id = {}
    by_title = {}
    for _id, isim, plats in c.fetchall():
        info = {"id": _id, "platforms": plats or ""}
        by_id[int(_id)] = info
        if isim:
            by_title[isim.strip().lower()] = info
    return by_id, by_title, cols


def fill_movies(min_votes, max_pages, min_rating):
    conn = sqlite3.connect(DB_MOVIES, timeout=60)
    by_tmdb, by_title = load_existing_movies(conn)
    c = conn.cursor()
    added = updated = 0

    for provider_id, provider_name in PROVIDERS.items():
        print(f"\n🎬 [{provider_name}] filmler (oy>={min_votes}, max {max_pages} sayfa)...")
        for page in range(1, max_pages + 1):
            url = (
                f"{BASE}/discover/movie?language={LANG}"
                f"&with_watch_providers={provider_id}&watch_region={REGION}"
                f"&vote_count.gte={min_votes}&vote_average.gte={min_rating}"
                f"&sort_by=vote_count.desc&page={page}"
            )
            data = fetch(url)
            results = data.get("results") or []
            total_pages = int(data.get("total_pages") or 1)
            if page > total_pages:
                break
            if not results:
                break
            for item in results:
                tid = item.get("id")
                if not tid:
                    continue
                title = (item.get("title") or item.get("original_title") or "").strip()
                title_key = title.lower()
                existing = by_tmdb.get(str(tid)) or by_title.get(title_key)
                if existing:
                    new_plats = merge_platform(existing["platforms"], provider_name)
                    if new_plats != clean_platforms(existing["platforms"]):
                        c.execute(
                            "UPDATE filmler SET platformlar = ? WHERE id = ?",
                            (new_plats, existing["id"]),
                        )
                        existing["platforms"] = new_plats
                        updated += 1
                    continue
                try:
                    m = movie_details(tid, provider_name)
                    if not m or not m.get("poster_url"):
                        continue
                    c.execute(
                        """
                        INSERT INTO filmler
                        (tmdb_id, isim, orijinal_isim, vizyon_tarihi, sure, turler, ozet,
                         poster_url, fragman_url, platformlar, anahtar_kelimeler, puan, oy_sayisi,
                         trailer_dub_url, trailer_sub_url, neden_izlemeli, backdrop_url,
                         slogan, koleksiyon, yonetmen, oyuncular, butce, hasilat,
                         yapim_sirketleri, yapim_ulkeleri, orijinal_dil, onerilen_idleri, benzer_idleri)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            m["tmdb_id"], m["isim"], m["orijinal_isim"], m["vizyon_tarihi"],
                            m["sure"], m["turler"], m["ozet"], m["poster_url"], m["fragman_url"],
                            m["platformlar"], m["anahtar_kelimeler"], m["puan"], m["oy_sayisi"],
                            m["trailer_dub_url"], m["trailer_sub_url"], m["neden_izlemeli"],
                            m["backdrop_url"], m["slogan"], m["koleksiyon"], m["yonetmen"],
                            m["oyuncular"], m["butce"], m["hasilat"], m["yapim_sirketleri"],
                            m["yapim_ulkeleri"], m["orijinal_dil"], m["onerilen_idleri"],
                            m["benzer_idleri"],
                        ),
                    )
                    new_id = c.lastrowid
                    info = {"id": new_id, "tmdb_id": str(tid), "platforms": provider_name}
                    by_tmdb[str(tid)] = info
                    by_title[m["isim"].strip().lower()] = info
                    added += 1
                    print(f"  + {m['isim']} ({provider_name}) oy={m['oy_sayisi']}")
                    time.sleep(0.12)
                except Exception as e:
                    print(f"  ! skip {tid}: {e}")
            conn.commit()
            print(f"  sayfa {page}/{min(max_pages, total_pages)} | +{added} ~{updated}")
            time.sleep(0.2)

    conn.commit()
    conn.close()
    return added, updated


def fill_shows(min_votes, max_pages, min_rating):
    conn = sqlite3.connect(DB_SHOWS, timeout=60)
    by_id, by_title, cols = load_existing_shows(conn)
    c = conn.cursor()
    added = updated = 0

    for provider_id, provider_name in PROVIDERS.items():
        print(f"\n📺 [{provider_name}] diziler (oy>={min_votes}, max {max_pages} sayfa)...")
        for page in range(1, max_pages + 1):
            url = (
                f"{BASE}/discover/tv?language={LANG}"
                f"&with_watch_providers={provider_id}&watch_region={REGION}"
                f"&vote_count.gte={min_votes}&vote_average.gte={min_rating}"
                f"&sort_by=vote_count.desc&page={page}"
            )
            data = fetch(url)
            results = data.get("results") or []
            total_pages = int(data.get("total_pages") or 1)
            if page > total_pages:
                break
            if not results:
                break
            for item in results:
                tid = item.get("id")
                if not tid:
                    continue
                title = (item.get("name") or item.get("original_name") or "").strip()
                title_key = title.lower()
                existing = by_id.get(int(tid)) or by_title.get(title_key)
                if existing:
                    new_plats = merge_platform(existing["platforms"], provider_name)
                    if new_plats != clean_platforms(existing["platforms"]):
                        c.execute(
                            "UPDATE diziler SET platformlar = ? WHERE id = ?",
                            (new_plats, existing["id"]),
                        )
                        existing["platforms"] = new_plats
                        updated += 1
                    continue
                try:
                    s = tv_details(tid, provider_name)
                    if not s or not s.get("afis_url"):
                        continue
                    c.execute(
                        """
                        INSERT OR IGNORE INTO diziler
                        (id, isim, ozet, puan_ortalamasi, oy_sayisi, sezon_sayisi,
                         toplam_bolum_sayisi, gercek_bolum_sureleri, cikis_tarihi, tur,
                         afis_url, durum, platformlar, backdrop_url, oyuncular_gercek,
                         anahtar_kelimeler, neden_izlemeli, trailer_tr_url, trailer_original_url,
                         yapim_ulkeleri, yayin_aglari, yapim_sirketleri, orijinal_dil,
                         onerilen_idleri, benzer_idleri)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            s["id"], s["isim"], s["ozet"], s["puan_ortalamasi"], s["oy_sayisi"],
                            s["sezon_sayisi"], s["toplam_bolum_sayisi"], s["gercek_bolum_sureleri"],
                            s["cikis_tarihi"], s["tur"], s["afis_url"], s["durum"], s["platformlar"],
                            s["backdrop_url"], s["oyuncular_gercek"], s["anahtar_kelimeler"],
                            s["neden_izlemeli"], s["trailer_tr_url"], s["trailer_original_url"],
                            s["yapim_ulkeleri"], s["yayin_aglari"], s["yapim_sirketleri"],
                            s["orijinal_dil"], s["onerilen_idleri"], s["benzer_idleri"],
                        ),
                    )
                    if c.rowcount:
                        info = {"id": s["id"], "platforms": provider_name}
                        by_id[int(tid)] = info
                        by_title[s["isim"].strip().lower()] = info
                        added += 1
                        print(f"  + {s['isim']} ({provider_name}) oy={s['oy_sayisi']}")
                    time.sleep(0.12)
                except Exception as e:
                    print(f"  ! skip {tid}: {e}")
            conn.commit()
            print(f"  sayfa {page}/{min(max_pages, total_pages)} | +{added} ~{updated}")
            time.sleep(0.2)

    conn.commit()
    conn.close()
    return added, updated


def platforms_from_watch(tmdb_id, media="movie"):
    """TR flatrate sağlayıcılarından ana platform etiketlerini çıkar."""
    try:
        data = fetch(f"{BASE}/{media}/{tmdb_id}/watch/providers")
    except Exception:
        return "Diğer Platform"
    tr = (data.get("results") or {}).get("TR") or {}
    flat = tr.get("flatrate") or []
    names = []
    for p in flat:
        pid = p.get("provider_id")
        if pid in PROVIDERS:
            name = PROVIDERS[pid]
            if name not in names:
                names.append(name)
        else:
            pname = (p.get("provider_name") or "").lower()
            mapped = None
            if "netflix" in pname:
                mapped = "Netflix"
            elif "disney" in pname:
                mapped = "Disney+"
            elif "amazon" in pname or "prime" in pname:
                mapped = "Amazon Prime"
            elif "hbo" in pname or pname.strip() == "max":
                mapped = "HBO Max"
            if mapped and mapped not in names:
                names.append(mapped)
    return ", ".join(names) if names else "Diğer Platform"


def fill_high_vote_classics(min_votes=8000, max_pages=40, min_rating=7.0):
    """
    Platformda olsun olmasın: yüksek oylu bilinen filmleri eksikse ekler.
    Catch Me If You Can gibi klasiklerin şans eseri kaçmasını önler.
    """
    conn = sqlite3.connect(DB_MOVIES, timeout=60)
    by_tmdb, by_title = load_existing_movies(conn)
    c = conn.cursor()
    added = updated = 0
    print(f"\n⭐ Yüksek oylu klasikler (oy>={min_votes}, puan>={min_rating}, max {max_pages} sayfa)...")

    for page in range(1, max_pages + 1):
        url = (
            f"{BASE}/discover/movie?language={LANG}"
            f"&vote_count.gte={min_votes}&vote_average.gte={min_rating}"
            f"&sort_by=vote_count.desc&page={page}"
        )
        data = fetch(url)
        results = data.get("results") or []
        total_pages = int(data.get("total_pages") or 1)
        if page > total_pages or not results:
            break
        for item in results:
            tid = item.get("id")
            if not tid:
                continue
            title = (item.get("title") or item.get("original_title") or "").strip()
            existing = by_tmdb.get(str(tid)) or by_title.get(title.lower())
            if existing:
                continue
            try:
                plats = platforms_from_watch(tid, "movie")
                m = movie_details(tid, plats)
                if not m or not m.get("poster_url"):
                    continue
                m["platformlar"] = plats
                c.execute(
                    """
                    INSERT INTO filmler
                    (tmdb_id, isim, orijinal_isim, vizyon_tarihi, sure, turler, ozet,
                     poster_url, fragman_url, platformlar, anahtar_kelimeler, puan, oy_sayisi,
                     trailer_dub_url, trailer_sub_url, neden_izlemeli, backdrop_url,
                     slogan, koleksiyon, yonetmen, oyuncular, butce, hasilat,
                     yapim_sirketleri, yapim_ulkeleri, orijinal_dil, onerilen_idleri, benzer_idleri)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        m["tmdb_id"], m["isim"], m["orijinal_isim"], m["vizyon_tarihi"],
                        m["sure"], m["turler"], m["ozet"], m["poster_url"], m["fragman_url"],
                        m["platformlar"], m["anahtar_kelimeler"], m["puan"], m["oy_sayisi"],
                        m["trailer_dub_url"], m["trailer_sub_url"], m["neden_izlemeli"],
                        m["backdrop_url"], m["slogan"], m["koleksiyon"], m["yonetmen"],
                        m["oyuncular"], m["butce"], m["hasilat"], m["yapim_sirketleri"],
                        m["yapim_ulkeleri"], m["orijinal_dil"], m["onerilen_idleri"],
                        m["benzer_idleri"],
                    ),
                )
                info = {"id": c.lastrowid, "tmdb_id": str(tid), "platforms": plats}
                by_tmdb[str(tid)] = info
                by_title[m["isim"].strip().lower()] = info
                added += 1
                print(f"  + KLASIK {m['isim']} | {plats} | oy={m['oy_sayisi']}")
                time.sleep(0.15)
            except Exception as e:
                print(f"  ! skip {tid}: {e}")
        conn.commit()
        print(f"  klasik sayfa {page}/{min(max_pages, total_pages)} | +{added}")
        time.sleep(0.2)

    conn.commit()
    conn.close()
    return added, updated


def backfill_missing_graph(limit=400):
    """Önceki turda eksik kalan benzer/önerilen/backdrop alanlarını tamamla."""
    print(f"\n🔧 Eksik meta backfill (max {limit} film + {limit} dizi)...")
    # Movies
    conn = sqlite3.connect(DB_MOVIES, timeout=60)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, tmdb_id, platformlar FROM filmler
        WHERE tmdb_id IS NOT NULL AND tmdb_id != ''
          AND (
            benzer_idleri IS NULL OR benzer_idleri = '' OR benzer_idleri = '[]'
            OR onerilen_idleri IS NULL OR onerilen_idleri = '' OR onerilen_idleri = '[]'
            OR backdrop_url IS NULL OR backdrop_url = ''
          )
        ORDER BY oy_sayisi DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = c.fetchall()
    fixed_m = 0
    for _id, tmdb_id, plats in rows:
        try:
            m = movie_details(int(tmdb_id), plats or "Diğer Platform")
            if not m:
                continue
            c.execute(
                """
                UPDATE filmler SET
                  poster_url = COALESCE(NULLIF(poster_url, ''), ?),
                  backdrop_url = COALESCE(NULLIF(backdrop_url, ''), ?),
                  platformlar = COALESCE(NULLIF(platformlar, ''), ?),
                  anahtar_kelimeler = COALESCE(NULLIF(anahtar_kelimeler, ''), ?),
                  yapim_sirketleri = COALESCE(NULLIF(yapim_sirketleri, ''), ?),
                  yapim_ulkeleri = COALESCE(NULLIF(yapim_ulkeleri, ''), ?),
                  orijinal_dil = COALESCE(NULLIF(orijinal_dil, ''), ?),
                  koleksiyon = COALESCE(NULLIF(koleksiyon, ''), ?),
                  onerilen_idleri = ?,
                  benzer_idleri = ?
                WHERE id = ?
                """,
                (
                    m["poster_url"], m["backdrop_url"], m["platformlar"],
                    m["anahtar_kelimeler"], m["yapim_sirketleri"], m["yapim_ulkeleri"],
                    m["orijinal_dil"], m["koleksiyon"], m["onerilen_idleri"],
                    m["benzer_idleri"], _id,
                ),
            )
            fixed_m += 1
            if fixed_m % 25 == 0:
                conn.commit()
                print(f"  film backfill {fixed_m}/{len(rows)}")
            time.sleep(0.1)
        except Exception as e:
            print(f"  ! film {_id}: {e}")
    conn.commit()
    conn.close()

    # Shows
    conn = sqlite3.connect(DB_SHOWS, timeout=60)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, platformlar FROM diziler
        WHERE (
            benzer_idleri IS NULL OR benzer_idleri = '' OR benzer_idleri = '[]'
            OR onerilen_idleri IS NULL OR onerilen_idleri = '' OR onerilen_idleri = '[]'
            OR backdrop_url IS NULL OR backdrop_url = ''
          )
        ORDER BY oy_sayisi DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = c.fetchall()
    fixed_s = 0
    for _id, plats in rows:
        try:
            s = tv_details(int(_id), plats or "Diğer Platform")
            if not s:
                continue
            c.execute(
                """
                UPDATE diziler SET
                  afis_url = COALESCE(NULLIF(afis_url, ''), ?),
                  backdrop_url = COALESCE(NULLIF(backdrop_url, ''), ?),
                  platformlar = COALESCE(NULLIF(platformlar, ''), ?),
                  anahtar_kelimeler = COALESCE(NULLIF(anahtar_kelimeler, ''), ?),
                  yapim_sirketleri = COALESCE(NULLIF(yapim_sirketleri, ''), ?),
                  yapim_ulkeleri = COALESCE(NULLIF(yapim_ulkeleri, ''), ?),
                  orijinal_dil = COALESCE(NULLIF(orijinal_dil, ''), ?),
                  yayin_aglari = COALESCE(NULLIF(yayin_aglari, ''), ?),
                  onerilen_idleri = ?,
                  benzer_idleri = ?
                WHERE id = ?
                """,
                (
                    s["afis_url"], s["backdrop_url"], s["platformlar"],
                    s["anahtar_kelimeler"], s["yapim_sirketleri"], s["yapim_ulkeleri"],
                    s["orijinal_dil"], s["yayin_aglari"], s["onerilen_idleri"],
                    s["benzer_idleri"], _id,
                ),
            )
            fixed_s += 1
            if fixed_s % 25 == 0:
                conn.commit()
                print(f"  dizi backfill {fixed_s}/{len(rows)}")
            time.sleep(0.1)
        except Exception as e:
            print(f"  ! dizi {_id}: {e}")
    conn.commit()
    conn.close()
    print(f"  backfill tamam: film={fixed_m} dizi={fixed_s}")
    return fixed_m, fixed_s


def verify_catch_me():
    conn = sqlite3.connect(DB_MOVIES)
    c = conn.cursor()
    c.execute(
        """
        SELECT id, tmdb_id, isim, platformlar, puan, oy_sayisi,
               CASE WHEN poster_url IS NOT NULL AND poster_url != '' THEN 1 ELSE 0 END,
               CASE WHEN backdrop_url IS NOT NULL AND backdrop_url != '' THEN 1 ELSE 0 END,
               CASE WHEN benzer_idleri IS NOT NULL AND benzer_idleri != '' AND benzer_idleri != '[]' THEN 1 ELSE 0 END,
               CASE WHEN onerilen_idleri IS NOT NULL AND onerilen_idleri != '' AND onerilen_idleri != '[]' THEN 1 ELSE 0 END
        FROM filmler
        WHERE tmdb_id = '640'
           OR lower(orijinal_isim) LIKE '%catch me if you can%'
        """
    )
    rows = c.fetchall()
    conn.close()
    print("\nCatch Me If You Can kontrol (poster/backdrop/benzer/önerilen):")
    if not rows:
        print("  YOK")
    for r in rows:
        print(" ", r)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-votes", type=int, default=500)
    parser.add_argument("--min-rating", type=float, default=6.5)
    parser.add_argument("--pages", type=int, default=30)
    parser.add_argument("--classics-votes", type=int, default=5000)
    parser.add_argument("--classics-pages", type=int, default=50)
    parser.add_argument("--type", choices=["all", "movie", "show"], default="all")
    parser.add_argument("--skip-classics", action="store_true")
    parser.add_argument("--backfill-only", action="store_true")
    parser.add_argument("--backfill-limit", type=int, default=350)
    args = parser.parse_args()

    if args.backfill_only:
        backfill_missing_graph(args.backfill_limit)
        verify_catch_me()
        return

    print("=" * 70)
    print("Ana platform kaliteli katalog doldurma")
    print(f"  min_votes={args.min_votes} min_rating={args.min_rating} pages={args.pages}")
    print("=" * 70)

    m_add = m_up = s_add = s_up = c_add = 0
    if args.type in ("all", "movie"):
        m_add, m_up = fill_movies(args.min_votes, args.pages, args.min_rating)
        if not args.skip_classics:
            c_add, _ = fill_high_vote_classics(
                min_votes=args.classics_votes,
                max_pages=args.classics_pages,
                min_rating=7.0,
            )
    if args.type in ("all", "show"):
        s_add, s_up = fill_shows(args.min_votes, args.pages, args.min_rating)

    backfill_missing_graph(args.backfill_limit)

    print("\n" + "=" * 70)
    print(f"Film (platform): +{m_add} eklendi, {m_up} platform güncellendi")
    print(f"Film (klasik):   +{c_add} eklendi")
    print(f"Dizi: +{s_add} eklendi, {s_up} platform güncellendi")
    print("=" * 70)
    verify_catch_me()


if __name__ == "__main__":
    main()
