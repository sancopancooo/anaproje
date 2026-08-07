# -*- coding: utf-8 -*-
"""
==============================================================================
🎬 KESİN VE DOĞRU FİLM PLATFORM DOLDURUCU (v1.0)
==============================================================================
Hedef:
1. 'katalog.db' içerisindeki 'filmler' tablosunu taramak.
2. TMDB (TheMovieDB) Türkiye (TR) Watch Providers verilerinden SIFIR TAHMİN ile
   resmi yayın platformlarını (Netflix, Prime Video, Disney+, HBO Max, TV+, BluTV vb.) çekmek.
3. Türkçe ve Orijinal film isimleri + Yapım yılı ile akıllı TMDB ID eşleştirmesi yapmak.
4. 'rent' (Kirala) ve 'buy' (Satın Al) modundaki Apple TV / TV+ haklarını da kapsamak.
5. Yayın platformu yoksa RASTGELE ATAMA YAPMAYIP 'Diğer Platform' basmak. (Doğruluk Şart!)
==============================================================================
"""

import sqlite3
import requests
import json
import re
import sys
import os
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "katalog.db"
TABLE_NAME = "filmler"
API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"

# 🎯 RESMİ CANONICAL PLATFORM DÖNÜŞÜM MAP'İ
PROVIDER_MAP = {
    "netflix": "Netflix",
    "amazon prime video": "Amazon Prime",
    "amazon prime": "Amazon Prime",
    "prime video": "Amazon Prime",
    "disney plus": "Disney Plus",
    "disney+": "Disney Plus",
    "hbo max": "HBO / Max",
    "max": "HBO / Max",
    "max amazon channel": "HBO / Max",
    "blutv": "BluTV",
    "blu tv": "BluTV",
    "gain": "GAIN",
    "tod": "TOD",
    "bein connect": "TOD",
    "tv+": "TV+",
    "apple tv": "TV+",
    "apple tv store": "TV+",
    "tabii": "Tabii",
    "exxen": "Exxen"
}


def clean_movie_title(raw_title):
    """Film adından parantez içlerini ve ekstra yılı temizler"""
    if not raw_title:
        return "", ""
    
    tr_title = str(raw_title).strip()
    orig_title = ""
    
    # "Başlangıç (Inception)" formatını ayır
    m = re.search(r'^(.*?)\s*[\(\[](.*?)[\)\]]', tr_title)
    if m:
        tr_title = m.group(1).strip()
        orig_title = m.group(2).strip()
        
    return tr_title, orig_title


def search_tmdb_movie(tr_title, orig_title, year=None):
    """TMDB üzerinde Türkçe ve Orijinal başlıkla film arar"""
    headers = {"Accept": "application/json"}
    
    for search_term in [tr_title, orig_title]:
        if not search_term or len(search_term) < 2:
            continue
            
        params = {
            "api_key": API_KEY,
            "query": search_term,
            "language": "tr-TR",
            "include_adult": "false"
        }
        if year and str(year).isdigit():
            params["primary_release_year"] = year
            
        try:
            r = requests.get(f"{BASE_URL}/search/movie", params=params, timeout=8)
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    return results[0].get("id"), results[0].get("title")
        except Exception:
            pass
            
    return None, None


def fetch_tr_watch_providers(tmdb_id):
    """TMDB'den Türkiye (TR) için resmi platformları çeker (Flatrate, Rent, Buy)"""
    if not tmdb_id:
        return []
        
    try:
        url = f"{BASE_URL}/movie/{tmdb_id}/watch/providers"
        r = requests.get(url, params={"api_key": API_KEY}, timeout=8)
        if r.status_code != 200:
            return []
            
        data = r.json().get("results", {}).get("TR", {})
        if not data:
            return []
            
        found_platforms = []
        
        # 1. Flatrate (Abonelik)
        for p in data.get("flatrate", []) or []:
            name = p.get("provider_name", "").lower().strip()
            canonical = PROVIDER_MAP.get(name)
            if canonical and canonical not in found_platforms:
                found_platforms.append(canonical)
                
        # 2. Rent / Buy (Apple TV Store -> TV+ eşleşmesi)
        for key in ["rent", "buy"]:
            for p in data.get(key, []) or []:
                name = p.get("provider_name", "").lower().strip()
                if "apple tv" in name or "tv+" in name:
                    if "TV+" not in found_platforms:
                        found_platforms.append("TV+")
                        
        return found_platforms
    except Exception:
        return []


