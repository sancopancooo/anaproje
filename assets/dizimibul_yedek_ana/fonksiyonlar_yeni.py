# -*- coding: utf-8 -*-
"""
🎬 dizimibul - Merkezi Fonksiyonlar Kütüphanesi (fonksiyonlar_yeni.py)
Bu dosya projedeki tüm arka plan mantığını, veritabanı işlemlerini, kullanıcı giriş/kayıt 
işlemlerini ve yapay zeka/öneri motoru işlevlerini tek bir çatı altında toplar.
"""

import os
import re
import json
import time
import sqlite3
import bcrypt
import logging
import hashlib
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import List, Dict, Set, Any, Tuple

import pandas as pd
import numpy as np
import streamlit as st
from openai import OpenAI
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Loglama Ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Çevre Değişkenleri Yükle
load_dotenv()

# Yapay Zeka API Bağlantısı (Merkez Üs Kontrolü)
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY")
)

# 🔌 GLOBAL AI KILL-SWITCH
# Kota dolduğunda / bakım sırasında .env'den AI_AKTIF=false yapılarak
# canlı üretim tamamen kapatılabilir; site çökmez, sadece geçici mesajlar döner.
AI_AKTIF = os.getenv("AI_AKTIF", "true").lower() == "true"

# 🧯 RETRY-STORM KORUMASI
# Bir dizi için üretim başarısız olduğunda (429 / kota / bağlantı hatası), o dizi
# için bir süre boyunca tekrar API'ye gidilmez; DB'ye ise HİÇBİR ZAMAN sahte/geçici
# içerik yazılmaz — sadece gerçek AI çıktısı kalıcı olur. Süre dolunca otomatik tekrar denenir.
_AI_BASARISIZ_DENEME_CACHE: Dict[str, float] = {}
AI_BASARISIZLIK_COOLDOWN_SANIYE = 300  # 5 dakika

def _ai_deneme_uygun_mu(anahtar: str) -> bool:
    """Bu anahtar (örn. 'ozet:Breaking Bad') için son başarısız denemeden beri yeterli süre geçti mi?"""
    son_deneme = _AI_BASARISIZ_DENEME_CACHE.get(anahtar)
    if son_deneme is None:
        return True
    return (time.time() - son_deneme) >= AI_BASARISIZLIK_COOLDOWN_SANIYE

def _ai_basarisiz_isaretle(anahtar: str) -> None:
    _AI_BASARISIZ_DENEME_CACHE[anahtar] = time.time()

# Global Veritabanı Tanımları
import shutil
PERSISTENT_DIR = "/app/data"
if os.path.exists(PERSISTENT_DIR):
    DB_ADI = os.path.join(PERSISTENT_DIR, "diziler_veritabani.db")
    DB_KULLANICILAR = os.path.join(PERSISTENT_DIR, "kullanicilar1.db")
    
    # Eğer kalıcı diskte henüz veritabanı yoksa, depodaki ilk veritabanını oraya kopyalayalım
    if not os.path.exists(DB_ADI) and os.path.exists("diziler_veritabani.db"):
        shutil.copy("diziler_veritabani.db", DB_ADI)
    if not os.path.exists(DB_KULLANICILAR) and os.path.exists("kullanicilar1.db"):
        shutil.copy("kullanicilar1.db", DB_KULLANICILAR)
else:
    DB_ADI = "diziler_veritabani.db"
    DB_KULLANICILAR = "kullanicilar1.db"


# JSON Config Yükleme
CONFIG_PATH = "config.json"
KELIME_KOK_VE_VARYASYONLARI: Dict[str, List[str]] = {}
ATMOSPHERE_ESLESME: Dict[str, List[str]] = {}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            KELIME_KOK_VE_VARYASYONLARI = config_data.get("KELIME_KOK_VE_VARYASYONLARI", {})
            ATMOSPHERE_ESLESME = config_data.get("ATMOSPHERE_ESLESME", {})
    except Exception as e:
        logger.error(f"Config yükleme hatası: {e}")

# Sözlük Yükleme
try:
    from sozlukler import SINONIM_MAP
except ImportError:
    SINONIM_MAP = {}


# ==============================================================================
# ------- SECTION 1: VERİTABANI İLKLENDİRME VE GÜNCELLEME -------
# ==============================================================================

def veritabanini_ilklendir():
    """Kitaplık, kullanıcılar ve arkadaşlık tablolarını SQLite üzerinde ilklendirir (WAL modunu açarak eşzamanlılığı artırır)."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute('''CREATE TABLE IF NOT EXISTS kitaplik 
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, dizi_isim TEXT, 
                           durum TEXT, izlenen_sezon INTEGER, izlenen_bolum INTEGER DEFAULT 1, 
                           eklenme_tarihi TIMESTAMP DEFAULT CURRENT_TIMESTAMP, favori INTEGER DEFAULT 0, puan INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS kullanicilar 
                          (username TEXT PRIMARY KEY, password_hash TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS arkadasliklar 
                          (user_id TEXT, arkadas_id TEXT)''')
        conn.commit()

def veritabani_sutunlarini_guncelle():
    """Dizi havuzu ve kitaplık tablolarına eksik kolonları ekler."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        
        # Oyuncu kolonları
        try:
            cursor.execute("ALTER TABLE dizi_havuzu ADD COLUMN oyuncular_gercek TEXT")
        except sqlite3.OperationalError:
            pass
            
        try:
            cursor.execute("ALTER TABLE dizi_havuzu ADD COLUMN oyuncular_rol TEXT")
        except sqlite3.OperationalError:
            pass
            
        # Puan kolonu
        try:
            cursor.execute("ALTER TABLE kitaplik ADD COLUMN puan INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # "Neden İzlemelisin" kalıcı önbellek kolonu (JSON liste olarak saklanır)
        try:
            cursor.execute("ALTER TABLE diziler ADD COLUMN neden_izlemeli TEXT")
        except sqlite3.OperationalError:
            pass

        conn.commit()

def dizi_oyuncu_bilgilerini_doldur(dizi_isim, gercek_isimler, karakter_isimler):
    """Oyuncu bilgilerini günceller."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE diziler 
            SET oyuncular_gercek = ?, oyuncular_rol = ? 
            WHERE isim = ?
        """, (gercek_isimler, karakter_isimler, dizi_isim))
        conn.commit()


# ==============================================================================
# ------- SECTION 2: AUTH UTILS (KULLANICI GİRİŞ / KAYIT / ŞİFRE) -------
# ==============================================================================

def init_auth_db():
    """Kullanıcılar veri tabanını ve tablosunu ilk kez ayağa kaldıran fonksiyon (WAL modunu açarak eşzamanlılığı artırır)."""
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kullanicilar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                email TEXT UNIQUE,
                reset_code TEXT,
                reset_expiry TIMESTAMP
            )
        ''')
        # E-posta relay ve brute force koruması için ek güvenlik kolonları
        try:
            cursor.execute("ALTER TABLE kullanicilar ADD COLUMN reset_attempts INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE kullanicilar ADD COLUMN login_attempts INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE kullanicilar ADD COLUMN last_login_attempt TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE kullanicilar ADD COLUMN last_reset_request REAL")
        except sqlite3.OperationalError:
            pass
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS oturumlar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                session_token TEXT UNIQUE,
                expires_at TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_sorgulari (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                timestamp REAL
            )
        ''')
        conn.commit()

def hash_password(password):
    """Kullanıcı şifresini bcrypt ile güvenli şekilde hashler."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password, hashed):
    """Girilmiş şifre ile veri tabanındaki hash'i doğrular."""
    if isinstance(hashed, str):
        hashed = hashed.encode('utf-8')
    return bcrypt.checkpw(password.encode('utf-8'), hashed)

def kullanici_kontrol_et(username, password):
    """Kullanıcı giriş kontrolü yapar (5 başarısız denemede 60 saniye kilit korumalı)."""
    import datetime
    user_clean = username.strip()
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        
        # Kullanıcının giriş denemelerini sorgula
        cursor.execute("SELECT password_hash, login_attempts, last_login_attempt FROM kullanicilar WHERE username = ?", (user_clean,))
        row = cursor.fetchone()
        if not row:
            return False # Kullanıcı yoksa doğrudan False
            
        hashed, attempts, last_attempt = row
        
        # Eğer kilitliyse süreyi kontrol et (Kademeli/Progresif kilit süreleri)
        if attempts >= 5 and last_attempt:
            # 5. deneme -> 1 dakika
            # 6. deneme -> 5 dakika
            # 7. deneme -> 30 dakika
            # 8+ deneme -> 24 saat kilit
            if attempts == 5:
                kilit_saniyesi = 60
            elif attempts == 6:
                kilit_saniyesi = 300
            elif attempts == 7:
                kilit_saniyesi = 1800
            else:
                kilit_saniyesi = 86400
                
            try:
                dt_last = datetime.datetime.strptime(last_attempt, "%Y-%m-%d %H:%M:%S")
            except:
                dt_last = datetime.datetime.now()
            saniye_gecen = (datetime.datetime.now() - dt_last).total_seconds()
            if saniye_gecen < kilit_saniyesi:
                kalan_sure = int(kilit_saniyesi - saniye_gecen)
                if kalan_sure >= 3600:
                    sure_metni = f"{kalan_sure // 3600} saat"
                elif kalan_sure >= 60:
                    sure_metni = f"{kalan_sure // 60} dakika"
                else:
                    sure_metni = f"{kalan_sure} saniye"
                raise PermissionError(f"⚠️ Çok fazla hatalı giriş denemesi! Hesabınız {sure_metni} süreyle kilitlendi.")
        
        # Şifre kontrolü
        if check_password(password.strip(), hashed):
            # Giriş başarılı: Sayacı sıfırla
            cursor.execute("UPDATE kullanicilar SET login_attempts = 0, last_login_attempt = NULL WHERE username = ?", (user_clean,))
            conn.commit()
            return True
        else:
            # Giriş başarısız: Sayacı arttır ve son deneme zamanını güncelle
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE kullanicilar SET login_attempts = login_attempts + 1, last_login_attempt = ? WHERE username = ?", (now_str, user_clean))
            conn.commit()
            return False

def oturum_olustur(username, expires_days=30):
    """Kullanıcı için rastgele, benzersiz bir oturum token'ı oluşturur ve DB'ye yazar (Oturum Güvenliği)."""
    import secrets
    import datetime
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.datetime.now() + datetime.timedelta(days=expires_days)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO oturumlar (username, session_token, expires_at) VALUES (?, ?, ?)",
                       (username.strip(), token, expires_at))
        conn.commit()
    return token

def oturum_dogrula(token):
    """Oturum token'ını doğrular, geçerliyse kullanıcı adını döner, geçersizse None döner."""
    import datetime
    if not token or not isinstance(token, str):
        return None
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, expires_at FROM oturumlar WHERE session_token = ?", (token.strip(),))
        row = cursor.fetchone()
        if not row:
            return None
        username, expires_at_str = row
        try:
            expires_at = datetime.datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
        except:
            expires_at = datetime.datetime.now()
            
        if datetime.datetime.now() > expires_at:
            # Süresi geçmiş oturumu temizle
            cursor.execute("DELETE FROM oturumlar WHERE session_token = ?", (token.strip(),))
            conn.commit()
            return None
        return username

def oturum_sil(token):
    """Kullanıcı çıkış yaptığında oturum token'ını DB'den tamamen siler."""
    if not token or not isinstance(token, str):
        return
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM oturumlar WHERE session_token = ?", (token.strip(),))
        conn.commit()

def kayit_ol(username, password, email):
    """Veri tabanına yeni kullanıcı kaydı açar (Şifre uzunluk kontrolü ve çakışma kontrolleriyle)."""
    user_clean = username.strip()
    email_clean = email.strip()
    pass_clean = password.strip()
    
    import re
    # 🔒 Kullanıcı Adı Karakter ve Uzunluk Kontrolü (3-15 karakter, sadece harf, rakam ve alt çizgi)
    if not re.match(r"^[a-zA-Z0-9_]{3,15}$", user_clean):
        return False, "⚠️ Kullanıcı adı 3-15 karakter uzunluğunda olmalı ve sadece İngilizce harfler, rakamlar ve alt çizgi (_) içermelidir!"
        
    # 🔒 Hesap Güvenliği için Şifre Uzunluk Kontrolü (Minimum 8 Karakter)
    if len(pass_clean) < 8:
        return False, "⚠️ Şifreniz en az 8 karakter uzunluğunda olmalıdır!"
        
    email_val = email_clean if email_clean else None
        
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM kullanicilar WHERE username = ?", (user_clean,))
        if cursor.fetchone():
            return False, "⚠️ Bu kullanıcı adı zaten alınmış!"
        
        if email_val:
            cursor.execute("SELECT id FROM kullanicilar WHERE email = ?", (email_val,))
            if cursor.fetchone():
                return False, "⚠️ Bu e-posta adresiyle zaten kayıtlı bir hesap var!"
        
        try:
            hashed = hash_password(pass_clean)
            cursor.execute(
                "INSERT INTO kullanicilar (username, password_hash, email) VALUES (?, ?, ?)", 
                (user_clean, hashed, email_val)
            )
            conn.commit()
            return True, "🎉 Başarıyla kayıt oldun!"
        except Exception as e:
            return False, f"❌ Hata: {e}"

