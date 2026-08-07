# -*- coding: utf-8 -*-
"""
dizi_platform_dogrulayici.py - Diziler İçin Platform Doğrulama Aracı
----------------------------------------------------------------------
Diziler tablosundaki platform bilgilerini TMDB Watch Providers API ile
karşılaştırır. Yanlış etiketlenmiş dizileri raporlar ve düzeltir.

Kullanım:
    python dizi_platform_dogrulayici.py                      # Tüm diziler rapor
    python dizi_platform_dogrulayici.py --platform Netflix   # Sadece Netflix
    python dizi_platform_dogrulayici.py --duzenle            # Yanlışları düzelt
    python dizi_platform_dogrulayici.py --limit 50           # 50 dizi test
    python dizi_platform_dogrulayici.py --platform Netflix --duzenle --limit 30
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
API_KEY      = "92051c06137fc349cd7e1fc16291b607"
BASE_URL     = "https://api.themoviedb.org/3"
DB_PATH      = "katalog.db"
REGION       = "TR"
LANGUAGE     = "tr-TR"
SLEEP        = 0.5          # API çağrıları arası bekleme (saniye)
MAX_RETRIES  = 3

RAPOR_DOSYASI = "dizi_platform_dogrulama_raporu.json"

# NOT: TMDB'deki "Apple TV Store" → satın alma mağazası → TV+ DEĞİL!
#      TMDB'deki "TV+" (provider_id=1904) → Türk TV+ (Turkcell) → doğru.
PLATFORM_ALIASES = {
    "Netflix":       ["netflix", "netflix standard with ads", "netflix basic with ads", "netflix kids"],
    "Amazon Prime":  ["amazon prime video", "prime video", "amazon video", "amazon prime video with ads"],
    "Disney Plus":   ["disney plus", "disney+"],
    "TV+":           ["tv+", "tv +(turkcell)"],   # Sadece Türk TV+ (provider_id=1904)
    "HBO / Max":     ["hbo max", "max"],
    "MUBI":          ["mubi"],
    "Crunchyroll":   ["crunchyroll"],
    "BluTV":         ["blutv", "blu tv"],
    "Exxen":         ["exxen"],
    "Tabii":         ["tabii"],
    "GAIN":          ["gain"],
    "TOD TV":        ["tod", "tod tv"],
    "Diğer Platformlar": [],
}

# ─── YARDIMCI FONKSİYONLAR ──────────────────────────────────────────────────

def normalize(text):
    return str(text).strip().lower()


def safe_request(url, params):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 20))
                print(f"\n⚠️ Rate limit! {wait}s bekleniyor...", end="", flush=True)
                time.sleep(wait + 1)
                continue
            if r.status_code == 200:
                return r.json()
            if r.status_code in [500, 502, 503, 504]:
                time.sleep(5 * attempt)
                continue
            return None
        except Exception:
            time.sleep(3 * attempt)
    return None


def tmdb_search_tv(isim, yil=""):
    """Dizi adına göre TMDB'de arama yapar, TMDB ID döner."""
    params = {
        "api_key": API_KEY,
        "language": LANGUAGE,
        "query": isim,
        "include_adult": "false"
    }
    if yil and str(yil)[:4].isdigit():
        params["first_air_date_year"] = str(yil)[:4]

    data = safe_request(f"{BASE_URL}/search/tv", params)
    if not data:
        return None

    results = data.get("results", [])
    if not results:
        return None

    # Yıl eşleşmesi varsa önce onu al
    if yil and str(yil)[:4].isdigit():
        for item in results:
            fad = item.get("first_air_date") or ""
            if fad.startswith(str(yil)[:4]):
                return item.get("id")

    return results[0].get("id")


def tmdb_get_tv_providers(tmdb_id):
    """
    Bir dizinin Türkiye'deki gerçek ABONE platformlarını TMDB'den çeker.
    Sadece flatrate (abonelik), free ve ads — buy/rent HARİÇ.
    """
    data = safe_request(
        f"{BASE_URL}/tv/{tmdb_id}/watch/providers",
        {"api_key": API_KEY}
    )
    if not data:
        return None, "api_hatasi"

    tr_data = data.get("results", {}).get(REGION)
    if not tr_data:
        return [], "tr_yok"

    providers = []
    for key in ["flatrate", "free", "ads"]:
        for p in tr_data.get(key, []) or []:
            name = normalize(p.get("provider_name", ""))
            if name and name not in providers:
                providers.append(name)
    return providers, "ok"


def parse_db_platforms(platformlar_str):
    """DB'deki platform stringini listeye çevirir."""
    if not platformlar_str:
        return []
    if platformlar_str.startswith("["):
        try:
            return json.loads(platformlar_str)
        except:
            pass
    return [p.strip() for p in platformlar_str.split(",") if p.strip()]


