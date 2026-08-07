# -*- coding: utf-8 -*-
"""
platform_ikinci_gecis.py
--------------------------------------------------------------
Amaç:
  - platform_guncellemeleri_tmdb.json içindeki "Diğer Platform" olan kayıtları
    ikinci kez TMDB'ye sorar
  - Bu sefer filmin ORİJİNAL adıyla arama yapar
  - Sadece FLATRATE (abonelik) platformlarını sayar
  - Netflix, Amazon Prime Video, Disney Plus'a öncelik verir
  - Bulunanları JSON'da günceller
  - DB'ye DOKUNMAZ

Çalıştırma:
  python platform_ikinci_gecis.py
  python platform_ikinci_gecis.py --limit 100
--------------------------------------------------------------
"""

import os
import sys
import json
import time
import argparse
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ================================
# AYARLAR
# ================================
API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"

INPUT_JSON = "platform_guncellemeleri_tmdb.json"
OUTPUT_JSON = "platform_guncellemeleri_tmdb.json"   # aynı dosya üzerine yazacağız

REGION = "TR"
LANGUAGE = "tr-TR"

REQUEST_TIMEOUT = 15
SLEEP_BETWEEN = 0.3
SAVE_EVERY = 20

PLATFORM_SEPARATOR = ", "

# Öncelikli platformlar
PRIORITY_PLATFORMS = ["Netflix", "Amazon Prime Video", "Disney Plus"]

ALLOWED_PLATFORMS = [
    "Netflix",
    "Amazon Prime Video",
    "Disney Plus",
    "TV+",
    "TOD TV",
    "MUBI",
    "HBO Max",
    "Crunchyroll",
    "BluTV",
    "Exxen",
    "Tabii",
    "GAIN",
    "Shahid VIP",
    "Sun Nxt",
    "KableOne",
    "Bloodstream",
    "Diğer Platform"
]

PLATFORM_ORDER = {name: i for i, name in enumerate(ALLOWED_PLATFORMS)}

PROVIDER_ALIASES = {
    "netflix": "Netflix",
    "netflix standard with ads": "Netflix",
    "netflix basic with ads": "Netflix",
    "netflix kids": "Netflix",

    "amazon prime video": "Amazon Prime Video",
    "amazon video": "Amazon Prime Video",
    "prime video": "Amazon Prime Video",
    "amazon prime video with ads": "Amazon Prime Video",

    "disney plus": "Disney Plus",
    "disney+": "Disney Plus",

    "apple tv plus": "TV+",
    "apple tv+": "TV+",
    "apple tv": "TV+",

    "tod": "TOD TV",
    "tod tv": "TOD TV",

    "mubi": "MUBI",

    "hbo max": "HBO Max",
    "max": "HBO Max",

    "crunchyroll": "Crunchyroll",

    "blutv": "BluTV",
    "blu tv": "BluTV",

    "exxen": "Exxen",

    "tabii": "Tabii",

    "gain": "GAIN",

    "shahid vip": "Shahid VIP",
    "shahid": "Shahid VIP",

    "sun nxt": "Sun Nxt",
    "sunnxt": "Sun Nxt",

    "kableone": "KableOne",
    "bloodstream": "Bloodstream"
}


# ================================
# YARDIMCILAR
# ================================
def normalize_provider_name(name):
    if not name:
        return None
    key = str(name).strip().lower()
    key = " ".join(key.split())
    return PROVIDER_ALIASES.get(key)


def finalize_platforms(platform_list):
    if not platform_list:
        return ["Diğer Platform"]

    unique = []
    seen = set()
    for p in platform_list:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    unique.sort(key=lambda x: PLATFORM_ORDER.get(x, 999))
    return unique


