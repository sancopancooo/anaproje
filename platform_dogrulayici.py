# -*- coding: utf-8 -*-
"""
platform_dogrulayici.py - Dizi & Film Platform Doğrulama Aracı
---------------------------------------------------------------
Veritabanındaki platform bilgilerini TMDB Watch Providers (TR) ile
karşılaştırır. Aynıysa dokunmaz; farklıysa TMDB sonucuna günceller.

Kullanım:
    python platform_dogrulayici.py                         # Dizi + film rapor
    python platform_dogrulayici.py --tip dizi              # Sadece diziler
    python platform_dogrulayici.py --tip film              # Sadece filmler
    python platform_dogrulayici.py --duzenle               # Farklıları güncelle
    python platform_dogrulayici.py --platform Netflix      # Sadece Netflix etiketli
    python platform_dogrulayici.py --tip dizi --duzenle --limit 50
"""

import os
import sys
import json
import time
import sqlite3
import argparse
import requests
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ─── AYARLAR ────────────────────────────────────────────────────────────────
API_KEY = "92051c06137fc349cd7e1fc16291b607"
BASE_URL = "https://api.themoviedb.org/3"

# Diziler → diziler_veritabani.db (~4600 kayıt)
# Filmler → diziler_veritabanı.db (filmler tablosu)
DB_PATH_DIZI = "katalog.db"
DB_PATH_FILM = "katalog.db"

REGION = "TR"
LANGUAGE = "tr-TR"
SLEEP = 0.4
MAX_RETRIES = 3

RAPOR_DOSYASI = "platform_dogrulama_raporu.json"


def db_path_for(media_type):
    return DB_PATH_DIZI if media_type == "dizi" else DB_PATH_FILM

# Her platform için:
#   aliases  → TMDB provider_name (normalize edilmiş) eşleşmeleri
#   dizi     → diziler tablosuna yazılacak isim
#   film     → filmler tablosuna yazılacak isim
#   db_aliases → DB'de görülebilecek alternatif yazımlar (karşılaştırma için)
#
# NOT: "Apple TV Store" (buy/rent) ≠ Apple TV+ ≠ Turkcell TV+
PLATFORM_MAP = {
    "netflix": {
        "aliases": ["netflix", "netflix standard with ads", "netflix basic with ads", "netflix kids"],
        "db_aliases": ["netflix"],
        "dizi": "Netflix",
        "film": "Netflix",
    },
    "amazon_prime": {
        "aliases": [
            "amazon prime video", "prime video", "amazon video",
            "amazon prime video with ads", "amazon prime",
        ],
        "db_aliases": ["amazon prime", "amazon prime video", "prime video"],
        "dizi": "Amazon Prime",
        "film": "Amazon Prime",
    },
    "disney": {
        "aliases": ["disney plus", "disney+"],
        "db_aliases": ["disney plus", "disney+", "disney"],
        "dizi": "Disney Plus",
        "film": "Disney+",
    },
    "hbo_max": {
        "aliases": ["hbo max", "max", "max amazon channel"],
        "db_aliases": ["hbo / max", "hbo max", "hbo", "max"],
        "dizi": "HBO / Max",
        "film": "HBO Max",
    },
    "apple_tv_plus": {
        "aliases": ["apple tv+", "apple tv plus"],
        "db_aliases": ["apple tv+", "apple tv plus", "apple tv"],
        "dizi": "Apple TV+",
        "film": "Apple TV+",
    },
    "tv_plus_turkcell": {
        # Sadece Turkcell TV+ (provider_id ≈ 1904) — Apple TV Store değil
        "aliases": ["tv+", "tv +(turkcell)"],
        "db_aliases": ["tv+"],
        "dizi": "TV+",
        "film": "TV+",
    },
    "crunchyroll": {
        "aliases": ["crunchyroll"],
        "db_aliases": ["crunchyroll"],
        "dizi": "Crunchyroll",
        "film": "Crunchyroll",
    },
    "blutv": {
        "aliases": ["blutv", "blu tv"],
        "db_aliases": ["blutv", "blu tv"],
        "dizi": "BluTV",
        "film": "BluTV",
    },
    "exxen": {
        "aliases": ["exxen"],
        "db_aliases": ["exxen"],
        "dizi": "Exxen",
        "film": "Exxen",
    },
    "tabii": {
        "aliases": ["tabii"],
        "db_aliases": ["tabii"],
        "dizi": "Tabii",
        "film": "Tabii",
    },
    "gain": {
        "aliases": ["gain"],
        "db_aliases": ["gain"],
        "dizi": "GAIN",
        "film": "GAIN",
    },
    "tod": {
        "aliases": ["tod", "tod tv", "bein connect"],
        "db_aliases": ["tod", "tod tv"],
        "dizi": "TOD TV",
        "film": "TOD TV",
    },
    "mubi": {
        "aliases": ["mubi"],
        "db_aliases": ["mubi"],
        "dizi": "MUBI",
        "film": "MUBI",
    },
}

