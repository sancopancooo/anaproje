# -*- coding: utf-8 -*-
"""
==============================================================================
🎬 AKILLI DİZİ FRAGMAN DENETLEYİCİ VE DÜZELTİCİ (v1.0)
==============================================================================
Hedef:
1. Mevcut veritabanındaki 2.340 diziyi (öncelikle platformu olanları) denetlemek.
2. La Casa de Papel, Squid Game gibi DOĞRU VE ÇALIŞAN 1. sezon fragmanlarını KORUMAK.
3. Sahne klipsi (Wicked Game), Türkçe dublaj, 4. Sezon, spinoff veya performans içeren
   HATALI videoları tespit edip TEMİZLEMEK.
4. Eğer varsa Türkçe Altyazılı 1. Sezon fragmanını, yoksa Orijinal 1. Sezon fragmanını eklemek.
5. Hiçbiri yoksa sahte/rastgele video koymayıp 'BULUNAMADI' yazmak. (Doğruluk Öncelikli!)
==============================================================================
"""

import sqlite3
import json
import re
import urllib.request
import urllib.parse
import sys
import os
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = "katalog.db"
TABLE_NAME = "diziler"

# ❌ YASAKLI KELİMELER (Sahne, Şarkı, Performans, Dublaj, Spinoff ve Sonraki Sezonlar)
STRICT_BAD = [
    # Sahne, Klip, Şarkı, Röportaj, Kamera Arkası, OVA, Bölüm Fragmanları
    'performansı', 'performans', 'sahne', 'sahnesi', 'şarkı', 'sarkisi', 'clip', 'scene',
    'this season on', 'behind the scenes', 'kamera arkası', 'röportaj', 'interview', 'soundtrack',
    'muzik', 'müzik', 'lyric', 'lyrics', 'blooper', 'bloopers', 'bölüm', 'episode',
    'ova', 'ova 1', 'ova 2', 'sıralaması', 'sıralama', 'güç sıralaması',
    '1x', '2x', '3x', '4x', '5x', '6x', '7x', '8x', '9x', '10x',
    's01', 's02', 's03', 's04', 's05', 's06', 's07', 's08', 's09', 's10',
    'ep 1', 'ep 2', 'ep 3', 'ep 4', 'ep 5', 'ep 6', 'ep 7', 'ep 8', 'ep 9', 'ep 10',
    # Spinofflar, Revival/Reboot ve Devam Dizileri/Filmler
    'spinoff', 'spin-off', 'film', 'filmi', 'movie', 'el camino', 'ölümsüz adam',
    'new blood', 'born again', 'resurrection', 'reboot', 'revival', 'sequel', 'prequel',
    # Yanlış Yapım / Karakter Karışımları
    'mortal kombat', 'sub zero', 'gameplay', 'gaming', 'walkthrough',
    # Sonraki Sezonlar & Final Fragmanları
    '2. sezon', '3. sezon', '4. sezon', '5. sezon', '6. sezon', '7. sezon', '8. sezon', '9. sezon', '10. sezon', '11. sezon',
    '2.sezon', '3.sezon', '4.sezon', '5.sezon', '6.sezon', '7.sezon', '8.sezon', '9.sezon', '10.sezon', '11.sezon',
    'season 2', 'season 3', 'season 4', 'season 5', 'season 6', 'season 7', 'season 8', 'season 9', 'season 10', 'season 11',
    'final trailer', 'official final trailer', 'final season', 'final sezon', 'series finale', 'final fragmanı', 'final fragman',
    '2. kısım', '3. kısım', '4. kısım', '5. kısım', 'part 2', 'part 3', 'part 4', 'part 5', 'volume 2', 'vol 2', 'vol 3',
    # Dizi Türkçe Dublaj Engeli & Yabancı Diller (Italia, Espana vb.)
    'dublaj', 'türkçe dublaj', 'tr dublaj', 'italia', 'espana', 'france', 'deutschland'
]

# ✅ FRAGMAN İŞARETLERİ (En az biri bulunmalı)
MUST_HAVE_TRAILER_WORD = [
    'fragman', 'fragmanı', 'tanıtım', 'tanıtımı', 'trailer', 'teaser', 'preview'
]

