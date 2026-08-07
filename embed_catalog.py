import os
import sys
import json
import sqlite3
import hashlib
from openai import OpenAI

if os.path.exists('.env'):
    try:
        for line in open('.env', encoding='utf-8'):
            if line.strip() and not line.startswith('#') and '=' in line:
                k, v = line.strip().split('=', 1)
                os.environ[k] = v.strip()
    except Exception:
        pass

sys.stdout.reconfigure(encoding='utf-8')

EMBEDDING_MODEL = 'text-embedding-3-small'
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

try:
    from db_paths import series_db_path, movies_db_path, EMBEDDINGS_DB_PATH as _EMB
    SERIES_DB_PATH = series_db_path()
    MOVIES_DB_PATH = movies_db_path()
    EMBEDDINGS_DB_PATH = _EMB if os.path.exists(_EMB) else 'embeddings.db'
except Exception:
    SERIES_DB_PATH = 'katalog.db'
    MOVIES_DB_PATH = 'katalog.db'
    EMBEDDINGS_DB_PATH = 'embeddings.db'

def get_embeddings_db():
    conn = sqlite3.connect(EMBEDDINGS_DB_PATH, timeout=30.0)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS item_embeddings (
            item_id TEXT PRIMARY KEY,
            media_type TEXT NOT NULL,
            item_title TEXT,
            text_hash TEXT,
            embedding_json TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_media_type ON item_embeddings(media_type)')
    conn.commit()
    return conn

def compute_md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()

def generate_pseudo_vector(text, dim=128):
    vector = [0.0] * dim
    words = text.lower().split()
    for w in words:
        h = 0
        for ch in w:
            h = (h * 31 + ord(ch)) % dim
        vector[abs(h)] += 1.0
    norm = sum(v * v for v in vector) ** 0.5 or 1.0
    return [v / norm for v in vector]

def process_table(db_path, table_name, media_type, text_cols, id_col, title_col, client, missing_only=False):
    if not os.path.exists(db_path):
        print(f"[!] {db_path} bulunamadı, atlanıyor.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table_name}")
    rows = c.fetchall()
    conn.close()

    print(f"\n📦 [{media_type}] {db_path} -> {table_name} ({len(rows)} kayıt okunuyor)...")

    emb_conn = get_embeddings_db()
    emb_c = emb_conn.cursor()

    pending_items = []
    skipped = 0

    for r in rows:
        item_dict = dict(r)
        item_id = f"{media_type.lower()}_{item_dict.get(id_col)}"
        item_title = item_dict.get(title_col) or 'İsimsiz'
        
        parts = []
        for col in text_cols:
            val = item_dict.get(col)
            if val:
                parts.append(str(val).strip())
        composite_text = " ".join(parts)
        text_hash = compute_md5(composite_text)

        emb_c.execute("SELECT text_hash FROM item_embeddings WHERE item_id = ?", (item_id,))
        existing = emb_c.fetchone()
        if existing:
            if missing_only or existing[0] == text_hash:
                skipped += 1
                continue

        pending_items.append({
            'item_id': item_id,
            'media_type': media_type,
            'item_title': item_title,
            'text_hash': text_hash,
            'composite_text': composite_text
        })

    mode = 'yalnızca eksik' if missing_only else 'eksik + hash değişen'
    print(f"  - Atlanan (güncel/mevcut) kayıt sayısı: {skipped}")
    print(f"  - Vektörleştirilecek kayıt sayısı ({mode}): {len(pending_items)}")

    if not pending_items:
        print(f"  [✓] {media_type} kataloğu zaten 100% güncel!")
        emb_conn.close()
        return

    BATCH_SIZE = 100
    processed = 0

    for i in range(0, len(pending_items), BATCH_SIZE):
        batch = pending_items[i:i + BATCH_SIZE]
        print(f"  -> İşleniyor: {i + 1} - {i + len(batch)} / {len(pending_items)}...")

        if client and OPENAI_API_KEY:
            try:
                inputs = [item['composite_text'][:8000] for item in batch]
                res = client.embeddings.create(model=EMBEDDING_MODEL, input=inputs)
                for idx, emb_data in enumerate(res.data):
                    item = batch[idx]
                    vector_json = json.dumps(emb_data.embedding)
                    emb_c.execute('''
                        INSERT INTO item_embeddings (item_id, media_type, item_title, text_hash, embedding_json)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(item_id) DO UPDATE SET
                          item_title = excluded.item_title,
                          text_hash = excluded.text_hash,
                          embedding_json = excluded.embedding_json,
                          updated_at = CURRENT_TIMESTAMP
                    ''', (item['item_id'], item['media_type'], item['item_title'], item['text_hash'], vector_json))
                emb_conn.commit()
                processed += len(batch)
            except Exception as e:
                print(f"  [!] OpenAI API Embeddings hatası: {e}")
                break
        else:
            for item in batch:
                vector_json = json.dumps(generate_pseudo_vector(item['composite_text']))
                emb_c.execute('''
                    INSERT INTO item_embeddings (item_id, media_type, item_title, text_hash, embedding_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(item_id) DO UPDATE SET
                      item_title = excluded.item_title,
                      text_hash = excluded.text_hash,
                      embedding_json = excluded.embedding_json,
                      updated_at = CURRENT_TIMESTAMP
                ''', (item['item_id'], item['media_type'], item['item_title'], item['text_hash'], vector_json))
            emb_conn.commit()
            processed += len(batch)

    emb_conn.close()
    print(f"  [✓] {media_type} kataloğu tamamlandı! Toplam eklenen/güncellenen: {processed}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='DizimiBul katalog embedding pipeline')
    parser.add_argument(
        '--missing-only',
        action='store_true',
        help='Sadece embeddings.db içinde hiç olmayan kayıtları üret (hash güncellemesi yapma)'
    )
    args = parser.parse_args()
    missing_only = bool(args.missing_only)

    print("==========================================================================")
    print("🚀 DIZIMIBUL SEMANTIC CATALOG EMBEDDING PIPELINE (PYTHON)")
    if missing_only:
        print("Mode: MISSING-ONLY (yalnızca eksik vektörler)")
    print("==========================================================================")

    client = None
    if OPENAI_API_KEY and OPENAI_API_KEY != 'your_openai_api_key_here':
        client = OpenAI(api_key=OPENAI_API_KEY)
        print(f"[+] OpenAI API Key aktif. Model: {EMBEDDING_MODEL}")
    else:
        print(f"[!] OPENAI_API_KEY ortam değişkeni tanımlı değil. Çevrimdışı yerel vektör sentezleyici çalışacak.")

    # Diziler
    process_table(
        db_path=SERIES_DB_PATH,
        table_name='diziler',
        media_type='SERIES',
        text_cols=['isim', 'ozet', 'tur', 'anahtar_kelimeler', 'neden_izlemeli', 'oyuncular_gercek', 'efsanevi_ikili', 'platformlar'],
        id_col='id',
        title_col='isim',
        client=client,
        missing_only=missing_only,
    )

    # Filmler
    process_table(
        db_path=MOVIES_DB_PATH,
        table_name='filmler',
        media_type='MOVIES',
        text_cols=['isim', 'orijinal_isim', 'ozet', 'turler', 'anahtar_kelimeler', 'neden_izlemeli', 'yonetmen', 'oyuncular', 'platformlar'],
        id_col='id',
        title_col='isim',
        client=client,
        missing_only=missing_only,
    )

    print("\n==========================================================================")
    print("🎉 KATALOG EMBEDDING İŞLEMİ EKSİKSİZ TAMAMLATILDI!")
    print("==========================================================================")

if __name__ == '__main__':
    main()