DIGER = {"dizi": "Diğer Platformlar", "film": "Diğer Platform"}


# ─── YARDIMCI FONKSİYONLAR ──────────────────────────────────────────────────

def normalize(text):
    return str(text).strip().lower()


def is_diger(name):
    n = normalize(name)
    return n in ("diğer platform", "diğer platformlar", "diger platform", "diger platformlar", "sinema")


def safe_request(url, params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 15))
                print(f"\n⚠️ Rate limit! {wait}s bekleniyor...", end="", flush=True)
                time.sleep(wait + 1)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in (500, 502, 503, 504):
                time.sleep(5 * attempt)
                continue
            return None
        except Exception:
            time.sleep(3 * attempt)
    return None


def tmdb_search(media_type, isim, yil=""):
    """İsim + yıl ile TMDB ID bulur (dizilerde tmdb_id yok)."""
    endpoint = "tv" if media_type == "dizi" else "movie"
    params = {
        "api_key": API_KEY,
        "language": LANGUAGE,
        "query": isim,
        "include_adult": "false",
    }
    if yil and str(yil)[:4].isdigit():
        if media_type == "dizi":
            params["first_air_date_year"] = str(yil)[:4]
        else:
            params["primary_release_year"] = str(yil)[:4]

    data = safe_request(f"{BASE_URL}/search/{endpoint}", params)
    if not data:
        return None

    results = data.get("results") or []
    if not results:
        return None

    date_key = "first_air_date" if media_type == "dizi" else "release_date"
    if yil and str(yil)[:4].isdigit():
        for item in results:
            d = item.get(date_key) or ""
            if d.startswith(str(yil)[:4]):
                return item.get("id")
    return results[0].get("id")


def tmdb_get_providers(media_type, tmdb_id):
    """
    TR abonelik platformlarını çeker.
    Sadece flatrate / free / ads — buy/rent hariç.
    """
    endpoint = "tv" if media_type == "dizi" else "movie"
    data = safe_request(
        f"{BASE_URL}/{endpoint}/{tmdb_id}/watch/providers",
        {"api_key": API_KEY},
    )
    if not data:
        return None, "api_hatasi"

    tr_data = data.get("results", {}).get(REGION)
    if not tr_data:
        return [], "tr_yok"

    providers = []
    for key in ("flatrate", "free", "ads"):
        for p in tr_data.get(key, []) or []:
            name = normalize(p.get("provider_name", ""))
            if name and name not in providers:
                providers.append(name)
    return providers, "ok"


def parse_db_platforms(platformlar_str):
    if not platformlar_str:
        return []
    s = str(platformlar_str).strip()
    if s.startswith("["):
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                return [str(p).strip() for p in parsed if str(p).strip()]
        except Exception:
            pass
    return [p.strip() for p in s.split(",") if p.strip()]


