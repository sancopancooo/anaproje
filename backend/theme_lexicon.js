/**
 * Tema sözlüğü: sorgu genişletme (embedding) + dar hard-gate token setleri.
 * Spesifik dönem/tema sorgularında saf cosine yanlış pozitiflerini keser.
 */

export const THEME_LEXICON = {
  ortacag: {
    triggers: ['ortaçağ', 'ortacag', 'orta çağ', 'medieval', 'feodal', 'feudal', 'middle ages', 'dark ages'],
    // Embedding zenginleştirme (geniş)
    expand: [
      'ortaçağ', 'medieval', 'feodal', 'feudal', 'şövalye', 'knight', 'kale', 'castle',
      'kılıç', 'sword', 'krallık', 'kingdom', 'period drama', 'tarihi dönem', 'dark ages'
    ],
    // Sert kapı — tek başına "krallık" / başlıktaki "şövalye" yetmez
    gateStrong: [
      'ortaçağ', 'orta çağ', 'ortacag', 'medieval', 'feodal', 'feudal',
      'middle ages', 'dark ages', 'period drama', 'tarihi dönem', 'şövalye dönemi',
      'viking', 'vikings', 'witcher', 'westeros', 'camelot', 'knightfall'
    ],
    gateComboA: ['şövalye', 'knight', 'kale', 'castle', 'kılıç', 'sword', 'zırh', 'armor', 'ejderha', 'dragon'],
    gateComboB: [
      'krallık', 'kingdom', 'hanedan', 'dynasty', 'taht', 'throne', 'feodal',
      'ejderha', 'dragon', 'viking', 'imparatorluk', 'empire', 'kral', 'kraliçe',
      'lord', 'baron', 'şato', 'chateau', 'ortaçağ', 'medieval', 'büyücü', 'elf', 'fantastik dönem'
    ]
  },
  tarih: {
    triggers: ['tarihi dizi', 'tarihi film', 'tarihî', 'period piece', 'biyografik dönem'],
    expand: ['tarihi', 'historical', 'dönem', 'period', 'imparatorluk', 'osmanlı', 'antik', 'biography period'],
    gateStrong: ['tarihi', 'historical', 'dönem filmi', 'period drama', 'period piece', 'osmanlı', 'antik roma', 'antik yunan'],
    gateComboA: ['tarih', 'tarihi', 'historical', 'dönem'],
    gateComboB: ['imparatorluk', 'savaş', 'kral', 'padişah', 'imparator', 'antik', 'osmanlı', 'roma', 'yunan']
  },
  uzay: {
    triggers: ['uzay', 'galaksi', 'uzaylı', 'space opera', 'yıldız gemisi'],
    expand: ['uzay', 'space', 'galaksi', 'galaxy', 'uzaylı', 'alien', 'yıldız gemisi', 'spaceship', 'sci-fi', 'bilimkurgu'],
    gateStrong: ['uzay', 'space', 'galaksi', 'galaxy', 'uzaylı', 'alien', 'spaceship', 'yıldız gemisi', 'mars', 'nasa'],
    gateComboA: ['uzay', 'space', 'galaksi', 'sci-fi', 'bilimkurgu'],
    gateComboB: ['gezegen', 'planet', 'astronot', 'yıldız', 'starship', 'evren', 'cosmos']
  },
  zombi: {
    triggers: ['zombi', 'zombie', 'ölü yürüyen'],
    // 'undead' expand'te yok — Undead Unluck başlık tuzağı
    expand: ['zombi', 'zombie', 'salgın', 'apocalypse', 'hayatta kalma', 'walking dead', 'walkers', 'enfekte'],
    gateStrong: ['zombi', 'zombie', 'ölü yürüyen', 'walking dead', 'zombie apocalypse'],
    gateComboA: ['zombi', 'zombie', 'enfekte', 'infected'],
    gateComboB: ['salgın', 'apocalypse', 'kıyamet', 'hayatta kalma', 'survival', 'outbreak', 'walkers'],
    titleHints: [
      'the walking dead', 'fear the walking dead', 'the last of us', 'last of us',
      'z nation', 'all of us are dead', 'train to busan', 'world war z', 'sweet home',
      'kingdom' // yalnızca Kore zombi dizisi "Kingdom" — "The Last Kingdom" aşağıda elenir
    ],
    titleExclude: ['last kingdom', 'the last kingdom']
  },
  okul: {
    triggers: ['okul', 'okulda', 'school', 'kampüs', 'kampus', 'lise', 'üniversite', 'universite', 'campus'],
    expand: [
      'okul', 'school', 'kampüs', 'kampus', 'lise', 'üniversite', 'universite', 'campus',
      'öğrenci', 'ogrenci', 'sınıf', 'sinif', 'akademi', 'yurt', 'teen drama', 'gençlik'
    ],
    gateStrong: [
      'okul', 'school', 'kampüs', 'kampus', 'lise', 'üniversite', 'universite', 'campus',
      'high school', 'boarding school', 'öğrenci', 'ogrenci'
    ],
    gateComboA: ['okul', 'school', 'kampüs', 'kampus', 'lise', 'üniversite', 'campus'],
    gateComboB: [
      'öğrenci', 'ogrenci', 'sınıf', 'sinif', 'hoca', 'öğretmen', 'ogretmen',
      'teen', 'genç', 'genc', 'akademi', 'yurt', 'mezun', 'sınıf arkadaş'
    ],
    titleHints: [
      'elite', 'riverdale', 'pretty little liars', 'gossip girl', 'sex education',
      'skam', 'control z', 'american vandal', 'dear white people', 'wednesday'
    ]
  },
  vampir: {
    triggers: ['vampir', 'vampire', 'kan emici'],
    expand: ['vampir', 'vampire', 'kan', 'gotik', 'doğaüstü', 'immortal'],
    gateStrong: ['vampir', 'vampire', 'vampires'],
    gateComboA: ['vampir', 'vampire'],
    gateComboB: ['kan', 'gotik', 'doğaüstü', 'gece', 'ölümsüz', 'immortal']
  },
  hapishane: {
    triggers: ['hapishane', 'cezaevi', 'prison', 'mahkum', 'parmaklık'],
    expand: [
      'hapishane', 'cezaevi', 'prison', 'mahkum', 'gardiyan', 'koğuş', 'hücre',
      'parmaklık', 'inmate', 'penitentiary', 'warden',
      'prison break', 'vis a vis', 'orange is the new black', 'oz', 'wentworth',
      'locked up', 'kızıl kadınlar', 'cezaevi draması'
    ],
    // Tek başına "hapishane/kaçış" yetmez (Avengers özeti gibi yan bahisleri ele)
    gateStrong: [
      'cezaevi', 'mahkum', 'koğuş', 'hücre', 'parmaklık', 'inmate', 'penitentiary',
      'prison break', 'vis a vis', 'orange is the new black', 'wentworth',
      'locked up abroad', 'kızıl kadınlar'
    ],
    gateComboA: ['hapishane', 'hapis', 'prison', 'cezaevi', 'cezaev'],
    gateComboB: ['mahkum', 'gardiyan', 'koğuş', 'hücre', 'parmaklık', 'inmate', 'warden', 'firar plan', 'hapis cezası'],
    // Başlık/bilinen yapım boost'u (lexical)
    titleHints: [
      'prison break', 'vis a vis', 'orange is the new black', 'oz', 'wentworth',
      'banshee', 'animal kingdom', 'lockup', 'papillon', 'shawshank', 'escape plan',
      'kızıl kadınlar', 'within these walls'
    ]
  },
  casus: {
    triggers: ['casus', 'ajan', 'casusluk', 'spy', 'istihbarat'],
    expand: ['casus', 'ajan', 'spy', 'cia', 'fbi', 'istihbarat', 'gizli görev'],
    gateStrong: ['casus', 'casusluk', 'spy', 'espionage', 'istihbarat', 'gizli ajan'],
    gateComboA: ['casus', 'ajan', 'spy', 'istihbarat'],
    gateComboB: ['cia', 'fbi', 'mi6', 'gizli', 'operasyon', 'undercover']
  }
};