def run_movie_platform_filler(force_all=False, limit=None):
    print("=" * 80)
    print("🎬 KESİN VE DOĞRU FİLM PLATFORM DOLDURUCU BAŞLATILDI")
    print("=" * 80)

    if not os.path.exists(DB_PATH):
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL;")

    # _platform_audited kolonu yoksa ekle
    c.execute(f"PRAGMA table_info({TABLE_NAME})")
    cols = [r[1] for r in c.fetchall()]
    if "_platform_audited" not in cols:
        c.execute(f"ALTER TABLE {TABLE_NAME} ADD COLUMN _platform_audited INTEGER DEFAULT 0")
        conn.commit()

    if force_all:
        audited_where = ""
    else:
        audited_where = "WHERE (_platform_audited IS NULL OR _platform_audited = 0)"

    c.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    total_count = c.fetchone()[0]

    c.execute(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE _platform_audited = 1")
    already_audited = c.fetchone()[0]

    c.execute(f"""
        SELECT id, isim, vizyon_tarihi, platformlar
        FROM {TABLE_NAME}
        {audited_where}
        ORDER BY id
    """)
    rows = c.fetchall()

    if limit:
        rows = rows[:limit]

    print(f"📋 Toplam Film Sayısı          : {total_count}")
    if not force_all and already_audited > 0:
        print(f"⏩ Daha Önce İşlenen (Atlanan) : {already_audited}")
    print(f"🔍 İşlenecek Kalan Film Sayısı  : {len(rows)}")
    print("-" * 80)

    if len(rows) == 0:
        print("🎉 Tüm filmlerin platform bilgisi zaten taranmış ve güncellenmiş!")
        conn.close()
        return

    updated_count = 0
    for idx, row in enumerate(rows, 1):
        m_id = row["id"]
        raw_name = row["isim"]
        year = str(row["vizyon_tarihi"] or "").strip()
        curr_platforms = str(row["platformlar"] or "").strip()

        tr_title, orig_title = clean_movie_title(raw_name)

        # TMDB'de film ara
        tmdb_id, found_title = search_tmdb_movie(tr_title, orig_title, year=year)

        # Türkiye platformlarını çek
        plat_list = fetch_tr_watch_providers(tmdb_id) if tmdb_id else []

        if plat_list:
            plat_str = ", ".join(plat_list)
        else:
            plat_str = "Diğer Platform"

        print(f"[{idx}/{len(rows)}] 🎬 {tr_title} ({year or 'Tarihsiz'}) -> TMDB: {found_title or 'Bulunamadı'} | Platform: {plat_str}")

        # Veritabanına kaydet ve taranmış olarak işaretle
        c.execute(f"""
            UPDATE {TABLE_NAME}
            SET platformlar = ?, _platform_audited = 1
            WHERE id = ?
        """, (plat_str, m_id))
        
        if idx % 20 == 0:
            conn.commit()
            print(f"💾 [{idx}/{len(rows)}] İlerleme veritabanına kaydedildi.")

        updated_count += 1
        time.sleep(0.15) # Rate limit koruması

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print(f"✅ FİLM PLATFORM TARAMASI TAMAMLANDI! Toplam İşlenen Film: {updated_count}")
    print("=" * 80)

    # Otomatik site verisini dışa aktar
    try:
        import export_data_store
        export_data_store.main()
        print("🎉 data_store.js site verisi başarıyla güncellendi!")
    except Exception as e:
        print(f"⚠️ data_store.js aktarımında hata: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kesin ve Doğru Film Platform Doldurucu")
    parser.add_argument("--force", action="store_true", help="Daha önce tarananları da tekrar tara")
    parser.add_argument("--limit", type=int, default=None, help="İşlenecek maksimum film sayısı")
    args = parser.parse_args()

    run_movie_platform_filler(force_all=args.force, limit=args.limit)