def db_to_keys(db_platforms):
    """DB platform isimlerini iç anahtar setine çevirir (karşılaştırma için)."""
    keys = set()
    for raw in db_platforms:
        if is_diger(raw):
            continue
        n = normalize(raw)
        matched = False
        for key, info in PLATFORM_MAP.items():
            if n in info["db_aliases"] or n in info["aliases"] or n == normalize(info["dizi"]) or n == normalize(info["film"]):
                keys.add(key)
                matched = True
                break
        if not matched:
            # Tanınmayan etiket — karşılaştırma için ham anahtar
            keys.add(f"unknown:{n}")
    return keys


def tmdb_to_keys(tmdb_providers):
    """TMDB ham provider listesini iç anahtar setine çevirir."""
    keys = set()
    for name in tmdb_providers:
        for key, info in PLATFORM_MAP.items():
            if name in info["aliases"]:
                keys.add(key)
                break
    return keys


def keys_to_display(keys, media_type):
    """İç anahtarları tabloya yazılacak canonical isimlere çevirir."""
    result = []
    for key, info in PLATFORM_MAP.items():
        if key in keys:
            result.append(info[media_type])
    if not result:
        return [DIGER[media_type]]
    return result


def platforms_equal(db_platforms, tmdb_providers):
    """Sıra bağımsız, alias-aware eşitlik kontrolü."""
    db_keys = db_to_keys(db_platforms)
    tmdb_keys = tmdb_to_keys(tmdb_providers)

    # İkisi de boş / Diğer → eşit
    if not db_keys and not tmdb_keys:
        return True
    return db_keys == tmdb_keys


# ─── TEK MEDYA TİPİ DOĞRULAMA ───────────────────────────────────────────────

