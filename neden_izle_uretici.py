# -*- coding: utf-8 -*-
"""
🎬 FİLM NEDEN İZLEMELİSİN? ÜRETİCİ
-------------------------------------
movies_dataset.json içindeki her film için Groq AI ile
3 maddelik "Neden İzlemelisin?" metni üretir.

Çıktı: neden_izle_havuzu.json
  {
    "<film_id>": {
      "id": "...",
      "title": "...",
      "maddeler": ["madde1", "madde2", "madde3"],
      "ts": 1234567890
    },
    ...
  }

Çalıştır:
  python neden_izle_uretici.py
  python neden_izle_uretici.py --limit 100
  python neden_izle_uretici.py --save-every 10
"""

import os
import sys
import json
import time
import re
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

# ═══════════════════════ AYARLAR ═══════════════════════
MOVIES_JSON  = "movies_dataset.json"       # kaynak
POOL_JSON    = "neden_izle_havuzu.json"    # hedef (birikimli havuz)
SAVE_EVERY   = 10                          # kaç filmde bir kaydet
SLEEP_SEC    = 0.4                         # istek arası bekleme
# ════════════════════════════════════════════════════════

# ─── Groq / OpenAI uyumlu client ─────────────────────
load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY", "")

try:
    from openai import OpenAI
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=API_KEY)
    AI_AVAILABLE = True
except ImportError:
    print("⚠️  'pip install openai python-dotenv' çalıştırın.")
    AI_AVAILABLE = False


# ═══════════════════════ PROMPT ═══════════════════════
SYSTEM_PROMPT = """\
Sen uzman bir film eleştirmenisin. Sana bir film verilecek; o filme özgü, somut, merak uyandıran 3 maddelik "Neden İzlemelisin?" metni yaz.

KESİN KURALLAR:
1. Tam olarak 3 madde — ne eksik ne fazla.
2. Her madde tek cümle, maksimum 15 kelime.
3. Her maddenin konusu farklı olsun:
   • 1. madde → senaryonun özgün yönü, beklenmedik bir unsur veya filmsel gerilim
   • 2. madde → oyunculuk/yönetmenlik/görsel-müzikal kalite; kime ait olduğunu söyle
   • 3. madde → izleyicide bıraktığı kalıcı his, tartışma ya da etki
4. Çıktı formatı kesinlikle şu şekilde olmalı, başka HİÇBİR şey yazma:
   MADDE1: <metin>
   MADDE2: <metin>
   MADDE3: <metin>

KESINLIKLE YAZMA — bu ifadeler yasak:
- "ilginç bir hikaye", "etkileyici bir hikaye", "güçlü bir hikaye"
- "ilginç bir" ile başlayan her şey
- "sahiptir" ile biten jenerik cümleler
- "izleyiciyi etkiler", "izleyiciyi düşündürür" gibi muğlak yargılar
- "mutlaka izleyin", "kaçırılmamalı" gibi klişe tavsiyeler
- "sunmaktadır", "barındırmaktadır" gibi pasif bürokratik ifadeler

BUNUN YERİNE YAP:
- Filmin türüne, dönemine, atmosferine veya yönetmenine özel bir detay ver
- Soyut değil, somut bir nitelik veya atmosfer tanımla
- Cümleyi güçlü bir fiil veya özgün bir sıfatla bitir

Spoiler verme. Reklam dili kullanma. Türkçe yaz.
"""


def build_user_prompt(title, year, genres):
    year_str  = f" ({year})" if year else ""
    # TMDB tarzı dict listesi: [{"id": 18, "name": "Drama"}, ...]
    if genres and isinstance(genres, list) and isinstance(genres[0], dict):
        genre_str = ", ".join(g.get("name", "") for g in genres if g.get("name"))
    elif isinstance(genres, list):
        genre_str = ", ".join(str(g) for g in genres)
    else:
        genre_str = str(genres)
    return f"Film: {title}{year_str}\nTürler: {genre_str}"


# ═══════════════════════ PARSE ════════════════════════
_MADDE_RE = re.compile(
    r"MADDE\d\s*[:：]\s*(.+)", re.IGNORECASE
)

def parse_maddeler(raw: str):
    """AI çıktısından 3 maddeyi ayıklar; başarısız olursa None döner."""
    if not raw:
        return None
    matches = _MADDE_RE.findall(raw)
    maddeler = [m.strip() for m in matches if m.strip()]
    if len(maddeler) >= 3:
        return maddeler[:3]
    # Alternatif: numaralı liste (1. 2. 3.)
    num_matches = re.findall(r"(?:^|\n)\s*\d[.)\-]\s*(.+)", raw)
    maddeler = [m.strip() for m in num_matches if m.strip()]
    if len(maddeler) >= 3:
        return maddeler[:3]
    return None


