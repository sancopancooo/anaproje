import express from 'express';
import cors from 'cors';
import OpenAI from 'openai';
import { config } from './config.js';
import { getSeriesDb, getMoviesDb, getEmbeddingsDb, cosineSimilarity } from './db.js';
import {
  detectThemes,
  expandQueryForEmbedding,
  lexicalScore,
  passesHardGate,
  tokenizeQuery,
  extractRequiredGenres,
  itemMatchesRequiredGenres,
  HYBRID_VECTOR_WEIGHT,
  HYBRID_LEXICAL_WEIGHT,
  MIN_HYBRID_SCORE,
  RELATIVE_GAP_RATIO,
  SEARCH_SAFETY_CAP,
  UNTHEMED_SEARCH_CAP
} from './theme_lexicon.js';

const app = express();
app.use(cors());
app.use(express.json());

let openai = null;
if (config.openaiApiKey && config.openaiApiKey !== 'your_openai_api_key_here') {
  openai = new OpenAI({ apiKey: config.openaiApiKey });
  console.log(`[+] OpenAI Client aktif. Model: ${config.embeddingModel}`);
}

async function getQueryEmbedding(text) {
  if (openai) {
    try {
      const res = await openai.embeddings.create({
        model: config.embeddingModel,
        input: text.slice(0, 8000)
      });
      return res.data[0].embedding;
    } catch (err) {
      console.error("OpenAI Query Embedding Hatası:", err.message);
    }
  }
  // Fallback local vector synthesizer
  const dim = 128;
  const vector = new Array(dim).fill(0);
  const words = text.toLowerCase().split(/\s+/);
  words.forEach(w => {
    let hash = 0;
    for (let i = 0; i < w.length; i++) hash = (hash * 31 + w.charCodeAt(i)) % dim;
    vector[Math.abs(hash)] += 1.0;
  });
  let norm = 0;
  for (let i = 0; i < dim; i++) norm += vector[i] * vector[i];
  norm = Math.sqrt(norm) || 1;
  return vector.map(v => v / norm);
}

function extractRawId(itemId) {
  if (!itemId) return null;
  const m = String(itemId).match(/^(?:series|movies)_(\d+)$/i);
  return m ? m[1] : String(itemId).replace(/^(?:series|movies)_/i, '');
}

/**
 * Katalog metadata (özet / tür / anahtar kelimeler) — hard gate & lexical için
 */
function getItemSearchMeta(itemId, mediaType) {
  const rawId = extractRawId(itemId);
  try {
    if (mediaType === 'SERIES') {
      const db = getSeriesDb();
      const row = db.prepare(
        'SELECT isim, ozet, tur, anahtar_kelimeler FROM diziler WHERE id = ?'
      ).get(rawId);
      if (!row) return { title: '', body: '' };
      return {
        title: String(row.isim || ''),
        body: [row.ozet, row.tur, row.anahtar_kelimeler].filter(Boolean).join(' ')
      };
    }
    const db = getMoviesDb();
    const row = db.prepare(
      'SELECT isim, ozet, turler, anahtar_kelimeler FROM filmler WHERE id = ?'
    ).get(rawId);
    if (!row) return { title: '', body: '' };
    return {
      title: String(row.isim || ''),
      body: [row.ozet, row.turler, row.anahtar_kelimeler].filter(Boolean).join(' ')
    };
  } catch (e) {
    return { title: '', body: '' };
  }
}

