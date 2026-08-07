# -*- coding: utf-8 -*-
"""
tmdb_ek_veri_toplayici.py
--------------------------------------------------------------
TMDb API'sinden Diziler ve Filmler için Ekstra Zengin Verileri Çeker:
- HD Arka Plan Resmi (backdrop_url)
- Orijinal Dil (orijinal_dil)
- Yapım Ülkeleri (yapim_ulkeleri)
- Yapım Şirketleri (yapim_sirketleri)
- TV Yayın Ağları (yayin_aglari - HBO, Netflix vb.)
- Bütçe ve Hasılat (butce, hasilat - Filmler için)
- Slogan (slogan / tagline)
- TMDb Önerilen ve Benzer Yapım ID'leri (onerilen_idleri, benzer_idleri)
- Gelecek / Son Bölüm Detayı (Diziler için)

Tüm verileri veritabanına dokunmadan JSON dosyalarına kaydeder:
- tmdb_ek_veriler_diziler.json
- tmdb_ek_veriler_filmler.json
--------------------------------------------------------------
Kullanım:
    python tmdb_ek_veri_toplayici.py --limit 10          (Test amaçlı 10'ar tane çeker)
    python tmdb_ek_veri_toplayici.py                     (Tüm veri setini çeker)
    python tmdb_ek_veri_toplayici.py --target diziler    (Sadece dizileri çeker)
    python tmdb_ek_veri_toplayici.py --target filmler    (Sadece filmleri çeker)
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"
DB_PATH = "katalog.db"

DIZI_JSON_PATH = "tmdb_ek_veriler_diziler.json"
FILM_JSON_PATH = "tmdb_ek_veriler_filmler.json"

IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w1280"

SAVE_EVERY = 20
SLEEP_BETWEEN = 0.15


def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ {filepath} okunurken hata oluştu, yeni oluşturulacak: {e}")
    return {}


def save_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_movie_extras(tmdb_id):
    url = f"{BASE_URL}/movie/{tmdb_id}?api_key={API_KEY}&language=tr-TR&append_to_response=recommendations,similar"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            d = r.json()
            backdrop_path = d.get("backdrop_path")
            return {
                "tmdb_id": tmdb_id,
                "isim": d.get("title") or d.get("original_title"),
                "orijinal_isim": d.get("original_title"),
                "backdrop_path": backdrop_path,
                "backdrop_url": f"{IMAGE_BASE_URL}{backdrop_path}" if backdrop_path else None,
                "orijinal_dil": d.get("original_language"),
                "yapim_ulkeleri": [c.get("iso_3166_1") for c in d.get("production_countries", []) if c.get("iso_3166_1")],
                "yapim_sirketleri": [p.get("name") for p in d.get("production_companies", []) if p.get("name")],
                "butce": d.get("budget", 0),
                "hasilat": d.get("revenue", 0),
                "slogan": d.get("tagline"),
                "koleksiyon": d.get("belongs_to_collection", {}).get("name") if d.get("belongs_to_collection") else None,
                "onerilen_film_idleri": [item["id"] for item in d.get("recommendations", {}).get("results", []) if "id" in item],
                "benzer_film_idleri": [item["id"] for item in d.get("similar", {}).get("results", []) if "id" in item]
            }
        elif r.status_code == 404:
            print(f"❌ Film ID {tmdb_id} TMDB'de bulunamadı (404).")
            return None
        else:
            print(f"⚠️ Film ID {tmdb_id} hata döndü: Status {r.status_code}")
            return None
    except Exception as e:
        print(f"⚠️ Film ID {tmdb_id} çekilirken istisna: {e}")
        return None


def fetch_tv_extras(tv_id):
    url = f"{BASE_URL}/tv/{tv_id}?api_key={API_KEY}&language=tr-TR&append_to_response=recommendations,similar,content_ratings"
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            d = r.json()
            backdrop_path = d.get("backdrop_path")
            
            # İçerik derecelendirmesi (TR veya US)
            content_rating = None
            ratings = d.get("content_ratings", {}).get("results", [])
            for r_item in ratings:
                if r_item.get("iso_3166_1") in ["TR", "US"]:
                    content_rating = r_item.get("rating")
                    break

            next_ep = d.get("next_episode_to_air")
            next_ep_data = None
            if next_ep:
                next_ep_data = {
                    "bolum_adi": next_ep.get("name"),
                    "yayin_tarihi": next_ep.get("air_date"),
                    "sezon_no": next_ep.get("season_number"),
                    "bolum_no": next_ep.get("episode_number")
                }

            return {
                "dizi_id": tv_id,
                "isim": d.get("name") or d.get("original_name"),
                "orijinal_isim": d.get("original_name"),
                "backdrop_path": backdrop_path,
                "backdrop_url": f"{IMAGE_BASE_URL}{backdrop_path}" if backdrop_path else None,
                "orijinal_dil": d.get("original_language"),
                "origin_country": d.get("origin_country", []),
                "yapim_ulkeleri": [c.get("iso_3166_1") for c in d.get("production_countries", []) if c.get("iso_3166_1")],
                "yayin_aglari": [n.get("name") for n in d.get("networks", []) if n.get("name")],
                "yapim_sirketleri": [p.get("name") for p in d.get("production_companies", []) if p.get("name")],
                "icerik_derecelendirme": content_rating,
                "sonraki_bolum": next_ep_data,
                "onerilen_dizi_idleri": [item["id"] for item in d.get("recommendations", {}).get("results", []) if "id" in item],
                "benzer_dizi_idleri": [item["id"] for item in d.get("similar", {}).get("results", []) if "id" in item]
            }
        elif r.status_code == 404:
            print(f"❌ Dizi ID {tv_id} TMDB'de bulunamadı (404).")
            return None
        else:
            print(f"⚠️ Dizi ID {tv_id} hata döndü: Status {r.status_code}")
            return None
    except Exception as e:
        print(f"⚠️ Dizi ID {tv_id} çekilirken istisna: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="TMDB Ekstra Veri Çekici (JSON Modu)")
    parser.add_argument("--limit", type=int, default=0, help="İşlenecek maksimum öge sayısı (0 = Tümü)")
    parser.add_argument("--target", choices=["all", "diziler", "filmler"], default="all", help="İşlenecek hedef")
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # --- 1. FILMLER İŞLEME ---
    if args.target in ["all", "filmler"]:
        film_json_data = load_json(FILM_JSON_PATH)
        cursor.execute("SELECT tmdb_id, isim FROM filmler WHERE tmdb_id IS NOT NULL AND tmdb_id != ''")
        movies = cursor.fetchall()
        
        print(f"\n🎬 Film Verileri Çekiliyor... Toplam Veritabanı Film Sayısı: {len(movies)}")
        print(f"ℹ️ Zaten JSON'da Kayıtlı Olan Film Sayısı: {len(film_json_data)}")

        processed = 0
        saved_count = 0
        for tmdb_id, isim in movies:
            str_id = str(tmdb_id)
            if str_id in film_json_data:
                continue

            data = fetch_movie_extras(tmdb_id)
            if data:
                film_json_data[str_id] = data
                saved_count += 1

            processed += 1
            if saved_count > 0 and saved_count % SAVE_EVERY == 0:
                save_json(FILM_JSON_PATH, film_json_data)
                print(f"💾 Filmler Kaydedildi... (Toplam JSON Kayıt: {len(film_json_data)})")

            if args.limit > 0 and processed >= args.limit:
                print(f"🛑 Limit ulaşıldı ({args.limit} film).")
                break

            time.sleep(SLEEP_BETWEEN)

        save_json(FILM_JSON_PATH, film_json_data)
        print(f"✅ Film İşlemi Tamamlandı. Toplam Kaydedilen: {len(film_json_data)}")

    # --- 2. DIZILER İŞLEME ---
    if args.target in ["all", "diziler"]:
        dizi_json_data = load_json(DIZI_JSON_PATH)
        cursor.execute("SELECT id, isim FROM diziler WHERE id IS NOT NULL")
        shows = cursor.fetchall()

        print(f"\n📺 Dizi Verileri Çekiliyor... Toplam Veritabanı Dizi Sayısı: {len(shows)}")
        print(f"ℹ️ Zaten JSON'da Kayıtlı Olan Dizi Sayısı: {len(dizi_json_data)}")

        processed = 0
        saved_count = 0
        for tv_id, isim in shows:
            str_id = str(tv_id)
            if str_id in dizi_json_data:
                continue

            data = fetch_tv_extras(tv_id)
            if data:
                dizi_json_data[str_id] = data
                saved_count += 1

            processed += 1
            if saved_count > 0 and saved_count % SAVE_EVERY == 0:
                save_json(DIZI_JSON_PATH, dizi_json_data)
                print(f"💾 Diziler Kaydedildi... (Toplam JSON Kayıt: {len(dizi_json_data)})")

            if args.limit > 0 and processed >= args.limit:
                print(f"🛑 Limit ulaşıldı ({args.limit} dizi).")
                break

            time.sleep(SLEEP_BETWEEN)

        save_json(DIZI_JSON_PATH, dizi_json_data)
        print(f"✅ Dizi İşlemi Tamamlandı. Toplam Kaydedilen: {len(dizi_json_data)}")

    conn.close()
    print("\n🎉 Tüm Ekstra TMDB Verileri Başarıyla Çekildi ve JSON Dosyalarına Kaydedildi!")


if __name__ == "__main__":
    main()