# ═══════════════════════ AI ÇAĞRISI ═══════════════════
MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

def generate_neden_izle(title, year, genres):
    if not AI_AVAILABLE:
        return None

    user_prompt = build_user_prompt(title, year, genres)

    for model in MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.85,
                max_tokens=220,
            )
            raw    = resp.choices[0].message.content or ""
            parsed = parse_maddeler(raw)
            if parsed:
                return parsed
            # parse başarısız → sonraki model
            print(f" (⚠️ {model} parse başarısız)", end="", flush=True)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate_limit" in err:
                print(f" (⏳ {model} limit→next)", end="", flush=True)
                time.sleep(2)
                continue
            print(f"\n⚠️  Hata ({model}): {e}")
            continue
    return None


# ═══════════════════════ HAVUZ ════════════════════════
def load_pool():
    if os.path.exists(POOL_JSON):
        try:
            with open(POOL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            print("⚠️  Havuz bozuk, sıfırdan başlanıyor.")
    return {}


def save_pool(pool):
    tmp = POOL_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
    os.replace(tmp, POOL_JSON)


# ═══════════════════════ ANA AKIŞ ═════════════════════
def run(max_to_process=None, save_every=SAVE_EVERY):
    print("=" * 70)
    print("🎬 NEDEN İZLEMELİSİN? ÜRETİCİ  |  movies_dataset.json → havuz")
    print("=" * 70)

    if not os.path.exists(MOVIES_JSON):
        print(f"❌ {MOVIES_JSON} bulunamadı!")
        return

    # Kaynak filmleri yükle
    with open(MOVIES_JSON, "r", encoding="utf-8") as f:
        all_movies = json.load(f)
    print(f"📂 Kaynak film sayısı : {len(all_movies):,}")

    # Mevcut havuzu yükle
    pool = load_pool()
    print(f"💾 Havuzdaki kayıt   : {len(pool):,}")

    # Eksik olanları belirle
    todo = [m for m in all_movies if str(m["id"]) not in pool]
    print(f"🎯 İşlenecek film    : {len(todo):,}")
    print("=" * 70)

    if not AI_AVAILABLE:
        print("❌ OpenAI/Groq client kurulu değil, çıkılıyor.")
        print("   → pip install openai python-dotenv")
        return

    if not todo:
        print("🎉 Tüm filmler hazır! Havuz tamamlandı.")
        return

    limit  = max_to_process or len(todo)
    ok = fail = 0
    start  = time.time()

    for i, film in enumerate(todo[:limit]):
        fid    = str(film["id"])
        title  = film.get("title") or film.get("original_title") or f"Film#{fid}"
        year   = str(film.get("release_date", ""))[:4] or None
        genres = film.get("genres", [])

        ytxt = f" ({year})" if year else ""
        print(f"[{i+1}/{limit}] 🎬 {title[:45]}{ytxt} ...", end="", flush=True)

        maddeler = generate_neden_izle(title, year, genres)

        if maddeler:
            pool[fid] = {
                "id"      : film["id"],
                "title"   : title,
                "maddeler": maddeler,
                "ts"      : int(time.time()),
            }
            ok += 1
            print(f" ✅")
            # İlk maddeyi önizleme olarak göster
            print(f"    💬 {maddeler[0][:70]}")
        else:
            fail += 1
            print(" ❌ BAŞARISIZ")

        if (i + 1) % save_every == 0:
            save_pool(pool)
            el   = time.time() - start
            rate = (i + 1) / el if el else 0
            kalan = (limit - i - 1) / rate / 60 if rate else 0
            print(f"    💾 Kaydedildi | {rate:.2f} film/sn | kalan ~{kalan:.1f} dk")

        time.sleep(SLEEP_SEC)

    save_pool(pool)
    el = round(time.time() - start, 1)
    print("=" * 70)
    print(f"🎉 BİTTİ ({el}s)  |  Başarılı: {ok}  |  Hata: {fail}  |  Havuz: {len(pool):,}")
    print(f"📁 Çıktı: {POOL_JSON}")
    print("=" * 70)


# ═══════════════════════ ENTRY ════════════════════════
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Film Neden İzlemelisin? Üretici")
    p.add_argument("--limit",      type=int, default=None,
                   help="Kaç film işlensin (varsayılan: hepsi)")
    p.add_argument("--save-every", type=int, default=SAVE_EVERY,
                   help=f"Kaç filmde bir kaydet (varsayılan: {SAVE_EVERY})")
    a = p.parse_args()
    run(max_to_process=a.limit, save_every=a.save_every)
