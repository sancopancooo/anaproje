import os
import sys
import json
import time
import re
import urllib.parse
import urllib.request
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY") or ""

try:
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=API_KEY
    )
except Exception:
    client = None

MOVIES_FILE = "movies_dataset.json"

BAD_TRAILER_KEYWORDS = [
    'concept', 'fan made', 'fanmade', 'fan-made', 'edit', 'reaction', 
    'gameplay', 'spoof', 'parody', 'concept trailer', 'idea trailer', 
    'smasher', 'screen culture', 'kh studio', 'fan trailer', 'fan teaser',
    'konsept', 'hayran yapımı', 'fan yapımı', 'tepki', 'reaksiyon',
    'inceleme', 'oynanış', 'montaj', 'parodi', 'kurgu', 
    'seslendirme denemesi', 'fan yapim', 'oyun videosu', 'oyun fragmanı', 'oyun içi',
    'full film', 'tek parça', 'tam film', 'full izle', 'film izlesene', 
    'film klip izle', 'film izle 1080p', 'türkçe dublaj film', '1080p hd', 'türkçe dublaj izle',
    'bölüm', 'sezon', 'dizi izle', 'bölüm fragmanı', 'sezon fragmanı'
]

TR_INDICATORS = [
    'türkçe', 'turkce', 'altyazı', 'altyazılı', 'dublaj', 'dublajlı', 
    'box office türkiye', 'netflix türkiye', 'warner bros. türkiye', 'disney türkiye', 
    'uip türkiye', 'tme films', 'filmartı', 'bir film', 'cj enm'
]

TRAILER_REQUIRED_WORDS = ['fragman', 'fragmanı', 'trailer', 'teaser', 'tanıtım', 'official']
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
    
    if orig_lower and len(orig_lower) > 2 and re.search(r'\b' + re.escape(orig_lower) + r'\b', v_title_lower):
        return True

    all_raw_words = [w.lower() for w in re.findall(r'[a-zA-Z0-9çğıöşüÇĞİÖŞÜ]+', movie_title) if len(w) > 1]
    
    if len(all_raw_words) <= 2 and len(all_raw_words) > 0:
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
        if (matches / len(words)) < 0.35:
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

def search_single_yt_query(query, target_movie_title=None, original_title=None, require_tr=False):
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
                        
                        if duration_sec > 360:
                            continue
                            
                        if not any(tw in title_lower for tw in TRAILER_REQUIRED_WORDS):
                            continue
                            
                        is_bad = any(b in title_lower for b in BAD_TRAILER_KEYWORDS) or any(b in channel_lower for b in BAD_TRAILER_KEYWORDS)
                        if is_bad:
                            continue
                            
                        has_tr = any(tr in title_lower for tr in TR_INDICATORS) or any(tr in channel_lower for tr in TR_INDICATORS)
                        if require_tr and not has_tr:
                            continue
                            
                        if target_movie_title and not check_title_words_match(target_movie_title, title, original_title=original_title):
                            continue
                        
                        if vid_id and len(vid_id) == 11 and is_youtube_video_valid(vid_id):
                            t_type = "tr" if has_tr else "original"
                            return f"https://www.youtube.com/watch?v={vid_id}", t_type
    except Exception:
        pass
    return None, None

def deep_review_movie(movie):
    title = movie.get("title", "")
    orig_title = movie.get("original_title", title)
    year = movie.get("year") or (movie.get("release_date", "")[:4] if movie.get("release_date") else None)
    year_str = f" {year}" if year else ""
    
    # 1. AŞAMA: ÖNCE SIKI TÜRKÇE FRAGMAN ARAMASI (require_tr=True)
    tr_queries = [
        f"{title}{year_str} filmi Türkçe Altyazılı Fragman",
        f"{title}{year_str} filmi Türkçe Dublaj Fragman",
        f"{title} Türkçe Altyazılı Fragman",
        f"{title} Türkçe Dublaj Fragman",
        f"{title} Türkçe Fragmanı",
        f"{title} Resmi Fragmanı"
    ]
    
    for q in tr_queries:
        url, t_type = search_single_yt_query(q, target_movie_title=title, original_title=orig_title, require_tr=True)
        if url:
            return url, "tr"

    # 2. AŞAMA: ORİJİNAL İNGİLİZCE FRAGMAN FALLBACK (require_tr=False)
    search_title = orig_title if orig_title else title
    orig_queries = [
        f"{search_title}{year_str} Official Trailer",
        f"{search_title} Official Teaser",
        f"{search_title} Movie Trailer"
    ]
    for q in orig_queries:
        url, t_type = search_single_yt_query(q, target_movie_title=search_title, original_title=orig_title, require_tr=False)
        if url:
            return url, "original"

    return None, "none"

def main():
    print("="*75)
    print("🔍 MATRIX PLATFORMU — FRAGMANI BULUNAMAMIŞ (NONE) FİLMLERİ GÖZDEN GEÇİRİCİ")
    print("="*75)

    if not os.path.exists(MOVIES_FILE):
        print(f"❌ {MOVIES_FILE} bulunamadı!")
        return

    with open(MOVIES_FILE, "r", encoding="utf-8") as f:
        movies = json.load(f)

    # SADECE trailer_url == 'None' veya boş olanları süz!
    none_list = [m for m in movies if m.get("trailer_url") == "None" or not m.get("trailer_url")]

    print(f"📊 Toplam 'None' (Fragmansız) Film Sayısı: {len(none_list):,} adet\n")

    if not none_list:
        print("🎉 Gözden geçirilecek boş film kalmadı!")
        return

    recovered_count = 0

    for idx, movie in enumerate(none_list, 1):
        title = movie.get("title", "İsimsiz Film")
        orig_title = movie.get("original_title", title)
        year = movie.get("year") or (movie.get("release_date", "")[:4] if movie.get("release_date") else "")
        
        print(f"[{idx}/{len(none_list)}] 🔍 '{title}' ({year}) yeniden taranıyor...", end="", flush=True)

        url, t_type = deep_review_movie(movie)

        if url:
            movie["trailer_url"] = url
            movie["trailer_type"] = t_type
            recovered_count += 1
            badge = "🇹🇷 [TR]" if t_type == "tr" else "🌐 [ORİJİNAL]"
            print(f"  🎉 BULDUM! {badge} ➔ {url}")
        else:
            print("  ⚠️ Fragman Yine Bulunamadı (Yok)")

        if idx % 10 == 0 or idx == len(none_list):
            with open(MOVIES_FILE, "w", encoding="utf-8") as f:
                json.dump(movies, f, ensure_ascii=False, indent=2)
            print(f"   💾 [Veritabanı Güncellendi: {idx}/{len(none_list)} film diske kaydedildi]")

        time.sleep(0.2)

    # Verileri data_store.js'ye aktar
    try:
        import export_data_store
        export_data_store.main()
    except Exception:
        pass

    print("\n" + "="*75)
    print(f"✨ GÖZDEN GEÇİRME TAMAMLANDI! {recovered_count} Adet Filmin Fragmanı Başarıyla Kurtarıldı!")
    print("="*75)

if __name__ == "__main__":
    main()
