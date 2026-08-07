# -*- coding: utf-8 -*-
"""
dizi_fragman_tmdb_senkron.py
----------------------------
Dizi fragmanlarını TMDB odaklı senkronlar (Mother/Father, Avatar remake karışmasını önler).

Akış:
  1) DB id → TMDB tv kaydı; isim uyuşmuyorsa isim+yıl araması
  2) /tv/{id}/videos (tr-TR + en-US)
  3) Video başlığı dizi adıyla sıkı eşleşmezse reddet
  4) TMDB'de fragman yoksa: eski/_eski_ YouTube linki başlık doğrularsa KORU
  5) Yanlış spinoff/remake (Father, Netflix Avatar 2005 vb.) yine silinir

Kullanım:
    python dizi_fragman_tmdb_senkron.py --export
    python dizi_fragman_tmdb_senkron.py --limit 50 --sadece-denetle
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
from urllib.parse import quote
from urllib.request import Request, urlopen

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"
DB_DIZI = "katalog.db"
REPORT_JSON = "dizi_fragman_senkron_raporu.json"
MAX_RETRIES = 3

print_lock = Lock()
STOP_WORDS = {
    "the", "a", "an", "and", "of", "ve", "ile", "bir", "series", "dizi", "tv",
    "official", "trailer", "fragman", "fragmanı", "season", "sezon",
}

HARD_BANS = [
    (re.compile(r"met your mother", re.I), re.compile(r"\bfather\b", re.I), "HIMYF spinoff"),
    (re.compile(r"met your father", re.I), re.compile(r"\bmother\b", re.I), "HIMYM karışması"),
    (
        re.compile(r"son havabük|last airbender", re.I),
        re.compile(r"netflix|live[\s-]?action|202[4-9]", re.I),
        "Avatar Netflix remake",
    ),
]


def log(msg: str):
    with print_lock:
        print(msg, flush=True)


def safe_get(url, params=None):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 8)) + 1)
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


def youtube_embed(key: str | None):
    if not key:
        return None
    return f"https://www.youtube.com/embed/{key}"


def extract_yt_key(url: str | None):
    if not url:
        return None
    m = re.search(r"(?:embed/|v=|youtu\.be/)([A-Za-z0-9_-]{6,})", str(url))
    return m.group(1) if m else None


def norm_tokens(text: str):
    t = re.sub(r"[^\w\s]", " ", (text or "").lower(), flags=re.UNICODE)
    return [w for w in t.split() if len(w) > 1 and w not in STOP_WORDS]


def title_ok(show_title: str, video_title: str, show_year: str = "") -> tuple[bool, str]:
    if not video_title:
        return False, "video başlığı yok"
    if not show_title:
        return False, "dizi adı yok"

    st = show_title.lower()
    vt = video_title.lower()

    for show_re, ban_re, reason in HARD_BANS:
        if show_re.search(st) and ban_re.search(vt):
            if "Avatar Netflix" in reason:
                if show_year and show_year.startswith("200"):
                    return False, reason
            else:
                return False, reason

    words = norm_tokens(show_title)
    if not words:
        return True, "ok"
    hits = sum(1 for w in words if w in vt)
    need = max(2, (len(words) + 1) // 2) if len(words) >= 2 else 1
    if hits < need:
        return False, f"başlık uyuşmazlığı ({hits}/{len(words)})"

    last = words[-1]
    if len(last) > 3 and last not in vt:
        return False, f"kritik kelime eksik: {last}"
    return True, "ok"


def oembed_title(yt_key: str) -> str | None:
    if not yt_key:
        return None
    try:
        url = f"https://www.youtube.com/oembed?url={quote('https://www.youtube.com/watch?v=' + yt_key)}&format=json"
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            return (data.get("title") or "").strip() or None
    except Exception:
        return None


def pick_best_video(results):
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
        "name": best.get("name") or "",
        "url": youtube_embed(best.get("key")),
        "iso": (best.get("iso_639_1") or "").lower(),
    }


def fetch_best(tmdb_id: int, language: str):
    data = safe_get(
        f"{BASE_URL}/tv/{tmdb_id}/videos",
        {"api_key": API_KEY, "language": language},
    )
    if not data:
        return None
    return pick_best_video(data.get("results") or [])


def jaccard(a: str, b: str) -> float:
    sa, sb = set(norm_tokens(a)), set(norm_tokens(b))
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def titles_match_show(db_title: str, tmdb_name: str, tmdb_orig: str) -> bool:
    if not db_title:
        return False
    sim = max(jaccard(db_title, tmdb_name or ""), jaccard(db_title, tmdb_orig or ""))
    ok1, _ = title_ok(db_title, tmdb_name or "")
    ok2, _ = title_ok(db_title, tmdb_orig or "")
    return ok1 or ok2 or sim >= 0.55


def search_tmdb_id(isim: str, yil: str = ""):
    params = {
        "api_key": API_KEY,
        "language": "tr-TR",
        "query": isim,
        "include_adult": "false",
    }
    if yil and yil.isdigit():
        params["first_air_date_year"] = yil
    data = safe_get(f"{BASE_URL}/search/tv", params) or {}
    results = data.get("results") or []
    if not results and yil:
        params.pop("first_air_date_year", None)
        data = safe_get(f"{BASE_URL}/search/tv", params) or {}
        results = data.get("results") or []
    if not results:
        return None

    scored = []
    for item in results:
        name = item.get("name") or ""
        orig = item.get("original_name") or ""
        sim = max(jaccard(isim, name), jaccard(isim, orig))
        date = item.get("first_air_date") or ""
        bonus = 0.25 if yil and date.startswith(yil) else 0.0
        if yil and date[:4].isdigit() and not date.startswith(yil):
            bonus -= min(abs(int(date[:4]) - int(yil)), 15) * 0.02
        scored.append((sim + bonus, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    best_sim, best = scored[0]
    if best_sim < 0.4:
        return None
    return best.get("id")


def resolve_tmdb_id(db_id: int, show_title: str, show_year: str):
    for lang in ("tr-TR", "en-US"):
        data = safe_get(f"{BASE_URL}/tv/{db_id}", {"api_key": API_KEY, "language": lang})
        if data and titles_match_show(show_title, data.get("name") or "", data.get("original_name") or ""):
            return int(db_id), "db-id"
    found = search_tmdb_id(show_title, show_year)
    if found:
        return int(found), "search"
    return None, "bulunamadi"


def keep_existing_if_valid(url: str | None, show_title: str, show_year: str):
    key = extract_yt_key(url)
    if not key:
        return None
    yt_title = oembed_title(key)
    ok, _ = title_ok(show_title, yt_title or "", show_year)
    if ok:
        return youtube_embed(key)
    return None


def resolve_for_show(
    tmdb_id: int | None,
    show_title: str,
    show_year: str,
    old_tr=None,
    old_orig=None,
    eski_tr=None,
    eski_orig=None,
):
    tr = fetch_best(tmdb_id, "tr-TR") if tmdb_id else None
    orig = fetch_best(tmdb_id, "en-US") if tmdb_id else None

    if tr and orig and tr.get("key") == orig.get("key"):
        if tr.get("iso") != "tr":
            orig = tr
            tr = None

    def accept(vid):
        if not vid:
            return None, "yok"
        ok, reason = title_ok(show_title, vid.get("name") or "", show_year)
        if ok:
            return vid, "ok-tmdb-name"
        yt_title = oembed_title(vid.get("key"))
        ok2, reason2 = title_ok(show_title, yt_title or "", show_year)
        if not ok2:
            return None, reason2 or reason
        return vid, "ok-oembed"

    tr_ok, tr_reason = accept(tr)
    orig_ok, orig_reason = accept(orig)

    trailer_tr = tr_ok.get("url") if tr_ok else None
    trailer_orig = orig_ok.get("url") if orig_ok else None

    # TMDB boşsa: doğrulanmış eski YouTube'u koru (yanlış spinoff yine elenir)
    if not trailer_tr:
        for cand in (old_tr, eski_tr):
            kept = keep_existing_if_valid(cand, show_title, show_year)
            if kept:
                trailer_tr = kept
                tr_reason = "korundu-eski"
                break
    if not trailer_orig:
        for cand in (old_orig, eski_orig):
            kept = keep_existing_if_valid(cand, show_title, show_year)
            if kept:
                trailer_orig = kept
                orig_reason = "korundu-eski"
                break

    return {
        "tmdb_id": tmdb_id,
        "trailer_tr": trailer_tr,
        "trailer_original": trailer_orig,
        "tr_reason": tr_reason,
        "orig_reason": orig_reason,
        "tr_name": (tr_ok.get("name") if tr_ok else None),
        "orig_name": (orig_ok.get("name") if orig_ok else None),
    }


def load_rows(limit=None):
    conn = sqlite3.connect(DB_DIZI)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(diziler)")}
    has_eski = "_eski_trailer_tr_url" in cols and "_eski_trailer_original_url" in cols
    if has_eski:
        sql = """SELECT id, isim, cikis_tarihi, trailer_tr_url, trailer_original_url,
                        _eski_trailer_tr_url, _eski_trailer_original_url
                 FROM diziler ORDER BY id"""
    else:
        sql = """SELECT id, isim, cikis_tarihi, trailer_tr_url, trailer_original_url
                 FROM diziler ORDER BY id"""
    rows = []
    for r in conn.execute(sql):
        rows.append({
            "id": r[0],
            "isim": r[1] or "",
            "yil": (r[2] or "")[:4],
            "old_tr": r[3],
            "old_orig": r[4],
            "eski_tr": r[5] if has_eski else None,
            "eski_orig": r[6] if has_eski else None,
        })
    conn.close()
    if limit:
        rows = rows[:limit]
    return rows


def process_row(row):
    tmdb_id, id_src = resolve_tmdb_id(int(row["id"]), row["isim"], row["yil"])
    resolved = resolve_for_show(
        tmdb_id,
        row["isim"],
        row["yil"],
        old_tr=row.get("old_tr"),
        old_orig=row.get("old_orig"),
        eski_tr=row.get("eski_tr"),
        eski_orig=row.get("eski_orig"),
    )
    return {
        "id": row["id"],
        "isim": row["isim"],
        "yil": row["yil"],
        "old_tr": row["old_tr"],
        "old_orig": row["old_orig"],
        "id_kaynak": id_src,
        **resolved,
    }


def apply_to_db(results):
    conn = sqlite3.connect(DB_DIZI, timeout=120)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(diziler)")}
    for col in ("_eski_trailer_tr_url", "_eski_trailer_original_url"):
        if col not in cols:
            conn.execute(f"ALTER TABLE diziler ADD COLUMN {col} TEXT")

    changed = cleared = same = 0
    for item in results:
        db_id = item["id"]
        # Not: _eski_ zaten önceki turda doldu; üzerine boş yazma
        new_tr = item.get("trailer_tr")
        new_orig = item.get("trailer_original")
        old_tr = item.get("old_tr")
        old_orig = item.get("old_orig")

        conn.execute(
            "UPDATE diziler SET trailer_tr_url = ?, trailer_original_url = ? WHERE id = ?",
            (new_tr, new_orig, db_id),
        )
        if (new_tr or "") == (old_tr or "") and (new_orig or "") == (old_orig or ""):
            same += 1
        else:
            changed += 1
        if not new_tr and not new_orig:
            cleared += 1

    conn.commit()
    conn.close()
    return changed, cleared, same


def main():
    parser = argparse.ArgumentParser(description="Dizi fragmanlarını TMDB ile senkronla")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--sadece-denetle", action="store_true")
    args = parser.parse_args()

    rows = load_rows(args.limit)
    total = len(rows)
    log("=" * 70)
    log("📺 DİZİ FRAGMAN TMDB SENKRON v2")
    log(f"   Kayıt   : {total}")
    log(f"   Workers : {args.workers}")
    log(f"   Yazma   : {'KAPALI' if args.sadece_denetle else 'AÇIK'}")
    log("=" * 70)

    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(process_row, row): row for row in rows}
        for fut in as_completed(futs):
            item = fut.result()
            results.append(item)
            done += 1
            has = "TR+ORJ" if item.get("trailer_tr") and item.get("trailer_original") else (
                "TR" if item.get("trailer_tr") else ("ORJ" if item.get("trailer_original") else "YOK")
            )
            changed = (
                (item.get("trailer_tr") or "") != (item.get("old_tr") or "")
                or (item.get("trailer_original") or "") != (item.get("old_orig") or "")
            )
            src = item.get("id_kaynak") or "?"
            mark = "↻" if changed else "="
            log(f"[{done:4d}/{total}] {mark} {str(item['isim'])[:38]:<38} {has:<7} ({src})")

    results.sort(key=lambda x: x["id"])
    suspicious = []
    for item in results:
        if (item.get("old_tr") or item.get("old_orig")) and (
            (item.get("trailer_tr") or "") != (item.get("old_tr") or "")
            or (item.get("trailer_original") or "") != (item.get("old_orig") or "")
        ):
            suspicious.append({
                "id": item["id"],
                "isim": item["isim"],
                "id_kaynak": item.get("id_kaynak"),
                "tmdb_id": item.get("tmdb_id"),
                "old_tr": item.get("old_tr"),
                "old_orig": item.get("old_orig"),
                "new_tr": item.get("trailer_tr"),
                "new_orig": item.get("trailer_original"),
                "tr_reason": item.get("tr_reason"),
                "orig_reason": item.get("orig_reason"),
            })

    report = {
        "olusturulma": datetime.now().isoformat(),
        "toplam": total,
        "degisecek": len(suspicious),
        "ozet": {
            "tr_ve_orijinal": sum(1 for x in results if x.get("trailer_tr") and x.get("trailer_original")),
            "sadece_tr": sum(1 for x in results if x.get("trailer_tr") and not x.get("trailer_original")),
            "sadece_orijinal": sum(1 for x in results if x.get("trailer_original") and not x.get("trailer_tr")),
            "yok": sum(1 for x in results if not x.get("trailer_tr") and not x.get("trailer_original")),
            "search_id": sum(1 for x in results if x.get("id_kaynak") == "search"),
        },
        "degisenler": suspicious[:500],
        "diziler": results,
    }
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"\n💾 Rapor: {REPORT_JSON}")
    log(f"   Değişen: {len(suspicious)} | Özet: {report['ozet']}")

    if not args.sadece_denetle:
        changed, cleared, same = apply_to_db(results)
        log(f"✅ DB → değişen={changed}, aynı={same}, boş={cleared}")

    if args.export and not args.sadece_denetle:
        log("💾 data_store.js export...")
        subprocess.run([sys.executable, "export_data_store.py"], check=False)

    log("\n✅ Bitti.")


if __name__ == "__main__":
    main()
