# -*- coding: utf-8 -*-
"""
film_neden_izle_uretici.py
--------------------------
Eksik / jenerik film "neden izlemeli" maddelerini Groq ile üretir.

AKİŞ (varsayılan):
  1) Sadece JSON havuza yazar  →  json_data/film_neden_izle_havuzu.json
  2) Havuzda olan ID'leri ATLAR (kaldığı yerden devam, çakışma yok)
  3) DB aktarımı ayrı adım

Çalıştır:
    # Kaldığı yerden devam (JSON only) — jenerik/kopyaları da doldur
    python film_neden_izle_uretici.py --jenerik

    # Sadece boşlar
    python film_neden_izle_uretici.py

    python film_neden_izle_uretici.py --jenerik --limit 50
    python film_neden_izle_uretici.py --dry-run --jenerik --limit 5

    # Bitince JSON → DB (+ isteğe export)
    python film_neden_izle_uretici.py --db-aktar
    python film_neden_izle_uretici.py --db-aktar --export

Gereksinim: .env içinde GROQ_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()
load_dotenv(os.path.join("backend", ".env"))

API_KEY = os.getenv("GROQ_API_KEY", "").strip()
DB_FILM = "katalog.db"
POOL_JSON = os.path.join("json_data", "film_neden_izle_havuzu.json")
LEGACY_POOL_JSON = os.path.join("json_data", "neden_izle_havuzu.json")
SAVE_EVERY = 10
SLEEP_SEC = 0.45

MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]

GENERIC_SNIPPETS = [
    "sinematik dokusu",
    "izleyicide bıraktığı kalıcı etki",
    "güçlü karakter gelişimi, dengeli oyuncu",
    "görsel efekt tasarımı, müzik uyumu",
    "eğlenceli seyir zevki ve tekrar izlendiğinde",
    "başrol oyuncularının usta işi performansları",
    "adrenalin seviyesi yüksek sekansları",
    "yüksek tempolu sahneleri ve sürükleyici",
    "ufuk açıcı evren tasarımı",
    "görsel kalitesi, tempolu yapısı ve akıcı hikaye",
    "derinlikli kurgusu ve yüksek görsel kalitesiyle",
    "yüksek görsel kalite, sürükleyici atmosfer",
]

SYSTEM_PROMPT = """\
Sen uzman bir film editörüsün. Sana bir film verilecek; o filme özgü, somut, merak uyandıran
tam 3 maddelik "Neden İzlemelisin?" metni yaz.

KESİN KURALLAR:
1. Tam 3 madde — ne eksik ne fazla.
2. Her madde tek cümle, 10–18 kelime arası.
3. Her maddenin konusu farklı olsun:
   • 1. madde → filmin türüne / senaryosuna özgü çengel (korkuysa gerilim dili, komediyse mizah dinamiği vb.)
   • 2. madde → oyuncu / yönetmen / görsel-müzikal kalite gibi SOMUT bir unsur (isim varsa kullan)
   • 3. madde → izleyicide bıraktığı özgün his veya tekrar izleme sebebi
4. Çıktı formatı kesinlikle şöyle olmalı, başka HİÇBİR şey yazma:
   MADDE1: <metin>
   MADDE2: <metin>
   MADDE3: <metin>

YASAK (asla yazma):
- "güzel atmosfer", "iyi oyunculuk", "güçlü hikaye", "ilginç bir hikaye"
- "kaçırılmamalı", "mutlaka izleyin", "izleyiciyi etkiler", "izleyiciyi heyecanlandırır"
- "sinematik dokusu", "kalıcı etki", "usta işi performans", "aksiyon dolu sahneler"
- Her filme uyacak jenerik cümleler ve 6 kelimeden kısa maddeler
- Spoiler (final, ölüm, büyük twist açıklama)

