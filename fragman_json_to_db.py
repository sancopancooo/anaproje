# -*- coding: utf-8 -*-
"""
fragman_json_to_db.py
---------------------
fragman_tmdb_raporu.json → veritabanı (SADECE BOŞ ALANLARI DOLDURUR).
Mevcut geçerli YouTube linklerini silmez / üzerine yazmaz.

Diziler  → diziler_veritabani.db  (trailer_tr_url, trailer_original_url)
Filmler  → diziler_veritabanı.db  (fragman_url, trailer_dub_url, trailer_sub_url, trailer_orig_url)

Kullanım:
    python fragman_json_to_db.py
    python fragman_json_to_db.py --export   # ardından export_data_store.py
"""

import os
import re
import sys
import json
import sqlite3
import argparse
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

JSON_PATH = "fragman_tmdb_raporu.json"
DB_DIZI = "katalog.db"
DB_FILM = "katalog.db"

PLACEHOLDER = re.compile(
    r"(bulunamad[ıi]|BULUNAMADI|placeholder|^$)",
    re.I,
)


def is_valid(url):
    if url is None:
        return False
    s = str(url).strip()
    if not s or PLACEHOLDER.search(s):
        return False
    u = s.lower()
    return "youtube.com" in u or "youtu.be" in u


def fill_if_empty(current, new_url):
    """Mevcut geçerliyse dokunma; boşsa yeni değeri ver."""
    if is_valid(current):
        return current, False
    if is_valid(new_url):
        return new_url, True
    return current, False


def merge_diziler(items):
    if not os.path.exists(DB_DIZI):
        print(f"❌ DB yok: {DB_DIZI}")
        return
    conn = sqlite3.connect(DB_DIZI, timeout=60)
    c = conn.cursor()
    filled_tr = filled_orig = skipped = 0

    for item in items:
        db_id = item.get("id")
        tr_new = item.get("trailer_tr")
        orig_new = item.get("trailer_original")
        if not db_id:
            continue

        row = c.execute(
            "SELECT trailer_tr_url, trailer_original_url FROM diziler WHERE id = ?",
            (db_id,),
        ).fetchone()
        if not row:
            skipped += 1
            continue

        cur_tr, cur_orig = row
        new_tr, ch_tr = fill_if_empty(cur_tr, tr_new)
        new_orig, ch_orig = fill_if_empty(cur_orig, orig_new)

        if ch_tr or ch_orig:
            c.execute(
                "UPDATE diziler SET trailer_tr_url = ?, trailer_original_url = ? WHERE id = ?",
                (new_tr, new_orig, db_id),
            )
            if ch_tr:
                filled_tr += 1
            if ch_orig:
                filled_orig += 1

    conn.commit()
    conn.close()
    print(f"📺 Diziler: TR doldurulan={filled_tr}, ORJ doldurulan={filled_orig}, atlanan={skipped}")


def merge_filmler(items):
    if not os.path.exists(DB_FILM):
        print(f"❌ DB yok: {DB_FILM}")
        return
    conn = sqlite3.connect(DB_FILM, timeout=60)
    c = conn.cursor()
    filled_frag = filled_dub = filled_sub = filled_orig = skipped = 0

    for item in items:
        db_id = item.get("id")
        tr_new = item.get("trailer_tr")
        orig_new = item.get("trailer_original")
        if not db_id:
            continue

        row = c.execute(
            "SELECT fragman_url, trailer_dub_url, trailer_sub_url, trailer_orig_url "
            "FROM filmler WHERE id = ?",
            (db_id,),
        ).fetchone()
        if not row:
            skipped += 1
            continue

        cur_frag, cur_dub, cur_sub, cur_orig = row

        # TR → dub; ORJ → sub + orig; fragman_url boşsa en iyi aday
        new_dub, ch_dub = fill_if_empty(cur_dub, tr_new)
        new_sub, ch_sub = fill_if_empty(cur_sub, orig_new or tr_new)
        new_orig, ch_orig = fill_if_empty(cur_orig, orig_new or tr_new)
        best_frag = tr_new or orig_new
        new_frag, ch_frag = fill_if_empty(cur_frag, best_frag)

        if ch_dub or ch_sub or ch_orig or ch_frag:
            c.execute(
                "UPDATE filmler SET fragman_url = ?, trailer_dub_url = ?, "
                "trailer_sub_url = ?, trailer_orig_url = ? WHERE id = ?",
                (new_frag, new_dub, new_sub, new_orig, db_id),
            )
            if ch_frag:
                filled_frag += 1
            if ch_dub:
                filled_dub += 1
            if ch_sub:
                filled_sub += 1
            if ch_orig:
                filled_orig += 1

    conn.commit()
    conn.close()
    print(
        f"🎬 Filmler: fragman={filled_frag}, dub={filled_dub}, "
        f"sub={filled_sub}, orig={filled_orig}, atlanan={skipped}"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", action="store_true", help="Sonra data_store.js aktar")
    args = parser.parse_args()

    if not os.path.exists(JSON_PATH):
        print(f"❌ JSON yok: {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    diziler = data.get("diziler") or []
    filmler = data.get("filmler") or []
    print("=" * 60)
    print("FRAGMAN JSON → DB (sadece boş alanlar)")
    print(f"  JSON diziler: {len(diziler)}")
    print(f"  JSON filmler: {len(filmler)}")
    print("=" * 60)

    merge_diziler(diziler)
    merge_filmler(filmler)

    if args.export:
        print("\n💾 export_data_store.py çalışıyor...")
        subprocess.run([sys.executable, "export_data_store.py"], check=False)

    print("\n✅ Bitti. Mevcut geçerli fragmanlar korundu.")


if __name__ == "__main__":
    main()