function normalizeTr(text) {
  return String(text || '')
    .toLowerCase()
    .replace(/ı/g, 'i')
    .replace(/İ/g, 'i')
    .replace(/ğ/g, 'g')
    .replace(/ü/g, 'u')
    .replace(/ş/g, 's')
    .replace(/ö/g, 'o')
    .replace(/ç/g, 'c');
}

function textHasToken(haystack, token) {
  if (!token || !haystack) return false;
  const h = haystack.toLowerCase();
  const t = token.toLowerCase();
  if (h.includes(t)) return true;
  // ASCII-fold fallback for TR chars
  return normalizeTr(h).includes(normalizeTr(t));
}

/** Kısa title hint'ler (oz) yanlış pozitif üretmesin — kelime sınırı / tam başlık */
function titleHintMatches(titleText, hint) {
  if (!hint || !titleText) return false;
  const title = String(titleText).toLowerCase().trim();
  const h = String(hint).toLowerCase().trim();
  if (!h) return false;
  if (title === h) return true;
  if (h.length <= 3) {
    // "oz" → Ozark / dozen yanlışları engelle
    const re = new RegExp(`(?:^|[\\s:;\\-_/("'\\[])${h.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}(?:$|[\\s:;\\-_/)"'\\]])`, 'i');
    return re.test(title);
  }
  return textHasToken(title, h);
}

