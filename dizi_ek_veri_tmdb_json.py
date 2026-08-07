# -*- coding: utf-8 -*-
"""
dizi_ek_veri_tmdb_json.py
-------------------------
Diziler için ek TMDB verilerini tek tarama + tek JSON'a çeker.
DB'ye yazmaz.

Alanlar (tek API çağrısı / dizi):
  - orijinal_dil
  - yapim_ulkeleri
  - onerilen_idleri
  - benzer_idleri
  (+ aynı yanıttan): yayin_aglari, yapim_sirketleri, icerik_derecelendirme

Kaynak DB : diziler_veritabani.db
Çıktı     : dizi_ek_veri_tmdb_raporu.json

Kullanım:
    python dizi_ek_veri_tmdb_json.py --sadece-bos --workers 6
    python dizi_ek_veri_tmdb_json.py --sadece-bos --devam
    python dizi_ek_veri_tmdb_json.py --limit 20
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
OUTPUT_JSON = "dizi_ek_veri_tmdb_raporu.json"
SEZON_JSON = "sezon_bolum_tmdb_raporu.json"  # tmdb_id önbelleği
LANGUAGE = "tr-TR"
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


def is_empty_field(val):
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s == "[]" or s.lower() == "null"


def load_tmdb_id_cache():
    """sezon_bolum JSON'undan bilinen tmdb_id'leri al."""
    cache = {}
    if not os.path.exists(SEZON_JSON):
        return cache
    try:
        with open(SEZON_JSON, encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("diziler") or []:
            if item.get("id") and item.get("tmdb_id"):
                cache[item["id"]] = int(item["tmdb_id"])
    except Exception:
        pass
    return cache


def search_tv_id(isim, yil=""):
    params = {
        "api_key": API_KEY,
        "language": LANGUAGE,
        "query": isim,
        "include_adult": "false",
    }
    if yil and str(yil)[:4].isdigit():
        params["first_air_date_year"] = str(yil)[:4]
    data = safe_get(f"{BASE_URL}/search/tv", params)
    if not data:
        return None
    results = data.get("results") or []
    if not results:
        return None
    if yil and str(yil)[:4].isdigit():
        for item in results:
            fad = item.get("first_air_date") or ""
            if fad.startswith(str(yil)[:4]):
                return item.get("id")
    return results[0].get("id")


def fetch_extras(tmdb_id):
    data = safe_get(
        f"{BASE_URL}/tv/{tmdb_id}",
        {
            "api_key": API_KEY,
            "language": LANGUAGE,
            "append_to_response": "recommendations,similar,content_ratings",
        },
    )
    if not data:
        return None

    countries = [c.get("iso_3166_1") for c in (data.get("production_countries") or []) if c.get("iso_3166_1")]
    if not countries:
        countries = list(data.get("origin_country") or [])

    rating = None
    for r_item in (data.get("content_ratings") or {}).get("results") or []:
        if r_item.get("iso_3166_1") in ("TR", "US"):
            rating = r_item.get("rating")
            if r_item.get("iso_3166_1") == "TR":
                break

    recs = [item["id"] for item in (data.get("recommendations") or {}).get("results") or [] if "id" in item]
    sims = [item["id"] for item in (data.get("similar") or {}).get("results") or [] if "id" in item]

    return {
        "tmdb_name": data.get("name") or data.get("original_name"),
        "orijinal_dil": data.get("original_language"),
        "yapim_ulkeleri": countries,
        "yayin_aglari": [n.get("name") for n in (data.get("networks") or []) if n.get("name")],
        "yapim_sirketleri": [p.get("name") for p in (data.get("production_companies") or []) if p.get("name")],
        "icerik_derecelendirme": rating,
        "onerilen_idleri": recs,
        "benzer_idleri": sims,
    }


def process_item(row, tmdb_cache):
    item_id = row["id"]
    isim = row["isim"] or ""
    yil = row.get("yil") or ""

    tmdb_id = tmdb_cache.get(item_id)
    if not tmdb_id:
        tmdb_id = search_tv_id(isim, yil)

    if not tmdb_id:
        return {
            "id": item_id,
            "isim": isim,
            "yil": yil,
            "tmdb_id": None,
            "durum": "tmdb_bulunamadi",
            "orijinal_dil": None,
            "yapim_ulkeleri": [],
            "onerilen_idleri": [],
            "benzer_idleri": [],
            "yayin_aglari": [],
            "yapim_sirketleri": [],
            "icerik_derecelendirme": None,
        }

    extras = fetch_extras(tmdb_id)
    if not extras:
        return {
            "id": item_id,
            "isim": isim,
            "yil": yil,
            "tmdb_id": tmdb_id,
            "durum": "api_hatasi",
            "orijinal_dil": None,
            "yapim_ulkeleri": [],
            "onerilen_idleri": [],
            "benzer_idleri": [],
            "yayin_aglari": [],
            "yapim_sirketleri": [],
            "icerik_derecelendirme": None,
        }

    return {
        "id": item_id,
        "isim": isim,
        "yil": yil,
        "tmdb_id": tmdb_id,
        "durum": "ok",
        **extras,
    }


def load_rows(sadece_bos=False):
    conn = sqlite3.connect(DB_DIZI)
    c = conn.cursor()
    if sadece_bos:
        c.execute("""
            SELECT id, isim, cikis_tarihi,
                   yapim_ulkeleri, orijinal_dil, onerilen_idleri, benzer_idleri
            FROM diziler
            WHERE (yapim_ulkeleri IS NULL OR TRIM(COALESCE(yapim_ulkeleri,''))='' OR yapim_ulkeleri='[]')
               OR (orijinal_dil IS NULL OR TRIM(COALESCE(orijinal_dil,''))='')
               OR (onerilen_idleri IS NULL OR TRIM(COALESCE(onerilen_idleri,''))='' OR onerilen_idleri='[]')
               OR (benzer_idleri IS NULL OR TRIM(COALESCE(benzer_idleri,''))='' OR benzer_idleri='[]')
            ORDER BY id
        """)
    else:
        c.execute("""
            SELECT id, isim, cikis_tarihi,
                   yapim_ulkeleri, orijinal_dil, onerilen_idleri, benzer_idleri
            FROM diziler ORDER BY id
        """)
    rows = [
        {
            "id": r[0],
            "isim": r[1],
            "yil": (r[2] or "")[:4],
            "db_yapim_ulkeleri": r[3],
            "db_orijinal_dil": r[4],
            "db_onerilen": r[5],
            "db_benzer": r[6],
        }
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
                # Windows: hedef kilitliyse önce silmeyi dene
                if os.path.exists(OUTPUT_JSON):
                    try:
                        os.replace(tmp, OUTPUT_JSON)
                    except FileNotFoundError:
                        # tmp kaybolduysa yeniden yaz
                        time.sleep(0.2)
                        continue
                    except PermissionError:
                        time.sleep(0.4 * attempt)
                        continue
                else:
                    os.replace(tmp, OUTPUT_JSON)
                return
            except PermissionError:
                time.sleep(0.4 * attempt)
            except FileNotFoundError:
                time.sleep(0.2 * attempt)
            except Exception:
                time.sleep(0.3 * attempt)
        alt = OUTPUT_JSON.replace(".json", f"_yedek_{int(time.time())}.json")
        with open(alt, "w", encoding="utf-8") as f:
            f.write(payload)
        log(f"⚠️ Yedek yazıldı: {alt}")


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


def main():
    global API_KEY
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--devam", action="store_true")
    parser.add_argument("--sadece-bos", action="store_true")
    parser.add_argument("--api-key", type=str, default=None)
    args = parser.parse_args()
    if args.api_key:
        API_KEY = args.api_key.strip()

    tmdb_cache = load_tmdb_id_cache()
    log(f"🔑 TMDB id önbelleği: {len(tmdb_cache)} (sezon JSON)")

    rows = load_rows(sadece_bos=args.sadece_bos)
    if args.limit:
        rows = rows[: args.limit]

    if args.devam:
        report = load_existing()
        if not report:
            log("⚠️ Devam JSON yok, sıfırdan.")
            args.devam = False
    else:
        report = None

    if not args.devam:
        report = {
            "olusturulma": datetime.now().isoformat(),
            "guncelleme": datetime.now().isoformat(),
            "not": "DB'ye yazılmadı. Aktarım ayrı adımda.",
            "kaynak_db": DB_DIZI,
            "alanlar": [
                "orijinal_dil", "yapim_ulkeleri", "onerilen_idleri", "benzer_idleri",
                "yayin_aglari", "yapim_sirketleri", "icerik_derecelendirme",
            ],
            "ozet": {},
            "diziler": [],
        }
    else:
        report.setdefault("diziler", [])
        done_ids = {x["id"] for x in report["diziler"]}
        rows = [r for r in rows if r["id"] not in done_ids]
        log(f"⏩ Devam: {len(done_ids)} atlandı, {len(rows)} kaldı")

    existing = list(report.get("diziler") or [])
    total_all = len(existing) + len(rows)

    log("=" * 70)
    log("📺 DİZİ EK VERİ → JSON (TMDB tek çağrı)")
    log(f"   DB       : {DB_DIZI}")
    log(f"   Çıktı    : {OUTPUT_JSON}")
    log(f"   Toplam   : {total_all} (bu tur: {len(rows)})")
    log(f"   Workers  : {args.workers}")
    log(f"   Sadece boş: {args.sadece_bos}")
    log("=" * 70)
    save_report(report)

    if not rows:
        log("✅ Taranacak kayıt yok.")
        return

    results = list(existing)
    done = 0
    counts = recount(results)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_item, row, tmdb_cache): row for row in rows}
        for fut in as_completed(futures):
            item = fut.result()
            results.append(item)
            d = item.get("durum") or "yok"
            counts[d] = counts.get(d, 0) + 1
            done += 1
            tamam = len(existing) + done

            mark = "✅" if d == "ok" else ("⚠️" if d == "tmdb_bulunamadi" else "❌")
            ulke = ",".join(item.get("yapim_ulkeleri") or []) or "-"
            dil = item.get("orijinal_dil") or "-"
            n_rec = len(item.get("onerilen_idleri") or [])
            n_sim = len(item.get("benzer_idleri") or [])
            log(
                f"[{tamam:4d}/{total_all}] {mark} {str(item.get('isim') or '')[:34]:<34} "
                f"{dil:>3} {ulke:<8} rec:{n_rec:2d} sim:{n_sim:2d}"
            )

            if done % SAVE_EVERY == 0 or done == len(rows):
                sorted_results = sorted(results, key=lambda x: x["id"])
                report["diziler"] = sorted_results
                report["ozet"] = {"toplam": total_all, "tamamlanan": tamam, **counts}
                report["guncelleme"] = datetime.now().isoformat()
                save_report(report)
                log(f"          💾 Ara kayıt ({tamam}/{total_all})")

    sorted_results = sorted(results, key=lambda x: x["id"])
    report["diziler"] = sorted_results
    report["ozet"] = {"toplam": total_all, "tamamlanan": len(sorted_results), **recount(sorted_results)}
    report["guncelleme"] = datetime.now().isoformat()
    save_report(report)

    log("\n" + "=" * 70)
    log("📊 ÖZET")
    for k, v in report["ozet"].items():
        log(f"  {k}: {v}")
    log(f"💾 {OUTPUT_JSON}")
    log("   DB'ye henüz yazılmadı.")
    log("=" * 70)


if __name__ == "__main__":
    main()