function hybridRank(query, mediaType, rows, queryVec) {
  const themes = detectThemes(query);
  const requiredGenres = extractRequiredGenres(query);
  const queryTokens = tokenizeQuery(query);
  const scored = [];

  for (const r of rows) {
    let vec;
    try { vec = JSON.parse(r.embedding_json); } catch (e) { continue; }

    const cosine = cosineSimilarity(queryVec, vec);
    if (cosine < (config.minSimilarityThreshold * 0.5)) continue;

    const meta = getItemSearchMeta(r.item_id, mediaType);
    const title = meta.title || r.item_title || '';

    if (!passesHardGate(meta.body, title, themes)) continue;
    if (!itemMatchesRequiredGenres(meta.body, requiredGenres)) continue;

    const lex = lexicalScore(meta.body, title, themes, queryTokens);
    const hybrid = (HYBRID_VECTOR_WEIGHT * cosine) + (HYBRID_LEXICAL_WEIGHT * lex);

    // Temasız genel aramada lexical 0 olabilir — cosine yeterliyse tut
    const effectiveMin = themes.length > 0 ? MIN_HYBRID_SCORE : Math.max(0.28, config.minSimilarityThreshold * 0.85);
    if (hybrid < effectiveMin && !(themes.length === 0 && cosine >= config.minSimilarityThreshold)) {
      continue;
    }

    scored.push({
      itemId: r.item_id,
      itemTitle: title || r.item_title,
      rawSimilarity: cosine,
      lexical: lex,
      hybridScore: hybrid
    });
  }

  scored.sort((a, b) => b.hybridScore - a.hybridScore);

  if (scored.length === 0) return [];

  // Temalı sorgu: gap yok — kalite = hard gate + min skor; sıralama FE'de yapılır
  if (themes.length > 0) {
    return scored;
  }

  // Temasız / belirsiz: relative gap ile şişmeyi kes
  const top1 = scored[0].hybridScore;
  const gapFloor = top1 * RELATIVE_GAP_RATIO;
  return scored.filter(s => s.hybridScore >= gapFloor);
}

