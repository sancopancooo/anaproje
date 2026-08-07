# -*- coding: utf-8 -*-
"""
Sosyal katman: arkadaşlık istekleri + ortak zevk füzyon istekleri (kullanicilar1.db).
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

import auth_utils

from user_db import connect_user_db, USER_DB_PATH as DB_PATH


def _conn():
    conn = connect_user_db(timeout=30.0)
    try:
        import sqlite3 as _sq

        if isinstance(conn, _sq.Connection):
            conn.row_factory = _sq.Row
    except Exception:
        pass
    return conn


def _row_keys(row) -> set:
    if hasattr(row, "keys") and callable(row.keys):
        try:
            return set(row.keys())
        except Exception:
            pass
    if hasattr(row, "asdict"):
        return set(row.asdict().keys())
    if hasattr(row, "_column_idxs"):
        return set(row._column_idxs.keys())
    return set()


def _ensure_tables(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS arkadasliklar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kullanici TEXT,
            arkadas TEXT,
            UNIQUE(kullanici, arkadas)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS arkadaslik_istekleri (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gonderen TEXT,
            alan TEXT,
            durum TEXT DEFAULT 'bekliyor'
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fuzyon_istekleri (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gonderen TEXT NOT NULL,
            alan TEXT NOT NULL,
            universe TEXT NOT NULL DEFAULT 'MOVIES',
            gonderen_secimler TEXT NOT NULL DEFAULT '[]',
            alan_secimler TEXT,
            durum TEXT NOT NULL DEFAULT 'bekliyor',
            overlap_json TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    _migrate_fuzyon_columns(cursor)


def _migrate_fuzyon_columns(cursor: sqlite3.Cursor) -> None:
    """Mevcut DB'lere güvenli kolon ekleme (yoksa ALTER, varsa yoksay)."""
    for col, col_type in (
        ("gonderen_kitaplik", "TEXT"),
        ("alan_kitaplik", "TEXT"),
        ("sonuclar_json", "TEXT"),
    ):
        try:
            cursor.execute(f"ALTER TABLE fuzyon_istekleri ADD COLUMN {col} {col_type}")
        except Exception:
            pass


def _canonical_username(username: str) -> Optional[str]:
    clean = (username or "").strip()
    if not clean:
        return None
    if hasattr(auth_utils, "kullanici_adi_var_mi"):
        exists, canonical = auth_utils.kullanici_adi_var_mi(clean)
        if exists and canonical:
            return canonical
    # Fallback: case-insensitive scan
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT username FROM kullanicilar WHERE LOWER(username) = LOWER(?) LIMIT 1",
            (clean,),
        )
        row = cur.fetchone()
        return row["username"] if row else None
    finally:
        conn.close()