YAP:
- Özet ve türe bakarak o filme özel detay yaz (mekan, meslek, ilişki dinamiği, dönem)
- Korku → korku/gerilim dili; komedi → ilişki/mizah; suç → soruşturma/ahlak gerilimi
- Yönetmen veya oyuncu adı varsa kullan; yoksa uydurma
Türkçe yaz. Reklam dili kullanma.
"""

_MADDE_RE = re.compile(r"MADDE\d\s*[:：]\s*(.+)", re.IGNORECASE)


def get_client():
    if not API_KEY:
        return None
    try:
        from openai import OpenAI
        return OpenAI(base_url="https://api.groq.com/openai/v1", api_key=API_KEY)
    except ImportError:
        print("❌ pip install openai python-dotenv")
        return None


def parse_maddeler(raw: str):
    if not raw:
        return None
    matches = _MADDE_RE.findall(raw)
    maddeler = [m.strip().strip('"').strip("'") for m in matches if m.strip()]
    if len(maddeler) >= 3:
        return maddeler[:3]
    num_matches = re.findall(r"(?:^|\n)\s*\d[.)\-]\s*(.+)", raw)
    maddeler = [m.strip() for m in num_matches if m.strip()]
    if len(maddeler) >= 3:
        return maddeler[:3]
    return None


def is_empty_why(raw) -> bool:
    if raw is None:
        return True
    s = str(raw).strip()
    if not s or s in ("[]", "null", "None", "Bilinmiyor"):
        return True
    if "bilinmiyor" in s.lower():
        return True
    try:
        arr = json.loads(s) if s.startswith("[") else []
        if not isinstance(arr, list) or len(arr) == 0:
            return True
        if all(not str(x).strip() for x in arr):
            return True
    except Exception:
        pass
    return False


def is_generic_why(raw) -> bool:
    if is_empty_why(raw):
        return True
    s = str(raw).lower()
    return any(g in s for g in GENERIC_SNIPPETS)


def pool_entry_ok(entry) -> bool:
    """Havuz kaydı geçerli 3 madde mi?"""
    if not isinstance(entry, dict):
        return False
    maddeler = entry.get("maddeler")
    if not isinstance(maddeler, list) or len(maddeler) < 3:
        return False
    if is_generic_why(json.dumps(maddeler, ensure_ascii=False)):
        return False
    return True


def build_user_prompt(row: dict) -> str:
    parts = [
        f"Film: {row['isim']}",
        f"Yıl: {row.get('yil') or '?'}",
        f"Türler: {row.get('tur') or '?'}",
        f"Platform: {row.get('platform') or '?'}",
        f"Puan: {row.get('puan') or '?'}",
    ]
    if row.get("yonetmen"):
        parts.append(f"Yönetmen: {row['yonetmen']}")
    if row.get("oyuncular"):
        parts.append(f"Oyuncular: {row['oyuncular'][:180]}")
    if row.get("ozet"):
        parts.append(f"Özet: {row['ozet'][:420]}")
    return "\n".join(parts)


def generate_neden(client, row: dict):
    user_prompt = build_user_prompt(row)
    for model in MODELS:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.9,
                max_tokens=260,
            )
            raw = (resp.choices[0].message.content or "").strip()
            parsed = parse_maddeler(raw)
            if parsed:
                joined = " ".join(parsed).lower()
                banned = (
                    "güzel atmosfer", "iyi oyunculuk", "kaçırılmamalı",
                    "güçlü bir hikaye", "izleyiciyi heyecanlandırır",
                )
                if any(b in joined for b in banned):
                    print(f" (⚠️ jenerik→retry {model})", end="", flush=True)
                    continue
                return parsed, model
            print(f" (⚠️ parse fail {model})", end="", flush=True)
        except Exception as e:
            err = str(e).lower()
            if "429" in err or "rate_limit" in err:
                print(f" (⏳ rate-limit {model})", end="", flush=True)
                time.sleep(3)
                continue
            print(f"\n   ⚠️ {model}: {e}")
            continue
    return None, None


def load_pool():
    os.makedirs(os.path.dirname(POOL_JSON) or ".", exist_ok=True)
    if os.path.exists(POOL_JSON):
        try:
            with open(POOL_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_pool(pool):
    os.makedirs(os.path.dirname(POOL_JSON) or ".", exist_ok=True)
    tmp = POOL_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
    os.replace(tmp, POOL_JSON)


def seed_pool_from_legacy(pool: dict) -> int:
    """Eski tmdb_id anahtarlı neden_izle_havuzu.json kayıtlarını DB id ile havuza aktar."""
    if not os.path.exists(LEGACY_POOL_JSON):
        return 0
    try:
        with open(LEGACY_POOL_JSON, "r", encoding="utf-8") as f:
            legacy = json.load(f)
    except Exception:
        return 0
    if not isinstance(legacy, dict) or not legacy:
        return 0

    conn = sqlite3.connect(DB_FILM)
    cur = conn.cursor()
    cur.execute("SELECT id, tmdb_id, isim FROM filmler")
    rows = cur.fetchall()
    conn.close()

    added = 0
    for db_id, tmdb_id, isim in rows:
        pid = str(db_id)
        if pool_entry_ok(pool.get(pid)):
            continue
        entry = None
        if tmdb_id is not None and str(tmdb_id) in legacy:
            entry = legacy[str(tmdb_id)]
        elif pid in legacy:
            entry = legacy[pid]
        if not pool_entry_ok(entry):
            continue
        pool[pid] = {
            "id": db_id,
            "tmdb_id": tmdb_id,
            "title": isim or entry.get("title") or "",
            "maddeler": entry["maddeler"][:3],
            "model": entry.get("model") or "legacy",
            "ts": entry.get("ts") or int(time.time()),
        }
        added += 1
    return added


def load_todo(include_generic: bool, pool: dict, limit=None):
    """Havuzda geçerli kaydı olan ID'ler ATLANIR (çakışma / baştan yazma yok)."""
    conn = sqlite3.connect(DB_FILM)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, tmdb_id, isim, vizyon_tarihi, turler, ozet, puan,
               yonetmen, oyuncular, platformlar, neden_izlemeli
        FROM filmler
        ORDER BY id
        """
    )
    rows = []
    skipped_pool = 0
    for r in cur.fetchall():
        pid = str(r["id"])
        if pool_entry_ok(pool.get(pid)):
            skipped_pool += 1
            continue

        why = r["neden_izlemeli"]
        needs = is_empty_why(why) or (include_generic and is_generic_why(why))
        if not needs:
            continue

        rows.append({
            "id": r["id"],
            "tmdb_id": r["tmdb_id"],
            "isim": r["isim"] or "",
            "yil": (r["vizyon_tarihi"] or "")[:4],
            "tur": r["turler"] or "",
            "ozet": r["ozet"] or "",
            "puan": r["puan"],
            "yonetmen": r["yonetmen"] or "",
            "platform": r["platformlar"] or "",
            "oyuncular": r["oyuncular"] or "",
            "neden_izlemeli": why,
        })
    conn.close()
    if limit:
        rows = rows[:limit]
    return rows, skipped_pool


def apply_pool_to_db(export=False):
    pool = load_pool()
    if not pool:
        print("❌ Havuz boş, aktarılacak bir şey yok.")
        return

    conn = sqlite3.connect(DB_FILM, timeout=120)
    updated = skipped = 0
    for pid, entry in pool.items():
        if not pool_entry_ok(entry):
            skipped += 1
            continue
        maddeler = entry["maddeler"][:3]
        conn.execute(
            "UPDATE filmler SET neden_izlemeli = ? WHERE id = ?",
            (json.dumps(maddeler, ensure_ascii=False), int(pid) if str(pid).isdigit() else pid),
        )
        updated += 1
    conn.commit()
    conn.close()

    print(f"✅ DB aktarıldı: {updated} film (atlanan geçersiz: {skipped})")
    print(f"📁 Kaynak: {POOL_JSON}")

    if export:
        print("💾 data_store.js export...")
        subprocess.run([sys.executable, "export_data_store.py"], check=False)


def run_generate(args):
    print("=" * 70)
    print("🎬 FİLM NEDEN İZLEMELİSİN?  |  Groq → JSON (kaldığı yerden)")
    print("=" * 70)

    if not API_KEY:
        print("❌ GROQ_API_KEY bulunamadı (.env)")
        return

    client = get_client()
    if not client:
        return

    pool = load_pool()
    if args.seed_legacy:
        seeded = seed_pool_from_legacy(pool)
        if seeded and not args.dry_run:
            save_pool(pool)
        print(f"📥 Eski havuzdan seed : {seeded}")

    print(f"💾 Havuzda hazır  : {sum(1 for v in pool.values() if pool_entry_ok(v))} film")

    todo, skipped_pool = load_todo(
        include_generic=args.jenerik,
        pool=pool,
        limit=args.limit,
    )
    print(f"⏩ Havuzda atlanan : {skipped_pool}")
    print(f"🎯 Bu tur işlenecek: {len(todo)}")
    print(f"   Mod             : {'boş + jenerik' if args.jenerik else 'sadece boş/null'}")
    print(f"   Yazma           : {'DRY-RUN' if args.dry_run else 'sadece JSON (DB yok)'}")
    print("=" * 70)

    if not todo:
        print("🎉 Yeni iş yok — havuzdaki kayıtlar zaten hazır.")
        print("   DB'ye aktarmak için: python film_neden_izle_uretici.py --db-aktar --export")
        return

    ok = fail = 0
    start = time.time()

    for i, row in enumerate(todo):
        title = row["isim"]
        pid = str(row["id"])
        print(f"[{i+1}/{len(todo)}] 🎬 {title[:48]} ...", end="", flush=True)

        maddeler, model = generate_neden(client, row)

        if maddeler:
            if not args.dry_run:
                pool[pid] = {
                    "id": row["id"],
                    "tmdb_id": row.get("tmdb_id"),
                    "title": title,
                    "maddeler": maddeler,
                    "model": model,
                    "ts": int(time.time()),
                }
            ok += 1
            print(" ✅")
            print(f"    💬 {maddeler[0][:75]}")
        else:
            fail += 1
            print(" ❌")

        if not args.dry_run and ((i + 1) % args.save_every == 0):
            save_pool(pool)
            el = time.time() - start
            rate = (i + 1) / el if el else 0
            kalan = (len(todo) - i - 1) / rate / 60 if rate else 0
            print(f"    💾 JSON ara kayıt | havuz={len(pool)} | {rate:.2f}/sn | kalan ~{kalan:.1f} dk")

        time.sleep(SLEEP_SEC)

    if not args.dry_run:
        save_pool(pool)

    el = round(time.time() - start, 1)
    print("=" * 70)
    print(f"🎉 BİTTİ ({el}s)  yeni={ok}  hata={fail}  havuz_toplam={len(pool)}")
    print(f"📁 JSON: {POOL_JSON}")
    print("➡️  DB aktarımı: python film_neden_izle_uretici.py --db-aktar --export")
    print(f"🕒 {datetime.now().isoformat(timespec='seconds')}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Film Neden İzlemelisin? Groq → JSON → DB")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--save-every", type=int, default=SAVE_EVERY)
    parser.add_argument("--jenerik", action="store_true",
                        help="Boşlara ek olarak kopya/jenerik maddeleri de üret")
    parser.add_argument("--dry-run", action="store_true", help="JSON/DB yazma")
    parser.add_argument("--seed-legacy", action="store_true",
                        help="Eski json_data/neden_izle_havuzu.json kayıtlarını yeni havuza aktar")
    parser.add_argument("--db-aktar", action="store_true",
                        help="Havuz JSON'unu veritabanına aktar (üretim yapmaz)")
    parser.add_argument("--export", action="store_true",
                        help="--db-aktar ile birlikte data_store.js güncelle")
    args = parser.parse_args()

    if args.db_aktar:
        print("=" * 70)
        print("📦 JSON HAVUZ → VERİTABANI AKTARIMI (FİLM)")
        print("=" * 70)
        apply_pool_to_db(export=args.export)
        return

    run_generate(args)


if __name__ == "__main__":
    main()
