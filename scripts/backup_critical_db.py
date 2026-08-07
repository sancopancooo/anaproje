# -*- coding: utf-8 -*-
"""
Haftalık kritik DB yedeği.

Kullanım:
  .\\venv\\Scripts\\python.exe scripts\\backup_critical_db.py
  .\\venv\\Scripts\\python.exe scripts\\backup_critical_db.py --turso

Turso için önce:
  turso auth login
  turso db shell <DB_ADI>   # veya TURSO_DB_NAME env

Ortam değişkenleri (isteğe bağlı):
  TURSO_DB_NAME=dizimibul-users
  BACKUP_DIR=C:\\Users\\...\\Desktop\\Yabancı Dizi Projem\\backups
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BACKUP_DIR = ROOT / "backups"
KEEP_LOCAL = 12  # ~3 ay haftalık


def _stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def backup_local_sqlite(src: Path, dest_dir: Path) -> Path | None:
    if not src.exists():
        print(f"[!] Yok, atlandı: {src.name}")
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{src.stem}_{_stamp()}.db"
    shutil.copy2(src, dest)
    # Aynı anda okunabilir dump (SQL text) — küçük DB'ler için
    sql_path = dest.with_suffix(".sql")
    try:
        import sqlite3

        conn = sqlite3.connect(str(src))
        with open(sql_path, "w", encoding="utf-8") as f:
            for line in conn.iterdump():
                f.write(f"{line}\n")
        conn.close()
    except Exception as e:
        print(f"[!] SQL dump uyarısı ({src.name}): {e}")
        sql_path = None
    print(f"[+] Yerel yedek: {dest.name}" + (f" + {sql_path.name}" if sql_path else ""))
    return dest


def prune_old(dest_dir: Path, pattern: str, keep: int = KEEP_LOCAL) -> None:
    files = sorted(dest_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
            print(f"[-] Eski yedek silindi: {old.name}")
        except OSError:
            pass


def backup_turso(dest_dir: Path, db_name: str) -> Path | None:
    """
    turso db shell <name> .dump  →  dosyaya yaz.
    Turso CLI yoksa net mesaj verip çık.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"turso_{db_name}_{_stamp()}.sql"
    turso = shutil.which("turso")
    if not turso:
        print("[!] `turso` CLI bulunamadı. https://docs.turso.tech/cli/install")
        print("    Yine de yerel kullanicilar1.db yedeği alındıysa o güvende.")
        return None

    # turso db shell DB ".dump" — bazı sürümlerde dump için ayrı komut
    cmd = [turso, "db", "shell", db_name, ".dump"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
        )
    except Exception as e:
        print(f"[!] Turso dump başarısız: {e}")
        return None

    if proc.returncode != 0:
        print(f"[!] Turso hata (exit {proc.returncode}): {(proc.stderr or proc.stdout)[:500]}")
        print("    İpucu: turso auth login && turso db list")
        return None

    out = (proc.stdout or "").strip()
    if not out:
        print("[!] Turso dump boş döndü.")
        return None

    dest.write_text(out + "\n", encoding="utf-8")
    print(f"[+] Turso dump: {dest.name} ({dest.stat().st_size // 1024} KB)")
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Kritik kullanıcı DB yedeği")
    parser.add_argument("--turso", action="store_true", help="Turso dump da al")
    parser.add_argument(
        "--dir",
        default=os.environ.get("BACKUP_DIR", str(DEFAULT_BACKUP_DIR)),
        help="Yedek klasörü",
    )
    parser.add_argument(
        "--turso-db",
        default=os.environ.get("TURSO_DB_NAME", "").strip(),
        help="Turso veritabanı adı",
    )
    args = parser.parse_args()
    dest_dir = Path(args.dir)

    print("=== Kritik veri yedeği (hesap / kitaplık / arkadaşlık) ===")
    print("Motor (embeddings.db) ve runtime_cache.db burada YOK — yeniden üretilebilir.\n")

    user_db = ROOT / "kullanicilar1.db"
    backup_local_sqlite(user_db, dest_dir)
    prune_old(dest_dir, "kullanicilar1_*.db")
    prune_old(dest_dir, "kullanicilar1_*.sql")

    if args.turso:
        name = args.turso_db
        if not name:
            print("[!] --turso için TURSO_DB_NAME veya --turso-db gerekli.")
            return 2
        backup_turso(dest_dir, name)
        prune_old(dest_dir, f"turso_{name}_*.sql")

    print("\nTamam. Haftada bir çalıştır (Task Scheduler veya hatırlatıcı).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