def geri_bildirim_kaydet(username, mesaj):
    """Kullanıcının yazdığı geri bildirimi kullanicilar1.db içinde depolar."""
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS geri_bildirimler (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT,
                mesaj TEXT,
                tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        try:
            cursor.execute(
                "INSERT INTO geri_bildirimler (username, mesaj) VALUES (?, ?)",
                (username.strip(), mesaj.strip())
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"🚨 Geri Bildirim Kayıt Hatası: {e}")
            return False

def sifre_sifirlama_talebi(email):
    """Şifre sıfırlama kodu oluşturur ve e-posta gönderir (Spam Relay, Enumeration ve SMTP Hız Korumalı)."""
    import random
    import time
    
    email_clean = email.strip()
    kod = str(random.randint(100000, 999999))
    current_time = time.time()
    
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        
        # 🛡️ Güvenlik ve E-Posta Relay Koruması: E-posta adresi DB'de var mı kontrol ediyoruz
        cursor.execute("SELECT id, last_reset_request FROM kullanicilar WHERE email = ?", (email_clean,))
        row = cursor.fetchone()
        if not row:
            # E-posta kayıtlı değilse mail göndermiyoruz, ama hacker'ların/saldırganların
            # e-posta tespiti yapmasını engellemek için başarılıymış gibi True dönüyoruz.
            return True
            
        u_id, last_request = row
        if last_request is not None:
            try:
                last_req_val = float(last_request)
                if current_time - last_req_val < 60.0:
                    raise PermissionError("⚠️ E-posta gönderme limiti aşıldı. Lütfen yeni bir kod istemeden önce 60 saniye bekleyin.")
            except ValueError:
                pass
            
        cursor.execute("UPDATE kullanicilar SET reset_code = ?, reset_expiry = DATETIME('now', '+10 minutes'), reset_attempts = 0, last_reset_request = ? WHERE id = ?", (kod, current_time, u_id))
        conn.commit()
    
    if mail_gonder(email_clean, kod):
        return True
    return False

def sifre_dogrula_ve_guncelle(email, kod, yeni_sifre):
    """Sıfırlama kodunu doğrular ve şifreyi günceller (Brute Force Korumalı)."""
    email_clean = email.strip()
    kod_clean = kod.strip()
    yeni_pass = yeni_sifre.strip()
    
    if len(yeni_pass) < 8:
        return False, "⚠️ Yeni şifreniz en az 8 karakter uzunluğunda olmalıdır!"
        
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        
        # Kullanıcının mevcut hatalı deneme sayısını ve aktif kod durumunu kontrol et
        cursor.execute("SELECT id, reset_attempts, reset_code, reset_expiry FROM kullanicilar WHERE email = ?", (email_clean,))
        row = cursor.fetchone()
        if not row:
            return False, "❌ Bu e-posta adresiyle kayıtlı bir kullanıcı bulunamadı!"
            
        u_id, attempts, db_code, expiry = row
        
        # Eğer hatalı deneme 5 veya daha fazlaysa kodu tamamen bloke et
        if attempts >= 5:
            cursor.execute("UPDATE kullanicilar SET reset_code = NULL WHERE id = ?", (u_id,))
            conn.commit()
            return False, "❌ Çok fazla hatalı deneme nedeniyle sıfırlama kodu bloke edildi. Lütfen yeni bir kod isteyin!"
            
        # Kod doğruluğunu ve süresini kontrol et
        cursor.execute("SELECT id FROM kullanicilar WHERE email = ? AND reset_code = ? AND reset_expiry > DATETIME('now')", (email_clean, kod_clean))
        if cursor.fetchone():
            hashed = hash_password(yeni_pass)
            cursor.execute("UPDATE kullanicilar SET password_hash = ?, reset_code = NULL, reset_attempts = 0 WHERE email = ?", (hashed, email_clean))
            conn.commit()
            return True, "✅ Şifreniz başarıyla güncellendi!"
        else:
            # Hatalı deneme sayısını arttır
            cursor.execute("UPDATE kullanicilar SET reset_attempts = reset_attempts + 1 WHERE id = ?", (u_id,))
            conn.commit()
            
            kalan = 5 - (attempts + 1)
            if kalan <= 0:
                cursor.execute("UPDATE kullanicilar SET reset_code = NULL WHERE id = ?", (u_id,))
                conn.commit()
                return False, "❌ Çok fazla hatalı deneme! Sıfırlama kodu bloke edildi."
                
            return False, f"❌ Geçersiz veya süresi dolmuş kod! Kalan deneme hakkı: {kalan}"

def mail_gonder(alici_email, kod):
    """SMTP üzerinden şifre sıfırlama kodu gönderir."""
    msg = EmailMessage()
    msg.set_content(f"Dizi Asistanı şifre sıfırlama kodunuz: {kod}\nBu kod 10 dakika geçerlidir.")
    msg['Subject'] = 'Dizi Asistanı Şifre Sıfırlama'
    msg['From'] = "dizimibul@gmail.com"
    msg['To'] = alici_email

    email_pass = os.getenv("EMAIL_PASS")
    if not email_pass:
        print("Mail hatası: EMAIL_PASS environment değişkeni bulunamadı.")
        return False

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login("dizimibul@gmail.com", email_pass) 
            smtp.send_message(msg)
        return True
    except Exception as e:
        print(f"Mail hatası: {e}")
        return False


# ==============================================================================
# ------- SECTION 3: KİTAPLIK VE TAKİP OPERASYONLARI -------
# ==============================================================================

def kullanıcı_kitaplığını_getir(username: str) -> pd.DataFrame:
    """Kullanıcının kitaplık verilerini en son eklenenden başlayarak Pandas DataFrame olarak döner."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        return pd.read_sql_query("SELECT * FROM kitaplik WHERE user_id = ? ORDER BY eklenme_tarihi DESC", conn, params=(username,))

def kitapliga_dizi_ekle_veya_güncelle(username: str, dizi_isim: str, durum: str, sezon: int, bolum: int) -> bool:
    """Dizi kitaplıkta varsa hiçbir şey yapma (False), yoksa yeni kayıt aç (True)."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM kitaplik WHERE user_id = ? AND dizi_isim = ?", (username, dizi_isim))
        var_mi = cursor.fetchone()
        
        if var_mi:
            print(f"{dizi_isim} zaten kitaplıkta mevcut!")
            return False 
        else:
            tarih_bilgisi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO kitaplik (user_id, dizi_isim, durum, izlenen_sezon, izlenen_bolum, eklenme_tarihi) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (username, dizi_isim, durum, sezon, bolum, tarih_bilgisi))
            conn.commit()
            return True

def kitapliktan_kayit_sil(kayit_id: int, username: str):
    """Kullanıcının kitaplığından belirtilen kayıt ID'sine sahip diziyi siler (IDOR Korumalı)."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        conn.execute("DELETE FROM kitaplik WHERE id = ? AND user_id = ?", (kayit_id, username.strip()))
        conn.commit()

def kitaplik_ilerleme_guncelle(kayit_id, yeni_sezon, yeni_bolum, dizi_isim, dizi_havuzu_df, yeni_puan=0, username=None):
    """Kitaplıktaki ilerlemeyi ve diziye verilen puanı günceller (IDOR Korumalı)."""
    meta = dizi_havuzu_df[dizi_havuzu_df['isim'] == dizi_isim].iloc[0]
    son_sezon = int(meta['sezon_sayisi'])
    bolum_listesi = [int(x) for x in str(meta['sezon_bolum_haritasi']).split(',')]
    son_bolum = bolum_listesi[yeni_sezon - 1]
    
    yeni_durum = "İzledim" if (yeni_sezon == son_sezon and yeni_bolum == son_bolum) else "İzliyorum"
    
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        if username:
            cursor.execute("""
                UPDATE kitaplik 
                SET izlenen_sezon = ?, izlenen_bolum = ?, durum = ?, puan = ?
                WHERE id = ? AND user_id = ?
            """, (yeni_sezon, yeni_bolum, yeni_durum, yeni_puan, kayit_id, username.strip()))
        else:
            cursor.execute("""
                UPDATE kitaplik 
                SET izlenen_sezon = ?, izlenen_bolum = ?, durum = ?, puan = ?
                WHERE id = ?
            """, (yeni_sezon, yeni_bolum, yeni_durum, yeni_puan, kayit_id))
        conn.commit()

def toplam_izleme_suresini_hesapla(kitaplik_df, dizi_havuzu_df):
    """Kullanıcının kitaplığındaki verilere dayanarak toplam kaç gün/saat/dakika dizi izlediğini hesaplar."""
    toplam_dakika = 0
    for idx, row in kitaplik_df.iterrows():
        eslesen = dizi_havuzu_df[dizi_havuzu_df['isim'] == row['dizi_isim']]
        if eslesen.empty: continue
        gercek_sure = int(eslesen.iloc[0]['gercek_bolum_sureleri'])
        if row['durum'] == "İzledim":
            toplam_dakika += (int(eslesen.iloc[0]['toplam_bolum_sayisi']) * gercek_sure)
        else:
            toplam_dakika += (int(row['izlenen_bolum']) * gercek_sure)
            
    toplam_saat, dk = divmod(toplam_dakika, 60)
    gun, saat = divmod(toplam_saat, 24)
    
    if gun > 0:
        sure_metni = f"{gun} Gün {saat} Saat {dk} Dakika"
    else:
        sure_metni = f"{saat} Saat {dk} Dakika"
        
    return sure_metni, len(kitaplik_df)

def kullanicinin_listesini_getir(username, tablo_adi):
    """Beğenilenler veya Gizlenenler listesini döner."""
    if tablo_adi not in ["begenilenler", "gizlenenler"]:
        raise ValueError("Geçersiz tablo adı")
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute(f"SELECT dizi_isim FROM {tablo_adi} WHERE username = ?", (username,))
        return [row[0] for row in cursor.fetchall()]

def dizi_islem_kaydet(username, dizi_isim, tablo_adi):
    """Kullanıcının diziye dair etkileşimini (beğenme, gizleme) kaydeder."""
    if tablo_adi not in ["begenilenler", "gizlenenler"]:
        raise ValueError("Geçersiz tablo adı")
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        query = f"INSERT OR IGNORE INTO {tablo_adi} (username, dizi_isim) VALUES (?, ?)"
        cursor.execute(query, (username, dizi_isim))
        conn.commit()

def dizi_listeden_sil(username, dizi_isim, tablo_adi):
    """Kullanıcının beğenilen/gizlenen listesinden diziyi çıkarır."""
    if tablo_adi not in ["begenilenler", "gizlenenler"]:
        raise ValueError("Geçersiz tablo adı")
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {tablo_adi} WHERE username = ? AND dizi_isim = ?", (username, dizi_isim))
        conn.commit()


# ==============================================================================
# ------- SECTION 4: FAVORİ YÖNETİM OPERASYONLARI -------
# ==============================================================================

def kullanıcı_favorilerini_getir(username):
    """Kullanıcının favori dizilerini favoriler tablosundan detaylarıyla çeker."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        query = "SELECT dizi_adi as dizi_isim, id as kitaplik_id FROM favoriler WHERE username = ?"
        df = pd.read_sql_query(query, conn, params=(username,))
    return df

def favoriye_ekle(username, dizi_adi):
    """Diziyi favoriler tablosuna kaydeder."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM favoriler WHERE username = ? AND dizi_adi = ?", (username, dizi_adi))
        if cursor.fetchone():
            return False
        cursor.execute("INSERT INTO favoriler (username, dizi_adi) VALUES (?, ?)", (username, dizi_adi))
        conn.commit()
    return True

def favori_sil(username, dizi_adi):
    """Diziyi favoriler tablosundan siler."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM favoriler WHERE username = ? AND dizi_adi = ?", (username, dizi_adi))
        conn.commit()


# ==============================================================================
# ------- SECTION 5: SOSYAL KATMAN VE ARKADAŞLIK SİSTEMİ -------
# ==============================================================================

