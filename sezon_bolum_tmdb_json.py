# -*- coding: utf-8 -*-
"""
sezon_bolum_tmdb_json.py
------------------------
Dizilerin sezon_bolum_haritasi bilgisini TMDB'den çeker, JSON'a yazar.
Veritabanına YAZMAZ (aktarım ayrı adım).

Kaynak DB : diziler_veritabani.db
Çıktı     : sezon_bolum_tmdb_raporu.json

Harita formatı: "16,22,21,16,18,22,13"  (sezon başına bölüm; specials/0 hariç)

Kullanım:
    python sezon_bolum_tmdb_json.py
    python sezon_bolum_tmdb_json.py --workers 6
    python sezon_bolum_tmdb_json.py --devam
    python sezon_bolum_tmdb_json.py --sadece-bos   # DB'de haritası boş olanlar
    python sezon_bolum_tmdb_json.py --api-key XXX
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

# Fragman taraması bitti → aynı ana key ile devam
DEFAULT_API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"
DB_DIZI = "katalog.db"
OUTPUT_JSON = "sezon_bolum_tmdb_raporu.json"
LANGUAGE = "tr-TR"
MAX_RETRIES = 3
SAVE_EVERY = 40

print_lock = Lock()
file_lock = Lock()
API_KEY = DEFAULT_API_KEY


def log(msg):
    with print_lock:
        print(msg, flush=True)


def safe_get(url, params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=20)
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


def fetch_season_map(tmdb_id):
    """
    TMDB TV detayından sezon başına bölüm sayısı.
    season_number == 0 (specials) atlanır.
    """
    data = safe_get(
        f"{BASE_URL}/tv/{tmdb_id}",
        {"api_key": API_KEY, "language": LANGUAGE},
    )
    if not data:
        return None, "api_hatasi"

    seasons = data.get("seasons") or []
    counts = []
    for s in seasons:
        sn = s.get("season_number")
        if sn is None or int(sn) == 0:
            continue
        ep = s.get("episode_count")
        if ep is None:
            continue
        counts.append(int(ep))

    if not counts:
        # seasons boşsa genel sayılara düş
        ns = int(data.get("number_of_seasons") or 0)
        ne = int(data.get("number_of_episodes") or 0)
        if ns > 0 and ne > 0:
            # eşit dağıtma yerine tek sezon toplamı yazma — belirsiz
            return {
                "sezon_sayisi": ns,
                "toplam_bolum_sayisi": ne,
                "sezon_bolum_haritasi": None,
                "tmdb_name": data.get("name"),
            }, "harita_yok"

        return None, "harita_yok"

    harita = ",".join(str(x) for x in counts)
    return {
        "sezon_sayisi": len(counts),
        "toplam_bolum_sayisi": sum(counts),
        "sezon_bolum_haritasi": harita,
        "tmdb_name": data.get("name"),
        "number_of_seasons_tmdb": data.get("number_of_seasons"),
        "number_of_episodes_tmdb": data.get("number_of_episodes"),
    }, "ok"


def process_item(row):
    item_id = row["id"]
    isim = row["isim"] or ""
    yil = row.get("yil") or ""
    db_harita = row.get("db_harita")
    db_sezon = row.get("db_sezon")
    db_bolum = row.get("db_bolum")

    tmdb_id = search_tv_id(isim, yil)
    if not tmdb_id:
        return {
            "id": item_id,
            "isim": isim,
            "yil": yil,
            "tmdb_id": None,
            "db_sezon_bolum_haritasi": db_harita,
            "db_sezon_sayisi": db_sezon,
            "db_toplam_bolum_sayisi": db_bolum,
            "sezon_sayisi": None,
            "toplam_bolum_sayisi": None,
            "sezon_bolum_haritasi": None,
            "durum": "tmdb_bulunamadi",
        }

    meta, durum = fetch_season_map(tmdb_id)
    if not meta:
        return {
            "id": item_id,
            "isim": isim,
            "yil": yil,
            "tmdb_id": tmdb_id,
            "db_sezon_bolum_haritasi": db_harita,
            "db_sezon_sayisi": db_sezon,
            "db_toplam_bolum_sayisi": db_bolum,
            "sezon_sayisi": None,
            "toplam_bolum_sayisi": None,
            "sezon_bolum_haritasi": None,
            "durum": durum,
        }

    return {
        "id": item_id,
        "isim": isim,
        "yil": yil,
        "tmdb_id": tmdb_id,
        "tmdb_name": meta.get("tmdb_name"),
        "db_sezon_bolum_haritasi": db_harita,
        "db_sezon_sayisi": db_sezon,
        "db_toplam_bolum_sayisi": db_bolum,
        "sezon_sayisi": meta.get("sezon_sayisi"),
        "toplam_bolum_sayisi": meta.get("toplam_bolum_sayisi"),
        "sezon_bolum_haritasi": meta.get("sezon_bolum_haritasi"),
        "durum": durum,
    }


def load_rows(sadece_bos=False):
    if not os.path.exists(DB_DIZI):
        raise FileNotFoundError(DB_DIZI)
    conn = sqlite3.connect(DB_DIZI)
    c = conn.cursor()
    if sadece_bos:
        c.execute(
            "SELECT id, isim, cikis_tarihi, sezon_sayisi, toplam_bolum_sayisi, sezon_bolum_haritasi "
            "FROM diziler WHERE sezon_bolum_haritasi IS NULL "
            "OR TRIM(COALESCE(sezon_bolum_haritasi,'')) = '' ORDER BY id"
        )
    else:
        c.execute(
            "SELECT id, isim, cikis_tarihi, sezon_sayisi, toplam_bolum_sayisi, sezon_bolum_haritasi "
            "FROM diziler ORDER BY id"
        )
    rows = [
        {
            "id": r[0],
            "isim": r[1],
            "yil": (r[2] or "")[:4],
            "db_sezon": r[3],
            "db_bolum": r[4],
            "db_harita": r[5],
        }
        for r in c.fetchall()
    ]
    conn.close()
    return rows


def save_report(data):
    with file_lock:
        tmp = OUTPUT_JSON + ".tmp"
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        for attempt in range(1, 8):
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(payload)
                os.replace(tmp, OUTPUT_JSON)
                return
            except PermissionError:
                time.sleep(0.4 * attempt)
        alt = OUTPUT_JSON.replace(".json", f"_yedek_{int(time.time())}.json")
        with open(alt, "w", encoding="utf-8") as f:
            f.write(payload)
        log(f"⚠️ Ana JSON kilitli, yedek: {alt}")


def load_existing():
    if not os.path.exists(OUTPUT_JSON):
        return None
    try:
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
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
    parser = argparse.ArgumentParser(description="TMDB sezon/bölüm haritasını JSON'a yazar.")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--devam", action="store_true")
    parser.add_argument("--sadece-bos", action="store_true", help="Sadece DB'de haritası boş diziler")
    parser.add_argument("--api-key", type=str, default=None)
    args = parser.parse_args()

    if args.api_key:
        API_KEY = args.api_key.strip()

    rows = load_rows(sadece_bos=args.sadece_bos)
    if args.limit:
        rows = rows[: args.limit]

    if args.devam:
        report = load_existing()
        if not report:
            log("⚠️ Devam edilecek JSON yok, sıfırdan.")
            args.devam = False

    if not args.devam:
        report = {
            "olusturulma": datetime.now().isoformat(),
            "guncelleme": datetime.now().isoformat(),
            "not": "DB'ye yazılmadı. Aktarım ayrı adımda.",
            "kaynak_db": DB_DIZI,
            "ozet": {},
            "diziler": [],
        }
    else:
        report.setdefault("diziler", [])
        report.setdefault("ozet", {})
        done_ids = {x["id"] for x in report["diziler"]}
        before = len(rows)
        rows = [r for r in rows if r["id"] not in done_ids]
        log(f"⏩ Devam: {len(done_ids)} atlandı, {len(rows)} kaldı (önce {before})")

    existing = list(report.get("diziler") or [])
    total_all = len(existing) + len(rows)

    log("=" * 70)
    log("📺 SEZON / BÖLÜM HARİTASI → JSON (TMDB)")
    log(f"   DB      : {DB_DIZI}")
    log(f"   Çıktı   : {OUTPUT_JSON}")
    log(f"   Toplam  : {total_all} (bu tur: {len(rows)})")
    log(f"   Workers : {args.workers}")
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
        futures = {ex.submit(process_item, row): row for row in rows}
        for fut in as_completed(futures):
            item = fut.result()
            results.append(item)
            d = item.get("durum") or "yok"
            counts[d] = counts.get(d, 0) + 1
            done += 1
            tamam = len(existing) + done

            harita = item.get("sezon_bolum_haritasi") or "-"
            mark = "✅" if d == "ok" else ("⚠️" if d == "tmdb_bulunamadi" else "❌")
            log(
                f"[{tamam:4d}/{total_all}] {mark} {str(item.get('isim') or '')[:38]:<38} "
                f"S:{item.get('sezon_sayisi') or '-'} B:{item.get('toplam_bolum_sayisi') or '-'} "
                f"| {harita[:40]}"
            )

            if done % SAVE_EVERY == 0 or done == len(rows):
                sorted_results = sorted(results, key=lambda x: x["id"])
                report["diziler"] = sorted_results
                report["ozet"] = {
                    "toplam": total_all,
                    "tamamlanan": tamam,
                    **counts,
                }
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