// --------------------------------------------------------------------------
// 1. ENDPOINT: /api/search (Hibrit Vektör + Kelime Kapısı)
// --------------------------------------------------------------------------
app.post('/api/search', async (req, res) => {
  try {
    const {
      query,
      mediaType = 'MOVIES',
      libraryItemIds = []
    } = req.body;
    if (!query || typeof query !== 'string' || !query.trim()) {
      return res.json({ results: [], count: 0, usedAI: false });
    }

    // GPT yalnızca imzalı Bearer (username.sig); body.isMember yok sayılır
    const auth = String(req.headers.authorization || '');
    const token = auth.startsWith('Bearer ') ? auth.slice(7).trim() : '';
    const gptMember = !!(token && token.includes('.') && !token.startsWith('user_auth_token_'));

    const cleanQuery = query.trim();
    const expandedQuery = expandQueryForEmbedding(cleanQuery);
    const queryVec = await getQueryEmbedding(expandedQuery);
    const embDb = getEmbeddingsDb();

    const targetType = (mediaType.toUpperCase() === 'SERIES') ? 'SERIES' : 'MOVIES';
    const rows = embDb.prepare(
      `SELECT item_id, item_title, embedding_json FROM item_embeddings WHERE media_type = ?`
    ).all(targetType);

    if (rows.length === 0) {
      return res.json({ results: [], count: 0, message: "Henüz vektör kataloğu oluşturulmamış." });
    }

    // Kitaplık ID seti (series_123 / 123 / movies_123)
    const excludeSet = new Set();
    (libraryItemIds || []).forEach(raw => {
      if (raw == null) return;
      const sid = String(raw).trim();
      if (!sid) return;
      excludeSet.add(sid);
      if (sid.startsWith('series_') || sid.startsWith('movies_')) {
        excludeSet.add(sid.replace(/^(series_|movies_)/, ''));
      } else {
        excludeSet.add(`series_${sid}`);
        excludeSet.add(`movies_${sid}`);
      }
    });

    const rankedAll = hybridRank(cleanQuery, targetType, rows, queryVec);
    const rankedFiltered = rankedAll.filter(item => {
      const id = String(item.itemId);
      if (excludeSet.has(id)) return false;
      const bare = id.replace(/^(series_|movies_)/, '');
      return !excludeSet.has(bare);
    });

    const themes = detectThemes(cleanQuery);
    // Temalı: eşik geçen TÜM havuz (sıralama/sayfalama FE silahları). Temasız: küçük tavan.
    const cap = themes.length > 0 ? SEARCH_SAFETY_CAP : UNTHEMED_SEARCH_CAP;
    const ranked = rankedFiltered.slice(0, cap);

    const results = ranked.map((item) => {
      const matchScore = Math.round(Math.min(99, Math.max(45, item.hybridScore * 100)));
      return {
        id: item.itemId,
        title: item.itemTitle,
        rawSimilarity: item.rawSimilarity,
        hybridScore: item.hybridScore,
        aiMatchScore: matchScore,
        aiReason: `Aradığınız "${cleanQuery}" teması ile %${matchScore} hibrit (vektör+kelime) uyumu taşıyor.`
      };
    });

    let usedMemberLLM = false;
    // LLM gerekçe: imzalı üye + top 8; hata/kota yok — şablon gerekçe kalır
    if (gptMember && openai && results.length > 0) {
      try {
        const compactList = results.slice(0, 8).map(r => {
          const meta = getItemSearchMeta(r.id, targetType);
          return {
            id: r.id,
            title: r.title,
            tur: (meta.body || '').split(' ').slice(0, 8).join(' ').slice(0, 70),
            ipuclari: String(meta.body || '').slice(0, 180)
          };
        });
        const systemPrompt =
          'Sen DizimiBul/FilmimiBul sinema uzmanısın. ' +
          'Kullanıcının arama cümlesine göre her yapım için Türkçe 1-2 cümle eşleşme notu yaz (max 40 kelime). ' +
          'Not, arama niyetini yansıtmalı (zombi/hapishane/ortaçağ vb.). ' +
          'Soyut skor / semantik uyum / yüzde YASAK. Strict JSON: {"item_id": "gerekçe"}';
        const userMsg =
          `Arama (notu buna göre yaz): "${cleanQuery}"\n` +
          `Her yapım: kısa konu + NEDEN bu aramaya uyuyor.\n` +
          `Yapımlar: ${JSON.stringify(compactList)}`;

        const completion = await openai.chat.completions.create({
          model: 'gpt-4o-mini',
          messages: [
            { role: 'system', content: systemPrompt },
            { role: 'user', content: userMsg }
          ],
          max_tokens: 420,
          temperature: 0.55,
          response_format: { type: 'json_object' }
        });

        const notes = JSON.parse(completion.choices[0].message.content);
        results.forEach(item => {
          if (notes[item.id]) {
            item.aiReason = notes[item.id];
          }
        });
        usedMemberLLM = true;
      } catch (err) {
        console.error("GPT-4o-mini Batch Rerank Hatası:", err.message);
      }
    }

    res.json({
      results,
      count: results.length,
      totalMatched: rankedFiltered.length,
      poolMode: themes.length > 0 ? 'themed_full_pool' : 'unthemed_capped',
      usedAI: true,
      usedMemberLLM,
      themes: themes.map(t => t.key)
    });
  } catch (err) {
    console.error("Search Endpoint Error:", err);
    res.status(500).json({ error: "Arama işlemi sırasında sunucu hatası." });
  }
});

