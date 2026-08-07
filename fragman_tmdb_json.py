# -*- coding: utf-8 -*-
"""
fragman_tmdb_json.py - TMDB Fragman Tarayıcı (JSON çıktı, DB'ye yazmaz)
---------------------------------------------------------------------
Diziler  → diziler_veritabani.db
Filmler  → diziler_veritabanı.db

Her kayıt için:
  1) Türkçe fragman (tr-TR)
  2) Yoksa / ayrıca orijinal fragman (en-US)
  3) İkisi de yoksa boş bırakılır

Sonuç: fragman_tmdb_raporu.json
Veritabanına aktarım ayrı adımda yapılır.

Kullanım:
    python fragman_tmdb_json.py
    python fragman_tmdb_json.py --tip dizi
    python fragman_tmdb_json.py --tip film --limit 100
    python fragman_tmdb_json.py --workers 8
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
OUTPUT_JSON = "fragman_tmdb_raporu.json"
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
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 10))
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


def youtube_embed(key):
    if not key:
        return None
    return f"https://www.youtube.com/embed/{key}"


def pick_best_video(results):
    """Trailer > Teaser, official tercih, YouTube only."""
    if not results:
        return None

    candidates = [
        v for v in results
        if v.get("site") == "YouTube"
        and v.get("type") in ("Trailer", "Teaser")
        and v.get("key")
    ]
    if not candidates:
        return None

    def score(v):
        s = 0
        if v.get("type") == "Trailer":
            s += 10
        if v.get("official"):
            s += 5
        s += min(int(v.get("size") or 0) / 200, 5)
        return s

    best = max(candidates, key=score)
    return {
        "key": best.get("key"),
        "name": best.get("name"),
        "type": best.get("type"),
        "official": bool(best.get("official")),
        "iso_639_1": best.get("iso_639_1"),
        "url": youtube_embed(best.get("key")),
    }


def fetch_videos(media_type, tmdb_id, language):
    endpoint = "tv" if media_type == "dizi" else "movie"
    data = safe_get(
        f"{BASE_URL}/{endpoint}/{tmdb_id}/videos",
        {"api_key": API_KEY, "language": language},
    )
    if not data:
        return None
    return pick_best_video(data.get("results") or [])


def _norm_title(text):
    if not text:
        return ""
    t = str(text).lower()
    for ch in (":", "-", "'", '"', ".", ",", "!", "?", "(", ")", "[", "]"):
        t = t.replace(ch, " ")
    return " ".join(t.split())


def _title_tokens(text):
    stop = {"the", "a", "an", "and", "of", "ve", "ile", "bir", "series", "dizi", "tv"}
    return [w for w in _norm_title(text).split() if len(w) > 1 and w not in stop]


def title_similarity(query, candidate):
    """Jaccard benzerliği — Mother/Father, Avatar remake karışmasını engeller."""
    q = set(_title_tokens(query))
    c = set(_title_tokens(candidate))
    if not q or not c:
        return 0.0
    return len(q & c) / len(q | c)


def pick_best_search_result(media_type, isim, results, yil=""):
    """Yıl + başlık benzerliği ile en doğru TMDB sonucunu seç."""
    if not results:
        return None

    date_key = "first_air_date" if media_type == "dizi" else "release_date"
    name_key = "name" if media_type == "dizi" else "title"
    orig_key = "original_name" if media_type == "dizi" else "original_title"
    yil4 = str(yil)[:4] if yil and str(yil)[:4].isdigit() else ""
    q_norm = _norm_title(isim)

    scored = []
    for item in results:
        name = item.get(name_key) or ""
        orig = item.get(orig_key) or ""
        sim = max(title_similarity(isim, name), title_similarity(isim, orig))
        # Tam eşleşme bonusu
        if _norm_title(name) == q_norm or _norm_title(orig) == q_norm:
            sim = max(sim, 1.0)

        date = item.get(date_key) or ""
        year_ok = bool(yil4 and date.startswith(yil4))
        year_close = False
        if yil4 and date[:4].isdigit():
            year_close = abs(int(date[:4]) - int(yil4)) <= 1

        score = sim * 100
        if year_ok:
            score += 25
        elif year_close:
            score += 8
        elif yil4 and date[:4].isdigit():
            # Farklı yıl cezası (2005 animasyon vs 2024 remake)
            score -= min(abs(int(date[:4]) - int(yil4)), 20)

        scored.append((score, sim, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_sim, best = scored[0]

    # Çok zayıf eşleşme → red (yanlış yapım riski)
    if best_sim < 0.45 and best_score < 55:
        return None
    return best.get("id")


def search_tmdb_id(media_type, isim, yil=""):
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
    results = (data.get("results") or []) if data else []

    # Yıl filtresi boş dönerse filtresiz dene, ama yine benzerlikle seç
    if not results and yil:
        params.pop("first_air_date_year", None)
        params.pop("primary_release_year", None)
        data = safe_get(f"{BASE_URL}/search/{endpoint}", params)
        results = (data.get("results") or []) if data else []

    if not results:
        return None

    return pick_best_search_result(media_type, isim, results, yil)


def resolve_trailers(media_type, tmdb_id):
    """TR önce, sonra orijinal (en-US)."""
    tr = fetch_videos(media_type, tmdb_id, "tr-TR")
    orig = fetch_videos(media_type, tmdb_id, "en-US")

    # Aynı video iki kez gelmesin
    if tr and orig and tr.get("key") == orig.get("key"):
        # TR sonuç aslında İngilizce olabilir; dil koduna bak
        if (tr.get("iso_639_1") or "").lower() != "tr":
            orig = tr
            tr = None

    trailer_tr = tr.get("url") if tr else None
    trailer_orig = orig.get("url") if orig else None

    if trailer_tr and trailer_orig:
        durum = "tr_ve_orijinal"
    elif trailer_tr:
        durum = "sadece_tr"
    elif trailer_orig:
        durum = "sadece_orijinal"
    else:
        durum = "yok"

    return trailer_tr, trailer_orig, durum


def process_item(media_type, row):
    item_id = row["id"]
    isim = row["isim"] or ""
    yil = row.get("yil") or ""
    tmdb_id = row.get("tmdb_id")

    if tmdb_id:
        try:
            tmdb_id = int(tmdb_id)
        except (TypeError, ValueError):
            tmdb_id = None

    if not tmdb_id:
        tmdb_id = search_tmdb_id(media_type, isim, yil)

    if not tmdb_id:
        return {
            "id": item_id,
            "isim": isim,
            "yil": yil,
            "tmdb_id": None,
            "trailer_tr": None,
            "trailer_original": None,
            "durum": "tmdb_bulunamadi",
        }

    trailer_tr, trailer_orig, durum = resolve_trailers(media_type, tmdb_id)
    return {
        "id": item_id,
        "isim": isim,
        "yil": yil,
        "tmdb_id": tmdb_id,
        "trailer_tr": trailer_tr,
        "trailer_original": trailer_orig,
        "durum": durum,
    }


def load_rows(media_type):
    if media_type == "dizi":
        if not os.path.exists(DB_DIZI):
            raise FileNotFoundError(DB_DIZI)
        conn = sqlite3.connect(DB_DIZI)
        c = conn.cursor()
        # Dizilerde PK genelde TMDB id'sidir — isim aramasına düşmeden doğrudan kullan
        c.execute("SELECT id, isim, cikis_tarihi FROM diziler ORDER BY id")
        rows = [
            {
                "id": r[0],
                "isim": r[1],
                "yil": (r[2] or "")[:4],
                "tmdb_id": r[0],  # dizi id = tmdb id
            }
            for r in c.fetchall()
        ]
        conn.close()
        return rows

    if not os.path.exists(DB_FILM):
        raise FileNotFoundError(DB_FILM)
    conn = sqlite3.connect(DB_FILM)
    c = conn.cursor()
    c.execute("SELECT id, tmdb_id, isim, vizyon_tarihi FROM filmler ORDER BY id")
    rows = [
        {"id": r[0], "tmdb_id": r[1], "isim": r[2], "yil": (r[3] or "")[:4]}
        for r in c.fetchall()
    ]
    conn.close()
    return rows


def save_report(data):
    """Windows'ta dosya açıksa PermissionError olabilir → birkaç kez dene."""
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
                time.sleep(0.5 * attempt)
            except Exception:
                time.sleep(0.5 * attempt)
        # Son çare: alternatif dosya adı
        alt = OUTPUT_JSON.replace(".json", f"_yedek_{int(time.time())}.json")
        with open(alt, "w", encoding="utf-8") as f:
            f.write(payload)
        log(f"⚠️ Ana JSON kilitli, yedek yazıldı: {alt}")