# 🏢 RESMİ PLATFORM KANALLARI MAPI
PLATFORM_CHANNELS = {
    "netflix": ["Netflix Türkiye", "Netflix"],
    "amazon": ["Prime Video Türkiye", "Amazon Prime Video"],
    "prime": ["Prime Video Türkiye", "Amazon Prime Video"],
    "disney": ["Disney+ Türkiye", "Disney Plus TR", "Disney Plus"],
    "hbo": ["HBO Max Türkiye", "Max Türkiye", "HBO"],
    "max": ["HBO Max Türkiye", "Max Türkiye", "HBO"],
    "blutv": ["BluTV"],
    "gain": ["GAİN"],
    "tod": ["TOD Türkiye", "beIN CONNECT"],
    "tv+": ["TV+"]
}


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'[\(\[\{].*?[\)\]\}]', '', str(text))
    return text.strip()


def extract_yt_video_title_and_channel(url):
    """YouTube URL'sinden video başlığını ve kanal adını çeker (Denetleme için)"""
    if not url or "youtube.com" not in url and "youtu.be" not in url:
        return None, None
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8'
        })
        html = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', errors='ignore')
        
        m_title = re.search(r'<title>(.*?)</title>', html)
        title = m_title.group(1).replace(' - YouTube', '').strip() if m_title else ""
        
        return title, ""
    except Exception:
        return None, None


def validate_trailer_title(title, show_title, is_tr_check=False, show_year=None):
    """Bir video başlığının GERÇEK 1. SEZON DİZİ FRAGMANI olup olmadığını sıfır hata ile denetler"""
    if not title:
        return False, "Başlık okunamadı"
        
    t_low = title.lower()
    s_low = show_title.lower()
    
    # 1. Başlıkta dizinin kritik kelimelerinin ÇOĞU geçmeli (any → majority)
    #    "How I Met Your Mother" vs "Father" gibi yakın isimleri ayırır
    clean_s = re.sub(r'[^\w\s]', '', s_low)
    main_words = [w for w in clean_s.split() if len(w) > 2]
    if main_words:
        hits = sum(1 for w in main_words if w in t_low)
        need = max(2, (len(main_words) + 1) // 2) if len(main_words) >= 2 else 1
        if hits < need:
            return False, f"Dizi adı ({show_title}) başlıkta yeterince geçmiyor ({hits}/{len(main_words)})"

        # Discriminating son kelime: Mother≠Father, Korra≠Airbender vb.
        last = main_words[-1]
        if len(last) > 3 and last not in t_low:
            # Son kelime yoksa ama diğerleri var → muhtemel spinoff/remake
            sibling_swaps = {
                'mother': 'father', 'father': 'mother',
                'korra': 'airbender', 'airbender': 'korra',
            }
            rival = sibling_swaps.get(last)
            if rival and rival in t_low:
                return False, f"Yanlış yapım (spinoff/remake): '{rival}'"
            if hits < len(main_words):
                return False, f"Kritik kelime eksik: '{last}'"
        
    # Yanlış dizi / remake / spinoff karışmasını önleme
    if "walking dead" in s_low and "dead to me" in t_low:
        return False, "Yanlış dizi (Dead to Me)"
    if "good doctor" in s_low and ("japan" in t_low or "japonya" in t_low):
        return False, "Japonya versiyonu"
    if "scorpion" in s_low and ("mortal kombat" in t_low or "mk" in t_low):
        return False, "Mortal Kombat karakteri"
    if "daredevil" in s_low and "born again" in t_low:
        return False, "Born Again devam dizisi"
    if "dexter" in s_low and "new blood" in t_low:
        return False, "New Blood devam dizisi"
    if "met your mother" in s_low and "father" in t_low:
        return False, "How I Met Your Father spinoff"
    if "met your father" in s_low and "mother" in t_low and "father" not in s_low:
        return False, "How I Met Your Mother (yanlış)"
    # Avatar: 2005 animasyon ≠ 2024 Netflix live-action
    if ("son havabükücü" in s_low or "last airbender" in s_low) and "animasyon" not in t_low:
        if any(x in t_low for x in ("netflix", "live action", "live-action", "2024", "2025", "2026")):
            # Animasyon orijinali için Netflix remake fragmanı yasak
            if show_year and str(show_year).startswith("200"):
                return False, "Netflix live-action remake fragmanı (animasyon dizi değil)"
        
    # 2. Yasaklı kelimeler (Sahne, Şarkı, Dublaj, 4. Sezon, 1x04 vb.) içeriyor mu?
    for bad in STRICT_BAD:
        if bad in t_low:
            return False, f"Yasaklı içerik tespit edildi: '{bad}'"
            
    # 3. Fragman/Trailer kelimesi içeriyor mu?
    if not any(tw in t_low for tw in MUST_HAVE_TRAILER_WORD):
        return False, "Fragman/Trailer tanımı içermiyor"
        
    # 4. Türkçe Kontrolü (TR slotu için Türkçe işaret şart)
    if is_tr_check:
        tr_indicators = ['türkçe', 'turkce', 'altyazı', 'altyazılı', 'altyazili', 'fragman', 'tanıtım']
        if not any(tw in t_low for tw in tr_indicators):
            return False, "Türkçe/Altyazı tanımı içermiyor"
        
    return True, "✅ Geçerli 1. Sezon Fragmanı"


def search_youtube_video(query):
    """YouTube üzerinde arama yapıp en uygun geçerli video bilgilerini döner"""
    try:
        search_url = 'https://www.youtube.com/results?search_query=' + urllib.parse.quote(query)
        req = urllib.request.Request(search_url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8'
        })
        html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
        
        m = re.search(r'ytInitialData\s*=\s*(\{.*?\});</script>', html)
        if not m:
            return None
            
        data = json.loads(m.group(1))
        sections = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
        
        candidates = []
        for sec in sections:
            for item in sec.get('itemSectionRenderer', {}).get('contents', []):
                vr = item.get('videoRenderer')
                if not vr:
                    continue
                videoId = vr.get('videoId')
                title = vr.get('title', {}).get('runs', [])[0].get('text', '')
                owner = vr.get('ownerText', {}).get('runs', [])[0].get('text', '') if vr.get('ownerText') else ''
                
                if videoId and title:
                    candidates.append({
                        "url": f"https://www.youtube.com/watch?v={videoId}",
                        "title": title,
                        "channel": owner
                    })
                    if len(candidates) >= 5:
                        break
        return candidates
    except Exception as e:
        return []


