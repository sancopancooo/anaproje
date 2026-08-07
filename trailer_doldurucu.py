import os
import sys
import json
import time
import re
import urllib.parse
from dotenv import load_dotenv

# Terminal çıktı kodlaması
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# API Key ve Groq Bağlantısı
load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY") or ""

try:
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=API_KEY
    )
except Exception as e:
    client = None
    print(f"⚠️ OpenAI/Groq kütüphanesi başlatılamadı: {e}")

# YEDEK MODEL ZİNCİRİ (Quota limitine takılınca sırayla geçer)
GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
    "mixtral-8x7b-32768"
]

MOVIES_FILE = "movies_dataset.json"

BAD_TRAILER_KEYWORDS = [
    'concept', 'fan made', 'fanmade', 'fan-made', 'edit', 'reaction', 
    'gameplay', 'spoof', 'parody', 'concept trailer', 'idea trailer', 
    'smasher', 'screen culture', 'kh studio', 'fan trailer', 'fan teaser',
    'konsept', 'hayran yapımı', 'fan yapımı', 'tepki', 'reaksiyon',
    'inceleme', 'oynanış', 'montaj', 'parodi', 'kurgu', 
    'seslendirme denemesi', 'fan yapim', 'oyun videosu', 'oyun fragmanı', 'oyun içi',
    # FULL MOVIE & TV SHOW EPISODE SPAM KEYWORDS:
    'full film', 'tek parça', 'tam film', 'full izle', 'film izlesene', 
    'film klip izle', 'film izle 1080p', 'türkçe dublaj film', '1080p hd', 'türkçe dublaj izle',
    'bölüm', 'sezon', 'dizi izle', 'bölüm fragmanı', 'sezon fragmanı'
]

TR_INDICATORS = [
    'türkçe', 'turkce', 'altyazı', 'altyazılı', 'dublaj', 'dublajlı', 
    'box office türkiye', 'netflix türkiye', 'warner bros. türkiye', 'disney türkiye', 
    'uip türkiye', 'tme films', 'filmartı', 'bir film', 'cj enm'
]

TRAILER_REQUIRED_WORDS = ['fragman', 'fragmanı', 'trailer', 'teaser', 'tanıtım']
STOP_WORDS = {
    'the', 'a', 'an', 'of', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 've', 'ile', 'bir', 'bu',
    'el', 'la', 'los', 'las', 'le', 'les', 'der', 'die', 'das', 'un', 'une', 'uno', 'una'
}

def parse_duration_to_seconds(len_str):
    if not len_str:
        return 0
    parts = len_str.split(':')
    try:
        if len(parts) == 3:
            return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0])*60 + int(parts[1])
    except Exception:
        pass
    return 0

def check_title_words_match(movie_title, video_title, original_title=None):
    v_title_lower = video_title.lower()
    m_title_lower = movie_title.lower()
    orig_lower = original_title.lower() if original_title else ""
    
    # 1. Eğer original_title Türkçe başlıktan farklıysa ve video başlığında tam geçiyorsa
    if orig_lower and len(orig_lower) > 2 and re.search(r'\b' + re.escape(orig_lower) + r'\b', v_title_lower):
        return True

    # Tüm kelimeleri al (stop-words çıkarmadan önce)
    all_raw_words = [w.lower() for w in re.findall(r'[a-zA-Z0-9çğıöşüÇĞİÖŞÜ]+', movie_title) if len(w) > 1]
    
    # Eğer başlık 2 kelime veya daha azsa (örn. "Bir Gün"):
    if len(all_raw_words) <= 2 and len(all_raw_words) > 0:
        # Eğer orijinal İngilizce adı verildiyse ve videoda o ad YOKSA reddet
        if orig_lower and len(orig_lower) > 2 and not re.search(r'\b' + re.escape(orig_lower) + r'\b', v_title_lower):
            return False
            
        words = all_raw_words
        matches = sum(1 for w in words if re.search(r'\b' + re.escape(w) + r'\b', v_title_lower))
        if matches < len(words):
            return False
    else:
        words = [w for w in all_raw_words if w not in STOP_WORDS]
        if not words and original_title:
            words = [w.lower() for w in re.findall(r'[a-zA-Z0-9çğıöşüÇĞİÖŞÜ]+', original_title) if len(w) > 1]
        if not words:
            return False
            
        matches = sum(1 for w in words if re.search(r'\b' + re.escape(w) + r'\b', v_title_lower))
        if (matches / len(words)) < 0.4:
            return False

    major_franchises = ['örümcek adam', 'örümcek-adam', 'spiderman', 'spider-man', 'batman', 'superman', 'avengers', 'iron man', 'star wars', 'harry potter']
    for mf in major_franchises:
        if mf in v_title_lower and mf not in m_title_lower:
            return False

    return True

