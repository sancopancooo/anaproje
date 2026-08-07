# -*- coding: utf-8 -*-
"""dizi_ek_veri_json_to_db.py — JSON → diziler_veritabani.db + export"""
import json
import os
import sys
import sqlite3
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

JSON_PATH = "dizi_ek_veri_tmdb_raporu.json"
DB_DIZI = "katalog.db"


def dumps_list(val):
    if not val:
        return "[]"
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


def main():
    if not os.path.exists(JSON_PATH):
        print(f"❌ JSON yok: {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("diziler") or []
    conn = sqlite3.connect(DB_DIZI, timeout=60)
    c = conn.cursor()

    updated = 0
    skipped = 0
    for item in items:
        if item.get("durum") != "ok":
            skipped += 1
            continue
        db_id = item.get("id")
        c.execute(
            """
            UPDATE diziler SET
                orijinal_dil = ?,
                yapim_ulkeleri = ?,
                onerilen_idleri = ?,
                benzer_idleri = ?,
                yayin_aglari = ?,
                yapim_sirketleri = ?,
                icerik_derecelendirme = ?
            WHERE id = ?
            """,
            (
                item.get("orijinal_dil") or None,
                dumps_list(item.get("yapim_ulkeleri")),
                dumps_list(item.get("onerilen_idleri")),
                dumps_list(item.get("benzer_idleri")),
                dumps_list(item.get("yayin_aglari")),
                dumps_list(item.get("yapim_sirketleri")),
                item.get("icerik_derecelendirme") or None,
                db_id,
            ),
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"✅ Güncellenen: {updated}")
    print(f"⏭ Atlanan: {skipped}")

    print("\n💾 data_store.js aktarılıyor...", flush=True)
    subprocess.run([sys.executable, "-u", "export_data_store.py"], check=False)
    print("Bitti.", flush=True)


if __name__ == "__main__":
    main()
