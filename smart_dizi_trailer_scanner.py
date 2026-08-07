# -*- coding: utf-8 -*-
"""
==========================================================================
🎬 AKILLI DIZI FRAGMAN TARAYICI (smart_dizi_trailer_scanner.py)
==========================================================================
Özellikler:
1. Platform Bazlı Resmi Kanal Önceliği:
   - Netflix -> Netflix Türkiye & Netflix Global
   - Amazon Prime -> Prime Video Türkiye & Amazon Prime Video
   - Disney Plus -> Disney+ Türkiye & Disney Plus
   - HBO Max -> Max Türkiye & HBO Max
   - BluTV, GAIN, Exxen, Tabii, TV+, MUBI -> Kendi Resmi Kanalları
2. Diziye Özel Fragman Yapısı (Dublaj Yok):
   - Slot 1: Türkçe Fragman / Türkçe Altyazılı (Resmi TR kanalı veya altyazı doğrulamalı)
   - Slot 2: Orijinal / İngilizce Fragman (Resmi Global kanal veya genel arama)
3. Esnek Filtreleme:
   - "Resmi Fragman", "1. Sezon Fragmanı", "Tanıtım", "Teaser" videolarını Kabul Eder.
   - Fanmade, Edit, Reaction, Gameplay, Full Bölüm spamlarını Elerr.
4. Veritabanı ve Web Otomatik Güncelleme:
   - diziler_veritabani.db ve diziler_veritabanı.db dosyalarını günceller.
   - Periyodik olarak export_data_store.py çalıştırarak data_store.js'i yeniler.
==========================================================================
"""

import os
import sys
import json
import time
import re
import sqlite3
import unicodedata
import urllib.request
import urllib.parse
import urllib.error

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DB_FILES = ["katalog.db"]

# 🎯 PLATFORM RESMİ KANAL VE SORGU EŞLEŞTİRMESİ
PLATFORM_CHANNEL_MAP = {
    'netflix': {
        'tr_channel': 'Netflix Türkiye',
        'global_channel': 'Netflix',
        'tr_queries': ['"{title}" Netflix Türkiye resmi fragman', '"{title}" Netflix Türkiye'],
        'global_queries': ['"{orig}" Netflix official trailer', '"{orig}" Netflix trailer']
    },
    'amazon prime': {
        'tr_channel': 'Prime Video Türkiye',
        'global_channel': 'Amazon Prime Video',
        'tr_queries': ['"{title}" Prime Video Türkiye resmi fragman', '"{title}" Prime Video Türkiye'],
        'global_queries': ['"{orig}" Prime Video official trailer', '"{orig}" Amazon Prime Video trailer']
    },
    'amazon prime video': {
        'tr_channel': 'Prime Video Türkiye',
        'global_channel': 'Amazon Prime Video',
        'tr_queries': ['"{title}" Prime Video Türkiye resmi fragman', '"{title}" Prime Video Türkiye'],
        'global_queries': ['"{orig}" Prime Video official trailer']
    },
    'disney plus': {
        'tr_channel': 'Disney+ Türkiye',
        'global_channel': 'Disney Plus',
        'tr_queries': ['"{title}" Disney+ Türkiye resmi fragman', '"{title}" Disney Türkiye fragman'],
        'global_queries': ['"{orig}" Disney Plus official trailer']
    },
    'disney+': {
        'tr_channel': 'Disney+ Türkiye',
        'global_channel': 'Disney Plus',
        'tr_queries': ['"{title}" Disney+ Türkiye resmi fragman', '"{title}" Disney Türkiye fragman'],
        'global_queries': ['"{orig}" Disney Plus official trailer']
    },
    'hbo': {
        'tr_channel': 'HBO Max Türkiye',
        'global_channel': 'Max',
        'tr_queries': ['"{title}" Max Türkiye resmi fragman', '"{title}" HBO Max Türkiye'],
        'global_queries': ['"{orig}" Max official trailer', '"{orig}" HBO official trailer']
    },
    'hbo max': {
        'tr_channel': 'HBO Max Türkiye',
        'global_channel': 'Max',
        'tr_queries': ['"{title}" Max Türkiye resmi fragman', '"{title}" HBO Max Türkiye'],
        'global_queries': ['"{orig}" Max official trailer', '"{orig}" HBO official trailer']
    },
    'blutv': {
        'tr_channel': 'BluTV',
        'global_channel': 'BluTV',
        'tr_queries': ['"{title}" BluTV fragman', '"{title}" BluTV'],
        'global_queries': ['"{orig}" BluTV official trailer']
    },
    'gain': {
        'tr_channel': 'GAIN',
        'global_channel': 'GAIN',
        'tr_queries': ['"{title}" GAIN fragman', '"{title}" GAIN'],
        'global_queries': ['"{orig}" GAIN official trailer']
    },
    'exxen': {
        'tr_channel': 'Exxen',
        'global_channel': 'Exxen',
        'tr_queries': ['"{title}" Exxen fragman', '"{title}" Exxen'],
        'global_queries': ['"{orig}" Exxen official trailer']
    },
    'tabii': {
        'tr_channel': 'tabii',
        'global_channel': 'tabii',
        'tr_queries': ['"{title}" tabii fragman', '"{title}" tabii'],
        'global_queries': ['"{orig}" tabii official trailer']
    },
    'tv+': {
        'tr_channel': 'TV+',
        'global_channel': 'Apple TV',
        'tr_queries': ['"{title}" TV+ fragman', '"{title}" Apple TV Türkiye'],
        'global_queries': ['"{orig}" Apple TV official trailer']
    },
    'mubi': {
        'tr_channel': 'MUBI Türkiye',
        'global_channel': 'MUBI',
        'tr_queries': ['"{title}" MUBI Türkiye fragman', '"{title}" MUBI Türkiye'],
        'global_queries': ['"{orig}" MUBI official trailer']
    }
}

