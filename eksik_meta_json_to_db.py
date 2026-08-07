# -*- coding: utf-8 -*-
"""eksik_meta_json_to_db.py — eksik_meta_tmdb_raporu.json → DB + export"""
import json
import os
import sys
import sqlite3
import subprocess

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

JSON_PATH = "eksik_meta_tmdb_raporu.json"
DB_DIZI = "katalog.db"
DB_FILM = "katalog.db"


def dumps_list(val):
    if not val:
        return "[]"
    if isinstance(val, str):
        return val
    return json.dumps(val, ensure_ascii=False)


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


def fill(cur, new, numeric=False):
    """Mevcut doluysa koru; boşsa TMDB değerini yaz."""
    if not is_empty(cur, numeric=numeric):
        return cur, False
    if new is None:
        return cur, False
    if numeric:
        try:
            if float(new) == 0 and (cur is None or is_empty(cur, numeric=True)):
                # 0 da geçerli TMDB değeri olabilir (puanı olmayan yapım)
                return new, True
        except (TypeError, ValueError):
            return cur, False
        return new, True
    if isinstance(new, list):
        if not new:
            return cur, False
        return dumps_list(new), True
    s = str(new).strip()
    if not s:
        return cur, False
    return s, True


def apply_diziler(items):
    conn = sqlite3.connect(DB_DIZI, timeout=60)
    c = conn.cursor()
    updated = skipped = 0
    for item in items:
        if item.get("durum") != "ok":
            skipped += 1
            continue
        db_id = item["id"]
        row = c.execute(
            "SELECT anahtar_kelimeler, efsanevi_ikili, oyuncular_gercek, puan_ortalamasi, "
            "oy_sayisi, icerik_derecelendirme, yapim_sirketleri, yayin_aglari, backdrop_url "
            "FROM diziler WHERE id = ?",
            (db_id,),
        ).fetchone()
        if not row:
            skipped += 1
            continue

        vals = []
        changed = False
        mapping = [
            (row[0], item.get("anahtar_kelimeler"), False),
            (row[1], item.get("efsanevi_ikili"), False),
            (row[2], item.get("oyuncular_gercek"), False),
            (row[3], item.get("puan_ortalamasi"), True),
            (row[4], item.get("oy_sayisi"), True),
            (row[5], item.get("icerik_derecelendirme"), False),
            (row[6], item.get("yapim_sirketleri"), False),
            (row[7], item.get("yayin_aglari"), False),
            (row[8], item.get("backdrop_url"), False),
        ]
        for cur, new, numeric in mapping:
            # list fields for şirket/ağ
            if isinstance(new, list):
                v, ch = fill(cur, new, numeric=False)
            else:
                v, ch = fill(cur, new, numeric=numeric)
            vals.append(v)
            changed = changed or ch

        if changed:
            c.execute(
                """
                UPDATE diziler SET
                    anahtar_kelimeler = ?, efsanevi_ikili = ?, oyuncular_gercek = ?,
                    puan_ortalamasi = ?, oy_sayisi = ?, icerik_derecelendirme = ?,
                    yapim_sirketleri = ?, yayin_aglari = ?, backdrop_url = ?
                WHERE id = ?
                """,
                (*vals, db_id),
            )
            updated += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    print(f"📺 Diziler güncellenen={updated}, atlanan={skipped}", flush=True)


def apply_filmler(items):
    conn = sqlite3.connect(DB_FILM, timeout=60)
    c = conn.cursor()
    updated = skipped = 0
    for item in items:
        if item.get("durum") != "ok":
            skipped += 1
            continue
        db_id = item["id"]
        row = c.execute(
            "SELECT anahtar_kelimeler, slogan, yonetmen, oyuncular, puan, oy_sayisi, "
            "yapim_sirketleri, backdrop_url, butce, hasilat, koleksiyon "
            "FROM filmler WHERE id = ?",
            (db_id,),
        ).fetchone()
        if not row:
            skipped += 1
            continue

        vals = []
        changed = False
        mapping = [
            (row[0], item.get("anahtar_kelimeler"), False),
            (row[1], item.get("slogan"), False),
            (row[2], item.get("yonetmen"), False),
            (row[3], item.get("oyuncular"), False),
            (row[4], item.get("puan"), True),
            (row[5], item.get("oy_sayisi"), True),
            (row[6], item.get("yapim_sirketleri"), False),
            (row[7], item.get("backdrop_url"), False),
            (row[8], item.get("butce"), True),
            (row[9], item.get("hasilat"), True),
            (row[10], item.get("koleksiyon"), False),
        ]
        for cur, new, numeric in mapping:
            if isinstance(new, list):
                v, ch = fill(cur, new, numeric=False)
            else:
                v, ch = fill(cur, new, numeric=numeric)
            vals.append(v)
            changed = changed or ch

        if changed:
            c.execute(
                """
                UPDATE filmler SET
                    anahtar_kelimeler = ?, slogan = ?, yonetmen = ?, oyuncular = ?,
                    puan = ?, oy_sayisi = ?, yapim_sirketleri = ?, backdrop_url = ?,
                    butce = ?, hasilat = ?, koleksiyon = ?
                WHERE id = ?
                """,
                (*vals, db_id),
            )
            updated += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()
    print(f"🎬 Filmler güncellenen={updated}, atlanan={skipped}", flush=True)


def main():
    if not os.path.exists(JSON_PATH):
        print(f"❌ JSON yok: {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    print("=" * 60, flush=True)
    print("EKSİK META JSON → DB (boş alanları doldur)", flush=True)
    print("=" * 60, flush=True)

    apply_diziler(data.get("diziler") or [])
    apply_filmler(data.get("filmler") or [])

    print("\n💾 data_store.js aktarılıyor...", flush=True)
    subprocess.run([sys.executable, "-u", "export_data_store.py"], check=False)
    print("Bitti.", flush=True)


if __name__ == "__main__":
    main()