// --------------------------------------------------------------------------
// 2. ENDPOINT: /api/recommendations (Kitaplık Bazlı Zevk Profili Vektörü)
// --------------------------------------------------------------------------
app.post('/api/recommendations', async (req, res) => {
  try {
    const {
      libraryItemIds = [],
      libraryItems = [],
      userUniverse = 'MOVIES',
      userQuery = '',
      isMember = false
    } = req.body;

    // FE bazen libraryItems[{id,weight}] gönderir — ID listesine çevir
    const resolvedLibIds = [
      ...libraryItemIds,
      ...(Array.isArray(libraryItems) ? libraryItems.map(x => (x && (x.id || x.itemId))).filter(Boolean) : [])
    ].map(String);

    const embDb = getEmbeddingsDb();
    const targetType = (userUniverse.toUpperCase() === 'SERIES') ? 'SERIES' : 'MOVIES';

    const rows = embDb.prepare(`SELECT item_id, item_title, embedding_json FROM item_embeddings WHERE media_type = ?`).all(targetType);
    if (rows.length === 0) {
      return res.json({ recommendations: [], count: 0 });
    }

    // Kullanıcı Kitaplık Ağırlıklı Ortalaması (User Taste Vector)
    let profileVector = null;
    if (resolvedLibIds.length > 0) {
      const libSet = new Set();
      resolvedLibIds.forEach(raw => {
        const sid = String(raw).trim();
        if (!sid) return;
        libSet.add(sid);
        const bare = sid.replace(/^(series_|movies_|movie_)/i, '');
        libSet.add(bare);
        libSet.add(`series_${bare}`);
        libSet.add(`movies_${bare}`);
      });
      let count = 0;

      rows.forEach(r => {
        if (libSet.has(r.item_id) || libSet.has(String(r.item_id).replace(/^(series_|movies_)/i, ''))) {
          let vec;
          try { vec = JSON.parse(r.embedding_json); } catch(e) { return; }
          if (!profileVector) {
            profileVector = new Array(vec.length).fill(0);
          }
          for (let i = 0; i < vec.length; i++) profileVector[i] += vec[i];
          count++;
        }
      });

      if (profileVector && count > 0) {
        for (let i = 0; i < profileVector.length; i++) profileVector[i] /= count;
      }
    }

    // Anlık arama sorgusu varsa vektörünü al (tema genişletmeli)
    let queryVec = null;
    if (userQuery && userQuery.trim()) {
      queryVec = await getQueryEmbedding(expandQueryForEmbedding(userQuery.trim()));
    }

    // Birleşik Vektör: sorgu varsa sorgu ağırlığını yükselt (tema niyeti ezilmesin)
    let targetVec = null;
    if (profileVector && queryVec) {
      const qW = 0.7;
      const pW = 0.3;
      targetVec = profileVector.map((val, idx) => (val * pW) + (queryVec[idx] * qW));
    } else if (profileVector) {
      targetVec = profileVector;
    } else if (queryVec) {
      targetVec = queryVec;
    } else {
      // Rastgele popüler adaylar
      targetVec = await getQueryEmbedding("popüler sürükleyici sinema");
    }

    const libSet = new Set();
    resolvedLibIds.forEach(raw => {
      const sid = String(raw).trim();
      if (!sid) return;
      libSet.add(sid);
      const bare = sid.replace(/^(series_|movies_|movie_)/i, '');
      libSet.add(bare);
      libSet.add(`series_${bare}`);
      libSet.add(`movies_${bare}`);
    });
    const themes = userQuery ? detectThemes(userQuery) : [];
    const queryTokens = userQuery ? tokenizeQuery(userQuery) : [];
    const scored = [];
    rows.forEach(r => {
      const rid = String(r.item_id);
      const bare = rid.replace(/^(series_|movies_)/i, '');
      if (libSet.has(rid) || libSet.has(bare)) return;
      let vec;
      try { vec = JSON.parse(r.embedding_json); } catch(e) { return; }
      const cosine = cosineSimilarity(targetVec, vec);
      if (cosine < config.minSimilarityThreshold * 0.5) return;

      const meta = getItemSearchMeta(r.item_id, targetType);
      const title = meta.title || r.item_title || '';
      if (userQuery && themes.length > 0 && !passesHardGate(meta.body, title, themes)) return;

      const lex = userQuery ? lexicalScore(meta.body, title, themes, queryTokens) : 0;
      const hybrid = userQuery
        ? (HYBRID_VECTOR_WEIGHT * cosine) + (HYBRID_LEXICAL_WEIGHT * lex)
        : cosine;

      if (hybrid >= (userQuery && themes.length > 0 ? MIN_HYBRID_SCORE : config.minSimilarityThreshold)) {
        scored.push({ itemId: r.item_id, itemTitle: title || r.item_title, rawSimilarity: cosine, hybridScore: hybrid });
      }
    });

    scored.sort((a, b) => b.hybridScore - a.hybridScore);
    // Temalı sorguda relative gap uygulama — Vis a Vis / OITNB gibi doğru ama düşük skorlu adaylar kesilmesin
    let filtered = scored;
    if (scored.length > 0 && userQuery && themes.length === 0) {
      const top1 = scored[0].hybridScore;
      filtered = scored.filter(s => s.hybridScore >= top1 * RELATIVE_GAP_RATIO);
    }

    const limit = 15;
    const topScored = filtered.slice(0, limit);

    const recommendations = topScored.map(item => {
      const matchScore = Math.round(Math.min(99, Math.max(40, item.hybridScore * 100)));
      const themeNote = themes.length > 0
        ? `"${String(userQuery).trim()}" temasına %${matchScore} hibrit uyum`
        : `Zevk profilinizle %${matchScore} anlamsal vektör uyumu`;
      return {
        id: item.itemId,
        title: item.itemTitle,
        rawSimilarity: item.rawSimilarity,
        hybridScore: item.hybridScore,
        aiMatchScore: matchScore,
        aiReason: `${themeNote} gösterdiği için önerildi.`
      };
    });

    res.json({
      recommendations,
      visible: recommendations,
      count: recommendations.length,
      usedAI: true,
      themes: themes.map(t => t.key)
    });
  } catch (err) {
    console.error("Recommendations Endpoint Error:", err);
    res.status(500).json({ error: "Tavsiye üretimi sırasında sunucu hatası." });
  }
});