def load_json():
    if not os.path.exists(INPUT_JSON):
        print(f"❌ Dosya bulunamadı: {INPUT_JSON}")
        sys.exit(1)

    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data):
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ================================
# TMDB İŞLEMLERİ
# ================================
def tmdb_get_movie_details(tmdb_id):
    """Filmin detayını çeker (orijinal adı almak için)."""
    try:
        r = requests.get(
            f"{BASE_URL}/movie/{tmdb_id}",
            params={"api_key": API_KEY, "language": "en-US"},
            timeout=REQUEST_TIMEOUT
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def tmdb_search_movie(title, year=""):
    """İsim + yıl ile film arar, ilk sonucun ID'sini döner."""
    if not title:
        return None
    try:
        params = {
            "api_key": API_KEY,
            "language": "en-US",
            "query": title,
            "include_adult": "false"
        }
        if year and str(year).isdigit():
            params["year"] = year

        r = requests.get(f"{BASE_URL}/search/movie", params=params, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None

        results = r.json().get("results", [])
        if not results:
            return None

        if year and str(year).isdigit():
            for item in results:
                rd = item.get("release_date") or ""
                if rd.startswith(str(year)):
                    return item.get("id")
        return results[0].get("id")
    except Exception:
        return None


def tmdb_get_watch_providers(tmdb_id):
    """Sadece flatrate (abonelik) alır."""
    if not tmdb_id:
        return []
    try:
        r = requests.get(
            f"{BASE_URL}/movie/{tmdb_id}/watch/providers",
            params={"api_key": API_KEY},
            timeout=REQUEST_TIMEOUT
        )
        if r.status_code != 200:
            return []

        tr_data = r.json().get("results", {}).get(REGION, {})

        collected = []
        for key in ["flatrate", "free", "ads"]:
            for provider in tr_data.get(key, []) or []:
                name = provider.get("provider_name", "")
                canonical = normalize_provider_name(name)
                if canonical and canonical not in collected:
                    collected.append(canonical)
        return collected
    except Exception:
        return []


# ================================
# ANA AKIŞ
# ================================
def run(limit=None):
    print("=" * 70)
    print("🎯 İKİNCİ GEÇİŞ - Netflix / Prime / Disney+ kurtarma modu")
    print("=" * 70)

    data = load_json()
    print(f"📄 Toplam kayıt: {len(data)}")

    # "Diğer Platform" olanları bul
    targets = []
    for idx, item in enumerate(data):
        plat = str(item.get("platformlar", "")).strip()
        if plat == "Diğer Platform":
            targets.append(idx)

    print(f"🎯 'Diğer Platform' kayıt sayısı: {len(targets)}")

    if limit:
        targets = targets[:int(limit)]

    print(f"🔁 Bu turda yeniden denenecek   : {len(targets)}")
    print("=" * 70)

    if not targets:
        print("✅ Yeniden denenecek kayıt yok.")
        return

    stat_kurtarildi = 0
    stat_hala_diger = 0
    stat_priority = 0
    start = time.time()

    for i, idx in enumerate(targets, start=1):
        item = data[idx]
        title = item.get("title", "")
        year = item.get("year", "")
        tmdb_id = item.get("tmdb_id")

        print(f"[{i}/{len(targets)}] 🎬 {title} ({year}) -> ", end="", flush=True)

        original_title = None

        # 1) tmdb_id varsa detay çek, orijinal ismi al
        if tmdb_id:
            details = tmdb_get_movie_details(tmdb_id)
            if details:
                original_title = details.get("original_title") or details.get("title")

        # 2) orijinal isimle tekrar ara
        new_tmdb_id = None
        if original_title and original_title != title:
            new_tmdb_id = tmdb_search_movie(original_title, year)

        # 3) tekrar aramadan bir şey çıkmadıysa mevcut id ile provider dene
        candidate_id = new_tmdb_id or tmdb_id

        platforms_raw = []
        if candidate_id:
            platforms_raw = tmdb_get_watch_providers(candidate_id)

        platforms_final = finalize_platforms(platforms_raw)

        if platforms_final == ["Diğer Platform"]:
            stat_hala_diger += 1
            print("hâlâ Diğer Platform")
        else:
            stat_kurtarildi += 1
            if any(p in PRIORITY_PLATFORMS for p in platforms_final):
                stat_priority += 1
                mark = "⭐"
            else:
                mark = "✅"

            platform_text = PLATFORM_SEPARATOR.join(platforms_final)
            data[idx]["platformlar"] = platform_text
            data[idx]["platformlar_liste"] = platforms_final
            data[idx]["kaynak"] = "tmdb_ikinci_gecis"
            data[idx]["orijinal_ad"] = original_title
            if new_tmdb_id and new_tmdb_id != tmdb_id:
                data[idx]["tmdb_id_duzeltildi"] = new_tmdb_id

            print(f"{mark} {platform_text}")

        if i % SAVE_EVERY == 0:
            save_json(data)
            print(f"💾 Ara kayıt yapıldı -> {OUTPUT_JSON}")

        time.sleep(SLEEP_BETWEEN)

    save_json(data)

    elapsed = round(time.time() - start, 1)
    print("=" * 70)
    print(f"✅ Tamamlandı ({elapsed} sn)")
    print(f"💾 Çıktı: {OUTPUT_JSON}")
    print("-" * 70)
    print("İSTATİSTİK")
    print(f"  Toplam yeniden denenen : {len(targets)}")
    print(f"  Kurtarılan             : {stat_kurtarildi}")
    print(f"  ⭐ Netflix/Prime/Disney : {stat_priority}")
    print(f"  Hâlâ 'Diğer Platform'  : {stat_hala_diger}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Bu turda işlenecek maksimum kayıt")
    args = parser.parse_args()
    run(limit=args.limit)