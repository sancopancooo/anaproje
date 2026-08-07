# -*- coding: utf-8 -*-
"""embeddings.db içindeki karışık tabloları bir kez ayır."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from db_paths import migrate_split_databases

report = migrate_split_databases(vacuum_embeddings=False)
print(json.dumps(report, ensure_ascii=False, indent=2))