def is_youtube_video_valid(video_id):
    if not video_id or len(video_id) != 11:
        return False
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            return resp.status == 200
    except Exception:
        return False

def search_single_yt_query(query, target_movie_title=None, original_title=None, require_tr=True):
    try:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        req = urllib.request.Request(url, headers=headers)
        html = urllib.request.urlopen(req, timeout=8).read().decode('utf-8')
        
        json_match = re.search(r'ytInitialData\s*=\s*({.*?});</script>', html)
        if json_match:
            data = json.loads(json_match.group(1))
            contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
            for sec in contents:
                item_section = sec.get('itemSectionRenderer', {}).get('contents', [])
                for item in item_section:
                    video_info = item.get('videoRenderer')
                    if video_info:
                        vid_id = video_info.get('videoId')
                        title_runs = video_info.get('title', {}).get('runs', [])
                        title = title_runs[0].get('text', '') if title_runs else ''
                        owner_runs = video_info.get('ownerText', {}).get('runs', [])
                        channel = owner_runs[0].get('text', '') if owner_runs else ''
                        len_text = video_info.get('lengthText', {}).get('simpleText', '')
                        
                        title_lower = title.lower()
                        channel_lower = channel.lower()
                        
                        duration_sec = parse_duration_to_seconds(len_text)
                        
                        # 1. Tam film engeli (Süre 6 dakikayı / 360 sn geçerse ALMA)
                        if duration_sec > 360:
                            continue
                            
                        # 2. Başlıkta en az bir fragman kelimesi zorunluluğu
                        if not any(tw in title_lower for tw in TRAILER_REQUIRED_WORDS):
                            continue
                            
                        # 3. Yanıltıcı / Kötü / Dizi Bölüm kelimeleri engeli
                        is_bad = any(b in title_lower for b in BAD_TRAILER_KEYWORDS) or any(b in channel_lower for b in BAD_TRAILER_KEYWORDS)
                        if is_bad:
                            continue
                            
                        # 4. Türkçe İbare Kontrolü (require_tr == True ise)
                        has_tr = any(tr in title_lower for tr in TR_INDICATORS) or any(tr in channel_lower for tr in TR_INDICATORS)
                        if require_tr and not has_tr:
                            continue
                            
                        # 5. Hedef film adı ile video başlığı kelime uyumu zorunluluğu
                        if target_movie_title and not check_title_words_match(target_movie_title, title, original_title=original_title):
                            continue
                        
                        if vid_id and len(vid_id) == 11 and is_youtube_video_valid(vid_id):
                            return f"https://www.youtube.com/watch?v={vid_id}"
    except Exception:
        pass
    return None