def check_platform_match(db_platform, tmdb_providers):
    """DB'deki platform adı gerçekten TMDB'de var mı? True/False/None döner."""
    if db_platform in ["Diğer Platformlar", "Diğer Platform"]:
        return None  # Doğrulama gerekmez

    aliases = PLATFORM_ALIASES.get(db_platform, [])
    for alias in aliases:
        if alias in tmdb_providers:
            return True
    return False


def get_canonical_platforms(tmdb_providers):
    """TMDB provider listesini DB'deki canonical isimlere çevirir."""
    result = []
    for platform_name, aliases in PLATFORM_ALIASES.items():
        if platform_name in ["Diğer Platformlar", "Diğer Platform"]:
            continue
        for alias in aliases:
            if alias in tmdb_providers:
                if platform_name not in result:
                    result.append(platform_name)
                break
    # Diziler için "Diğer Platformlar" (s'li)
    return result if result else ["Diğer Platformlar"]


# ─── ANA KONTROL FONKSİYONU ─────────────────────────────────────────────────

def dogrula(hedef_platform=None, duzenle=False, limit=None):
    print("=" * 70)
    print("📺 DİZİ PLATFORM DOĞRULAYICI")
    print(f"   Hedef Platform : {hedef_platform or 'Tümü'}")
    print(f"   Düzeltme Modu  : {'AÇIK ✅' if duzenle else 'KAPALI (sadece rapor)'}")
    print(f"   Limit          : {limit or 'Tümü'}")
    print("=" * 70)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if hedef_platform:
        cursor.execute(
            "SELECT id, isim, cikis_tarihi, platformlar FROM diziler "
            "WHERE platformlar LIKE ? AND platformlar IS NOT NULL "
            "ORDER BY id",
            (f"%{hedef_platform}%",)
        )
    else:
        cursor.execute(
            "SELECT id, isim, cikis_tarihi, platformlar FROM diziler "
            "WHERE platformlar IS NOT NULL AND platformlar != '' "
            "ORDER BY id"
        )

    rows = cursor.fetchall()
    if limit:
        rows = rows[:limit]

    print(f"📋 Kontrol edilecek dizi sayısı: {len(rows)}\n")

    # TMDB ID önbelleği (aynı diziye iki kez arama yapmamak için)
    tmdb_cache = {}

    rapor = []
    dogru = 0
    yanlis = 0
    api_hatasi = 0
    bulunamadi = 0
    duzeltilen = 0

    for i, (dizi_id, isim, cikis, platformlar_str) in enumerate(rows, 1):
        db_platforms = parse_db_platforms(platformlar_str)
        yil = (cikis or "")[:4]

        print(f"[{i:4d}/{len(rows)}] 📺 {isim[:40]:<40} ", end="", flush=True)

        # TMDB'de ara (önbellekte yoksa)
        cache_key = f"{isim}_{yil}"
        if cache_key in tmdb_cache:
            tmdb_id = tmdb_cache[cache_key]
        else:
            tmdb_id = tmdb_search_tv(isim, yil)
            tmdb_cache[cache_key] = tmdb_id
            time.sleep(0.3)  # arama için ek bekleme

        if not tmdb_id:
            bulunamadi += 1
            print("⚠️  TMDB'de bulunamadı, atlandı")
            time.sleep(SLEEP)
            continue

        # TMDB'den gerçek platformları çek
        tmdb_providers, durum = tmdb_get_tv_providers(tmdb_id)

        if durum == "api_hatasi":
            api_hatasi += 1
            print("❌ API hatası")
            time.sleep(SLEEP)
            continue

        gercek_platforms = get_canonical_platforms(tmdb_providers)

        # Hatalı ve eksik etiketleri bul
        hatalar = []
        for db_p in db_platforms:
            eslesme = check_platform_match(db_p, tmdb_providers)
            if eslesme is False:
                hatalar.append(db_p)

        eksik = []
        for gercek_p in gercek_platforms:
            if gercek_p not in ["Di&#287;er Platformlar", "Di&#287;er Platform"] and gercek_p not in db_platforms:
                eksik.append(gercek_p)

        if hatalar or eksik:
            yanlis += 1
            sembol = "❌"
            durum_text = f"YANLIŞ — DB: {', '.join(db_platforms)} | Gerçek: {', '.join(gercek_platforms)}"
        else:
            dogru += 1
            sembol = "✅"
            durum_text = f"DOĞRU — {', '.join(db_platforms)}"

        print(f"{sembol} {durum_text}")

        rapor_kaydi = {
            "id": dizi_id,
            "tmdb_id": tmdb_id,
            "isim": isim,
            "cikis_tarihi": cikis,
            "db_platformlari": db_platforms,
            "gercek_platformlar": gercek_platforms,
            "yanlis_etiketler": hatalar,
            "eksik_etiketler": eksik,
            "durum": "yanlis" if (hatalar or eksik) else "dogru",
            "tmdb_raw_providers": tmdb_providers
        }
        rapor.append(rapor_kaydi)

        # Düzeltme modu
        if duzenle:
            if hatalar or eksik:
                yeni_platformlar = ", ".join(gercek_platforms)
                cursor.execute(
                    "UPDATE diziler SET platformlar = ? WHERE id = ?",
                    (yeni_platformlar, dizi_id)
                )
                conn.commit()
                duzeltilen += 1
                print(f"          ✏️  Düzeltildi: '{platformlar_str}' → '{yeni_platformlar}'")
            elif not hatalar and not eksik:
                # Mükerrer platform kaydı varsa temizle (ör: HBO/Max 4 kez)
                db_set = list(dict.fromkeys(db_platforms))  # sırayı koruyarak tekrarları sil
                if len(db_set) != len(db_platforms):
                    temiz = ", ".join(db_set)
                    cursor.execute(
                        "UPDATE diziler SET platformlar = ? WHERE id = ?",
                        (temiz, dizi_id)
                    )
                    conn.commit()
                    duzeltilen += 1
                    print(f"          🧹 Mükerrer temizlendi: '{platformlar_str}' → '{temiz}'")

        time.sleep(SLEEP)

    # ─── ÖZET ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("📊 ÖZET")
    print(f"  ✅ Doğru platform bilgisi   : {dogru}")
    print(f"  ❌ Yanlış platform bilgisi  : {yanlis}")
    print(f"  ⚠️  TMDB'de bulunamayan     : {bulunamadi}")
    print(f"  🌐 API hatası               : {api_hatasi}")
    if duzenle:
        print(f"  ✏️  Düzeltilen kayıt        : {duzeltilen}")

    if dogru + yanlis > 0:
        dogruluk = round(dogru / (dogru + yanlis) * 100, 1)
        print(f"  📈 Doğruluk oranı          : %{dogruluk}")

    print(f"\n💾 Rapor kaydedildi: {RAPOR_DOSYASI}")
    print("=" * 70)

    # Raporu kaydet
    rapor_data = {
        "olusturulma": datetime.now().isoformat(),
        "hedef_platform": hedef_platform,
        "duzenle": duzenle,
        "limit": limit,
        "ozet": {
            "toplam": len(rows),
            "dogru": dogru,
            "yanlis": yanlis,
            "bulunamadi": bulunamadi,
            "api_hatasi": api_hatasi,
            "duzeltilen": duzeltilen
        },
        "diziler": rapor
    }
    with open(RAPOR_DOSYASI, "w", encoding="utf-8") as f:
        json.dump(rapor_data, f, ensure_ascii=False, indent=2)

    conn.close()

    # Yanlışları özet olarak göster
    yanlis_diziler = [r for r in rapor if r["durum"] == "yanlis"]
    if yanlis_diziler:
        print(f"\n❌ YANLIŞ ETİKETLİ DİZİLER ({len(yanlis_diziler)} adet):")
        print("-" * 70)
        for r in yanlis_diziler[:20]:
            print(f"  📺 {r['isim']}")
            print(f"     DB'de    : {', '.join(r['db_platformlari'])}")
            print(f"     Gerçekte : {', '.join(r['gercek_platformlar'])}")
            if r['yanlis_etiketler']:
                print(f"     Hatalı   : {', '.join(r['yanlis_etiketler'])}")
            if r['eksik_etiketler']:
                print(f"     Eksik    : {', '.join(r['eksik_etiketler'])}")
        if len(yanlis_diziler) > 20:
            print(f"\n  ... ve {len(yanlis_diziler) - 20} dizi daha. Tüm liste: {RAPOR_DOSYASI}")


# ─── GİRİŞ NOKTASI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Diziler tablosundaki platform bilgilerini TMDB ile doğrular."
    )
    parser.add_argument(
        "--platform",
        type=str,
        default=None,
        help="Kontrol edilecek platform (ör: Netflix, 'Disney Plus', 'Amazon Prime'). "
             "Belirtilmezse tüm diziler kontrol edilir."
    )
    parser.add_argument(
        "--duzenle",
        action="store_true",
        help="Yanlış platform bilgilerini otomatik olarak düzeltir."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Kontrol edilecek maksimum dizi sayısı (test için)."
    )

    args = parser.parse_args()
    dogrula(
        hedef_platform=args.platform,
        duzenle=args.duzenle,
        limit=args.limit
    )