/**
 * Sorgudan aktif temaları çıkarır.
 */
export function detectThemes(queryText) {
  const q = (queryText || '').toLowerCase();
  const qNorm = normalizeTr(q);
  const active = [];
  for (const [key, theme] of Object.entries(THEME_LEXICON)) {
    const hit = theme.triggers.some(tr => {
      const t = tr.toLowerCase();
      return q.includes(t) || qNorm.includes(normalizeTr(t));
    });
    if (hit) active.push({ key, ...theme });
  }
  return active;
}

/**
 * Embedding için zenginleştirilmiş sorgu metni.
 */
export function expandQueryForEmbedding(queryText) {
  const themes = detectThemes(queryText);
  if (themes.length === 0) return queryText;
  const extra = [];
  themes.forEach(th => {
    th.expand.forEach(w => {
      if (!extra.includes(w)) extra.push(w);
    });
  });
  return `${queryText.trim()} | temalar: ${extra.join(', ')}`;
}

/**
 * Lexical skor (0..1) — title/keywords/genres/summary ağırlıklı.
 * Zayıf başlık token'ları (undead, good, kingdom…) tek başına şişirmesin.
 */
const TITLE_WEAK_SOFT_TOKENS = new Set([
  'undead', 'dead', 'alive', 'good', 'bad', 'new', 'last', 'first', 'next',
  'house', 'home', 'world', 'war', 'night', 'day', 'man', 'boy', 'girl',
  'love', 'dark', 'power', 'force', 'legend', 'legacy', 'origin', 'origins',
  'kingdom', 'place', 'doctor', 'office', 'black', 'white', 'red', 'blue',
  'big', 'little', 'one', 'two', 'life', 'death', 'city', 'land', 'story',
  'game', 'games', 'star', 'stars', 'true', 'real', 'american', 'secret'
]);

function isTitleWeakSoftToken(token) {
  const t = normalizeTr(String(token || '').trim().toLowerCase());
  if (!t) return true;
  if (t.includes(' ')) return false;
  return TITLE_WEAK_SOFT_TOKENS.has(t) || t.length <= 3;
}

