# -*- coding: utf-8 -*-
"""
eksik_meta_tmdb_json.py
-----------------------
Dizi + film için kalan önemli meta alanlarını TMDB'den çeker, JSON'a yazar.
DB'ye yazmaz.

Diziler  → diziler_veritabani.db
Filmler  → diziler_veritabanı.db
Çıktı    → eksik_meta_tmdb_raporu.json

Dizi alanları:
  anahtar_kelimeler, efsanevi_ikili, oyuncular_gercek,
  puan_ortalamasi, oy_sayisi, icerik_derecelendirme,
  yapim_sirketleri, yayin_aglari, backdrop_url

Film alanları:
  anahtar_kelimeler, slogan, yonetmen, oyuncular,
  puan, oy_sayisi, yapim_sirketleri, backdrop_url,
  butce, hasilat, koleksiyon

Kullanım:
    python eksik_meta_tmdb_json.py --tip hepsi --sadece-bos --workers 6
    python eksik_meta_tmdb_json.py --tip dizi --sadece-bos --devam
    python eksik_meta_tmdb_json.py --tip film --limit 50
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"
DB_DIZI = "katalog.db"
DB_FILM = "katalog.db"
OUTPUT_JSON = "eksik_meta_tmdb_raporu.json"
LANGUAGE = "tr-TR"
IMAGE_BASE = "https://image.tmdb.org/t/p/w1280"
MAX_RETRIES = 3
SAVE_EVERY = 40

print_lock = Lock()
file_lock = Lock()


def log(msg):
    with print_lock:
        print(msg, flush=True)


def safe_get(url, params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=25)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 12))
                time.sleep(wait + 1)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (500, 502, 503, 504):
                time.sleep(2 * attempt)
                continue
            return None
        except Exception:
            time.sleep(2 * attempt)
    return None


def is_empty(val, numeric=False):
    if val is None:
        return True
    if numeric:
        try:
            return float(val) == 0
        except (TypeError, ValueError):
            return True
    s = str(val).strip()
    return s == "" or s == "[]" or s.lower() in ("null", "bilinmiyor")


def load_tmdb_cache():
    """Önceki JSON raporlarından tmdb_id haritası."""
    dizi_cache, film_cache = {}, {}
    for path, key, cache in [
        ("sezon_bolum_tmdb_raporu.json", "diziler", dizi_cache),
        ("dizi_ek_veri_tmdb_raporu.json", "diziler", dizi_cache),
        ("film_ek_veri_tmdb_raporu.json", "filmler", film_cache),
        ("fragman_tmdb_raporu.json", "diziler", dizi_cache),
        ("fragman_tmdb_raporu.json", "filmler", film_cache),
    ]:
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get(key) or []:
                if item.get("id") and item.get("tmdb_id"):
                    cache[item["id"]] = int(item["tmdb_id"])
        except Exception:
            pass
    return dizi_cache, film_cache


def search_id(media_type, isim, yil=""):
    endpoint = "tv" if media_type == "dizi" else "movie"
    params = {
        "api_key": API_KEY,
        "language": LANGUAGE,
        "query": isim,
        "include_adult": "false",
    }
    if yil and str(yil)[:4].isdigit():
        if media_type == "dizi":
            params["first_air_date_year"] = str(yil)[:4]
        else:
            params["primary_release_year"] = str(yil)[:4]
    data = safe_get(f"{BASE_URL}/search/{endpoint}", params)
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    date_key = "first_air_date" if media_type == "dizi" else "release_date"
    if yil and str(yil)[:4].isdigit():
        for item in results:
            d = item.get(date_key) or ""
            if d.startswith(str(yil)[:4]):
                return item.get("id")
    return results[0].get("id")


def keywords_str(keywords_block):
    # movie: {"keywords":[...]}  tv: {"results":[...]}
    if not keywords_block:
        return ""
    items = keywords_block.get("keywords") or keywords_block.get("results") or []
    names = []
    for k in items:
        n = (k.get("name") or "").strip().lower()
        if n and n not in names:
            names.append(n)
        if len(names) >= 12:
            break
    return ", ".join(names)


def cast_names(credits, limit=6):
    cast = (credits or {}).get("cast") or []
    names = []
    for p in cast:
        n = (p.get("name") or "").strip()
        if n and n not in names:
            names.append(n)
        if len(names) >= limit:
            break
    return names


def cast_with_roles(credits, limit=5):
    cast = (credits or {}).get("cast") or []
    parts = []
    for p in cast[:limit]:
        n = (p.get("name") or "").strip()
        ch = (p.get("character") or "").strip()
        if not n:
            continue
        parts.append(f"{n} ({ch})" if ch else n)
    return ", ".join(parts)


def director_name(credits):
    crew = (credits or {}).get("crew") or []
    for p in crew:
        if (p.get("job") or "") == "Director":
            return (p.get("name") or "").strip() or None
    return None


def content_rating(block):
    for r_item in (block or {}).get("results") or []:
        if r_item.get("iso_3166_1") == "TR" and r_item.get("rating"):
            return r_item.get("rating")
    for r_item in (block or {}).get("results") or []:
        if r_item.get("iso_3166_1") == "US" and r_item.get("rating"):
            return r_item.get("rating")
    return None


def fetch_dizi_meta(tmdb_id):
    data = safe_get(
        f"{BASE_URL}/tv/{tmdb_id}",
        {
            "api_key": API_KEY,
            "language": LANGUAGE,
            "append_to_response": "credits,keywords,content_ratings",
        },
    )
    if not data:
        return None

    names = cast_names(data.get("credits"), 6)
    duo = f"{names[0]} & {names[1]}" if len(names) >= 2 else (names[0] if names else None)
    bp = data.get("backdrop_path")

    puan = data.get("vote_average")
    try:
        puan = round(float(puan), 1) if puan is not None else None
    except (TypeError, ValueError):
        puan = None
    oy = data.get("vote_count")
    try:
        oy = int(oy) if oy is not None else None
    except (TypeError, ValueError):
        oy = None

    return {
        "tmdb_name": data.get("name"),
        "anahtar_kelimeler": keywords_str(data.get("keywords")),
        "oyuncular_gercek": ", ".join(names) if names else None,
        "efsanevi_ikili": duo,
        "puan_ortalamasi": puan,
        "oy_sayisi": oy,
        "icerik_derecelendirme": content_rating(data.get("content_ratings")),
        "yapim_sirketleri": [p.get("name") for p in (data.get("production_companies") or []) if p.get("name")],
        "yayin_aglari": [n.get("name") for n in (data.get("networks") or []) if n.get("name")],
        "backdrop_url": f"{IMAGE_BASE}{bp}" if bp else None,
    }


def fetch_film_meta(tmdb_id):
    data = safe_get(
        f"{BASE_URL}/movie/{tmdb_id}",
        {
            "api_key": API_KEY,
            "language": LANGUAGE,
            "append_to_response": "credits,keywords",
        },
    )
    if not data:
        return None

    bp = data.get("backdrop_path")
    puan = data.get("vote_average")
    try:
        puan = round(float(puan), 3) if puan is not None else None
    except (TypeError, ValueError):
        puan = None
    oy = data.get("vote_count")
    try:
        oy = int(oy) if oy is not None else None
    except (TypeError, ValueError):
        oy = None

    coll = data.get("belongs_to_collection")
    return {
        "tmdb_name": data.get("title"),
        "anahtar_kelimeler": keywords_str(data.get("keywords")),
        "slogan": (data.get("tagline") or "").strip() or None,
        "yonetmen": director_name(data.get("credits")),
        "oyuncular": cast_with_roles(data.get("credits"), 5) or None,
        "puan": puan,
        "oy_sayisi": oy,
        "yapim_sirketleri": [p.get("name") for p in (data.get("production_companies") or []) if p.get("name")],
        "backdrop_url": f"{IMAGE_BASE}{bp}" if bp else None,
        "butce": int(data.get("budget") or 0),
        "hasilat": int(data.get("revenue") or 0),
        "koleksiyon": (coll.get("name") if isinstance(coll, dict) else None),
    }


def process_dizi(row, cache):
    item_id, isim, yil = row["id"], row["isim"] or "", row.get("yil") or ""
    tmdb_id = cache.get(item_id) or search_id("dizi", isim, yil)
    if not tmdb_id:
        return {"id": item_id, "isim": isim, "tmdb_id": None, "durum": "tmdb_bulunamadi"}
    meta = fetch_dizi_meta(tmdb_id)
    if not meta:
        return {"id": item_id, "isim": isim, "tmdb_id": tmdb_id, "durum": "api_hatasi"}
    return {"id": item_id, "isim": isim, "tmdb_id": tmdb_id, "durum": "ok", **meta}


def process_film(row, cache):
    item_id, isim = row["id"], row["isim"] or ""
    tmdb_id = row.get("tmdb_id") or cache.get(item_id)
    try:
        tmdb_id = int(tmdb_id) if tmdb_id not in (None, "") else None
    except (TypeError, ValueError):
        tmdb_id = None
    if not tmdb_id:
        tmdb_id = search_id("film", isim, row.get("yil") or "")
    if not tmdb_id:
        return {"id": item_id, "isim": isim, "tmdb_id": None, "durum": "tmdb_bulunamadi"}
    meta = fetch_film_meta(tmdb_id)
    if not meta:
        return {"id": item_id, "isim": isim, "tmdb_id": tmdb_id, "durum": "api_hatasi"}
    return {"id": item_id, "isim": isim, "tmdb_id": tmdb_id, "durum": "ok", **meta}


def load_dizi_rows(sadece_bos):
    conn = sqlite3.connect(DB_DIZI)
    c = conn.cursor()
    if sadece_bos:
        c.execute("""
            SELECT id, isim, cikis_tarihi FROM diziler WHERE
              (anahtar_kelimeler IS NULL OR TRIM(COALESCE(anahtar_kelimeler,''))='')
              OR (efsanevi_ikili IS NULL OR TRIM(COALESCE(efsanevi_ikili,''))='')
              OR (oyuncular_gercek IS NULL OR TRIM(COALESCE(oyuncular_gercek,''))='')
              OR (puan_ortalamasi IS NULL OR puan_ortalamasi = 0)
              OR (oy_sayisi IS NULL OR oy_sayisi = 0)
              OR (icerik_derecelendirme IS NULL OR TRIM(COALESCE(icerik_derecelendirme,''))='')
              OR (yapim_sirketleri IS NULL OR TRIM(COALESCE(yapim_sirketleri,''))='' OR yapim_sirketleri='[]')
              OR (yayin_aglari IS NULL OR TRIM(COALESCE(yayin_aglari,''))='' OR yayin_aglari='[]')
              OR (backdrop_url IS NULL OR TRIM(COALESCE(backdrop_url,''))='')
            ORDER BY id
        """)
    else:
        c.execute("SELECT id, isim, cikis_tarihi FROM diziler ORDER BY id")
    rows = [{"id": r[0], "isim": r[1], "yil": (r[2] or "")[:4]} for r in c.fetchall()]
    conn.close()
    return rows


def load_film_rows(sadece_bos):
    conn = sqlite3.connect(DB_FILM)
    c = conn.cursor()
    if sadece_bos:
        c.execute("""
            SELECT id, tmdb_id, isim, vizyon_tarihi FROM filmler WHERE
              (anahtar_kelimeler IS NULL OR TRIM(COALESCE(anahtar_kelimeler,''))='')
              OR (slogan IS NULL OR TRIM(COALESCE(slogan,''))='')
              OR (yonetmen IS NULL OR TRIM(COALESCE(yonetmen,''))='' OR yonetmen='Bilinmiyor')
              OR (oyuncular IS NULL OR TRIM(COALESCE(oyuncular,''))='')
              OR (puan IS NULL OR puan = 0)
              OR (oy_sayisi IS NULL OR oy_sayisi = 0)
              OR (yapim_sirketleri IS NULL OR TRIM(COALESCE(yapim_sirketleri,''))='' OR yapim_sirketleri='[]')
              OR (backdrop_url IS NULL OR TRIM(COALESCE(backdrop_url,''))='')
            ORDER BY id
        """)
    else:
        c.execute("SELECT id, tmdb_id, isim, vizyon_tarihi FROM filmler ORDER BY id")
    rows = [
        {"id": r[0], "tmdb_id": r[1], "isim": r[2], "yil": (r[3] or "")[:4]}
        for r in c.fetchall()
    ]
    conn.close()
    return rows


def save_report(data):
    with file_lock:
        tmp = OUTPUT_JSON + ".tmp"
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        for attempt in range(1, 10):
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.replace(tmp, OUTPUT_JSON)
                except (FileNotFoundError, PermissionError):
                    time.sleep(0.3 * attempt)
                    continue
                return
            except (PermissionError, FileNotFoundError, OSError):
                time.sleep(0.3 * attempt)
        alt = OUTPUT_JSON.replace(".json", f"_yedek_{int(time.time())}.json")
        with open(alt, "w", encoding="utf-8") as f:
            f.write(payload)
        log(f"⚠️ Yedek: {alt}")


def load_existing():
    if not os.path.exists(OUTPUT_JSON):
        return None
    try:
        with open(OUTPUT_JSON, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def recount(items):
    counts = {}
    for it in items:
        d = it.get("durum") or "yok"
        counts[d] = counts.get(d, 0) + 1
    return counts


def scan_tip(media_type, workers, limit, sadece_bos, devam, report, cache):
    label = "DİZİ" if media_type == "dizi" else "FİLM"
    emoji = "📺" if media_type == "dizi" else "🎬"
    key = "diziler" if media_type == "dizi" else "filmler"
    rows = load_dizi_rows(sadece_bos) if media_type == "dizi" else load_film_rows(sadece_bos)
    if limit:
        rows = rows[:limit]

    existing = list(report.get(key) or []) if devam else []
    if devam and existing:
        done_ids = {x["id"] for x in existing}
        rows = [r for r in rows if r["id"] not in done_ids]
        log(f"⏩ {label} devam: {len(done_ids)} atlandı, {len(rows)} kaldı")

    total_all = len(existing) + len(rows)
    log(f"\n{'=' * 70}")
    log(f"{emoji} {label} EKSİK META → JSON")
    log(f"   Toplam: {total_all} (bu tur: {len(rows)}) | workers={workers}")
    log("=" * 70)

    if not rows:
        log(f"✅ {label}: taranacak yok.")
        report[key] = sorted(existing, key=lambda x: x["id"])
        report["ozet"][key] = {"toplam": total_all, "tamamlanan": total_all, **recount(existing)}
        return report

    results = list(existing)
    done = 0
    counts = recount(results)
    worker = process_dizi if media_type == "dizi" else process_film

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker, row, cache): row for row in rows}
        for fut in as_completed(futures):
            item = fut.result()
            results.append(item)
            d = item.get("durum") or "yok"
            counts[d] = counts.get(d, 0) + 1
            done += 1
            tamam = len(existing) + done
            mark = "✅" if d == "ok" else "❌"
            extra = ""
            if media_type == "dizi" and d == "ok":
                extra = f"kw={(item.get('anahtar_kelimeler') or '')[:20]:<20} cast={(item.get('oyuncular_gercek') or '')[:18]}"
            elif d == "ok":
                extra = f"★{item.get('puan')} dir={(item.get('yonetmen') or '-')[:16]}"
            log(f"[{tamam:4d}/{total_all}] {mark} {str(item.get('isim') or '')[:30]:<30} {extra}")

            if done % SAVE_EVERY == 0 or done == len(rows):
                sorted_results = sorted(results, key=lambda x: x["id"])
                report[key] = sorted_results
                report["ozet"][key] = {"toplam": total_all, "tamamlanan": tamam, **counts}
                report["guncelleme"] = datetime.now().isoformat()
                save_report(report)
                log(f"          💾 Ara kayıt ({tamam}/{total_all})")

    sorted_results = sorted(results, key=lambda x: x["id"])
    report[key] = sorted_results
    report["ozet"][key] = {"toplam": total_all, "tamamlanan": len(sorted_results), **recount(sorted_results)}
    report["guncelleme"] = datetime.now().isoformat()
    save_report(report)

    log(f"\n📊 {label} ÖZET: {report['ozet'][key]}")
    return report


def main():
    global API_KEY
    parser = argparse.ArgumentParser()
    parser.add_argument("--tip", choices=["dizi", "film", "hepsi"], default="hepsi")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--devam", action="store_true")
    parser.add_argument("--sadece-bos", action="store_true")
    parser.add_argument("--api-key", type=str, default=None)
    args = parser.parse_args()
    if args.api_key:
        API_KEY = args.api_key.strip()

    dizi_cache, film_cache = load_tmdb_cache()
    log(f"🔑 TMDB önbellek: dizi={len(dizi_cache)}, film={len(film_cache)}")

    if args.devam:
        report = load_existing()
        if not report:
            log("⚠️ Devam JSON yok, sıfırdan.")
            args.devam = False
            report = None
    else:
        report = None

    if not args.devam:
        report = {
            "olusturulma": datetime.now().isoformat(),
            "guncelleme": datetime.now().isoformat(),
            "not": "DB'ye yazılmadı. Aktarım ayrı adımda.",
            "ozet": {},
            "diziler": [],
            "filmler": [],
        }
    else:
        report.setdefault("ozet", {})
        report.setdefault("diziler", [])
        report.setdefault("filmler", [])

    log("=" * 70)
    log("🧩 EKSİK META → JSON (dizi + film, tek script)")
    log(f"   Tip: {args.tip} | sadece-bos={args.sadece_bos} | devam={args.devam}")
    log(f"   Çıktı: {OUTPUT_JSON}")
    log("=" * 70)
    save_report(report)

    if args.tip in ("dizi", "hepsi"):
        scan_tip("dizi", args.workers, args.limit, args.sadece_bos, args.devam, report, dizi_cache)
    if args.tip in ("film", "hepsi"):
        scan_tip("film", args.workers, args.limit, args.sadece_bos, args.devam, report, film_cache)

    log("\n" + "=" * 70)
    log(f"✅ Bitti → {OUTPUT_JSON}")
    log("   DB'ye henüz yazılmadı.")
    log("=" * 70)


if __name__ == "__main__":
    main()
