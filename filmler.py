import json
import os
import time
import requests

API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"
OUTPUT_FILE = "movies_dataset.json"
SEEN_FILE = "seen_movie_ids.json"

# Daha önce indirilen verileri yükle
if os.path.exists(OUTPUT_FILE):
  with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
    collected_movies = json.load(f)
else:
  collected_movies = []

if os.path.exists(SEEN_FILE):
  with open(SEEN_FILE, "r", encoding="utf-8") as f:
    seen_movie_ids = set(json.load(f))
else:
  seen_movie_ids = set()

# KRİTİK NOKTA: Toplam hedef 5000 film
CURRENT_COUNT = len(collected_movies)
ADDITIONAL_MOVIES_TARGET = max(0, 5000 - CURRENT_COUNT)  # Eksik kalanı tamamla
TARGET_MOVIE_COUNT = 5000  # Sabit hedef: 5000 film

print(
    f"📥 Mevcut Durum: Veritabanında {CURRENT_COUNT} film var."
    f" Hedeflenen yeni toplam: {TARGET_MOVIE_COUNT} film. Kaldığı yerden"
    " devam ediliyor..."
)


def get_movie_details(movie_id):
  url = f"{BASE_URL}/movie/{movie_id}?api_key={API_KEY}&language=tr-TR&append_to_response=credits,videos,watch/providers,keywords,similar"
  response = requests.get(url)

  if response.status_code == 429:
    print("⚠️ API Limiti aşıldı! 10 saniye bekleniyor...")
    time.sleep(10)
    return get_movie_details(movie_id)

  if response.status_code != 200:
    return None

  data = response.json()

  director = "Bilinmiyor"
  for crew in data.get("credits", {}).get("crew", []):
    if crew.get("job") == "Director":
      director = crew.get("name")
      break

  cast = [
      {"name": actor.get("name"), "character": actor.get("character")}
      for actor in data.get("credits", {}).get("cast", [])[:5]
  ]

  trailer_url = None
  for video in data.get("videos", {}).get("results", []):
    if video.get("site") == "YouTube" and video.get("type") == "Trailer":
      trailer_url = f"https://www.youtube.com/watch?v={video.get('key')}"
      break

  streaming_platforms = [
      p.get("provider_name")
      for p in data.get("watch/providers", {})
      .get("results", {})
      .get("TR", {})
      .get("flatrate", [])
  ]

  keywords = [kw.get("name") for kw in data.get("keywords", {}).get("keywords", [])]
  similar_movie_ids = [
      str(sim.get("id")) for sim in data.get("similar", {}).get("results", [])[:10]
  ]

  return {
      "id": str(data.get("id")),
      "imdb_id": data.get("imdb_id"),
      "title": data.get("title"),
      "original_title": data.get("original_title"),
      "release_date": data.get("release_date"),
      "runtime_minutes": data.get("runtime"),
      "genres": [genre["name"] for genre in data.get("genres", [])],
      "summary": data.get("overview"),
      "director": director,
      "cast": cast,
      "poster_url": (
          f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}"
          if data.get("poster_path")
          else None
      ),
      "trailer_url": trailer_url,
      "streaming_platforms": streaming_platforms,
      "keywords": keywords,
      "similar_movie_ids": similar_movie_ids,
  }


# Strateji 1: popular + top_rated (hızlı)
base_endpoints = ["movie/popular", "movie/top_rated", "movie/now_playing"]

# Strateji 2: Yıl bazlı discover (2000-2025 arası, her yıldan film çek)
discover_years = list(range(2025, 1979, -1))  # 2025'ten 1980'e

# Strateji 3: Tür bazlı discover
genre_ids = [28, 12, 16, 35, 80, 99, 18, 10751, 14, 36, 27, 10749, 878, 53, 10752]

def fetch_page(endpoint, page, extra_params=""):
    url = f"{BASE_URL}/{endpoint}?api_key={API_KEY}&language=tr-TR&page={page}{extra_params}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 429:
            print("  Rate limit - 10s bekleniyor...")
            time.sleep(10)
            return fetch_page(endpoint, page, extra_params)
        if res.status_code == 200:
            return res.json().get("results", [])
    except Exception as e:
        print(f"  Baglanti hatasi: {e}")
    return []