# ❌ SPAM / FANMADE / İNCELEME, KISIM/BÖLÜM VE FİLM/SPINOFF FİLTRELERİ
BAD_KEYWORDS = [
    'fan made', 'fanmade', 'fan-made', 'concept', 'concept trailer', 'idea trailer',
    'edit', 'reaction', 'gameplay', 'spoof', 'parody', 'smasher', 'screen culture',
    'full episode', 'tek parça', 'bölüm izle', 'tam bölüm', '1. bölüm izle', 'dizi izle',
    's01e01', 's01e02', 'review', 'inceleme', 'recap', 'analiz', 'ozet', 'özet',
    'son sahne', 'ending scene', 'oyun videosu', 'shorts', 'tiktok',
    # 🚫 FİLM / TEK BÖLÜM SPİNOFF ENGELLEME (Dizi yerine film fragmanı gelmesini engeller)
    'film', 'filmi', 'movie', 'el camino', 'bölüm', 'bolum', 'episode',
    # 🚫 SONRAKİ SEZON, FİNAL VE KISIMLARI ENGELLE (2. Sezon, Final Fragman vb. engellenir; 1. Sezon veya Genel Fragman kabul edilir)
    'final trailer', 'official final trailer', 'final season', 'final sezon', 'series finale', 'final fragmanı', 'final fragman',
    '2. sezon', '3. sezon', '4. sezon', '5. sezon', '6. sezon', '7. sezon', '8. sezon', '9. sezon', '10. sezon', '11. sezon',
    '2.sezon', '3.sezon', '4.sezon', '5.sezon', '6.sezon', '7.sezon', '8.sezon', '9.sezon', '10.sezon', '11.sezon',
    'season 2', 'season 3', 'season 4', 'season 5', 'season 6', 'season 7', 'season 8', 'season 9', 'season 10', 'season 11',
    'stranger things 2', 'stranger things 3', 'stranger things 4', 'stranger things 5',
    's02', 's03', 's04', 's05', 's06', 's07', 's08', 's09', 's10', 's11',
    '2. kısım', '3. kısım', '4. kısım', '5. kısım',
    'part 2', 'part 3', 'part 4', 'part 5',
    'volume 2', 'vol 2', 'vol. 2', 'vol.2', 'vol 3', 'vol 4'
]

# 🇹🇷 TÜRKÇE İŞARETLERİ (Kanal veya Başlıkta Olmalı)
TR_MARKS = [
    'türkçe', 'turkce', 'altyazı', 'altyazılı', 'altyazili', 'fragman', 'fragmanı',
    'tanıtım', 'tanıtımı', 'tanitim', 'resmi fragman', 'resmi tanıtım',
    'netflix türkiye', 'prime video türkiye', 'disney+ türkiye', 'blutv', 'gain',
    'exxen', 'tabii', 'digiturk', 'tivibu', 'tv+', 'box office türkiye'
]

STOP_WORDS = {'the', 'a', 'an', 'of', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 've', 'ile', 'bir', 'bu'}

def parse_duration(s):
    if not s: return 0
    parts = s.split(':')
    try:
        if len(parts) == 3: return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
        if len(parts) == 2: return int(parts[0])*60 + int(parts[1])
    except Exception: pass
    return 0

