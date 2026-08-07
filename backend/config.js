import path from 'path';
import dotenv from 'dotenv';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '.env') });

export const config = {
  port: process.env.PORT || 4000,
  openaiApiKey: process.env.OPENAI_API_KEY || '',
  minSimilarityThreshold: parseFloat(process.env.MIN_SIMILARITY_THRESHOLD || '0.35'),
  embeddingModel: 'text-embedding-3-small',
  
  databases: {
    // Tek katalog: diziler + filmler aynı SQLite dosyasında
    seriesDbPath: path.resolve(__dirname, process.env.SERIES_DB_PATH || process.env.CATALOG_DB_PATH || '../katalog.db'),
    moviesDbPath: path.resolve(__dirname, process.env.MOVIES_DB_PATH || process.env.CATALOG_DB_PATH || '../katalog.db'),
    embeddingsDbPath: path.resolve(__dirname, process.env.EMBEDDINGS_DB_PATH || './embeddings.db')
  },

  mediaTypes: {
    MOVIES: {
      key: 'MOVIES',
      dbType: 'moviesDbPath',
      tableName: 'filmler',
      idColumn: 'id',
      titleColumn: 'isim',
      textColumns: ['isim', 'orijinal_isim', 'ozet', 'turler', 'anahtar_kelimeler', 'neden_izlemeli', 'yonetmen', 'oyuncular', 'platformlar']
    },
    SERIES: {
      key: 'SERIES',
      dbType: 'seriesDbPath',
      tableName: 'diziler',
      idColumn: 'id',
      titleColumn: 'isim',
      textColumns: ['isim', 'ozet', 'tur', 'anahtar_kelimeler', 'neden_izlemeli', 'oyuncular_gercek', 'efsanevi_ikili', 'platformlar']
    }
  }
};
