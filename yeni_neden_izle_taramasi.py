"""
==============================================================================
💡 YENİ YAPIMLAR İÇİN "NEDEN İZLEMELİSİN?" ÜRETİCİ BOT (CANLI İLERLEME LOGLU)
==============================================================================
Veritabanlarındaki "Neden İzlemelisin?" maddeleri eksik veya jenerik olan tüm
yeni film ve dizileri tespit eder; canlı terminal loglarıyla 3 maddelik zengin
"Neden İzlemelisin?" listesi basar!

Kullanım:
python yeni_neden_izle_taramasi.py
==============================================================================
"""

import sqlite3
import json
import os
import sys
import subprocess

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

neden_izle_pool = {}
if os.path.exists('neden_izle_havuzu.json'):
    with open('neden_izle_havuzu.json', 'r', encoding='utf-8') as f:
        neden_izle_pool = json.load(f)

def generate_smart_why_watch(title, genres_raw, summary_raw, rating_num, director=None, is_movie=True):
    g_str = str(genres_raw or '').lower()
    sum_str = str(summary_raw or '').lower()
    r_val = float(rating_num or 7.5)
    
    p1, p2, p3 = "", "", ""

    if director and director != "Bilinmiyor":
        p1 = f"{director} yönetmenliğinde öne çıkan etkileyici sinematik atmosfer."
    elif 'aksiyon' in g_str or 'macera' in g_str:
        p1 = "Yüksek tempolu sahneleri ve sürükleyici macera dolu kurgusu."
    elif 'bilim' in g_str or 'fantastik' in g_str:
        p1 = "Ufuk açıcı evren tasarımı, yüksek görsel kalite ve özgün kurgu."
    elif 'komedi' in g_str:
        p1 = "Eğlenceli atmosferi ve karakterler arası keyifli dinamikler."
    elif 'suç' in g_str or 'gerilim' in g_str or 'gizem' in g_str:
        p1 = "Gizem dolu olay örgüsü ve sürprizlerle dolu gerilim temposu."
    elif 'animasyon' in g_str:
        p1 = "Büyüleyici görsel dünyası ve her yaşa hitap eden duygusal derinliği."
    else:
        p1 = "Derinlikli kurgusu ve güçlü karakter anlatımı."

    if r_val >= 8.0:
        p2 = f"{r_val:.1f} yüksek izleyici puanıyla türün en beğenilen ve ikonik yapımlarından biri."
    elif r_val >= 7.0:
        p2 = f"{r_val:.1f} güçlü puanıyla türün tutkunları için kaçırılmayacak akıcı bir seyir."
    else:
        p2 = "Sürükleyici temposu ve merak uyandıran olay zinciri."

    p3 = "Görsel kalitesi, tempolu yapısı ve akıcı hikaye anlatımı."

    return [p1, p2, p3]

def process_movies():
    print("\n--- 🎬 FİLMLER İÇİN NEDEN İZLEMELİSİN MADDELERİ ÜRETİLİYOR ---")
    conn = sqlite3.connect('katalog.db', timeout=60.0)
    c = conn.cursor()

    c.execute('''
        SELECT id, tmdb_id, isim, turler, ozet, puan, yonetmen, neden_izlemeli 
        FROM filmler 
        WHERE neden_izlemeli IS NULL OR neden_izlemeli = "" OR neden_izlemeli LIKE "%Bilinmiyor%" OR neden_izlemeli = "[]"
    ''')
    rows = c.fetchall()
    total = len(rows)
    print(f"📦 Maddeleri eksik {total} adet film bulundu. Canlı işleme başlatıldı...\n")

    updated = 0
    for idx, row in enumerate(rows, start=1):
        db_id, tmdb_id, title, genres, summary, rating, director, cur_why = row

        maddeler = None
        if str(tmdb_id) in neden_izle_pool and isinstance(neden_izle_pool[str(tmdb_id)], dict):
            maddeler = neden_izle_pool[str(tmdb_id)].get('maddeler')
        elif title in neden_izle_pool and isinstance(neden_izle_pool[title], dict):
            maddeler = neden_izle_pool[title].get('maddeler')

        if not maddeler or not isinstance(maddeler, list):
            maddeler = generate_smart_why_watch(title, genres, summary, rating, director, is_movie=True)

        maddeler_json = json.dumps(maddeler, ensure_ascii=False)
        c.execute('UPDATE filmler SET neden_izlemeli = ? WHERE id = ?', (maddeler_json, db_id))
        updated += 1

        # Live Terminal Progress
        pct = (idx / total) * 100
        print(f"[{idx}/{total}] (%{pct:.1f}) 💡 {title[:30]:<30} -> 3 Madde Eklendi ✅")

        if idx % 20 == 0:
            conn.commit()

    conn.commit()
    conn.close()
    print(f"\n✅ {updated} film için 'Neden İzlemelisin?' maddeleri başarıyla güncellendi!")

def process_shows():
    print("\n--- 📺 DİZİLER İÇİN NEDEN İZLEMELİSİN MADDELERİ ÜRETİLİYOR ---")
    conn = sqlite3.connect('katalog.db', timeout=60.0)
    c = conn.cursor()

    c.execute('''
        SELECT id, isim, tur, ozet, puan_ortalamasi, neden_izlemeli 
        FROM diziler 
        WHERE neden_izlemeli IS NULL OR neden_izlemeli = "" OR neden_izlemeli LIKE "%Bilinmiyor%" OR neden_izlemeli = "[]"
    ''')
    rows = c.fetchall()
    total = len(rows)
    print(f"📦 Maddeleri eksik {total} adet dizi bulundu. Canlı işleme başlatıldı...\n")

    updated = 0
    for idx, row in enumerate(rows, start=1):
        db_id, title, genres, summary, rating, cur_why = row

        maddeler = None
        if title in neden_izle_pool and isinstance(neden_izle_pool[title], dict):
            maddeler = neden_izle_pool[title].get('maddeler')

        if not maddeler or not isinstance(maddeler, list):
            maddeler = generate_smart_why_watch(title, genres, summary, rating, is_movie=False)

        maddeler_json = json.dumps(maddeler, ensure_ascii=False)
        c.execute('UPDATE diziler SET neden_izlemeli = ? WHERE id = ?', (maddeler_json, db_id))
        updated += 1

        pct = (idx / total) * 100
        print(f"[{idx}/{total}] (%{pct:.1f}) 💡 {title[:30]:<30} -> 3 Madde Eklendi ✅")

        if idx % 20 == 0:
            conn.commit()

    conn.commit()
    conn.close()
    print(f"\n✅ {updated} dizi için 'Neden İzlemelisin?' maddeleri başarıyla güncellendi!")

if __name__ == '__main__':
    print("========================================================================")
    print("🚀 YENİ YAPIMLAR İÇİN NEDEN İZLEMELİSİN ÜRETİCİ BOT BAŞLATILIYOR...")
    print("========================================================================\n")
    process_movies()
    process_shows()

    print("\n--- 💾 data_store.js YENİDEN AKTARILIYOR ---")
    try:
        subprocess.run([sys.executable, 'export_data_store.py'], check=True)
        print("✅ data_store.js başarıyla güncellendi!")
    except Exception as e:
        print(f"⚠️ export_data_store.py uyarısı: {e}")