export function lexicalScore(metaText, titleText, themes, queryTokens) {
  if (!metaText && !titleText) return 0;
  const full = `${titleText || ''} ${metaText || ''}`.toLowerCase();
  const title = (titleText || '').toLowerCase();
  const body = (metaText || '').toLowerCase();
  let raw = 0;
  let hits = 0;

  const scoreToken = (token, weightTitle, weightBody) => {
    if (!token || token.length < 2) return;
    const inTitle = textHasToken(title, token);
    const inBody = textHasToken(body, token);
    if (inTitle && !inBody && isTitleWeakSoftToken(token)) {
      raw += Math.min(weightTitle, weightBody) * 0.35;
      hits += 0.25;
    } else if (inTitle) {
      raw += weightTitle;
      hits += 1;
    } else if (textHasToken(full, token)) {
      raw += weightBody;
      hits += 1;
    }
  };

  // Genel sorgu token'ları
  (queryTokens || []).forEach(t => scoreToken(t, 0.12, 0.06));

  // Tema expand kelimeleri
  themes.forEach(th => {
    (th.expand || []).forEach(t => scoreToken(t, 0.18, 0.12));
    (th.gateStrong || []).forEach(t => scoreToken(t, 0.28, 0.22));
    // Bilinen tema yapımları — başlıkta geçince güçlü boost
    (th.titleHints || []).forEach(hint => {
      if (!hint) return;
      if (titleHintMatches(title, hint)) {
        raw += 0.55;
        hits += 2;
      }
    });
  });

  if (hits === 0) return 0;
  return Math.min(1, raw);
}

/**
 * Hard gate: spesifik tema sorgusunda aday metinde çekirdek iz olmalı.
 * true = geçti / gate yok; false = elendi
 */
export function passesHardGate(metaText, titleText, themes) {
  if (!themes || themes.length === 0) return true;

  const full = `${titleText || ''} ${metaText || ''}`.toLowerCase();
  const title = (titleText || '').toLowerCase();

  return themes.every(th => {
    // Tema-özel başlık dışlamaları (örn. zombi "Kingdom" ≠ The Last Kingdom)
    if (Array.isArray(th.titleExclude) && th.titleExclude.some(ex => textHasToken(title, ex))) {
      return false;
    }

    // Bilinen tema dizisi/filmi başlıkta → direkt geç
    const titleHintHit = (th.titleHints || []).some(h => titleHintMatches(title, h));
    if (titleHintHit) return true;

    const strongHit = (th.gateStrong || []).some(t => textHasToken(full, t));
    if (strongHit) return true;

    const aHits = (th.gateComboA || []).filter(t => textHasToken(full, t));
    const bHits = (th.gateComboB || []).filter(t => textHasToken(full, t));

    // Combo: A ve B'den en az birer — ama A yalnızca başlıkta ve B yoksa reddet
    if (aHits.length > 0 && bHits.length > 0) {
      const aOnlyInTitle = aHits.every(t => textHasToken(title, t) && !textHasToken(metaText || '', t));
      const bOnlyWeak = bHits.length === 1 && ['krallık', 'kingdom', 'kral'].includes(bHits[0].toLowerCase()) && aOnlyInTitle;
      if (bOnlyWeak) return false;

      // Hapishane: süper kahraman / animasyon yan bahislerini ele
      if (th.key === 'hapishane') {
        const isSuperheroNoise = /avengers|superhero|süper kahraman|marvel|dc comics|animasyon|animation/.test(full)
          && !/(cezaevi|mahkum|koğuş|parmaklık|wentworth|prison break|vis a vis|orange is the new black)/.test(full);
        if (isSuperheroNoise) return false;
      }

      // Zombi: yalnız başlıkta undead / dead yetmez
      if (th.key === 'zombi') {
        const body = (metaText || '').toLowerCase();
        const titleOnlyUndead = textHasToken(title, 'undead') && !textHasToken(body, 'undead')
          && !textHasToken(body, 'zombi') && !textHasToken(body, 'zombie');
        if (titleOnlyUndead) return false;
      }
      return true;
    }

    // Fantastik dönem: özet/keyword'de 2+ güçlü B token (ejderha+taht, hanedan+krallık…)
    const strongB = bHits.filter(t =>
      !['kral', 'kingdom', 'krallık'].includes(String(t).toLowerCase()) || textHasToken(metaText || '', t)
    );
    if (strongB.length >= 2 && !(strongB.every(t => textHasToken(title, t) && !textHasToken(metaText || '', t)))) {
      return true;
    }

    // Title-only şövalye / knight gibi zayıf tekil eşleşme → red
    return false;
  });
}