def get_official_channels_for_platform(platform_str):
    """Platform ismine göre öncelikli YouTube resmi kanallarını döner"""
    if not platform_str:
        return []
    plat_low = platform_str.lower()
    channels = []
    for key, ch_list in PLATFORM_CHANNELS.items():
        if key in plat_low:
            for ch in ch_list:
                if ch not in channels:
                    channels.append(ch)
    return channels


def audit_and_fix_series(series_id, title, orig_title, platform_str, curr_tr_url, curr_orig_url, show_year=None):
    """
    Tek bir diziyi sıfır hatayla denetler ve düzeltir:
    1. Mevcut TR linki geçerli mi? (Geçerliyse KORU)
    2. Geçersizse -> Resmi Platform Kanalında Türkçe Altyazılı Fragman ara.
    3. Yoksa -> Orijinal 1. Sezon Resmi Fragman ara.
    4. Hiçbiri yoksa -> 'BULUNAMADI' olarak işaretle.
    """
    print(f"\n📺 Denetleniyor: {title} (Orijinal: {orig_title or 'Yok'}) [{platform_str or 'Diğer'}]")
    
    tr_url = curr_tr_url
    orig_url = curr_orig_url
    
    tr_is_valid = False
    orig_is_valid = False
    
    # --- 1. MEVCUT TR LİNKİ DENETİMİ ---
    if curr_tr_url and "youtube.com" in curr_tr_url:
        t_title, _ = extract_yt_video_title_and_channel(curr_tr_url)
        valid, reason = validate_trailer_title(t_title, title, is_tr_check=True, show_year=show_year)
        if valid:
            print(f"   🟢 Mevcut TR Fragman Kaliteli & Geçerli (KORUNDU): {t_title}")
            tr_is_valid = True
        else:
            print(f"   🔴 Mevcut TR Fragman Hatalı/Gerekarsiz: {t_title} -> ({reason})")
            tr_url = "TÜRKÇE_FRAGMAN_BULUNAMADI"
    else:
        tr_url = "TÜRKÇE_FRAGMAN_BULUNAMADI"
        
    # --- 2. MEVCUT ORİJİNAL LİNKİ DENETİMİ ---
    if curr_orig_url and "youtube.com" in curr_orig_url:
        o_title, _ = extract_yt_video_title_and_channel(curr_orig_url)
        valid, reason = validate_trailer_title(o_title, orig_title or title, is_tr_check=False, show_year=show_year)
        if valid:
            print(f"   🟢 Mevcut Orijinal Fragman Kaliteli & Geçerli (KORUNDU): {o_title}")
            orig_is_valid = True
        else:
            print(f"   🔴 Mevcut Orijinal Fragman Hatalı: {o_title} -> ({reason})")
            orig_url = "ORİJİNAL_FRAGMAN_BULUNAMADI"
    else:
        orig_url = "ORİJİNAL_FRAGMAN_BULUNAMADI"
        
    # --- 3. EĞER TR FRAGMAN GEÇERSİZSE YENİDEN ARA ---
    if not tr_is_valid:
        print("   🔍 Türkçe Altyazılı 1. Sezon Fragmanı Aranıyor...")
        target_channels = get_official_channels_for_platform(platform_str)
        found_new_tr = False
        
        # A. Resmi Kanallarda Arama
        for ch in target_channels:
            query = f'"{ch}" "{title}" fragman'
            candidates = search_youtube_video(query)
            for cand in candidates:
                valid, reason = validate_trailer_title(cand["title"], title, is_tr_check=True, show_year=show_year)
                if valid:
                    tr_url = cand["url"]
                    print(f"   ✨ YENİ TR FRAGMAN BULUNDU ({ch}): {cand['title']}")
                    found_new_tr = True
                    tr_is_valid = True
                    break
            if found_new_tr:
                break
                
        # B. Genel Türkçe Altyazı Araması
        if not found_new_tr:
            query = f'"{title}" 1. Sezon Türkçe altyazılı fragman'
            candidates = search_youtube_video(query)
            for cand in candidates:
                valid, reason = validate_trailer_title(cand["title"], title, is_tr_check=True, show_year=show_year)
                if valid:
                    tr_url = cand["url"]
                    print(f"   ✨ YENİ TR ALTYAZILI FRAGMAN BULUNDU: {cand['title']}")
                    found_new_tr = True
                    tr_is_valid = True
                    break

    # --- 4. EĞER ORİJİNAL FRAGMAN GEÇERSİZSE YENİDEN ARA ---
    if not orig_is_valid:
        search_name = orig_title or title
        print(f"   🔍 Orijinal 1. Sezon Fragmanı Aranıyor ({search_name})...")
        query = f'"{search_name}" Season 1 Official Trailer'
        candidates = search_youtube_video(query)
        for cand in candidates:
            valid, reason = validate_trailer_title(cand["title"], search_name, show_year=show_year)
            if valid:
                orig_url = cand["url"]
                print(f"   ✨ YENİ ORİJİNAL FRAGMAN BULUNDU: {cand['title']}")
                orig_is_valid = True
                break

    if not tr_is_valid and not orig_is_valid:
        print("   ⚠️ Bu dizi için kriterlere uyan 1. Sezon fragmanı bulunamadı. (Boş bırakıldı - Doğruluk Öncelikli)")

    return tr_url, orig_url


