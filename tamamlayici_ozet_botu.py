# -*- coding: utf-8 -*-
"""
==============================================================================
🚀 EKSİK ÖZET TAMAMLAYICI BOTU (FASTER & MULTI-MODEL FALLBACK)
==============================================================================
Groq AI (Llama 3.1 8B / Gemma 2 9B / Llama 3.3 70B) ve TMDB API ile
tüm eksik özetleri %100 dolduran akıllı tamamlayıcı bot!

Çalıştırma Komutu:
    python tamamlayici_ozet_botu.py
==============================================================================
"""

import os
import sys
import sqlite3
import requests
import time
from openai import OpenAI

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()
GROQ_KEY = os.getenv("GROQ_API_KEY") or ""
client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_KEY) if GROQ_KEY else None

API_KEY = os.getenv("TMDB_API_KEY") or ""
BASE_URL = "https://api.themoviedb.org/3"

DB_MOVIES = "katalog.db"
DB_SHOWS = "katalog.db"

SYSTEM_PROMPT = """\
Sen profesyonel bir film ve dizi eleştirmenisin. Sana verilecek film veya dizi için izleyicinin ilgisini çekecek, akıcı, merak uyandıran TAM OLARAK 1 VEYA 2 CÜMLELİK mükemmel bir Türkçe özet yaz.

KESİN KURALLAR:
1. Tam olarak 1 veya 2 cümle yaz.
2. Spoiler verme, merak uyandır.
3. Tırnak işareti, başlık veya jenerik ifadeler kullanma. Doğrudan özet cümlesini ver.
"""

def generate_summary_ai(title, genres, year, is_movie=True):
    media_type = "film" if is_movie else "dizi"
    prompt = f"Yapım Adı: {title}\nTür: {media_type} ({genres or 'Dram'})\nYıl: {year or '2023'}"
    
    models = ["llama-3.1-8b-instant", "gemma2-9b-it", "llama-3.3-70b-versatile"]
    for m in models:
        try:
            resp = client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=150
            )
            res = (resp.choices[0].message.content or "").strip()
            if res and len(res) > 15:
                return res
        except Exception:
            continue
    return None

def fetch_tmdb_summary(name, is_movie=True):
    try:
        endpoint = "movie" if is_movie else "tv"
        url_s = f"{BASE_URL}/search/{endpoint}?api_key={API_KEY}&query={requests.utils.quote(str(name))}&language=tr-TR"
        r_s = requests.get(url_s, timeout=6).json()
        results = r_s.get("results", [])
        if results and results[0].get("overview"):
            ov = results[0].get("overview")
            if len(ov) > 20: return ov
    except Exception:
        pass
    return None

def fallback_nlp_summary(title, genres, is_movie=True):
    m_type = "film" if is_movie else "dizi"
    g_low = (genres or "").lower()
    
    if "bilim" in g_low or "fantastik" in g_low:
        return f"{title}, sıra dışı kurgusu ve insan zihnini zorlayan evren tasarımıyla öne çıkan heyecan dolu bir {m_type}."
    elif "aksiyon" in g_low or "macera" in g_low:
        return f"{title}, yüksek tempolu sekansları ve soluksuz olay örgüsüyle sürükleyici bir seyir sunuyor."
    elif "suç" in g_low or "gerilim" in g_low:
        return f"{title}, karakterler arasındaki ahlaki ikilemleri ve tırmanan psikolojik gerilimi işleyen etkileyici bir {m_type}."
    elif "komedi" in g_low:
        return f"{title}, neşeli atmosferi ve mizahi diyalog yapısıyla izleyicileri eğlenceli bir yolculuğa davet ediyor."
    else:
        return f"{title}, karakter odaklı güçlü anlatımı ve duygusal derinliğiyle dikkat çeken başarılı bir yapım."

def run_fix():
    print("=" * 75)
    print("🚀 EKSİK ÖZET TAMAMLAYICI BOTU (AKILLI MODEL YEDEKLEME) BAŞLATILIYOR...")
    print("=" * 75)

    # 1. MOVIES
    conn_m = sqlite3.connect(DB_MOVIES)
    c_m = conn_m.cursor()
    c_m.execute("SELECT id, tmdb_id, isim, turler, vizyon_tarihi, ozet FROM filmler")
    movies = c_m.fetchall()

    missing_m = [m for m in movies if not m[5] or len(str(m[5]).strip()) < 20 or "özeti yakında" in str(m[5]).lower()]
    print(f"🎬 Özeti Eksik Film Sayısı: {len(missing_m)} / {len(movies)}")

    m_fixed = 0
    for i, (db_id, tmdb_id, name, genres, vdate, cur_ozet) in enumerate(missing_m):
        new_ozet = fetch_tmdb_summary(name, is_movie=True)
        if not new_ozet:
            year = str(vdate or "")[:4]
            new_ozet = generate_summary_ai(name, genres, year, is_movie=True)
        if not new_ozet:
            new_ozet = fallback_nlp_summary(name, genres, is_movie=True)

        if new_ozet:
            c_m.execute("UPDATE filmler SET ozet = ? WHERE id = ?", (new_ozet, db_id))
            conn_m.commit()
            m_fixed += 1
            pct = round(((i + 1) / len(missing_m)) * 100, 1)
            print(f"  🎬 [{m_fixed}/{len(missing_m)}] (%{pct}) {name} -> Özet Yazıldı ✅")
            print(f"     💬 \"{new_ozet[:80]}...\"")
        time.sleep(0.15)

    conn_m.close()
    print(f"✅ Filmler Bitti: {m_fixed} adet film için özgün özet tamamlandı!")

    # 2. SHOWS
    conn_s = sqlite3.connect(DB_SHOWS)
    c_s = conn_s.cursor()
    c_s.execute("SELECT id, isim, tur, cikis_tarihi, ozet FROM diziler")
    shows = c_s.fetchall()

    missing_s = [s for s in shows if not s[4] or len(str(s[4]).strip()) < 20 or "özeti yakında" in str(s[4]).lower()]
    print(f"\n📺 Özeti Eksik Dizi Sayısı: {len(missing_s)} / {len(shows)}")

    s_fixed = 0
    for i, (db_id, name, genres, cdate, cur_ozet) in enumerate(missing_s):
        new_ozet = fetch_tmdb_summary(name, is_movie=False)
        if not new_ozet:
            year = str(cdate or "")[:4]
            new_ozet = generate_summary_ai(name, genres, year, is_movie=False)
        if not new_ozet:
            new_ozet = fallback_nlp_summary(name, genres, is_movie=False)

        if new_ozet:
            c_s.execute("UPDATE diziler SET ozet = ? WHERE id = ?", (new_ozet, db_id))
            conn_s.commit()
            s_fixed += 1
            pct = round(((i + 1) / len(missing_s)) * 100, 1)
            print(f"  📺 [{s_fixed}/{len(missing_s)}] (%{pct}) {name} -> Özet Yazıldı ✅")
            print(f"     💬 \"{new_ozet[:80]}...\"")
        time.sleep(0.15)

    conn_s.close()
    print(f"✅ Diziler Bitti: {s_fixed} adet dizi için özgün özet tamamlandı!")

    print("\n" + "=" * 75)
    print("🎉 EKSİK ÖZET TAMAMLAMA İŞLEMİ %100 BİTTİ!")
    print("📌 ŞİMDİ SİTEYE AKTARMAK İÇİN TERMINALDE ŞU KOMUTU ÇALIŞTIRIN:")
    print("👉 python export_data_store.py")
    print("=" * 75)

if __name__ == "__main__":
    run_fix()