def dogrula_tip(media_type, hedef_platform=None, duzenle=False, limit=None):
    label = "DİZİ" if media_type == "dizi" else "FİLM"
    table = "diziler" if media_type == "dizi" else "filmler"
    emoji = "📺" if media_type == "dizi" else "🎬"
    db_path = db_path_for(media_type)

    print("\n" + "=" * 70)
    print(f"{emoji} {label} PLATFORM DOĞRULAYICI")
    print(f"   Veritabanı     : {db_path}")
    print(f"   Hedef Platform : {hedef_platform or 'Tümü'}")
    print(f"   Düzeltme Modu  : {'AÇIK ✅' if duzenle else 'KAPALI (sadece rapor)'}")
    print(f"   Limit          : {limit or 'Tümü'}")
    print("=" * 70)

    if not os.path.exists(db_path):
        print(f"❌ Veritabanı bulunamadı: {db_path}")
        return {
            "tip": media_type,
            "ozet": {
                "toplam": 0, "dogru": 0, "yanlis": 0,
                "bulunamadi": 0, "api_hatasi": 0, "duzeltilen": 0,
            },
            "kayitlar": [],
        }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if media_type == "dizi":
        # diziler tablosunda tmdb_id yok → isim + yıl ile aranacak
        if hedef_platform:
            cursor.execute(
                "SELECT id, isim, cikis_tarihi, platformlar FROM diziler "
                "WHERE platformlar LIKE ? AND platformlar IS NOT NULL ORDER BY id",
                (f"%{hedef_platform}%",),
            )
        else:
            cursor.execute(
                "SELECT id, isim, cikis_tarihi, platformlar FROM diziler "
                "WHERE platformlar IS NOT NULL AND platformlar != '' ORDER BY id"
            )
        rows = [
            {"id": r[0], "tmdb_id": None, "isim": r[1], "yil": (r[2] or "")[:4], "platformlar": r[3]}
            for r in cursor.fetchall()
        ]
    else:
        if hedef_platform:
            cursor.execute(
                "SELECT id, tmdb_id, isim, vizyon_tarihi, platformlar FROM filmler "
                "WHERE platformlar LIKE ? AND platformlar IS NOT NULL ORDER BY id",
                (f"%{hedef_platform}%",),
            )
        else:
            cursor.execute(
                "SELECT id, tmdb_id, isim, vizyon_tarihi, platformlar FROM filmler "
                "WHERE platformlar IS NOT NULL AND platformlar != '' ORDER BY id"
            )
        rows = [
            {"id": r[0], "tmdb_id": r[1], "isim": r[2], "yil": (r[3] or "")[:4], "platformlar": r[4]}
            for r in cursor.fetchall()
        ]

    if limit:
        rows = rows[:limit]

    print(f"📋 Kontrol edilecek {label.lower()} sayısı: {len(rows)}\n")

    tmdb_cache = {}
    rapor = []
    dogru = yanlis = api_hatasi = bulunamadi = duzeltilen = 0

    for i, row in enumerate(rows, 1):
        item_id = row["id"]
        isim = row["isim"] or ""
        yil = row["yil"]
        platformlar_str = row["platformlar"]
        db_platforms = parse_db_platforms(platformlar_str)

        print(f"[{i:4d}/{len(rows)}] {emoji} {isim[:40]:<40} ", end="", flush=True)

        # TMDB ID
        tmdb_id = row["tmdb_id"]
        if tmdb_id:
            try:
                tmdb_id = int(tmdb_id)
            except (TypeError, ValueError):
                tmdb_id = None

        if not tmdb_id:
            cache_key = f"{media_type}:{normalize(isim)}:{yil}"
            if cache_key in tmdb_cache:
                tmdb_id = tmdb_cache[cache_key]
            else:
                tmdb_id = tmdb_search(media_type, isim, yil)
                tmdb_cache[cache_key] = tmdb_id
                time.sleep(0.25)

        if not tmdb_id:
            bulunamadi += 1
            print("⚠️  TMDB'de bulunamadı, atlandı")
            time.sleep(SLEEP)
            continue

        tmdb_providers, durum = tmdb_get_providers(media_type, tmdb_id)

        if durum == "api_hatasi":
            api_hatasi += 1
            print("❌ API hatası")
            time.sleep(SLEEP)
            continue

        gercek_platforms = keys_to_display(tmdb_to_keys(tmdb_providers), media_type)
        ayni = platforms_equal(db_platforms, tmdb_providers)

        if ayni:
            # Yazım farkı varsa (Disney Plus vs Disney+) yine de normalize et
            canonical_str = ", ".join(gercek_platforms)
            db_str = ", ".join(db_platforms) if db_platforms else DIGER[media_type]
            if duzenle and normalize(db_str) != normalize(canonical_str):
                # Aynı platformlar ama farklı yazım → düzelt
                cursor.execute(
                    f"UPDATE {table} SET platformlar = ? WHERE id = ?",
                    (canonical_str, item_id),
                )
                conn.commit()
                duzeltilen += 1
                dogru += 1
                print(f"✅ AYNI (yazım düzeltildi) — {db_str} → {canonical_str}")
                rapor.append({
                    "id": item_id, "tmdb_id": tmdb_id, "isim": isim,
                    "db_platformlari": db_platforms,
                    "gercek_platformlar": gercek_platforms,
                    "durum": "yazim_duzeltildi",
                })
            else:
                dogru += 1
                print(f"✅ AYNI — {', '.join(db_platforms) or DIGER[media_type]}")
                rapor.append({
                    "id": item_id, "tmdb_id": tmdb_id, "isim": isim,
                    "db_platformlari": db_platforms,
                    "gercek_platformlar": gercek_platforms,
                    "durum": "dogru",
                })
        else:
            yanlis += 1
            print(
                f"❌ FARKLI — DB: {', '.join(db_platforms) or DIGER[media_type]} "
                f"| TMDB: {', '.join(gercek_platforms)}"
            )
            rapor.append({
                "id": item_id, "tmdb_id": tmdb_id, "isim": isim,
                "db_platformlari": db_platforms,
                "gercek_platformlar": gercek_platforms,
                "durum": "yanlis",
                "tmdb_raw_providers": tmdb_providers,
            })

            if duzenle:
                yeni = ", ".join(gercek_platforms)
                cursor.execute(
                    f"UPDATE {table} SET platformlar = ? WHERE id = ?",
                    (yeni, item_id),
                )
                conn.commit()
                duzeltilen += 1
                print(f"          ✏️  Güncellendi: '{platformlar_str}' → '{yeni}'")

        time.sleep(SLEEP)

    print("\n" + "-" * 70)
    print(f"📊 {label} ÖZET")
    print(f"  ✅ Aynı platform bilgisi    : {dogru}")
    print(f"  ❌ Farklı platform bilgisi  : {yanlis}")
    print(f"  ⚠️  TMDB'de bulunamayan     : {bulunamadi}")
    print(f"  🌐 API hatası               : {api_hatasi}")
    if duzenle:
        print(f"  ✏️  Güncellenen kayıt       : {duzeltilen}")
    if dogru + yanlis > 0:
        print(f"  📈 Eşleşme oranı           : %{round(dogru / (dogru + yanlis) * 100, 1)}")

    conn.close()

    return {
        "tip": media_type,
        "ozet": {
            "toplam": len(rows),
            "dogru": dogru,
            "yanlis": yanlis,
            "bulunamadi": bulunamadi,
            "api_hatasi": api_hatasi,
            "duzeltilen": duzeltilen,
        },
        "kayitlar": rapor,
    }