def try_add_movie(item):
    global collected_movies
    m_id = item.get("id")
    if not m_id or m_id in seen_movie_ids:
        return False
    seen_movie_ids.add(m_id)
    detailed = get_movie_details(m_id)
    if detailed and detailed.get("poster_url"):
        collected_movies.append(detailed)
        print(f"  [{len(collected_movies)}/{TARGET_MOVIE_COUNT}] OK {detailed['title']}")
        return True
    return False

# --- STRATEJI 1: popular / top_rated / now_playing ---
print("\n[1] popular/top_rated/now_playing taranıyor...")
for page in range(1, 300):
    if len(collected_movies) >= TARGET_MOVIE_COUNT:
        break
    added_in_page = 0
    for ep in base_endpoints:
        if len(collected_movies) >= TARGET_MOVIE_COUNT:
            break
        results = fetch_page(ep, page)
        if not results:
            continue
        for item in results:
            if len(collected_movies) >= TARGET_MOVIE_COUNT:
                break
            if try_add_movie(item):
                added_in_page += 1
                time.sleep(0.25)
                # Her 50 filmde kaydet
                if len(collected_movies) % 50 == 0:
                    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                        json.dump(collected_movies, f, ensure_ascii=False, indent=4)
                    with open(SEEN_FILE, "w", encoding="utf-8") as f:
                        json.dump(list(seen_movie_ids), f)
                    print(f"  [KAYIT] {len(collected_movies)} film kaydedildi")
    if added_in_page == 0 and page > 10:
        print(f"  Sayfa {page}'de yeni film yok, bir sonraki stratejiye geciliyor...")
        break

# --- STRATEJI 2: Yıl bazlı discover ---
if len(collected_movies) < TARGET_MOVIE_COUNT:
    print("\n[2] Yil bazli discover taranıyor...")
    for year in discover_years:
        if len(collected_movies) >= TARGET_MOVIE_COUNT:
            break
        for page in range(1, 11):  # Her yıldan max 10 sayfa
            if len(collected_movies) >= TARGET_MOVIE_COUNT:
                break
            results = fetch_page(
                "discover/movie", page,
                f"&sort_by=vote_count.desc&primary_release_year={year}&vote_count.gte=50"
            )
            if not results:
                break
            added = 0
            for item in results:
                if len(collected_movies) >= TARGET_MOVIE_COUNT:
                    break
                if try_add_movie(item):
                    added += 1
                    time.sleep(0.25)
                    if len(collected_movies) % 50 == 0:
                        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                            json.dump(collected_movies, f, ensure_ascii=False, indent=4)
                        with open(SEEN_FILE, "w", encoding="utf-8") as f:
                            json.dump(list(seen_movie_ids), f)
                        print(f"  [KAYIT] {len(collected_movies)} film kaydedildi")
            if added == 0:
                break

# --- STRATEJI 3: Tür bazlı discover ---
if len(collected_movies) < TARGET_MOVIE_COUNT:
    print("\n[3] Tur bazli discover taranıyor...")
    for genre_id in genre_ids:
        if len(collected_movies) >= TARGET_MOVIE_COUNT:
            break
        for page in range(1, 26):  # Her türden max 25 sayfa
            if len(collected_movies) >= TARGET_MOVIE_COUNT:
                break
            results = fetch_page(
                "discover/movie", page,
                f"&sort_by=popularity.desc&with_genres={genre_id}&vote_count.gte=100"
            )
            if not results:
                break
            added = 0
            for item in results:
                if len(collected_movies) >= TARGET_MOVIE_COUNT:
                    break
                if try_add_movie(item):
                    added += 1
                    time.sleep(0.25)
                    if len(collected_movies) % 50 == 0:
                        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                            json.dump(collected_movies, f, ensure_ascii=False, indent=4)
                        with open(SEEN_FILE, "w", encoding="utf-8") as f:
                            json.dump(list(seen_movie_ids), f)
                        print(f"  [KAYIT] {len(collected_movies)} film kaydedildi")
            if added == 0:
                break

# Son kayit
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(collected_movies, f, ensure_ascii=False, indent=4)
with open(SEEN_FILE, "w", encoding="utf-8") as f:
    json.dump(list(seen_movie_ids), f)

print(
    f"\nIslem tamamlandi! Toplam {len(collected_movies)} filme ulasildi ve"
    f" '{OUTPUT_FILE}' dosyasina kaydedildi."
)