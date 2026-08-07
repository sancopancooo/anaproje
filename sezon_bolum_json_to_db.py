# -*- coding: utf-8 -*-
"""sezon_bolum_json_to_db.py — JSON → diziler_veritabani.db + export"""
import json
import os
import sys
import sqlite3
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

JSON_PATH = "sezon_bolum_tmdb_raporu.json"
DB_DIZI = "katalog.db"


def main():
    if not os.path.exists(JSON_PATH):
        print(f"❌ JSON yok: {JSON_PATH}")
        sys.exit(1)
    if not os.path.exists(DB_DIZI):
        print(f"❌ DB yok: {DB_DIZI}")
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
        harita = item.get("sezon_bolum_haritasi")
        if not harita:
            skipped += 1
            continue
        sezon = item.get("sezon_sayisi")
        bolum = item.get("toplam_bolum_sayisi")
        db_id = item.get("id")
        c.execute(
            "UPDATE diziler SET sezon_bolum_haritasi = ?, sezon_sayisi = ?, toplam_bolum_sayisi = ? "
            "WHERE id = ?",
            (harita, sezon, bolum, db_id),
        )
        updated += 1

    conn.commit()
    remaining = c.execute(
        "SELECT COUNT(*) FROM diziler WHERE sezon_bolum_haritasi IS NULL "
        "OR TRIM(COALESCE(sezon_bolum_haritasi,'')) = ''"
    ).fetchone()[0]
    conn.close()

    print(f"✅ Güncellenen: {updated}")
    print(f"⏭ Atlanan (bulunamadı/harita yok): {skipped}")
    print(f"📭 Hâlâ boş harita: {remaining}")

    print("\n💾 data_store.js aktarılıyor...")
    subprocess.run([sys.executable, "export_data_store.py"], check=False)
    print("Bitti.")


if __name__ == "__main__":
    main()
