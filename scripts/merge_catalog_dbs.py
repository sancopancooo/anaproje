# -*- coding: utf-8 -*-
"""İki katalog DB'sini (dizi + film) tek katalog.db dosyasında birleştir."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from db_paths import merge_catalog_databases

if __name__ == "__main__":
    archive = "--keep-legacy" not in sys.argv
    report = merge_catalog_databases(archive_legacy=archive)
    print(json.dumps(report, ensure_ascii=False, indent=2))
