import Database from 'better-sqlite3';
import { config } from './config.js';

let seriesDbInstance = null;
let moviesDbInstance = null;
let embeddingsDbInstance = null;

export function getSeriesDb() {
  if (!seriesDbInstance) {
    // Aynı dosya ise movies ile tek bağlantı paylaş
    if (moviesDbInstance && config.databases.seriesDbPath === config.databases.moviesDbPath) {
      seriesDbInstance = moviesDbInstance;
    } else {
      seriesDbInstance = new Database(config.databases.seriesDbPath, { readonly: true });
    }
  }
  return seriesDbInstance;
}

export function getMoviesDb() {
  if (!moviesDbInstance) {
    if (seriesDbInstance && config.databases.seriesDbPath === config.databases.moviesDbPath) {
      moviesDbInstance = seriesDbInstance;
    } else {
      moviesDbInstance = new Database(config.databases.moviesDbPath, { readonly: true });
    }
  }
  return moviesDbInstance;
}

export function getEmbeddingsDb() {
  if (!embeddingsDbInstance) {
    embeddingsDbInstance = new Database(config.databases.embeddingsDbPath);
    embeddingsDbInstance.pragma('journal_mode = WAL');
    
    // Initialize item_embeddings table
    embeddingsDbInstance.exec(`
      CREATE TABLE IF NOT EXISTS item_embeddings (
        item_id TEXT PRIMARY KEY,
        media_type TEXT NOT NULL,
        item_title TEXT,
        text_hash TEXT,
        vector_blob BLOB,
        embedding_json TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );
      CREATE INDEX IF NOT EXISTS idx_media_type ON item_embeddings(media_type);

      CREATE TABLE IF NOT EXISTS content_error_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL,
        item_title TEXT,
        media_type TEXT NOT NULL,
        fields_json TEXT NOT NULL,
        note TEXT,
        username TEXT,
        status TEXT DEFAULT 'open',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );
      CREATE INDEX IF NOT EXISTS idx_error_reports_item ON content_error_reports(item_id);
      CREATE INDEX IF NOT EXISTS idx_error_reports_status ON content_error_reports(status);
      CREATE INDEX IF NOT EXISTS idx_error_reports_created ON content_error_reports(created_at);

      CREATE TABLE IF NOT EXISTS user_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        message TEXT NOT NULL,
        media_type TEXT,
        status TEXT DEFAULT 'open',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
      );
      CREATE INDEX IF NOT EXISTS idx_user_feedback_created ON user_feedback(created_at);
      CREATE INDEX IF NOT EXISTS idx_user_feedback_status ON user_feedback(status);
    `);
  }
  return embeddingsDbInstance;
}

export function cosineSimilarity(vecA, vecB) {
  let dot = 0.0;
  let normA = 0.0;
  let normB = 0.0;
  for (let i = 0; i < vecA.length; i++) {
    dot += vecA[i] * vecB[i];
    normA += vecA[i] * vecA[i];
    normB += vecB[i] * vecB[i];
  }
  if (normA === 0 || normB === 0) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}