def is_title_matched(title, orig_title, video_title):
    vt = video_title.lower()
    st = title.lower()
    ot = orig_title.lower() if orig_title else ""
    if st in vt or (ot and ot in vt):
        return True
    words = [w for w in re.findall(r'[\w]+', st) if len(w) > 2 and w not in STOP_WORDS]
    if words and sum(1 for w in words if w in vt) == len(words):
        return True
    return False

def search_yt(query):
    url = 'https://www.youtube.com/results?search_query=' + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8'
    })
    try:
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
        m = re.search(r'ytInitialData\s*=\s*(\{.*?\});</script>', html) or re.search(r'var ytInitialData = (\{.*?\});</script>', html)
        if not m: return []
        data = json.loads(m.group(1))
        results = []
        sections = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
        for sec in sections:
            for item in sec.get('itemSectionRenderer', {}).get('contents', []):
                vr = item.get('videoRenderer')
                if not vr: continue
                vid_id = vr.get('videoId', '')
                truns = vr.get('title', {}).get('runs', [])
                vtitle = truns[0].get('text', '') if truns else ''
                cruns = vr.get('ownerText', {}).get('runs', [])
                channel = cruns[0].get('text', '') if cruns else ''
                dur_str = vr.get('lengthText', {}).get('simpleText', '')
                dur = parse_duration(dur_str)
                if vid_id and vtitle:
                    results.append({'id': vid_id, 'title': vtitle, 'channel': channel, 'duration': dur})
        return results
    except Exception as e:
        return []

def find_dizi_trailers(title, orig_title=None, platform_str=None):
    orig_title = orig_title or title
    plat_key = None
    if platform_str:
        for p in PLATFORM_CHANNEL_MAP:
            if p in platform_str.lower():
                plat_key = p
                break

    # 1. 🇹🇷 TÜRKÇE FRAGMAN ARAMASI
    tr_url = ""
    tr_title_found = ""
    queries_tr = []
    
    if plat_key and plat_key in PLATFORM_CHANNEL_MAP:
        queries_tr = [q.format(title=title, orig=orig_title) for q in PLATFORM_CHANNEL_MAP[plat_key]['tr_queries']]
    
    queries_tr.append(f'"{title}" türkçe altyazılı fragman')
    queries_tr.append(f'"{title}" resmi fragmanı')
    queries_tr.append(f'"{title}" fragman')

    for q in queries_tr:
        candidates = search_yt(q)
        for c in candidates:
            vt = c['title'].lower()
            ch = c['channel'].lower()
            
            # Süre kontrolü (20 sn - 420 sn arası)
            if c['duration'] and (c['duration'] < 20 or c['duration'] > 420):
                continue
            
            # Spam / Fanmade / Sonraki Sezonlar engelleme
            if any(b in vt or b in ch for b in BAD_KEYWORDS):
                continue

            # Başlık uyumu kontrolü (Spinoff engelleme)
            if not is_title_matched(title, orig_title, c['title']):
                continue
            
            # Türkçe doğrulama (Başlıkta veya Kanalda Türkçe ibare bulunmalı)
            if any(t in vt or t in ch for t in TR_MARKS):
                tr_url = f"https://www.youtube.com/watch?v={c['id']}"
                tr_title_found = f"{c['title']} [{c['channel']}]"
                break
        if tr_url:
            break

    # 2. 🌐 ORİJİNAL / İNGİLİZCE FRAGMAN ARAMASI
    orig_url = ""
    orig_title_found = ""
    queries_orig = []
    
    if plat_key and plat_key in PLATFORM_CHANNEL_MAP:
        queries_orig = [q.format(title=title, orig=orig_title) for q in PLATFORM_CHANNEL_MAP[plat_key]['global_queries']]
    
    queries_orig.append(f'"{orig_title}" official trailer')
    queries_orig.append(f'"{orig_title}" trailer')

    for q in queries_orig:
        candidates = search_yt(q)
        for c in candidates:
            vt = c['title'].lower()
            ch = c['channel'].lower()
            
            if c['duration'] and (c['duration'] < 20 or c['duration'] > 420):
                continue
            if any(b in vt or b in ch for b in BAD_KEYWORDS):
                continue
            if not is_title_matched(title, orig_title, c['title']):
                continue
            
            if 'trailer' in vt or 'teaser' in vt or 'official' in vt or 'first look' in vt:
                orig_url = f"https://www.youtube.com/watch?v={c['id']}"
                orig_title_found = f"{c['title']} [{c['channel']}]"
                break
        if orig_url:
            break

    return tr_url, orig_url, tr_title_found, orig_title_found


