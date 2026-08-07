# -*- coding: utf-8 -*-
"""
fragman_tmdb_siteye_uygula.py
-----------------------------
1) Mevcut fragman alanlarını _eski_* kolonlarına yedekler (bir kez).
2) Aktif fragman alanlarını fragman_tmdb_raporu.json ile TAMAMEN yazar
   (TMDB'de yoksa aktif alan boşaltılır → sitede eski YouTube kullanılmaz).
3) İstenirse export_data_store.py ile data_store.js güncellenir.

Kullanım:
    python fragman_tmdb_siteye_uygula.py --export
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

PLACEHOLDER = re.compile(r"(bulunamad[ıi]|BULUNAMADI|placeholder|^$)", re.I)


def is_valid(url):
    if url is None:
        return False
    s = str(url).strip()
    if not s or PLACEHOLDER.search(s):
        return False
    u = s.lower()
    return "youtube.com" in u or "youtu.be" in u


def ensure_columns(conn, table, columns):
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    for col in columns:
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
            print(f"  + kolon eklendi: {table}.{col}")


def backup_if_empty(conn, table, id_col, active_cols, eski_cols):
    """_eski_ boşsa aktif değeri yedekle (mevcut YouTube korunur)."""
    rows = conn.execute(f"SELECT {id_col}, {', '.join(active_cols + eski_cols)} FROM {table}").fetchall()
    n_backed = 0
    for row in rows:
        item_id = row[0]
        actives = row[1:1 + len(active_cols)]
        eskiler = row[1 + len(active_cols):]
        sets = []
        vals = []
        changed = False
        for a, e, e_name in zip(actives, eskiler, eski_cols):
            if not is_valid(e) and is_valid(a):
                sets.append(f"{e_name} = ?")
                vals.append(a)
                changed = True
        if changed:
            vals.append(item_id)
            conn.execute(
                f"UPDATE {table} SET {', '.join(sets)} WHERE {id_col} = ?",
                vals,
            )
            n_backed += 1
    return n_backed


def apply_diziler(items):
    conn = sqlite3.connect(DB_DIZI, timeout=60)
    ensure_columns(conn, "diziler", ["_eski_trailer_tr_url", "_eski_trailer_original_url"])
    conn.commit()

    backed = backup_if_empty(
        conn, "diziler", "id",
        ["trailer_tr_url", "trailer_original_url"],
        ["_eski_trailer_tr_url", "_eski_trailer_original_url"],
    )
    conn.commit()
    print(f"📺 Dizi yedeklenen kayıt: {backed}")

    by_id = {x["id"]: x for x in items if x.get("id") is not None}
    updated = 0
    cleared = 0

    for db_id, item in by_id.items():
        tr = item.get("trailer_tr") if is_valid(item.get("trailer_tr")) else None
        orig = item.get("trailer_original") if is_valid(item.get("trailer_original")) else None
        # Aktif alanlar = sadece TMDB (yoksa NULL)
        conn.execute(
            "UPDATE diziler SET trailer_tr_url = ?, trailer_original_url = ? WHERE id = ?",
            (tr, orig, db_id),
        )
        updated += 1
        if not tr and not orig:
            cleared += 1

    conn.commit()
    conn.close()
    print(f"📺 Diziler TMDB uygulandı: {updated} (ikisi de boş: {cleared})")


def apply_filmler(items):
    conn = sqlite3.connect(DB_FILM, timeout=60)
    ensure_columns(conn, "filmler", [
        "_eski_fragman_url",
        "_eski_trailer_dub_url",
        "_eski_trailer_sub_url",
        "_eski_trailer_orig_url",
    ])
    conn.commit()

    backed = backup_if_empty(
        conn, "filmler", "id",
        ["fragman_url", "trailer_dub_url", "trailer_sub_url", "trailer_orig_url"],
        ["_eski_fragman_url", "_eski_trailer_dub_url", "_eski_trailer_sub_url", "_eski_trailer_orig_url"],
    )
    conn.commit()
    print(f"🎬 Film yedeklenen kayıt: {backed}")

    by_id = {x["id"]: x for x in items if x.get("id") is not None}
    updated = 0
    cleared = 0

    for db_id, item in by_id.items():
        tr = item.get("trailer_tr") if is_valid(item.get("trailer_tr")) else None
        orig = item.get("trailer_original") if is_valid(item.get("trailer_original")) else None
        # Site: dub=TR, sub/orig=orijinal, fragman=TR yoksa orijinal
        frag = tr or orig
        conn.execute(
            "UPDATE filmler SET fragman_url = ?, trailer_dub_url = ?, "
            "trailer_sub_url = ?, trailer_orig_url = ? WHERE id = ?",
            (frag, tr, orig, orig, db_id),
        )
        updated += 1
        if not frag:
            cleared += 1

    conn.commit()
    conn.close()
    print(f"🎬 Filmler TMDB uygulandı: {updated} (fragman boş: {cleared})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()

    if not os.path.exists(JSON_PATH):
        print(f"❌ JSON yok: {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 60)
    print("TMDB FRAGMAN → AKTİF ALANLAR (eski YouTube → _eski_* yedek)")
    print("=" * 60)

    apply_diziler(data.get("diziler") or [])
    apply_filmler(data.get("filmler") or [])

    if args.export:
        print("\n💾 data_store.js aktarılıyor...")
        subprocess.run([sys.executable, "export_data_store.py"], check=False)

    print("\n✅ Sitede artık sadece TMDB fragmanları kullanılır.")
    print("   Eski YouTube linkleri _eski_* kolonlarında duruyor.")


if __name__ == "__main__":
    main()