def arkadas_listesini_getir(username: str) -> List[str]:
    """Kullanıcının onaylanmış arkadaş listesini kullanicilar1.db üzerinden getirir."""
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        # Tabloyu otomatik oluştur
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS arkadasliklar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kullanici TEXT,
                arkadas TEXT,
                UNIQUE(kullanici, arkadas)
            )
        ''')
        conn.commit()
        cursor.execute("SELECT arkadas FROM arkadasliklar WHERE kullanici = ?", (username.strip(),))
        rows = cursor.fetchall()
    return [row[0] for row in rows]

def arkadas_ekle(kullanici, arkadas_adi) -> Tuple[bool, str]:
    """Yeni bir arkadaşlık ilişkisini her iki veritabanına da çift taraflı kaydeder (Bütünlük ve Senkronizasyon için)."""
    k_clean = kullanici.strip()
    a_clean = arkadas_adi.strip()
    
    if k_clean == a_clean:
        return False, "⚠️ Kendinizi arkadaş olarak ekleyemezsiniz!"
        
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn_user:
        cur_user = conn_user.cursor()
        cur_user.execute("SELECT username FROM kullanicilar WHERE username = ?", (a_clean,))
        user_exists = cur_user.fetchone()
        
        if not user_exists:
            return False, f"❌ '{a_clean}' adında bir kullanıcı sistemde kayıtlı değil!"
            
        try:
            # 1. kullanicilar1.db'ye çift taraflı arkadaş ekleme
            cur_user.execute("INSERT INTO arkadasliklar (kullanici, arkadas) VALUES (?, ?)", (k_clean, a_clean))
            cur_user.execute("INSERT INTO arkadasliklar (kullanici, arkadas) VALUES (?, ?)", (a_clean, k_clean))
            conn_user.commit()
            
            # 2. diziler_veritabanı.db'ye çift taraflı arkadaş ekleme
            with sqlite3.connect(DB_ADI, timeout=30.0) as conn_dizi:
                cur_dizi = conn_dizi.cursor()
                cur_dizi.execute("CREATE TABLE IF NOT EXISTS arkadasliklar (user_id TEXT, arkadas_id TEXT)")
                cur_dizi.execute("INSERT OR IGNORE INTO arkadasliklar (user_id, arkadas_id) VALUES (?, ?)", (k_clean, a_clean))
                cur_dizi.execute("INSERT OR IGNORE INTO arkadasliklar (user_id, arkadas_id) VALUES (?, ?)", (a_clean, k_clean))
                conn_dizi.commit()
                
            return True, f"🎉 {a_clean} başarıyla arkadaş olarak eklendi!"
        except sqlite3.IntegrityError:
            return False, "⚠️ Bu kullanıcı zaten arkadaş listenizde mevcut."

def arkadas_sil(kullanici, arkadas_adi) -> bool:
    """Arkadaşlığı her iki veritabanından da çift taraflı olarak tamamen siler."""
    k_clean = kullanici.strip()
    a_clean = arkadas_adi.strip()
    
    # 1. kullanicilar1.db'den sil
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn_user:
        cur_user = conn_user.cursor()
        cur_user.execute("DELETE FROM arkadasliklar WHERE kullanici = ? AND arkadas = ?", (k_clean, a_clean))
        cur_user.execute("DELETE FROM arkadasliklar WHERE kullanici = ? AND arkadas = ?", (a_clean, k_clean))
        conn_user.commit()
        
    # 2. diziler_veritabanı.db'den sil
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn_dizi:
        cur_dizi = conn_dizi.cursor()
        cur_dizi.execute("DELETE FROM arkadasliklar WHERE user_id = ? AND arkadas_id = ?", (k_clean, a_clean))
        cur_dizi.execute("DELETE FROM arkadasliklar WHERE user_id = ? AND arkadas_id = ?", (a_clean, k_clean))
        conn_dizi.commit()
        
    return True

def arkadaslik_istegi_gonder(gonderen, alan) -> Tuple[bool, str]:
    """Kullanıcıya 'bekliyor' durumunda arkadaşlık isteği gönderir."""
    g_clean = gonderen.strip()
    a_clean = alan.strip()
    
    if g_clean == a_clean:
        return False, "⚠️ Kendinize arkadaşlık isteği gönderemezsiniz!"
        
    # 1. Alıcı kullanıcı kayıtlı mı kontrol et
    try:
        with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn_user:
            cur_user = conn_user.cursor()
            cur_user.execute("SELECT username FROM kullanicilar WHERE username = ?", (a_clean,))
            user_exists = cur_user.fetchone()
            
            if not user_exists:
                return False, f"❌ '{a_clean}' adında bir kullanıcı sistemde kayıtlı değil!"
                
            # 2. Zaten arkadaş mı kontrolü
            cur_user.execute("SELECT 1 FROM arkadasliklar WHERE kullanici = ? AND arkadas = ?", (g_clean, a_clean))
            already_friends = cur_user.fetchone()
            
            if already_friends:
                return False, f"⚠️ '{a_clean}' ile zaten arkadaşsınız!"
    except Exception as e:
        print(f"Kullanıcı kontrolü sırasında hata: {e}")
        
    # 3. İstek gönderme/Zaten var mı kontrolü
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        
        # Tablo yoksa oluştur
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS arkadaslik_istekleri (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gonderen TEXT,
                alan TEXT,
                durum TEXT DEFAULT 'bekliyor'
            )
        ''')
        conn.commit()
        
        # Zaten bekleyen istek var mı?
        cursor.execute("SELECT id FROM arkadaslik_istekleri WHERE gonderen=? AND alan=? AND durum='bekliyor'", (g_clean, a_clean))
        if cursor.fetchone():
            return False, "⚠️ Bu kişiye zaten bir istek göndermişsin!"
            
        cursor.execute("INSERT INTO arkadaslik_istekleri (gonderen, alan) VALUES (?, ?)", (g_clean, a_clean))
        conn.commit()
    return True, "✅ İstek gönderildi!"

def bekleyen_istekleri_getir(kullanici_adi) -> List[Tuple[int, str]]:
    """Sana gelen 'bekliyor' durumundaki istekleri listeler."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        
        # Tablo yoksa oluştur
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS arkadaslik_istekleri (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gonderen TEXT,
                alan TEXT,
                durum TEXT DEFAULT 'bekliyor'
            )
        ''')
        conn.commit()
        
        cursor.execute("SELECT id, gonderen FROM arkadaslik_istekleri WHERE alan = ? AND durum = 'bekliyor'", (kullanici_adi,))
        istekler = cursor.fetchall()
    return istekler

def istek_yanitla(istek_id, kabul_mu, username):
    """Gelen arkadaşlık isteğini yanıtlar ve kabul durumunda arkadaşlığı her iki DB'ye de işler (IDOR Korumalı)."""
    username_clean = username.strip()
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn_dizi:
        cur_dizi = conn_dizi.cursor()
        
        # 🛡️ IDOR Koruması: İsteğin alıcısı (alan) gerçekten oturum açmış kullanıcı mı kontrol et
        cur_dizi.execute("SELECT gonderen, alan FROM arkadaslik_istekleri WHERE id = ? AND alan = ?", (istek_id, username_clean))
        res = cur_dizi.fetchone()
        if not res:
            return False, "❌ Yetkisiz işlem veya geçersiz istek!"
            
        gonderen, alan = res
        
        if kabul_mu:
            # 1. diziler_veritabanı.db'ye çift taraflı ekle
            cur_dizi.execute("CREATE TABLE IF NOT EXISTS arkadasliklar (user_id TEXT, arkadas_id TEXT)")
            cur_dizi.execute("INSERT OR IGNORE INTO arkadasliklar (user_id, arkadas_id) VALUES (?, ?)", (gonderen, alan))
            cur_dizi.execute("INSERT OR IGNORE INTO arkadasliklar (user_id, arkadas_id) VALUES (?, ?)", (alan, gonderen))
            
            # 2. kullanicilar1.db'ye çift taraflı ekle
            with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn_user:
                cur_user = conn_user.cursor()
                cur_user.execute('''
                    CREATE TABLE IF NOT EXISTS arkadasliklar (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        kullanici TEXT,
                        arkadas TEXT,
                        UNIQUE(kullanici, arkadas)
                    )
                ''')
                cur_user.execute("INSERT OR IGNORE INTO arkadasliklar (kullanici, arkadas) VALUES (?, ?)", (gonderen, alan))
                cur_user.execute("INSERT OR IGNORE INTO arkadasliklar (kullanici, arkadas) VALUES (?, ?)", (alan, gonderen))
                conn_user.commit()
                
        # İsteği güncelle
        cur_dizi.execute("UPDATE arkadaslik_istekleri SET durum = ? WHERE id = ? AND alan = ?", ('kabul' if kabul_mu else 'red', istek_id, username_clean))
        conn_dizi.commit()
    return True, "İşlem başarılı"

def arkadas_istekleri_yukle(friend_username: str) -> List[str]:
    """Arkadaşın kitaplığındaki 'İzledim' veya 'İzliyorum' durumundaki dizilerini döndürür."""
    try:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            return [r[0] for r in conn.execute(
                "SELECT dizi_isim FROM kitaplik WHERE user_id = ? AND durum IN ('İzledim', 'İzliyorum')", 
                (friend_username,)
            ).fetchall()]
    except Exception as e:
        logger.error(f"Arkadaş verileri yüklenirken hata: {e}")
        return []


# ==============================================================================
# ------- SECTION 6: NLP VE METİN İŞLEME OPERASYONLARI -------
# ==============================================================================

def turkce_normalize_et(metin: str) -> str:
    """Türkçe karakterleri ve diakritikleri normalize eden hafif fonksiyon."""
    metin = metin.lower()
    metin = metin.replace('ı', 'i').replace('ğ', 'g').replace('ü', 'u').replace('ş', 's').replace('ö', 'o').replace('ç', 'c')
    return metin

def metni_anlamli_kelimeye_cevir(metin: str) -> Dict[str, List[str]]:
    """Kullanıcının arama metnini temizler ve alt varyasyonları akıllıca tarar."""
    temiz_temel_kelimeler: List[str] = []
    tur_onerileri: Set[str] = set()

    metin_temiz = " ".join(re.findall(r'\b\w+\b', metin.lower()))
    metin_norm = turkce_normalize_et(metin_temiz)

    for ana_tema, varyasyonlar in KELIME_KOK_VE_VARYASYONLARI.items():
        for varyasyon in varyasyonlar:
            varyasyon_norm = turkce_normalize_et(varyasyon)
            if varyasyon_norm in metin_norm:
                temiz_temel_kelimeler.append(ana_tema)
                if ana_tema in ATMOSPHERE_ESLESME:
                    if "Tüm Türler" not in ATMOSPHERE_ESLESME[ana_tema]:
                        tur_onerileri.update(ATMOSPHERE_ESLESME[ana_tema])
                break

    return {
        "temalar": list(set(temiz_temel_kelimeler)),
        "tur_onerileri": list(tur_onerileri)
    }

def yapay_zeka_icin_anlamli_sorgu_olustur(ana_metin: str, es_temalar: List[str]) -> str:
    """Sentence-transformers için optimize, ağırlıklı bir sorgu cümlesi oluşturur."""
    sorgu = ana_metin
    if len(es_temalar) > 0:
        ağırlıklı_ek: List[str] = []
        for tema in es_temalar:
            ağırlıklı_ek.append(f"{tema} {tema} {tema}")
        sorgu += " " + " ".join(ağırlıklı_ek)
    return sorgu.strip()

def arama_metnini_genislet(arama_metni):
    """Sözlük varsa kullanır, yoksa orijinal metni olduğu gibi bırakır."""
    genisletilmis = arama_metni
    for kelime, sinonimler in SINONIM_MAP.items():
        if f" {kelime} " in f" {arama_metni.lower()} ":
            genisletilmis += " " + sinonimler
    return genisletilmis


# ==============================================================================
# ------- SECTION 7: AI VE ÖNERİ MOTORU BİLEŞENLERİ -------
# ==============================================================================

@st.cache_resource
def yapay_zeka_modelini_yukle():
    """Modelleri bir kez yükler ve tüm oturumlar için bellekte tutar."""
    return SentenceTransformer('intfloat/multilingual-e5-small')

