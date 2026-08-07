# -*- coding: utf-8 -*-
"""
Eski deneysel aktarım scripti — hardcoded token YASAK.

Kullanıcı DB taşıma:
  .\\venv\\Scripts\\python.exe scripts\\migrate_users_to_turso.py

Gerekli env (.env — GitHub'a gitmez):
  TURSO_DATABASE_URL=libsql://...
  TURSO_AUTH_TOKEN=...
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / "scripts" / "migrate_users_to_turso.py"

if __name__ == "__main__":
    if not TARGET.is_file():
        print("[!] scripts/migrate_users_to_turso.py bulunamadı.")
        raise SystemExit(2)
    sys.path.insert(0, str(ROOT))
    runpy.run_path(str(TARGET), run_name="__main__")