# ─── ANA GİRİŞ ──────────────────────────────────────────────────────────────

def dogrula(tip="hepsi", hedef_platform=None, duzenle=False, limit=None):
    print("=" * 70)
    print("🔍 PLATFORM DOĞRULAYICI (TMDB Watch Providers · TR)")
    print(f"   Tip            : {tip}")
    print(f"   Dizi DB        : {DB_PATH_DIZI}")
    print(f"   Film DB        : {DB_PATH_FILM}")
    print(f"   Hedef Platform : {hedef_platform or 'Tümü'}")
    print(f"   Düzeltme Modu  : {'AÇIK ✅' if duzenle else 'KAPALI (sadece rapor)'}")
    print(f"   Limit          : {limit or 'Tümü'}")
    print("=" * 70)

    rapor_data = {
        "olusturulma": datetime.now().isoformat(),
        "tip": tip,
        "hedef_platform": hedef_platform,
        "duzenle": duzenle,
        "limit": limit,
        "sonuclar": {},
    }

    tipler = []
    if tip in ("dizi", "hepsi"):
        tipler.append("dizi")
    if tip in ("film", "hepsi"):
        tipler.append("film")

    for media_type in tipler:
        sonuc = dogrula_tip(
            media_type,
            hedef_platform=hedef_platform,
            duzenle=duzenle,
            limit=limit,
        )
        rapor_data["sonuclar"][media_type] = sonuc

    with open(RAPOR_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(rapor_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print(f"💾 Rapor kaydedildi: {RAPOR_DOSYASI}")
    print("=" * 70)

    # Kısa yanlış özeti
    for media_type, sonuc in rapor_data["sonuclar"].items():
        yanlislar = [r for r in sonuc["kayitlar"] if r["durum"] == "yanlis"]
        if not yanlislar:
            continue
        emoji = "📺" if media_type == "dizi" else "🎬"
        print(f"\n❌ FARKLI {media_type.upper()}LER ({len(yanlislar)} adet) — ilk 20:")
        print("-" * 70)
        for r in yanlislar[:20]:
            print(f"  {emoji} {r['isim']}")
            print(f"     DB   : {', '.join(r['db_platformlari']) or DIGER[media_type]}")
            print(f"     TMDB : {', '.join(r['gercek_platformlar'])}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Dizi ve film platform bilgilerini TMDB ile doğrular / günceller."
    )
    parser.add_argument(
        "--tip",
        choices=["dizi", "film", "hepsi"],
        default="hepsi",
        help="Kontrol edilecek medya tipi (varsayılan: hepsi — önce dizi, sonra film).",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default=None,
        help="Sadece bu platform etiketine sahip kayıtlar (ör: Netflix, 'Disney Plus').",
    )
    parser.add_argument(
        "--duzenle",
        action="store_true",
        help="Farklı platform bilgilerini TMDB sonucuna göre günceller.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Her tip için maksimum kayıt sayısı (test için).",
    )

    args = parser.parse_args()
    dogrula(
        tip=args.tip,
        hedef_platform=args.platform,
        duzenle=args.duzenle,
        limit=args.limit,
    )