@st.cache_data
def veritabanı_baslangik_yukle():
    """Diziler veritabanındaki tüm dizileri çeker ve cache'ler."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        df = pd.read_sql_query("SELECT * FROM diziler", conn)
    return df

@st.cache_data(ttl=30)
def tum_dizi_verilerini_getir() -> pd.DataFrame:
    """Veri tabanındaki tüm dizileri detaylı kolonlarıyla birlikte alfabetik olarak çeker."""
    try:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            return pd.read_sql_query("SELECT isim, sezon_sayisi, toplam_bolum_sayisi, gercek_bolum_sureleri, sezon_bolum_haritasi, tur, platformlar, durum, ozet, afis_url, puan_ortalamasi, oy_sayisi, cikis_tarihi, efsanevi_ikili, neden_izlemeli FROM diziler ORDER BY isim ASC", conn)
    except sqlite3.Error as e:
        logger.error(f"Dizi verileri çekilirken hata: {e}")
        return pd.DataFrame()

def zengin_metin_olustur(df: pd.DataFrame) -> List[str]:
    """Diziler için birleştirilmiş ve optimize edilmiş zengin metin temsili oluşturur."""
    def karakterleri_birlestir(row):
        try:
            gercekler = str(row.get('oyuncular_gercek', '')).split(',')
            roller = str(row.get('oyuncular_rol', '')).split(',')
            metin = ""
            for i in range(min(len(gercekler), len(roller), 4)):
                metin += f"{gercekler[i].strip()} rolünde {roller[i].strip()} "
            return metin.strip()
        except:
            return ""

    karakter_detay = df.apply(karakterleri_birlestir, axis=1)
    
    # Temizlenmiş neden izlemeli maddeleri (JSON formatından düz metne çeviriyoruz)
    neden_temiz = df['neden_izlemeli'].fillna("").str.replace(r'[\[\]"\'\\]', ' ', regex=True)
    ikili_temiz = df['efsanevi_ikili'].fillna("")
    
    zengin = (
        df['isim'].fillna("") + " " + 
        df['tur'].fillna("") + " " + df['tur'].fillna("") + " " + 
        karakter_detay + " " + 
        df['ozet'].fillna("").str[:200] + " " +
        neden_temiz + " " +
        ikili_temiz
    )
    return zengin.tolist()

def db_satir_sayisi_getir() -> int:
    """Veritabanındaki toplam dizi sayısını ve içerik uzunluğunu (neden_izlemeli ve efsanevi_ikili dahil)
    birleştirerek bir sürüm hash'i döner. Bu sayede tüm veri güncellemeleri anında yakalanır."""
    try:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*), 
                       SUM(length(isim) + length(ozet) + length(tur) + 
                           COALESCE(length(neden_izlemeli), 0) + 
                           COALESCE(length(efsanevi_ikili), 0)) 
                FROM diziler
            """)
            row = cursor.fetchone()
            return int(row[0] or 0) + int(row[1] or 0)
    except Exception:
        return 0

def dizi_hafizasini_vektorize_et(model, df) -> np.ndarray:
    """Tüm dizilerin zenginleştirilmiş metinlerini tek seferde vektörleştirip döner."""
    zengin_metinler = zengin_metin_olustur(df)
    # E5 models require prepending 'passage: ' to all documents
    zengin_metinler_prefixed = ["passage: " + str(m) for m in zengin_metinler]
    return model.encode(zengin_metinler_prefixed, show_progress_bar=False)

# Disk tabanlı vektör önbelleği
VEKTOR_DOSYASI = "dizi_vektorleri.npy"

@st.cache_data(ttl=1800)
def verileri_ve_vektorleri_hazirla(_model, db_version: int):
    """Veriyi veritabanından çeker ve vektörleştirme işlemini yapar. Disk ve bellek önbelleği kullanır."""
    df = tum_dizi_verilerini_getir()
    
    model_name_clean = "e5_small" if "e5" in str(type(_model)).lower() or "e5-small" in str(_model).lower() else "minilm"
    if os.path.exists(PERSISTENT_DIR):
        vektor_dosyasi_versioned = os.path.join(PERSISTENT_DIR, f"dizi_vektorleri_{model_name_clean}_{db_version}.npy")
    else:
        vektor_dosyasi_versioned = f"dizi_vektorleri_{model_name_clean}_{db_version}.npy"
    
    # Disk önbellek kontrolü
    if os.path.exists(vektor_dosyasi_versioned):
        try:
            vektorler = np.load(vektor_dosyasi_versioned)
            if len(vektorler) == len(df):
                return df, vektorler
        except Exception:
            pass
            
    # Vektörleri baştan oluştur ve diske kaydet
    vektorler = dizi_hafizasini_vektorize_et(_model, df)
    try:
        # Eski npy dosyalarını temizle (disk temizliği)
        import glob
        for f_path in glob.glob("dizi_vektorleri_*.npy") + ["dizi_vektorleri.npy"]:
            if os.path.exists(f_path):
                try: os.remove(f_path)
                except: pass
        # Yeni sürümü diske yaz
        np.save(vektor_dosyasi_versioned, vektorler)
    except Exception:
        pass
    return df, vektorler
def sorgu_anlamli_mi(sorgu: str) -> bool:
    """Arama sorgusunun rastgele harf yığını (gibberish) olup olmadığını kontrol eder.
    Vokal uyumu ve sessiz harf yığılması kurallarını kontrol eder."""
    words = [w.strip() for w in sorgu.lower().split() if w.strip()]
    if not words:
        return False
    vowels = set("aeıioöuü")
    for w in words:
        # 3 karakterden kısa kelimeleri (oz, tv vb.) atlayıp sadece uzun kelimeleri test ediyoruz
        if len(w) <= 3:
            continue
        # Kelimede en az bir sesli harf var mı?
        has_vowel = any(c in vowels for c in w)
        # Ardışık sessiz harf yığılması kontrolü (Örn: sjgfdsfs -> 8 ardışık sessiz)
        consonant_streak = 0
        max_consonant_streak = 0
        for char in w:
            if char.isalpha():
                if char in vowels:
                    consonant_streak = 0
                else:
                    consonant_streak += 1
                    if consonant_streak > max_consonant_streak:
                        max_consonant_streak = consonant_streak
        # Sesli harfi olmayan veya 4'ten fazla ardışık sessiz barındıran uzun kelimeler anlamsızdır
        if not has_vowel or max_consonant_streak > 4:
            return False
    return True

TR_STOP_WORDS = {
    "ben", "sen", "o", "biz", "siz", "onlar", "beni", "seni", "onu", "bizi", "sizi", "onları",
    "bana", "sana", "ona", "bize", "size", "onlara", "bende", "sende", "onda", "bizde", "sizde", "onda",
    "benim", "senin", "onun", "bizim", "sizin", "onların",
    "bir", "ve", "veya", "ise", "de", "da", "ki", "en", "daha", "ile", "için", "olan", "olarak", "gibi",
    "mi", "mı", "mu", "mü", "neden", "nasıl", "ne", "nedir", "nerede", "nereden", "nereye", "kim", "kimi", "kime",
    "istiyorum", "dizi", "dizisi", "dizileri", "film", "filmi", "filmleri", "yapım", "yapımı", "yapımları",
    "hakkında", "ilgili", "tarzı", "türü", "türünde", "geçen", "konulu", "temalı", "olsun", "izlemek", "izlesem",
    "şey", "birşey", "seyler", "şeyler",
    # Arama eylemleri (Arama çubuğundan temizlenmesi gereken fiiller)
    "listele", "listelesin", "öner", "bul", "göster", "getir", "arama", "ara", "yaz",
    # Blok listesi (Arama kirliliğini önlemek için yaygın hakaret, argo, yetişkin ve anlamsız ifadeler)
    "salak", "salağım", "aptal", "mal", "gerizekalı", "gerizekali", "deli", "manyak", "enayi", "keriz", 
    "klavyeyim", "buzdolabıyım", "porno", "seks", "sex", "porn", "erotik", "sikiş", "sik", "amcık", "göt",
    "cart", "curt", "pipi", "meme", "yarak", "yaraklar", "fuck", "bitch", "shit"
}

_DB_VOCAB = None
_DB_VOCAB_VERSION = None

def get_db_vocabulary(df):
    """Veritabanındaki tüm dizilerin isim, tür ve özet kelimelerini toplayarak dinamik sözlük oluşturur.
    Veritabanı güncellendiğinde önbelleği otomatik olarak yeniler."""
    global _DB_VOCAB, _DB_VOCAB_VERSION
    
    current_version = db_satir_sayisi_getir()
    if _DB_VOCAB is not None and _DB_VOCAB_VERSION == current_version:
        return _DB_VOCAB
        
    vocab = set()
    for col in ['isim', 'tur', 'ozet']:
        if col in df.columns:
            for text in df[col].fillna("").astype(str).str.lower():
                for word in text.split():
                    w_clean = "".join([c for c in word if c.isalnum()])
                    if w_clean:
                        vocab.add(w_clean)
    _DB_VOCAB = vocab
    _DB_VOCAB_VERSION = current_version
    return _DB_VOCAB

def yapay_zeka_semantik_oner_yeni(kullanici_mesaji, min_puan, max_sezon, min_oy, 
                                  secilen_turler, min_yil, otomatik_izlenenler, 
                                  secilen_platformlar, sadece_bitmis, siralama_tipi,
                                  dizi_havuzu_df, dizi_vektorleri, model, esik_degeri=0.35):
    """Mevcut uygulamadaki yeni semantik arama motoru (Vektörel Dilimleme, Dolgu Kelime Temizliği, Dinamik Sözlük ve Eşik Filtresi ile)."""
    df = dizi_havuzu_df.copy()
    if df.empty: return pd.DataFrame()
    
    df['yil'] = pd.to_numeric(df['cikis_tarihi'].fillna("0000").astype(str).str[:4], errors='coerce').fillna(0).astype(int)
    df = df[(df['puan_ortalamasi'] >= min_puan) & (df['sezon_sayisi'] <= max_sezon) &
            (df['oy_sayisi'] >= min_oy) & (df['yil'] >= min_yil)]

    if secilen_turler: df = df[df['tur'].fillna("").apply(lambda x: any(t.lower() in x.lower() for t in secilen_turler))]
    if secilen_platformlar: df = df[df['platformlar'].fillna("").apply(lambda x: any(p.lower() in x.lower() for p in secilen_platformlar))]
    if sadece_bitmis: df = df[df['durum'].fillna("").str.contains("Bitmiş|Final", case=False, na=False)]
    if otomatik_izlenenler: df = df[~df['isim'].isin(otomatik_izlenenler)]
    
    if not kullanici_mesaji or not kullanici_mesaji.strip():
        if siralama_tipi == "⭐ Dizi Puanı":
            return df.sort_values(by='puan_ortalamasi', ascending=False).reset_index(drop=True)
        elif siralama_tipi == "🗳️ Popülerlik":
            return df.sort_values(by='oy_sayisi', ascending=False).reset_index(drop=True)
        elif "şansımı dene" in siralama_tipi.lower() or "rastgele" in siralama_tipi.lower():
            # Arama boşken Şansımı Dene: Filtrelenmiş tüm dizileri karıştırarak getirir
            return df.sample(frac=1.0).reset_index(drop=True)
        elif "gizli cevher" in siralama_tipi.lower():
            # Arama boşken Gizli Cevherler: Puanı yüksek ama oy sayısı nispeten az olan butik dizileri listeler
            df['oner_skoru'] = ((df['puan_ortalamasi'] / 10) * 0.8) - (np.log1p(df['oy_sayisi'].fillna(0)) * 0.2)
            return df.sort_values(by='oner_skoru', ascending=False).reset_index(drop=True)
        else:
            return df.sort_values(by='puan_ortalamasi', ascending=False).reset_index(drop=True)
            
    # 🔒 Güvenlik Duvarı 1: Dolgu kelimeleri ve bloklu anlamsız kelimeleri temizliyoruz
    sorgu_words = [w.strip() for w in kullanici_mesaji.lower().split() if w.strip()]
    temiz_words = [w for w in sorgu_words if w not in TR_STOP_WORDS]
    
    if not temiz_words:
        return pd.DataFrame() # Temizlik sonrası boş kalıyorsa arama sonlandırılır
        
    sorgu_temiz = " ".join(temiz_words)
            
    # 🔒 Güvenlik Duvarı 2: Arama sorgusu yapısal olarak anlamsızsa (gibberish) aramayı kesiyoruz (0$ maliyet)
    if not sorgu_anlamli_mi(sorgu_temiz):
        return pd.DataFrame()
        
    # 🔒 Güvenlik Duvarı 3: Kelimelerin en az birinin veritabanı kelime haznesinde geçip geçmediğini kontrol ediyoruz
    # (Türkçe eklerinden dolayı alt kelime / substring kontrolü yapıyoruz, örn: ortaçağda -> ortaçağ)
    vocab = get_db_vocabulary(df)
    has_vocab = False
    for w in temiz_words:
        w_clean = "".join([c for c in w if c.isalnum()])
        if len(w_clean) < 3:
            continue
        # Sözlük kelimeleriyle kesişim kontrolü
        for v_word in vocab:
            if len(v_word) >= 3:
                if v_word in w_clean or w_clean in v_word:
                    has_vocab = True
                    break
        if has_vocab:
            break
            
    if not has_vocab:
        return pd.DataFrame()
            
    # 🚀 HIZLANDIRMA: Vektörleri önceden hesaplanmış tüm diziler havuzundan dilimliyoruz!
    filtreli_indeksler = df.index.tolist()
    dizi_vektorleri_dilimli = dizi_vektorleri[filtreli_indeksler]
    
    genisletilmis_sorgu = arama_metnini_genislet(sorgu_temiz)
    # E5 models require prepending 'query: ' to search queries
    sorgu_vektoru = model.encode(["query: " + genisletilmis_sorgu], show_progress_bar=False)
    
    benzerlikler = cosine_similarity(sorgu_vektoru, dizi_vektorleri_dilimli).flatten()
    
    # 🔒 Güvenlik Duvarı 3: Eğer arama kelimesi tamamen alakasız ise (En yüksek benzerlik < esik_degeri) boş sonuç döner
    max_benzerlik = benzerlikler.max() if len(benzerlikler) > 0 else 0.0
    if max_benzerlik < 0.72:  # E5 base similarity threshold for gibberish/unrelated queries
        return pd.DataFrame()
        
    # Mean-to-Max normalization for E5-small model
    mean_sim = benzerlikler.mean() if len(benzerlikler) > 0 else 0.0
    max_sim = benzerlikler.max() if len(benzerlikler) > 0 else 0.0
    if max_sim > mean_sim:
        benzerlikler_olcekli = np.clip((benzerlikler - mean_sim) / (max_sim - mean_sim), 0.0, 1.0)
    else:
        benzerlikler_olcekli = np.zeros_like(benzerlikler)
        
    # Calculate keyword match score to boost literal matches and penalize unrelated matches
    query_words_raw = [w.strip().lower() for w in genisletilmis_sorgu.split() if len(w.strip()) > 2]
    query_words = [w for w in query_words_raw if w not in TR_STOP_WORDS]
    
    keyword_scores = np.zeros(len(df))
    if query_words:
        isimler_norm = df['isim'].fillna('').apply(turkce_normalize_et).values
        turler_norm = df['tur'].fillna('').apply(turkce_normalize_et).values
        ozetler_norm = df['ozet'].fillna('').apply(turkce_normalize_et).values
        
        for w in query_words:
            w_norm = turkce_normalize_et(w)
            in_title = np.array([w_norm in name for name in isimler_norm])
            in_genre = np.array([w_norm in t for t in turler_norm])
            in_synopsis = np.array([w_norm in o for o in ozetler_norm])
            
            keyword_scores += np.where(in_title, 1.0, 0.0)
            keyword_scores += np.where(in_genre, 0.5, 0.0)
            keyword_scores += np.where(in_synopsis, 0.3, 0.0)
            
        keyword_scores = np.clip(keyword_scores, 0.0, 1.0)
        
    # Combine: 70% semantic similarity + 30% keyword overlap boost
    df['benzerlik_orani'] = 0.7 * benzerlikler_olcekli + 0.3 * keyword_scores
    df['benzerlik_orani'] = df['benzerlik_orani'].clip(0.0, 1.0)
    
    # Arama yapıldığında alakasız dizilerin listelenmesini önlemek için esik_degeri uyguluyoruz
    df = df[df['benzerlik_orani'] >= esik_degeri]
    
    if siralama_tipi == "⭐ Dizi Puanı":
        df['oner_skoru'] = df['puan_ortalamasi']
    elif siralama_tipi == "🗳️ Popülerlik":
        df['oner_skoru'] = df['oy_sayisi']
    elif "şansımı dene" in siralama_tipi.lower() or "rastgele" in siralama_tipi.lower():
        # Şansımı Dene: Arama eşleşmelerinden rastgele bir karıştırma yapar (Fikir 1)
        df['oner_skoru'] = np.random.rand(len(df))
    elif "gizli cevher" in siralama_tipi.lower():
        # Gizli Cevherler: Benzerliği ve puanı yüksek ama oy sayısı az olan butik dizileri öne çıkarır (Fikir 2)
        df['oner_skoru'] = (df['benzerlik_orani'] * 0.5) + ((df['puan_ortalamasi'] / 10) * 0.4) - (np.log1p(df['oy_sayisi'].fillna(0)) * 0.1)
    elif "yapay zeka uyumu" in siralama_tipi.lower():
        df['oner_skoru'] = df['benzerlik_orani']
    else:
        df['oner_skoru'] = df['benzerlik_orani']
        
    df['Eşleşme Oranı'] = (df['benzerlik_orani'] * 100).clip(0, 100).round(1)
    return df.sort_values(by='oner_skoru', ascending=False).reset_index(drop=True)

def hybrid_arama_skorla(dizi_df: pd.DataFrame, arama_metni: str, benzerlik_serisi: pd.Series) -> pd.Series:
    """NLP + embedding benzerliğini Pandas vektörel işlemleriyle (Vectorization) hesaplar."""
    if str(arama_metni).strip() == "":
        return benzerlik_serisi
        
    aranan_kelimeler = [turkce_normalize_et(k.strip()) for k in str(arama_metni).split() if len(k.strip()) > 2]
    if not aranan_kelimeler:
        return benzerlik_serisi

    isimler_norm = dizi_df['isim'].fillna('').astype(str).apply(turkce_normalize_et)
    ozetler_norm = dizi_df['ozet'].fillna('').astype(str).apply(turkce_normalize_et)
    turler_norm = dizi_df['tur'].fillna('').astype(str).apply(turkce_normalize_et)

    bonus_serisi = pd.Series(0.0, index=dizi_df.index)
    eslesen_kelime_sayisi_serisi = pd.Series(0, index=dizi_df.index)

    for kelime in aranan_kelimeler:
        in_isim = isimler_norm.str.contains(kelime, regex=False)
        in_ozet = ozetler_norm.str.contains(kelime, regex=False)
        in_tur = turler_norm.str.contains(kelime, regex=False)

        bonus_serisi += np.where(in_isim, 0.60, 0.0)
        bonus_serisi += np.where(in_ozet, 0.35, 0.0)
        bonus_serisi += np.where(in_tur, 0.20, 0.0)

        any_match = in_isim | in_ozet | in_tur
        eslesen_kelime_sayisi_serisi += np.where(any_match, 1, 0)

    total_aranan = len(aranan_kelimeler)
    ham_benzerlikler = benzerlik_serisi.reindex(dizi_df.index, fill_value=0.0)

    nihai_skorlar = np.where(
        eslesen_kelime_sayisi_serisi == 0,
        ham_benzerlikler * 0.01,
        np.where(
            (total_aranan >= 2) & (eslesen_kelime_sayisi_serisi == 1) & (ham_benzerlikler < 0.28),
            ham_benzerlikler * 0.05,
            ham_benzerlikler + bonus_serisi
        )
    )

    nihai_skorlar = np.clip(nihai_skorlar, 0.0, 1.0)
    return pd.Series(nihai_skorlar, index=dizi_df.index)

def yapay_zeka_ozet_uret(dizi_adi, tur="", bekleme=30, senkron_bekle=True):
    """Groq API (Llama 3.1) kullanarak diziler için otomatik 2 cümlelik özet üretir.

    senkron_bekle=True  -> 429 alınca bekleyip tekrar dener (toplu_ozet_onar gibi
                            arka plan/offline işler için; UI'ı bloklamaz çünkü zaten
                            UI'dan çağrılmaz).
    senkron_bekle=False -> 429 ya da başka bir hatada hiç beklemeden None döner
                            (canlı/arayüz kullanımı için — kullanıcıyı asla bekletmez).
    """
    if not AI_AKTIF:
        return None
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Sen profesyonel bir dizi eleştirmenisin."},
                {"role": "user", "content": f"'{dizi_adi}' ({tur} türünde) dizisi hakkında 2 cümlelik, çok etkileyici bir özet yazar mısın?"}
            ]
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        if "429" in str(e) and senkron_bekle:
            logger.warning(f"⚠️ Limit aşıldı, {bekleme} saniye bekleniyor... ({dizi_adi})")
            time.sleep(bekleme)
            return yapay_zeka_ozet_uret(dizi_adi, tur, bekleme + 10, senkron_bekle=True)
        logger.warning(f"Özet üretilemedi ({dizi_adi}): {e}")
        return None


def ozet_getir_veya_uret(dizi_adi, tur=""):
    """🚀 CANLI KULLANIM İÇİN: Write-through cache.
    Önce DB'de özet var mı bakılır (arayüz zaten sadece eksikse çağırır).
    Groq'tan üretilen her başarılı sonuç ANINDA veritabanına yazılır; bir daha
    bu dizi için asla API'ye gidilmez. Başarısız denemede DB'ye HİÇBİR ŞEY
    yazılmaz (kaliteyi bozmamak için) — sadece geçici bir mesaj gösterilir ve
    o dizi 5 dakika boyunca tekrar denenmez (retry-storm koruması)."""
    cache_anahtari = f"ozet:{dizi_adi}"
    if not _ai_deneme_uygun_mu(cache_anahtari):
        return f"{tur} türünde bir yapım. (Özet birazdan hazır olacak.)"

    ozet = yapay_zeka_ozet_uret(dizi_adi, tur, senkron_bekle=False)
    if ozet:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            conn.execute("UPDATE diziler SET ozet = ? WHERE isim = ?", (ozet, dizi_adi))
            conn.commit()
        return ozet

    _ai_basarisiz_isaretle(cache_anahtari)
    return f"{tur} türünde bir yapım. (Özet birazdan hazır olacak.)"

def profil_bazli_tavsiye_uret(aktif_izlenenler, otomatik_izlenenler, kullanici_puan, kullanici_sezon, min_oy_sayisi, min_yil, dizi_havuzu_df, dizi_vektorleri):
    """Eski profil bazlı tavsiye fonksiyonu."""
    try:
        izlenen_indeksler = dizi_havuzu_df[dizi_havuzu_df['isim'].isin(aktif_izlenenler)].index.tolist()
        izlenen_vektorler = dizi_vektorleri[izlenen_indeksler]
        kullanici_profil_vektoru = np.mean(izlenen_vektorler, axis=0).reshape(1, -1)
        
        havuz_df = dizi_havuzu_df[~dizi_havuzu_df['isim'].isin(otomatik_izlenenler)].copy()
        havuz_df['yil'] = havuz_df['cikis_tarihi'].fillna("0000").str[:4].replace('', '0000').astype(int)
        havuz_df = havuz_df[
            (havuz_df['puan_ortalamasi'] >= kullanici_puan) & 
            (havuz_df['sezon_sayisi'] <= kullanici_sezon) & 
            (havuz_df['oy_sayisi'] >= min_oy_sayisi) & 
            (havuz_df['yil'] >= min_yil)
        ]
        
        if havuz_df.empty: return None
            
        kalan_indeksler = havuz_df.index.tolist()
        tavsiye_skorlari = cosine_similarity(kullanici_profil_vektoru, dizi_vektorleri[kalan_indeksler])[0]
        havuz_df['profil_benzerligi'] = tavsiye_skorlari
        tum_tavsiyeler = havuz_df.sort_values(by='profil_benzerligi', ascending=False).head(10).copy()
        
        gerekceler = []
        for idx, row in tum_tavsiyeler.iterrows():
            tekli_vektor = dizi_vektorleri[idx].reshape(1, -1)
            bireysel_benzerlikler = cosine_similarity(tekli_vektor, izlenen_vektorler)[0]
            en_yakin_dizi = aktif_izlenenler[np.argmax(bireysel_benzerlikler)]
            gerekceler.append(en_yakin_dizi)
            
        tum_tavsiyeler['en_yakin_dizi_gerekce'] = gerekceler
        return tum_tavsiyeler
    except Exception as e:
        print(f"HATA (profil_bazli_tavsiye_uret): {e}")
        return None

def profil_bazli_tavsiye_uret_akilli(username, kullanici_puan, kullanici_sezon, min_oy_sayisi, 
                                     min_yil, secilen_platformlar, dizi_havuzu_df, dizi_vektorleri):
    """Kullanıcının detaylı zevk profilini çeker ve akıllı hibrit tavsiyeler üretir."""
    profile = get_user_profile(username)
    izlenenler = profile["izlenen_diziler"]
    gizlenenler = profile["gizlenen_diziler"]
    gercekten_izlenenler = profile["gercekten_izlenen_diziler"]
    
    havuz_df = dizi_havuzu_df[~dizi_havuzu_df['isim'].isin(izlenenler) & ~dizi_havuzu_df['isim'].isin(gizlenenler)].copy()
    if havuz_df.empty: return None
        
    havuz_df['yil'] = pd.to_numeric(havuz_df['cikis_tarihi'].fillna("0000").astype(str).str[:4], errors='coerce').fillna(0).astype(int)
    havuz_df = havuz_df[
        (havuz_df['puan_ortalamasi'] >= kullanici_puan) & 
        (havuz_df['sezon_sayisi'] <= kullanici_sezon) & 
        (havuz_df['oy_sayisi'] >= min_oy_sayisi) & 
        (havuz_df['yil'] >= min_yil)
    ]
    
    if secilen_platformlar:
        havuz_df = havuz_df[havuz_df['platformlar'].fillna("").apply(lambda x: any(p.lower() in x.lower() for p in secilen_platformlar))]
        
    if havuz_df.empty: return None
        
    izlenen_indeksler = dizi_havuzu_df[dizi_havuzu_df['isim'].isin(gercekten_izlenenler)].index.tolist()
    if not izlenen_indeksler:
        return havuz_df.sort_values(by='puan_ortalamasi', ascending=False).head(5)
        
    # 🚀 HIZLANDIRMA: İzlenen her dizi için ayrı ayrı bağlantı açmak yerine
    # TEK sorguda (IN operatörü ile) hepsinin puan/favori bilgisini çekiyoruz.
    izlenen_isimler = dizi_havuzu_df.loc[izlenen_indeksler, 'isim'].tolist()
    puan_favori_map: Dict[str, tuple] = {}
    if izlenen_isimler:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            cursor = conn.cursor()
            yer_tutucular = ",".join("?" * len(izlenen_isimler))
            cursor.execute(
                f"SELECT dizi_isim, puan, favori FROM kitaplik WHERE user_id = ? AND dizi_isim IN ({yer_tutucular})",
                (username, *izlenen_isimler)
            )
            puan_favori_map = {row[0]: (row[1] or 0, row[2] or 0) for row in cursor.fetchall()}

    hizali_agirliklar = []
    for idx in izlenen_indeksler:
        name = dizi_havuzu_df.loc[idx, 'isim']
        puan, favori = puan_favori_map.get(name, (0, 0))
        
        weight = puan if puan > 0 else 3.0
        if favori == 1:
            weight += 1.5
        hizali_agirliklar.append(weight)
        
    izlenen_vektorler = dizi_vektorleri[izlenen_indeksler]
    kullanici_profil_vektoru = np.average(izlenen_vektorler, weights=hizali_agirliklar, axis=0).reshape(1, -1)
    
    kalan_indeksler = havuz_df.index.tolist()
    tavsiye_skorlari = cosine_similarity(kullanici_profil_vektoru, dizi_vektorleri[kalan_indeksler])[0]
    havuz_df['profil_benzerligi'] = tavsiye_skorlari
    
    genre_weights = profile["tur_dagilimi"]
    fav_keywords = profile["favori_anahtar_kelimeler"]
    ideal_sure = profile["ortalama_sure"]
    ideal_sezon = profile["ortalama_sezon"]
    
    def detayli_skorla(row):
        tur_skor = 0.0
        dizi_turleri = [t.strip() for t in str(row['tur']).split(',') if t.strip()]
        for t in dizi_turleri:
            tur_skor += genre_weights.get(t, 0.0)
        tur_skor = min(1.0, tur_skor)
        
        sure_farki = abs(int(row['gercek_bolum_sureleri']) - ideal_sure)
        sure_skor = max(0.0, 1.0 - (sure_farki / 60.0))
        
        sezon_farki = abs(int(row['sezon_sayisi']) - ideal_sezon)
        sezon_skor = max(0.0, 1.0 - (sezon_farki / 10.0))
        
        keyword_skor = 0.0
        if 'anahtar_kelimeler' in row and pd.notna(row['anahtar_kelimeler']):
            dizi_kws = [kw.strip() for kw in str(row['anahtar_kelimeler']).split(',') if kw.strip()]
            ortak_kws = set(dizi_kws).intersection(fav_keywords)
            if fav_keywords:
                keyword_skor = len(ortak_kws) / len(fav_keywords)
                
        final_skor = (
            (row['profil_benzerligi'] * 0.40) +
            (tur_skor * 0.25) +
            (keyword_skor * 0.15) +
            (sure_skor * 0.10) +
            (sezon_skor * 0.10)
        )
        return final_skor, tur_skor, sure_skor, keyword_skor
    
    skorlar = havuz_df.apply(detayli_skorla, axis=1)
    
    havuz_df['nihai_tavsiye_skoru'] = [s[0] for s in skorlar]
    havuz_df['tur_uyumu_yuzde'] = [round(s[1] * 100, 1) for s in skorlar]
    havuz_df['sure_uyumu_yuzde'] = [round(s[2] * 100, 1) for s in skorlar]
    
    # 🚀 HIZLANDIRMA: Havuzdaki her dizi için tek tek cosine_similarity çağırmak yerine
    # TEK matris çarpımıyla (havuz x izlenenler) tüm benzerlikleri aynı anda hesaplıyoruz.
    izlenen_vektorler_all = dizi_vektorleri[izlenen_indeksler]
    havuz_vektorleri = dizi_vektorleri[kalan_indeksler]
    tum_benzerlik_matrisi = cosine_similarity(havuz_vektorleri, izlenen_vektorler_all)
    en_yakin_siralar = np.argmax(tum_benzerlik_matrisi, axis=1)
    en_yakin_dizi_indeksleri = [izlenen_indeksler[sira] for sira in en_yakin_siralar]
    gerekceler = dizi_havuzu_df.loc[en_yakin_dizi_indeksleri, 'isim'].tolist()
        
    havuz_df['en_yakin_dizi_gerekce'] = gerekceler
    return havuz_df.sort_values(by='nihai_tavsiye_skoru', ascending=False).head(5)

def get_user_profile(username: str) -> dict:
    """Kullanıcının detaylı izleme profilini hazırlar (Zevk pastası, süre, sezon vb.)."""
    profile = {
        "tur_dagilimi": {},           
        "ortalama_sure": 45,          
        "ortalama_sezon": 3,          
        "izlenen_platformlar": [],     
        "favori_anahtar_kelimeler": [],  
        "gercekten_izlenen_diziler": [], 
        "izlenen_diziler": [],        
        "gizlenen_diziler": []        
    }
    
    if not username: return profile
        
    kitaplik_df = kullanıcı_kitaplığını_getir(username)
    profile["gizlenen_diziler"] = kullanicinin_listesini_getir(username, "gizlenenler")
    
    if kitaplik_df.empty: return profile
        
    profile["izlenen_diziler"] = kitaplik_df['dizi_isim'].tolist()
    
    aktif_kitaplik = kitaplik_df[kitaplik_df['durum'].isin(["İzledim", "İzliyorum"]) | (kitaplik_df['favori'] == 1)]
    profile["gercekten_izlenen_diziler"] = aktif_kitaplik['dizi_isim'].tolist()
    
    if aktif_kitaplik.empty: return profile
        
    dizi_df = tum_dizi_verilerini_getir()
    if dizi_df.empty: return profile
        
    user_dizileri = dizi_df[dizi_df['isim'].isin(aktif_kitaplik['dizi_isim'])]
    if user_dizileri.empty: return profile
        
    profile["ortalama_sure"] = int(user_dizileri['gercek_bolum_sureleri'].dropna().mean()) if not user_dizileri['gercek_bolum_sureleri'].dropna().empty else 45
    profile["ortalama_sezon"] = int(user_dizileri['sezon_sayisi'].dropna().mean()) if not user_dizileri['sezon_sayisi'].dropna().empty else 3
    
    genre_weights = {}
    for idx, row in user_dizileri.iterrows():
        lib_row = aktif_kitaplik[aktif_kitaplik['dizi_isim'] == row['isim']].iloc[0]
        puan = int(lib_row.get('puan', 0)) if pd.notna(lib_row.get('puan')) else 0
        favori = int(lib_row.get('favori', 0)) if pd.notna(lib_row.get('favori')) else 0
        
        base_weight = puan if puan > 0 else 3.0
        if favori == 1:
            base_weight += 1.5
            
        dizi_turleri = [t.strip() for t in str(row['tur']).split(',') if t.strip()]
        for t in dizi_turleri:
            genre_weights[t] = genre_weights.get(t, 0.0) + base_weight
            
    total_weight = sum(genre_weights.values())
    if total_weight > 0:
        profile["tur_dagilimi"] = {t: w / total_weight for t, w in genre_weights.items()}
        
    plat_listesi = []
    for p_str in user_dizileri['platformlar'].dropna().astype(str):
        plat_listesi.extend([p.strip() for p in p_str.split(',') if p.strip()])
    if plat_listesi:
        profile["izlenen_platformlar"] = list(pd.Series(plat_listesi).value_counts().index)
        
    if 'anahtar_kelimeler' in user_dizileri.columns:
        kw_listesi = []
        for kw_str in user_dizileri['anahtar_kelimeler'].dropna().astype(str):
            kw_listesi.extend([kw.strip() for kw in kw_str.split(',') if kw.strip()])
        if kw_listesi:
            profile["favori_anahtar_kelimeler"] = list(pd.Series(kw_listesi).value_counts().head(5).index)
            
    return profile

def iki_dizi_karsilastir_meta_uret(dizi1, dizi2, dizi_havuzu_df, dizi_vektorleri):
    """İki dizinin vektör benzerliğini hesaplar."""
    try:
        meta1 = dizi_havuzu_df[dizi_havuzu_df['isim'] == dizi1].iloc[0]
        meta2 = dizi_havuzu_df[dizi_havuzu_df['isim'] == dizi2].iloc[0]
        
        idx1 = dizi_havuzu_df[dizi_havuzu_df['isim'] == dizi1].index[0]
        idx2 = dizi_havuzu_df[dizi_havuzu_df['isim'] == dizi2].index[0]
        
        vec1 = dizi_vektorleri[idx1].reshape(1, -1)
        vec2 = dizi_vektorleri[idx2].reshape(1, -1)
        benzerlik = round(float(cosine_similarity(vec1, vec2)[0][0]) * 100, 1)
        
        return benzerlik, meta1, meta2
    except Exception as e:
        print(f"HATA (iki_dizi_karsilastir_meta_uret): {e}")
        return 0, None, None

def ortak_zevk_fuzyon_tavsiyesi_uret(kendi_aktifler, otomatik_izlenenler, arkadas_izlenenler, dizi_havuzu_df, dizi_vektorleri):
    """İki arkadaşın zevk füzyonunu hesaplayarak ortak dizi önerir."""
    try:
        kendi_indeksler = dizi_havuzu_df[dizi_havuzu_df['isim'].isin(kendi_aktifler)].index.tolist()
        arkadas_indeksler = dizi_havuzu_df[dizi_havuzu_df['isim'].isin(arkadas_izlenenler)].index.tolist()
        
        if not kendi_indeksler and not arkadas_indeksler: return None
            
        ortak_izlenen_vektorler = dizi_vektorleri[kendi_indeksler + arkadas_indeksler]
        kolektif_profil_vektoru = np.mean(ortak_izlenen_vektorler, axis=0).reshape(1, -1)
        
        yasakli_ortak_havuz = list(set(otomatik_izlenenler + arkadas_izlenenler))
        sosyal_havuz_df = dizi_havuzu_df[~dizi_havuzu_df['isim'].isin(yasakli_ortak_havuz)].copy()
        
        if sosyal_havuz_df.empty: return None
            
        sosyal_tavsiye_skorlari = cosine_similarity(kolektif_profil_vektoru, dizi_vektorleri[sosyal_havuz_df.index.tolist()])[0]
        sosyal_havuz_df['ortak_benzerlik'] = sosyal_tavsiye_skorlari
        
        return sosyal_havuz_df.sort_values(by='ortak_benzerlik', ascending=False).head(5)
    except Exception as e:
        print(f"HATA (ortak_zevk_fuzyon_tavsiyesi_uret): {e}")
        return None

def dizi_bul(secilen_turler, secilen_platformlar, max_sezon):
    """Kriterlere uyan dizileri filtreleyerek döner."""
    try:
        df = tum_dizi_verilerini_getir()
        if df is None or df.empty: return None

        df['sezon_sayisi'] = pd.to_numeric(df['sezon_sayisi'], errors='coerce').fillna(0)
        df['tur_temiz'] = df['tur'].fillna('').astype(str).str.lower()
        df['plat_temiz'] = df['platformlar'].fillna('').astype(str).str.lower()
        
        mask = pd.Series([True] * len(df))
        if secilen_turler:
            mask &= df['tur_temiz'].apply(lambda x: any(t.lower().strip() in x for t in secilen_turler))
        mask &= (df['sezon_sayisi'] <= max_sezon)
        if secilen_platformlar:
            mask &= df['plat_temiz'].apply(lambda x: any(p.lower().strip() in x for p in secilen_platformlar))

        sonuclar = df[mask]
        return sonuclar if not sonuclar.empty else None
    except Exception as e:
        print(f"HATA (dizi_bul): {e}")
        return None

def turleri_ve_platformlari_getir():
    """Tüm dizilerden benzersiz ve sıralı tür/platform listelerini üretir (Hız için Statikleştirildi)."""
    tum_turler = ["Aile", "Aksiyon & Macera", "Animasyon", "Belgesel", "Bilim Kurgu & Fantastik", "Bilinmiyor", "Dram", "Gizem", "Haber", "Komedi", "Pembe Dizi", "Realite", "Savaş & Politik", "Suç", "Talk Şov", "Vahşi Batı", "Çocuk"]
    tum_platformlar = ["Amazon Prime", "Disney Plus", "Diğer Platformlar", "HBO / Max", "MUBI", "Netflix"]
    return tum_turler, tum_platformlar

def get_dizi_info(dizi_ismi):
    """Belirtilen dizinin özet, sezon, bölüm, afiş, platform ve tür bilgilerini sözlük yapısında döner."""
    try:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            cursor = conn.cursor()
            sorgu = """
            SELECT ozet, sezon_sayisi, toplam_bolum_sayisi, cikis_tarihi, durum, afis_url, platformlar, tur 
            FROM diziler 
            WHERE isim = ?
            """
            cursor.execute(sorgu, (dizi_ismi,))
            sonuc = cursor.fetchone()
        
        if sonuc:
            return {
                'ozet': sonuc[0] or 'Özet yok',
                'sezon_sayisi': sonuc[1],
                'toplam_bolum': sonuc[2],
                'yayin_yili': sonuc[3].split('-')[0] if sonuc[3] else '?',
                'durum': sonuc[4],
                'afis_url': sonuc[5],
                'platformlar': sonuc[6] or 'Bilgi yok',
                'tur': sonuc[7] or 'Tür yok'
            }
        return {'ozet': 'Bu dizi veritabanında yok.', 'sezon_sayisi': '?', 'toplam_bolum': '?', 'yil': '?', 'durum': '?'}
    except Exception as e:
        print(f"🚨 get_dizi_info Hatası ({dizi_ismi}): {e}")
        return {'ozet': 'Dizi bilgileri alınamadı.', 'sezon_sayisi': '?', 'toplam_bolum': '?', 'yil': '?', 'durum': '?'}

def toplu_ozet_onar():
    """Veri tabanında özeti eksik olan dizileri tespit edip yapay zeka motoruyla toplu olarak günceller."""
    with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT isim FROM diziler WHERE ozet = 'Özet yok' OR ozet IS NULL OR ozet = ''")
        eksik_diziler = cursor.fetchall()
        
        toplam = len(eksik_diziler)
        print(f"🚀 Toplam {toplam} dizi onarılmayı bekliyor, başlıyoruz...")
        for index, (isim,) in enumerate(eksik_diziler, 1):
            print(f"[{index}/{toplam}] ✨ '{isim}' işleniyor...")
            yeni_ozet = yapay_zeka_ozet_uret(isim, senkron_bekle=True)
            if yeni_ozet:
                cursor.execute("UPDATE diziler SET ozet = ? WHERE isim = ?", (yeni_ozet, isim))
                conn.commit()
                print(f"✅ Bitti. Kalan: {toplam - index}")
            else:
                print("❌ Hata oluştu, geçiliyor.")
            time.sleep(10) 
    print("✅ Tüm işlemler bitti, dizi kütüphanen hazır!")

ODULLU_DIZILER = {
    "breaking bad", "game of thrones", "sherlock", "lost", "chernobyl", "succession", 
    "the crown", "fargo", "true detective", "fleabag", "mad men", "the office", 
    "modern family", "arrested development", "seinfeld", "the sopranos", "the wire", 
    "friends", "better call saul", "narcos", "peaky blinders", "black mirror",
    "stranger things", "the mandalorian", "ted lasso", "the bear", "squid game",
    "house of the dragon", "downton abbey", "homeland", "westworld", "mr. robot",
    "twin peaks", "dexter", "prison break", "rome", "band of brothers", "the pacific",
    "bojack horseman", "rick and morty", "arcane", "avatar: the last airbender",
    "how i met your mother", "the big bang theory", "desperate housewives", "grey's anatomy",
    "house", "the walking dead", "glee", "the twilight zone", "frasier", "cheers", 
    "mash", "x-files", "er", "nypd blue", "the west wing", "curb your enthusiasm", 
    "30 rock", "veep", "atlanta", "barry", "hacks", "abbott elementary", "schitt's creek", 
    "marvelous mrs. maisel", "dallas", "dynasty", "law & order", "oz", "six feet under", 
    "deadwood", "boardwalk empire", "hannibal", "justified", "sons of anarchy", 
    "the shield", "battlestar galactica", "firefly", "doctor who", "supernatural", 
    "fringe", "heroes", "daredevil", "punisher", "invincible", "the boys", "loki", 
    "wandavision", "mindhunter", "generation kill", "normal people", "queen's gambit", 
    "white lotus", "beef", "dahr", "gibi", "sahisiyet", "behzat c."
}

def yapay_zeka_neden_izlemeli_uret(dizi_adi, tur):
    """🚀 Dizi için 3 adet %100 o diziye özel 'neden izlemelisin' maddesi döner.

    Sıra:
    1) Veritabanında zaten üretilmiş mi? (kalıcı cache -> 0 saniye, 0 token)
    2) Elde hazır/özenle yazılmış madde var mı? (birkaç ikonik dizi için)
    3) Groq/Llama'dan %100 o diziye özel 3 madde üretilip DB'ye KALICI yazılır.
    4) Üretim başarısız olursa -> DB'ye HİÇBİR ŞEY yazılmaz (sahte/genel içerik
       kalıcılaşmasın diye), sadece geçici, açıkça "hazırlanıyor" diyen bir mesaj
       gösterilir ve o dizi için 5 dakika tekrar denenmez (retry-storm koruması).
    """
    hazir_maddeler = {
        "Breaking Bad": [
            "Kimya öğretmeninin suç imparatorluğuna dönüşümünü anlatan gelmiş geçmiş en iyi senaryolardan biri.",
            "Bryan Cranston ve Aaron Paul'un hayat verdiği efsanevi oyunculuk performansları.",
            "Televizyon tarihinin en tatmin edici, en çok övülen final bölümlerinden biri."
        ],
        "Stranger Things": [
            "80'lerin nostaljik atmosferini, müziklerini ve sinema kültürünü harika yansıtır.",
            "Gizemli hükümet deneyleri ve doğaüstü olaylarla dolu sürükleyici fantastik hikaye.",
            "Çocuk karakterlerin samimi arkadaşlık bağları ve yüksek enerjili maceralar."
        ],
        "Dark": [
            "Zaman yolculuğu temasını beyin yakan, muazzam bir mantık çerçevesinde işleyen senaryo.",
            "Ufak bir kasabadaki 4 ailenin geçmiş ve gelecek ilişkilerini düğüm düğüm çözen kurgu.",
            "Karanlık, gizemli ve gerilim dolu enfes Alman yapımı atmosfer."
        ],
        "Friends": [
            "Günlük hayatın tüm yorgunluğunu unutturan, kafa dağıtmalık ve yüksek enerjili mizah.",
            "Yıllar geçse de eskimeyen ikonik karakterler ve aralarındaki harika kimya.",
            "Kahkahalar eşliğinde izleyeceğiniz sıcak ve samimi Manhattan dostluk hikayesi."
        ],
        "Sherlock": [
            "Benedict Cumberbatch'in dahi ve sıra dışı Sherlock Holmes yorumu.",
            "Modern Londra sokaklarında geçen yüksek tempolu ve akıl oyunlarıyla dolu suç gizemleri.",
            "Her bölümü bir sinema filmi kalitesinde ve uzunluğunda olan ödüllü yapım."
        ]
    }

    # 1) Kalıcı DB cache
    try:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT neden_izlemeli FROM diziler WHERE isim = ?", (dizi_adi,))
            sonuc = cursor.fetchone()
        if sonuc and sonuc[0]:
            kayitli_maddeler = json.loads(sonuc[0])
            if isinstance(kayitli_maddeler, list) and len(kayitli_maddeler) == 3:
                return kayitli_maddeler
    except Exception as e:
        logger.warning(f"neden_izlemeli DB okuma hatası ({dizi_adi}): {e}")

    # 2) Elde hazır, özenle yazılmış içerik
    if dizi_adi in hazir_maddeler:
        maddeler = hazir_maddeler[dizi_adi]
        _neden_izlemeli_db_kaydet(dizi_adi, maddeler)
        return maddeler

    # Retry-storm koruması: yakın zamanda başarısız olduysa boşuna API'ye gitme
    cache_anahtari = f"neden:{dizi_adi}"
    if not AI_AKTIF or not _ai_deneme_uygun_mu(cache_anahtari):
        return ["Bu dizi için özel değerlendirme hazırlanıyor, birazdan tekrar dene."]

    # 3) Groq/Llama'dan %100 bu diziye özel üretim
    try:
        # Özet bilgisini veritabanından çekerek yapay zekaya bağlam (context) olarak veriyoruz (Halüsinasyon engelleme)
        ozet_metni = ""
        try:
            with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT ozet FROM diziler WHERE isim = ?", (dizi_adi,))
                res = cursor.fetchone()
                if res and res[0]:
                    ozet_metni = res[0]
        except Exception as e:
            logger.warning(f"Özet çekme hatası ({dizi_adi}): {e}")

        # Ödül durumunu Python tarafında kontrol ediyoruz (100% deterministik halüsinasyon engelleme)
        import re
        isim_lower = dizi_adi.lower()
        clean_name = re.sub(r'\(.*\)', '', isim_lower).strip()
        ozet_lower = ozet_metni.lower()
        
        is_award_winner = (
            clean_name in ODULLU_DIZILER or 
            any(w in ozet_lower for w in ["emmy", "altın küre", "golden globe", "bafta", "oscar", "ödüllü", "ödül aldı", "ödül kazandı"])
        )
        
        if is_award_winner:
            system_prompt = (
                "Sen profesyonel bir dizi danışmanısın. Sana sunulan dizinin adını, türünü ve özetini (konusunu) temel alarak, kullanıcının bu diziyi izlemesi için 3 maddelik, son derece kısa ve vurucu nedenler yazmalısın.\n\n"
                "KESİN KURALLAR:\n"
                "1. TAM CÜMLE YAZMA: Her madde tam bir cümle (özne, yüklem vb.) şeklinde OLMAYACAKTIR. Kısa kelime grupları (tamlama/öbek) şeklinde yazmalısın.\n"
                "2. KELİME SINIRI: Her madde en fazla 4-7 kelimeden oluşmalıdır. Asla bu sınırı aşma.\n"
                "3. TÜRKÇE KALİTESİ: Türkçe dil bilgisine %100 uy. Çeviri kokan bozuk cümleler kurma. Kesinlikle İngilizce kelime (main, around, characters vb.) karıştırma.\n"
                "4. KAÇIŞ KARAKTERİ KULLANMA: Metin içinde tırnak işaretleri, ters bölü (\\) veya kaçış karakterleri (', \", \\' vb.) asla kullanma. Kesme işaretlerini düzgün yaz veya hiç kullanma.\n"
                "5. ÖDÜL KURALI: Bu dizi prestijli ödüller kazanmış tescilli bir yapımdır. İlk 2 maddeyi normal neden yaz, 3. maddeyi ise MUTLAKA bu prestijli ödülleri (Emmy, Altın Küre, BAFTA) ve başarıyı öne çıkaracak şekilde kurgula. Sayısal ödül miktarından emin değilsen uydurma sayılar (30 Emmy vb.) yazma, genel ve havalı yaz (örn: 'Emmy ve Altın Küre ödüllü başyapıt' veya 'Çok sayıda Emmy ödüllü tescilli başarı').\n\n"
                "FORMAT ÖRNEĞİ (Sherlock dizisi için):\n"
                "1. Zeka dolu modern dedektif hikayeleri.\n"
                "2. Benedict Cumberbatch ve Martin Freeman uyumu.\n"
                "3. Çok sayıda Emmy ödüllü tescilli başarı.\n\n"
                "Çıktıyı MUTLAKA tam olarak şu formatta ver:\n"
                "1. [Birinci neden]\n"
                "2. [İkinci neden]\n"
                "3. [Üçüncü neden]"
            )
        else:
            system_prompt = (
                "Sen profesyonel bir dizi danışmanısın. Sana sunulan dizinin adını, türünü ve özetini (konusunu) temel alarak, kullanıcının bu diziyi izlemesi için 3 maddelik, son derece kısa ve vurucu nedenler yazmalısın.\n\n"
                "KESİN KURALLAR:\n"
                "1. TAM CÜMLE YAZMA: Her madde tam bir cümle (özne, yüklem vb.) şeklinde OLMAYACAKTIR. Kısa kelime grupları (tamlama/öbek) şeklinde yazmalısın.\n"
                "2. KELİME SINIRI: Her madde en fazla 4-7 kelimeden oluşmalıdır. Asla bu sınırı aşma.\n"
                "3. TÜRKÇE KALİTESİ: Türkçe dil bilgisine %100 uy. Çeviri kokan bozuk cümleler kurma. Kesinlikle İngilizce kelime (main, around, characters vb.) karıştırma.\n"
                "4. KAÇIŞ KARAKTERİ KULLANMA: Metin içinde tırnak işaretleri, ters bölü (\\) veya kaçış karakterleri (', \", \\' vb.) asla kullanma. Kesme işaretlerini düzgün yaz veya hiç kullanma.\n"
                "5. ÖDÜL BİLGİSİ YASAKTIR: Bu dizinin büyük bir ödülü yoktur. Bu nedenle metin içinde kesinlikle 'Emmy', 'Altın Küre', 'BAFTA', 'Oscar' veya 'ödüllü' gibi kelimeleri KULLANMA. 3. maddeye de normal, diziye özel başka bir neden yaz.\n\n"
                "FORMAT ÖRNEĞİ (Stranger Things dizisi için):\n"
                "1. 80ler nostaljisi ve müzikleri.\n"
                "2. Doğaüstü olaylar ve gizemli deneyler.\n"
                "3. Çocuk karakterlerin samimi arkadaşlık bağları.\n\n"
                "Çıktıyı MUTLAKA tam olarak şu formatta ver:\n"
                "1. [Birinci neden]\n"
                "2. [İkinci neden]\n"
                "3. [Üçüncü neden]"
            )

        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Dizi Adı: '{dizi_adi}'\nTür: {tur}\nÖzet/Konu: {ozet_metni}\n\nBu diziyi izlemek için 3 kısa, o diziye özel neden yazar mısın?"}
            ]
        )
        content = completion.choices[0].message.content.strip()
        
        import re
        maddeler = re.findall(r'(?:^|\n)\s*\d+[\.\-\)]\s*(.+)', content)
        
        if len(maddeler) < 3:
            # Fallback splitting on newline and cleaning leading bullets/numbers
            maddeler = []
            for line in content.split("\n"):
                line = line.strip()
                if not line:
                    continue
                cleaned = re.sub(r'^\s*[\d\-•\*\)\.]+\s*', '', line).strip()
                if cleaned:
                    maddeler.append(cleaned)
        
        maddeler = maddeler[:3]
        
        if len(maddeler) < 3:
            raise ValueError(f"Model yalnızca {len(maddeler)} geçerli madde döndürdü, 3 bekleniyor. Model Çıktısı:\n{content}")
        
        _neden_izlemeli_db_kaydet(dizi_adi, maddeler)
        return maddeler
    except Exception as e:
        logger.warning(f"neden_izlemeli üretim hatası ({dizi_adi}): {e}")
        _ai_basarisiz_isaretle(cache_anahtari)
        return ["Bu dizi için özel değerlendirme hazırlanıyor, birazdan tekrar dene."]


def _neden_izlemeli_db_kaydet(dizi_adi, maddeler):
    """3 maddeyi JSON olarak diziler.neden_izlemeli kolonuna kalıcı yazar."""
    try:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            conn.execute(
                "UPDATE diziler SET neden_izlemeli = ? WHERE isim = ?",
                (json.dumps(maddeler, ensure_ascii=False), dizi_adi)
            )
            conn.commit()
    except Exception as e:
        logger.warning(f"neden_izlemeli DB yazma hatası ({dizi_adi}): {e}")


# ------------------------------------------------------------------------------
# 🎛️ PORT ETME KÖPRÜSÜ (Arayüz Uyumluluğu İçin)
# ------------------------------------------------------------------------------
def platform_linklerini_olustur(platform_metni, dizi_adi):
    """Arayüzün platform linki oluşturma işlevini üstlenir."""
    if not platform_metni: return "Belirtilmemiş"
    import urllib.parse
    encoded_name = urllib.parse.quote(dizi_adi)
    parcalar = [p.strip() for p in platform_metni.split(',')]
    html_linkleri = []
    for p in parcalar:
        p_lower = p.lower()
        if "netflix" in p_lower:
            url = f"https://www.netflix.com/search?q={encoded_name}"
            html_linkleri.append(f'<a href="{url}" target="_blank" style="color:#E50914; text-decoration:none; font-weight:bold;">🎬 Netflix</a>')
        elif "prime" in p_lower:
            url = f"https://www.primevideo.com/search/?phrase={encoded_name}"
            html_linkleri.append(f'<a href="{url}" target="_blank" style="color:#00A8E1; text-decoration:none; font-weight:bold;">🎬 Amazon Prime</a>')
        elif "disney" in p_lower:
            url = f"https://www.disneyplus.com/search?q={encoded_name}"
            html_linkleri.append(f'<a href="{url}" target="_blank" style="color:#00e5ff; text-decoration:none; font-weight:bold;">🎬 Disney Plus</a>')
        else:
            url = f"https://www.google.com/search?q={encoded_name}+{p}+izle"
            html_linkleri.append(f'<a href="{url}" target="_blank" style="font-weight:bold; color:#10b981; text-decoration:none;">🔎 {p} (Google\'da Ara)</a>')
    return " | ".join(html_linkleri)


def kullanici_rozetlerini_hesapla(username):
    """Kullanıcının veritabanındaki kitaplık durumuna göre tüm başarımlarını ve rozetlerini hesaplar."""
    rozetler = {}
    
    try:
        with sqlite3.connect(DB_ADI, timeout=30.0) as conn:
            # 1. Kullanıcının kitaplığındaki dizileri ve detayları tek seferde çek (JOIN)
            query = """
                SELECT k.durum, k.izlenen_bolum, k.puan, d.isim, d.tur, d.platformlar, d.toplam_bolum_sayisi, d.gercek_bolum_sureleri, d.oy_sayisi
                FROM kitaplik k
                JOIN diziler d ON k.dizi_isim = d.isim
                WHERE k.user_id = ?
            """
            cursor = conn.cursor()
            cursor.execute(query, (username,))
            rows = cursor.fetchall()
            
            toplam_dizi = len(rows)
            toplam_dakika = 0
            tur_sayilari = {}
            platform_sayilari = {"netflix": 0, "prime": 0, "disney": 0}
            gizli_cevher_sayisi = 0
            puanlanan_dizi_sayisi = 0
            
            for row in rows:
                durum, izlenen_bolum, puan, isim, tur, platformlar, toplam_bolum, gercek_sure, oy_sayisi = row
                
                # Süre hesaplama
                gercek_sure = int(gercek_sure or 0)
                if durum == "İzledim":
                    toplam_dakika += (int(toplam_bolum or 0) * gercek_sure)
                else:
                    toplam_dakika += (int(izlenen_bolum or 0) * gercek_sure)
                    
                # Tür sayımı
                if tur:
                    dizi_turleri = [t.strip().lower() for t in str(tur).split(',') if t.strip()]
                    for t in dizi_turleri:
                        tur_sayilari[t] = tur_sayilari.get(t, 0) + 1
                        
                # Platform sayımı
                if platformlar:
                    p_lower = str(platformlar).lower()
                    if "netflix" in p_lower:
                        platform_sayilari["netflix"] += 1
                    if "prime" in p_lower:
                        platform_sayilari["prime"] += 1
                    if "disney" in p_lower:
                        platform_sayilari["disney"] += 1
                        
                # Gizli Cevher sayımı (oy_sayisi 200 ile 400 arasındakiler)
                if oy_sayisi and 200 <= int(oy_sayisi) <= 400:
                    gizli_cevher_sayisi += 1
                    
                # Puanlanan dizi sayımı
                if puan and int(puan) > 0:
                    puanlanan_dizi_sayisi += 1
            
            toplam_saat = toplam_dakika / 60.0
            
            # Arkadaş sayısını çek
            friend_count = 0
            try:
                with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn_user:
                    cur_user = conn_user.cursor()
                    cur_user.execute("SELECT COUNT(*) FROM arkadasliklar WHERE kullanici = ?", (username,))
                    friend_count = cur_user.fetchone()[0]
            except Exception as fe:
                pass
                
            # Kademe hesaplayıcı yardımcı fonksiyon
            def build_badge_info(current_value, tiers):
                earned_tier = None
                next_target = None
                next_tier = None
                
                for val, tier in tiers:
                    if current_value >= val:
                        earned_tier = tier
                    else:
                        next_target = val
                        next_tier = tier
                        break
                        
                # İlerleme oranı hesaplama
                if earned_tier is None:
                    prev_val = 0
                else:
                    prev_val = [v for v, t in tiers if t == earned_tier][0]
                
                if next_target:
                    progress_current = current_value - prev_val
                    progress_total = next_target - prev_val
                    ratio = min(1.0, max(0.0, progress_current / progress_total))
                else:
                    ratio = 1.0
                    
                return {
                    "seviye": earned_tier,
                    "deger": current_value,
                    "hedef": next_target,
                    "sonraki_seviye": next_tier,
                    "oran": ratio
                }
            
            # 1. Ekran Bağımlısı
            rozetler["ekran_bagimlisi"] = build_badge_info(
                toplam_dizi,
                [(10, "bronz"), (25, "gumus"), (50, "altin"), (100, "elmas")]
            )
            
            # 2. Koltuk Patatesi
            rozetler["koltuk_patatesi"] = build_badge_info(
                int(toplam_saat),
                [(100, "bronz"), (1000, "gumus"), (5000, "altin"), (10000, "elmas")]
            )
            
            # 3. Netflix Gurmesi
            rozetler["netflix_gurmesi"] = build_badge_info(
                platform_sayilari["netflix"],
                [(5, "bronz"), (15, "gumus"), (30, "altin"), (50, "elmas")]
            )
            
            # 4. Prime Seçici
            rozetler["prime_secici"] = build_badge_info(
                platform_sayilari["prime"],
                [(5, "bronz"), (15, "gumus"), (30, "altin"), (50, "elmas")]
            )
            
            # 5. Disney Seyyahı
            rozetler["disney_seyyahi"] = build_badge_info(
                platform_sayilari["disney"],
                [(5, "bronz"), (15, "gumus"), (30, "altin"), (50, "elmas")]
            )
            
            # 6. Gizli Cevher Avcısı
            rozetler["gizli_cevher"] = build_badge_info(
                gizli_cevher_sayisi,
                [(1, "bronz"), (3, "gumus"), (5, "altin"), (10, "elmas")]
            )
            
            # Tür Uzmanlıkları
            rozetler["dram_sever"] = build_badge_info(
                tur_sayilari.get("dram", 0),
                [(5, "bronz"), (10, "gumus"), (15, "altin"), (20, "elmas")]
            )
            sci_fi_count = tur_sayilari.get("bilim kurgu", 0) + tur_sayilari.get("bilimkurgu", 0) + tur_sayilari.get("gizem", 0)
            rozetler["bilimkurgu_kasifi"] = build_badge_info(
                sci_fi_count,
                [(5, "bronz"), (10, "gumus"), (15, "altin"), (20, "elmas")]
            )
            comedy_count = tur_sayilari.get("komedi", 0) + tur_sayilari.get("sitcom", 0)
            rozetler["kahkaha_makinesi"] = build_badge_info(
                comedy_count,
                [(5, "bronz"), (10, "gumus"), (15, "altin"), (20, "elmas")]
            )
            crime_count = tur_sayilari.get("suç", 0) + tur_sayilari.get("polisiye", 0)
            rozetler["suc_ortagi"] = build_badge_info(
                crime_count,
                [(5, "bronz"), (10, "gumus"), (15, "altin"), (20, "elmas")]
            )
            
            # Sosyal ve Eleştiri
            rozetler["sosyal_kelebek"] = build_badge_info(
                friend_count,
                [(1, "bronz"), (3, "gumus"), (5, "altin"), (10, "elmas")]
            )
            rozetler["kritik_zihin"] = build_badge_info(
                puanlanan_dizi_sayisi,
                [(5, "bronz"), (10, "gumus"), (15, "altin"), (20, "elmas")]
            )
            
            # Koleksiyoner
            kazanilan_rozet_sayisi = 0
            for k, info in rozetler.items():
                if info["seviye"] is not None:
                    kazanilan_rozet_sayisi += 1
            rozetler["koleksiyoner"] = build_badge_info(
                kazanilan_rozet_sayisi,
                [(3, "bronz"), (6, "gumus"), (10, "altin"), (15, "elmas")]
            )
            
            # Efsane (Gizli Rozet)
            altin_elmas_sayisi = sum(1 for k, info in rozetler.items() if info["seviye"] in ["altin", "elmas"])
            rozetler["efsane"] = build_badge_info(
                altin_elmas_sayisi,
                [(5, "bronz"), (8, "gumus"), (10, "altin"), (12, "elmas")]
            )
            
    except Exception as e:
        print(f"Rozet hesaplama hatası: {e}")
        
    return rozetler

def gpt4o_ile_arama_sirala_ve_yorumla(arama_metni, top_shows_df, username):
    """GPT-4o mini kullanarak ilk 15 sonucu kullanıcı sorgusuna göre sıralar ve kişisel yorum üretir."""
    import openai
    import json
    import os

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {}, list(top_shows_df['isim']) # API key yoksa hiçbir şeyi değiştirme

    # Dizi listesini hazırla
    dizi_listesi = []
    for _, row in top_shows_df.iterrows():
        dizi_listesi.append({
            "isim": str(row['isim']),
            "ozet": str(row.get('ozet', ''))[:300] # Çok uzun özet gönderip token yakmayalım
        })

    client = openai.OpenAI(api_key=api_key)
    
    system_prompt = f"""
    Sen sinema ve dizi konusunda uzman akıllı bir yapay zeka asistanısın.
    Sana gelen kullanıcı arama sorgusuna ve yerel arama motorumuzun bulduğu en iyi dizilere dayanarak şunları yapmalısın:
    1. Bu dizileri, kullanıcının sorgusuna en çok uyacak şekilde kendi içinde mükemmelce sırala.
    2. Her dizi için doğrudan kullanıcıya ({username}) hitap eden, maksimum 1-2 kısa cümleden oluşan, o diziyi neden izlemesi gerektiğini açıklayan bir yorum ('reason') yaz.
    
    JSON Formatında şu şemayı kullanarak yanıt dön:
    {{
      "ordered_recommendations": [
        {{
          "isim": "Dizi Adı",
          "reason": "kullanıcıya hitap eden açıklama"
        }}
      ]
    }}
    Lütfen başka hiçbir metin veya açıklama ekleme, sadece saf JSON döndür.
    """
    
    user_prompt = f"""
    Kullanıcı Adı: {username}
    Kullanıcı Arama Sorgusu: "{arama_metni}"
    
    Aday Dizi Listesi:
    {json.dumps(dizi_listesi, ensure_ascii=False)}
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        
        result_json = json.loads(response.choices[0].message.content)
        recs = result_json.get("ordered_recommendations", [])
        
        reasons_dict = {}
        ordered_names = []
        for r in recs:
            r_name = r.get("isim")
            r_reason = r.get("reason")
            if r_name is not None:
                reasons_dict[r_name] = r_reason
                ordered_names.append(r_name)
                
        return reasons_dict, ordered_names
    except Exception as e:
        import logging
        logging.error(f"GPT-4o mini Arama Sıralama Hatası: {e}")
        return {}, list(top_shows_df['isim'])

def ai_sorgusu_limitle_ve_kaydet(username):
    """Kullanıcı için AI arama sorgu sayısını limitler (Dakikada maks 5 arama, DB-backed)."""
    import time
    current_time = time.time()
    cutoff = current_time - 60.0
    
    with sqlite3.connect(DB_KULLANICILAR, timeout=30.0) as conn:
        cursor = conn.cursor()
        
        # 🧹 Disk ve DB temizliği: 24 saatten eski sorguları periyodik olarak temizle
        try:
            cursor.execute("DELETE FROM ai_sorgulari WHERE timestamp < ?", (current_time - 86400.0,))
        except sqlite3.OperationalError:
            pass
            
        # Son 60 saniyedeki sorguları say
        cursor.execute("SELECT COUNT(*) FROM ai_sorgulari WHERE username = ? AND timestamp > ?", (username.strip(), cutoff))
        count = cursor.fetchone()[0]
        
        if count >= 5:
            return False # Limit aşıldı
            
        # Yeni aramayı kaydet
        cursor.execute("INSERT INTO ai_sorgulari (username, timestamp) VALUES (?, ?)", (username.strip(), current_time))
        conn.commit()
        return True