/**
 * Basit sorgu tokenizasyonu (TR stop-word hafif filtre).
 */
export function tokenizeQuery(queryText) {
  const stop = new Set([
    'bir', 've', 'ile', 'icin', 'için', 'olan', 'olarak', 'gibi', 'cok', 'çok',
    'da', 'de', 'ki', 'bu', 'su', 'şu', 'o', 'ben', 'sen', 'biz', 'siz',
    'dizi', 'dizisi', 'film', 'filmi', 'izlemek', 'istiyorum', 'isterim',
    'arni', 'arıyorum', 'ara', 'ne', 'tur', 'tür', 'gecen', 'geçen', 'olsun',
    'bana', 'lutfen', 'lütfen', 'the', 'a', 'an', 'of', 'in', 'on'
  ]);
  return String(queryText || '')
    .toLowerCase()
    .split(/[^\wığüşöçİĞÜŞÖÇ0-9]+/)
    .map(w => w.trim())
    .filter(w => w.length >= 2 && !stop.has(w) && !stop.has(normalizeTr(w)));
}

/** Arama cümlesinde açıkça istenen türler (dram, gizem vb.) */
const QUERY_GENRE_ALIASES = {
  dram: ['dram', 'drama'],
  gizem: ['gizem', 'mystery'],
  komedi: ['komedi', 'comedy'],
  korku: ['korku', 'horror'],
  gerilim: ['gerilim', 'thriller'],
  aksiyon: ['aksiyon', 'action'],
  animasyon: ['animasyon', 'animation'],
  belgesel: ['belgesel', 'documentary'],
  romantik: ['romantik', 'romance'],
  suc: ['suç', 'suc', 'crime'],
  fantastik: ['fantastik', 'fantasy'],
  bilimkurgu: ['bilim kurgu', 'bilimkurgu', 'sci-fi', 'scifi']
};

export function extractRequiredGenres(queryText) {
  const q = String(queryText || '').toLowerCase();
  const qNorm = normalizeTr(q);
  const required = [];
  for (const [genreKey, aliases] of Object.entries(QUERY_GENRE_ALIASES)) {
    const hit = aliases.some(alias => {
      const a = alias.toLowerCase();
      return q.includes(a) || qNorm.includes(normalizeTr(a));
    });
    if (hit) required.push(genreKey);
  }
  return required;
}

export function itemMatchesRequiredGenres(metaText, requiredGenres) {
  if (!requiredGenres || requiredGenres.length === 0) return true;
  const body = normalizeTr(String(metaText || '').toLowerCase());
  return requiredGenres.every(g => body.includes(g));
}

export const HYBRID_VECTOR_WEIGHT = 0.55;
export const HYBRID_LEXICAL_WEIGHT = 0.45;
/** Tema kapısından geçen adaylar için minimum hibrit skor (Prison Break vb. elenir). */
export const MIN_HYBRID_SCORE = 0.34;
/**
 * Relative gap: sadece TEMASIZ / geniş sorgularda kullanılır.
 * Temalı aramada (ortaçağ vb.) gap uygulanmaz — sıralama silahları tam havuzda çalışsın.
 */
export const RELATIVE_GAP_RATIO = 0.55;
/** Patolojik dump güvenlik tavanı (katalog boyutu üstü değil, sadece kaza önleyici). */
export const SEARCH_SAFETY_CAP = 800;
/** Tema yokken (belirsiz sorgu) makul üst sınır. */
export const UNTHEMED_SEARCH_CAP = 48;
