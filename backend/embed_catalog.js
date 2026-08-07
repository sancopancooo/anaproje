import crypto from 'crypto';
import OpenAI from 'openai';
import { config } from './config.js';
import { getSeriesDb, getMoviesDb, getEmbeddingsDb } from './db.js';

function computeMd5(text) {
  return crypto.createHash('md5').update(text).digest('hex');
}

function constructCompositeText(row, textCols) {
  const parts = [];
  textCols.forEach(col => {
    const val = row[col];
    if (val) {
      if (typeof val === 'string') parts.push(val.trim());
      else parts.push(String(val));
    }
  });
  return parts.join(' ');
}

async function processMediaType(typeConfig, db, openai) {
  console.log(`\n📦 [${typeConfig.key}] Verileri okunuyor ve işleniyor...`);
  const rows = db.prepare(`SELECT * FROM ${typeConfig.tableName}`).all();
  console.log(`[+] ${typeConfig.key} toplam kayıt sayısı: ${rows.length}`);

  const embDb = getEmbeddingsDb();
  const selectStmt = embDb.prepare(`SELECT text_hash FROM item_embeddings WHERE item_id = ?`);
  const insertStmt = embDb.prepare(`
    INSERT INTO item_embeddings (item_id, media_type, item_title, text_hash, embedding_json, updated_at)
    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(item_id) DO UPDATE SET
      item_title = excluded.item_title,
      text_hash = excluded.text_hash,
      embedding_json = excluded.embedding_json,
      updated_at = CURRENT_TIMESTAMP
  `);

  const pendingBatch = [];
  let skippedCount = 0;
  let processedCount = 0;

  for (const row of rows) {
    const itemId = `${typeConfig.key.toLowerCase()}_${row[typeConfig.idColumn]}`;
    const compositeText = constructCompositeText(row, typeConfig.textColumns);
    const hash = computeMd5(compositeText);
    const itemTitle = row[typeConfig.titleColumn] || 'İsimsiz';

    const existing = selectStmt.get(itemId);
    if (existing && existing.text_hash === hash) {
      skippedCount++;
      continue;
    }

    pendingBatch.push({ itemId, itemTitle, compositeText, hash });
  }

  console.log(`[i] Değişmeyen/atlanan kayıt sayısı: ${skippedCount}`);
  console.log(`[i] Vektörleştirilecek yeni/güncellenen kayıt sayısı: ${pendingBatch.length}`);

  if (pendingBatch.length === 0) {
    console.log(`[✓] ${typeConfig.key} için tüm kayıtlar zaten güncel!`);
    return;
  }

  // Process in batches of 100
  const BATCH_SIZE = 100;
  for (let i = 0; i < pendingBatch.length; i += BATCH_SIZE) {
    const chunk = pendingBatch.slice(i, i + BATCH_SIZE);
    console.log(`  -> Batch işleniyor: ${i + 1} - ${i + chunk.length} / ${pendingBatch.length}...`);

    if (openai) {
      try {
        const inputs = chunk.map(item => item.compositeText.slice(0, 8000));
        const res = await openai.embeddings.create({
          model: config.embeddingModel,
          input: inputs
        });

        const transaction = embDb.transaction(() => {
          res.data.forEach((embData, index) => {
            const item = chunk[index];
            insertStmt.run(item.itemId, typeConfig.key, item.itemTitle, item.hash, JSON.stringify(embData.embedding));
          });
        });
        transaction();
        processedCount += chunk.length;
      } catch (err) {
        console.error(`  [!] OpenAI API Embeddings hatası:`, err.message);
        break;
      }
    } else {
      // Deterministic Local Vector Synthesizer (Fallback when API key is pending)
      const transaction = embDb.transaction(() => {
        chunk.forEach(item => {
          const pseudoVector = generatePseudoVector(item.compositeText);
          insertStmt.run(item.itemId, typeConfig.key, item.itemTitle, item.hash, JSON.stringify(pseudoVector));
        });
      });
      transaction();
      processedCount += chunk.length;
    }
  }

  console.log(`[✓] ${typeConfig.key} tamamlandı! Toplam işlenen: ${processedCount}`);
}

function generatePseudoVector(text) {
  // Deterministic 128-float feature vector generator for offline testing
  const dim = 128;
  const vector = new Array(dim).fill(0);
  const words = text.toLowerCase().split(/\s+/);
  words.forEach(w => {
    let hash = 0;
    for (let i = 0; i < w.length; i++) {
      hash = (hash * 31 + w.charCodeAt(i)) % dim;
    }
    vector[Math.abs(hash)] += 1.0;
  });
  let norm = 0;
  for (let i = 0; i < dim; i++) norm += vector[i] * vector[i];
  norm = Math.sqrt(norm) || 1;
  return vector.map(v => v / norm);
}

async function runCatalogEmbedding() {
  console.log("==========================================================================");
  console.log("🚀 DIZIMIBUL SEMANTIC CATALOG EMBEDDING PIPELINE");
  console.log("==========================================================================");

  let openai = null;
  if (config.openaiApiKey && config.openaiApiKey !== 'your_openai_api_key_here') {
    openai = new OpenAI({ apiKey: config.openaiApiKey });
    console.log(`[+] OpenAI API Key tespit edildi. Model: ${config.embeddingModel}`);
  } else {
    console.log(`[!] OPENAI_API_KEY henüz tanımlanmadı. Çevrimdışı test yerel vektör sentezleyicisi kullanılıyor.`);
  }

  const seriesDb = getSeriesDb();
  await processMediaType(config.mediaTypes.SERIES, seriesDb, openai);

  const moviesDb = getMoviesDb();
  await processMediaType(config.mediaTypes.MOVIES, moviesDb, openai);

  console.log("\n==========================================================================");
  console.log("🎉 KATALOG EMBEDDING İŞLEMİ TAMAMLATILDI!");
  console.log("==========================================================================");
}

runCatalogEmbedding().catch(err => {
  console.error("Fatal Embedding Error:", err);
  process.exit(1);
});
