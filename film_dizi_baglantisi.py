# -*- coding: utf-8 -*-
"""
==========================================================================
🎬 MATRIX DİZİ & FİLM PLATFORMU - MERKEZİ VERİ VE ENTEGRASYON MODÜLÜ
==========================================================================
Açıklama: Bu dosya 'movies_dataset.json' (Film Verisi) ve 'katalog.db'
(Dizi Veritabanı) kaynaklarını tek bir çatı altında birleştirerek performanslı
arama, filtreleme, puan sıralama ve AI öneri uç noktalarını sağlar.
==========================================================================
"""

import os
import json
import sqlite3
import logging
from typing import List, Dict, Any, Optional

# Loglama ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MatrixApp")

# Dosya Yolları
MOVIES_JSON_PATH = os.path.join(os.path.dirname(__file__), "movies_dataset.json")
SERIES_DB_PATH = os.path.join(os.path.dirname(__file__), "katalog.db")


# ==========================================================================
# 📌 BAŞLIK 1: FİLM VERİLERİNİ YÜKLEME VE İŞLEME (MOVIES_DATASET.JSON)
# ==========================================================================
# Açıklama: filmler.py script'i ile çekilen 3000+ film verisini belleğe yükler
# ve hızlı sorgulanabilir veri yapısına dönüştürür.
# ==========================================================================

def yukle_film_verileri() -> List[Dict[str, Any]]:
    """movies_dataset.json dosyasından film listesini güvenli bir şekilde yükler."""
    if not os.path.exists(MOVIES_JSON_PATH):
        logger.warning(f"⚠️ Film veri dosyası bulunamadı: {MOVIES_JSON_PATH}")
        return []
    
    try:
        with open(MOVIES_JSON_PATH, "r", encoding="utf-8") as f:
            filmler = json.load(f)
            logger.info(f"✅ Toplam {len(filmler)} adet film verisi başarıyla yüklendi.")
            return filmler
    except Exception as e:
        logger.error(f"❌ Film verisi yüklenirken hata oluştu: {e}")
        return []


# ==========================================================================
# 📌 BAŞLIK 2: DİZİ VERİLERİNİ SORGULAMA (DIZILER_VERITABANI.DB)
# ==========================================================================
# Açıklama: dizimibul projesindeki SQLite veritabanından dizileri çeker.
# ==========================================================================

def get_db_connection():
    """SQLite veritabanı bağlantısı açar."""
    if not os.path.exists(SERIES_DB_PATH):
        logger.warning(f"⚠️ Dizi veritabanı bulunamadı: {SERIES_DB_PATH}")
        return None
    conn = sqlite3.connect(SERIES_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def yukle_dizi_verileri(limit: int = 50) -> List[Dict[str, Any]]:
    """Dizi veritabanından dizi kayıtlarını çeker."""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM diziler ORDER BY puan_ortalamasi DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        diziler = [dict(row) for row in rows]
        conn.close()
        logger.info(f"✅ Toplam {len(diziler)} adet dizi verisi SQLite'tan çekildi.")
        return diziler
    except Exception as e:
        logger.error(f"❌ Dizi verisi çekilirken hata oluştu: {e}")
        return []


# ==========================================================================
# 📌 BAŞLIK 3: ORTAK FİLTRELEME VE ARAMA MOTORU (UNIFIED FILTER ENGINE)
# ==========================================================================
# Açıklama: Kullanıcının Kırmızı (Film) veya Mavi (Dizi) evreninde yaptığı
# arama, tür, platform ve minimum puan filtrelerini uygular.
# ==========================================================================

def icerik_filtrele(
    evren: str = "MOVIES",  # 'MOVIES' (Film) veya 'SERIES' (Dizi)
    min_puan: float = 7.0,
    tur: str = "ALL",
    platform: str = "ALL",
    arama_metni: str = ""
) -> List[Dict[str, Any]]:
    """Gelen filtrelere göre filmleri veya dizileri süzer."""
    
    if evren == "MOVIES":
        veri_seti = yukle_film_verileri()
    else:
        veri_seti = yukle_dizi_verileri(limit=100)
    
    sonuclar = []
    arama_metni_lower = arama_metni.lower().strip()

    for item in veri_seti:
        # Puan Kontrolü
        puan = item.get("puan_ortalamasi") or item.get("puan") or item.get("rating") or item.get("vote_average") or 0.0
        try:
            puan = float(puan)
        except (ValueError, TypeError):
            puan = 0.0
        
        if puan < min_puan:
            continue

        # Tür Kontrolü
        turler = item.get("genres") or item.get("turler") or item.get("tur") or []
        if isinstance(turler, str):
            turler = [t.strip() for t in turler.split(",")]
        
        if tur != "ALL" and tur not in turler:
            continue

        # Platform Kontrolü
        platformlar = item.get("streaming_platforms") or item.get("platformlar") or []
        if isinstance(platformlar, str):
            platformlar = [p.strip() for p in platformlar.split(",")]
        
        if platform != "ALL" and platform not in platformlar:
            continue

        # Arama Metni Kontrolü
        baslik = item.get("title") or item.get("isim") or item.get("dizi_adi") or ""
        oyuncular = str(item.get("cast") or item.get("oyuncular_gercek") or item.get("oyuncular") or "")
        
        if arama_metni_lower:
            if arama_metni_lower not in baslik.lower() and arama_metni_lower not in oyuncular.lower():
                continue

        sonuclar.append(item)

    return sonuclar


# ==========================================================================
# 📌 BAŞLIK 4: MODÜL TEST KODLARI (STANDALONE TEST)
# ==========================================================================
if __name__ == "__main__":
    print("--- MATRIX VERI ENTEGRASYON TESTI ---")
    film_test = yukle_film_verileri()
    print(f"Film Veri Sayisi: {len(film_test)}")
    
    dizi_test = yukle_dizi_verileri(limit=5)
    print(f"Dizi Veri Ornek Sayisi: {len(dizi_test)}")