def load_existing_report():
    if not os.path.exists(OUTPUT_JSON):
        return None
    try:
        with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def recount(items):
    counts = {
        "tr_ve_orijinal": 0,
        "sadece_tr": 0,
        "sadece_orijinal": 0,
        "yok": 0,
        "tmdb_bulunamadi": 0,
    }
    for item in items:
        d = item.get("durum")
        if d in counts:
            counts[d] += 1
    return counts


def scan_tip(media_type, workers=8, limit=None, report=None, devam=False):
    label = "DİZİ" if media_type == "dizi" else "FİLM"
    emoji = "📺" if media_type == "dizi" else "🎬"
    key = "diziler" if media_type == "dizi" else "filmler"

    rows = load_rows(media_type)
    if limit:
        rows = rows[:limit]

    existing = list(report.get(key) or []) if devam else []
    done_ids = {item["id"] for item in existing}
    if devam and done_ids:
        rows = [r for r in rows if r["id"] not in done_ids]
        log(f"⏩ Kaldığı yerden: {len(done_ids)} kayıt atlandı, {len(rows)} kaldı")

    total_all = len(existing) + len(rows)
    total = len(rows)
    log(f"\n{'=' * 70}")
    log(f"{emoji} {label} FRAGMAN TARAMASI (JSON)")
    log(f"   Kaynak DB : {DB_DIZI if media_type == 'dizi' else DB_FILM}")
    log(f"   Toplam    : {total_all} (bu tur: {total})")
    log(f"   Workers   : {workers}")
    log(f"{'=' * 70}\n")

    results = list(existing)
    counts = recount(results)
    done = 0

    if total == 0:
        log(f"✅ {label}: taranacak yeni kayıt yok.")
        report[key] = sorted(results, key=lambda x: x["id"])
        report["ozet"][key] = {"toplam": total_all, "tamamlanan": total_all, **counts}
        report["guncelleme"] = datetime.now().isoformat()
        save_report(report)
        return report

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(process_item, media_type, row): row for row in rows}
        for fut in as_completed(futures):
            item = fut.result()
            results.append(item)
            counts[item["durum"]] = counts.get(item["durum"], 0) + 1
            done += 1
            tamam = len(existing) + done

            durum = item["durum"]
            if durum in ("tr_ve_orijinal", "sadece_tr"):
                mark = "✅ TR"
            elif durum == "sadece_orijinal":
                mark = "🌐 ORJ"
            elif durum == "tmdb_bulunamadi":
                mark = "⚠️  ID yok"
            else:
                mark = "❌ yok"

            log(f"[{tamam:4d}/{total_all}] {emoji} {str(item['isim'])[:40]:<40} {mark}")

            if done % SAVE_EVERY == 0 or done == total:
                sorted_results = sorted(results, key=lambda x: x["id"])
                report[key] = sorted_results
                report["ozet"][key] = {
                    "toplam": total_all,
                    "tamamlanan": tamam,
                    **counts,
                }
                report["guncelleme"] = datetime.now().isoformat()
                save_report(report)
                log(f"          💾 Ara kayıt: {OUTPUT_JSON} ({tamam}/{total_all})")

    sorted_results = sorted(results, key=lambda x: x["id"])
    report[key] = sorted_results
    report["ozet"][key] = {
        "toplam": total_all,
        "tamamlanan": len(sorted_results),
        **counts,
    }
    report["guncelleme"] = datetime.now().isoformat()
    save_report(report)

    log(f"\n📊 {label} ÖZET")
    log(f"  ✅ TR + orijinal     : {counts.get('tr_ve_orijinal', 0)}")
    log(f"  ✅ Sadece TR         : {counts.get('sadece_tr', 0)}")
    log(f"  🌐 Sadece orijinal   : {counts.get('sadece_orijinal', 0)}")
    log(f"  ❌ Fragman yok       : {counts.get('yok', 0)}")
    log(f"  ⚠️  TMDB bulunamadı  : {counts.get('tmdb_bulunamadi', 0)}")
    return report