def _are_friends(cursor: sqlite3.Cursor, a: str, b: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM arkadasliklar
        WHERE (LOWER(kullanici) = LOWER(?) AND LOWER(arkadas) = LOWER(?))
           OR (LOWER(kullanici) = LOWER(?) AND LOWER(arkadas) = LOWER(?))
        LIMIT 1
        """,
        (a, b, b, a),
    )
    return cursor.fetchone() is not None


def _add_friendship(cursor: sqlite3.Cursor, a: str, b: str) -> None:
    cursor.execute(
        "INSERT OR IGNORE INTO arkadasliklar (kullanici, arkadas) VALUES (?, ?)",
        (a, b),
    )
    cursor.execute(
        "INSERT OR IGNORE INTO arkadasliklar (kullanici, arkadas) VALUES (?, ?)",
        (b, a),
    )


# --- Arkadaşlık ---

def arkadas_listesini_getir(username: str) -> List[str]:
    user = (username or "").strip()
    if not user:
        return []
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        conn.commit()
        cur.execute(
            """
            SELECT arkadas FROM arkadasliklar
            WHERE LOWER(kullanici) = LOWER(?)
            ORDER BY arkadas COLLATE NOCASE
            """,
            (user,),
        )
        return [row["arkadas"] for row in cur.fetchall()]
    finally:
        conn.close()


def arkadas_sil(kullanici: str, arkadas_adi: str) -> Tuple[bool, str]:
    a = (kullanici or "").strip()
    b = (arkadas_adi or "").strip()
    if not a or not b:
        return False, "Eksik kullanıcı."
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        cur.execute(
            "DELETE FROM arkadasliklar WHERE LOWER(kullanici)=LOWER(?) AND LOWER(arkadas)=LOWER(?)",
            (a, b),
        )
        cur.execute(
            "DELETE FROM arkadasliklar WHERE LOWER(kullanici)=LOWER(?) AND LOWER(arkadas)=LOWER(?)",
            (b, a),
        )
        conn.commit()
        return True, "Arkadaşlık silindi."
    finally:
        conn.close()


def arkadasliklari_birlestir(username: str, friends: List[str]) -> Tuple[bool, str, List[str]]:
    """
    Render ephemeral disk wipe sonrası istemcideki arkadaş listesini sunucuya geri yazar.
    Mevcut kayıtlara MERGE eder (silmez).
    """
    user = (username or "").strip()
    if not user:
        return False, "Kullanıcı yok.", []

    cleaned: List[str] = []
    seen = set()
    for raw in friends or []:
        name = str(raw or "").strip()
        if not name:
            continue
        key = name.lower()
        if key == user.lower() or key in seen:
            continue
        seen.add(key)
        cleaned.append(name)

    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        for friend in cleaned:
            _add_friendship(cur, user, friend)
        conn.commit()
        cur.execute(
            """
            SELECT arkadas FROM arkadasliklar
            WHERE LOWER(kullanici) = LOWER(?)
            ORDER BY arkadas COLLATE NOCASE
            """,
            (user,),
        )
        merged = [row["arkadas"] for row in cur.fetchall()]
        return True, f"{len(cleaned)} arkadaş senkronize edildi.", merged
    finally:
        conn.close()


def arkadaslik_istegi_gonder(gonderen: str, alan: str) -> Tuple[bool, str]:
    g = (gonderen or "").strip()
    a_raw = (alan or "").strip()
    if not g or not a_raw:
        return False, "Eksik alan."
    if g.lower() == a_raw.lower():
        return False, "Kendinize arkadaşlık isteği gönderemezsiniz."

    # DB'de yoksa bile isteği kaydet — karşı taraf giriş yapınca (case-insensitive) görür.
    # Render ephemeral disk / boş DB yüzünden "kayıtlı değil" engeli arkadaşlığı kırıyordu.
    canonical = _canonical_username(a_raw) or a_raw

    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        if _are_friends(cur, g, canonical):
            return False, f"'{canonical}' ile zaten arkadaşsınız."

        cur.execute(
            """
            SELECT id FROM arkadaslik_istekleri
            WHERE LOWER(gonderen)=LOWER(?) AND LOWER(alan)=LOWER(?) AND durum='bekliyor'
            LIMIT 1
            """,
            (g, canonical),
        )
        if cur.fetchone():
            return False, "Bu kişiye zaten bekleyen bir istek gönderilmiş."

        # Karşı taraf size zaten istek göndermişse otomatik kabul
        cur.execute(
            """
            SELECT id FROM arkadaslik_istekleri
            WHERE LOWER(gonderen)=LOWER(?) AND LOWER(alan)=LOWER(?) AND durum='bekliyor'
            LIMIT 1
            """,
            (canonical, g),
        )
        reverse = cur.fetchone()
        if reverse:
            _add_friendship(cur, g, canonical)
            cur.execute(
                "UPDATE arkadaslik_istekleri SET durum='kabul' WHERE id=?",
                (reverse["id"],),
            )
            conn.commit()
            return True, f"{canonical} zaten size istek göndermişti — arkadaş oldunuz!"

        cur.execute(
            "INSERT INTO arkadaslik_istekleri (gonderen, alan, durum) VALUES (?, ?, 'bekliyor')",
            (g, canonical),
        )
        conn.commit()
        return True, f"Arkadaşlık isteği {canonical} kullanıcısına gönderildi."
    finally:
        conn.close()


def bekleyen_istekleri_getir(kullanici_adi: str) -> List[Dict[str, Any]]:
    user = (kullanici_adi or "").strip()
    if not user:
        return []
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        conn.commit()
        cur.execute(
            """
            SELECT id, gonderen FROM arkadaslik_istekleri
            WHERE LOWER(alan)=LOWER(?) AND durum='bekliyor'
            ORDER BY id DESC
            """,
            (user,),
        )
        return [{"id": row["id"], "from": row["gonderen"]} for row in cur.fetchall()]
    finally:
        conn.close()


def istek_yanitla(istek_id: int, kabul_mu: bool, username: str) -> Tuple[bool, str]:
    user = (username or "").strip()
    if not user or not istek_id:
        return False, "Eksik parametre."
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        cur.execute(
            """
            SELECT id, gonderen, alan FROM arkadaslik_istekleri
            WHERE id=? AND LOWER(alan)=LOWER(?) AND durum='bekliyor'
            """,
            (int(istek_id), user),
        )
        row = cur.fetchone()
        if not row:
            return False, "Yetkisiz işlem veya geçersiz istek."

        gonderen, alan = row["gonderen"], row["alan"]
        if kabul_mu:
            _add_friendship(cur, gonderen, alan)
            cur.execute(
                "UPDATE arkadaslik_istekleri SET durum='kabul' WHERE id=?",
                (row["id"],),
            )
            conn.commit()
            return True, f"{gonderen} arkadaş olarak eklendi."
        cur.execute(
            "UPDATE arkadaslik_istekleri SET durum='red' WHERE id=?",
            (row["id"],),
        )
        conn.commit()
        return True, "İstek reddedildi."
    finally:
        conn.close()


# --- Füzyon istekleri ---

def _parse_id_list(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        out = []
        for x in raw:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return _parse_id_list(parsed)
        except Exception:
            pass
        return [p.strip() for p in s.split(",") if p.strip()]
    return []


def _parse_results_json(raw: Any) -> Optional[List[Dict[str, Any]]]:
    if raw is None:
        return None
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except Exception:
            return None
    return None


def _row_to_fusion(row: sqlite3.Row) -> Dict[str, Any]:
    overlap = None
    if row["overlap_json"]:
        try:
            overlap = json.loads(row["overlap_json"])
        except Exception:
            overlap = None
    keys = _row_keys(row)
    sender_lib_raw = row["gonderen_kitaplik"] if "gonderen_kitaplik" in keys else None
    receiver_lib_raw = row["alan_kitaplik"] if "alan_kitaplik" in keys else None
    results_raw = row["sonuclar_json"] if "sonuclar_json" in keys else None
    return {
        "id": row["id"],
        "from": row["gonderen"],
        "to": row["alan"],
        "universe": row["universe"],
        "senderSelections": _parse_id_list(row["gonderen_secimler"]),
        "receiverSelections": _parse_id_list(row["alan_secimler"]) if row["alan_secimler"] else [],
        "senderLibrary": _parse_id_list(sender_lib_raw),
        "receiverLibrary": _parse_id_list(receiver_lib_raw),
        "results": _parse_results_json(results_raw),
        "status": row["durum"],
        "overlap": overlap,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def fuzyon_istegi_olustur(
    gonderen: str,
    alan: str,
    universe: str,
    secimler: List[str],
    kitaplik: List[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    g = (gonderen or "").strip()
    a_raw = (alan or "").strip()
    uni = str(universe or "MOVIES").upper()
    if uni not in ("MOVIES", "SERIES"):
        uni = "MOVIES"
    picks = _parse_id_list(secimler)
    lib = _parse_id_list(kitaplik) if kitaplik is not None else []

    if not g or not a_raw:
        return False, "Eksik kullanıcı.", None
    if g.lower() == a_raw.lower():
        return False, "Kendinize füzyon isteği gönderemezsiniz.", None
    if len(picks) != 5:
        return False, "Tam olarak 5 yapım seçmelisiniz.", None
    if len(set(picks)) != 5:
        return False, "Aynı yapımı birden fazla seçemezsiniz.", None

    canonical = _canonical_username(a_raw) or a_raw

    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        if not _are_friends(cur, g, canonical):
            return False, "Füzyon için önce arkadaş olmalısınız.", None

        cur.execute(
            """
            SELECT id FROM fuzyon_istekleri
            WHERE LOWER(gonderen)=LOWER(?) AND LOWER(alan)=LOWER(?)
              AND universe=? AND durum='bekliyor'
            LIMIT 1
            """,
            (g, canonical, uni),
        )
        if cur.fetchone():
            return False, "Bu arkadaşa zaten bekleyen bir füzyon isteği var.", None

        now = time.time()
        cur.execute(
            """
            INSERT INTO fuzyon_istekleri
            (gonderen, alan, universe, gonderen_secimler, alan_secimler,
             gonderen_kitaplik, durum, created_at, updated_at)
            VALUES (?, ?, ?, ?, NULL, ?, 'bekliyor', ?, ?)
            """,
            (
                g,
                canonical,
                uni,
                json.dumps(picks, ensure_ascii=False),
                json.dumps(lib, ensure_ascii=False) if lib else None,
                now,
                now,
            ),
        )
        conn.commit()
        fid = cur.lastrowid
        cur.execute("SELECT * FROM fuzyon_istekleri WHERE id=?", (fid,))
        row = cur.fetchone()
        return True, f"Füzyon isteği {canonical} kullanıcısına gönderildi.", _row_to_fusion(row)
    finally:
        conn.close()


def bekleyen_fuzyon_istekleri(kullanici: str) -> List[Dict[str, Any]]:
    user = (kullanici or "").strip()
    if not user:
        return []
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        conn.commit()
        cur.execute(
            """
            SELECT * FROM fuzyon_istekleri
            WHERE LOWER(alan)=LOWER(?) AND durum='bekliyor'
            ORDER BY id DESC
            """,
            (user,),
        )
        return [_row_to_fusion(r) for r in cur.fetchall()]
    finally:
        conn.close()


def giden_fuzyon_istekleri(kullanici: str) -> List[Dict[str, Any]]:
    user = (kullanici or "").strip()
    if not user:
        return []
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        conn.commit()
        cur.execute(
            """
            SELECT * FROM fuzyon_istekleri
            WHERE LOWER(gonderen)=LOWER(?) AND durum IN ('bekliyor', 'tamamlandi')
            ORDER BY id DESC
            LIMIT 20
            """,
            (user,),
        )
        return [_row_to_fusion(r) for r in cur.fetchall()]
    finally:
        conn.close()


def tamamlanan_fuzyonlar(kullanici: str) -> List[Dict[str, Any]]:
    user = (kullanici or "").strip()
    if not user:
        return []
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        conn.commit()
        cur.execute(
            """
            SELECT * FROM fuzyon_istekleri
            WHERE (LOWER(gonderen)=LOWER(?) OR LOWER(alan)=LOWER(?))
              AND durum='tamamlandi'
            ORDER BY updated_at DESC
            LIMIT 10
            """,
            (user, user),
        )
        return [_row_to_fusion(r) for r in cur.fetchall()]
    finally:
        conn.close()


def fuzyon_istegi_getir(istek_id: int, username: str) -> Optional[Dict[str, Any]]:
    user = (username or "").strip()
    if not user or not istek_id:
        return None
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        cur.execute("SELECT * FROM fuzyon_istekleri WHERE id=?", (int(istek_id),))
        row = cur.fetchone()
        if not row:
            return None
        if row["gonderen"].lower() != user.lower() and row["alan"].lower() != user.lower():
            return None
        return _row_to_fusion(row)
    finally:
        conn.close()


def fuzyon_istegi_yanitla(
    istek_id: int,
    username: str,
    kabul_mu: bool,
    secimler: Optional[List[str]] = None,
    kitaplik: List[str] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    user = (username or "").strip()
    if not user or not istek_id:
        return False, "Eksik parametre.", None

    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        cur.execute(
            """
            SELECT * FROM fuzyon_istekleri
            WHERE id=? AND LOWER(alan)=LOWER(?) AND durum='bekliyor'
            """,
            (int(istek_id), user),
        )
        row = cur.fetchone()
        if not row:
            return False, "Yetkisiz işlem veya geçersiz füzyon isteği.", None

        now = time.time()
        if not kabul_mu:
            cur.execute(
                "UPDATE fuzyon_istekleri SET durum='red', updated_at=? WHERE id=?",
                (now, row["id"]),
            )
            conn.commit()
            cur.execute("SELECT * FROM fuzyon_istekleri WHERE id=?", (row["id"],))
            return True, "Füzyon isteği reddedildi.", _row_to_fusion(cur.fetchone())

        picks = _parse_id_list(secimler)
        if len(picks) != 5:
            return False, "Kabul için tam olarak 5 yapım seçmelisiniz.", None
        if len(set(picks)) != 5:
            return False, "Aynı yapımı birden fazla seçemezsiniz.", None

        lib = _parse_id_list(kitaplik) if kitaplik is not None else []
        sender_picks = _parse_id_list(row["gonderen_secimler"])
        overlap_ids = [x for x in picks if x in set(sender_picks)]
        overlap_payload = {"ids": overlap_ids, "count": len(overlap_ids)} if overlap_ids else None

        cur.execute(
            """
            UPDATE fuzyon_istekleri
            SET alan_secimler=?, alan_kitaplik=?, durum='tamamlandi',
                overlap_json=?, updated_at=?
            WHERE id=?
            """,
            (
                json.dumps(picks, ensure_ascii=False),
                json.dumps(lib, ensure_ascii=False) if lib else None,
                json.dumps(overlap_payload, ensure_ascii=False) if overlap_payload else None,
                now,
                row["id"],
            ),
        )
        conn.commit()
        cur.execute("SELECT * FROM fuzyon_istekleri WHERE id=?", (row["id"],))
        updated = _row_to_fusion(cur.fetchone())
        msg = "Füzyon seçimleri kaydedildi."
        if overlap_ids:
            msg = f"Uyarı: {len(overlap_ids)} ortak seçim var. Yine de füzyon hesaplanabilir."
        return True, msg, updated
    finally:
        conn.close()


def fuzyon_sonuclari_kaydet(
    istek_id: int,
    username: str,
    results: List[Dict[str, Any]],
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Füzyon öneri sonuçlarını kaydet (yalnızca gönderen veya alan)."""
    user = (username or "").strip()
    if not user or not istek_id:
        return False, "Eksik parametre.", None
    if not isinstance(results, list):
        return False, "Sonuç listesi gerekli.", None

    clean_results: List[Dict[str, Any]] = [r for r in results if isinstance(r, dict)]

    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_tables(cur)
        cur.execute("SELECT * FROM fuzyon_istekleri WHERE id=?", (int(istek_id),))
        row = cur.fetchone()
        if not row:
            return False, "Füzyon isteği bulunamadı.", None
        if row["gonderen"].lower() != user.lower() and row["alan"].lower() != user.lower():
            return False, "Yetkisiz işlem.", None

        now = time.time()
        cur.execute(
            """
            UPDATE fuzyon_istekleri
            SET sonuclar_json=?, updated_at=?
            WHERE id=?
            """,
            (json.dumps(clean_results, ensure_ascii=False), now, row["id"]),
        )
        conn.commit()
        cur.execute("SELECT * FROM fuzyon_istekleri WHERE id=?", (row["id"],))
        return True, "Füzyon sonuçları kaydedildi.", _row_to_fusion(cur.fetchone())
    finally:
        conn.close()