def main(limit=None, force=False):
    print("==========================================================================")
    print("🎬 AKILLI DIZI FRAGMAN TARAMA BAŞLATILDI (Resmi Kanal & Türkçe Altyazı)")
    print("==========================================================================")
    
    # 1. DB Dosyalarındaki Dizileri Al
    target_dbs = []
    for db in DB_FILES:
        if os.path.exists(db):
            target_dbs.append(db)

    if not target_dbs:
        print("❌ Veritabanı dosyası bulunamadı!")
        return

    primary_db = target_dbs[0]
    conn = sqlite3.connect(primary_db)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Kolonlar yoksa ekle
    c.execute("PRAGMA table_info(diziler)")
    existing_cols = [x[1] for x in c.fetchall()]
    if 'trailer_tr_url' not in existing_cols:
        c.execute("ALTER TABLE diziler ADD COLUMN trailer_tr_url TEXT")
    if 'trailer_original_url' not in existing_cols:
        c.execute("ALTER TABLE diziler ADD COLUMN trailer_original_url TEXT")
    conn.commit()

    c.execute("""
        SELECT id, isim, platformlar, trailer_tr_url, trailer_original_url 
        FROM diziler 
        ORDER BY oy_sayisi DESC, puan_ortalamasi DESC
    """)
    all_rows = c.fetchall()

    if not force:
        # ⏩ KALDIĞI YERDEN DEVAM ET: Daha önceden fragmanı bulunmuş dizileri atla
        series_rows = []
        skipped_count = 0
        for r in all_rows:
            tr = r['trailer_tr_url'] or ''
            orig = r['trailer_original_url'] or ''
            if ('youtube.com' in tr or 'youtu.be' in tr) or ('youtube.com' in orig or 'youtu.be' in orig):
                skipped_count += 1
                continue
            series_rows.append(r)
        if skipped_count > 0:
            print(f"⏩ {skipped_count} dizi daha önceden taranıp kayıt edildiği için ATLANDI.")
    else:
        series_rows = all_rows

    if limit and limit > 0:
        series_rows = series_rows[:limit]

    total = len(series_rows)
    if total == 0:
        print("🎉 Tüm dizilerin fragmanları zaten taranmış ve kayıt edilmiş! İşlem gerektirmiyor.")
        return

    print(f"📋 İşlenecek Kalan Dizi Sayısı: {total}")
    print("-" * 72)

    updated_count = 0
    t0 = time.time()

    for idx, r in enumerate(series_rows, 1):
        sid = r['id']
        title = r['isim']
        platform_str = r['platformlar']

        print(f"[{idx}/{total}] 📺 {title} ({platform_str or 'Bilinmiyor'})...", end=" ", flush=True)

        tr_url, orig_url, tr_info, orig_info = find_dizi_trailers(title, title, platform_str)

        # Tüm ilgili DB dosyalarını güncelle
        for db in target_dbs:
            try:
                db_conn = sqlite3.connect(db)
                db_c = db_conn.cursor()
                # Kolonlar varsa güncelle
                db_c.execute("PRAGMA table_info(diziler)")
                cols = [x[1] for x in db_c.fetchall()]
                if 'trailer_tr_url' in cols and 'trailer_original_url' in cols:
                    db_c.execute("""
                        UPDATE diziler 
                        SET trailer_tr_url = ?, trailer_original_url = ?
                        WHERE id = ?
                    """, (tr_url, orig_url, sid))
                    db_conn.commit()
                db_conn.close()
            except Exception as e:
                pass

        status_str = []
        if tr_url: status_str.append("🇹🇷 TR")
        if orig_url: status_str.append("🌐 ORIG")
        
        print(" | ".join(status_str) if status_str else "❌ BULUNAMADI")
        updated_count += 1

        # Her 20 dizide bir otomatik export ve ara bilgi
        if idx % 20 == 0:
            print(f"💾 [{idx}/{total}] Ara kayıt yapılıyor ve site verisi güncelleniyor...")
            try:
                import export_data_store
                export_data_store.main()
            except Exception as e:
                print(f"⚠️ Export uyarısı: {e}")

        time.sleep(0.4)

    conn.close()

    print("=" * 72)
    print(f"✅ Dizi Fragman Taraması Tamamlandı! ({round(time.time() - t0, 1)} saniye)")
    
    # Otomatik son export
    try:
        import export_data_store
        export_data_store.main()
        print("🎉 data_store.js site verisi başarıyla güncellendi!")
    except Exception as e:
        print(f"⚠️ Export uyarısı: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="Zaten taranmış dizileri tekrar tara")
    args = parser.parse_args()
    main(limit=args.limit, force=args.force)