def main():
    parser = argparse.ArgumentParser(description="TMDB fragmanlarını JSON'a yazar (DB'ye yazmaz).")
    parser.add_argument("--tip", choices=["dizi", "film", "hepsi"], default="hepsi")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--devam",
        action="store_true",
        help="Mevcut JSON'daki kayıtları atlayıp kaldığı yerden devam eder.",
    )
    args = parser.parse_args()

    if args.devam:
        report = load_existing_report()
        if not report:
            report = None
        if report is None:
            log("⚠️ Devam edilecek JSON yok, sıfırdan başlanıyor.")
            args.devam = False

    if not args.devam:
        report = {
            "olusturulma": datetime.now().isoformat(),
            "guncelleme": datetime.now().isoformat(),
            "not": "DB'ye yazılmadı. Aktarım ayrı adımda yapılacak.",
            "kaynaklar": {
                "diziler": DB_DIZI,
                "filmler": DB_FILM,
            },
            "ozet": {},
            "diziler": [],
            "filmler": [],
        }
        save_report(report)
    else:
        report.setdefault("ozet", {})
        report.setdefault("diziler", [])
        report.setdefault("filmler", [])
        log(f"⏩ Devam: diziler={len(report.get('diziler') or [])}, filmler={len(report.get('filmler') or [])}")

    log("=" * 70)
    log("🎬 TMDB FRAGMAN → JSON TARAYICI")
    log(f"   Tip     : {args.tip}")
    log(f"   Çıktı   : {OUTPUT_JSON}")
    log(f"   Devam   : {'Evet' if args.devam else 'Hayır'}")
    log(f"   DB yazma: KAPALI")
    log("=" * 70)

    if args.tip in ("dizi", "hepsi"):
        scan_tip("dizi", workers=args.workers, limit=args.limit, report=report, devam=args.devam)
    if args.tip in ("film", "hepsi"):
        scan_tip("film", workers=args.workers, limit=args.limit, report=report, devam=args.devam)

    log("\n" + "=" * 70)
    log(f"✅ Bitti. Sonuç dosyası: {OUTPUT_JSON}")
    log("   Veritabanına henüz yazılmadı.")
    log("=" * 70)


if __name__ == "__main__":
    main()