// --------------------------------------------------------------------------
// 3. ENDPOINT: /api/error-reports (Kullanıcı içerik hata bildirimleri)
// --------------------------------------------------------------------------
const ERROR_REPORT_ALLOWED_FIELDS = new Set([
  'poster', 'title', 'slogan', 'rating', 'year', 'platform', 'status',
  'genres', 'summary', 'why_watch', 'trailer', 'seasons', 'episodes',
  'ep_duration', 'duration', 'other'
]);

app.post('/api/error-reports', (req, res) => {
  try {
    const {
      itemId,
      itemTitle = '',
      mediaType = 'SERIES',
      fields = [],
      note = '',
      username = null
    } = req.body || {};

    if (!itemId || typeof itemId !== 'string') {
      return res.status(400).json({ error: 'itemId zorunlu.' });
    }

    const media = String(mediaType).toUpperCase() === 'MOVIES' ? 'MOVIES' : 'SERIES';
    const selected = Array.isArray(fields)
      ? [...new Set(fields.map(f => String(f)).filter(f => ERROR_REPORT_ALLOWED_FIELDS.has(f)))]
      : [];

    if (selected.length === 0) {
      return res.status(400).json({ error: 'En az bir hata alanı seçilmeli.' });
    }

    const noteText = String(note || '').trim().slice(0, 300);
    const user = username ? String(username).trim().slice(0, 80) : null;

    const db = getEmbeddingsDb();
    const info = db.prepare(`
      INSERT INTO content_error_reports (item_id, item_title, media_type, fields_json, note, username)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(
      String(itemId).slice(0, 120),
      String(itemTitle || '').trim().slice(0, 200),
      media,
      JSON.stringify(selected),
      noteText || null,
      user
    );

    res.json({
      ok: true,
      id: info.lastInsertRowid,
      message: 'Hata bildirimi kaydedildi.'
    });
  } catch (err) {
    console.error('Error report POST failed:', err);
    res.status(500).json({ error: 'Hata bildirimi kaydedilemedi.' });
  }
});

app.get('/api/error-reports', (req, res) => {
  try {
    const limit = Math.min(100, Math.max(1, parseInt(req.query.limit, 10) || 50));
    const status = req.query.status ? String(req.query.status) : null;
    const db = getEmbeddingsDb();

    let rows;
    if (status) {
      rows = db.prepare(`
        SELECT id, item_id, item_title, media_type, fields_json, note, username, status, created_at
        FROM content_error_reports
        WHERE status = ?
        ORDER BY created_at DESC
        LIMIT ?
      `).all(status, limit);
    } else {
      rows = db.prepare(`
        SELECT id, item_id, item_title, media_type, fields_json, note, username, status, created_at
        FROM content_error_reports
        ORDER BY created_at DESC
        LIMIT ?
      `).all(limit);
    }

    const reports = rows.map(r => ({
      id: r.id,
      itemId: r.item_id,
      itemTitle: r.item_title,
      mediaType: r.media_type,
      fields: (() => { try { return JSON.parse(r.fields_json); } catch (e) { return []; } })(),
      note: r.note,
      username: r.username,
      status: r.status,
      createdAt: r.created_at
    }));

    res.json({ reports, count: reports.length });
  } catch (err) {
    console.error('Error report GET failed:', err);
    res.status(500).json({ error: 'Hata bildirimleri okunamadı.' });
  }
});

app.patch('/api/error-reports/:id', (req, res) => {
  try {
    const id = parseInt(req.params.id, 10);
    const status = String((req.body || {}).status || '').toLowerCase();
    if (!Number.isFinite(id) || !['open', 'resolved', 'ignored'].includes(status)) {
      return res.status(400).json({ error: 'Geçersiz id veya status.' });
    }
    const db = getEmbeddingsDb();
    const info = db.prepare('UPDATE content_error_reports SET status = ? WHERE id = ?').run(status, id);
    if (!info.changes) return res.status(404).json({ error: 'Kayıt bulunamadı.' });
    res.json({ ok: true, id, status });
  } catch (err) {
    console.error('Error report PATCH failed:', err);
    res.status(500).json({ error: 'Durum güncellenemedi.' });
  }
});

// --------------------------------------------------------------------------
// 3b. ENDPOINT: /api/feedback (Geri Bildirim sekmesi mesajları — aynı DB)
// --------------------------------------------------------------------------
app.post('/api/feedback', (req, res) => {
  try {
    const { message = '', username = null, mediaType = null } = req.body || {};
    const text = String(message || '').trim().slice(0, 2000);
    if (!text) {
      return res.status(400).json({ error: 'Mesaj zorunlu.' });
    }
    const user = username ? String(username).trim().slice(0, 80) : null;
    const media = mediaType ? String(mediaType).toUpperCase().slice(0, 20) : null;
    const db = getEmbeddingsDb();
    const info = db.prepare(`
      INSERT INTO user_feedback (username, message, media_type)
      VALUES (?, ?, ?)
    `).run(user, text, media);
    res.json({ ok: true, id: info.lastInsertRowid, message: 'Geri bildirim kaydedildi.' });
  } catch (err) {
    console.error('Feedback POST failed:', err);
    res.status(500).json({ error: 'Geri bildirim kaydedilemedi.' });
  }
});

app.get('/api/feedback', (req, res) => {
  try {
    const limit = Math.min(100, Math.max(1, parseInt(req.query.limit, 10) || 50));
    const db = getEmbeddingsDb();
    const rows = db.prepare(`
      SELECT id, username, message, media_type, status, created_at
      FROM user_feedback
      ORDER BY created_at DESC
      LIMIT ?
    `).all(limit);
    res.json({
      feedback: rows.map(r => ({
        id: r.id,
        username: r.username,
        message: r.message,
        mediaType: r.media_type,
        status: r.status,
        createdAt: r.created_at
      })),
      count: rows.length
    });
  } catch (err) {
    console.error('Feedback GET failed:', err);
    res.status(500).json({ error: 'Geri bildirimler okunamadı.' });
  }
});

app.listen(config.port, () => {
  console.log("==========================================================================");
  console.log(`🚀 DIZIMIBUL SEMANTIC BACKEND RUNNING ON HTTP://LOCALHOST:${config.port}`);
  console.log("==========================================================================");
});