def fetch_direct_yt_video_id(movie_title, original_title=None, release_year=None, platforms=None):
    year_str = f" {release_year}" if release_year else ""
    
    # --- 1. AŞAMA: TÜRKÇE ALTYAZILI / DUBLAJLI ARAMA (require_tr=True) ---
    tr_queries = []
    if platforms and isinstance(platforms, list):
        for p in platforms:
            p_lower = str(p).lower()
            if "netflix" in p_lower: tr_queries.append(f"{movie_title}{year_str} Netflix Türkiye Türkçe Fragman")
            elif "prime" in p_lower or "amazon" in p_lower: tr_queries.append(f"{movie_title}{year_str} Prime Video Türkiye Türkçe Fragman")
            elif "disney" in p_lower: tr_queries.append(f"{movie_title}{year_str} Disney+ Türkiye Türkçe Fragman")
            elif "blutv" in p_lower: tr_queries.append(f"{movie_title}{year_str} BluTV Fragman")
            elif "tabii" in p_lower: tr_queries.append(f"{movie_title}{year_str} tabii Fragman")
            elif "gain" in p_lower: tr_queries.append(f"{movie_title}{year_str} GAİN Fragman")

    tr_queries.extend([
        f"{movie_title}{year_str} filmi Türkçe Altyazılı Fragman",
        f"{movie_title}{year_str} filmi Türkçe Dublaj Fragman",
        f"{movie_title} Türkçe Altyazılı Fragman",
        f"{movie_title} Türkçe Dublaj Fragman",
        f"{movie_title}{year_str} filmi Türkçe fragmanı",
        f"{movie_title} resmi fragman"
    ])
    
    if original_title and original_title.lower() != movie_title.lower():
        tr_queries.append(f"{original_title}{year_str} movie Türkçe Altyazılı Fragman")

    for q in tr_queries:
        url = search_single_yt_query(q, target_movie_title=movie_title, original_title=original_title, require_tr=True)
        if url:
            return url, "tr"

    # --- 2. AŞAMA: ORİJİNAL RESMİ FRAGMAN FALLBACK (require_tr=False) ---
    search_title = original_title if original_title else movie_title
    orig_queries = [
        f"{search_title}{year_str} Official Trailer",
        f"{search_title} Official Teaser",
        f"{search_title} Movie Trailer"
    ]
    for q in orig_queries:
        url = search_single_yt_query(q, target_movie_title=search_title, original_title=original_title, require_tr=False)
        if url:
            return url, "original"

    return None, "none"

def ask_groq_trailer(movie_title, release_year=None, original_title=None, platforms=None):
    prompt = f"""Sanat/Sinema Veritabanı Uzmanısın.
Aşağıdaki film için varsa TÜRKÇE ALTYAZILI veya TÜRKÇE DUBLAJLI resmi YouTube fragman URL'sini veya 11 haneli YouTube Video ID'sini ver.

Film Adı: {movie_title}
Orijinal Adı: {original_title if original_title else movie_title}
Yayın Yılı: {release_year if release_year else "Bilinmiyor"}

Eğer kesin ve doğru YouTube video ID'sini bilmiyorsan "youtube_video_id": null ver.
Sadece aşağıdaki JSON formatında yanıt ver (başka hiçbir açıklama yazma):
{{
  "youtube_video_id": null
}}
"""

    for model in GROQ_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Sen bir Türkçe fragman veritabanı asistanısın. Sadece geçerli JSON yanıt verirsin."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            data = json.loads(content)
            
            video_id = data.get("youtube_video_id")
            trailer_url = data.get("trailer_url")

            dummy_ids = ["null", "none", "dqw4w9wgxcq", "ab12cd34ef5", "video_id", "video_id_or_null"]
            
            if video_id and str(video_id).lower() not in dummy_ids and len(str(video_id)) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', str(video_id)):
                if is_youtube_video_valid(video_id):
                    return f"https://www.youtube.com/watch?v={video_id}", "tr"
            elif trailer_url and "youtube.com/watch?v=" in trailer_url and not any(d in trailer_url.lower() for d in dummy_ids):
                v_id = trailer_url.split("watch?v=")[1].split("&")[0]
                if is_youtube_video_valid(v_id):
                    return trailer_url, "tr"
        except Exception as e:
            err_msg = str(e)
            if "rate_limit" in err_msg.lower() or "429" in err_msg:
                print(f" (⚠️ {model} limiti doldu, sonraki modele geçiliyor...)", end="")
                continue
            else:
                break

    # 2 Aşamalı Hibrit Fragman Motoru Fallback
    return fetch_direct_yt_video_id(movie_title, original_title, release_year, platforms)

