# -*- coding: utf-8 -*-
"""
kullanicilar1.db → Turso taşıma.

Gerekli env (.env / Render — koda YAZMA):
  TURSO_DATABASE_URL=libsql://...
  TURSO_AUTH_TOKEN=...

Kullanım:
  .\\venv\\Scripts\\python.exe scripts\\migrate_users_to_turso.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        val = v.strip().strip('"').strip("'")
        if val and not os.environ.get(k.strip()):
            os.environ[k.strip()] = val


def main() -> int:
    _load_env()
    url = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
    token = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()
    if not url or not token:
        print("[!] TURSO_DATABASE_URL ve TURSO_AUTH_TOKEN gerekli (.env).")
        print("    Token'ı koda yazma — sadece .env / Render Environment.")
        return 2

    local = ROOT / "kullanicilar1.db"
    if not local.is_file():
        print("[!] kullanicilar1.db yok.")
        return 2

    import libsql_client

    kaynak = sqlite3.connect(str(local))
    hedef = libsql_client.create_client_sync(url=url, auth_token=token)

    tablolar = [
        r[0]
        for r in kaynak.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    print(f"Kaynak: {local.name} | Tablolar: {', '.join(tablolar)}")
    print(f"Hedef: {url.split('@')[-1] if '@' in url else url}")

    for tablo in tablolar:
        ddl = kaynak.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (tablo,)
        ).fetchone()
        if not ddl or not ddl[0]:
            continue
        try:
            hedef.execute(ddl[0])
        except Exception as e:
            # tablo zaten varsa devam
            if "already exists" not in str(e).lower():
                print(f"[!] CREATE {tablo}: {e}")

        cols = [r[1] for r in kaynak.execute(f'PRAGMA table_info("{tablo}")')]
        if not cols:
            continue
        col_list = ", ".join(f'"{c}"' for c in cols)
        placeholders = ",".join(["?"] * len(cols))
        # Mevcut satırları temizle (yeniden yükleme)
        try:
            hedef.execute(f'DELETE FROM "{tablo}"')
        except Exception:
            pass

        paket, toplam = [], 0
        for satir in kaynak.execute(f'SELECT {col_list} FROM "{tablo}"'):
            paket.append(
                (f'INSERT INTO "{tablo}" ({col_list}) VALUES ({placeholders})', list(satir))
            )
            if len(paket) >= 200:
                hedef.batch(paket)
                toplam += len(paket)
                print(f"  {tablo}: {toplam}...")
                paket = []
        if paket:
            hedef.batch(paket)
            toplam += len(paket)

        yerel = kaynak.execute(f'SELECT COUNT(*) FROM "{tablo}"').fetchone()[0]
        bulut = hedef.execute(f'SELECT COUNT(*) FROM "{tablo}"').rows[0][0]
        ok = "OK" if int(yerel) == int(bulut) else "UYUMSUZ"
        print(f"  {tablo}: yerel={yerel} turso={bulut} [{ok}]")

    kaynak.close()
    print("\nBitti. Render'a TURSO_DATABASE_URL + TURSO_AUTH_TOKEN ekle, redeploy et.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
