# -*- coding: utf-8 -*-
"""Legacy dizi/film DB dosyalarını .legacy_*.bak olarak arşivle (katalog.db hazırsa)."""
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from db_paths import CATALOG_DB_PATH, find_legacy_series_db, find_legacy_movies_db
import sqlite3

if not os.path.exists(CATALOG_DB_PATH):
    raise SystemExit("katalog.db yok — önce merge_catalog_dbs.py çalıştır.")

conn = sqlite3.connect(CATALOG_DB_PATH)
n_d = conn.execute("SELECT COUNT(*) FROM diziler").fetchone()[0]
n_f = conn.execute("SELECT COUNT(*) FROM filmler").fetchone()[0]
conn.close()
print(f"katalog.db OK — diziler={n_d}, filmler={n_f}")

stamp = time.strftime("%Y%m%d_%H%M%S")
for src in (find_legacy_series_db(), find_legacy_movies_db()):
    if not src or not os.path.exists(src):
        continue
    if os.path.abspath(src) == os.path.abspath(CATALOG_DB_PATH):
        continue
    dest = src + f".legacy_{stamp}.bak"
    shutil.move(src, dest)
    print(f"Arşiv: {os.path.basename(src)} -> {os.path.basename(dest)}")

print("Bitti.")
