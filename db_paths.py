# -*- coding: utf-8 -*-
"""
Merkezi SQLite yolları — veri sınıflarını karıştırma.

  embeddings.db      → yalnızca item_embeddings (yeniden üretilebilir motor, pahalı)
  runtime_cache.db   → GPT önbellek / kota / analytics (yeniden üretilebilir, ucuz)
  kullanicilar1.db   → hesaplar, kitaplık, arkadaşlık, füzyon, geri bildirim (kritik)
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import time
from typing import Iterable, Sequence

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

EMBEDDINGS_DB_PATH = os.path.join(_BASE_DIR, "embeddings.db")
RUNTIME_CACHE_DB_PATH = os.path.join(_BASE_DIR, "runtime_cache.db")
USER_DB_PATH = os.path.join(_BASE_DIR, "kullanicilar1.db")

# embeddings.db içinde kalmaması gereken tablolar
_CACHE_TABLES = (
    "gpt_notes_cache",
    "gpt_usage_daily",
    "gpt_global_daily",
    "gpt_query_expand_cache",
    "analytics_events",
)
_USER_OPS_TABLES = (
    "user_feedback",
    "content_error_reports",
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return bool(row)


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> int:
    if not _table_exists(src, table):
        return 0
    if not _table_exists(dst, table):
        ddl = src.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not ddl or not ddl[0]:
            return 0
        dst.execute(ddl[0])
        for (idx_sql,) in src.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
            (table,),
        ):
            try:
                dst.execute(idx_sql)
            except sqlite3.OperationalError:
                pass
    cols_src = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")')]
    cols_dst = [r[1] for r in dst.execute(f'PRAGMA table_info("{table}")')]
    cols = [c for c in cols_src if c in cols_dst]
    if not cols:
        return 0
    col_list = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join("?" for _ in cols)
    rows = src.execute(f'SELECT {col_list} FROM "{table}"').fetchall()
    if rows:
        dst.executemany(
            f'INSERT OR IGNORE INTO "{table}" ({col_list}) VALUES ({placeholders})',
            rows,
        )
    return len(rows)


def _drop_tables(conn: sqlite3.Connection, tables: Iterable[str]) -> None:
    for table in tables:
        if _table_exists(conn, table):
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')


def ensure_runtime_cache_schema(path: str = RUNTIME_CACHE_DB_PATH) -> None:
    conn = sqlite3.connect(path, timeout=30.0)
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS gpt_notes_cache (
                cache_key TEXT PRIMARY KEY,
                notes_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS gpt_usage_daily (
                day_key TEXT NOT NULL,
                username TEXT NOT NULL,
                feature TEXT NOT NULL,
                call_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day_key, username, feature)
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS gpt_global_daily (
                day_key TEXT PRIMARY KEY,
                call_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS gpt_query_expand_cache (
                cache_key TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS analytics_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                item_id TEXT,
                username TEXT,
                rec_source TEXT,
                timestamp REAL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def ensure_user_ops_schema(path: str = USER_DB_PATH) -> None:
    # Turso varsa oraya yaz; yoksa yerel kullanicilar1.db
    try:
        from user_db import connect_user_db, turso_configured

        conn = connect_user_db(timeout=30.0) if turso_configured() else sqlite3.connect(path, timeout=30.0)
    except Exception:
        conn = sqlite3.connect(path, timeout=30.0)
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS content_error_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                item_title TEXT,
                media_type TEXT NOT NULL,
                fields_json TEXT NOT NULL,
                note TEXT,
                username TEXT,
                status TEXT DEFAULT 'open',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_error_reports_item ON content_error_reports(item_id)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_error_reports_status ON content_error_reports(status)"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_error_reports_created ON content_error_reports(created_at)"
            )
        except Exception:
            # Turso / kısıtlı ortamlarda index CREATE başarısız olabilir; tablolar yeter
            pass
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                message TEXT NOT NULL,
                media_type TEXT,
                status TEXT DEFAULT 'open',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def migrate_split_databases(
    embeddings_path: str = EMBEDDINGS_DB_PATH,
    cache_path: str = RUNTIME_CACHE_DB_PATH,
    user_path: str = USER_DB_PATH,
    *,
    vacuum_embeddings: bool = False,
) -> dict:
    """
    embeddings.db içindeki cache / kullanıcı-op tablolarını ayırır.
    Idempotent: tekrar çalıştırılabilir.
    """
    report = {
        "migrated_cache": {},
        "migrated_user_ops": {},
        "dropped_from_embeddings": [],
        "skipped": False,
    }
    if not os.path.exists(embeddings_path):
        report["skipped"] = True
        report["reason"] = "embeddings.db yok"
        ensure_runtime_cache_schema(cache_path)
        ensure_user_ops_schema(user_path)
        return report

    ensure_runtime_cache_schema(cache_path)
    ensure_user_ops_schema(user_path)

    src = sqlite3.connect(embeddings_path, timeout=60.0)
    cache = sqlite3.connect(cache_path, timeout=60.0)
    user = sqlite3.connect(user_path, timeout=60.0)
    try:
        mixed = [t for t in (_CACHE_TABLES + _USER_OPS_TABLES) if _table_exists(src, t)]
        if not mixed:
            report["skipped"] = True
            report["reason"] = "embeddings.db zaten temiz"
            return report

        # Güvenlik: ayırmadan önce bir kez yedek al (aynı klasör, timestamp)
        bak = embeddings_path + f".pre_split_{time.strftime('%Y%m%d_%H%M%S')}.bak"
        try:
            shutil.copy2(embeddings_path, bak)
            report["backup"] = bak
        except Exception as e:
            report["backup_error"] = str(e)

        for table in _CACHE_TABLES:
            n = _copy_table(src, cache, table)
            if n or _table_exists(src, table):
                report["migrated_cache"][table] = n

        for table in _USER_OPS_TABLES:
            n = _copy_table(src, user, table)
            if n or _table_exists(src, table):
                report["migrated_user_ops"][table] = n

        cache.commit()
        user.commit()

        _drop_tables(src, mixed)
        src.commit()
        report["dropped_from_embeddings"] = list(mixed)

        if vacuum_embeddings:
            src.execute("VACUUM")
            report["vacuum"] = True
    finally:
        src.close()
        cache.close()
        user.close()

    return report


def resolve_embeddings_path() -> str:
    path = EMBEDDINGS_DB_PATH
    if not os.path.exists(path):
        alt = "embeddings.db"
        if os.path.exists(alt):
            return alt
    return path


# --------------------------------------------------------------------------
# Katalog: dizi + film tek dosya (katalog.db)
# --------------------------------------------------------------------------
CATALOG_DB_NAME = "katalog.db"
CATALOG_DB_PATH = os.path.join(_BASE_DIR, CATALOG_DB_NAME)
LEGACY_SERIES_DB_NAME = "diziler_veritabani.db"
LEGACY_MOVIES_DB_NAME = "diziler_veritabanı.db"


def find_legacy_series_db() -> str | None:
    p = os.path.join(_BASE_DIR, LEGACY_SERIES_DB_NAME)
    if os.path.exists(p):
        return p
    for fname in os.listdir(_BASE_DIR):
        if not fname.endswith(".db"):
            continue
        if "veritaban" not in fname.lower():
            continue
        if any(x in fname for x in ("embeddings", "kullanici", "runtime", "katalog", ".bak")):
            continue
        fpath = os.path.join(_BASE_DIR, fname)
        try:
            conn = sqlite3.connect(fpath)
            tables = {
                r[0]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            n_dizi = 0
            if "diziler" in tables:
                n_dizi = conn.execute("SELECT COUNT(*) FROM diziler").fetchone()[0]
            has_film = "filmler" in tables
            conn.close()
        except Exception:
            continue
        # Asıl dizi DB: filmler yok, diziler dolu
        if "diziler" in tables and not has_film and n_dizi >= 1000:
            return fpath
    return None


def find_legacy_movies_db() -> str | None:
    p = os.path.join(_BASE_DIR, LEGACY_MOVIES_DB_NAME)
    if os.path.exists(p):
        return p
    for fname in os.listdir(_BASE_DIR):
        if not fname.endswith(".db"):
            continue
        if "veritaban" not in fname.lower():
            continue
        if any(x in fname for x in ("embeddings", "kullanici", "runtime", "katalog", ".bak")):
            continue
        fpath = os.path.join(_BASE_DIR, fname)
        try:
            conn = sqlite3.connect(fpath)
            tables = {
                r[0]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            n_film = 0
            if "filmler" in tables:
                n_film = conn.execute("SELECT COUNT(*) FROM filmler").fetchone()[0]
            conn.close()
        except Exception:
            continue
        if "filmler" in tables and n_film >= 1000:
            return fpath
    return None


def merge_catalog_databases(
    *,
    dest_path: str = CATALOG_DB_PATH,
    series_src: str | None = None,
    movies_src: str | None = None,
    archive_legacy: bool = True,
) -> dict:
    """
    diziler + filmler tablolarını tek katalog.db dosyasında birleştirir.
    Kullanıcı/op tabloları (kitaplık, favori…) taşınmaz.
    """
    series_src = series_src or find_legacy_series_db()
    movies_src = movies_src or find_legacy_movies_db()
    report = {
        "dest": dest_path,
        "series_src": series_src,
        "movies_src": movies_src,
        "diziler": 0,
        "filmler": 0,
        "archived": [],
    }
    if not series_src or not os.path.exists(series_src):
        raise FileNotFoundError("Dizi kaynağı (diziler tablosu) bulunamadı.")
    if not movies_src or not os.path.exists(movies_src):
        raise FileNotFoundError("Film kaynağı (filmler tablosu) bulunamadı.")

    # Mevcut katalog varsa ve doluysa atla (idempotent)
    if os.path.exists(dest_path):
        conn = sqlite3.connect(dest_path)
        try:
            tables = {
                r[0]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            ok_d = "diziler" in tables and conn.execute("SELECT COUNT(*) FROM diziler").fetchone()[0] > 0
            ok_f = "filmler" in tables and conn.execute("SELECT COUNT(*) FROM filmler").fetchone()[0] > 0
            if ok_d and ok_f:
                report["skipped"] = True
                report["reason"] = "katalog.db zaten diziler+filmler içeriyor"
                report["diziler"] = conn.execute("SELECT COUNT(*) FROM diziler").fetchone()[0]
                report["filmler"] = conn.execute("SELECT COUNT(*) FROM filmler").fetchone()[0]
                return report
        finally:
            conn.close()

    if os.path.exists(dest_path):
        bak = dest_path + f".pre_merge_{time.strftime('%Y%m%d_%H%M%S')}.bak"
        shutil.copy2(dest_path, bak)
        report["dest_backup"] = bak
        os.remove(dest_path)

    src_s = sqlite3.connect(series_src)
    src_m = sqlite3.connect(movies_src)
    dst = sqlite3.connect(dest_path)
    try:
        if not _table_exists(src_s, "diziler"):
            raise RuntimeError(f"{series_src} içinde diziler tablosu yok")
        if not _table_exists(src_m, "filmler"):
            raise RuntimeError(f"{movies_src} içinde filmler tablosu yok")

        report["diziler"] = _copy_table(src_s, dst, "diziler")
        report["filmler"] = _copy_table(src_m, dst, "filmler")
        dst.commit()
    finally:
        src_s.close()
        src_m.close()
        dst.close()

    if archive_legacy:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        for src in (series_src, movies_src):
            if not src or not os.path.exists(src):
                continue
            # katalog ile aynı dosya olmasın
            if os.path.abspath(src) == os.path.abspath(dest_path):
                continue
            archived = src + f".legacy_{stamp}.bak"
            try:
                shutil.move(src, archived)
                report["archived"].append(archived)
            except Exception as e:
                report.setdefault("archive_errors", []).append(f"{src}: {e}")

    return report


def resolve_catalog_db_path() -> str:
    """
    Tercih: katalog.db
    Yoksa: legacy iki dosyadan birleştir (mümkünse) veya series path fallback
    """
    if os.path.exists(CATALOG_DB_PATH):
        return CATALOG_DB_PATH
    # Aynı klasörde relative
    if os.path.exists(CATALOG_DB_NAME):
        return os.path.abspath(CATALOG_DB_NAME)
    try:
        report = merge_catalog_databases(archive_legacy=False)
        if report.get("diziler") or report.get("skipped"):
            return CATALOG_DB_PATH
    except Exception:
        pass
    # Son çare: eski dizi dosyası (film tarafı ayrı kalabilir — geçici)
    legacy = find_legacy_series_db() or find_legacy_movies_db()
    return legacy or CATALOG_DB_PATH


def series_db_path() -> str:
    return resolve_catalog_db_path()


def movies_db_path() -> str:
    return resolve_catalog_db_path()
