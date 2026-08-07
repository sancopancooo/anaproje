# -*- coding: utf-8 -*-
"""
🔑 AUTH UTILS (Merkezi Köprü Modülü)
Yerel: kullanicilar1.db | Prod: Turso (TURSO_DATABASE_URL + TURSO_AUTH_TOKEN)
"""

import bcrypt

from user_db import connect_user_db, user_db_backend_name, USER_DB_PATH as DB_PATH


def init_auth_db():
    """Tabloları oluşturur. E-posta sütununu UNIQUE yaparak çakışmayı engeller."""
    conn = connect_user_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS kullanicilar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            email TEXT UNIQUE,
            reset_code TEXT,
            reset_expiry TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()
    print(f"[+] Auth DB: {user_db_backend_name()}")
    _seed_default_accounts()


def _seed_default_accounts():
    """Demo / varsayılan hesapları boş DB'ye yazar (Render restart sonrası)."""
    defaults = [
        ("sancopancoo", "password123", "sanco@example.com"),
        ("adm", "123", "admin@dizimibul.com"),
        ("ahmet_matrix", "123", "ahmet@matrix.com"),
        ("zeynep_dizi", "123", "zeynep@matrix.com"),
        ("can_cinephile", "123", "can@matrix.com"),
        ("neo_matrix", "123", "neo@matrix.com"),
        ("selin_cinema", "123", "selin@matrix.com"),
    ]
    conn = connect_user_db()
    cursor = conn.cursor()
    try:
        for username, password, email in defaults:
            cursor.execute(
                "SELECT id FROM kullanicilar WHERE LOWER(username) = LOWER(?) LIMIT 1",
                (username,),
            )
            if cursor.fetchone():
                continue
            try:
                hashed = hash_password(password)
                cursor.execute(
                    "INSERT INTO kullanicilar (username, password_hash, email) VALUES (?, ?, ?)",
                    (username, hashed, email),
                )
            except Exception:
                pass
        conn.commit()
    finally:
        conn.close()


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password, hashed):
    if isinstance(hashed, str):
        hashed = hashed.encode("utf-8")
    return bcrypt.checkpw(password.encode("utf-8"), hashed)


def kullanici_kontrol_et(username, password):
    user_clean = username.strip()
    conn = connect_user_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT password_hash FROM kullanicilar WHERE LOWER(username) = LOWER(?) LIMIT 1",
        (user_clean,),
    )
    result = cursor.fetchone()
    conn.close()
    if result and check_password(password.strip(), result[0]):
        return True
    return False


def kullanici_adi_var_mi(username):
    """Kullanıcı adının kayıtlı olup olmadığını büyük/küçük harf duyarsız kontrol eder."""
    user_clean = (username or "").strip()
    if not user_clean:
        return False, None
    conn = connect_user_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username FROM kullanicilar WHERE LOWER(username) = LOWER(?) LIMIT 1",
        (user_clean,),
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return True, row[0]
    return False, None


def kayit_ol(username, password, email):
    """Kayıt. E-posta opsiyonel; boşsa kullanıcıya özel placeholder kullanılır."""
    user_clean = username.strip()
    email_clean = (email or "").strip() or f"{user_clean.lower()}@local.dizimibul"

    conn = connect_user_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM kullanicilar WHERE LOWER(username) = LOWER(?) LIMIT 1",
        (user_clean,),
    )
    if cursor.fetchone():
        conn.close()
        return False, "⚠️ Bu kullanıcı adı zaten alınmış!"

    if email_clean and not email_clean.endswith("@local.dizimibul"):
        cursor.execute("SELECT id FROM kullanicilar WHERE email = ?", (email_clean,))
        if cursor.fetchone():
            conn.close()
            return False, "⚠️ Bu e-posta adresiyle zaten kayıtlı bir hesap var!"

    try:
        hashed = hash_password(password.strip())
        cursor.execute(
            "INSERT INTO kullanicilar (username, password_hash, email) VALUES (?, ?, ?)",
            (user_clean, hashed, email_clean),
        )
        conn.commit()
        return True, "🎉 Başarıyla kayıt oldun!"
    except Exception as e:
        return False, f"❌ Hata: {e}"
    finally:
        conn.close()


def geri_bildirim_kaydet(username, mesaj):
    """Kullanıcının yazdığı geri bildirimi kullanıcı DB içinde depolar."""
    conn = connect_user_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS geri_bildirimler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            mesaj TEXT,
            tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    try:
        cursor.execute(
            "INSERT INTO geri_bildirimler (username, mesaj) VALUES (?, ?)",
            (username.strip(), mesaj.strip()),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"🚨 Geri Bildirim Kayıt Hatası: {e}")
        return False
    finally:
        conn.close()


def sifre_sifirlama_talebi(email):
    import random
    from fonksiyonlar import mail_gonder

    kod = str(random.randint(100000, 999999))
    conn = connect_user_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE kullanicilar SET reset_code = ?, reset_expiry = DATETIME('now', '+10 minutes') WHERE email = ?",
        (kod, email),
    )
    conn.commit()
    conn.close()

    if mail_gonder(email, kod):
        return True
    return False


def sifre_dogrula_ve_guncelle(email, kod, yeni_sifre):
    conn = connect_user_db()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM kullanicilar WHERE email = ? AND reset_code = ? AND reset_expiry > DATETIME('now')",
        (email, kod),
    )
    if cursor.fetchone():
        hashed = hash_password(yeni_sifre)
        cursor.execute(
            "UPDATE kullanicilar SET password_hash = ?, reset_code = NULL WHERE email = ?",
            (hashed, email),
        )
        conn.commit()
        conn.close()
        return True, "✅ Şifren başarıyla güncellendi!"
    else:
        conn.close()
        return False, "❌ Geçersiz veya süresi dolmuş kod!"