def process_missing_trailers(limit=None):
    print("="*70)
    print("🎬 MATRIX PLATFORMU — ADIM 4: FİLM YOUTUBE FRAGMAN TAMAMLAYICI MOTOR")
    print("="*70)

    if not os.path.exists(MOVIES_FILE):
        print(f"❌ {MOVIES_FILE} bulunamadı!")
        return

    with open(MOVIES_FILE, "r", encoding="utf-8") as f:
        movies = json.load(f)

    total_movies = len(movies)

    def is_missing(movie):
        url = movie.get("trailer_url")
        # Henüz hiç taranmamış (boş/None objesi) filmleri eksik kabul et ('None' olanlar zaten taranmıştır, atla)
        if url is None or url == "" or url == "#" or url == "null":
            return True
        if "results?search_query=" in url:
            return True
        return False

    missing_list = [m for m in movies if is_missing(m)]
    already_done = total_movies - len(missing_list)

    print(f"📊 Toplam Film Sayısı              : {total_movies:,}")
    print(f"✅ Fragmanı Zaten Var Olanlar       : {already_done:,}")
    print(f"❌ Fragmanı Eksik Olan Film Sayısı : {len(missing_list):,}")
    print("="*70)

    if not missing_list:
        print("🎉 Tüm filmlerin YouTube fragman bilgisi zaten %100 tamamlandı!")
        return

    to_process = missing_list[:limit] if limit else missing_list
    print(f"🚀 {len(to_process):,} adet filmin YouTube fragman linki dolduruluyor...\n")

    start_time = time.time()
    updated_count = 0

    for idx, movie in enumerate(to_process, 1):
        title = movie.get("title", "Bilinmeyen Film")
        orig_title = movie.get("original_title", title)
        year = movie.get("year") or (movie.get("release_date", "")[:4] if movie.get("release_date") else None)

        print(f"[{idx}/{len(to_process)}] 🎬 '{title}' Türkçe fragmanı aranıyor...", end="", flush=True)

        platforms = movie.get("streaming_platforms") or movie.get("platforms")
        new_trailer_url, trailer_type = ask_groq_trailer(title, year, orig_title, platforms)
        if new_trailer_url:
            movie["trailer_url"] = new_trailer_url
            movie["trailer_type"] = trailer_type
            updated_count += 1
            badge = "🇹🇷 [TR]" if trailer_type == "tr" else "🌐 [ORİJİNAL]"
            print(f" ✅ OK {badge} ➔ {new_trailer_url}")
        else:
            movie["trailer_url"] = "None"
            movie["trailer_type"] = "none"
            print(" ⚠️ Fragman Bulunamadı (Yok)")

        # Her 10 filmde bir veya sonunda dataset'i kaydet
        if idx % 10 == 0 or idx == len(to_process):
            with open(MOVIES_FILE, "w", encoding="utf-8") as f:
                json.dump(movies, f, ensure_ascii=False, indent=2)
            print(f"   💾 [Veritabanı Güncellendi: {idx}/{len(to_process)} film diske kaydedildi]")

        time.sleep(0.3)

    # Son kayıt
    with open(MOVIES_FILE, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

    elapsed = round(time.time() - start_time, 1)
    print("\n" + "="*70)
    print(f"🎉 İŞLEM TAMAMLANDI! ({elapsed} saniye)")
    print(f"✅ Tamamlanan Film Sayısı     : {updated_count:,}")
    print(f"💾 {MOVIES_FILE} başarıyla güncellendi.")

    # Otomatik web veritabanı senkronizasyonu
    print("\n🔄 Web veritabanı (data_store.js) güncelleniyor...")
    try:
        import export_data_store
        export_data_store.main()
        print("✅ data_store.js senkronize edildi!")
    except Exception as e:
        print(f"⚠️ data_store.js güncellenirken hata: {e}")
    print("="*70)

if __name__ == "__main__":
    limit_val = None
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith("--limit="):
                limit_val = int(arg.split("=")[1])
            elif arg == "--limit" and len(sys.argv) > sys.argv.index(arg) + 1:
                limit_val = int(sys.argv[sys.argv.index(arg) + 1])
    process_missing_trailers(limit=limit_val)