def run_audit(only_platforms=True, force_all=False, limit=None, tr_only=True):
    print("=" * 80)
    print("🎬 AKILLI DİZİ FRAGMAN DENETLEYİCİ VE DÜZELTİCİ (KALDĞI YERDEN DEVAM MODU)")
    print("=" * 80)

    if not os.path.exists(DB_PATH):
        print(f"❌ Veritabanı bulunamadı: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # _audited kolonu var mı kontrol et, yoksa ekle
    c.execute("PRAGMA table_info(diziler)")
    cols = [r[1] for r in c.fetchall()]
    if "_audited" not in cols:
        c.execute("ALTER TABLE diziler ADD COLUMN _audited INTEGER DEFAULT 0")
        conn.commit()

    if tr_only:
        tr_clause = "trailer_tr_url IS NOT NULL AND TRIM(trailer_tr_url) != '' AND trailer_tr_url != 'TÜRKÇE_FRAGMAN_BULUNAMADI'"
    elif only_platforms:
        tr_clause = "platformlar IS NOT NULL AND TRIM(platformlar) != '' AND platformlar != 'Diğer Platformlar'"
    else:
        tr_clause = "1=1"

    c.execute(f"SELECT COUNT(*) FROM diziler WHERE {tr_clause}")
    total_target = c.fetchone()[0]

    c.execute(f"SELECT COUNT(*) FROM diziler WHERE {tr_clause} AND _audited = 1")
    already_audited = c.fetchone()[0]

    if force_all:
        audited_where = ""
    else:
        audited_where = "AND (_audited IS NULL OR _audited = 0)"

    query = f"""
        SELECT id, isim, platformlar, trailer_tr_url, trailer_original_url, cikis_tarihi
        FROM diziler
        WHERE {tr_clause} {audited_where}
        ORDER BY id
    """

    c.execute(query)
    rows = c.fetchall()

    if limit:
        rows = rows[:limit]

    print(f"📋 Toplam Hedef Türkçe Fragmanlı Dizi : {total_target}")
    if not force_all and already_audited > 0:
        print(f"⏩ Daha Önce Denetlendiği İçin ATLANAN        : {already_audited}")
    print(f"🔍 İşlenecek Kalan Dizi Sayısı                 : {len(rows)}")
    print("-" * 80)

    if len(rows) == 0:
        print("🎉 Harika! Tüm Türkçe fragmanlı diziler denetlendi. İşlenecek dizi kalmadı.")
        conn.close()
        return

    updated_count = 0
    for idx, row in enumerate(rows, 1):
        s_id = row["id"]
        title = clean_text(row["isim"])
        platform = row["platformlar"]
        curr_tr = row["trailer_tr_url"]
        curr_orig = row["trailer_original_url"]
        show_year = (row["cikis_tarihi"] or "")[:4]

        new_tr, new_orig = audit_and_fix_series(
            s_id, title, title, platform, curr_tr, curr_orig, show_year=show_year
        )

        # Her diziyi _audited = 1 olarak işaretle (Bulunsa da bulunmasa da bir daha başa sarmaz)
        c.execute("""
            UPDATE diziler
            SET trailer_tr_url = ?, trailer_original_url = ?, _audited = 1
            WHERE id = ?
        """, (new_tr, new_orig, s_id))
        conn.commit()

        if new_tr != curr_tr or new_orig != curr_orig:
            updated_count += 1

    conn.close()

    print("\n" + "=" * 80)
    print(f"✅ DENETİM TAMAMLANDI! Toplam Değiştirilen/Düzeltilen Dizi Sayısı: {updated_count}")
    print("=" * 80)

    # Otomatik site verisini dışa aktar
    try:
        import export_data_store
        export_data_store.main()
        print("🎉 data_store.js site verisi başarıyla güncellendi!")
    except Exception as e:
        print(f"⚠️ data_store.js aktarımında hata: {e}")


def run_audit_entry(only_platforms=False, force_all=False, limit=None, tr_only=True):
    run_audit(only_platforms=only_platforms, force_all=force_all, limit=limit, tr_only=tr_only)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Akıllı Dizi Fragman Denetleyici (Devam Desteği)")
    parser.add_argument("--force", action="store_true", help="Daha önce denetlenenleri de tekrar tara")
    parser.add_argument("--all", action="store_true", help="Sadece Türkçe olanları değil tüm 2340 diziyi tara")
    parser.add_argument("--limit", type=int, default=None, help="İşlenecek maksimum dizi sayısı")
    args = parser.parse_args()

    run_audit(only_platforms=False, force_all=args.force, limit=args.limit, tr_only=not args.all)

