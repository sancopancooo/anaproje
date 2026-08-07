# -*- coding: utf-8 -*-
"""
Kullanıcı DB bağlantısı: yerel SQLite veya Turso (libsql).

Env (Render / .env — asla koda yazma):
  TURSO_DATABASE_URL=libsql://....turso.io
  TURSO_AUTH_TOKEN=...

İkisi de varsa Turso; yoksa kullanicilar1.db (yerel).
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any, Iterable, List, Sequence, Union

from db_paths import USER_DB_PATH

__all__ = [
    "USER_DB_PATH",
    "connect_user_db",
    "turso_configured",
    "user_db_backend_name",
]

Params = Union[Sequence[Any], None]


def _load_env() -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        for line in open(env_path, encoding="utf-8"):
            if not line.strip() or line.strip().startswith("#") or "=" not in line:
                continue
            k, v = line.strip().split("=", 1)
            val = v.strip().strip('"').strip("'")
            if val and not os.environ.get(k):
                os.environ[k] = val
    except Exception:
        pass


_load_env()


def turso_configured() -> bool:
    url = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
    token = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()
    return bool(url and token and url.startswith(("libsql://", "https://")))


class _TursoCursor:
    def __init__(self, client):
        self._client = client
        self._rows: List[Any] = []
        self._idx = 0
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, sql: str, params: Params = None):
        args = list(params) if params is not None else []
        result = self._client.execute(sql, args)
        # libsql Row: hem indeks hem kolon adı destekler
        self._rows = list(result.rows or [])
        self._idx = 0
        self.lastrowid = result.last_insert_rowid
        self.rowcount = result.rows_affected
        return self

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]):
        stmts = [(sql, list(p)) for p in seq_of_params]
        if stmts:
            self._client.batch(stmts)
            self.rowcount = len(stmts)
        return self

    def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchall(self):
        rest = self._rows[self._idx :]
        self._idx = len(self._rows)
        return rest

    def close(self):
        return None


class _TursoConnection:
    """sqlite3.Connection'a yakın senkron sarmalayıcı (Flask kodu için)."""

    def __init__(self, client):
        self._client = client
        self.row_factory = None  # libsql Row zaten isimli erişim sunar

    def cursor(self):
        return _TursoCursor(self._client)

    def execute(self, sql: str, params: Params = None):
        return self.cursor().execute(sql, params)

    def commit(self):
        return None

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


_turso_client = None


def _get_turso_client():
    global _turso_client
    if _turso_client is not None:
        return _turso_client
    import libsql_client

    _turso_client = libsql_client.create_client_sync(
        url=os.environ["TURSO_DATABASE_URL"].strip(),
        auth_token=os.environ["TURSO_AUTH_TOKEN"].strip(),
    )
    return _turso_client


def connect_user_db(timeout: float = 30.0):
    if turso_configured():
        return _TursoConnection(_get_turso_client())
    return sqlite3.connect(USER_DB_PATH, timeout=timeout)


def user_db_backend_name() -> str:
    return "turso" if turso_configured() else f"sqlite:{os.path.basename(USER_DB_PATH)}"
