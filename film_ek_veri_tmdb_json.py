# -*- coding: utf-8 -*-
"""
film_ek_veri_tmdb_json.py
-------------------------
Filmler için ek TMDB verilerini tek tarama + tek JSON'a çeker.
DB'ye yazmaz.

Alanlar (tek API çağrısı / film):
  - puan (vote_average)
  - oy_sayisi (vote_count)
  - orijinal_dil
  - yapim_ulkeleri
  - onerilen_idleri
  - benzer_idleri

Kaynak DB : diziler_veritabanı.db (filmler)
Çıktı     : film_ek_veri_tmdb_raporu.json

Kullanım:
    python film_ek_veri_tmdb_json.py --sadece-bos --workers 6
    python film_ek_veri_tmdb_json.py --sadece-bos --devam
    python film_ek_veri_tmdb_json.py --limit 20
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
DB_FILM = "katalog.db"
OUTPUT_JSON = "film_ek_veri_tmdb_raporu.json"
LANGUAGE = "tr-TR"
MAX_RETRIES = 3
SAVE_EVERY = 50

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


def fetch_extras(tmdb_id):
    data = safe_get(
        f"{BASE_URL}/movie/{tmdb_id}",
        {
            "api_key": API_KEY,
            "language": LANGUAGE,
            "append_to_response": "recommendations,similar",
        },
    )
    if not data:
        return None

    countries = [
        c.get("iso_3166_1")
        for c in (data.get("production_countries") or [])
        if c.get("iso_3166_1")
    ]
    recs = [
        item["id"]
        for item in (data.get("recommendations") or {}).get("results") or []
        if "id" in item
    ]
    sims = [
        item["id"]
        for item in (data.get("similar") or {}).get("results") or []
        if "id" in item
    ]

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

    return {
        "tmdb_name": data.get("title") or data.get("original_title"),
        "puan": puan,
        "oy_sayisi": oy,
        "orijinal_dil": data.get("original_language"),
        "yapim_ulkeleri": countries,
        "onerilen_idleri": recs,
        "benzer_idleri": sims,
    }


def process_item(row):
    item_id = row["id"]
    isim = row["isim"] or ""
    tmdb_id = row.get("tmdb_id")

    try:
        tmdb_id = int(tmdb_id) if tmdb_id not in (None, "") else None
    except (TypeError, ValueError):
        tmdb_id = None

    if not tmdb_id:
        return {
            "id": item_id,
            "isim": isim,
            "tmdb_id": None,
            "durum": "tmdb_id_yok",
            "puan": None,
            "oy_sayisi": None,
            "orijinal_dil": None,
            "yapim_ulkeleri": [],
            "onerilen_idleri": [],
            "benzer_idleri": [],
        }

    extras = fetch_extras(tmdb_id)
    if not extras:
        return {
            "id": item_id,
            "isim": isim,
            "tmdb_id": tmdb_id,
            "durum": "api_hatasi",
            "puan": None,
            "oy_sayisi": None,
            "orijinal_dil": None,
            "yapim_ulkeleri": [],
            "onerilen_idleri": [],
            "benzer_idleri": [],
        }

    return {
        "id": item_id,
        "isim": isim,
        "tmdb_id": tmdb_id,
        "durum": "ok",
        **extras,
    }


def load_rows(sadece_bos=False):
    conn = sqlite3.connect(DB_FILM)
    c = conn.cursor()
    if sadece_bos:
        c.execute("""
            SELECT id, tmdb_id, isim
            FROM filmler
            WHERE (puan IS NULL OR puan = 0)
               OR (oy_sayisi IS NULL OR oy_sayisi = 0)
               OR (yapim_ulkeleri IS NULL OR TRIM(COALESCE(yapim_ulkeleri,''))='' OR yapim_ulkeleri='[]')
               OR (orijinal_dil IS NULL OR TRIM(COALESCE(orijinal_dil,''))='')
               OR (onerilen_idleri IS NULL OR TRIM(COALESCE(onerilen_idleri,''))='' OR onerilen_idleri='[]')
               OR (benzer_idleri IS NULL OR TRIM(COALESCE(benzer_idleri,''))='' OR benzer_idleri='[]')
            ORDER BY id
        """)
    else:
        c.execute("SELECT id, tmdb_id, isim FROM filmler ORDER BY id")
    rows = [{"id": r[0], "tmdb_id": r[1], "isim": r[2]} for r in c.fetchall()]
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
                if os.path.exists(OUTPUT_JSON):
                    try:
                        os.replace(tmp, OUTPUT_JSON)
                    except (FileNotFoundError, PermissionError):
                        time.sleep(0.3 * attempt)
                        continue
                else:
                    os.replace(tmp, OUTPUT_JSON)
                return
            except (PermissionError, FileNotFoundError, OSError):
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
            "kaynak_db": DB_FILM,
            "alanlar": [
                "puan", "oy_sayisi", "orijinal_dil", "yapim_ulkeleri",
                "onerilen_idleri", "benzer_idleri",
            ],
            "ozet": {},
            "filmler": [],
        }
    else:
        report.setdefault("filmler", [])
        done_ids = {x["id"] for x in report["filmler"]}
        rows = [r for r in rows if r["id"] not in done_ids]
        log(f"⏩ Devam: {len(done_ids)} atlandı, {len(rows)} kaldı")

    existing = list(report.get("filmler") or [])
    total_all = len(existing) + len(rows)

    log("=" * 70)
    log("🎬 FİLM EK VERİ → JSON (TMDB tek çağrı)")
    log(f"   DB       : {DB_FILM}")
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
        futures = {ex.submit(process_item, row): row for row in rows}
        for fut in as_completed(futures):
            item = fut.result()
            results.append(item)
            d = item.get("durum") or "yok"
            counts[d] = counts.get(d, 0) + 1
            done += 1
            tamam = len(existing) + done

            mark = "✅" if d == "ok" else "❌"
            dil = item.get("orijinal_dil") or "-"
            ulke = ",".join(item.get("yapim_ulkeleri") or []) or "-"
            puan = item.get("puan")
            oy = item.get("oy_sayisi")
            n_rec = len(item.get("onerilen_idleri") or [])
            n_sim = len(item.get("benzer_idleri") or [])
            log(
                f"[{tamam:4d}/{total_all}] {mark} {str(item.get('isim') or '')[:32]:<32} "
                f"★{puan if puan is not None else '-':>5} oy:{oy if oy is not None else '-':>6} "
                f"{dil:>3} {ulke:<10} r:{n_rec:2d} s:{n_sim:2d}"
            )

            if done % SAVE_EVERY == 0 or done == len(rows):
                sorted_results = sorted(results, key=lambda x: x["id"])
                report["filmler"] = sorted_results
                report["ozet"] = {"toplam": total_all, "tamamlanan": tamam, **counts}
                report["guncelleme"] = datetime.now().isoformat()
                save_report(report)
                log(f"          💾 Ara kayıt ({tamam}/{total_all})")

    sorted_results = sorted(results, key=lambda x: x["id"])
    report["filmler"] = sorted_results
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
