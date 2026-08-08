/* ==========================================================================
   🎬 MATRIX DIZI & FILM PLATFORMU - ANA UYGULAMA VE ETKİLEŞİM SCRIPTİ
   ==========================================================================
   Açıklama: Bu dosya Matrix Landing Page geçişlerini, Kırmızı/Mavi evren
   temalarını, dizimibul tasarımındaki geniş yatay içerik kartlarını, 
   gelişmiş filtreleme motorunu ve sayfalama (pagination) mantığını yönetir.
   ========================================================================== */

function resolveApiBaseUrl() {
    const cfg = (typeof window !== 'undefined' && window.APP_CONFIG && window.APP_CONFIG.API_BASE_URL)
        ? String(window.APP_CONFIG.API_BASE_URL).trim().replace(/\/$/, '')
        : '';
    if (cfg) return cfg;

    const host = (typeof window !== 'undefined' && window.location) ? window.location.hostname : '';
    if (host === 'localhost' || host === '127.0.0.1') {
        return 'http://localhost:4000';
    }

    // config.js henüz doldurulmadıysa canlı sitede API'ye bağlanılmaz
    console.warn('[API] APP_CONFIG.API_BASE_URL boş. config.js içine Render URL yaz.');
    return '';
}

const API_BASE_URL = resolveApiBaseUrl();


/* ==========================================================================
   🎬 YOUTUBE SİTE İÇİ MODAL POPUP VİDEO OYNATICI (SEKME DEĞİŞTİRMEDEN İZLEME)
   ========================================================================== */
function escapeQuotes(str) {
    if (!str) return '';
    return str.replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * Kart arka plan (TMDB backdrop) HTML'i.
 * mode: 'overlay' = Keşfet/Kitaplık/Favoriler (kart üstüne bindirme)
 *       'hero'    = AI Tavsiyeler (kartın üstünde ayrı şerit)
 */
/** HTML attribute içine güvenli yazım — & kaçmazsa data-proxy/data-mirror URL'leri kırılır. */
function safeImageSrc(url) {
    return String(url || '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function renderCardBackdropHtml(backdropUrl, mode = 'overlay') {
    if (!backdropUrl) return '';
    const safeUrl = safeImageSrc(optimizeTmdbBackdropUrl(backdropUrl));
    const variant = (mode === 'hero') ? 'card-backdrop-banner--hero' : 'card-backdrop-banner--overlay';
    return `
        <div class="card-backdrop-banner ${variant}" aria-hidden="true">
            <img class="card-backdrop-banner__img" src="${safeUrl}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onError="this.closest('.card-backdrop-banner') && this.closest('.card-backdrop-banner').remove();" />
            <div class="card-backdrop-banner__fade"></div>
        </div>
    `;
}

// Placeholder constants for missing trailers
const PLACEHOLDER_DUB = "TÜRKÇE_FRAGMAN_BULUNAMADI";
const PLACEHOLDER_SUB = "ORİJİNAL_FRAGMAN_BULUNAMADI";
const PLACEHOLDER_GENERIC = "not_found";

const TMDB_POSTER_FALLBACK = 'https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500';
let _renderCardsToken = 0;

function getApiBaseUrl() {
    return (typeof API_BASE_URL !== 'undefined' && API_BASE_URL)
        ? String(API_BASE_URL).replace(/\/$/, '')
        : '';
}

function extractTmdbImagePath(url) {
    const m = String(url || '').match(/\/t\/p\/[^/]+(\/[^?\s#]+)/);
    return m ? m[1] : '';
}

function toDirectTmdbUrl(url, size) {
    let raw = String(url || '').trim();
    if (!raw) return '';

    // weserv / wsrv katmanlarını soy (çift sarmalama URL'yi bozuyordu)
    for (let i = 0; i < 4; i++) {
        if (!/weserv\.nl|wsrv\.nl/i.test(raw)) break;
        try {
            const nested = new URL(raw).searchParams.get('url');
            if (!nested) break;
            raw = /^https?:\/\//i.test(nested) ? nested : `https://${nested}`;
        } catch (_) {
            break;
        }
    }

    if (raw.includes('/api/tmdb-image')) {
        try {
            const u = new URL(raw, 'https://local.invalid');
            const path = u.searchParams.get('path') || '';
            const sz = u.searchParams.get('size') || size;
            if (path) return `https://image.tmdb.org/t/p/${sz}${path.startsWith('/') ? path : '/' + path}`;
        } catch (_) { /* ignore */ }
    }

    // Host kontrolü — query string içinde geçen image.tmdb.org'a kanma
    let host = '';
    try { host = new URL(raw).hostname; } catch (_) { /* ignore */ }
    if (host !== 'image.tmdb.org') return raw;

    return raw
        .replace(/\/t\/p\/w\d+\//, `/t/p/${size}/`)
        .replace(/\/t\/p\/original\//, `/t/p/${size}/`);
}

function toProxiedTmdbUrl(url, size) {
    const direct = toDirectTmdbUrl(url, size);
    if (!direct || !direct.includes('image.tmdb.org')) return '';
    const path = extractTmdbImagePath(direct);
    const apiBase = getApiBaseUrl();
    if (!apiBase || !path) return '';
    return `${apiBase}/api/tmdb-image?size=${size}&path=${encodeURIComponent(path)}`;
}

function isTmdbImageHost(url) {
    try { return new URL(String(url || '')).hostname === 'image.tmdb.org'; }
    catch (_) { return false; }
}

function toWeservTmdbUrl(url, size) {
    const direct = toDirectTmdbUrl(url, size);
    if (!direct || !isTmdbImageHost(direct)) return '';
    const width = (size === 'w780') ? 780 : (size === 'w185' ? 185 : 342);
    // TMDB TR'de sık engelli; weserv CDN (Render cold-start yok)
    return `https://images.weserv.nl/?url=${encodeURIComponent(direct.replace(/^https?:\/\//, ''))}&w=${width}&output=webp`;
}

/** Liste/kart afişleri: weserv öncelikli (TR engeline dayanıklı). */
function optimizeTmdbPosterUrl(url) {
    const direct = toDirectTmdbUrl(url, 'w342');
    if (!direct) return url;
    return toWeservTmdbUrl(direct, 'w342') || (isTmdbImageHost(direct) ? direct : (direct || url));
}

function optimizeTmdbBackdropUrl(url) {
    const direct = toDirectTmdbUrl(url, 'w780');
    if (!direct) return url;
    return toWeservTmdbUrl(direct, 'w780') || (isTmdbImageHost(direct) ? direct : (direct || url));
}

function resolvePosterUrl(item) {
    if (!item) return TMDB_POSTER_FALLBACK;
    const raw = String(item.poster_url || item.afis_url || '').trim();
    if (!raw) return TMDB_POSTER_FALLBACK;
    return optimizeTmdbPosterUrl(raw);
}

window.__posterImgError = function (img) {
    if (!img) return;
    const direct = img.getAttribute('data-direct') || '';
    const fallback = img.getAttribute('data-fallback') || TMDB_POSTER_FALLBACK;
    // Birincil weserv fail → direkt TMDB dene → placeholder
    if (direct && !img.dataset.triedDirect) {
        img.dataset.triedDirect = '1';
        img.src = direct;
        return;
    }
    img.onerror = null;
    if (img.src !== fallback) img.src = fallback;
};

/**
 * Kart afişleri: weserv → TMDB → placeholder.
 * Ham TMDB veya önceden weserv'lenmiş URL kabul eder (çift sarmalama yok).
 */
function posterImgHtml(url, alt, className = 'card-poster-img', lazy = false, fetchPriority = '') {
    const resolved = url || TMDB_POSTER_FALLBACK;
    const direct = toDirectTmdbUrl(resolved, 'w342');
    const primary = (direct && toWeservTmdbUrl(direct, 'w342'))
        || (direct && isTmdbImageHost(direct) ? direct : '')
        || resolved;
    const prioAttr = (!lazy && fetchPriority) ? ` fetchpriority="${fetchPriority}"` : '';
    const lazyAttr = lazy ? 'loading="lazy" decoding="async"' : `loading="eager" decoding="async"${prioAttr}`;
    return `<img class="${className}" src="${safeImageSrc(primary)}" alt="${escapeHtml(alt || '')}" ${lazyAttr} referrerpolicy="no-referrer" data-direct="${safeImageSrc(direct || '')}" data-fallback="${TMDB_POSTER_FALLBACK}" onError="window.__posterImgError(this)" />`;
}

/** Landing hero yarım yarım boyanmasın — tam yüklenince göster. */
function bindLandingHeroReady() {
    const hero = document.querySelector('.hero-split-image');
    if (!hero) return;
    const markReady = () => hero.classList.add('is-ready');
    if (hero.complete && hero.naturalWidth > 0) {
        markReady();
        return;
    }
    hero.addEventListener('load', markReady, { once: true });
    hero.addEventListener('error', markReady, { once: true });
}

/** Evren değişince eski kartları anında sil; async render yarışını iptal et. */
function resetExploreCardsForUniverseSwitch() {
    _renderCardsToken += 1;
    currentPage = 1;
    if (_renderCardsDebounceTimer) {
        clearTimeout(_renderCardsDebounceTimer);
        _renderCardsDebounceTimer = null;
    }
    const cardsContainer = document.getElementById('cards-container');
    const resultsCountText = document.getElementById('results-count-text');
    if (cardsContainer) {
        cardsContainer.innerHTML = `
            <div style="grid-column:1/-1;text-align:center;padding:28px 12px;color:#9ca3af;font-weight:700;">
                Liste yenileniyor…
            </div>`;
    }
    if (resultsCountText) resultsCountText.textContent = 'Liste yenileniyor…';
}

function isMainAppVisible() {
    const mainApp = document.getElementById('main-app');
    if (!mainApp) return false;
    if (mainApp.classList.contains('hidden')) return false;
    const display = (mainApp.style && mainApp.style.display) || '';
    return display !== 'none';
}

function brandLogoSvgMarkup(universe) {
    if (universe === 'MOVIES') {
        return `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" aria-hidden="true">
  <defs>
    <linearGradient id="filmGradMark" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f97316"/><stop offset="100%" stop-color="#dc2626"/>
    </linearGradient>
    <linearGradient id="goldGradMark" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fbbf24"/><stop offset="100%" stop-color="#f97316"/>
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="46" fill="rgba(220,38,38,0.15)" stroke="url(#filmGradMark)" stroke-width="1.5"/>
  <ellipse cx="50" cy="52" rx="42" ry="22" fill="none" stroke="url(#goldGradMark)" stroke-width="3.5" transform="rotate(-22 50 52)" opacity="0.95"/>
  <rect x="22" y="38" width="38" height="28" rx="6" fill="url(#filmGradMark)" stroke="#fbbf24" stroke-width="1.5"/>
  <polygon points="60,44 76,35 76,69 60,60" fill="url(#filmGradMark)" stroke="#fbbf24" stroke-width="1.5"/>
  <circle cx="33" cy="29" r="9" fill="#120505" stroke="url(#goldGradMark)" stroke-width="2.5"/>
  <circle cx="33" cy="29" r="3" fill="#fbbf24"/>
  <circle cx="51" cy="29" r="9" fill="#120505" stroke="url(#goldGradMark)" stroke-width="2.5"/>
  <circle cx="51" cy="29" r="3" fill="#fbbf24"/>
  <polygon points="37,45 37,59 50,52" fill="#ffffff"/>
</svg>`;
    }
    return `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" aria-hidden="true">
  <defs>
    <linearGradient id="diziGradMark" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00f0ff"/><stop offset="100%" stop-color="#3b82f6"/>
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="46" fill="rgba(59,130,246,0.15)" stroke="url(#diziGradMark)" stroke-width="1.5"/>
  <path d="M 40 76 L 60 76 L 66 85 L 34 85 Z" fill="url(#diziGradMark)"/>
  <rect x="16" y="26" width="68" height="48" rx="10" fill="#050a12" stroke="url(#diziGradMark)" stroke-width="3"/>
  <line x1="38" y1="26" x2="26" y2="12" stroke="#00f0ff" stroke-width="3" stroke-linecap="round"/>
  <line x1="62" y1="26" x2="74" y2="12" stroke="#00f0ff" stroke-width="3" stroke-linecap="round"/>
  <circle cx="26" cy="12" r="3" fill="#00f0ff"/>
  <circle cx="74" cy="12" r="3" fill="#00f0ff"/>
  <polygon points="36,37 36,61 54,49" fill="url(#diziGradMark)"/>
</svg>`;
}

function setBrandLogo(universe) {
    const mark = document.getElementById('brand-logo-img');
    if (!mark) return;
    mark.innerHTML = brandLogoSvgMarkup(universe === 'MOVIES' ? 'MOVIES' : 'SERIES');
}

function isValidTrailerUrl(url) {
    if (!url) return false;
    const lowered = String(url).toLowerCase();
    if (lowered === 'none' || lowered === '#' || lowered === 'null' || lowered === PLACEHOLDER_DUB.toLowerCase() || lowered === PLACEHOLDER_SUB.toLowerCase() || lowered === PLACEHOLDER_GENERIC.toLowerCase()) {
        return false;
    }
    if (lowered.includes('youtube.com') || lowered.includes('youtu.be')) {
        return true;
    }
    return false;
}

function extractYoutubeVideoId(url) {
    if (!url || url === 'None') return '';
    const s = String(url);
    if (s.includes('youtube.com/watch?v=')) return s.split('watch?v=')[1].split('&')[0];
    if (s.includes('youtu.be/')) return s.split('youtu.be/')[1].split('?')[0];
    if (s.includes('youtube.com/embed/')) return s.split('embed/')[1].split('?')[0];
    return '';
}

/** YouTube başlığına göre: dub | sub_tr | original */
function classifyTrailerKindFromMeta(metaText, fallbackKind = 'original') {
    const t = String(metaText || '').toLowerCase()
        .replace(/ı/g, 'i').replace(/İ/g, 'i')
        .replace(/ğ/g, 'g').replace(/ü/g, 'u')
        .replace(/ş/g, 's').replace(/ö/g, 'o')
        .replace(/ç/g, 'c');
    const has = (arr) => arr.some(k => t.includes(k));

    const dubHints = ['dublaj', 'dublajli', 'dubbed', 'turkish dub', 'turkce dublaj', 'tr dublaj'];
    const subHints = ['altyazi', 'altyazili', 'subtitle', 'subtitled', 'turkce altyazi', 'closed caption'];
    const trHints = [
        'turkce', 'turkish', 'turkiye',
        'netflix turkiye', 'disney+ turkiye', 'disney turkiye',
        'warner bros. turkiye', 'prime video turkiye', 'box office turkiye'
    ];

    if (has(dubHints)) return 'dub';
    if (has(subHints)) return 'sub_tr';
    if (has(trHints)) return 'sub_tr';
    return fallbackKind;
}

async function fetchYoutubeOEmbedMeta(url) {
    const id = extractYoutubeVideoId(url);
    if (!id) return '';
    try {
        const res = await fetch(
            `https://www.youtube.com/oembed?url=${encodeURIComponent(`https://www.youtube.com/watch?v=${id}`)}&format=json`
        );
        if (!res.ok) return '';
        const data = await res.json();
        return `${data.title || ''} ${data.author_name || ''}`;
    } catch (e) {
        return '';
    }
}

function trailerKindLabel(kind) {
    if (kind === 'dub') return '🎬 Resmi Fragman · Türkçe Dublaj';
    if (kind === 'sub_tr') return '🎬 Resmi Fragman · Türkçe Altyazı';
    if (kind === 'original') return '🎬 Resmi Fragman · Orijinal (EN)';
    return '🎬 Resmi Fragman';
}

function trailerKindBadgeHtml(kind) {
    if (kind === 'dub') {
        return '<i class="fa-solid fa-microphone"></i> Resmi Fragman · Türkçe Dublaj';
    }
    if (kind === 'sub_tr') {
        return '<i class="fa-solid fa-closed-captioning"></i> Resmi Fragman · Türkçe Altyazı';
    }
    if (kind === 'original') {
        return '<i class="fa-solid fa-globe"></i> Resmi Fragman · Orijinal (EN)';
    }
    return '<i class="fa-solid fa-film"></i> Resmi Fragman';
}

function trailerKindCss(kind) {
    if (kind === 'dub' || kind === 'sub_tr') return 'trailer-frame-badge trailer-frame-badge--tr';
    if (kind === 'original') return 'trailer-frame-badge trailer-frame-badge--en';
    return 'trailer-frame-badge trailer-frame-badge--official';
}

function trailerStaticBadgeClass(kind) {
    if (kind === 'original') return 'trailer-static-badge--en';
    if (kind === 'dub' || kind === 'sub_tr') return 'trailer-static-badge--tr';
    return 'trailer-static-badge--official';
}

/** Ana katalogdan güncel fragman — kitaplık/localStorage eski Father/remake URL'lerini ezer */
function getCanonicalCatalogItem(itemId, titleHint) {
    const series = (typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : [];
    const movies = (typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : [];
    if (itemId) {
        const id = String(itemId);
        const hit = series.find(d => d.id === id) || movies.find(d => d.id === id);
        if (hit) return hit;
    }
    if (titleHint) {
        const t = String(titleHint).trim().toLowerCase();
        return series.find(d => (d.title || '').toLowerCase() === t)
            || movies.find(d => (d.title || '').toLowerCase() === t)
            || null;
    }
    return null;
}

function resolveFreshTrailerUrls(itemId, title, dubUrl, subUrl, trailerUrl) {
    const canon = getCanonicalCatalogItem(itemId, title);
    if (!canon) {
        return {
            dubUrl: isValidTrailerUrl(dubUrl) ? dubUrl : null,
            subUrl: isValidTrailerUrl(subUrl) ? subUrl : null,
            primaryUrl: isValidTrailerUrl(dubUrl) ? dubUrl : (isValidTrailerUrl(subUrl) ? subUrl : (isValidTrailerUrl(trailerUrl) ? trailerUrl : null)),
            title: title,
            backdropUrl: ''
        };
    }
    const dub = isValidTrailerUrl(canon.trailer_dub_url) ? canon.trailer_dub_url : null;
    const sub = isValidTrailerUrl(canon.trailer_sub_url) ? canon.trailer_sub_url : null;
    return {
        dubUrl: dub,
        subUrl: sub,
        primaryUrl: dub || sub || (isValidTrailerUrl(canon.trailer_url) ? canon.trailer_url : null),
        title: canon.title || title,
        backdropUrl: canon.backdrop_url || ''
    };
}

/** Kartlarda fragman butonu — dil pill'leri yok (sadece Resmi Fragman) */
function buildTrailerActionHtml(item, opts = {}) {
    const isSeries = opts.isSeries != null
        ? opts.isSeries
        : Boolean(item && item.id && String(item.id).startsWith('series_'));
    const fullWidth = opts.fullWidth ? 'width: 100%; justify-content: center;' : '';
    const dub = item.trailer_dub_url || '';
    const sub = item.trailer_sub_url || '';
    const hasDub = isValidTrailerUrl(dub);
    const hasSub = isValidTrailerUrl(sub);
    const hasAny = hasDub || hasSub || isValidTrailerUrl(item.trailer_url);

    if (!hasAny) {
        return `
            <button class="card-action-btn btn-no-trailer" onclick="showToast('⚠️ Bu yapım için henüz resmi fragman eklenmemiş.', 2500)" style="${fullWidth}">
                <i class="fa-solid fa-film"></i> Fragman Henüz Yok
            </button>
        `;
    }

    return `
        <button onclick="openTrailerModal('${item.id}', '${escapeQuotes(item.title)}', 'tr', '${escapeQuotes(dub)}', '${escapeQuotes(sub)}', ${Boolean(isSeries)})" class="card-action-btn btn-trailer-play" style="${fullWidth}">
            <i class="fa-solid fa-play"></i> Resmi Fragman
        </button>
    `;
}

async function openTrailerModal(itemIdOrUrl, movieTitle, trailerType = 'tr', dubUrl = null, subUrl = null, isSeriesArg = false) {
    const modal = document.getElementById('youtube-trailer-modal');
    const iframe = document.getElementById('trailer-modal-iframe');
    const titleElem = document.getElementById('trailer-modal-title');
    const frameBadge = document.getElementById('trailer-frame-badge');

    if (!modal || !iframe) return;

    let primaryUrl = itemIdOrUrl;
    let isSeries = Boolean(isSeriesArg) || (typeof currentUniverse !== 'undefined' && currentUniverse === 'SERIES');
    let itemObj = null;
    let itemId = null;
    let backdropUrl = '';

    if (typeof itemIdOrUrl === 'object' && itemIdOrUrl !== null) {
        itemObj = itemIdOrUrl;
        itemId = itemObj.id || null;
        isSeries = (itemObj.id && String(itemObj.id).startsWith('series_')) || itemObj.seasons_num !== undefined || itemObj.total_episodes !== undefined;
        movieTitle = itemObj.title;
        dubUrl = itemObj.trailer_dub_url;
        subUrl = itemObj.trailer_sub_url;
        primaryUrl = itemObj.trailer_url;
    } else if (typeof itemIdOrUrl === 'string' && (itemIdOrUrl.startsWith('series_') || itemIdOrUrl.startsWith('movie_'))) {
        itemId = itemIdOrUrl;
        primaryUrl = null;
    }

    // Katalog her zaman kaynak (eski kitaplık URL'leri Father/remake getirebiliyordu)
    const fresh = resolveFreshTrailerUrls(itemId, movieTitle, dubUrl, subUrl, primaryUrl);
    dubUrl = fresh.dubUrl;
    subUrl = fresh.subUrl;
    primaryUrl = fresh.primaryUrl;
    movieTitle = fresh.title || movieTitle;
    backdropUrl = fresh.backdropUrl || (itemObj && itemObj.backdrop_url) || '';

    if (!primaryUrl || primaryUrl === '#' || primaryUrl === 'None' || primaryUrl === '') {
        showToast('⚠️ Bu yapım için henüz resmi fragman linki eklenmemiş.', 3000);
        return;
    }

    const hasDub = isValidTrailerUrl(dubUrl);
    const hasSub = isValidTrailerUrl(subUrl);
    const isSameUrl = hasDub && hasSub && (String(dubUrl).trim() === String(subUrl).trim());

    // Doğrulanmadan dil iddiası yok — oEmbed sonrası dub / sub_tr / original atanır
    let kindA = hasDub ? 'official' : null;
    let kindB = (hasSub && !isSameUrl) ? 'official' : null;

    function setFrameBadgeByKind(kind) {
        if (!frameBadge) return;
        const safeKind = kind || 'official';
        frameBadge.innerHTML = trailerKindBadgeHtml(safeKind);
        frameBadge.className = trailerKindCss(safeKind);
        frameBadge.style.display = 'inline-flex';
    }

    window.switchTrailerStream = function(url, kindOrMode) {
        const kind = (kindOrMode === 'DUB') ? 'dub'
            : (kindOrMode === 'SUB') ? 'original'
            : (kindOrMode === 'OFFICIAL') ? 'official'
            : (kindOrMode || 'official');
        const vid = extractYoutubeVideoId(url);
        if (vid) {
            iframe.src = `https://www.youtube.com/embed/${vid}?autoplay=1&rel=0&cc_load_policy=1&cc_lang_pref=tr&hl=tr&enablejsapi=1`;
        }
        const btnA = document.getElementById('btn-trailer-stream-a');
        const btnB = document.getElementById('btn-trailer-stream-b');
        const activeUrl = String(url || '');

        [btnA, btnB].forEach(btn => {
            if (!btn) return;
            const isActive = btn.getAttribute('data-url') === activeUrl;
            const k = btn.getAttribute('data-kind') || 'official';
            const isTr = (k === 'dub' || k === 'sub_tr');
            btn.style.background = isActive
                ? (isTr ? 'linear-gradient(135deg, #10b981 0%, #059669 100%)' : 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)')
                : 'rgba(255,255,255,0.1)';
            btn.style.borderColor = isActive
                ? (isTr ? '#10b981' : '#3b82f6')
                : 'rgba(255,255,255,0.2)';
        });
        setFrameBadgeByKind(kind);
    };

    function buildSelectorHtml(kA, kB) {
        const streams = [];
        if (hasDub) streams.push({ url: dubUrl, kind: kA || 'official', btnId: 'btn-trailer-stream-a' });
        if (hasSub && !isSameUrl) streams.push({ url: subUrl, kind: kB || 'official', btnId: 'btn-trailer-stream-b' });
        if (!streams.length && isValidTrailerUrl(primaryUrl)) {
            streams.push({ url: primaryUrl, kind: 'official', btnId: 'btn-trailer-stream-a' });
        }

        const unique = [];
        const seen = new Set();
        streams.forEach(s => {
            const key = String(s.url).trim();
            if (!key || seen.has(key)) return;
            seen.add(key);
            unique.push(s);
        });

        if (unique.length >= 2) {
            return `
                <div class="trailer-lang-selector">
                    ${unique.map(s => `
                        <button id="${s.btnId}" type="button"
                            data-url="${String(s.url).replace(/"/g, '&quot;')}"
                            data-kind="${s.kind}"
                            onclick="switchTrailerStream(this.getAttribute('data-url'), this.getAttribute('data-kind'))"
                            class="trailer-lang-btn ${s.kind === 'original' ? 'trailer-lang-btn--en' : 'trailer-lang-btn--tr'}">
                            ${trailerKindLabel(s.kind)}
                        </button>
                    `).join('')}
                </div>
            `;
        }
        if (unique.length === 1) {
            const s = unique[0];
            return `<div style="margin-top: 6px;"><span class="trailer-static-badge ${trailerStaticBadgeClass(s.kind)}">${trailerKindLabel(s.kind)}</span></div>`;
        }
        return `<div style="margin-top: 6px;"><span class="trailer-static-badge trailer-static-badge--official">🎬 Resmi Fragman</span></div>`;
    }

    function paintHeader(kA, kB) {
        if (!titleElem) return;
        const backdropHtml = backdropUrl
            ? `<img class="modal-backdrop-hero" src="${backdropUrl}" alt="Hero Backdrop" style="width: 100%; height: 140px; object-fit: cover; border-radius: 10px; margin-bottom: 12px; filter: brightness(0.7);" />`
            : '';
        titleElem.innerHTML = `
            ${backdropHtml}
            <div style="position: relative; z-index: 1;">
                <h3 style="margin: 0; color: #fff; font-size: 1.25rem; font-weight: 800;">${movieTitle || 'Yapım'}</h3>
                ${buildSelectorHtml(kA, kB)}
            </div>
        `;
    }

    paintHeader(kindA, kindB);

    const initialUrl = hasDub ? dubUrl : (hasSub ? subUrl : primaryUrl);
    const initialKind = hasDub ? (kindA || 'official') : (hasSub ? (kindB || 'official') : 'official');
    window.switchTrailerStream(initialUrl, initialKind);
    modal.style.display = 'flex';

    // YouTube başlığından gerçek dil türünü doğrula; üst seçici ile alt badge aynı kalsın
    try {
        const [metaA, metaB] = await Promise.all([
            hasDub ? fetchYoutubeOEmbedMeta(dubUrl) : Promise.resolve(''),
            (hasSub && !isSameUrl) ? fetchYoutubeOEmbedMeta(subUrl) : Promise.resolve('')
        ]);
        if (hasDub) {
            // Meta yoksa dil iddiası yapma (yanlış "Türkçe Altyazı" engeli)
            kindA = metaA ? classifyTrailerKindFromMeta(metaA, 'original') : 'official';
        }
        if (hasSub && !isSameUrl) {
            kindB = metaB ? classifyTrailerKindFromMeta(metaB, 'original') : 'official';
        }
        paintHeader(kindA, kindB);
        const btnA = document.getElementById('btn-trailer-stream-a');
        const btnB = document.getElementById('btn-trailer-stream-b');
        const playUrl = (btnA && btnA.getAttribute('data-url'))
            || (btnB && btnB.getAttribute('data-url'))
            || initialUrl;
        const playKind = (btnA && btnA.getAttribute('data-kind'))
            || (btnB && btnB.getAttribute('data-kind'))
            || 'official';
        window.switchTrailerStream(playUrl, playKind);
    } catch (e) {
        // oEmbed başarısızsa nötr "Resmi Fragman" etiketiyle devam
        setFrameBadgeByKind('official');
    }
}

function closeTrailerModal() {
    const modal = document.getElementById('youtube-trailer-modal');
    const iframe = document.getElementById('trailer-modal-iframe');

    if (iframe) iframe.src = '';
    if (modal) modal.style.display = 'none';
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeTrailerModal();
});

/* ==========================================================================
   📌 BAŞLIK 1: YEDEK VERİ SETLERİ (MOCK FALLBACK)
   ========================================================================== */
const SAMPLE_SERIES = [
    {
        id: "series_01",
        title: "Teach You a Lesson",
        rating: "9.477/10",
        rating_num: 9.477,
        seasons: "1 Sezon (10 Bölüm)",
        seasons_num: 1,
        votes_num: 39593,
        runtime: "22 dk",
        platform: "Netflix",
        status: "Bitmiş / Final Yapmış",
        genres: ["Aksiyon & Macera", "Dram", "Komedi"],
        summary: "Özet: Okullarda otoriteye saygı yerle bir olduğunda işleri yoluna koymak için gelen sıra dışı müfettişler, ders kitaplarında bulunmayan katı ve ciddi dersler vermeye başlar.",
        duo: 'Terrence "T" Kelly & Jessica Murphy',
        duo_desc: "Otoriteye karşı gözü pek mücadele eden sıra dışı ikili.",
        why_watch: [
            "Otoriteye karşı sıra dışı müfettişlerin komik ve aksiyon dolu hikayesi.",
            "Okullarda otoriteye saygı konusunda bir dönüm noktası olan sıra dışı derslikler."
        ],
        poster_url: "https://image.tmdb.org/t/p/w500/yO1yfYyHemDZAJyLNLz3tCiaNC8.jpg",
        year: 2024
    }
];

const SAMPLE_MOVIES = [
    {
        id: "tt1375666",
        title: "Başlangıç (Inception)",
        rating: "8.8/10",
        rating_num: 8.8,
        seasons: "Sinema Filmi",
        seasons_num: 1,
        votes_num: 50000,
        runtime: "148 dk",
        platform: "Netflix",
        status: "Vizyon Filmi",
        genres: ["Aksiyon", "Bilim-Kurgu", "Macera"],
        summary: "Özet: Hedeflerinin bilinçaltına sızarak kurumsal casusluk yapan yetenekli bir hırsız olan Cobb'a, imkansız bir görev teklif edilir.",
        duo: "Dom Cobb & Arthur",
        duo_desc: "Rüya mimarları ve zihin hırsızlığı ekibi.",
        why_watch: [
            "Christopher Nolan'dan sinema tarihinin en ikonik zihin bükücü kurgusu.",
            "Hans Zimmer imzalı muazzam müzikler ve unutulmaz rüya katmanları."
        ],
        poster_url: "https://image.tmdb.org/t/p/w500/oYuLEW92AR8rA92gvhZ8BJu25E9.jpg",
        year: 2010
    }
];

let currentUniverse = 'MOVIES';
let currentPage = 1;
// AI arama: yazarken canlı tetiklenmesin — sadece Enter / Listele ile commit edilir
let COMMITTED_AI_SEARCH_QUERY = '';
let COMMITTED_SIDEBAR_SEARCH_QUERY = '';

let USER_FAVORITES = [];
let currentFavPage = 1;
const FAV_PER_PAGE = 5;


/* ==========================================================================
   📌 BAŞLIK 2: MATRIX CANVAS ANIMASYONU
   ========================================================================== */
let matrixCanvasTimer = null;

function initMatrixCanvas() {
    const canvas = document.getElementById('matrix-canvas');
    if (!canvas) return;

    if (matrixCanvasTimer) return;

    const ctx = canvas.getContext('2d');
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const chars = '01アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン';
    const fontSize = 14;
    const columns = Math.floor(canvas.width / fontSize);
    const drops = Array(columns).fill(1);

    function drawMatrix() {
        ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        ctx.fillStyle = '#22c55e';
        ctx.font = fontSize + 'px monospace';

        for (let i = 0; i < drops.length; i++) {
            const text = chars.charAt(Math.floor(Math.random() * chars.length));
            ctx.fillText(text, i * fontSize, drops[i] * fontSize);

            if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                drops[i] = 0;
            }
            drops[i]++;
        }
    }

    matrixCanvasTimer = setInterval(drawMatrix, 40);
}

function stopMatrixCanvas() {
    if (matrixCanvasTimer) {
        clearInterval(matrixCanvasTimer);
        matrixCanvasTimer = null;
    }
    const canvas = document.getElementById('matrix-canvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
}


/* ==========================================================================
   📌 BAŞLIK 3: EVREN SEÇİMİ VE KÜRESEL GEÇİŞ MOTORU
   ========================================================================== */
let isTransitioning = false;
window.enterAppFromGlobal = function(universe) {
    if (isTransitioning) return;
    isTransitioning = true;
    console.log("Entering universe:", universe);
    const landingPage = document.getElementById('landing-page');
    const mainApp = document.getElementById('main-app');

    try {
        setUniverse(universe);
    } catch (e) {
        console.warn("setUniverse error:", e);
    }

    // 💊 Matrix Hap Yutma Efekti (Pill Swallow Flying FX)
    try {
        const targetBadge = (universe === 'MOVIES') 
            ? document.querySelector('.red-badge') 
            : document.querySelector('.blue-badge');

        if (targetBadge) {
            const rect = targetBadge.getBoundingClientRect();
            const flyEl = document.createElement('div');
            flyEl.className = `flying-pill-overlay ${(universe === 'MOVIES') ? 'red-swallow' : 'blue-swallow'}`;
            flyEl.style.left = `${rect.left + rect.width / 2}px`;
            flyEl.style.top = `${rect.top + rect.height / 2}px`;
            flyEl.style.width = `${rect.width}px`;
            flyEl.style.height = `${rect.height}px`;
            flyEl.style.display = 'flex';
            flyEl.style.alignItems = 'center';
            flyEl.style.justifyContent = 'center';
            flyEl.innerHTML = targetBadge.innerHTML;
            document.body.appendChild(flyEl);

            setTimeout(() => {
                if (flyEl && flyEl.parentNode) {
                    flyEl.parentNode.removeChild(flyEl);
                }
            }, 800);
        }
    } catch (err) {
        console.warn("Pill FX warning:", err);
    }

    if (landingPage) {
        landingPage.classList.add('portal-shatter');
    }

    setTimeout(() => {
        if (landingPage) {
            landingPage.style.setProperty('display', 'none', 'important');
            landingPage.style.opacity = '0';
            landingPage.style.pointerEvents = 'none';
            landingPage.classList.add('hidden');
            landingPage.classList.remove('portal-shatter');
        }

        if (mainApp) {
            mainApp.style.setProperty('display', 'flex', 'important');
            mainApp.style.opacity = '1';
            mainApp.classList.remove('hidden');
            mainApp.classList.add('portal-entry');
            setTimeout(() => mainApp.classList.remove('portal-entry'), 850);
        }

        stopMatrixCanvas();
        // Kartları portal-entry (opacity:0 + blur) bitmeden boyama —
        // ilk girişte afişler error'a düşüp sarı placeholder'a kilitleniyordu.
        // Evren değiştirince animasyon olmadığı için resimler düzgün geliyordu.
        const paintExplore = () => {
            try {
                scheduleRenderContentCards(true);
                window._libraryNeedsRefresh = true;
                window._favoritesNeedsRefresh = true;
                if (typeof updateVersusUI === 'function') updateVersusUI();
                if (typeof renderSocialUI === 'function') renderSocialUI();
                if (typeof renderFeedbackUI === 'function') renderFeedbackUI();
            } catch (err) {
                console.warn("Render error:", err);
            }
            isTransitioning = false;
        };
        setTimeout(paintExplore, 820);
    }, 600);
};

function setupUniverseSelection() {
    const btnMovies = document.getElementById('btn-select-movies');
    const btnSeries = document.getElementById('btn-select-series');
    const btnSwitch = document.getElementById('btn-switch-universe');

    if (btnMovies) {
        btnMovies.addEventListener('click', (e) => {
            e.stopPropagation();
            window.enterAppFromGlobal('MOVIES');
        });
    }

    if (btnSeries) {
        btnSeries.addEventListener('click', (e) => {
            e.stopPropagation();
            window.enterAppFromGlobal('SERIES');
        });
    }

    if (btnSwitch) {
        btnSwitch.addEventListener('click', () => {
            setUniverse((currentUniverse === 'MOVIES') ? 'SERIES' : 'MOVIES');
        });
    }
}


/* ==========================================================================
   📌 BAŞLIK 4: TEMATİK DÖNÜŞÜM VE EVREN YÖNETİMİ
   ========================================================================== */
/** Keşfet yan paneli varsayılanları — evren değişince sıfırlanır */
function resetExploreSidebarFilters() {
    const sliderRating = document.getElementById('slider-min-rating');
    const valRating = document.getElementById('val-min-rating');
    if (sliderRating) sliderRating.value = '5.0';
    if (valRating) valRating.textContent = '5.0';

    const sliderSensitivity = document.getElementById('slider-search-sensitivity');
    const valSensitivity = document.getElementById('val-search-sensitivity');
    if (sliderSensitivity) sliderSensitivity.value = '65';
    if (valSensitivity) valSensitivity.textContent = '65';

    const selectSort = document.getElementById('select-sort');
    if (selectSort) selectSort.value = 'AI';

    const selectGenre = document.getElementById('select-genre');
    if (selectGenre) selectGenre.value = 'ALL';

    const selectPlatform = document.getElementById('select-platform');
    if (selectPlatform) selectPlatform.value = 'ALL';

    const selectLanguage = document.getElementById('select-language');
    if (selectLanguage) selectLanguage.value = 'ALL';

    const inputMinYear = document.getElementById('input-min-year');
    if (inputMinYear) inputMinYear.value = '1990';

    const inputMaxSeasons = document.getElementById('input-max-seasons');
    if (inputMaxSeasons) inputMaxSeasons.value = '20';

    const inputMinVotes = document.getElementById('input-min-votes');
    if (inputMinVotes) inputMinVotes.value = '100';

    const selectPerPage = document.getElementById('select-per-page');
    if (selectPerPage) selectPerPage.value = '30';

    const checkOnlyEnded = document.getElementById('check-only-ended');
    if (checkOnlyEnded) checkOnlyEnded.checked = false;

    const inputSearch = document.getElementById('input-search');
    if (inputSearch) inputSearch.value = '';
}

function setUniverse(universe) {
    closeAssistantModal();
    currentUniverse = universe;
    currentPage = 1;

    // ARAMA SIFIRLAMA: Evren değiştirildiğinde arama kutuları temizlenir
    const inputSearchReset = document.getElementById('input-search');
    const aiSearchReset = document.getElementById('ai-search-text-input');
    if (inputSearchReset) inputSearchReset.value = '';
    if (aiSearchReset) aiSearchReset.value = '';
    COMMITTED_AI_SEARCH_QUERY = '';
    COMMITTED_SIDEBAR_SEARCH_QUERY = '';
    resetExploreSidebarFilters();
    if (typeof window.BACKEND_SEARCH_CACHE !== 'undefined') {
        window.BACKEND_SEARCH_CACHE = {};
    }
    const body = document.body;
    const universeName = document.getElementById('universe-name');
    const switchText = document.getElementById('switch-text');
    const brandText = document.getElementById('brand-text');
    const aiHeading = document.getElementById('ai-search-heading');
    const aiLabel = document.getElementById('ai-search-prompt-label');
    const btnListText = document.getElementById('btn-list-text');
    
    // Sidebar & Kitaplığım Dinamik Etiketler & Filtre Grupları
    const lblMinRating = document.getElementById('lbl-min-rating');
    const lblPerPage = document.getElementById('lbl-per-page');
    const grpMaxSeasons = document.getElementById('grp-max-seasons');
    const grpOnlyEnded = document.getElementById('grp-only-ended');
    const inputSearch = document.getElementById('input-search');
    
    const lblStatMediaCount = document.getElementById('lbl-stat-media-count');
    const summaryManualAdd = document.getElementById('summary-manual-add');
    const lblSelectManual = document.getElementById('lbl-select-manual');

    if (universe === 'MOVIES') {
        body.classList.remove('theme-blue');
        if (universeName) universeName.textContent = 'Film Evreni';
        if (switchText) switchText.textContent = 'Dizilere Geç';
        if (brandText) brandText.textContent = 'FilmimiBul';
        setBrandLogo('MOVIES');
        if (aiHeading) aiHeading.innerHTML = '<i class="fa-solid fa-film"></i> Yapay Zeka ile Film Keşfet';
        if (aiLabel) aiLabel.textContent = 'Ne tür bir film arıyorsun?';
        if (btnListText) btnListText.textContent = 'Filmleri Listele';
        
        // 🔴 KIRMIZI HAP / FILM EVRENİ DÖNÜŞÜMLERİ
        if (lblMinRating) lblMinRating.textContent = 'Minimum Film Puanı';
        if (lblPerPage) lblPerPage.innerHTML = '<i class="fa-solid fa-file"></i> Sayfa Başına Film';
        if (grpMaxSeasons) grpMaxSeasons.style.display = 'none'; // Filmlerin sezonu olmaz!
        if (grpOnlyEnded) grpOnlyEnded.style.display = 'none';   // Filmlerin 'bitmiş dizi' durumu olmaz!
        if (inputSearch) inputSearch.placeholder = 'Film veya yönetmen adı...';
        
        if (lblStatMediaCount) lblStatMediaCount.textContent = '🎬 Takip Edilen Film Sayısı';
        if (summaryManualAdd) summaryManualAdd.innerHTML = '➕ Manuel Film Ekleme';
        if (lblSelectManual) lblSelectManual.textContent = '🔍 Film Seçiniz...';
    } else {
        body.classList.add('theme-blue');
        if (universeName) universeName.textContent = 'Dizi Evreni';
        if (switchText) switchText.textContent = 'Filmlere Geç';
        if (brandText) brandText.textContent = 'DizimiBul';
        setBrandLogo('SERIES');
        if (aiHeading) aiHeading.innerHTML = '<i class="fa-solid fa-tv"></i> Yapay Zeka ile Dizi Keşfet';
        if (aiLabel) aiLabel.textContent = 'Ne tür bir dizi arıyorsun?';
        if (btnListText) btnListText.textContent = 'Dizileri Listele';
        
        // 🔵 MAVİ HAP / DIZI EVRENİ DÖNÜŞÜMLERİ
        if (lblMinRating) lblMinRating.textContent = 'Minimum Dizi Puanı';
        if (lblPerPage) lblPerPage.innerHTML = '<i class="fa-solid fa-file"></i> Sayfa Başına Dizi';
        if (grpMaxSeasons) grpMaxSeasons.style.display = 'block';
        if (grpOnlyEnded) grpOnlyEnded.style.display = 'flex';
        if (inputSearch) inputSearch.placeholder = 'Dizi veya oyuncu adı...';
        
        if (lblStatMediaCount) lblStatMediaCount.textContent = '🎬 Takip Edilen Dizi Sayısı';
        if (summaryManualAdd) summaryManualAdd.innerHTML = '➕ Manuel Dizi Ekleme';
        if (lblSelectManual) lblSelectManual.textContent = '🔍 Dizi Seçiniz...';
    }

    currentFavPage = 1;
    currentLibraryPage = 1;
    currentLibrarySearchQuery = '';
    window.BACKEND_REC_CACHE = {};
    window.CURRENT_REC_STATE = { visible: [], overflowQueue: [], isMovie: (universe === 'MOVIES') };
    window._exploreNeedsRefresh = true;
    window._libraryNeedsRefresh = true;
    window._favoritesNeedsRefresh = true;
    const aiResultsContainer = document.getElementById('ai-results-container');
    if (aiResultsContainer) aiResultsContainer.innerHTML = '';

    const libSearchInput = document.getElementById('input-library-search');
    if (libSearchInput) {
        libSearchInput.value = '';
        libSearchInput.placeholder = (universe === 'MOVIES')
            ? 'Kitaplığında film ara...'
            : 'Kitaplığında dizi ara...';
    }

    currentPage = 1;
    // Eski evren kartlarını hemen sil — film/dizi karışmasını engeller
    resetExploreCardsForUniverseSwitch();

    // Landing'deyken ağır render yapma — giriş ekranı donmasın
    if (!isMainAppVisible()) {
        window._exploreNeedsRefresh = true;
        window._libraryNeedsRefresh = true;
        window._favoritesNeedsRefresh = true;
        return;
    }

    scheduleRenderContentCards(true);
    if (isLibraryTabActive()) {
        updateLibraryUI();
    } else {
        window._libraryNeedsRefresh = true;
    }
    renderFavorites();
    updateVersusUI();
    renderSocialUI();
    resetFusionUI();
    renderFeedbackUI();

    // AI sekmesi açık değilken ağır tavsiye üretimini ertele
    const aiTab = document.getElementById('tab-recommender');
    if (aiTab && aiTab.classList.contains('active') && typeof generateAIRecommendations === 'function') {
        syncAIOngoingPrefUI();
        generateAIRecommendations();
    } else if (typeof syncAIOngoingPrefUI === 'function') {
        syncAIOngoingPrefUI();
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('filter-sidebar');
    const mainContent = document.getElementById('app-main-content');
    const expandBtn = document.getElementById('btn-expand-sidebar');

    if (!sidebar) return;

    const isHidden = sidebar.classList.contains('collapsed') || sidebar.style.display === 'none';

    if (isHidden) {
        // Genişlet (Eski Haline Getir)
        sidebar.style.display = 'block';
        sidebar.classList.remove('collapsed');
        if (mainContent) mainContent.classList.remove('sidebar-collapsed');
        if (expandBtn) expandBtn.style.display = 'none';
        showToast('◀ Yan panel açıldı (Varsayılan Düzen)', 1500);
    } else {
        // Gizle / Daralt (100% Ekrandan Kaldır)
        sidebar.style.display = 'none';
        sidebar.classList.add('collapsed');
        if (mainContent) mainContent.classList.add('sidebar-collapsed');
        if (expandBtn) expandBtn.style.display = 'block';
        showToast('▶ Yan panel gizlendi, ekran genişletildi!', 1500);
    }
}


/* ==========================================================================
   📌 BAŞLIK 5: GELİŞMİŞ FİLTRELEME VE SAYFALAMA RENDER MOTORU (PAGINATION)
   ==========================================================================
   Açıklama: Min Puan, Min Yayın Yılı, Max Sezon, Min Oy Sayısı, Sadece Bitmiş
   Diziler, Sayfa Başına Dizi ve Sayfalama butonlarını eksiksiz yönetir.
   ========================================================================== */
/* ==========================================================================
   📌 BAŞLIK: GPT NOTLARI — SUNUCU TARAFLI (istemci API key yok)
   Kota bitince UI uyarısı yok; cosine/şablon gerekçeler sessizce devam eder.
   ========================================================================== */
function getSignedAuthToken() {
    const username = (typeof CURRENT_USER !== 'undefined' && CURRENT_USER && CURRENT_USER !== 'Kullanıcı')
        ? CURRENT_USER
        : null;
    if (!username) return '';
    return localStorage.getItem(`MATRIX_SIGNED_TOKEN_${username.toLowerCase()}`) || '';
}

function isUserLoggedInStrict() {
    return !!(typeof CURRENT_USER !== 'undefined' && CURRENT_USER && CURRENT_USER !== 'Kullanıcı');
}

async function ensureSignedAuthToken() {
    if (!isUserLoggedInStrict()) return '';
    const existing = getSignedAuthToken();
    if (existing && existing.includes('.')) {
        refreshAdminSessionFromServer().catch(() => {});
        return existing;
    }

    const username = CURRENT_USER;
    loadRegisteredAccounts();
    const acc = (REGISTERED_ACCOUNTS || []).find(a => a.username && a.username.toLowerCase() === username.toLowerCase());
    const saved = (() => {
        try { return JSON.parse(localStorage.getItem('MATRIX_SAVED_USER') || 'null'); } catch (e) { return null; }
    })();
    const password = (acc && acc.password) || (saved && saved.password) || '';
    const email = (acc && acc.email) || '';
    if (!password) return '';

    const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
    try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 2500);
        const res = await fetch(`${baseUrl}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, email }),
            signal: ctrl.signal
        });
        clearTimeout(timer);
        if (!res.ok) return '';
        const data = await res.json();
        if (data.token) {
            localStorage.setItem(`MATRIX_SIGNED_TOKEN_${username.toLowerCase()}`, data.token);
            if (typeof data.isAdmin !== 'undefined') {
                setAdminSessionFlag(!!data.isAdmin);
            }
            return data.token;
        }
    } catch (e) {}
    return '';
}

/* ==========================================================================
   📌 BAŞLIK: DOĞAL DİL YAPAY ZEKA ARAMA MOTORU VE SİNONİM SÖZLÜĞÜ (NLP & COSINE)
   ========================================================================== */
const TURKISH_STOP_WORDS = new Set([
    "ben", "bir", "ve", "veya", "ile", "için", "gibi", "olan", "olduğu", "da", "de", "mı", "mi", "mu", "mü",
    "bana", "sana", "böyle", "şöyle", "istiyorum", "dizi", "diziler", "film", "filmler", "yapım", "yapımlar",
    "var", "yok", "getir", "bul", "öner", "tarzı", "tarzında", "türü", "türünde", "türündeki", "hakkında",
    "geçen", "geçtiği", "geçenler", "temalı", "konulu", "adlı", "en", "çok", "daha", "her", "şey", "malım",
    "kral", "lütfen", "asdasd", "qwerty", "tavsiye", "öneri", "izlemek",
    // 🆕 Türkçe çekim ekleri ile gelen yaygın gürültü kelimeleri
    "filmleri", "dizileri", "yapımları", "filmin", "dizinin", "tarzında", "türünden",
    "istiyorum", "izlemek", "izlemek", "önerin", "gibi", "kadar", "olan", "olacak",
    "birini", "birini", "birinde", "birinden", "biri"
]);

/* ─── TÜRKÇE EK SOYMA (STEMMING) ────────────────────────────────────────────
   Basit suffix stripping: "dedektiflik" → "dedektif", "filmleri" → "film"
   Bu sayede çekim ekleriyle yazılan kelimeler kök formlarıyla eşleşir.
   Sinonim haritasındaki kök form bulununca genişletme devreye girer.
   ─────────────────────────────────────────────────────────────────────── */
function turkishStem(word) {
    if (word.length <= 4) return word; // çok kısa kelimelere dokunma
    // En uzun ekten kısaya doğru sırala (greedy olmamak için)
    const suffixes = [
        'cilik', 'cılık', 'çilik', 'çılık',   // -cilik (uzmanlık)
        'likleri', 'lıkları', 'lükleri', 'lukları', // karmaşık çoklu ekler
        'lik', 'lık', 'lük', 'luk',            // -lik (isim yapan ek)
        'lerin', 'ların', 'lere', 'lara',       // çoğul + yön hali
        'lerde', 'larda', 'lerden', 'lardan',   // çoğul + bulunma/çıkma
        'leri', 'ları',                         // çoğul iyelik
        'ler', 'lar',                           // çoğul
        'nin', 'nın', 'nün', 'nun',             // tamlayan
        'den', 'dan', 'ten', 'tan',             // çıkma hali
        'de', 'da', 'te', 'ta',                 // bulunma hali
    ];
    for (const sfx of suffixes) {
        if (word.endsWith(sfx) && word.length - sfx.length >= 3) {
            return word.slice(0, -sfx.length);
        }
    }
    return word;
}

/* ==========================================================================
   📌 BAŞLIK: GERÇEK VEKTÖR SEMANTİK ARAMA VE BACKEND ENTEGRASYONU
   ========================================================================== */
async function searchViaBackend(queryText, userUniverse) {
    const q = queryText || '';
    const universe = userUniverse || 'MOVIES';
    if (!q.strip && !q.trim()) return null;

    const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
    await ensureSignedAuthToken();
    const signed = getSignedAuthToken();
    const headers = { 'Content-Type': 'application/json' };
    // GPT için yalnızca imzalı token; zayıf fallback GPT açmaz (sunucu tarafı)
    if (signed) headers['Authorization'] = `Bearer ${signed}`;

    const lib = (typeof getActiveLibrary === 'function') ? getActiveLibrary() : [];
    const libraryItemIds = (lib || []).map(i => i && i.id).filter(Boolean);

    try {
        const res = await fetch(`${baseUrl}/api/search`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                query: q,
                mediaType: universe,
                queryText: q,
                userUniverse: universe,
                libraryItemIds
            })
        });
        // 429 / hata: sessizce yerel motora düş (limit mesajı gösterme)
        if (!res.ok) return null;
        return await res.json();
    } catch (err) {
        console.warn("⚠️ Backend Vektör Sunucusuna bağlanılamadı, yerel NLP motoru devrede:", err);
        return null;
    }
}

async function getRecommendationsViaBackend(libraryItems, userUniverse, userQuery, includeOngoing) {
    const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
    const headers = { 'Content-Type': 'application/json' };
    const signed = getSignedAuthToken();
    if (signed) headers['Authorization'] = `Bearer ${signed}`;
    try {
        const hiddenIds = (userUniverse === 'MOVIES')
            ? (typeof HIDDEN_MOVIES_IDS !== 'undefined' ? HIDDEN_MOVIES_IDS : [])
            : (typeof HIDDEN_SERIES_IDS !== 'undefined' ? HIDDEN_SERIES_IDS : []);
        const res = await fetch(`${baseUrl}/api/recommendations`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                libraryItems: libraryItems || [],
                userUniverse,
                userQuery,
                hiddenItemIds: hiddenIds,
                includeOngoing: includeOngoing !== false
            })
        });
        if (!res.ok) return null;
        return await res.json();
    } catch(err) {
        console.warn("⚠️ Backend Vektör Sunucusuna bağlanılamadı, yerel NLP motoru devrede.");
        return null;
    }
}

async function getSocialRecommendationsViaBackend(userALibrary, userBLibrary, userUniverse, extra = {}) {
    const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
    const headers = { 'Content-Type': 'application/json' };
    const signed = getSignedAuthToken();
    if (signed) headers['Authorization'] = `Bearer ${signed}`;
    try {
        const res = await fetch(`${baseUrl}/api/social_recommendations`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                userALibrary: userALibrary || [],
                userBLibrary: userBLibrary || [],
                userASelected5: extra.userASelected5 || userALibrary || [],
                userBSelected5: extra.userBSelected5 || userBLibrary || [],
                userAFullLibrary: extra.userAFullLibrary || userALibrary || [],
                userBFullLibrary: extra.userBFullLibrary || userBLibrary || [],
                userAName: extra.userAName || '',
                userBName: extra.userBName || '',
                userUniverse
            })
        });
        if (!res.ok) return null;
        return await res.json();
    } catch(err) {
        console.warn("⚠️ Backend Sosyal Vektör Sunucusuna bağlanılamadı.");
        return null;
    }
}

/* ─── SİNONİM GENİŞLETME SÖZLÜĞÜ ─────────────────────────────────────────
   Kullanıcının yazdığı kelimeyi ilgili Türkçe/İngilizce eşdeğerlere çevirir.
   ─────────────────────────────────────────────────────────────────────── */
const SYNONYM_MAP = {
    "dedektif":     ["polisiye", "suç", "cinayet", "soruşturma", "detective"],
    "polisiye":     ["dedektif", "suç", "cinayet", "polis", "soruşturma"],
    "komik":        ["komedi", "güldürü", "mizah", "eğlenceli", "sitcom"],
    "eğlenceli":    ["komedi", "komik", "mizah", "hafif"],
    "bilimkurgu":   ["bilim kurgu", "bilim-kurgu", "sci-fi", "uzay", "distopya", "robot", "yapay zeka"],
    "uzay":         ["bilim kurgu", "bilim-kurgu", "galaksi", "uzay gemisi", "uzaylı"],
    "distopya":     ["bilim kurgu", "kıyamet sonrası", "post-apokaliptik", "gelecek"],
    "gerilim":      ["thriller", "gizem", "korku", "psikolojik", "süspans"],
    "psikolojik":   ["gerilim", "gizem", "zihinsel", "akıl", "korku"],
    "korku":        ["gerilim", "psikolojik", "dehşet", "canavar", "doğaüstü"],
    "savaş":        ["askeri", "ordu", "cephe", "dünya savaşı", "muharebe"],
    "askeri":       ["savaş", "ordu", "asker", "operasyon"],
    "aşk":          ["romantik", "romance", "dram", "duygusal", "sevgi", "ilişki"],
    "romantik":     ["aşk", "romance", "duygusal", "sevgi"],
    "macera":       ["aksiyon", "keşif", "yolculuk", "serüven"],
    "aksiyon":      ["macera", "kavga", "dövüş", "patlama", "kovalamaca"],
    "zombi":        ["ölümsüz", "salgın", "apocalypse", "kıyamet", "walkers", "enfekte"],
    "vampir":       ["doğaüstü", "karanlık", "gotik", "kan", "ölümsüz"],
    "ajan":         ["casusluk", "cia", "fbi", "gizli görev", "spy", "istihbarat"],
    "casusluk":     ["ajan", "spy", "gizli", "operasyon", "cia", "fbi"],
    "tarih":        ["tarihi", "dönem", "antik", "ortaçağ", "imparatorluk", "osmanlı"],
    "tarihi":       ["tarih", "dönem", "antik", "ortaçağ", "geçmiş"],
    // ortaçağ: "krallık" / yalnız "şövalye" başlık tuzağını (Ay Şövalyesi, Vahşi Krallık) üretmesin
    "ortaçağ":      ["tarihi", "feodal", "medieval", "orta çağ", "kale", "şövalye dönemi", "period drama"],
    "ortacag":      ["ortaçağ", "tarihi", "feodal", "medieval", "kale"],
    "fantastik":    ["büyü", "sihir", "ejderha", "mitoloji", "elf", "vampir", "doğaüstü"],
    "büyü":         ["fantastik", "sihir", "cadı", "büyücü", "doğaüstü"],
    "hapishane":    ["cezaevi", "mahkum", "koğuş", "gardiyan", "hücre", "parmaklık", "prison", "inmate", "penitentiary"],
    "beyinyakan":   ["mind-bending", "nonlinear", "paradoks", "plot twist", "zihin bükücü", "kafa karıştırıcı"],
    "zihin":        ["mind-bending", "psikolojik", "paradoks"],

    "suç":          ["polisiye", "dedektif", "cinayet", "mafya", "çete", "organize"],
    "mafya":        ["suç", "organize suç", "çete", "gangster", "kartel"],
    "hukuk":        ["avukat", "mahkeme", "dava", "adalet", "savcı"],
    "tıbbi":        ["doktor", "hastane", "cerrah", "ameliyat", "medikal"],
    "doktor":       ["tıbbi", "hastane", "cerrah", "sağlık"],
    "okul":         ["kampüs", "öğrenci", "üniversite", "lise", "sınıf"],
    "gençlik":      ["genç", "okul", "lise", "üniversite", "büyüme"],
    "aile":         ["çocuk", "ebeveyn", "anne", "baba", "kardeş", "ev"],
    "çocuk":        ["aile", "animasyon", "çizgi", "genç", "büyüme"],
    "animasyon":    ["çizgi film", "anime", "çizgi dizi", "canlandırma"],
    "anime":        ["animasyon", "japon", "çizgi dizi", "manga"],
    "belgesel":     ["gerçek", "true story", "gerçek olaylar", "documentary"],
    "gerçek":       ["belgesel", "true story", "gerçek hikaye", "biyografi"],
    "biyografi":    ["gerçek", "hayat hikayesi", "belgesel", "true story"],
    "müzik":        ["müzikal", "rock", "pop", "konser", "şarkı", "sanatçı"],
    "spor":         ["futbol", "basketbol", "boks", "yarış", "şampiyonluk"],
    "yemek":        ["gastronomi", "şef", "mutfak", "restoran", "aşçı"],
    "doğaüstü":     ["hayalet", "paranormal", "supernatural", "ruh", "şeytan"],
    "hayalet":      ["doğaüstü", "paranormal", "korku", "ruh", "ölü"],
    "robot":        ["bilim kurgu", "yapay zeka", "android", "makine"],
    "yapay zeka":   ["robot", "bilim kurgu", "teknoloji", "android", "algoritma"],
    "politika":     ["siyaset", "hükümet", "seçim", "parti", "devlet"],
    "intikam":      ["öç", "hesaplaşma", "vendetta", "adalet", "ceza"],
    "kıyamet":      ["apocalypse", "distopya", "salgın", "zombi", "hayatta kalma"],
    "hayatta kalma":["survival", "kıyamet", "salgın", "mahsur", "ada"],
    "karanlık":     ["noir", "distopya", "kasvetli", "psikolojik", "karamsar", "gotik"],
    "nostaljik":    ["retro", "geçmiş", "80ler", "90lar", "vintage", "eski"],
    "komedi":       ["komik", "güldürü", "mizah", "eğlenceli", "sitcom"],
    "dram":         ["dramatik", "duygusal", "ağır", "ciddi", "trajedi"],
    "netflix":      ["netflix"],
    "amazon":       ["amazon prime", "prime video"],
    "disney":       ["disney plus", "disney+"],
    "hbo":          ["hbo max", "max"],
    "tv+":          ["tv+", "turkcell"],
};

function expandQueryTokens(tokens) {
    const expanded = new Set();
    tokens.forEach(t => {
        // Önce orijinal token
        expanded.add(t);
        // Sinonim genişletme (orijinal kelime)
        const syn1 = SYNONYM_MAP[t];
        if (syn1) syn1.forEach(s => expanded.add(s));
        // Kök forma indir ve tekrar sinonim ara
        const stemmed = turkishStem(t);
        if (stemmed !== t) {
            expanded.add(stemmed);
            const syn2 = SYNONYM_MAP[stemmed];
            if (syn2) syn2.forEach(s => expanded.add(s));
        }
    });
    return [...expanded];
}

/** Arama cümlesinde açıkça geçen türler — hepsi yapımda olmalı (dram + zombi vb.) */
const SEARCH_QUERY_GENRE_ALIASES = {
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

/** Bağlam kelimeleri — sorguda varsa yapım metninde de olmalı (okulda geçen gizem vb.) */
const SEARCH_QUERY_ANCHOR_LEXICON = {
    okul: ['okul', 'school', 'kampüs', 'kampus', 'lise', 'üniversite', 'universite', 'campus', 'öğrenci', 'ogrenci', 'sınıf', 'sinif', 'akademi', 'yurt', 'high school', 'boarding school'],
    zombi: ['zombi', 'zombie', 'ölü yürüyen', 'walking dead', 'enfekte', 'infected', 'walkers', 'salgın'],
    hapishane: ['hapishane', 'cezaevi', 'prison', 'mahkum', 'koğuş', 'parmaklık', 'inmate'],
    ortacag: ['ortaçağ', 'ortacag', 'medieval', 'feodal', 'feudal', 'middle ages', 'şövalye', 'sovalye', 'viking']
};

const SEARCH_ANCHOR_QUERY_TRIGGERS = {
    okul: ['okul', 'okulda', 'school', 'kampüs', 'kampus', 'lise', 'üniversite', 'universite', 'campus'],
    zombi: ['zombi', 'zombie', 'ölü yürüyen'],
    hapishane: ['hapishane', 'cezaevi', 'prison', 'mahkum'],
    ortacag: ['ortaçağ', 'ortacag', 'medieval', 'feodal', 'feudal']
};

function normalizeSearchText(text) {
    return String(text || '')
        .toLowerCase()
        .replace(/ı/g, 'i').replace(/ğ/g, 'g').replace(/ü/g, 'u')
        .replace(/ş/g, 's').replace(/ö/g, 'o').replace(/ç/g, 'c');
}

function extractRequiredGenresFromSearchQuery(query) {
    const q = String(query || '').toLowerCase();
    const qNorm = normalizeSearchText(q);
    const required = [];
    Object.entries(SEARCH_QUERY_GENRE_ALIASES).forEach(([genreKey, aliases]) => {
        const hit = aliases.some(alias => {
            const a = alias.toLowerCase();
            return q.includes(a) || qNorm.includes(normalizeSearchText(a));
        });
        if (hit) required.push(genreKey);
    });
    return required;
}

function extractRequiredAnchorsFromSearchQuery(query) {
    const q = String(query || '').toLowerCase();
    const qNorm = normalizeSearchText(q);
    const anchors = [];
    Object.entries(SEARCH_ANCHOR_QUERY_TRIGGERS).forEach(([anchorKey, triggers]) => {
        const hit = triggers.some(tr => q.includes(tr) || qNorm.includes(normalizeSearchText(tr)));
        if (hit) anchors.push(anchorKey);
    });
    return anchors;
}

function getItemSearchableText(item) {
    const genresStr = (Array.isArray(item.genres) ? item.genres.join(' ') : String(item.genres || '')).toLowerCase();
    const whyStr = Array.isArray(item.why_watch) ? item.why_watch.join(' ') : String(item.why_watch || '');
    const platStr = item.platform || (Array.isArray(item.platforms) ? item.platforms.join(' ') : (item.platforms || ''));
    return normalizeSearchText([
        item.title, item.summary, genresStr, item.duo, item.cast, item.director,
        item.yonetmen, item.oyuncular, whyStr, platStr, item.keywords
    ].filter(Boolean).join(' '));
}

function itemMatchesSearchGenreRequirements(item, requiredGenres) {
    if (!requiredGenres || !requiredGenres.length) return true;
    const text = getItemSearchableText(item);
    return requiredGenres.every(g => text.includes(g));
}

function itemMatchesSearchAnchorRequirements(item, requiredAnchors) {
    if (!requiredAnchors || !requiredAnchors.length) return true;
    const text = getItemSearchableText(item);
    const titleLow = String(item.title || '').toLowerCase();

    return requiredAnchors.every(anchorKey => {
        const tokens = SEARCH_QUERY_ANCHOR_LEXICON[anchorKey] || [];
        if (tokens.some(t => text.includes(normalizeSearchText(t)))) return true;

        // Zombi: "Kingdom" (Kore) evet, "The Last Kingdom" hayır
        if (anchorKey === 'zombi') {
            if (/last kingdom/.test(titleLow)) return false;
            if (titleLow === 'kingdom' || titleLow === 'krallik' || titleLow === 'krallık') {
                return text.includes('zombi') || text.includes('zombie');
            }
        }
        return false;
    });
}

/** Yerel + backend arama sonuçlarında niyet filtreleri */
function applySearchIntentFilters(query, items) {
    if (!query || !Array.isArray(items) || !items.length) return items || [];
    const requiredGenres = extractRequiredGenresFromSearchQuery(query);
    const requiredAnchors = extractRequiredAnchorsFromSearchQuery(query);
    if (!requiredGenres.length && !requiredAnchors.length) return items;

    return items.filter(item =>
        itemMatchesSearchGenreRequirements(item, requiredGenres)
        && itemMatchesSearchAnchorRequirements(item, requiredAnchors)
    );
}

function processNaturalLanguageQuery(rawQuery, dataset) {
    if (!rawQuery) return { isNonsense: false, matches: dataset };

    const lowerRaw = rawQuery.toLowerCase().trim();
    if (!lowerRaw) return { isNonsense: false, matches: dataset };

    let negativeTerms = [];
    let positivePromptText = lowerRaw;

    const negationMatch = lowerRaw.match(/(?:ama|fakat|lütfen|olmasın|olmayan|dışında|haricinde|değil)\s+(.*)/);
    if (negationMatch && (lowerRaw.includes('olmasın') || lowerRaw.includes('olmayan') || lowerRaw.includes('değil') || lowerRaw.includes('haricinde'))) {
        const negPart = negationMatch[1];
        negativeTerms = negPart.split(/[^\wığüşöçİĞÜŞÖÇ0-9]+/).filter(w => w.length >= 2 && !TURKISH_STOP_WORDS.has(w));
        positivePromptText = lowerRaw.replace(negPart, '').replace(/olmasın|olmayan|değil|haricinde|ama/g, '');
    }

    const rawTokens = positivePromptText.split(/[^\wığüşöçİĞÜŞÖÇ0-9]+/).filter(w => w.length >= 2);
    // 🆕 Önce kök formuna indir, sonra stop word filtrele
    const stemmedTokens = rawTokens.map(w => turkishStem(w));
    const meaningfulTokens = stemmedTokens.filter(w => !TURKISH_STOP_WORDS.has(w));
    let baseTokens = meaningfulTokens.length > 0 ? meaningfulTokens : stemmedTokens.filter(w => w.length >= 2);

    // Çok kelimeli tema: "beyin yakan" → tekil "beyin" başlık tuzağını (Beyin Avcıları) kes
    const phraseSkipTokens = new Set();
    const forcedPhrases = [];
    const THEME_PHRASES = [
        'beyin yakan', 'zihin bükücü', 'zihin bukucu', 'kafa karıştıran', 'kafa karistiran',
        'mind bending', 'mind-bending', 'zaman yolculuğu', 'zaman yolculugu',
        'bilim kurgu', 'vahşi batı', 'vahsi bati'
    ];
    THEME_PHRASES.forEach(ph => {
        if (lowerRaw.includes(ph)) {
            forcedPhrases.push(ph);
            ph.split(/\s+/).forEach(t => {
                if (t.length >= 2) phraseSkipTokens.add(turkishStem(t));
            });
        }
    });
    if (phraseSkipTokens.size > 0) {
        baseTokens = baseTokens.filter(t => !phraseSkipTokens.has(t));
        // Tema kelimelerini kontrollü geri ekle (geniş eşleşme için)
        if (forcedPhrases.some(p => p.includes('beyin') || p.includes('zihin') || p.includes('mind') || p.includes('kafa'))) {
            ['mind-bending', 'nonlinear', 'paradoks', 'plot', 'twist', 'psikolojik'].forEach(t => baseTokens.push(t));
        }
    }

    const searchTokens = expandQueryTokens(baseTokens);

    let phrases = [...forcedPhrases];
    for (let i = 0; i < baseTokens.length - 1; i++) {
        phrases.push(baseTokens[i] + " " + baseTokens[i+1]);
    }

    const N = dataset.length;
    let tokenIDF = {};
    searchTokens.forEach(t => {
        let df = 0;
        dataset.forEach(item => {
            const whyText = Array.isArray(item.why_watch) ? item.why_watch.join(' ') : '';
            const platText = item.platform || (Array.isArray(item.platforms) ? item.platforms.join(' ') : (item.platforms || ''));
            const itemText = `${item.title || ''} ${item.summary || ''} ${Array.isArray(item.genres) ? item.genres.join(' ') : (item.genres || '')} ${whyText} ${platText}`.toLowerCase();
            if (itemText.includes(t)) df++;
        });
        tokenIDF[t] = Math.log(1 + (N / (df + 1)));
    });

    let scoredItems = [];
    let maxPossibleScore = 0;

    dataset.forEach(item => {
        const itemTitleLower = (item.title || '').toLowerCase();
        const itemSummaryLower = (item.summary || '').toLowerCase();
        const itemGenresLower = Array.isArray(item.genres) ? item.genres.map(g => g.toLowerCase()) : [(item.genres || '').toLowerCase()];
        const itemDuoLower = (item.duo || '').toLowerCase();
        const itemDirectorLower = (item.director || item.yonetmen || '').toLowerCase();
        const itemCastLower = (item.cast || item.oyuncular || '').toLowerCase();
        const itemWhyWatchLower = Array.isArray(item.why_watch) ? item.why_watch.join(' ').toLowerCase() : '';
        const itemPlatformLower = (item.platform || (Array.isArray(item.platforms) ? item.platforms.join(' ') : (item.platforms || ''))).toLowerCase();

        const fullItemText = `${itemTitleLower} ${itemSummaryLower} ${itemGenresLower.join(' ')} ${itemDuoLower} ${itemCastLower} ${itemDirectorLower} ${itemWhyWatchLower} ${itemPlatformLower}`;

        if (negativeTerms.length > 0) {
            const hasNegHit = negativeTerms.some(neg => fullItemText.includes(neg));
            if (hasNegHit) return;
        }

        if (itemTitleLower === lowerRaw) {
            scoredItems.push({ item, rawScore: 999 });
            return;
        } else if (itemTitleLower.startsWith(lowerRaw)) {
            scoredItems.push({ item, rawScore: 950 });
            return;
        } else if (itemTitleLower.includes(lowerRaw)) {
            scoredItems.push({ item, rawScore: 900 });
            return;
        }

        let itemScore = 0.0;
        let matchedTokenCount = 0;

        phrases.forEach(phrase => {
            if (itemTitleLower.includes(phrase)) itemScore += 16.0;
            else if (fullItemText.includes(phrase)) itemScore += 9.0;
        });

        // Zorunlu tema cümleleri (beyin yakan…): başlık/özette yoksa cezalandır
        if (forcedPhrases.length > 0) {
            const hasThemeSignal = forcedPhrases.some(ph => fullItemText.includes(ph))
                || ['mind-bending', 'nonlinear', 'paradoks', 'zaman döngüsü', 'rüya', 'gerçeklik', 'simülasyon']
                    .some(k => fullItemText.includes(k))
                || (typeof CONCEPT_THEMES !== 'undefined' && CONCEPT_THEMES.some(th =>
                    (th.triggers || []).some(tr => lowerRaw.includes(tr))
                    && (th.titleHints || []).some(h => itemTitleLower.includes(String(h).toLowerCase()))
                ));
            if (!hasThemeSignal) {
                // Sadece "beyin" geçen alakasız başlıkları (Beyin Avcıları) ele
                itemScore *= 0.15;
            } else {
                itemScore += 22.0;
            }
        }

        searchTokens.forEach(t => {
            let tScore = 0.0;
            const idf = tokenIDF[t] || 1.0;

            if (itemTitleLower.includes(t))                                                      tScore += 8.0 * idf;
            if (itemGenresLower.some(g => g.includes(t)))                                        tScore += 4.5 * idf;
            if (itemPlatformLower.includes(t))                                                   tScore += 4.0 * idf;
            if (itemDuoLower.includes(t) || itemCastLower.includes(t) || itemDirectorLower.includes(t)) tScore += 3.0 * idf;
            if (itemSummaryLower.includes(t))                                                    tScore += 1.6 * idf;
            if (itemWhyWatchLower.includes(t))                                                   tScore += 1.2 * idf;

            if (tScore > 0) {
                itemScore += tScore;
                matchedTokenCount++;
            }
        });

        if (matchedTokenCount === 0 || itemScore <= 0) return;

        if (itemScore > maxPossibleScore) maxPossibleScore = itemScore;
        scoredItems.push({ item, rawScore: itemScore });
    });

    if (scoredItems.length === 0) return { isNonsense: true, matches: [] };

    const threshold = maxPossibleScore * 0.15;
    scoredItems = scoredItems.filter(x => x.rawScore >= threshold || x.rawScore >= 900);

    if (scoredItems.length === 0) return { isNonsense: true, matches: [] };

    scoredItems.sort((a, b) => b.rawScore - a.rawScore);

    const maxRaw = scoredItems[0].rawScore;
    const minRaw = scoredItems[scoredItems.length - 1].rawScore;
    const rangeRaw = Math.max(1.0, maxRaw - minRaw);

    // 🆕 Mutlak kalite tavanı: ham skor düşükse maksimum gösterilecek % sınırlanır
    // Böylece zayıf sonuçlar asla %99 görmez — gerçekçi uyum skoru
    let maxDisplayPct;
    if      (maxRaw >= 30.0) maxDisplayPct = 99; // güçlü eşleşme → tam aralık
    else if (maxRaw >= 15.0) maxDisplayPct = 88; // orta eşleşme  → max %88
    else if (maxRaw >= 8.0)  maxDisplayPct = 75; // zayıf eşleşme → max %75
    else if (maxRaw >= 4.0)  maxDisplayPct = 62; // çok zayıf     → max %62
    else                     maxDisplayPct = 50; // alakasız      → max %50

    let matches = scoredItems.map((x) => {
            const mapped = { ...x.item };
            if (x.rawScore >= 900) {
                mapped.aiMatchScore = x.rawScore >= 990 ? 99 : (x.rawScore >= 950 ? 97 : 94);
            } else {
                const ratio = (x.rawScore - minRaw) / rangeRaw; // 0.0 – 1.0
                const minDisplayPct = Math.max(35, maxDisplayPct - 30); // alt taban
                const normPct = Math.round(minDisplayPct + (ratio * (maxDisplayPct - minDisplayPct)));
                mapped.aiMatchScore = Math.min(maxDisplayPct, Math.max(35, normPct));
            }
            // Not burada doldurulmaz — capExploreAiReasons en fazla 10'a yazar
            mapped.aiReason = '';
            return mapped;
        });

    matches = applySearchIntentFilters(rawQuery, matches);

    return {
        isNonsense: matches.length === 0,
        matches
    };
}

const MAX_AI_MATCH_NOTES = 10;

/** Keşfet listesinde AI eşleşme notunu en fazla N yapımda tutar; kalanlardan siler.
 *  Misafir kullanıcıda not üretilmez / gösterilmez (GPT yalnızca kayıtlı üye). */
function capExploreAiReasons(items, query, maxNotes = MAX_AI_MATCH_NOTES) {
    if (!Array.isArray(items) || items.length === 0) return items || [];
    if (!isUserLoggedInStrict()) {
        return items.map(item => {
            if (!item.aiReason) return item;
            const copy = { ...item };
            copy.aiReason = '';
            return copy;
        });
    }
    const ranked = items
        .map((item, idx) => ({
            item,
            idx,
            score: Number(item.hybridScore) || Number(item.aiMatchScore) || 0
        }))
        .sort((a, b) => b.score - a.score || a.idx - b.idx);

    const keepIds = new Set(ranked.slice(0, maxNotes).map(x => String(x.item.id)));

    return items.map(item => {
        const id = String(item.id);
        if (!keepIds.has(id)) {
            if (item.aiReason) {
                const copy = { ...item };
                copy.aiReason = '';
                return copy;
            }
            return item;
        }
        const hasNote = item.aiReason && String(item.aiReason).trim();
        if (hasNote) return item;
        // Yerel fallback notu yalnızca girişli kullanıcıda (GPT yoksa)
        const note = buildItemSpecificAiReason(item, query, item.aiMatchScore);
        if (!note) return item;
        return { ...item, aiReason: note };
    });
}

/** Arama sonucu için diziye/filme özgü kısa AI notu — kullanıcı aramasına göre şekillenir */
function buildItemSpecificAiReason(item, query, score) {
    if (!item) return '';
    const title = (item.title || '').trim();
    if (!title) return '';
    const genres = Array.isArray(item.genres)
        ? item.genres.filter(Boolean).slice(0, 2).join(' / ')
        : String(item.genres || '').split(',')[0].trim();
    const why = Array.isArray(item.why_watch) ? String(item.why_watch[0] || '').trim() : '';
    const summary = String(item.summary || '').trim();
    const q = String(query || '').trim();
    const pct = Number(score) || '';
    if (!q) return '';

    const qLow = q.toLowerCase();
    const blob = `${summary} ${Array.isArray(item.why_watch) ? item.why_watch.join(' ') : ''} ${genres}`.toLowerCase();
    const intentHooks = {
        zombi: ['zombi', 'zombie', 'salgın', 'apocalypse', 'enfekte', 'hayatta kalma', 'walking dead'],
        hapishane: ['hapishane', 'cezaevi', 'mahkum', 'kaçış', 'koğuş'],
        ortaçağ: ['ortaçağ', 'medieval', 'şövalye', 'krallık', 'feodal'],
        polisiye: ['polis', 'dedektif', 'cinayet', 'soruşturma'],
        korku: ['korku', 'dehşet', 'psikolojik', 'gerilim'],
        komedi: ['komedi', 'mizah', 'komik']
    };
    let found = [];
    for (const [key, hooks] of Object.entries(intentHooks)) {
        if (qLow.includes(key) || hooks.slice(0, 3).some(h => qLow.includes(h))) {
            for (const h of hooks) {
                if (blob.includes(h) && !found.includes(h)) found.push(h);
                if (found.length >= 2) break;
            }
        }
        if (found.length >= 2) break;
    }

    let snippet = '';
    if (summary.length > 28) {
        const parts = summary.split(/[.!?]+/).map(s => s.trim()).filter(s => s.length >= 28);
        snippet = (found.length
            ? (parts.find(p => found.some(f => p.toLowerCase().includes(f))) || parts[0] || summary)
            : (parts[0] || summary));
        if (snippet.length > 100) snippet = snippet.slice(0, 97).replace(/\s+\S*$/, '') + '…';
    }

    if (found.length && snippet) {
        return `"${q}" aramanız için ${title}: ${found.join(', ')} izleri taşıyor — ${snippet}`;
    }
    if (snippet) {
        return `"${q}" aramanız için ${title} önerildi çünkü: ${snippet}`;
    }
    if (genres && found.length) {
        return `"${q}" aramanız için ${title} seçildi; ${genres} + ${found[0]} dokusu aramanızla örtüşüyor.`;
    }
    if (genres) {
        return pct
            ? `"${q}" aramanız için ${title} (${genres}) tematik olarak yakın duruyor (%${pct}).`
            : `"${q}" aramanız için ${title} (${genres}) tematik olarak yakın duruyor.`;
    }
    // why_watch yalnızca arama bağlamı kurulamadığında yedek
    if (why && why.length > 25 && !/^aradığınız/i.test(why)) {
        const shortWhy = why.length > 120 ? why.slice(0, 117) + '…' : why;
        return `"${q}" aramanızla bağlantılı: ${shortWhy}`;
    }
    return '';
}

/**
 * Temalı aramada bilinen başlık + anahtar kelime adaylarını havuza ekler.
 * Film + dizi evreninde aynı mantık; multi-word tetikleyiciler (beyin yakan…) desteklenir.
 */
function enrichMatchesWithThemeHints(query, dataset, existingMatches) {
    const q = String(query || '').toLowerCase().trim();
    const qNorm = q.replace(/ı/g, 'i').replace(/ğ/g, 'g').replace(/ü/g, 'u').replace(/ş/g, 's').replace(/ö/g, 'o').replace(/ç/g, 'c');
    if (!q || !Array.isArray(dataset) || !dataset.length) return existingMatches || [];

    const themes = (typeof CONCEPT_THEMES !== 'undefined' && Array.isArray(CONCEPT_THEMES))
        ? CONCEPT_THEMES.filter(th => {
            const triggers = th.triggers || [];
            if (triggers.some(tr => q.includes(tr) || qNorm.includes(String(tr).replace(/ı/g,'i').replace(/ğ/g,'g').replace(/ü/g,'u').replace(/ş/g,'s').replace(/ö/g,'o').replace(/ç/g,'c')))) {
                return true;
            }
            if ((th.keywords || []).some(kw => kw.length >= 4 && q.includes(kw))) return true;
            if (q.includes(th.id)) return true;
            return false;
          })
        : [];

    if (themes.length === 0) return existingMatches || [];

    const have = new Set((existingMatches || []).map(m => String(m.id)));
    const extra = [];

    dataset.forEach(item => {
        if (!item || item.id == null || have.has(String(item.id))) return;
        const titleLow = (item.title || '').toLowerCase();
        const summaryLow = (item.summary || '').toLowerCase();
        const genresStr = (Array.isArray(item.genres) ? item.genres.join(' ') : String(item.genres || '')).toLowerCase();
        const whyLow = Array.isArray(item.why_watch) ? item.why_watch.join(' ').toLowerCase() : '';
        const kwLow = String(item.keywords || '').toLowerCase();
        const full = `${titleLow} ${summaryLow} ${genresStr} ${whyLow} ${kwLow}`;

        for (const th of themes) {
            if (Array.isArray(th.excludeIf) && th.excludeIf.some(ex => full.includes(ex))) continue;
            if (/last kingdom/.test(titleLow) && (th.id === 'zombi_apokalips' || (th.triggers || []).some(t => t.includes('zombi')))) continue;

            const titleHit = (th.titleHints || []).some(h => {
                const hint = String(h || '').toLowerCase();
                if (!hint) return false;
                if (titleLow === hint) return true;
                if (hint.length <= 3) {
                    return new RegExp(`(?:^|[\\s\\-:/])${hint.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}(?:$|[\\s\\-:/])`).test(titleLow);
                }
                return titleLow.includes(hint);
            });

            let kwHits = 0;
            (th.keywords || []).forEach(kw => {
                if (kw.length < 4) return; // "beyin" tek başına yetmez
                if (full.includes(kw)) kwHits += 1;
            });

            // Bilinen başlık VEYA en az 2 güçlü tema kelimesi
            if (titleHit || kwHits >= 2) {
                const score = titleHit ? 93 : Math.min(90, 60 + kwHits * 8);
                const mapped = { ...item, aiMatchScore: score, aiReason: '' };
                extra.push(mapped);
                have.add(String(item.id));
                break;
            }
        }
    });

    const merged = [...(existingMatches || []), ...extra]
        .filter(item => {
            if (!item) return false;
            const titleLow = (item.title || '').toLowerCase();
            const full = `${titleLow} ${(item.summary || '').toLowerCase()}`;
            return !themes.some(th =>
                Array.isArray(th.excludeIf) && th.excludeIf.some(ex => full.includes(ex))
            );
        });
    merged.sort((a, b) => (b.aiMatchScore || 0) - (a.aiMatchScore || 0));
    return merged;
}

function formatPlatformBadge(platformStr) {
    if (!platformStr) return 'Diğer Platform';
    let parts = String(platformStr).split(',').map(s => s.trim()).filter(Boolean);

    let unique = [];
    parts.forEach(p => {
        let name = p;
        if (p.includes('Amazon') || p.includes('Prime')) name = 'Amazon Prime';
        else if (p.includes('Disney')) name = 'Disney+';
        else if (p.includes('Netflix')) name = 'Netflix';
        else if (p.includes('HBO') || p.includes('Max')) name = 'HBO Max';
        else if (p.includes('Apple')) name = 'Apple TV+';
        else if (p.includes('Diğer')) name = 'Diğer Platform';

        if (!unique.includes(name)) unique.push(name);
    });

    if (unique.length > 1 && unique.includes('Diğer Platform')) {
        unique = unique.filter(u => u !== 'Diğer Platform');
    }

    if (unique.length === 0) return 'Diğer Platform';
    if (unique.length <= 2) return unique.join(', ');
    return `${unique[0]}, ${unique[1]} (+${unique.length - 2} diğer)`;
}

function normalizePlatformName(raw) {
    const p = String(raw || '').trim();
    if (!p) return 'Diğer Platform';
    if (/amazon|prime/i.test(p)) return 'Amazon Prime';
    if (/disney/i.test(p)) return 'Disney+';
    if (/netflix/i.test(p)) return 'Netflix';
    if (/hbo|\bmax\b/i.test(p)) return 'HBO Max';
    if (/apple/i.test(p)) return 'Apple TV+';
    if (/diğer|diger|other/i.test(p)) return 'Diğer Platform';
    return p;
}

function buildPlatformWatchUrl(platformName, title) {
    const rawTitle = String(title || '').trim() || 'film';
    const q = encodeURIComponent(rawTitle);
    const google = `https://www.google.com/search?q=${encodeURIComponent(`${rawTitle} türkçe altyazılı izle`)}`;
    const norm = String(platformName || '').toLowerCase();

    if (/amazon|prime/.test(norm)) {
        return `https://www.primevideo.com/search/ref=atv_nb_sr?phrase=${q}`;
    }
    if (/netflix/.test(norm)) {
        return `https://www.netflix.com/search?q=${q}`;
    }
    if (/disney/.test(norm)) {
        return `https://www.disneyplus.com/browse/search?query=${q}`;
    }
    if (/hbo|\bmax\b/.test(norm)) {
        return `https://play.max.com/search?q=${q}`;
    }
    if (/apple/.test(norm)) {
        return `https://tv.apple.com/search?term=${q}`;
    }
    return google;
}

/** Platform adlarını tıklanabilir linklere çevirir (yeni sekme). */
function formatPlatformLinks(platformStr, title) {
    const rawParts = String(platformStr || '')
        .split(',')
        .map(s => s.trim())
        .filter(Boolean)
        .map(normalizePlatformName);

    let unique = [];
    rawParts.forEach(name => {
        if (!unique.includes(name)) unique.push(name);
    });
    if (unique.length > 1 && unique.includes('Diğer Platform')) {
        unique = unique.filter(u => u !== 'Diğer Platform');
    }
    if (unique.length === 0) unique = ['Diğer Platform'];

    const googleUrl = buildPlatformWatchUrl('Diğer Platform', title);
    const visible = unique.slice(0, 2);
    const rest = unique.slice(2);

    const linkHtml = (name) => {
        const url = buildPlatformWatchUrl(name, title);
        return `<a class="platform-link" href="${url}" target="_blank" rel="noopener noreferrer">${escapeHtml(name)}</a>`;
    };

    let html = visible.map(linkHtml).join(', ');
    if (rest.length > 0) {
        html += ` (<a class="platform-link platform-link-other" href="${googleUrl}" target="_blank" rel="noopener noreferrer">+${rest.length} diğer</a>)`;
    }
    return html;
}

function normalizeMediaIdKey(id) {
    // Backend: movies_122 / series_1399  |  Frontend dataset: movie_122 / series_1399
    return String(id == null ? '' : id).replace(/^(series_|movies_|movie_)/i, '');
}

function idsLooselyEqual(a, b) {
    if (a == null || b == null) return false;
    const sa = String(a);
    const sb = String(b);
    if (sa === sb) return true;
    return normalizeMediaIdKey(sa) === normalizeMediaIdKey(sb);
}

function setExplorePaginationVisible(visible) {
    const box = document.getElementById('pagination-container');
    if (!box) return;
    if (visible) box.removeAttribute('hidden');
    else box.setAttribute('hidden', '');
}

/**
 * Numaralı sayfalama dizisi üretir.
 * Mantık: her zaman ilk + son sayfa; ortada aktif sayfanın ±1 komşusu; boşluklarda "…".
 * Örn. (5/10) → [1, '…', 4, 5, 6, '…', 10]
 */
function buildPageNumberItems(current, total) {
    if (total <= 1) return [1];
    if (total <= 5) {
        return Array.from({ length: total }, (_, i) => i + 1);
    }

    let windowStart = Math.max(1, current - 1);
    let windowEnd = Math.min(total, current + 1);

    // Kenarda 3’lü pencereyi doldur (1. sayfada 1-2-3, sonda n-2..n)
    if (windowEnd - windowStart + 1 < 3) {
        if (windowStart === 1) windowEnd = Math.min(total, 3);
        else if (windowEnd === total) windowStart = Math.max(1, total - 2);
    }

    const items = [];
    const pushUnique = (v) => {
        if (items[items.length - 1] !== v) items.push(v);
    };

    pushUnique(1);

    if (windowStart > 2) {
        pushUnique('…');
    }

    for (let p = windowStart; p <= windowEnd; p++) {
        if (p !== 1 && p !== total) pushUnique(p);
        else if (p === 1) pushUnique(1);
        else if (p === total) pushUnique(total);
    }

    if (windowEnd < total - 1) {
        pushUnique('…');
    }

    if (total > 1) pushUnique(total);

    return items;
}

/**
 * Ortak numaralı sayfalama renderer.
 * Sol/sağ oklar: bir sayfa geri / ileri.
 * @returns {boolean} true = birden fazla sayfa var ve butonlar çizildi
 */
function fillNumberedPaginationNav(navIdOrEl, current, totalPages, goToFnName) {
    const nav = (typeof navIdOrEl === 'string')
        ? document.getElementById(navIdOrEl)
        : navIdOrEl;
    if (!nav) return false;

    if (totalPages <= 1) {
        nav.innerHTML = '';
        return false;
    }

    const items = buildPageNumberItems(current, totalPages);
    const prevDisabled = current <= 1;
    const nextDisabled = current >= totalPages;

    const prevBtn = `<button type="button" class="page-num-btn page-nav-btn${prevDisabled ? ' is-disabled' : ''}" ${prevDisabled ? 'disabled' : ''} onclick="${goToFnName}(${current - 1})" aria-label="Önceki sayfa"><i class="fa-solid fa-chevron-left"></i></button>`;
    const nextBtn = `<button type="button" class="page-num-btn page-nav-btn${nextDisabled ? ' is-disabled' : ''}" ${nextDisabled ? 'disabled' : ''} onclick="${goToFnName}(${current + 1})" aria-label="Sonraki sayfa"><i class="fa-solid fa-chevron-right"></i></button>`;

    const pageBtns = items.map((item) => {
        if (item === '…') {
            return `<span class="page-ellipsis" aria-hidden="true">…</span>`;
        }
        const isActive = item === current;
        return `<button type="button" class="page-num-btn${isActive ? ' is-active' : ''}" data-page="${item}" onclick="${goToFnName}(${item})" aria-label="Sayfa ${item}"${isActive ? ' aria-current="page"' : ''}>${item}</button>`;
    }).join('');

    nav.innerHTML = prevBtn + pageBtns + nextBtn;
    return true;
}

function renderExplorePagination(totalPages) {
    const shown = fillNumberedPaginationNav('numbered-pagination', currentPage, totalPages, 'goToExplorePage');
    const meta = document.getElementById('page-info-text');
    if (meta) {
        meta.textContent = shown ? `Sayfa ${currentPage} / ${totalPages}` : '';
    }
    setExplorePaginationVisible(shown);
}

function goToExplorePage(page) {
    const target = parseInt(page, 10);
    if (!Number.isFinite(target) || target < 1 || target === currentPage) return;
    currentPage = target;
    renderContentCards();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function passesExploreSidebarFilters(item, opts) {
    const {
        minRating, minYear, maxSeasons, minVotes, onlyEnded,
        selectedLanguage, selectedGenre, selectedPlatform
    } = opts;

    if (typeof item.rating_num === 'number' && item.rating_num < minRating) return false;
    if (item.year && item.year < minYear) return false;
    if (currentUniverse === 'SERIES' && item.seasons_num && item.seasons_num > maxSeasons) return false;
    if (typeof item.votes_num === 'number' && item.votes_num < minVotes) return false;
    if (onlyEnded && item.status && !item.status.includes('Bitmiş') && !item.status.includes('Final')) return false;

    if (selectedLanguage !== 'ALL') {
        const itemLang = (item.language || 'en').toLowerCase().trim();
        if (itemLang !== selectedLanguage.toLowerCase()) return false;
    }

    if (selectedGenre !== 'ALL') {
        const genresArr = Array.isArray(item.genres) ? item.genres : [item.genres || ''];
        const gJoined = genresArr.join(' ').toLowerCase();
        if (selectedGenre === 'Aksiyon & Macera') {
            if (!genresArr.includes('Aksiyon') && !genresArr.includes('Macera') &&
                !genresArr.includes('Aksiyon & Macera') && !gJoined.includes('aksiyon') && !gJoined.includes('macera')) {
                return false;
            }
        } else if (selectedGenre === 'Bilim Kurgu & Fantastik') {
            if (!genresArr.includes('Bilim Kurgu & Fantastik') &&
                !genresArr.includes('Bilim-Kurgu') && !genresArr.includes('Bilimkurgu') &&
                !genresArr.includes('Fantastik') &&
                !gJoined.includes('bilim') && !gJoined.includes('fantastik')) {
                return false;
            }
        } else if (!genresArr.includes(selectedGenre)) {
            return false;
        }
    }

    if (selectedPlatform !== 'ALL') {
        const pList = Array.isArray(item.platforms) ? item.platforms : [item.platform || ''];
        const pStr = pList.join(' ').toLowerCase();
        if (selectedPlatform === 'HBO / Max') {
            if (!pStr.includes('hbo') && !pStr.includes('max')) return false;
        } else if (selectedPlatform === 'Amazon Prime') {
            if (!pStr.includes('amazon') && !pStr.includes('prime')) return false;
        } else if (selectedPlatform === 'Disney Plus') {
            if (!pStr.includes('disney')) return false;
        } else if (!pStr.includes(selectedPlatform.toLowerCase())) {
            return false;
        }
    }

    return true;
}

let _renderCardsDebounceTimer = null;
const RENDER_CARDS_DEBOUNCE_MS = 400;

function scheduleRenderContentCards(immediate = false) {
    if (_renderCardsDebounceTimer) {
        clearTimeout(_renderCardsDebounceTimer);
        _renderCardsDebounceTimer = null;
    }
    const run = () => {
        _renderCardsDebounceTimer = null;
        renderContentCards();
    };
    if (immediate) {
        run();
    } else {
        _renderCardsDebounceTimer = setTimeout(run, RENDER_CARDS_DEBOUNCE_MS);
    }
}

function renderContentCards() {
    window._exploreNeedsRefresh = false;
    const cardsContainer = document.getElementById('cards-container');
    const resultsCountText = document.getElementById('results-count-text');
    if (!cardsContainer) return;
    const renderToken = ++_renderCardsToken;
    const universeSnapshot = currentUniverse;

    const dataset = (universeSnapshot === 'MOVIES') 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    // Girdi Değerlerini Oku (Null-Safety)
    const minRating = parseFloat(document.getElementById('slider-min-rating')?.value) || 5.0;
    const minYear = parseInt(document.getElementById('input-min-year')?.value) || 1900;
    const maxSeasons = parseInt(document.getElementById('input-max-seasons')?.value) || 999;
    const minVotes = parseInt(document.getElementById('input-min-votes')?.value) || 100;
    const selectedGenre = document.getElementById('select-genre')?.value || 'ALL';
    const selectedPlatform = document.getElementById('select-platform')?.value || 'ALL';
    const selectedLanguage = document.getElementById('select-language')?.value || 'ALL';
    const sortOption = document.getElementById('select-sort')?.value || 'AI';
    const onlyEnded = document.getElementById('check-only-ended')?.checked || false;
    const perPage = parseInt(document.getElementById('select-per-page')?.value) || 5;
    const searchSensitivity = parseInt(document.getElementById('slider-search-sensitivity')?.value, 10) || 65;

    const searchQuery = (COMMITTED_SIDEBAR_SEARCH_QUERY || '').toLowerCase().trim();
    const aiSearchQuery = (COMMITTED_AI_SEARCH_QUERY || '').toLowerCase().trim();
    const activeSearchQuery = aiSearchQuery || searchQuery;

    const sidebarOpts = {
        minRating, minYear, maxSeasons, minVotes, onlyEnded,
        selectedLanguage, selectedGenre, selectedPlatform
    };

    // 1. Filtreleme Algoritması (Kriter Filtreleri)
    let filteredData = dataset.filter(item => passesExploreSidebarFilters(item, sidebarOpts));

    // 🔒 KULLANICI KİTAPLIĞINDAKİ YAPIMLARI KEŞFET LİSTESİNDEN ELE (TEKRAR ÇIKMASIN)
    const userLib = getActiveLibrary();
    const userLibIds = new Set();
    (userLib || []).forEach(i => {
        if (!i || i.id == null) return;
        const sid = String(i.id);
        userLibIds.add(sid);
        const bare = normalizeMediaIdKey(sid);
        if (bare) {
            userLibIds.add(bare);
            userLibIds.add(`series_${bare}`);
            userLibIds.add(`movies_${bare}`);
            userLibIds.add(`movie_${bare}`);
        }
    });
    const isInUserLibrary = (itemId) => {
        if (itemId == null) return false;
        const sid = String(itemId);
        if (userLibIds.has(sid)) return true;
        const bare = normalizeMediaIdKey(sid);
        return userLibIds.has(bare)
            || userLibIds.has(`series_${bare}`)
            || userLibIds.has(`movies_${bare}`)
            || userLibIds.has(`movie_${bare}`);
    };
    filteredData = filteredData.filter(item => !isInUserLibrary(item.id));

    // 🧠 YAPAY ZEKA VE ÇOKLU ALAN ARAMA MOTORU (BACKEND SEMANTİK VEKTÖR + YEREL FALLBACK)
    let isNonsenseQuery = false;
    if (activeSearchQuery) {
        if (typeof window.BACKEND_SEARCH_CACHE === 'undefined') {
            window.BACKEND_SEARCH_CACHE = {};
        }
        // Kitaplık değişince cache bozulsun
        const libCacheSig = [...userLibIds].sort().join(',').slice(0, 200);
        // v6: zombi undead tuzağı + aramaya özel AI notu
        const cacheKey = `v6_${universeSnapshot}_${activeSearchQuery.toLowerCase().trim()}_${libCacheSig}`;
        let backendData = window.BACKEND_SEARCH_CACHE[cacheKey];

        if (backendData === undefined || backendData === 'LOADING') {
            if (backendData === undefined) {
                window.BACKEND_SEARCH_CACHE[cacheKey] = 'LOADING';
                // Arka planda sürer; kullanıcı başka sekmeye geçebilir
                searchViaBackend(activeSearchQuery, universeSnapshot).then(data => {
                    window.BACKEND_SEARCH_CACHE[cacheKey] = data;
                    // Keşfet görünür olsun/olmasın sonuçları hazırla
                    const exploreTab = document.getElementById('tab-explore');
                    if (exploreTab && exploreTab.classList.contains('active')) {
                        renderContentCards();
                    }
                }).catch(err => {
                    window.BACKEND_SEARCH_CACHE[cacheKey] = null;
                    const exploreTab = document.getElementById('tab-explore');
                    if (exploreTab && exploreTab.classList.contains('active')) {
                        renderContentCards();
                    }
                });
            }

            // Arama sürerken sayfalama butonlarını gizle
            setExplorePaginationVisible(false);
            if (resultsCountText) {
                resultsCountText.textContent = 'Semantik arama sürüyor…';
            }

            const mediaWord = universeSnapshot === 'MOVIES' ? 'filmler' : 'diziler';
            cardsContainer.innerHTML = `
                <div style="grid-column: 1 / -1; background: rgba(22, 18, 42, 0.95); border: 2px dashed #06b6d4; border-radius: 20px; padding: 45px 20px; text-align: center; box-shadow: 0 0 35px rgba(6, 182, 212, 0.3);">
                    <div style="width: 58px; height: 58px; border: 4px solid rgba(6, 182, 212, 0.2); border-top-color: #06b6d4; border-right-color: #3b82f6; border-radius: 50%; animation: spin 0.7s linear infinite; margin: 0 auto 18px;"></div>
                    <div style="font-size: 1.25rem; font-weight: 900; color: #fff; letter-spacing: 0.5px; display: flex; align-items: center; justify-content: center; gap: 10px;">
                        <span>⚡ Keşfet Semantik Yapay Zeka Arıyor...</span>
                    </div>
                    <div style="font-size: 0.92rem; color: #38bdf8; font-weight: 700; margin-top: 8px;">
                        "${activeSearchQuery}" temasına uygun ${mediaWord} taranıyor...
                    </div>
                    <div style="font-size: 0.82rem; color: #9ca3af; margin-top: 8px;">
                        ✨ Vektör kataloğu taranıyor. İstersen başka sekmeye geçebilirsin — arama arka planda devam eder.
                    </div>
                </div>
            `;
            return;
        }

        if (backendData && backendData !== 'LOADING' && backendData.results && backendData.results.length > 0) {
            const matchedBackend = [];
            const usedIds = new Set();
            // Backend skor sırasını koru — movie_ / movies_ / series_ çapraz eşle
            backendData.results.forEach((res, idx) => {
                const rid = String(res.id);
                const raw = normalizeMediaIdKey(rid);
                const item = dataset.find(d => idsLooselyEqual(d.id, rid) || normalizeMediaIdKey(d.id) === raw);
                if (!item || isInUserLibrary(item.id)) return;
                const uid = normalizeMediaIdKey(item.id) || String(item.id);
                if (usedIds.has(uid)) return;
                usedIds.add(uid);
                let reason = (res.aiReason && String(res.aiReason).trim()) ? String(res.aiReason).trim() : '';
                if (!isUserLoggedInStrict()) reason = '';
                matchedBackend.push({
                    ...item,
                    aiMatchScore: res.aiMatchScore,
                    aiReason: reason,
                    hybridScore: res.hybridScore,
                    rawSimilarity: res.rawSimilarity
                });
            });

            if (matchedBackend.length > 0) {
                // Temalı aramada bilinen yapımları da ekle (liste şişmesin diye makul tavan)
                filteredData = enrichMatchesWithThemeHints(activeSearchQuery, dataset, matchedBackend)
                    .filter(item => !isInUserLibrary(item.id));
            } else {
                const nlpResult = processNaturalLanguageQuery(activeSearchQuery, filteredData);
                let localMatches = nlpResult.matches.filter(item => !isInUserLibrary(item.id));
                localMatches = enrichMatchesWithThemeHints(activeSearchQuery, dataset, localMatches)
                    .filter(item => !isInUserLibrary(item.id));
                filteredData = localMatches;
                if (nlpResult.isNonsense && localMatches.length === 0) isNonsenseQuery = true;
            }
        } else if (backendData !== 'LOADING') {
            if (backendData && backendData.isNonsense) {
                isNonsenseQuery = true;
                filteredData = [];
            } else {
                const nlpResult = processNaturalLanguageQuery(activeSearchQuery, filteredData);
                if (nlpResult.isNonsense) {
                    let localMatches = enrichMatchesWithThemeHints(activeSearchQuery, dataset, [])
                        .filter(item => !isInUserLibrary(item.id));
                    if (localMatches.length === 0) {
                        isNonsenseQuery = true;
                        filteredData = [];
                    } else {
                        filteredData = localMatches.slice(0, 120);
                    }
                } else {
                    let localMatches = nlpResult.matches.filter(item => !isInUserLibrary(item.id));
                    localMatches = enrichMatchesWithThemeHints(activeSearchQuery, dataset, localMatches)
                        .filter(item => !isInUserLibrary(item.id));
                    // Yerel fallback şişmesin — en fazla 120 (sayfalama ile gezinilir)
                    filteredData = localMatches.slice(0, 120);
                }
            }
        }

        // ✅ Keşfet aramasından SONRA sidebar filtreleri yeniden uygulanır
        // (önceden backend sonuçları platform/puan/tür filtrelerini eziyordu)
        filteredData = filteredData.filter(item => passesExploreSidebarFilters(item, sidebarOpts));

        // ✅ Arama hassasiyeti:
        // hybridScore varsa: üst skora göre oran
        // yoksa: aiMatchScore'u da ÜSTE GÖRE oranla (mutlak 65 kesimi 7 sonuca düşürüyordu)
        if (filteredData.length > 0) {
            const hasHybrid = filteredData.some(i => Number.isFinite(Number(i.hybridScore)));
            if (hasHybrid) {
                const topHybrid = Math.max(...filteredData.map(i => Number(i.hybridScore) || 0));
                const need = topHybrid * (searchSensitivity / 100);
                filteredData = filteredData.filter(item => (Number(item.hybridScore) || 0) >= need);
            } else {
                const topAi = Math.max(...filteredData.map(i => Number(i.aiMatchScore) || 0));
                const need = topAi * (searchSensitivity / 100);
                filteredData = filteredData.filter(item => {
                    const score = Number(item.aiMatchScore);
                    if (!Number.isFinite(score)) return true;
                    return score >= need;
                });
            }
        }

        // AI eşleşme notu: en fazla 10 yapım (maliyet / gürültü)
        filteredData = capExploreAiReasons(filteredData, activeSearchQuery, MAX_AI_MATCH_NOTES);

        // Niyet filtreleri: okul+gizem, zombi+dram vb. — alakasız sonuçları ele
        filteredData = applySearchIntentFilters(activeSearchQuery, filteredData);
    }

    // Ana 4 platform (Netflix / Amazon / Disney / HBO) varsayılan listede hafif öne alınır
    const majorPlatformBoost = (item) => {
        const p = `${item.platform || ''} ${(Array.isArray(item.platforms) ? item.platforms.join(' ') : '')}`.toLowerCase();
        if (p.includes('netflix') || p.includes('amazon') || p.includes('prime') ||
            p.includes('disney') || p.includes('hbo') || p.includes('max')) {
            return 1.25;
        }
        return 1.0;
    };

    // 2. Sıralama Algoritması (Kullanıcının seçtiği sıralama her durumda öncelik kazanır)
    if (sortOption === 'RATING') {
        filteredData.sort((a, b) => (b.rating_num || 0) - (a.rating_num || 0));
    } else if (sortOption === 'POPULARITY') {
        filteredData.sort((a, b) => (b.votes_num || 0) - (a.votes_num || 0));
    } else if (sortOption === 'YEAR') {
        filteredData.sort((a, b) => (b.year || 0) - (a.year || 0));
    } else if (sortOption === 'TITLE') {
        filteredData.sort((a, b) => (a.title || '').localeCompare(b.title || '', 'tr'));
    } else if (sortOption === 'GEMS') {
        filteredData.sort((a, b) => (b.rating_num || 0) - (a.rating_num || 0));
    } else if (sortOption === 'RANDOM') {
        filteredData.sort(() => Math.random() - 0.5);
    } else {
        // AI / Default sorting: Arama yapılıyorsa en yüksek AI uyum skoru ilk sıraya gelir
        if (activeSearchQuery) {
            filteredData.sort((a, b) => (b.aiMatchScore || 0) - (a.aiMatchScore || 0));
        } else {
            filteredData.sort((a, b) => {
                const scoreA = (a.votes_num || 0) * (a.rating_num || 0) * majorPlatformBoost(a);
                const scoreB = (b.votes_num || 0) * (b.rating_num || 0) * majorPlatformBoost(b);
                return scoreB - scoreA;
            });
        }
    }

    // 3. Sayfalama (Pagination) Hesabı
    const totalItems = filteredData.length;
    const totalPages = Math.max(1, Math.ceil(totalItems / perPage));

    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIndex = (currentPage - 1) * perPage;
    const endIndex = Math.min(startIndex + perPage, totalItems);
    const paginatedItems = filteredData.slice(startIndex, endIndex);

    // Sonuç Metni ve Numaralı Sayfalama Güncelleme
    if (resultsCountText) {
        resultsCountText.textContent = (totalItems > 0)
            ? `Toplam ${totalItems} sonuçtan ${startIndex + 1}-${endIndex} arası gösteriliyor.`
            : `Toplam 0 sonuç gösteriliyor.`;
    }

    renderExplorePagination(totalPages);

    // 🔴 KULLANICI UYARISI: ANLAMSIZ VE SAÇMA GİRDİDE (ÖRN: "ben malım") ENGEL VE TEMİZ UYARI METNİ
    if (isNonsenseQuery || paginatedItems.length === 0) {
        setExplorePaginationVisible(false);
        cardsContainer.innerHTML = `
            <div class="empty-state" style="background: rgba(18, 15, 38, 0.85); border: 1px solid var(--border-card); border-radius: 20px; padding: 40px 20px; text-align: center; margin-top: 15px;">
                <i class="fa-solid fa-face-frown empty-icon" style="font-size: 3rem; color: #ef4444; margin-bottom: 15px;"></i>
                <h3 style="color: #fff; font-weight: 800; margin-bottom: 10px; font-size: 1.2rem;">Aradığınız Kriterlere Uygun Yapım Bulunamadı</h3>
                <p style="color: #9ca3af; font-size: 0.95rem; max-width: 550px; margin: 0 auto; line-height: 1.5;">
                    ${aiSearchQuery ? `"<strong>${aiSearchQuery}</strong>" araması için anlamlı bir kurgu veya dizi/film teması tespit edilemedi.<br/>` : ''}
                    Lütfen <em>"ortaçağda geçen diziler"</em>, <em>"zeki bir başrol"</em> veya <em>"hapishane temalı yapımlar"</em> gibi belirgin bir kurgu tanımlayınız.
                </p>
            </div>
        `;
        return;
    }

    // Evren değiştiyse bu render'ı at (eski film/dizi listesi karışmasın)
    if (renderToken !== _renderCardsToken || universeSnapshot !== currentUniverse) return;

    // 4. Kartları anında boya — afişler tarayıcıda paralel yüklenir (preload bekleme yok)
    const showCardBackdrops = false;
    const isMoviesView = universeSnapshot === 'MOVIES';
    const fragment = document.createDocumentFragment();

    paginatedItems.forEach((item, cardIdx) => {
        const card = document.createElement('div');
        card.className = 'media-horizontal-card';

        const whyWatchList = (item.why_watch || []).map(w => `<li>${escapeHtml(w)}</li>`).join('');
        const posterSrc = resolvePosterUrl(item);

        card.innerHTML = `
            ${showCardBackdrops ? renderCardBackdropHtml(item.backdrop_url) : ''}

            <!-- ÜST BÖLÜM: AFİŞ VE SAĞ DETAYLAR -->
            <div class="card-top-row" style="position: relative; z-index: 2; padding-top: 16px;">
                <div class="card-left-poster">
                    ${posterImgHtml(posterSrc, item.title, 'card-poster-img', false, cardIdx < 6 ? 'high' : 'auto')}
                </div>
                <div class="card-right-details">
                    <h2 class="card-item-title">${escapeHtml(item.title)}</h2>
                    ${(item.slogan && item.slogan.trim()) ? `<div class="card-slogan-text">"${escapeHtml(item.slogan)}"</div>` : ''}

                    <div class="card-badges-row">
                        <span class="badge-yellow"><i class="fa-solid fa-star"></i> Puan: ${item.rating_num ? item.rating_num.toFixed(1) : item.rating}</span>
                        <span class="badge-purple" style="background: rgba(168, 85, 247, 0.15); border-color: #a855f7; color: #c084fc;"><i class="fa-solid ${isMoviesView ? 'fa-clock' : 'fa-layer-group'}"></i> ${isMoviesView ? (item.ep_duration || item.runtime || 120) + ' dk' : (item.seasons || '1 Sezon')}</span>
                        ${item.year ? `<span class="badge-cyan" style="background: rgba(14, 165, 233, 0.15); border-color: #0ea5e9; color: #38bdf8;"><i class="fa-solid fa-calendar-days"></i> ${item.year}</span>` : ''}
                        ${!isMoviesView && item.ep_duration ? `<span class="badge-cyan" style="background: rgba(168, 85, 247, 0.15); border-color: #a855f7; color: #c084fc;"><i class="fa-solid fa-clock"></i> ${item.ep_duration} dk/bölüm</span>` : ''}
                    </div>

                    <div class="card-platform-status">
                        📺 ${formatPlatformLinks(item.platform, item.title)} | 📌 ${escapeHtml(item.status || 'Devam Ediyor')}
                    </div>

                    <div class="card-genres">
                        🎭 ${(item.genres || ['Dram']).join(', ')}
                    </div>

                    <p class="card-summary-text">${item.summary || 'Özet bilgisi bulunmuyor.'}</p>

                    ${(isUserLoggedInStrict() && item.aiReason && String(item.aiReason).trim()) ? `
                        <div class="ai-match-reason-box" style="background: linear-gradient(135deg, rgba(6,182,212,0.14), rgba(168,85,247,0.12)); border: 1px solid rgba(6,182,212,0.45); border-radius: 10px; padding: 10px 14px; margin-top: 10px;">
                            <div style="color:#67e8f9; font-weight:800; font-size:0.84rem; margin-bottom:4px;">
                                <i class="fa-solid fa-brain"></i> Yapay Zeka Eşleşme Notu
                                ${item.aiMatchScore ? `<span style="margin-left:8px; color:#c084fc; font-weight:700;">%${item.aiMatchScore} uyum</span>` : ''}
                            </div>
                            <em style="color:#e0f2fe; font-size:0.86rem; line-height:1.45; display:block;">${escapeHtml(String(item.aiReason).trim())}</em>
                        </div>
                    ` : ''}

                    ${whyWatchList ? `
                        <div class="neden-izlemeli-box">
                            <div class="neden-title">💡 Neden İzlemeli?</div>
                            <ul class="neden-ul">${whyWatchList}</ul>
                        </div>
                    ` : ''}
                </div>
            </div>

            <!-- ALT AKSİYON BUTONLARI ROW -->
            <div class="card-bottom-actions-row">
                <button onclick="openItemDetailModal('${item.id}')" class="card-action-btn" style="background: rgba(168, 85, 247, 0.2); border: 1px solid #a855f7; color: #c084fc; font-weight: 700;">
                    <i class="fa-solid fa-circle-info"></i> Detaylı İncele
                </button>
                ${(typeof buildTrailerActionHtml === 'function') ? buildTrailerActionHtml(item, { isSeries: Boolean(item.id && String(item.id).startsWith('series_')) }) : `
                    <button onclick="openTrailerModal('${item.id}', '${escapeQuotes(item.title)}', 'tr', '${escapeQuotes(item.trailer_dub_url || '')}', '${escapeQuotes(item.trailer_sub_url || '')}', ${Boolean(item.id && String(item.id).startsWith('series_'))})" class="card-action-btn btn-trailer-play">
                        <i class="fa-solid fa-play"></i> Fragman İzle
                    </button>
                `}
                <button onclick="addToLibraryFromExplore('${item.id}')" class="card-action-btn btn-add-library">
                    <i class="fa-solid fa-plus"></i> Kitaplığa Ekle
                </button>
                <button onclick="likeItemPreference('${item.id}')" class="card-action-btn btn-like">
                    <i class="fa-solid fa-thumbs-up"></i> Beğen
                </button>
                <button onclick="hideItemPreference('${item.id}')" class="card-action-btn btn-hide">
                    <i class="fa-solid fa-eye-slash"></i> Gizle
                </button>
                <button onclick="openErrorReportModal('${item.id}')" class="card-action-btn btn-report-error">
                    <i class="fa-solid fa-flag"></i> Hatayı Bildir
                </button>
            </div>
        `;

        fragment.appendChild(card);
    });
    cardsContainer.innerHTML = '';
    cardsContainer.appendChild(fragment);
}


/* ==========================================================================
   📌 BAŞLIK 6: SEKMELER VE FİLTRE DİNLENİCİLERİ (ENTER VE BUTON DESTEĞİ)
   ========================================================================== */
function setupTabNavigation() {
    const navItems = document.querySelectorAll('.main-nav .nav-item');
    const tabContents = document.querySelectorAll('.tab-content');

    // İlk boyamada dirty flag'ler
    if (typeof window._exploreNeedsRefresh === 'undefined') window._exploreNeedsRefresh = true;
    if (typeof window._libraryNeedsRefresh === 'undefined') window._libraryNeedsRefresh = true;
    if (typeof window._favoritesNeedsRefresh === 'undefined') window._favoritesNeedsRefresh = true;

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetTabId = item.getAttribute('data-tab');
            if (!targetTabId) return;
            if (targetTabId === 'tab-admin-inbox' && (!IS_ADMIN_SESSION || !isUserLoggedInStrict())) return;

            // Önce sekmeyi göster — ağır DOM işi bir sonraki tick'te (donma azalır)
            navItems.forEach(n => n.classList.remove('active'));
            tabContents.forEach(c => c.classList.remove('active'));

            item.classList.add('active');
            const targetTab = document.getElementById(targetTabId);
            if (targetTab) targetTab.classList.add('active');

            const runTabWork = () => {
                if (targetTabId === 'tab-explore') {
                    // Tab CSS ile gizlenir; DOM silinmez — her geçişte tam render donmaya yol açıyordu
                    if (window._exploreNeedsRefresh) {
                        window._exploreNeedsRefresh = false;
                        renderContentCards();
                    }
                }

                if (targetTabId === 'tab-favorites') {
                    if (window._favoritesNeedsRefresh !== false) {
                        window._favoritesNeedsRefresh = false;
                        renderFavorites();
                    }
                }

                if (targetTabId === 'tab-versus') {
                    updateVersusUI();
                }

                if (targetTabId === 'tab-library') {
                    if (window._libraryNeedsRefresh !== false) {
                        window._libraryNeedsRefresh = false;
                        updateLibraryUI();
                    }
                }

                if (targetTabId === 'tab-social') {
                    renderSocialUI();
                }

                if (targetTabId === 'tab-feedback') {
                    renderFeedbackUI();
                }

                if (targetTabId === 'tab-recommender') {
                    renderAIRecommenderUI();
                }

                if (targetTabId === 'tab-admin-inbox' && IS_ADMIN_SESSION) {
                    renderAdminInboxUI(true);
                }
            };

            if (typeof requestAnimationFrame === 'function') {
                requestAnimationFrame(() => setTimeout(runTabWork, 0));
            } else {
                setTimeout(runTabWork, 0);
            }
        });
    });
}

function setupFilterListeners() {
    const sliderRating = document.getElementById('slider-min-rating');
    const valRating = document.getElementById('val-min-rating');
    const sliderSensitivity = document.getElementById('slider-search-sensitivity');
    const valSensitivity = document.getElementById('val-search-sensitivity');
    
    const inputSearch = document.getElementById('input-search');
    const aiSearchInput = document.getElementById('ai-search-text-input');
    const inputMinYear = document.getElementById('input-min-year');
    const inputMaxSeasons = document.getElementById('input-max-seasons');
    const inputMinVotes = document.getElementById('input-min-votes');
    
    const selectGenre = document.getElementById('select-genre');
    const selectPlatform = document.getElementById('select-platform');
    const selectLanguage = document.getElementById('select-language');
    const selectSort = document.getElementById('select-sort');
    const selectPerPage = document.getElementById('select-per-page');
    const checkOnlyEnded = document.getElementById('check-only-ended');
    
    const btnApply = document.getElementById('btn-apply-filters');
    const btnListMedia = document.getElementById('btn-list-media');

    function commitSearchQueries() {
        const aiEl = document.getElementById('ai-search-text-input');
        const sideEl = document.getElementById('input-search');
        COMMITTED_AI_SEARCH_QUERY = (aiEl && aiEl.value) ? aiEl.value.trim() : '';
        COMMITTED_SIDEBAR_SEARCH_QUERY = (sideEl && sideEl.value) ? sideEl.value.trim() : '';
        if (COMMITTED_AI_SEARCH_QUERY && COMMITTED_AI_SEARCH_QUERY.length < 3) {
            COMMITTED_AI_SEARCH_QUERY = '';
        }
        window._exploreNeedsRefresh = true;
    }

    function triggerSearch(forceCommit, immediateRender) {
        const aiEl = document.getElementById('ai-search-text-input');
        const sideEl = document.getElementById('input-search');
        const typingInSearch = document.activeElement === aiEl || document.activeElement === sideEl;

        // Kullanıcı arama kutusuna yazıyorken filtre change'i canlı metni commit etmesin
        if (forceCommit || !typingInSearch) {
            commitSearchQueries();
        }

        currentPage = 1;
        const activeId = (document.activeElement && document.activeElement.id) || '';
        const selStart = document.activeElement && document.activeElement.selectionStart;
        const selEnd = document.activeElement && document.activeElement.selectionEnd;
        scheduleRenderContentCards(immediateRender === true);
        if (activeId) {
            const el = document.getElementById(activeId);
            if (el && typeof el.focus === 'function') {
                el.focus();
                try {
                    if (typeof selStart === 'number' && typeof selEnd === 'number') {
                        el.setSelectionRange(selStart, selEnd);
                    }
                } catch (e) {}
            }
        }
    }

    if (sliderRating) {
        sliderRating.addEventListener('input', (e) => {
            if (valRating) valRating.textContent = parseFloat(e.target.value).toFixed(1);
        });
        sliderRating.addEventListener('change', triggerSearch);
    }

    if (sliderSensitivity && valSensitivity) {
        sliderSensitivity.addEventListener('input', (e) => { valSensitivity.textContent = e.target.value; });
        sliderSensitivity.addEventListener('change', triggerSearch);
    }

    // ARAMA KUTULARI: yazarken ARAMA YAPILMAZ — sadece Enter
    [inputSearch, aiSearchInput].forEach(input => {
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    triggerSearch(true, true);
                }
            });
        }
    });

    [inputMinYear, inputMaxSeasons, inputMinVotes].forEach(input => {
        if (input) {
            input.addEventListener('input', triggerSearch);
            input.addEventListener('change', triggerSearch);
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') triggerSearch(true, true);
            });
        }
    });

    if (selectGenre) selectGenre.addEventListener('change', triggerSearch);
    if (selectPlatform) selectPlatform.addEventListener('change', triggerSearch);
    if (selectLanguage) selectLanguage.addEventListener('change', triggerSearch);
    if (selectSort) selectSort.addEventListener('change', triggerSearch);
    if (selectPerPage) selectPerPage.addEventListener('change', triggerSearch);
    if (checkOnlyEnded) checkOnlyEnded.addEventListener('change', triggerSearch);

    // FİLTRELE VE ARA BUTONU
    if (btnApply) btnApply.addEventListener('click', () => triggerSearch(true, true));
    if (btnListMedia) btnListMedia.addEventListener('click', () => triggerSearch(true, true));
}

function isLibraryTabActive() {
    const tab = document.getElementById('tab-library');
    return !!(tab && tab.classList.contains('active'));
}


/* ==========================================================================
   📌 BAŞLIK 7: KİTAPLIĞIM (MY LIBRARY) YÖNETİMİ & İSTATİSTİK MOTORU
   ==========================================================================
   Açıklama: Kullanıcının eklediği yapımları tutar, Ay/Gün/Saat izleme sürelerini
   hesaplar, 14 rozet, grafik dağılımları ve 2. fotoğraftaki kart aksiyonlarını yönetir.
   ========================================================================== */

let USER_SERIES_LIBRARY = [];
let USER_MOVIES_LIBRARY = [];

let currentLibraryFilter = 'ALL';
let currentLibrarySearchQuery = '';

function normalizeLibrarySearchText(value) {
    return String(value || '')
        .toLocaleLowerCase('tr-TR')
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/ı/g, 'i')
        .trim();
}

function getLibrarySearchQuery() {
    return normalizeLibrarySearchText(currentLibrarySearchQuery);
}

function libraryItemMatchesSearch(item, query) {
    if (!query) return true;
    if (!item) return false;

    const haystackParts = [
        item.title,
        item.slogan,
        item.platform,
        item.status,
        item.status_text,
        item.duo,
        Array.isArray(item.genres) ? item.genres.join(' ') : item.genres
    ];

    const haystack = normalizeLibrarySearchText(haystackParts.filter(Boolean).join(' '));
    return haystack.includes(query);
}

function getFilteredLibraryItems(libData) {
    const source = Array.isArray(libData) ? libData : [];
    const byStatus = (currentLibraryFilter === 'ALL')
        ? source
        : source.filter(item => item && item.status === currentLibraryFilter);
    const query = getLibrarySearchQuery();
    if (!query) return byStatus;
    return byStatus.filter(item => libraryItemMatchesSearch(item, query));
}

function syncLibrarySearchUI(matchCount) {
    const input = document.getElementById('input-library-search');
    const clearBtn = document.getElementById('btn-clear-library-search');
    const meta = document.getElementById('library-search-meta');
    const queryRaw = String(currentLibrarySearchQuery || '').trim();

    if (input && input.value !== currentLibrarySearchQuery) {
        input.value = currentLibrarySearchQuery;
    }

    if (clearBtn) clearBtn.hidden = !queryRaw;

    if (meta) {
        if (!queryRaw) {
            meta.hidden = true;
            meta.textContent = '';
        } else {
            meta.hidden = false;
            meta.innerHTML = `<strong>${matchCount}</strong> sonuç · “${escapeHtml(queryRaw)}”`;
        }
    }
}

function clearLibrarySearch(shouldRender = true) {
    currentLibrarySearchQuery = '';
    currentLibraryPage = 1;
    const input = document.getElementById('input-library-search');
    if (input) input.value = '';
    if (shouldRender) renderLibraryCards();
}

// --------------------------------------------------------------------------
// 1. İZLEME SÜRESİ HESAPLAMA FORMATI (AY / GÜN / SAAT / DAKİKA)
// --------------------------------------------------------------------------
function formatWatchTime(totalMins) {
    if (!totalMins || totalMins <= 0) return "0 Gün 0 Saat 0 Dk";

    let totalHours = Math.floor(totalMins / 60);
    let mins = totalMins % 60;

    let days = Math.floor(totalHours / 24);
    let hours = totalHours % 24;

    let months = Math.floor(days / 30);
    let remDays = days % 30;

    if (months > 0) {
        return `${months} Ay ${remDays} Gün ${hours} Saat ${mins} Dk`;
    } else if (days > 0) {
        return `${days} Gün ${hours} Saat ${mins} Dk`;
    } else {
        return `${hours} Saat ${mins} Dk`;
    }
}

function getActiveLibrary() {
    return (currentUniverse === 'MOVIES') ? USER_MOVIES_LIBRARY : USER_SERIES_LIBRARY;
}

// --------------------------------------------------------------------------
// 2. 14 ADET KAZANILAN ROZET VE BAŞARIMLARIN RENDER EDİLMESİ
// --------------------------------------------------------------------------
let chartPlatformInstance = null;
let chartGenreInstance = null;

// --------------------------------------------------------------------------
// 2. 14 ADET KAZANILAN ROZET VE BAŞARIMLARIN RENDER EDİLMESİ (3. FOTOĞRAFTAKİ BİREBİR TASARIM)
// --------------------------------------------------------------------------
/* ==========================================================================
   📌 BAŞLIK: ÇOK SEVİYELİ (BRONZ, GÜMÜŞ, ALTIN, ELMAS) BAŞARIM ROZETLERİ MOTORU
   ========================================================================== */
const UNLOCKED_BADGES_STATE = new Set(
    JSON.parse(localStorage.getItem('matrix_notified_badges') || '[]')
);

function isLibraryItemFinished(item) {
    return item && item.status === 'İzledim';
}

function getFinishedLibraryItems(libData) {
    return (Array.isArray(libData) ? libData : []).filter(isLibraryItemFinished);
}

function getBadgeTierInfo(cur, thresholds) {
    if (cur < thresholds.bronz) {
        return {
            tier: "KİLİTLİ",
            nextTier: "BRONZ",
            target: thresholds.bronz,
            isLocked: true,
            statusColor: "#9ca3af",
            borderColor: "rgba(255, 255, 255, 0.2)",
            pct: Math.min(100, Math.round((cur / thresholds.bronz) * 100))
        };
    } else if (cur < thresholds.gumus) {
        return {
            tier: "BRONZ",
            nextTier: "GÜMÜŞ",
            target: thresholds.gumus,
            isLocked: false,
            statusColor: "#cd7f32",
            borderColor: "#cd7f32",
            pct: Math.min(100, Math.round((cur / thresholds.gumus) * 100))
        };
    } else if (cur < thresholds.altin) {
        return {
            tier: "GÜMÜŞ",
            nextTier: "ALTIN",
            target: thresholds.altin,
            isLocked: false,
            statusColor: "#cbd5e1",
            borderColor: "#cbd5e1",
            pct: Math.min(100, Math.round((cur / thresholds.altin) * 100))
        };
    } else if (cur < thresholds.elmas) {
        return {
            tier: "ALTIN",
            nextTier: "ELMAS",
            target: thresholds.elmas,
            isLocked: false,
            statusColor: "#facc15",
            borderColor: "#facc15",
            pct: Math.min(100, Math.round((cur / thresholds.elmas) * 100))
        };
    } else {
        return {
            tier: "ELMAS",
            nextTier: "MAX",
            target: thresholds.elmas,
            isLocked: false,
            statusColor: "#00f0ff",
            borderColor: "#00f0ff",
            pct: 100
        };
    }
}

function renderBadges(options = {}) {
    const notifyNewBadges = options.notify === true;
    const badgesContainer = document.getElementById('badges-container');
    if (!badgesContainer) return;

    const libData = getActiveLibrary();
    const finishedItems = getFinishedLibraryItems(libData);
    const isMovie = (currentUniverse === 'MOVIES');

    // Metrikleri dinamik hesapla — platform/tür rozetleri yalnızca bitirilen yapımlardan sayılır
    const finishedCount = finishedItems.length;
    const ratedCount = libData.filter(i => (i.user_rating || 0) > 0).length;
    
    let totalWatchedMins = 0;
    libData.forEach(item => {
        const epMins = item.ep_duration || (isMovie ? 120 : 45);
        if (item.status === 'İzledim') {
            const map = item.season_episodes_map || [10];
            const totalEps = isMovie ? 1 : (item.total_episodes || map.reduce((a, b) => a + b, 0));
            totalWatchedMins += totalEps * epMins;
        } else if (!isMovie && (item.status === 'İzliyorum' || (item.current_episode || 0) > 0 || (item.current_season || 1) > 1)) {
            const curS = item.current_season || 1;
            const curE = item.current_episode || 0;
            const map = item.season_episodes_map || [10];
            let eps = 0;
            for (let i = 0; i < curS - 1; i++) eps += (map[i] || 10);
            eps += curE;
            totalWatchedMins += eps * epMins;
        }
    });

    const totalHours = Math.floor(totalWatchedMins / 60);

    const netflixCount = finishedItems.filter(i => (i.platform || '').includes('Netflix')).length;
    const primeCount = finishedItems.filter(i => (i.platform || '').includes('Prime') || (i.platform || '').includes('Amazon')).length;
    const disneyCount = finishedItems.filter(i => (i.platform || '').includes('Disney')).length;
    const dramCount = finishedItems.filter(i => (i.genres || []).includes('Dram')).length;
    const sciFiCount = finishedItems.filter(i => (i.genres || []).some(g => g.includes('Bilim') || g.includes('Gizem') || g.includes('Fantastik'))).length;
    const comedyCount = finishedItems.filter(i => (i.genres || []).includes('Komedi')).length;
    const crimeCount = finishedItems.filter(i => (i.genres || []).some(g => g.includes('Suç') || g.includes('Polisiye') || g.includes('Gerilim'))).length;
    const gemCount = finishedItems.filter(i => i.votes_num && i.votes_num >= 200 && i.votes_num <= 400).length;

    let rawBadgesList = [];

    if (isMovie) {
        // 🎬 FİLM EVRENİ BAŞARIMLARI (BİREBİR KULLANICI EŞİKLERİ VE İSİMLERİ)
        rawBadgesList = [
            {
                id: "movie_total",
                faIcon: "fa-solid fa-film",
                title: "Sinema Perdesi",
                desc: "Bitirdiğin toplam film sayısı",
                cur: finishedCount,
                thresholds: { bronz: 1, gumus: 15, altin: 50, elmas: 150 }
            },
            {
                id: "movie_hours",
                faIcon: "fa-solid fa-stopwatch",
                title: "Maratoncu",
                desc: "Toplam film izleme süresi (Saat)",
                cur: totalHours,
                thresholds: { bronz: 10, gumus: 50, altin: 200, elmas: 600 }
            },
            {
                id: "movie_netflix",
                faIcon: "fa-solid fa-clapperboard",
                title: "Netflix Sineması",
                desc: "Bitirdiğin Netflix filmleri",
                cur: netflixCount,
                thresholds: { bronz: 1, gumus: 10, altin: 30, elmas: 75 }
            },
            {
                id: "movie_prime",
                faIcon: "fa-solid fa-gift",
                title: "Prime Sinema Kulübü",
                desc: "Bitirdiğin Amazon Prime filmleri",
                cur: primeCount,
                thresholds: { bronz: 1, gumus: 10, altin: 30, elmas: 75 }
            },
            {
                id: "movie_disney",
                faIcon: "fa-solid fa-fort-awesome",
                title: "Disney Vizyonu",
                desc: "Bitirdiğin Disney+ filmleri",
                cur: disneyCount,
                thresholds: { bronz: 1, gumus: 10, altin: 30, elmas: 75 }
            },
            {
                id: "movie_gems",
                faIcon: "fa-solid fa-gem",
                title: "Gizli Vizyoner",
                desc: "Popüler olmayan (200-400 oy) film yapımlarını keşfetme",
                cur: gemCount,
                thresholds: { bronz: 1, gumus: 5, altin: 15, elmas: 35 }
            },
            {
                id: "movie_drama",
                faIcon: "fa-solid fa-masks-theater",
                title: "Dram Kuşağı",
                desc: "Bitirdiğin dram filmleri",
                cur: dramCount,
                thresholds: { bronz: 1, gumus: 8, altin: 25, elmas: 60 }
            },
            {
                id: "movie_scifi",
                faIcon: "fa-solid fa-rocket",
                title: "Bilimkurgu Evreni",
                desc: "Bitirdiğin bilimkurgu/fantastik filmler",
                cur: sciFiCount,
                thresholds: { bronz: 1, gumus: 8, altin: 25, elmas: 60 }
            },
            {
                id: "movie_comedy",
                faIcon: "fa-solid fa-face-laugh-beam",
                title: "Sinema Komedisi",
                desc: "Bitirdiğin komedi filmleri",
                cur: comedyCount,
                thresholds: { bronz: 1, gumus: 8, altin: 25, elmas: 60 }
            },
            {
                id: "movie_thriller",
                faIcon: "fa-solid fa-user-secret",
                title: "Gerilim & Suç",
                desc: "Bitirdiğin suç/gerilim/polisiye filmleri",
                cur: crimeCount,
                thresholds: { bronz: 1, gumus: 8, altin: 25, elmas: 60 }
            },
            {
                id: "movie_critic",
                faIcon: "fa-solid fa-pen-nib",
                title: "Film Eleştirmeni",
                desc: "Puan verdiğin film sayısı",
                cur: ratedCount,
                thresholds: { bronz: 1, gumus: 10, altin: 30, elmas: 75 }
            },
            {
                id: "movie_social",
                faIcon: "fa-solid fa-users",
                title: "Sosyal Sinemasever",
                desc: "Kazanılan arkadaş sayısı",
                cur: 1,
                thresholds: { bronz: 1, gumus: 3, altin: 5, elmas: 10 }
            },
            {
                id: "movie_collector",
                faIcon: "fa-solid fa-trophy",
                title: "Koleksiyoner",
                desc: "Kazanılan toplam rozet sayısı",
                cur: 2,
                thresholds: { bronz: 1, gumus: 3, altin: 6, elmas: 12 }
            },
            {
                id: "movie_legend",
                faIcon: "fa-solid fa-crown",
                title: "Sinema Efsanesi",
                desc: "Altın/Elmas rozet toplama başarısı",
                cur: 0,
                thresholds: { bronz: 1, gumus: 3, altin: 5, elmas: 10 }
            }
        ];
    } else {
        // 📺 DİZİ EVRENİ BAŞARIMLARI (BİREBİR KULLANICI EŞİKLERİ VE İSİMLERİ)
        rawBadgesList = [
            {
                id: "series_total",
                faIcon: "fa-solid fa-desktop",
                title: "Ekran Bağımlısı",
                desc: "Bitirdiğin toplam dizi sayısı",
                cur: finishedCount,
                thresholds: { bronz: 1, gumus: 5, altin: 15, elmas: 40 }
            },
            {
                id: "series_hours",
                faIcon: "fa-solid fa-tv",
                title: "Koltuk Patatesi",
                desc: "Toplam izleme süresi (Saat)",
                cur: totalHours,
                thresholds: { bronz: 10, gumus: 50, altin: 250, elmas: 3500 }
            },
            {
                id: "series_netflix",
                faIcon: "fa-solid fa-clapperboard",
                title: "Netflix Gurmesi",
                desc: "Bitirdiğin Netflix dizileri",
                cur: netflixCount,
                thresholds: { bronz: 1, gumus: 3, altin: 8, elmas: 20 }
            },
            {
                id: "series_prime",
                faIcon: "fa-solid fa-gift",
                title: "Prime Seçici",
                desc: "Bitirdiğin Prime Video dizileri",
                cur: primeCount,
                thresholds: { bronz: 1, gumus: 3, altin: 8, elmas: 20 }
            },
            {
                id: "series_disney",
                faIcon: "fa-solid fa-fort-awesome",
                title: "Disney Seyyahı",
                desc: "Bitirdiğin Disney Plus dizileri",
                cur: disneyCount,
                thresholds: { bronz: 1, gumus: 3, altin: 8, elmas: 20 }
            },
            {
                id: "series_gems",
                faIcon: "fa-solid fa-gem",
                title: "Gizli Cevher Avcısı",
                desc: "Popüler olmayan (200-400 oy) dizileri keşfetme",
                cur: gemCount,
                thresholds: { bronz: 1, gumus: 2, altin: 5, elmas: 12 }
            },
            {
                id: "series_drama",
                faIcon: "fa-solid fa-masks-theater",
                title: "Dram Sever",
                desc: "Bitirdiğin dram dizileri",
                cur: dramCount,
                thresholds: { bronz: 1, gumus: 3, altin: 8, elmas: 18 }
            },
            {
                id: "series_scifi",
                faIcon: "fa-solid fa-rocket",
                title: "Bilimkurgu Kaşifi",
                desc: "Bitirdiğin bilimkurgu/gizem dizileri",
                cur: sciFiCount,
                thresholds: { bronz: 1, gumus: 3, altin: 8, elmas: 18 }
            },
            {
                id: "series_comedy",
                faIcon: "fa-solid fa-face-laugh-beam",
                title: "Kahkaha Makinesi",
                desc: "Bitirdiğin komedi dizileri",
                cur: comedyCount,
                thresholds: { bronz: 1, gumus: 3, altin: 8, elmas: 18 }
            },
            {
                id: "series_thriller",
                faIcon: "fa-solid fa-user-secret",
                title: "Suç Ortağı",
                desc: "Bitirdiğin suç/polisiye dizileri",
                cur: crimeCount,
                thresholds: { bronz: 1, gumus: 3, altin: 8, elmas: 18 }
            },
            {
                id: "series_social",
                faIcon: "fa-solid fa-users",
                title: "Sosyal Kelebek",
                desc: "Kazanılan arkadaş sayısı",
                cur: 1,
                thresholds: { bronz: 1, gumus: 3, altin: 5, elmas: 10 }
            },
            {
                id: "series_critic",
                faIcon: "fa-solid fa-pen-nib",
                title: "Kritik Zihin",
                desc: "Puan verdiğin dizi sayısı",
                cur: ratedCount,
                thresholds: { bronz: 1, gumus: 5, altin: 12, elmas: 25 }
            },
            {
                id: "series_collector",
                faIcon: "fa-solid fa-trophy",
                title: "Koleksiyoner",
                desc: "Kazanılan toplam rozet sayısı",
                cur: 2,
                thresholds: { bronz: 1, gumus: 3, altin: 6, elmas: 12 }
            },
            {
                id: "series_legend",
                faIcon: "fa-solid fa-crown",
                title: "Efsane (Gizli)",
                desc: "Altın/Elmas rozet toplama başarısı",
                cur: 0,
                thresholds: { bronz: 1, gumus: 3, altin: 5, elmas: 10 }
            }
        ];
    }

    badgesContainer.innerHTML = rawBadgesList.map(b => {
        const tierInfo = getBadgeTierInfo(b.cur, b.thresholds);

        // 🔔 BİLEDİRİM TETİKLEME: YENİ SEVİYE KİLİDİ AÇILDIĞINDA SAĞ ÜSTTE GÖRKEMLİ POPUP BİLDİRİMİ BAS!
        if (!tierInfo.isLocked && CURRENT_USER) {
            const unlockKey = `${CURRENT_USER}_${b.id}_${tierInfo.tier}`;
            if (!UNLOCKED_BADGES_STATE.has(unlockKey)) {
                UNLOCKED_BADGES_STATE.add(unlockKey);
                localStorage.setItem('matrix_notified_badges', JSON.stringify(Array.from(UNLOCKED_BADGES_STATE)));
                if (notifyNewBadges) {
                    showBadgeToast(b.title, tierInfo.tier, b.faIcon);
                }
            }
        }

        const isMax = tierInfo.tier === 'ELMAS';
        const progressLabel = isMax 
            ? `${b.cur} / ${tierInfo.target} (ELMAS - MAX)` 
            : `${b.cur} / ${tierInfo.target} (${tierInfo.tier === 'KİLİTLİ' ? 'BRONZ' : tierInfo.nextTier})`;

        return `
            <div class="badge-card" style="background: var(--bg-card); border: 1px solid var(--border-card); border-radius: 16px; padding: 18px 14px; text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: space-between; min-height: 225px; position: relative;">
                
                <div style="width: 54px; height: 54px; border-radius: 50%; border: 2.5px dashed ${tierInfo.borderColor}; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; margin-bottom: 8px; background: rgba(0,0,0,0.4); color: ${tierInfo.statusColor}; box-shadow: 0 0 15px ${tierInfo.isLocked ? 'transparent' : tierInfo.statusColor}; opacity: ${tierInfo.isLocked ? 0.55 : 1};">
                    <i class="${b.faIcon}"></i>
                </div>

                <div style="font-weight: 800; color: #fff; font-size: 0.95rem; margin-bottom: 2px;">${b.title}</div>
                
                <div style="font-size: 0.78rem; font-weight: 800; color: ${tierInfo.statusColor}; letter-spacing: 0.5px; margin-bottom: 6px;">
                    ${tierInfo.tier}
                </div>

                <div style="font-size: 0.72rem; color: #9ca3af; margin-bottom: 10px; line-height: 1.35;">${b.desc}</div>

                <div style="width: 100%; margin-top: auto;">
                    <div style="display: flex; justify-content: space-between; font-size: 0.75rem; font-weight: 800; color: #fff; margin-bottom: 4px;">
                        <span>${progressLabel}</span>
                    </div>
                    <div style="background: rgba(255,255,255,0.1); height: 7px; border-radius: 4px; overflow: hidden;">
                        <div style="background: ${tierInfo.isLocked ? 'rgba(255,255,255,0.2)' : 'var(--primary-gradient)'}; width: ${tierInfo.pct}%; height: 100%;"></div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// --------------------------------------------------------------------------
// 3. FOTOĞRAFTAKİ BİREBİR GRAFİKLER (PLATFORM & TÜR DAĞILIMI - CHART.JS)
// --------------------------------------------------------------------------
function renderDistributionCharts() {
    const platformCanvas = document.getElementById('canvas-platform-chart');
    const genreCanvas = document.getElementById('canvas-genre-chart');
    if (!platformCanvas || !genreCanvas) return;

    if (typeof Chart === 'undefined') return;

    const libData = getActiveLibrary();
    const isMovie = (currentUniverse === 'MOVIES');

    // 🎨 EVRENE GÖRE DİNAMİK GRAFİK RENGİ
    // Film Evreni -> Sinematik Kehribar Ateşi (#f97316)
    // Dizi Evreni -> Doygun Cobalt Saf Mavi (#3b82f6)
    const chartBarColor = isMovie ? '#f97316' : '#3b82f6';
    
    // Platform Dağılımı (Diğer Platformlar, Amazon Prime, Netflix)
    const pCounts = { 'Diğer Platformlar': 0, 'Amazon Prime': 0, 'Netflix': 0 };
    libData.forEach(item => {
        const p = (item.platform || '');
        if (p.includes('Netflix')) pCounts['Netflix']++;
        else if (p.includes('Amazon') || p.includes('Prime')) pCounts['Amazon Prime']++;
        else pCounts['Diğer Platformlar']++;
    });

    // Tür Dağılımı (Dram, Vahşi Batı, Aksiyon & Macera, Komedi)
    const gCounts = { 'Dram': 0, 'Vahşi Batı': 0, 'Aksiyon & Macera': 0, 'Komedi': 0 };
    libData.forEach(item => {
        if (item.genres && Array.isArray(item.genres)) {
            item.genres.forEach(g => {
                if (gCounts[g] !== undefined) gCounts[g]++;
                else gCounts[g] = 1;
            });
        } else {
            gCounts['Dram']++;
        }
    });

    const commonOptions = {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: {
                beginAtZero: true,
                ticks: {
                    stepSize: 1,
                    precision: 0,
                    color: '#9ca3af',
                    font: { weight: 'bold' }
                },
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                title: { display: true, text: 'İzlenme Sayısı', color: '#9ca3af', font: { weight: 'bold' } }
            },
            y: {
                ticks: { color: '#fff', font: { weight: 'bold', size: 11 } },
                grid: { display: false }
            }
        }
    };

    if (chartPlatformInstance) chartPlatformInstance.destroy();
    chartPlatformInstance = new Chart(platformCanvas, {
        type: 'bar',
        data: {
            labels: Object.keys(pCounts),
            datasets: [{
                data: Object.values(pCounts),
                backgroundColor: chartBarColor,
                borderRadius: 4
            }]
        },
        options: commonOptions
    });

    if (chartGenreInstance) chartGenreInstance.destroy();
    chartGenreInstance = new Chart(genreCanvas, {
        type: 'bar',
        data: {
            labels: Object.keys(gCounts),
            datasets: [{
                data: Object.values(gCounts),
                backgroundColor: chartBarColor,
                borderRadius: 4
            }]
        },
        options: commonOptions
    });
}

// --------------------------------------------------------------------------
// 4. KİTAPLIK UI GÜNCELLEMESİ VE DATALIST DOLDURMA
// --------------------------------------------------------------------------
function updateLibraryUI(options = {}) {
    const renderHeavy = options.forceHeavy === true || options.notifyBadges === true || isLibraryTabActive();

    if (!renderHeavy) {
        window._libraryNeedsRefresh = true;
        if (CURRENT_USER) saveUserData(CURRENT_USER);
        return;
    }

    window._libraryNeedsRefresh = false;
    const statWatchTime = document.getElementById('stat-watch-time');
    const statMediaCount = document.getElementById('stat-media-count');
    const datalist = document.getElementById('datalist-manual-media');

    if (!CURRENT_USER) {
        CURRENT_USER = 'Kullanıcı';
    }

    const libData = getActiveLibrary();

    // Toplam İzleme Süresi Hesabı (Sadece izlenen bölümler hesaba katılır, S1 B0 = 0 dk!)
    let totalMins = 0;
    libData.forEach(item => {
        const epMins = item.ep_duration || 45;
        const isMovie = (currentUniverse === 'MOVIES');

        if (isMovie) {
            if (item.status === 'İzledim') {
                totalMins += (item.ep_duration || 120);
            }
        } else {
            const map = item.season_episodes_map || [10];
            if (item.status === 'İzledim') {
                const totalEps = item.total_episodes || map.reduce((a, b) => a + b, 0);
                totalMins += totalEps * epMins;
            } else if (item.status === 'İzliyorum' || (item.current_episode || 0) > 0 || (item.current_season || 1) > 1) {
                const curS = item.current_season || 1;
                const curE = item.current_episode || 0;
                let epsWatched = 0;
                for (let i = 0; i < curS - 1; i++) {
                    epsWatched += (map[i] || 10);
                }
                epsWatched += curE;
                totalMins += epsWatched * epMins;
            }
            // S1 B0 (İzleyeceğim) ise 0 dakika kalır!
        }
    });

    if (statWatchTime) statWatchTime.textContent = formatWatchTime(totalMins);
    if (statMediaCount) statMediaCount.textContent = `${libData.length} Adet`;

    // Arama Yapılabilir Datalist Doldur
    if (datalist) {
        const dataset = (currentUniverse === 'MOVIES') 
            ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
            : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

        datalist.innerHTML = '';
        dataset.forEach(item => {
            const opt = document.createElement('option');
            opt.value = item.title;
            datalist.appendChild(opt);
        });
    }

    // Çip Sayılarını ve Görünürlüğünü Güncelle
    const chips = document.querySelectorAll('.lib-chip');
    chips.forEach(chip => {
        const status = chip.getAttribute('data-status');
        if (currentUniverse === 'MOVIES' && status === 'İzliyorum') {
            chip.style.display = 'none';
            if (currentLibraryFilter === 'İzliyorum') currentLibraryFilter = 'ALL';
        } else {
            chip.style.display = 'inline-block';
        }
        let count = (status === 'ALL') ? libData.length : libData.filter(i => i.status === status).length;
        chip.textContent = `${status === 'ALL' ? 'Tümü' : status} (${count})`;
    });

    // Manuel Ekleme Select Dropdown'ındaki "İzliyorum" opsiyonunu Film evreninde gizle
    const selectManualStatus = document.getElementById('select-manual-status');
    if (selectManualStatus) {
        Array.from(selectManualStatus.options).forEach(opt => {
            if (opt.value === 'İzliyorum') {
                opt.style.display = (currentUniverse === 'MOVIES') ? 'none' : 'block';
                if (currentUniverse === 'MOVIES' && selectManualStatus.value === 'İzliyorum') {
                    selectManualStatus.value = 'İzleyeceğim';
                }
            }
        });
    }

    renderBadges({ notify: options.notifyBadges === true });
    renderDistributionCharts();
    renderLibraryCards();

    if (CURRENT_USER) saveUserData(CURRENT_USER);
}

let currentLibraryPage = 1;
const LIB_PER_PAGE = 6;

function goToLibraryPage(page) {
    const target = parseInt(page, 10);
    if (!Number.isFinite(target) || target < 1 || target === currentLibraryPage) return;
    currentLibraryPage = target;
    renderLibraryCards();
    const container = document.getElementById('tab-library');
    if (container) container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function changeLibraryPage(delta) {
    goToLibraryPage(currentLibraryPage + delta);
}

// --------------------------------------------------------------------------
// 5. 2. EKRAN GÖRÜNTÜSÜNDEKİ BİREBİR KİTAPLIK KARTI MİMARİSİ
// --------------------------------------------------------------------------
function renderLibraryCards() {
    const libTab = document.getElementById('tab-library');
    const isMovie = (currentUniverse === 'MOVIES');

    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        if (libTab) {
            renderGuestLockBanner(libTab, 'Kitaplığım', isMovie);
        }
        return;
    }

    if (libTab && ORIGINAL_LIBRARY_TAB_HTML && !document.getElementById('library-cards-container')) {
        libTab.innerHTML = ORIGINAL_LIBRARY_TAB_HTML;
    }

    const libCardsContainer = document.getElementById('library-cards-container');
    if (!libCardsContainer) return;

    const libData = getActiveLibrary();
    const filtered = getFilteredLibraryItems(libData);
    const searchQueryRaw = String(currentLibrarySearchQuery || '').trim();

    libCardsContainer.innerHTML = '';
    syncLibrarySearchUI(filtered.length);

    const paginationWrapper = document.getElementById('library-pagination');

    // Aktif filtre çipini koru (HTML restore sonrası da)
    document.querySelectorAll('.lib-chip').forEach(chip => {
        const status = chip.getAttribute('data-status');
        chip.classList.toggle('active', status === currentLibraryFilter);
    });

    if (filtered.length === 0) {
        if (paginationWrapper) paginationWrapper.style.display = 'none';
        const otherLib = (currentUniverse === 'MOVIES') ? USER_SERIES_LIBRARY : USER_MOVIES_LIBRARY;
        if (libData.length === 0 && otherLib.length > 0) {
            libCardsContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-${currentUniverse === 'MOVIES' ? 'tv' : 'film'} empty-icon" style="color: var(--primary-color);"></i>
                    <p style="font-weight: 800; font-size: 1.05rem;">
                        ${currentUniverse === 'MOVIES' ? 'Dizi Evreninizde' : 'Film Evreninizde'} ${otherLib.length} adet kayıtlı yapımınız bulunuyor!
                    </p>
                    <p style="font-size: 0.85rem; color: #9ca3af; margin-top: 4px;">Kayıtlı ${otherLib.length} yapımınızı görüntülemek için evren değiştirin:</p>
                    <button onclick="setUniverse('${currentUniverse === 'MOVIES' ? 'SERIES' : 'MOVIES'}')" class="primary-gradient-btn" style="padding: 10px 22px; font-size: 0.88rem; margin-top: 12px; border-radius: 20px; font-weight: 800; cursor: pointer; border: none; display: inline-flex; align-items: center; gap: 8px;">
                        <i class="fa-solid fa-repeat"></i> ${currentUniverse === 'MOVIES' ? '📺 Dizilere Geç' : '🎬 Filmlere Geç'}
                    </button>
                </div>
            `;
        } else if (searchQueryRaw && libData.length > 0) {
            libCardsContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-magnifying-glass empty-icon"></i>
                    <p>“${escapeHtml(searchQueryRaw)}” için kitaplığınızda eşleşme yok.</p>
                    <p style="font-size: 0.85rem; color: #9ca3af; margin-top: 4px;">Aramayı temizleyerek ${currentLibraryFilter === 'ALL' ? 'tüm' : currentLibraryFilter} listesine dönebilirsiniz.</p>
                    <button onclick="clearLibrarySearch()" class="secondary-gradient-btn" style="padding: 8px 18px; font-size: 0.85rem; margin-top: 10px; border-radius: 20px; font-weight: 800; cursor: pointer;">
                        Aramayı Temizle
                    </button>
                </div>
            `;
        } else if (libData.length > 0) {
            libCardsContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-filter empty-icon"></i>
                    <p>'${currentLibraryFilter}' kategorisinde içerik bulunamadı.</p>
                    <p style="font-size: 0.85rem; color: #9ca3af; margin-top: 4px;">Toplam ${libData.length} kayıtlı yapımınızı görüntülemek için filtrenizi sıfırlayabilirsiniz:</p>
                    <button onclick="currentLibraryFilter='ALL'; currentLibraryPage=1; updateLibraryUI();" class="secondary-gradient-btn" style="padding: 8px 18px; font-size: 0.85rem; margin-top: 10px; border-radius: 20px; font-weight: 800; cursor: pointer;">
                        Tümünü Göster (${libData.length})
                    </button>
                </div>
            `;
        } else {
            libCardsContainer.innerHTML = `
                <div class="empty-state">
                    <i class="fa-solid fa-folder-open empty-icon"></i>
                    <p>Henüz kayıtlı ${currentUniverse === 'MOVIES' ? 'film' : 'dizi'} bulunmuyor. Keşfet sekmesinden içerik ekleyebilirsiniz!</p>
                </div>
            `;
        }
        return;
    }

    // Sayfalama Hesaplaması
    const totalPages = Math.ceil(filtered.length / LIB_PER_PAGE) || 1;
    if (currentLibraryPage > totalPages) currentLibraryPage = totalPages;
    if (currentLibraryPage < 1) currentLibraryPage = 1;

    const startIdx = (currentLibraryPage - 1) * LIB_PER_PAGE;
    const pageItems = filtered.slice(startIdx, startIdx + LIB_PER_PAGE);

    // Ana dataset'ten eksik bilgileri tamamla (genres, ep_duration vb.)
    const mainDataset = (currentUniverse === 'MOVIES')
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    pageItems.forEach((item, index) => {
        const card = document.createElement('div');
        card.className = 'media-horizontal-card';

        // Ana dataset'ten katalog alanlarını güncelle (fragman URL'leri her zaman kataloğdan — eski Father/remake ezilir)
        const found = mainDataset.find(d => d.id === item.id);
        if (found) {
            if (!item.genres || item.genres.length === 0) item.genres = found.genres || [];
            if (!item.ep_duration) item.ep_duration = found.ep_duration;
            item.trailer_url = found.trailer_url || '';
            item.trailer_dub_url = found.trailer_dub_url || '';
            item.trailer_sub_url = found.trailer_sub_url || '';
            item.backdrop_url = found.backdrop_url || item.backdrop_url || '';
            if (!item.poster_url) item.poster_url = found.poster_url || found.afis_url || '';
            if (!item.slogan) item.slogan = found.slogan || '';
        }

        const isMovie = (currentUniverse === 'MOVIES');

        card.innerHTML = `
            ${renderCardBackdropHtml(item.backdrop_url)}

            <div class="card-top-row" style="position: relative; z-index: 2; padding-top: 16px;">
                <!-- SOL AFİŞ -->
                <div class="card-left-poster">
                    ${posterImgHtml(resolvePosterUrl(item), item.title)}
                </div>

                <!-- ORTA BÖLÜM: DETAYLAR VE SEZON/BÖLÜM (+) İKONU -->
                <div class="card-right-details">
                    <h2 class="card-item-title">${escapeHtml(item.title)}</h2>
                    ${(item.slogan && item.slogan.trim()) ? `<div class="card-slogan-text">"${escapeHtml(item.slogan)}"</div>` : ''}

                    <div class="card-badges-row">
                        <span class="badge-yellow"><i class="fa-solid fa-star"></i> Genel Puan: ${item.rating || '9.4/10'}</span>
                        ${!isMovie ? `
                            <span class="badge-purple"><i class="fa-solid fa-film"></i> ${item.total_seasons || 1} Sezon (${item.total_episodes || 10} Bölüm)</span>
                            <span class="badge-purple" style="background: rgba(6,182,212,0.15); color: #22d3ee; border-color: #22d3ee;"><i class="fa-solid fa-clock"></i> Bölüm: ~${item.ep_duration || 45} dk</span>
                        ` : `
                            <span class="badge-purple"><i class="fa-solid fa-clock"></i> Film Süresi: ${item.ep_duration || 120} dk</span>
                        `}
                        <span class="badge-cyan" style="background: rgba(16,185,129,0.15); color: #10b981; border-color: #10b981;">📌 Durum: ${item.status_text || 'Bitmiş / Final Yapmış'}</span>
                        ${(() => {
                            const genres = Array.isArray(item.genres) ? item.genres : (item.genres ? [item.genres] : []);
                            if (genres.length === 0) return '';
                            const genreColors = {
                                'Aksiyon': '#ef4444', 'Dram': '#8b5cf6', 'Komedi': '#f59e0b',
                                'Gerilim': '#dc2626', 'Bilim-Kurgu': '#06b6d4', 'Fantastik': '#a855f7',
                                'Suç': '#f97316', 'Macera': '#10b981', 'Romantik': '#ec4899',
                                'Gizem': '#6366f1', 'Korku': '#7f1d1d', 'Animasyon': '#fbbf24',
                                'Belgesel': '#84cc16', 'Tarih': '#78716c', 'Müzik': '#e879f9'
                            };
                            return genres.slice(0, 3).map(g => {
                                const col = genreColors[g] || '#64748b';
                                return `<span style="display:inline-flex; align-items:center; gap:4px; background:${col}22; color:${col}; border:1px solid ${col}66; padding:3px 9px; border-radius:20px; font-size:0.75rem; font-weight:700;">🎭 ${g}</span>`;
                            }).join('');
                        })()}
                    </div>

                    <div class="card-platform-status">
                        📺 Yayınlandığı Platformlar: ${formatPlatformLinks(item.platform, item.title)}
                    </div>

                    <!-- 📺 DİZİLER VE FİLMLER İÇİN DURUM VE PUAN BİLGİSİ -->
                    ${!isMovie ? `
                        <div style="display: flex; align-items: center; gap: 15px; margin: 12px 0; flex-wrap: wrap;">
                            <span style="font-size: 0.85rem; color: #a855f7; font-weight: 700;">📌 ${item.status}</span>
                            <div style="display: flex; align-items: center; gap: 8px; background: rgba(0,0,0,0.4); padding: 6px 14px; border-radius: 20px; border: 1px solid var(--border-card);">
                                <span style="font-weight: 800; color: #fff;">📺 S${item.current_season || 1} B${item.current_episode !== undefined ? item.current_episode : 0}</span>
                                <button onclick="incrementEpisode('${item.id}')" title="Bir Sonraki Bölüme Geç (+1)" style="background: var(--primary-gradient); border: none; color: #fff; width: 26px; height: 26px; border-radius: 50%; cursor: pointer; font-weight: bold; font-size: 1rem; display: flex; align-items: center; justify-content: center;">
                                    +
                                </button>
                            </div>
                            <span style="font-size: 0.85rem; color: #9ca3af;" id="user-rating-label-${item.id}">
                                Senin Puanın: <strong style="color: #facc15;">${item.user_rating ? '⭐ ' + item.user_rating + ' / 5' : 'Puanlanmadı'}</strong>
                            </span>
                        </div>
                    ` : `
                        <div style="display: flex; align-items: center; gap: 15px; margin: 12px 0; flex-wrap: wrap;">
                            <span style="font-size: 0.85rem; color: #f97316; font-weight: 700;">📌 Durum: ${item.status}</span>
                            <span style="font-size: 0.85rem; color: #9ca3af;" id="user-rating-label-${item.id}">
                                Senin Puanın: <strong style="color: #facc15;">${item.user_rating ? '⭐ ' + item.user_rating + ' / 5' : 'Puanlanmadı'}</strong>
                            </span>
                        </div>
                    `}

                    ${item.summary ? `
                        <details class="custom-expander" style="margin-top: 8px; background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 8px 12px;">
                            <summary style="color: #38bdf8; font-weight: 700; font-size: 0.88rem; cursor: pointer;">
                                📄 Detaylı Özet
                            </summary>
                            <p style="font-size: 0.85rem; color: #d1d5db; margin-top: 6px; line-height: 1.5;">${item.summary}</p>
                        </details>
                    ` : ''}
                </div>

                <!-- SAĞ AKSİYON SÜTUNU -->
                <div style="width: 250px; flex-shrink: 0; display: flex; flex-direction: column; gap: 10px;">
                    <button onclick="openItemDetailModal('${item.id}')" class="card-action-btn" style="background: rgba(168, 85, 247, 0.2); border: 1px solid #a855f7; color: #c084fc; font-weight: 700; width: 100%; justify-content: center;">
                        <i class="fa-solid fa-circle-info"></i> Detaylı İncele
                    </button>
                    ${(typeof buildTrailerActionHtml === 'function') ? buildTrailerActionHtml(item, { isSeries: Boolean(!isMovie), fullWidth: true }) : `
                        <button onclick="openTrailerModal('${item.id}', '${escapeQuotes(item.title)}', 'tr', '${escapeQuotes(item.trailer_dub_url || '')}', '${escapeQuotes(item.trailer_sub_url || '')}', ${Boolean(!isMovie)})" class="card-action-btn btn-trailer-play" style="width: 100%; justify-content: center;">
                            <i class="fa-solid fa-play"></i> Fragman İzle
                        </button>
                    `}

                    <button onclick="openErrorReportModal('${item.id}')" class="card-action-btn btn-report-error" style="width: 100%; justify-content: center;">
                        <i class="fa-solid fa-flag"></i> Hatayı Bildir
                    </button>

                    <!-- DÜZENLE BUTONU VE POPOVER (HEM DİZİ HEM FİLM İÇİN AKTİF) -->
                    <button onclick="toggleEditPopover('${item.id}')" class="card-action-btn" id="btn-edit-toggle-${item.id}" style="background: rgba(255,255,255,0.08); border: 1px solid var(--border-card); font-size: 0.82rem; width: 100%;">
                        <i class="fa-solid fa-gear"></i> Düzenle <span id="arrow-edit-${item.id}">˅</span>
                    </button>
                    
                    <div id="edit-popover-${item.id}" class="edit-in-card-panel" style="display: none; background: rgba(22, 18, 42, 0.98); border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 14px; padding: 16px; margin-top: 2px;">
                        <!-- İZLEME DURUMU SEÇİMİ (YARIDA BIRAKTIM DAHİL) -->
                        <div class="edit-field-group" style="margin-bottom: 12px;">
                            <label class="edit-field-label" style="font-size: 0.85rem; color: #e5e7eb; font-weight: 700; display: block; margin-bottom: 4px;">İzleme Durumu:</label>
                            <select id="edit-status-val-${item.id}" class="custom-select" style="font-size: 0.85rem; padding: 6px;">
                                ${!isMovie ? `<option value="İzliyorum" ${item.status === 'İzliyorum' ? 'selected' : ''}>İzliyorum</option>` : ''}
                                <option value="İzleyeceğim" ${item.status === 'İzleyeceğim' ? 'selected' : ''}>İzleyeceğim</option>
                                <option value="İzledim" ${item.status === 'İzledim' ? 'selected' : ''}>İzledim</option>
                                <option value="Yarıda Bıraktım" ${item.status === 'Yarıda Bıraktım' ? 'selected' : ''}>Yarıda Bıraktım</option>
                            </select>
                        </div>

                        ${!isMovie ? `
                            <div class="edit-field-group" style="margin-bottom: 12px;">
                                <label class="edit-field-label" style="font-size: 0.85rem; color: #e5e7eb; font-weight: 700; display: block; margin-bottom: 4px;">Sezon:</label>
                                <div class="stepper-control" style="background: rgba(10, 8, 24, 0.8); border: 1px solid var(--border-card); border-radius: 8px; padding: 4px 8px; display: flex; align-items: center; justify-content: space-between;">
                                    <input type="text" id="edit-season-val-${item.id}" class="stepper-val" value="${item.current_season || 1}" readonly style="width: 40px; text-align: center; border: none; background: transparent; color: #fff; font-weight: 800;" />
                                    <div style="display: flex; gap: 4px;">
                                        <button type="button" class="stepper-btn" onclick="stepSeason('${item.id}', -1)">-</button>
                                        <button type="button" class="stepper-btn" onclick="stepSeason('${item.id}', 1)">+</button>
                                    </div>
                                </div>
                            </div>

                            <div class="edit-field-group" style="margin-bottom: 12px;">
                                <label class="edit-field-label" style="font-size: 0.85rem; color: #e5e7eb; font-weight: 700; display: block; margin-bottom: 4px;">Bölüm:</label>
                                <div class="stepper-control" style="background: rgba(10, 8, 24, 0.8); border: 1px solid var(--border-card); border-radius: 8px; padding: 4px 8px; display: flex; align-items: center; justify-content: space-between;">
                                    <input type="text" id="edit-ep-val-${item.id}" class="stepper-val" value="${item.current_episode !== undefined ? item.current_episode : 0}" readonly style="width: 40px; text-align: center; border: none; background: transparent; color: #fff; font-weight: 800;" />
                                    <div style="display: flex; gap: 4px;">
                                        <button type="button" class="stepper-btn" onclick="stepEpisode('${item.id}', -1)">-</button>
                                        <button type="button" class="stepper-btn" onclick="stepEpisode('${item.id}', 1)">+</button>
                                    </div>
                                </div>
                            </div>
                        ` : ''}

                        <div class="edit-field-group" style="margin-bottom: 14px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                <label class="edit-field-label" style="font-size: 0.85rem; color: #e5e7eb; font-weight: 700;">${isMovie ? 'Film Puanı' : 'Dizi Puanı'} (1-5 ⭐):</label>
                                <span id="star-preview-${item.id}" style="color: #facc15; font-weight: 800; font-size: 0.85rem;">
                                    ${item.user_rating ? '⭐ ' + item.user_rating : 'Puanlanmadı'}
                                </span>
                            </div>
                            <div class="star-rating-container" id="star-rating-box-${item.id}" data-rating="${item.user_rating || 0}" style="display: flex; gap: 6px; font-size: 1.2rem;">
                                ${[1, 2, 3, 4, 5].map(star => `
                                    <i class="fa-solid fa-star star-icon ${(item.user_rating || 0) >= star ? 'active' : ''}" onclick="selectStarRating('${item.id}', ${star})"></i>
                                `).join('')}
                            </div>
                        </div>

                        <button onclick="saveEditPanel('${item.id}')" style="background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); color: #fff; border: none; padding: 12px; border-radius: 12px; font-weight: 800; font-size: 0.95rem; cursor: pointer; width: 100%; box-shadow: 0 4px 15px rgba(168, 85, 247, 0.4);">
                            Güncelle
                        </button>
                    </div>

                    <button onclick="markAsFinished('${item.id}')" class="card-action-btn" style="background: rgba(255,255,255,0.1); border: 1px solid var(--border-card); font-size: 0.82rem;">
                        <i class="fa-solid fa-check"></i> Bitirdim
                    </button>
                    <button onclick="toggleFavorite('${item.id}')" class="card-action-btn" style="background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); font-size: 0.82rem;">
                        <i class="fa-solid fa-heart"></i> Favoriye Ekle
                    </button>
                    <button onclick="removeFromLibrary('${item.id}')" class="card-action-btn" style="background: linear-gradient(135deg, #ef4444 0%, #b91c1c 100%); font-size: 0.82rem;">
                        <i class="fa-solid fa-trash"></i> Sil
                    </button>
                </div>
            </div>
        `;

        libCardsContainer.appendChild(card);
    });

    // Sayfalama Butonları Güncelleme
    if (paginationWrapper) {
        const shown = fillNumberedPaginationNav(
            'library-numbered-pagination',
            currentLibraryPage,
            totalPages,
            'goToLibraryPage'
        );
        paginationWrapper.style.display = shown ? 'flex' : 'none';
    }
}

// --------------------------------------------------------------------------
// 6. KİTAPLIK KART AKSİYONLARI (KEŞFET'TEN EKLE, BÖLÜM +, BİTİRDİM, DÜZENLE, FAVORİ, SİL)
// --------------------------------------------------------------------------

function showBadgeToast(title, tier, iconClass) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'badge-unlock-toast';
    toast.style.cssText = `
        background: linear-gradient(135deg, rgba(30, 27, 75, 0.96) 0%, rgba(49, 16, 75, 0.96) 100%);
        border: 2px solid #facc15;
        box-shadow: 0 0 25px rgba(250, 204, 21, 0.6), 0 8px 32px rgba(0,0,0,0.8);
        border-radius: 16px;
        padding: 14px 20px;
        margin-top: 10px;
        color: #fff;
        display: flex;
        align-items: center;
        gap: 14px;
        backdrop-filter: blur(10px);
        transform: translateY(-20px) scale(0.9);
        opacity: 0;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    `;

    toast.innerHTML = `
        <div style="width: 46px; height: 46px; border-radius: 50%; background: linear-gradient(135deg, #facc15, #f59e0b); display: flex; align-items: center; justify-content: center; font-size: 1.4rem; color: #1e1b4b; flex-shrink: 0; box-shadow: 0 0 15px #facc15;">
            <i class="${iconClass || 'fa-solid fa-trophy'}"></i>
        </div>
        <div>
            <div style="font-size: 0.72rem; font-weight: 900; color: #facc15; text-transform: uppercase; letter-spacing: 1px; display: flex; align-items: center; gap: 4px;">
                🎉 YENİ ROZET KAZANILDI!
            </div>
            <div style="font-weight: 800; font-size: 0.95rem; color: #fff; margin-top: 2px;">${title}</div>
            <div style="font-size: 0.8rem; color: #c084fc; font-weight: 700; margin-top: 1px;">
                Seviye: <span style="color: #facc15; font-weight: 900;">${tier}</span>
            </div>
        </div>
    `;

    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateY(0) scale(1)';
    });

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-20px) scale(0.9)';
        setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 400);
    }, 4500);
}

// --------------------------------------------------------------------------
// 🔔 SAĞ ÜST KÖŞE ENGELLEYİCİ OLMAYAN BİLDİRİM TOAST MOTORU
// --------------------------------------------------------------------------
function showToast(message, durationMs = 1800) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = 'toast-pill';
    toast.innerHTML = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fade-out');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 400);
    }, durationMs);
}

// --------------------------------------------------------------------------
// ⚙️ KÜÇÜK AKSİYON DÜZENLEME PANELDİR (POPOVER DROPDOWN)
// --------------------------------------------------------------------------
function toggleEditPopover(itemId) {
    const popover = document.getElementById(`edit-popover-${itemId}`);
    const arrow = document.getElementById(`arrow-edit-${itemId}`);
    if (!popover) return;

    if (popover.style.display === 'none' || !popover.style.display) {
        popover.style.display = 'block';
        if (arrow) arrow.textContent = '^';
    } else {
        popover.style.display = 'none';
        if (arrow) arrow.textContent = '˅';
    }
}

// KEŞFET SEKMESİNDEN KİTAPLIĞA EKLEME (VARSAYILAN: İZLEYECEĞİM, S1 B0)
function addToLibraryFromExplore(itemId) {
    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        showToast('🔒 Kitaplığa içerik eklemek için lütfen giriş yapın veya kaydolun!', 2200);
        openAuthModal('LOGIN');
        return false;
    }

    const dataset = (currentUniverse === 'MOVIES')
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const foundItem = getMediaItemFullDetails({ id: itemId }, dataset);
    if (!foundItem || !foundItem.title) {
        showToast('⚠️ Yapım katalogda bulunamadı, kitaplığa eklenemedi.', 2200);
        return false;
    }

    const canonicalId = foundItem.id || itemId;
    const targetLib = getActiveLibrary();
    const existing = targetLib.find(i => idsLooselyEqual(i.id, canonicalId) || idsLooselyEqual(i.id, itemId));

    if (existing) {
        showToast(`ℹ️ ${foundItem.title} zaten kitaplığınızda (${existing.status}) kayıtlı!`, 1800);
        return false;
    }

    const map = foundItem.season_episodes_map || [10];
    const totalSeasons = foundItem.seasons_num || map.length;
    const totalEpisodes = foundItem.total_episodes || map.reduce((a, b) => a + b, 0);

    targetLib.unshift({
        id: canonicalId,
        title: foundItem.title,
        status: (currentUniverse === 'MOVIES') ? "İzleyeceğim" : "İzleyeceğim",
        poster_url: foundItem.poster_url || foundItem.afis_url,
        rating: foundItem.rating,
        total_seasons: totalSeasons,
        season_episodes_map: map,
        total_episodes: totalEpisodes,
        current_season: 1,
        current_episode: 0,
        platform: foundItem.platform || 'Netflix',
        status_text: foundItem.status || foundItem.status_text || 'Bitmiş / Final Yapmış',
        duo: foundItem.duo || '',
        summary: foundItem.summary || foundItem.ozet || '',
        ep_duration: foundItem.ep_duration || (currentUniverse === 'MOVIES' ? 140 : 45),
        genres: foundItem.genres || [],
        trailer_url: foundItem.trailer_url || '',
        trailer_dub_url: foundItem.trailer_dub_url || '',
        trailer_sub_url: foundItem.trailer_sub_url || ''
    });

    showToast(`✅ <strong>${foundItem.title}</strong> kitaplığınıza eklendi!`, 1800);
    window.BACKEND_REC_CACHE = {};
    window._libraryNeedsRefresh = true;
    if (typeof clearPersistedAIRecCache === 'function') clearPersistedAIRecCache(currentUniverse);
    if (CURRENT_USER) saveUserData(CURRENT_USER);
    updateLibraryUI();
    return true;
}

// BÖLÜM İLERLETME (+): SEZON BÖLÜM HARİTASINA GÖRE SONRAKİ SEZONA VE 'İZLİYORUM'A GEÇER
function incrementEpisode(itemId) {
    const libData = getActiveLibrary();
    const item = libData.find(i => i.id === itemId);
    if (!item) return;

    const map = item.season_episodes_map || [10];
    let curS = item.current_season || 1;
    let curE = item.current_episode || 0;
    let maxEpInSeason = map[curS - 1] || 10;

    if (curE < maxEpInSeason) {
        item.current_episode = curE + 1;
    } else if (curS < (item.total_seasons || map.length)) {
        item.current_season = curS + 1;
        item.current_episode = 1;
    } else {
        item.status = "İzledim";
        showToast(`🎉 ${item.title} dizisinin tüm sezon ve bölümlerini tamamladınız!`, 2000);
        updateLibraryUI({ notifyBadges: true });
        return;
    }

    if (item.status === 'İzleyeceğim') {
        item.status = 'İzliyorum';
    }

    updateLibraryUI();
}

// BİTİRDİM BUTONU: GERÇEK SON SEZON VE SON BÖLÜME TAŞIR (Örn: S5 B16 veya S4 B24)
function markAsFinished(itemId) {
    const libData = getActiveLibrary();
    const item = libData.find(i => i.id === itemId);
    if (!item) return;

    const isMovie = (currentUniverse === 'MOVIES');

    if (isMovie) {
        item.status = "İzledim";
        showToast(`🎉 <strong>${item.title}</strong> tamamlandı!`, 2000);
    } else {
        const map = item.season_episodes_map || [10];
        const lastSeasonIdx = (item.total_seasons || map.length) - 1;
        const lastSeasonMaxEp = map[lastSeasonIdx] || 10;

        item.current_season = item.total_seasons || map.length;
        item.current_episode = lastSeasonMaxEp;
        item.status = "İzledim";

        showToast(`🎉 <strong>${item.title}</strong> tamamlandı! (S${item.current_season} B${item.current_episode})`, 2000);
    }
    updateLibraryUI({ notifyBadges: true });
}

function stepSeason(itemId, delta) {
    const libData = getActiveLibrary();
    const item = libData.find(i => i.id === itemId);
    if (!item) return;

    const input = document.getElementById(`edit-season-val-${itemId}`);
    if (!input) return;

    let curS = parseInt(input.value) || 1;
    const maxS = item.total_seasons || (item.season_episodes_map || [10]).length;

    curS += delta;
    if (curS < 1) curS = 1;
    if (curS > maxS) curS = maxS;

    input.value = curS;
}

function stepEpisode(itemId, delta) {
    const libData = getActiveLibrary();
    const item = libData.find(i => i.id === itemId);
    if (!item) return;

    const seasonInput = document.getElementById(`edit-season-val-${itemId}`);
    const epInput = document.getElementById(`edit-ep-val-${itemId}`);
    if (!epInput) return;

    let curS = seasonInput ? (parseInt(seasonInput.value) || 1) : (item.current_season || 1);
    let curE = parseInt(epInput.value) || 0;

    const map = item.season_episodes_map || [10];
    const maxEpInSeason = map[curS - 1] || 10;

    curE += delta;
    if (curE < 0) curE = 0;
    if (curE > maxEpInSeason) curE = maxEpInSeason;

    epInput.value = curE;
}

function selectStarRating(itemId, rating) {
    const container = document.getElementById(`star-rating-box-${itemId}`);
    const previewText = document.getElementById(`star-preview-${itemId}`);

    if (container) {
        container.setAttribute('data-rating', rating);
        const stars = container.querySelectorAll('.star-icon');
        stars.forEach((star, idx) => {
            if (idx < rating) {
                star.classList.add('active');
            } else {
                star.classList.remove('active');
            }
        });
    }

    if (previewText) {
        previewText.textContent = `⭐ ${rating}/5`;
    }
}

function saveEditPanel(itemId) {
    const libData = getActiveLibrary();
    const item = libData.find(i => i.id === itemId);
    if (!item) return;

    const statusSelect = document.getElementById(`edit-status-val-${itemId}`);
    const seasonInput = document.getElementById(`edit-season-val-${itemId}`);
    const epInput = document.getElementById(`edit-ep-val-${itemId}`);
    const starBox = document.getElementById(`star-rating-box-${itemId}`);

    const isMovie = (currentUniverse === 'MOVIES');
    const previousStatus = item.status;

    if (!isMovie) {
        const map = item.season_episodes_map || [10];
        const maxSeasons = item.total_seasons || map.length;
        const maxEpInLastSeason = map[maxSeasons - 1] || 10;

        let selectedS = seasonInput ? (parseInt(seasonInput.value) || 1) : (item.current_season || 1);
        let selectedE = epInput ? (parseInt(epInput.value) || 0) : (item.current_episode || 0);

        item.current_season = selectedS;
        item.current_episode = selectedE;

        const isFullyFinished = (selectedS >= maxSeasons && selectedE >= maxEpInLastSeason);
        let desiredStatus = statusSelect ? statusSelect.value : item.status;

        if (desiredStatus === 'İzledim') {
            if (!isFullyFinished) {
                // Sezon/bölüm henüz bitmemişken "İzledim" seçilirse otomatik son bölüme tamamla
                item.current_season = maxSeasons;
                item.current_episode = maxEpInLastSeason;
                showToast(`🎉 <strong>${item.title}</strong> tüm sezon ve bölümleri tamamlandı (İzledim) olarak güncellendi! (S${maxSeasons} B${maxEpInLastSeason})`, 2500);
            }
            item.status = 'İzledim';
        } else {
            // Eğer "İzledim" harici bir durum seçildiyse (İzliyorum, İzleyeceğim, Yarıda Bıraktım)
            if (!isFullyFinished && item.status === 'İzledim') {
                item.status = (desiredStatus !== 'İzledim') ? desiredStatus : 'İzliyorum';
            } else {
                item.status = desiredStatus;
            }
        }
    } else {
        if (statusSelect) {
            item.status = statusSelect.value;
        }
    }

    if (starBox) {
        const chosenRating = parseInt(starBox.getAttribute('data-rating')) || 0;
        if (chosenRating > 0) {
            item.user_rating = chosenRating;
        }
    }

    // Popover Paneli Kapat
    const popover = document.getElementById(`edit-popover-${itemId}`);
    if (popover) popover.style.display = 'none';

    showToast(`✅ <strong>${item.title}</strong> güncellendi!`, 1800);
    const earnedNewBadge = item.status === 'İzledim' && previousStatus !== 'İzledim';
    updateLibraryUI({ notifyBadges: earnedNewBadge });
}

function toggleFavorite(itemId) {
    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        showToast('🔒 Favorilere içerik eklemek için lütfen giriş yapın veya kaydolun!', 2200);
        openAuthModal('LOGIN');
        return;
    }

    const dataset = (currentUniverse === 'MOVIES') 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const item = dataset.find(i => i.id === itemId) || getActiveLibrary().find(i => i.id === itemId);

    if (item) {
        if (!USER_FAVORITES.includes(item.id)) {
            USER_FAVORITES.push(item.id);
            showToast(`💖 <strong>${item.title}</strong> Favorilerinize eklendi!`, 1800);
        } else {
            USER_FAVORITES = USER_FAVORITES.filter(id => id !== item.id);
            showToast(`💔 ${item.title} Favorilerinizden çıkarıldı.`, 1800);
        }
        renderFavorites();
        if (CURRENT_USER) saveUserData(CURRENT_USER);
    }
}

/* ==========================================================================
   📌 BAŞLIK: FAVORİLERİM SEKMESİ VE SAYFALAMA MOTORU (FOTOĞRAFTAKİ BİREBİR)
   ========================================================================== */
function renderFavorites() {
    window._favoritesNeedsRefresh = false;
    const container = document.getElementById('favorites-cards-container');
    const titleEl = document.getElementById('favorites-section-title');
    const paginationWrapper = document.getElementById('favorites-pagination');

    if (!container) return;

    const isMovie = (currentUniverse === 'MOVIES');

    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        renderGuestLockBanner(container, 'Favoriler', isMovie);
        if (paginationWrapper) paginationWrapper.style.display = 'none';
        return;
    }

    if (titleEl) {
        titleEl.innerHTML = isMovie 
            ? `<i class="fa-solid fa-heart" style="color: #ef4444;"></i> Favori Filmleriniz` 
            : `<i class="fa-solid fa-heart" style="color: #0ea5e9;"></i> Favori Dizileriniz`;
    }

    // Favorideki ID'lere karşılık gelen tüm veri kümesini hazırla
    const dataset = isMovie 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const targetLib = getActiveLibrary();
    
    let favItems = dataset.filter(item => USER_FAVORITES.includes(item.id));
    targetLib.forEach(libItem => {
        if (USER_FAVORITES.includes(libItem.id) && !favItems.some(i => i.id === libItem.id)) {
            favItems.push(libItem);
        }
    });

    if (favItems.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-heart-crack empty-icon"></i>
                <p>Henüz favorilerinize eklediğiniz ${isMovie ? 'film' : 'dizi'} bulunmuyor.</p>
            </div>
        `;
        if (paginationWrapper) paginationWrapper.style.display = 'none';
        return;
    }

    // Sayfalama Hesaplaması
    const totalPages = Math.ceil(favItems.length / FAV_PER_PAGE) || 1;
    if (currentFavPage > totalPages) currentFavPage = totalPages;
    if (currentFavPage < 1) currentFavPage = 1;

    const startIndex = (currentFavPage - 1) * FAV_PER_PAGE;
    const paginatedFavs = favItems.slice(startIndex, startIndex + FAV_PER_PAGE);

    container.innerHTML = '';

    paginatedFavs.forEach(item => {
        const card = document.createElement('div');
        card.className = 'media-horizontal-card';

        const found = dataset.find(d => d.id === item.id);
        if (found) {
            item.backdrop_url = found.backdrop_url || item.backdrop_url || '';
            if (!item.poster_url) item.poster_url = found.poster_url || found.afis_url || '';
            if (!item.slogan) item.slogan = found.slogan || '';
            item.trailer_url = found.trailer_url || '';
            item.trailer_dub_url = found.trailer_dub_url || '';
            item.trailer_sub_url = found.trailer_sub_url || '';
        }

        const seasonsOrDuration = !isMovie 
            ? `${item.total_seasons || item.seasons_num || 1} Sezon (${item.total_episodes || (item.season_episodes_map || [10]).reduce((a,b)=>a+b,0)} Bölüm)`
            : `${item.ep_duration || 120} dk`;

        const statusText = item.status || item.status_text || 'Devam Ediyor';

        card.innerHTML = `
            ${renderCardBackdropHtml(item.backdrop_url)}

            <div class="card-top-row" style="position: relative; z-index: 2; padding-top: 16px;">
                <!-- SOL AFİŞ -->
                <div class="card-left-poster">
                    ${posterImgHtml(resolvePosterUrl(item), item.title)}
                </div>

                <!-- SAĞ DETAYLAR VE BİREBİR AKORDEON PANELLERİ -->
                <div class="card-right-details">
                    <h2 class="card-item-title">${item.title}</h2>

                    <div class="card-badges-row">
                        <span class="badge-yellow"><i class="fa-solid fa-star"></i> Puan: ${item.rating || '8.967/10'}</span>
                        <span class="badge-purple"><i class="fa-solid fa-${isMovie ? 'clock' : 'film'}"></i> ${isMovie ? 'Süre:' : 'Bölüm:'} ${seasonsOrDuration}</span>
                        <span class="badge-cyan">📌 Durum: <strong style="color: #10b981;">${statusText}</strong></span>
                    </div>

                    <div class="card-platform-status" style="margin-top: 10px;">
                        📺 Yayınlandığı Platformlar: ${formatPlatformLinks(item.platform, item.title)}
                    </div>

                    <!-- FOTOĞRAFTAKİ BİREBİR AÇILIR KAPANIR AKORDEON MENÜLERİ -->
                    <div class="fav-accordion-details">
                        <!-- EFSANEVİ İKİLİ FAVORİLER - GİZLENDİ
                        ${item.duo ? `
                            <div class="fav-accordion-item">
                                <div class="fav-accordion-header" onclick="toggleFavAccordion('duo-${item.id}')">
                                    <i class="fa-solid fa-chevron-right" id="arrow-duo-${item.id}"></i>
                                    <span>👥 ${item.duo}</span>
                                </div>
                                <div id="body-duo-${item.id}" class="fav-accordion-body" style="display: none;">
                                    ${item.duo_desc || 'Karakter ikilisi açıklaması.'}
                                </div>
                            </div>
                        ` : ''}
                        -->

                        <div class="fav-accordion-item">
                            <div class="fav-accordion-header" onclick="toggleFavAccordion('summary-${item.id}')">
                                <i class="fa-solid fa-chevron-right" id="arrow-summary-${item.id}"></i>
                                <span>📝 Özet</span>
                            </div>
                            <div id="body-summary-${item.id}" class="fav-accordion-body" style="display: none;">
                                ${item.summary || 'Özet bilgisi bulunmuyor.'}
                            </div>
                        </div>
                    </div>

                    <!-- FAVORİLERDEN KALDIR VE DETAYLI İNCELE BUTONLARI -->
                    <div style="margin-top: 14px; display: flex; gap: 10px; flex-wrap: wrap;">
                        <button onclick="openItemDetailModal('${item.id}')" class="card-action-btn" style="background: rgba(168, 85, 247, 0.2); border: 1px solid #a855f7; color: #c084fc; font-weight: 700; padding: 8px 14px; border-radius: 10px;">
                            <i class="fa-solid fa-circle-info"></i> Detaylı İncele
                        </button>
                        <button class="fav-remove-btn" onclick="removeFromFavorites('${item.id}')">
                            <i class="fa-solid fa-heart-crack"></i> Favorilerden Kaldır
                        </button>
                    </div>
                </div>
            </div>
        `;

        container.appendChild(card);
    });

    // Sayfalama Butonları Güncelleme
    if (paginationWrapper) {
        const shown = fillNumberedPaginationNav(
            'favorites-numbered-pagination',
            currentFavPage,
            totalPages,
            'goToFavPage'
        );
        paginationWrapper.style.display = shown ? 'flex' : 'none';
    }
}

function toggleFavAccordion(accId) {
    const body = document.getElementById(`body-${accId}`);
    const arrow = document.getElementById(`arrow-${accId}`);
    if (!body) return;

    if (body.style.display === 'none' || !body.style.display) {
        body.style.display = 'block';
        if (arrow) arrow.className = 'fa-solid fa-chevron-down';
    } else {
        body.style.display = 'none';
        if (arrow) arrow.className = 'fa-solid fa-chevron-right';
    }
}

function goToFavPage(page) {
    const target = parseInt(page, 10);
    if (!Number.isFinite(target) || target < 1 || target === currentFavPage) return;
    currentFavPage = target;
    renderFavorites();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function changeFavPage(delta) {
    goToFavPage(currentFavPage + delta);
}

function removeFromFavorites(itemId) {
    USER_FAVORITES = USER_FAVORITES.filter(id => id !== itemId);
    showToast(`💔 Yapım favorilerinizden çıkarıldı.`, 1800);
    renderFavorites();
}

function removeFromLibrary(itemId) {
    if (confirm('Bu yapımı kitaplığınızdan silmek istediğinize emin misiniz?')) {
        if (currentUniverse === 'MOVIES') {
            USER_MOVIES_LIBRARY = USER_MOVIES_LIBRARY.filter(i => i.id !== itemId);
        } else {
            USER_SERIES_LIBRARY = USER_SERIES_LIBRARY.filter(i => i.id !== itemId);
        }
        if (CURRENT_USER && CURRENT_USER !== 'Kullanıcı') {
            saveUserData(CURRENT_USER);
        }
        showToast(`🗑️ Yapım kitaplıktan silindi.`, 1800);
        window.BACKEND_REC_CACHE = {};
        if (typeof clearPersistedAIRecCache === 'function') clearPersistedAIRecCache(currentUniverse);
        updateLibraryUI();
    }
}

function clearEntireLibrary() {
    if (confirm('Tüm kitaplığınızı (Diziler ve Filmler) kalıcı olarak sıfırlamak istediğinize emin misiniz?')) {
        USER_SERIES_LIBRARY = [];
        USER_MOVIES_LIBRARY = [];
        USER_FAVORITES = [];
        if (CURRENT_USER && CURRENT_USER !== 'Kullanıcı') {
            saveUserData(CURRENT_USER);
        }
        showToast('🧹 Kitaplığınız tamamen sıfırlandı.', 2000);
        window.BACKEND_REC_CACHE = {};
        if (typeof clearPersistedAIRecCache === 'function') {
            clearPersistedAIRecCache('SERIES');
            clearPersistedAIRecCache('MOVIES');
        }
        updateLibraryUI();
    }
}

function handleManualSearchInput(inputEl) {
    const resultsDiv = document.getElementById('manual-search-results');
    if (!resultsDiv) return;

    const query = inputEl.value.toLowerCase().trim();

    const dataset = (currentUniverse === 'MOVIES') 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const targetLib = getActiveLibrary();
    const libIds = new Set(targetLib.map(i => i.id));

    const matches = query
        ? dataset.filter(i => i.title.toLowerCase().includes(query)).slice(0, 10)
        : dataset.slice(0, 8);

    if (matches.length === 0) {
        resultsDiv.innerHTML = `<div style="padding: 12px; color: #9ca3af; font-size: 0.88rem; text-align: center;">⚠️ Eşleşen yapım bulunamadı</div>`;
    } else {
        resultsDiv.innerHTML = matches.map(item => {
            const inLib = libIds.has(item.id);
            const statusBadge = inLib 
                ? `<span style="font-size: 0.75rem; font-weight: 800; color: #10b981; background: rgba(16, 185, 129, 0.18); padding: 4px 8px; border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.35);">📌 Kitaplıkta</span>`
                : `<span style="font-size: 0.8rem; font-weight: 800; color: #facc15; background: rgba(250, 204, 21, 0.12); padding: 4px 8px; border-radius: 6px; border: 1px solid rgba(250, 204, 21, 0.3);">⭐ ${item.rating || '8.5'}</span>`;

            return `
                <div class="manual-dropdown-item" onclick="selectManualDropdownItem('${item.id}', '${escapeQuotes(item.title)}', ${inLib})" style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; cursor: pointer; border-bottom: 1px solid rgba(255,255,255,0.06); background: rgba(22, 18, 42, 0.98); transition: background 0.2s ease;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <img src="${resolvePosterUrl(item)}" style="width: 34px; height: 46px; object-fit: cover; border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.5);" onError="this.onerror=null; this.src='https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500';" />
                        <div>
                            <div style="font-weight: 800; color: #fff; font-size: 0.9rem;">${item.title}</div>
                            <div style="font-size: 0.75rem; color: #9ca3af;">${item.year || ''} · ${Array.isArray(item.genres) ? item.genres.slice(0, 2).join(', ') : (item.genres || '')}</div>
                        </div>
                    </div>
                    ${statusBadge}
                </div>
            `;
        }).join('');
    }
    resultsDiv.style.display = 'block';
}

function setupCustomManualSearchDropdown() {
    document.addEventListener('input', (e) => {
        if (e.target && e.target.id === 'input-manual-search') {
            handleManualSearchInput(e.target);
        }
    });

    document.addEventListener('focusin', (e) => {
        if (e.target && e.target.id === 'input-manual-search') {
            handleManualSearchInput(e.target);
        }
    });

    document.addEventListener('click', (e) => {
        const inputSearch = document.getElementById('input-manual-search');
        const resultsDiv = document.getElementById('manual-search-results');
        if (inputSearch && resultsDiv && !inputSearch.contains(e.target) && !resultsDiv.contains(e.target)) {
            resultsDiv.style.display = 'none';
        }
    });
}

function selectManualDropdownItem(id, title, inLib) {
    if (inLib) {
        showToast(`⚠️ <strong>${title}</strong> zaten kitaplığınızda ekli! Tekrar ekleyemezsiniz.`, 2600);
        const resultsDiv = document.getElementById('manual-search-results');
        if (resultsDiv) resultsDiv.style.display = 'none';
        return;
    }
    const inputSearch = document.getElementById('input-manual-search');
    const resultsDiv = document.getElementById('manual-search-results');
    if (inputSearch) inputSearch.value = title;
    if (resultsDiv) resultsDiv.style.display = 'none';
}

function handleSaveManualEntry() {
    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        showToast('🔒 Kitaplığa içerik eklemek için lütfen giriş yapın veya kaydolun!', 2200);
        openAuthModal('LOGIN');
        return;
    }

    const inputSearch = document.getElementById('input-manual-search');
    const selectStatus = document.getElementById('select-manual-status');
    const checkWatched = document.getElementById('check-manual-watched');

    const queryTitle = inputSearch?.value.trim();
    if (!queryTitle) {
        showToast('⚠️ Lütfen eklenecek dizi/film adını yazınız.', 2200);
        return;
    }

    const dataset = (currentUniverse === 'MOVIES') 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    let foundItem = dataset.find(i => i.title.toLowerCase() === queryTitle.toLowerCase());
    if (!foundItem) {
        foundItem = dataset.find(i => i.title.toLowerCase().includes(queryTitle.toLowerCase()));
    }

    if (!foundItem) {
        showToast('⚠️ Seçtiğiniz yapım sistemde bulunamadı. Lütfen listeden bir dizi/film seçiniz!', 2500);
        return;
    }

    const targetLib = getActiveLibrary();
    const existing = targetLib.find(i => i.id === foundItem.id);
    if (existing) {
        showToast(`⚠️ <strong>${foundItem.title}</strong> zaten kitaplığınızda (${existing.status}) kayıtlı! Tekrar ekleyemezsiniz.`, 2800);
        return;
    }

    const finalStatus = checkWatched?.checked ? 'İzledim' : (selectStatus?.value || 'İzliyorum');
    const map = foundItem.season_episodes_map || [10];
    const totalSeasons = foundItem.seasons_num || (currentUniverse === 'MOVIES' ? 1 : map.length);
    const totalEpisodes = foundItem.total_episodes || (currentUniverse === 'MOVIES' ? 1 : map.reduce((a, b) => a + b, 0));

    let curS = 1;
    let curE = 1;
    if (finalStatus === 'İzledim') {
        curS = totalSeasons;
        curE = map[totalSeasons - 1] || 10;
    } else if (finalStatus === 'İzleyeceğim') {
        curS = 1;
        curE = 0;
    }

    targetLib.unshift({
        id: foundItem.id,
        title: foundItem.title,
        status: finalStatus,
        poster_url: foundItem.poster_url,
        rating: foundItem.rating,
        total_seasons: totalSeasons,
        total_episodes: totalEpisodes,
        season_episodes_map: map,
        current_season: curS,
        current_episode: curE,
        platform: foundItem.platform || 'Netflix',
        status_text: foundItem.status || 'Bitmiş / Final Yapmış',
        duo: foundItem.duo || '',
        summary: foundItem.summary || '',
        ep_duration: foundItem.ep_duration || (currentUniverse === 'MOVIES' ? 120 : 45),
        genres: foundItem.genres || [],
        trailer_url: foundItem.trailer_url || '',
        trailer_dub_url: foundItem.trailer_dub_url || '',
        trailer_sub_url: foundItem.trailer_sub_url || ''
    });

    showToast(`✅ <strong>${foundItem.title}</strong> kitaplığınıza (${finalStatus}) eklendi!`, 2200);
    window.BACKEND_REC_CACHE = {};
    if (typeof clearPersistedAIRecCache === 'function') clearPersistedAIRecCache(currentUniverse);
    if (inputSearch) inputSearch.value = '';
    const resultsDiv = document.getElementById('manual-search-results');
    if (resultsDiv) resultsDiv.style.display = 'none';
    updateLibraryUI({ notifyBadges: finalStatus === 'İzledim' });
}

function setupLibraryListeners() {
    document.addEventListener('click', (e) => {
        const chip = e.target.closest('.lib-chip');
        if (chip) {
            document.querySelectorAll('.lib-chip').forEach(c => c.classList.remove('active'));
            chip.classList.add('active');
            currentLibraryFilter = chip.getAttribute('data-status');
            currentLibraryPage = 1;
            renderLibraryCards();
            return;
        }

        const clearSearchBtn = e.target.closest('#btn-clear-library-search');
        if (clearSearchBtn) {
            clearLibrarySearch(true);
            const searchInput = document.getElementById('input-library-search');
            if (searchInput) searchInput.focus();
            return;
        }

        const btnSaveManual = e.target.closest('#btn-save-manual-entry');
        if (btnSaveManual) {
            handleSaveManualEntry();
            return;
        }
    });

    document.addEventListener('input', (e) => {
        if (!e.target || e.target.id !== 'input-library-search') return;
        currentLibrarySearchQuery = e.target.value || '';
        currentLibraryPage = 1;
        renderLibraryCards();
    });

    setupCustomManualSearchDropdown();
}


/* ==========================================================================
   🤖 DİJİTAL ASİSTAN & 'NE İZLESEM?' TAVSİYE MOTORU (2, 3, 4 VE 5. FOTOĞRAF BİREBİR)
   ========================================================================== */
let currentRecommendedItem = null;

function openAssistantModal() {
    const overlay = document.getElementById('assistant-modal-overlay');
    const titleEl = document.getElementById('assistant-modal-title');
    const submitBtn = document.getElementById('btn-submit-recommend');
    const closeBtn = document.querySelector('.modal-close-btn');
    const groupSeason = document.getElementById('group-max-season');
    const formBody = document.getElementById('assistant-form-body');
    const inspectBody = document.getElementById('inspect-details-body');
    const inspectShowBtn = document.getElementById('btn-inspect-show');
    const resultBox = document.getElementById('recommendation-result-box');
    const floatingBtn = document.getElementById('btn-floating-recommend');

    if (!overlay) return;

    const isMovie = (currentUniverse === 'MOVIES');

    if (titleEl) {
        titleEl.innerHTML = isMovie 
            ? `<i class="fa-solid fa-robot" style="color: #ef4444;"></i> Film Asistanı` 
            : `<i class="fa-solid fa-robot" style="color: #0ea5e9;"></i> Dizi Asistanı`;
    }

    if (closeBtn) {
        closeBtn.style.background = isMovie ? '#ef4444' : '#0ea5e9';
        closeBtn.style.boxShadow = isMovie ? '0 4px 15px rgba(239, 68, 68, 0.4)' : '0 4px 15px rgba(14, 165, 233, 0.4)';
    }

    if (submitBtn) {
        submitBtn.textContent = isMovie ? 'Film Öner' : 'Dizi Öner';
        if (isMovie) {
            submitBtn.style.background = 'linear-gradient(135deg, #ef4444 0%, #f59e0b 100%)';
        } else {
            submitBtn.style.background = 'linear-gradient(135deg, #0ea5e9 0%, #06b6d4 100%)';
        }
    }

    // Sezon Filtresi Sadece Dizilerde Görünür (Filmlerde Gizlenir)
    if (groupSeason) {
        groupSeason.style.display = isMovie ? 'none' : 'block';
    }

    // Tür ve Platform Checkbox Listelerini Doldur (VARSAYILAN BOŞ / ISARETSİZ)
    populateAssistantCheckboxes();

    if (formBody) formBody.style.display = 'block';
    if (inspectBody) inspectBody.style.display = 'none';
    if (inspectShowBtn) inspectShowBtn.style.display = 'none';
    if (resultBox) resultBox.style.display = 'none';

    overlay.style.display = 'flex';
    if (floatingBtn) floatingBtn.innerHTML = `<i class="fa-solid fa-sparkles"></i> Ne İzlesem? ▼`;
}

function closeAssistantModal() {
    const overlay = document.getElementById('assistant-modal-overlay');
    const floatingBtn = document.getElementById('btn-floating-recommend');
    if (overlay) overlay.style.display = 'none';
    if (floatingBtn) floatingBtn.innerHTML = `<i class="fa-solid fa-sparkles"></i> Ne İzlesem? ▲`;
}

// 2. ISTEK: BUTONA TIKLAYINCA PANEL AÇILSIN/KAPANSIN TOGGLE MOTORU
function toggleAssistantModal() {
    const overlay = document.getElementById('assistant-modal-overlay');
    if (!overlay) return;

    if (overlay.style.display === 'none' || !overlay.style.display) {
        openAssistantModal();
    } else {
        closeAssistantModal();
    }
}

// 3. ISTEK: (X) BUTONUNA BASINCA DUVARA GİZLEME VE SOL OK İLE TEKRAR AÇMA MOTORU
function collapseFloatingBar() {
    const wrapper = document.getElementById('floating-recommend-wrapper');
    const expandTab = document.getElementById('floating-expand-tab');

    closeAssistantModal();

    if (wrapper) wrapper.style.display = 'none';
    if (expandTab) expandTab.style.display = 'flex';
}

function expandFloatingBar() {
    const wrapper = document.getElementById('floating-recommend-wrapper');
    const expandTab = document.getElementById('floating-expand-tab');

    if (wrapper) wrapper.style.display = 'flex';
    if (expandTab) expandTab.style.display = 'none';
}

function populateAssistantCheckboxes() {
    const genreListEl = document.getElementById('genre-checkbox-list');
    const platformListEl = document.getElementById('platform-checkbox-list');

    const genres = ["Aile", "Aksiyon & Macera", "Belgesel", "Animasyon", "Bilim Kurgu & Fantastik", "Bilinmiyor", "Dram", "Gizem", "Komedi", "Suç", "Vahşi Batı", "Fantastik", "Romantik", "Gerilim", "Korku", "Tarih", "Savaş", "Müzik"];
    const platforms = ["Netflix", "Amazon Prime", "Disney Plus", "HBO / Max", "TOD TV", "BluTV", "GAIN", "Exxen", "tabii", "MUBI", "Diğer Platformlar"];

    if (genreListEl) {
        genreListEl.innerHTML = genres.map(g => `
            <label class="dropdown-item-check">
                <input type="checkbox" class="chk-genre-item" value="${g}" /> ${g}
            </label>
        `).join('');
    }

    if (platformListEl) {
        platformListEl.innerHTML = platforms.map(p => `
            <label class="dropdown-item-check">
                <input type="checkbox" class="chk-platform-item" value="${p}" /> ${p}
            </label>
        `).join('');
    }

    // Labels Reset to Choose Options
    const lblG = document.getElementById('label-selected-genres');
    const lblP = document.getElementById('label-selected-platforms');
    if (lblG) lblG.innerHTML = 'Choose options';
    if (lblP) lblP.innerHTML = 'Choose options';
}

function toggleMultiSelectDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;

    if (dropdown.style.display === 'none' || !dropdown.style.display) {
        document.querySelectorAll('.multiselect-dropdown-menu').forEach(m => m.style.display = 'none');
        dropdown.style.display = 'flex';
    } else {
        dropdown.style.display = 'none';
    }
}

function confirmMultiSelectDropdown(dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    if (dropdown) dropdown.style.display = 'none';

    if (dropdownId === 'dropdown-genres') {
        const checked = Array.from(document.querySelectorAll('.chk-genre-item:checked')).map(c => c.value);
        const label = document.getElementById('label-selected-genres');
        if (label) {
            if (checked.length === 0) {
                label.innerHTML = 'Choose options';
            } else {
                label.innerHTML = checked.map(val => `<span class="tag-chip">${val} <span class="remove-tag" onclick="uncheckItem('genre', '${val}', event)">×</span></span>`).join('');
            }
        }
    } else if (dropdownId === 'dropdown-platforms') {
        const checked = Array.from(document.querySelectorAll('.chk-platform-item:checked')).map(c => c.value);
        const label = document.getElementById('label-selected-platforms');
        if (label) {
            if (checked.length === 0) {
                label.innerHTML = 'Choose options';
            } else {
                label.innerHTML = checked.map(val => `<span class="tag-chip">${val} <span class="remove-tag" onclick="uncheckItem('platform', '${val}', event)">×</span></span>`).join('');
            }
        }
    }
}

function uncheckItem(type, value, event) {
    if (event) event.stopPropagation();
    const selector = (type === 'genre') ? `.chk-genre-item[value="${value}"]` : `.chk-platform-item[value="${value}"]`;
    const chk = document.querySelector(selector);
    if (chk) {
        chk.checked = false;
        confirmMultiSelectDropdown(type === 'genre' ? 'dropdown-genres' : 'dropdown-platforms');
    }
}

/** Asistan platform seçeneklerini katalog adlarıyla eşleştir */
function normalizePlatformToken(value) {
    return String(value || '')
        .toLowerCase()
        .replace(/ı/g, 'i').replace(/İ/g, 'i')
        .replace(/ğ/g, 'g').replace(/ü/g, 'u')
        .replace(/ş/g, 's').replace(/ö/g, 'o')
        .replace(/ç/g, 'c')
        .replace(/[^a-z0-9+]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

const ASSISTANT_PLATFORM_ALIASES = {
    'netflix': ['netflix'],
    'amazon prime': ['amazon prime', 'prime video', 'amazon prime video', 'amazon'],
    'disney plus': ['disney plus', 'disney+', 'disney'],
    'hbo / max': ['hbo', 'hbo max', 'max'],
    'apple tv+': ['apple tv+', 'apple tv', 'tv+'],
    'tod tv': ['tod tv', 'tod'],
    'blutv': ['blutv', 'blu tv'],
    'gain': ['gain'],
    'exxen': ['exxen'],
    'tabii': ['tabii'],
    'mubi': ['mubi']
};

function itemMatchesAssistantPlatform(item, selectedPlatforms) {
    if (!selectedPlatforms || !selectedPlatforms.length) return true;

    if (selectedPlatforms.includes('Diğer Platformlar')) {
        const known = Object.values(ASSISTANT_PLATFORM_ALIASES).flat();
        const haystack = normalizePlatformToken([
            item.platform,
            ...(Array.isArray(item.platforms) ? item.platforms : [])
        ].filter(Boolean).join(' '));
        const isKnown = known.some(alias => haystack.includes(alias));
        // "Diğer" yalnız başına seçildiyse bilinen platform dışı kalsın;
        // başka platformlarla birlikte seçildiyse OR mantığı aşağıda
        if (selectedPlatforms.length === 1) return !isKnown;
    }

    const itemTokens = [
        item.platform || '',
        ...(Array.isArray(item.platforms) ? item.platforms : [])
    ].map(normalizePlatformToken).filter(Boolean);
    const haystack = itemTokens.join(' | ');

    return selectedPlatforms.some(sp => {
        if (sp === 'Diğer Platformlar') return false;
        const key = normalizePlatformToken(sp);
        const aliases = ASSISTANT_PLATFORM_ALIASES[key] || [key];
        return aliases.some(alias => haystack.includes(alias));
    });
}

function itemMatchesAssistantGenre(item, selectedGenres) {
    if (!selectedGenres || !selectedGenres.length) return true;
    const itemGenres = Array.isArray(item.genres) ? item.genres : [];
    if (!itemGenres.length) return false;

    const norm = (s) => normalizePlatformToken(s);
    const itemNorm = itemGenres.map(norm);

    return selectedGenres.some(sg => {
        const sn = norm(sg);
        // Tam veya kısmi eşleşme: "Aksiyon & Macera" ↔ "Aksiyon", "Fantastik" ↔ "Bilim Kurgu & Fantastik"
        return itemNorm.some(ig => ig === sn || ig.includes(sn) || sn.includes(ig));
    });
}

// 3. FOTOĞRAFTAKİ BİREBİR 'DİZİ ÖNER' VE ÖNERİM MAVİ KUTUSU KONTROLÜ
function generateRecommendation() {
    const isMovie = (currentUniverse === 'MOVIES');
    const dataset = isMovie 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const selectedGenres = Array.from(document.querySelectorAll('.chk-genre-item:checked')).map(c => c.value);
    const selectedPlatforms = Array.from(document.querySelectorAll('.chk-platform-item:checked')).map(c => c.value);
    const maxSeason = parseInt(document.getElementById('range-max-season')?.value || 15, 10);

    const activeLib = getActiveLibrary();
    const userLibIds = new Set(activeLib.map(i => i.id));
    const hasFilters = selectedGenres.length > 0 || selectedPlatforms.length > 0 || (!isMovie && maxSeason < 15);

    // Filtreleme — seçilen tür/platform ZORUNLU; eşleşme yoksa rastgele havuza düşülmez
    let candidates = dataset.filter(item => {
        if (userLibIds.has(item.id)) return false;

        if (!isMovie && (item.seasons_num || item.total_seasons || 1) > maxSeason) {
            return false;
        }

        if (!itemMatchesAssistantPlatform(item, selectedPlatforms)) return false;
        if (!itemMatchesAssistantGenre(item, selectedGenres)) return false;

        return true;
    });

    // Aynı öneriyi peş peşe tekrarlama
    if (currentRecommendedItem && candidates.length > 1) {
        candidates = candidates.filter(item => item.id !== currentRecommendedItem.id);
    }

    if (candidates.length === 0) {
        const resultBox = document.getElementById('recommendation-result-box');
        const inspectShowBtn = document.getElementById('btn-inspect-show');
        if (resultBox) resultBox.style.display = 'none';
        if (inspectShowBtn) inspectShowBtn.style.display = 'none';
        currentRecommendedItem = null;

        if (hasFilters) {
            showToast('⚠️ Bu tür/platform filtresine uyan yapım bulunamadı. Filtreleri gevşetip tekrar dene.', 3200);
        } else {
            showToast('⚠️ Önerilecek yapım kalmadı.', 2200);
        }
        return;
    }

    const randomIndex = Math.floor(Math.random() * candidates.length);
    currentRecommendedItem = candidates[randomIndex];

    const resultBox = document.getElementById('recommendation-result-box');
    const recTitleDisplay = document.getElementById('rec-title-display');
    const inspectShowBtn = document.getElementById('btn-inspect-show');

    if (recTitleDisplay && currentRecommendedItem) {
        const genreHint = (currentRecommendedItem.genres || []).slice(0, 2).join(', ');
        const platHint = currentRecommendedItem.platform || '';
        recTitleDisplay.innerHTML = `Önerim: <strong>${currentRecommendedItem.title}</strong>`
            + (genreHint || platHint
                ? `<div style="margin-top:6px;font-size:0.78rem;opacity:0.85;">${[genreHint, platHint].filter(Boolean).join(' · ')}</div>`
                : '');
    }

    if (resultBox) resultBox.style.display = 'flex';
    if (inspectShowBtn) {
        inspectShowBtn.textContent = isMovie ? '🎬 Filmi İncele' : '📺 Diziyi İncele';
        inspectShowBtn.style.display = 'block';
    }
}

function likeRecommendation() {
    if (!currentRecommendedItem) return;
    // Tercih motoruna (Beğenilenler) kaydet
    likeItemPreference(currentRecommendedItem.id);
}

function addRecommendedToLibrary() {
    if (!currentRecommendedItem) return;
    addToLibraryFromExplore(currentRecommendedItem.id);
}
/* ==========================================================================
   📌 BAŞLIK: "AI TAVSİYELER" SEKMESİ - SİNONİM + KAVRAMSAL KÜME MOTORU
   ========================================================================== */
const SINONIM_MAP = {
    "zeki": "zeki akıllı dahi stratejik analitik kurnaz zekice manipülatif plan kuran akıl oyunları deha sherlock zeka oyunları death note code geass suits mentalist mind games breaking bad",
    "hapishane": "hapishane cezaevi firar mahkum gardiyan koğuş hücre parmaklık prison break vis a vis orange is the new black wentworth oz banshee",
    "ortaçağ": "ortaçağ taht krallık şövalye feodal savaş viking kılıç kale taht kavgaları game of thrones vikings last kingdom house of the dragon",
    "bilimkurgu": "bilimkurgu bilim kurgu uzay distopya gelecek teknoloji sibernetik siberpunk yapay zeka robot android uzaylı galaksi",
    "aksiyon": "aksiyon macera savaş dövüş yüksek tempo adrenalin silah patlama çatışma kovalamaca dövüş sanatları",
    "dram": "dram drama duygusal derin hikaye hayat hikayesi acıklı hüzünlü trajedi yaşanmış olaylar ağır dram gözyaşı breaking bad chernobyl",
    "komedi": "komedi komik mizah eğlenceli durum komedisi sitcom kahkaha parodi absürt espri güldürü friends office seinfeld brooklyn nine nine",
    "polisiye": "polisiye suç dedektif cinayet gizem soruşturma şerif ajan fbi cia ipucu dava katil polis true detective mindhunter criminal minds sherlock",
    "gerilim": "gerilim korku psikolojik gizem karanlık atmosfer tedirgin edici tekinsiz gergin süspans tırnak yedirten shutter island se7en",
    "korku": "korku dehşet ürkütücü kabus canavar yaratık slasher katil maskeli tehlike ani korku conjuring insidious it alien",
    "intikam": "intikam adalet hesaplaşma kanunsuzluk kurnazlık intikamcı öc alma ceza vendetta hesap sorma punisher revenge",
    "zamanda_yolculuk": "zamanda yolculuk zaman makinesi geçmiş gelecek paradoks zaman döngüsü time travel kelebek etkisi 12 monkeys dark timeless loki",
    "zombi": "zombi yürüyen ölüler salgın virüs enfekte kıyamet sonrası apocalypse last of us walking dead kingdom walkers",
    "korsan": "korsan anime manga güç tek parça deniz macera one piece naruto dragon ball japonya hunter x hunter jujutsu kaisen",
    "casusluk": "casusluk ajan casus fbi cia mi6 kgb gizli görev operasyon köstebek sızma şifre soğuk savaş jack ryan homeland",
    "karanlık": "karanlık kasvetli gotik depresif korku gerilim puslu distopik ürpertici tekinsiz noir gotham dark",
    "beyin_yakan": "beyin yakan kafa karıştırıcı karmaşık gizemli teoriler kurduran paradoks şaşırtıcı plot twist inception memento fight club shutter island tenet başlangıç prestij akıl defteri dövüş kulübü yıldızlararası"
};

/* ==========================================================================
   🧠 KAVRAMSAL TEMA KÜMELEYİCİ (CONCEPT CLUSTER ENGINE)
   Prison Break + Vis a Vis + OITNB → "hapishane" cluster → Oz öner
   Supernatural izleyen → The X-Files da izler (doğaüstü cluster)
   ========================================================================== */
const CONCEPT_THEMES = [
    {
        id: 'beyin_yakan', label: 'Beyin Yakan / Zihin Bükücü', icon: '🧠', maxRecs: 5,
        triggers: ['beyin yakan', 'beyinyakan', 'zihin bükücü', 'zihin bukucu', 'kafa karıştır', 'kafa karistir', 'mind bending', 'mind-bending', 'nonlinear', 'plot twist'],
        titleHints: [
            // Filmler (TR katalog adları)
            'başlangıç', 'tenet', 'prestij', 'akıl defteri', 'dövüş kulübü', 'yıldızlararası',
            'vanilla sky', 'shutter island', 'inception', 'memento', 'fight club', 'the prestige',
            'donnie darko', 'primer', 'coherence', 'predestination', 'looper',
            'source code', 'arrival', 'enemy', 'triangle', 'mr. nobody', 'cloud atlas', 'mulholland',
            'ex machina', 'annihilation', 'under the skin', 'pi', 'requiem for a dream',
            // Diziler
            'dark', 'westworld', 'black mirror', 'devs', 'severance', 'the oa', 'legacy of lies'
        ],
        keywords: [
            'mind-bending', 'mind bending', 'nonlinear', 'non-linear', 'paradoks', 'zaman döngüsü',
            'gerçeklik', 'rüya içinde', 'plot twist', 'zihin bükücü', 'kafa karıştırıcı',
            'time travel', 'zaman yolculuğu', 'paralel evren', 'bilinç', 'simülasyon'
        ],
        // "Beyin Avcıları", ejderha animasyonu vb. yanlış pozitifler
        excludeIf: ['how to train your dragon', 'ejderhanı nasıl eğitirsin', 'beyin avcı', 'mindhunter', 'dragon ball']
    },
    {
        id: 'hapishane', label: 'Hapishane & Kaçış Gerilimi', icon: '🔒', maxRecs: 4,
        triggers: ['hapishane', 'cezaevi', 'prison', 'mahkum', 'parmaklık'],
        titleHints: [
            'prison break', 'vis a vis', 'orange is the new black', 'oz', 'wentworth', 'banshee',
            'animal kingdom', 'papillon', 'shawshank', 'esaretin bedeli', 'kaçış planı', 'escape plan',
            'the experiment', 'das experiment', 'bronson', 'starred up', 'felon'
        ],
        keywords: ['hapishane', 'cezaevi', 'firar', 'mahkum', 'gardiyan', 'koğuş', 'tutuklama', 'parmaklık', 'hücre', 'hapis', 'inmate', 'penitentiary'],
        excludeIf: ['avengers', "earth's mightiest", 'marvel animation', 'süper kahraman']
    },
    {
        id: 'doğaüstü', label: 'Doğaüstü & Fantezi', icon: '👻', maxRecs: 3,
        triggers: ['doğaüstü', 'dogaustu', 'paranormal', 'vampir', 'hayalet'],
        titleHints: ['supernatural','the x files','x files','grimm','once upon a time','charmed','buffy','angel','constantine','sleepy hollow','the originals','legacies','wynonna earp','evil'],
        keywords: ['doğaüstü','vampir','hayalet','şeytan','demon','büyü','cadı','cin','iblis','ruh','monster','yaratık','paranormal','mistik','büyücü','lanet']
    },
    {
        id: 'polisiye_dedektif', label: 'Polisiye & Dedektif', icon: '🔍', maxRecs: 3,
        triggers: ['polisiye', 'dedektif', 'cinayet', 'soruşturma'],
        titleHints: ['true detective','mindhunter','criminal minds','sherlock','monk','psych','castle','mentalist','the wire','law & order','ncis','csi','bones','person of interest','se7en','zodiac','gone girl'],
        keywords: ['dedektif','cinayet','soruşturma','polis','katil','ipucu','dava','delil','seri katil','şüpheli','profiling','forensik']
    },
    {
        id: 'bilim_kurgu', label: 'Bilim Kurgu & Uzay', icon: '🚀', maxRecs: 3,
        triggers: ['bilimkurgu', 'bilim kurgu', 'sci-fi', 'uzay', 'distopya'],
        titleHints: ['rick and morty','the expanse','altered carbon','westworld','black mirror','dark','dark matter','fringe','star trek','battlestar galactica','firefly','the orville','matrix','blade runner','yıldızlararası','interstellar'],
        keywords: ['uzay','bilim kurgu','bilimkurgu','robot','android','yapay zeka','teknoloji','distopya','gelecek','galaksi','uzaylı','siberpunk','klonlama','paralel evren']
    },
    {
        id: 'ortaçağ_fantasy', label: 'Ortaçağ & Epik Fantezi', icon: '⚔️', maxRecs: 3,
        triggers: ['ortaçağ', 'ortacag', 'medieval', 'feodal', 'şövalye dönemi'],
        titleHints: ['game of thrones','the witcher','vikings','last kingdom','house of the dragon','the wheel of time','shadow and bone','merlin','outlander','rome','spartacus','gladiator','braveheart','kingdom of heaven'],
        keywords: ['ortaçağ','taht','krallık','şövalye','viking','feodal','kılıç','kalkan','kale','elfler','sihirbaz','savaşçı','kral','kraliçe']
        // "ejderha" tek başına animasyon/çocuk filmlerini çekmesin diye keywords'ten çıkarıldı
    },
    {
        id: 'anime', label: 'Anime & Animasyon', icon: '🎌', maxRecs: 3,
        titleHints: ['one piece','naruto','dragon ball','attack on titan','demon slayer','jujutsu kaisen','my hero academia','fullmetal alchemist','death note','hunter x hunter','bleach','one punch man','futurama'],
        keywords: ['anime','manga','animasyon','shinigami','jutsu','ninjutsu','chakra','titans','demon','hero','quirk','alchemy','soul reaper']
    },
    {
        id: 'suç_çete', label: 'Suç Örgütleri & Çete', icon: '💰', maxRecs: 3,
        titleHints: ['breaking bad','better call saul','narcos','peaky blinders','ozark','money heist','the sopranos','gomorra','el chapo','weeds','boardwalk empire','power','snowfall'],
        keywords: ['uyuşturucu','kartel','mafya','çete','suç örgütü','kara para','kaçakçılık','organize suç','mob','gang','traffik','dealer','baron']
    },
    {
        id: 'zombi_apokalips', label: 'Zombi & Apokalips', icon: '🧟', maxRecs: 2,
        triggers: ['zombi', 'zombie', 'ölü yürüyen'],
        titleHints: ['the walking dead','fear the walking dead','last of us','the last of us','z nation','dead set','santa clarita diet','all of us are dead','sweet home','train to busan'],
        // 'kingdom' çıkarıldı — "The Last Kingdom" yanlış pozitif
        keywords: ['zombi','zombie','apokalips','kıyamet sonrası','salgın','enfekte','hayatta kalma','survivor','post-apokaliptik','outbreak','walkers'],
        excludeIf: ['undead unluck', 'last kingdom', 'the last kingdom']
    },
    {
        id: 'casusluk_gizem', label: 'Casusluk & Gizli Operasyonlar', icon: '🕵️', maxRecs: 3,
        titleHints: ['homeland','jack ryan','the americans','burn notice','alias','covert affairs','quantico','nikita','24','spooks','killing eve'],
        keywords: ['casus','casusluk','ajan','gizli görev','operasyon','köstebek','sızma','istihbarat','cia','fbi','mi6','kgb','mossad','şifre','soğuk savaş']
    },
    {
        id: 'tıp_hastane', label: 'Tıp & Hastane Draması', icon: '🏥', maxRecs: 3,
        titleHints: ["grey's anatomy",'house md','er','scrubs','the good doctor','new amsterdam','chicago med'],
        keywords: ['doktor','hastane','ameliyat','hasta','tıp','klinik','cerrahi','hemşire','tanı','teşhis','acil servis']
    },
    {
        id: 'korku_gerilim', label: 'Korku & Psikolojik Gerilim', icon: '😱', maxRecs: 2,
        titleHints: ['american horror story','the haunting','bates motel','hannibal','you','mindhunter','ratched','dexter','castle rock','twin peaks'],
        keywords: ['korku','psikolojik','karanlık','gerilim','tekinsiz','kabus','dehşet','seri katil','takıntı','obsesyon','paranoia']
    },
    {
        id: 'komedi', label: 'Komedi & Sitcom', icon: '😂', maxRecs: 3,
        titleHints: ['friends','the office','seinfeld','brooklyn nine nine','parks and recreation','it crowd','arrested development','how i met your mother','modern family','community','big bang theory'],
        keywords: ['komedi','sitcom','esprili','güldürü','absürt','parodi','hiciv','stand-up','komik','mizah']
    },
    {
        id: 'zamanda_yolculuk', label: 'Zamanda Yolculuk & Paralel Evren', icon: '⏱️', maxRecs: 2,
        titleHints: ['dark','12 monkeys','timeless','travelers','outlander','the umbrella academy','loki','quantum leap','flash','continuum','manifest'],
        keywords: ['zaman yolculuğu','paradoks','zaman döngüsü','geçmiş gelecek','time travel','paralel evren','multiverse','zaman makinesi','kelebek etkisi']
    }
];

/** Kütüphaneyi temalara göre kümelere ayırır */
function detectLibraryClusters(library, dataset) {
    if (!library || library.length === 0) return [];
    const clusterScores = {};
    const clusterItems  = {};
    CONCEPT_THEMES.forEach(t => { clusterScores[t.id] = 0; clusterItems[t.id] = []; });

    library.forEach(libItem => {
        const fullItem   = dataset.find(d => d.id === libItem.id) || libItem;
        const titleLow   = (fullItem.title   || '').toLowerCase();
        const genresStr  = (Array.isArray(fullItem.genres) ? fullItem.genres.join(' ') : (fullItem.genres || '')).toLowerCase();
        const summaryLow = (fullItem.summary  || '').toLowerCase();
        const whyLow     = (Array.isArray(fullItem.why_watch) ? fullItem.why_watch.join(' ') : '').toLowerCase();
        const fullText   = `${titleLow} ${genresStr} ${summaryLow} ${whyLow}`;

        CONCEPT_THEMES.forEach(theme => {
            let s = 0;
            if (theme.titleHints.some(hint => titleLow.includes(hint))) s += 10;
            theme.keywords.forEach(kw => { if (fullText.includes(kw)) s += 2; });
            if (s > 0) {
                clusterScores[theme.id] += s;
                clusterItems[theme.id].push({ item: fullItem, score: s });
            }
        });
    });

    return CONCEPT_THEMES
        .filter(t => clusterScores[t.id] > 0)
        .sort((a, b) => clusterScores[b.id] - clusterScores[a.id])
        .map(t => ({
            theme: t,
            items: clusterItems[t.id].sort((a,b) => b.score - a.score).map(x => x.item),
            totalScore: clusterScores[t.id]
        }));
}

/** Bir adayın belirli bir tema cluster'ına uyum skorunu hesaplar */
function scoreCandidateForCluster(candidate, theme) {
    const titleLow   = (candidate.title   || '').toLowerCase();
    const genresStr  = (Array.isArray(candidate.genres) ? candidate.genres.join(' ') : '').toLowerCase();
    const summaryLow = (candidate.summary  || '').toLowerCase();
    const whyLow     = (Array.isArray(candidate.why_watch) ? candidate.why_watch.join(' ') : '').toLowerCase();
    const fullText   = `${titleLow} ${genresStr} ${summaryLow} ${whyLow}`;
    if (Array.isArray(theme.excludeIf) && theme.excludeIf.some(ex => fullText.includes(ex))) {
        return 0;
    }
    let score = 0;
    const titleHit = (theme.titleHints || []).some(hint => {
        const h = String(hint || '').toLowerCase();
        if (!h) return false;
        if (titleLow === h) return true;
        if (h.length <= 3) {
            return new RegExp(`(?:^|[\\s\\-:/])${h.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')}(?:$|[\\s\\-:/])`).test(titleLow);
        }
        return titleLow.includes(h);
    });
    if (titleHit) score += 14;
    theme.keywords.forEach(kw => { if (fullText.includes(kw)) score += 3; });
    return score;
}

/** Temalı sorguda (hapishane vb.) adayın gerçekten temaya uyup uymadığını kontrol eder */
function candidateMatchesActiveThemeQuery(candidate, userQuery) {
    if (!userQuery || !userQuery.trim()) return true;
    const q = userQuery.toLowerCase();
    const matchedThemes = CONCEPT_THEMES.filter(th =>
        th.keywords.some(kw => q.includes(kw)) ||
        th.titleHints.some(h => q.includes(h)) ||
        q.includes(th.id) ||
        (th.id === 'hapishane' && (q.includes('hapishane') || q.includes('cezaevi') || q.includes('prison')))
    );
    if (matchedThemes.length === 0) return true;

    return matchedThemes.some(th => {
        const s = scoreCandidateForCluster(candidate, th);
        // Bilinen başlık veya en az 2 keyword eşleşmesi (scoreCandidate title = +14)
        return s >= 6;
    });
}

function expandQueryText(query) {

    if (!query) return '';
    const cleanTokens = query.toLowerCase().split(/\s+/).filter(w => !TURKISH_STOP_WORDS.has(w) && w.length > 1);
    let expanded = cleanTokens.join(' ');
    
    for (const [key, synonyms] of Object.entries(SINONIM_MAP)) {
        if (cleanTokens.some(t => t.includes(key) || key.includes(t))) {
            expanded += " " + synonyms;
        }
    }
    return expanded;
}

function renderAIRecommenderUI() {
    const resultsContainer = document.getElementById('ai-results-container');
    const submitBtn = document.getElementById('btn-submit-ai');
    if (!resultsContainer) return;

    const isMovie = (currentUniverse === 'MOVIES');
    syncAIOngoingPrefUI();

    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        renderGuestLockBanner(resultsContainer, 'AI Tavsiyeler', isMovie);
        if (submitBtn) submitBtn.disabled = true;
        return;
    }

    const activeLib = (typeof getActiveLibrary === 'function') ? (getActiveLibrary() || []) : [];
    const libCount = activeLib.length;
    if (libCount < MIN_LIBRARY_FOR_AI) {
        renderLibraryMinBanner(resultsContainer, libCount, isMovie);
        if (submitBtn) submitBtn.disabled = true;
        return;
    }

    if (submitBtn) submitBtn.disabled = false;

    generateAIRecommendations();
}

const MIN_LIBRARY_FOR_AI = 5;

function renderLibraryMinBanner(containerEl, currentCount, isMovie) {
    if (!containerEl) return;
    const mediaWord = isMovie ? 'film' : 'dizi';
    const need = Math.max(0, MIN_LIBRARY_FOR_AI - (currentCount || 0));
    containerEl.innerHTML = `
        <div style="background: rgba(18, 15, 38, 0.9); border: 1px solid rgba(250, 204, 21, 0.45); border-radius: 20px; padding: 36px 22px; text-align: center; margin-top: 10px; box-shadow: 0 10px 30px rgba(0,0,0,0.45);">
            <i class="fa-solid fa-books" style="font-size: 2.6rem; color: #facc15; margin-bottom: 14px; display: block;"></i>
            <h3 style="color: #fff; font-weight: 800; font-size: 1.15rem; margin-bottom: 10px;">
                AI Tavsiyeler için kitaplığında en az ${MIN_LIBRARY_FOR_AI} ${mediaWord} olmalı
            </h3>
            <p style="color: #d1d5db; font-size: 0.92rem; max-width: 520px; margin: 0 auto 16px; line-height: 1.55;">
                Şu an <strong style="color:#facc15;">${currentCount || 0}</strong> ${mediaWord} var.
                Kişiselleştirilmiş öneri için <strong style="color:#fff;">${need} tane daha</strong> ekle —
                aksi halde motorun neye göre tavsiye vereceği belirsiz kalır.
            </p>
            <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap;">
                <button type="button" onclick="document.querySelector('.nav-item[data-tab=tab-explore]')?.click()" class="primary-gradient-btn" style="padding: 10px 20px; font-size: 0.88rem; border: none; border-radius: 50px; font-weight: 800; cursor: pointer;">
                    <i class="fa-solid fa-compass"></i> Keşfet’e Git
                </button>
                <button type="button" onclick="document.querySelector('.nav-item[data-tab=tab-library]')?.click()" class="secondary-gradient-btn" style="padding: 10px 20px; font-size: 0.88rem; border-radius: 50px; font-weight: 800; cursor: pointer;">
                    <i class="fa-solid fa-bookmark"></i> Kitaplığım
                </button>
            </div>
        </div>
    `;
}

const PLATFORM_ALIASES = {
    "netflix": ["netflix", "nf"],
    "prime": ["prime", "amazon", "amazon prime", "prime video"],
    "disney": ["disney", "disney+", "disney plus"],
    "blutv": ["blutv", "blu tv", "blu"],
    "mubi": ["mubi"],
    "gain": ["gain"],
    "exxen": ["exxen"],
    "tabii": ["tabii"]
};

function parseNegativeTerms(userQuery) {
    if (!userQuery) return [];
    const negPattern = /(?:ama|dışında|hariç|olmasın|istemiyorum)\s+([a-çğıöşü\w\s]+)/gi;
    const matches = [];
    let match;
    while ((match = negPattern.exec(userQuery)) !== null) {
        if (match[1]) {
            const words = match[1].toLowerCase().split(/\s+/).filter(w => w.length > 2 && !TURKISH_STOP_WORDS.has(w));
            matches.push(...words);
        }
    }
    return matches;
}

function parsePlatformQuery(userQuery) {
    if (!userQuery) return null;
    const lower = userQuery.toLowerCase();
    for (const [platformKey, aliases] of Object.entries(PLATFORM_ALIASES)) {
        if (aliases.some(alias => lower.includes(alias))) {
            return platformKey;
        }
    }
    return null;
}

async function getRecommendationsViaBackend(libraryItems, userUniverse, userQuery, includeOngoing) {
    try {
        const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
        const headers = { 'Content-Type': 'application/json' };
        const signed = getSignedAuthToken();
        if (signed) headers['Authorization'] = `Bearer ${signed}`;
        const hiddenIds = (userUniverse === 'MOVIES')
            ? (typeof HIDDEN_MOVIES_IDS !== 'undefined' ? HIDDEN_MOVIES_IDS : [])
            : (typeof HIDDEN_SERIES_IDS !== 'undefined' ? HIDDEN_SERIES_IDS : []);
        const res = await fetch(`${baseUrl}/api/recommendations`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                userQuery: userQuery || '',
                userUniverse: userUniverse || 'MOVIES',
                libraryItems: libraryItems || [],
                hiddenItemIds: hiddenIds || [],
                includeOngoing: includeOngoing !== false
            })
        });
        if (!res.ok) return null;
        return await res.json();
    } catch (e) {
        console.warn('Backend recommendations fetch failed:', e);
        return null;
    }
}

// ─── FAZ 3: KART OLUŞTURMA & ANLIK SLOT DOLUMU (INSTANT SLOT SWAP) ───
window.CURRENT_REC_STATE = { visible: [], overflowQueue: [], isMovie: false };

function buildAICardHTML(itemData, score, reason, isMovie) {
    const itemId = itemData.id;
    const title = itemData.title || 'Önerilen Yapım';
    const poster = resolvePosterUrl(itemData);
    
    let ratingVal = itemData.rating_num || itemData.puan_ortalamasi || itemData.puan || itemData.rating || 7.5;
    if (typeof ratingVal === 'number') ratingVal = ratingVal.toFixed(1);
    
    const seasonsOrDuration = isMovie 
        ? ((itemData.sure || itemData.ep_duration || 110) + ' dk')
        : (itemData.sezon_sayisi ? (itemData.sezon_sayisi + ' Sezon') : (itemData.seasons || '1 Sezon'));
    
    const platform = itemData.platformlar || itemData.platform || 'Netflix';
    const status = itemData.durum || itemData.status || 'Devam Ediyor';
    
    let genresStr = 'Dram';
    if (Array.isArray(itemData.genres)) genresStr = itemData.genres.join(', ');
    else if (itemData.tur) genresStr = itemData.tur;
    else if (itemData.turler) genresStr = itemData.turler;
    else if (itemData.genres) genresStr = String(itemData.genres);

    const summary = itemData.ozet || itemData.summary || 'Özet bilgisi bulunmuyor.';
    const year = itemData.vizyon_tarihi || itemData.cikis_tarihi || itemData.year || '';
    const backdropUrl = itemData.backdrop_url || '';
    const slogan = itemData.slogan || '';

    const canon = getCanonicalCatalogItem(itemId, title);
    const trailerDub = (canon && canon.trailer_dub_url) || itemData.trailer_dub_url || itemData.trailer_tr_url || '';
    const trailerSub = (canon && canon.trailer_sub_url) || itemData.trailer_sub_url || itemData.trailer_original_url || itemData.trailer_url || '';
    const hasTrailer = (typeof isValidTrailerUrl === 'function') 
        ? (isValidTrailerUrl(trailerDub) || isValidTrailerUrl(trailerSub))
        : Boolean(trailerDub || trailerSub);

    return `
        <div class="media-horizontal-card ai-recommendation-card" style="position: relative; border: 1px solid rgba(168, 85, 247, 0.4); box-shadow: 0 0 25px rgba(168, 85, 247, 0.15); margin-bottom: 20px;">
            ${renderCardBackdropHtml(backdropUrl, 'hero')}

            <!-- ÜST BÖLÜM: AFİŞ VE SAĞ DETAYLAR -->
            <div class="card-top-row" style="padding-top: ${backdropUrl ? '0px' : '16px'}; margin-top: ${backdropUrl ? '-36px' : '0px'}; position: relative; z-index: 2;">
                <div class="card-left-poster" style="position: relative;">
                    ${posterImgHtml(poster, title)}
                    <div style="position: absolute; top: 8px; left: 8px; background: rgba(0,0,0,0.85); border: 1px solid #facc15; border-radius: 12px; padding: 2px 8px; font-weight: 800; font-size: 0.75rem; color: #facc15; backdrop-filter: blur(4px);">
                        ⚡ %${score} Yapay Zeka Uyum
                    </div>
                </div>
                <div class="card-right-details">
                    <h2 class="card-item-title">${escapeHtml(title)}</h2>

                    <div class="card-badges-row">
                        <span class="badge-yellow"><i class="fa-solid fa-star"></i> Puan: ${ratingVal}</span>
                        <span class="badge-purple"><i class="fa-solid fa-film"></i> ${seasonsOrDuration}</span>
                        ${year ? `<span class="badge-cyan" style="background: rgba(14, 165, 233, 0.15); border-color: #0ea5e9; color: #38bdf8;"><i class="fa-solid fa-calendar-days"></i> ${year}</span>` : ''}
                        <span class="badge-cyan" style="background: rgba(236, 72, 153, 0.2); border-color: #ec4899; color: #ec4899;">⚡ %${score} Yapay Zeka Uyumu</span>
                    </div>

                    <div class="card-platform-status">
                        📺 ${formatPlatformLinks(platform, title)} | 📌 ${escapeHtml(status)}
                    </div>

                    <div class="card-genres">
                        🎭 ${escapeHtml(genresStr)}
                    </div>

                    <!-- AI GEREKÇE KUTUSU -->
                    <div style="font-size: 0.88rem; color: #d8b4fe; line-height: 1.4; margin: 10px 0; background: rgba(168, 85, 247, 0.12); padding: 10px 12px; border-radius: 10px; border-left: 4px solid #a855f7;">
                        ${reason}
                    </div>

                    <p class="card-summary-text">${escapeHtml(summary)}</p>
                </div>
            </div>

            <!-- ALT AKSİYON BUTONLARI ROW -->
            <div class="card-bottom-actions-row">
                <button onclick="openItemDetailModal('${itemId}')" class="card-action-btn" style="background: rgba(168, 85, 247, 0.2); border: 1px solid #a855f7; color: #c084fc; font-weight: 700;">
                    <i class="fa-solid fa-circle-info"></i> Detaylı İncele
                </button>
                ${hasTrailer ? `
                    <button onclick="openTrailerModal('${itemId}', '${escapeQuotes(title)}', 'tr', '${escapeQuotes(trailerDub)}', '${escapeQuotes(trailerSub)}', ${Boolean(!isMovie)})" class="card-action-btn btn-trailer-play">
                        <i class="fa-solid fa-play"></i> Fragman İzle
                    </button>
                ` : `
                    <button class="card-action-btn btn-no-trailer" onclick="showToast('⚠️ Fragman bulunamadı.', 2000)">
                        <i class="fa-solid fa-film"></i> Fragman Henüz Yok
                    </button>
                `}
                <button onclick="addRecToLibrary('${itemId}', this)" class="card-action-btn btn-add-library">
                    <i class="fa-solid fa-plus"></i> Kitaplığa Ekle
                </button>
                <button onclick="likeItemPreference('${itemId}')" class="card-action-btn btn-like">
                    <i class="fa-solid fa-thumbs-up"></i> Beğen
                </button>
                <button onclick="hideRecCard('${itemId}', this)" class="card-action-btn btn-hide">
                    <i class="fa-solid fa-eye-slash"></i> Gizle
                </button>
                <button onclick="openErrorReportModal('${itemId}')" class="card-action-btn btn-report-error">
                    <i class="fa-solid fa-flag"></i> Hatayı Bildir
                </button>
            </div>
        </div>
    `;
}

function getMediaItemFullDetails(candidate, dataset) {
    if (!candidate) return null;
    const rawId = String(candidate.id || '');
    const cTitle = String(candidate.title || '').toLowerCase().trim();
    const extractDigits = (s) => String(s).replace(/\D/g, '');
    const cNum = extractDigits(rawId);

    let found = null;
    if (dataset && Array.isArray(dataset)) {
        // 1. Exact ID match
        found = dataset.find(d => d && String(d.id) === rawId);
        // 2. Numeric ID match (movies_122 <-> movie_122 <-> 122)
        if (!found && cNum) {
            found = dataset.find(d => d && extractDigits(d.id) === cNum);
        }
        // 3. Title match
        if (!found && cTitle) {
            found = dataset.find(d => d && d.title && String(d.title).toLowerCase().trim() === cTitle);
        }
    }

    if (found) {
        return {
            ...found,
            id: candidate.id || found.id,
            afis_url: found.afis_url || found.poster_url || candidate.poster_url,
            poster_url: found.poster_url || found.afis_url || candidate.poster_url,
            summary: found.summary || found.ozet || candidate.summary,
            ozet: found.ozet || found.summary || candidate.summary,
            genres: found.genres || found.tur || found.turler || candidate.genres,
            rating_num: found.rating_num || candidate.rating || 7.5,
            platform: found.platform || found.platformlar || candidate.platform || 'Netflix',
            year: found.year || found.cikis_tarihi || found.vizyon_tarihi || candidate.year
        };
    }

    return {
        id: candidate.id,
        title: candidate.title || 'Önerilen Yapım',
        afis_url: candidate.poster_url || 'https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500',
        poster_url: candidate.poster_url || 'https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500',
        genres: candidate.genres || 'Dram',
        summary: candidate.summary || 'Semantik vektör analizi ile izleme geçmişinize en uygun içerik olarak seçilmiştir.',
        ozet: candidate.summary || 'Semantik vektör analizi ile izleme geçmişinize en uygun içerik olarak seçilmiştir.',
        rating_num: candidate.rating || 7.5,
        platform: candidate.platform || 'Netflix',
        year: candidate.year || '',
        seasons: candidate.duration_or_seasons || '110 dk',
        ep_duration: candidate.duration_or_seasons || '110 dk'
    };
}

function renderAIRecommendationsCards(recsPayload, userQuery, container, isMovie, onlyEnded) {
    if (!container) return;

    let visibleItems = [];
    let overflowQueue = [];

    if (recsPayload && recsPayload.visible && Array.isArray(recsPayload.visible)) {
        visibleItems = recsPayload.visible.slice(0, 15);
        overflowQueue = [
            ...(recsPayload.visible.slice(15) || []),
            ...(recsPayload.overflowQueue || []),
            ...(Array.isArray(recsPayload.recommendations) ? recsPayload.recommendations.slice(15) : [])
        ];
    } else if (recsPayload && Array.isArray(recsPayload.recommendations)) {
        visibleItems = recsPayload.recommendations.slice(0, 15);
        overflowQueue = recsPayload.recommendations.slice(15);
    } else if (recsPayload && Array.isArray(recsPayload.results)) {
        visibleItems = recsPayload.results.slice(0, 15);
        overflowQueue = recsPayload.results.slice(15);
    } else if (Array.isArray(recsPayload)) {
        visibleItems = recsPayload.slice(0, 15);
        overflowQueue = recsPayload.slice(15);
    }

    const preferEnded = (onlyEnded === true) || (!isMovie && getAIOnlyEndedPref());
    visibleItems = filterEndedOnlyRecommendations(visibleItems, preferEnded, isMovie);
    overflowQueue = filterEndedOnlyRecommendations(overflowQueue, preferEnded, isMovie);

    // Görünür slotlar boşaldıysa overflow'dan doldur (en fazla 15 kart)
    while (visibleItems.length < 15 && overflowQueue.length > 0) {
        visibleItems.push(overflowQueue.shift());
    }

    window.CURRENT_REC_STATE = { visible: visibleItems, overflowQueue: overflowQueue, isMovie: isMovie };

    if (!visibleItems || visibleItems.length === 0) {
        container.innerHTML = `
            <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: #9ca3af; background: rgba(25, 20, 45, 0.8); border-radius: 16px;">
                🔍 Harika öneriler bulmak için kitaplığını güncelle veya «Önerileri Yenile»ye bas.
            </div>
        `;
        return;
    }

    const dataset = isMovie 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    let html = `<div style="grid-column: 1 / -1; display: flex; flex-direction: column; gap: 16px;">`;
    visibleItems.forEach(item => {
        const candidate = item.candidate || item;
        const fullData = getMediaItemFullDetails(candidate, dataset) || candidate;
        const score = candidate.aiMatchScore || candidate.score || 85;
        const reason = candidate.aiReason || candidate.reasonText || 'Kütüphanenizle yüksek yapay zeka uyumu.';
        html += `<div id="ai-rec-card-${candidate.id}">${buildAICardHTML(fullData, score, reason, isMovie)}</div>`;
    });
    html += `</div>`;
    container.innerHTML = html;
}

function handleInstantSlotSwap(itemId, buttonEl) {
    const cardEl = buttonEl ? buttonEl.closest('[id^="ai-rec-card-"]') : document.getElementById(`ai-rec-card-${itemId}`);
    if (!cardEl) return;

    if (!window.CURRENT_REC_STATE || !window.CURRENT_REC_STATE.overflowQueue || window.CURRENT_REC_STATE.overflowQueue.length === 0) {
        cardEl.style.transition = 'all 0.3s ease';
        cardEl.style.opacity = '0';
        cardEl.style.transform = 'scale(0.85)';
        setTimeout(() => {
            cardEl.innerHTML = `
                <div style="background: rgba(18, 14, 38, 0.6); border: 1px dashed rgba(168, 85, 247, 0.3); border-radius: 16px; padding: 25px; text-align: center; color: #a7f3d0; font-size: 0.85rem;">
                    ✨ Bu kulvardaki tüm önerileri incelediniz!
                </div>
            `;
            cardEl.style.opacity = '1';
            cardEl.style.transform = 'scale(1)';
        }, 300);
        return;
    }

    const nextItem = window.CURRENT_REC_STATE.overflowQueue.shift();
    const isMovie = window.CURRENT_REC_STATE.isMovie;
    const dataset = isMovie 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const fullData = getMediaItemFullDetails(nextItem, dataset);
    const score = nextItem.aiMatchScore || 85;
    const reason = nextItem.aiReason || 'İzleme profilinizle yüksek yapay zeka uyumu.';

    cardEl.style.transition = 'all 0.3s ease';
    cardEl.style.opacity = '0';
    cardEl.style.transform = 'scale(0.85)';

    setTimeout(() => {
        cardEl.id = `ai-rec-card-${nextItem.id}`;
        cardEl.innerHTML = buildAICardHTML(fullData, score, reason, isMovie);
        cardEl.style.opacity = '1';
        cardEl.style.transform = 'scale(1)';
    }, 300);
}

function purgeItemFromRecState(itemId) {
    if (!window.CURRENT_REC_STATE) return;
    const matches = (entry) => {
        const candidate = entry && (entry.candidate || entry);
        if (!candidate || candidate.id == null) return false;
        return idsLooselyEqual(candidate.id, itemId);
    };
    window.CURRENT_REC_STATE.visible = (window.CURRENT_REC_STATE.visible || []).filter(x => !matches(x));
    window.CURRENT_REC_STATE.overflowQueue = (window.CURRENT_REC_STATE.overflowQueue || []).filter(x => !matches(x));
}

function addRecToLibrary(itemId, buttonEl) {
    const added = addToLibraryFromExplore(itemId);
    if (!added) return;
    purgeItemFromRecState(itemId);
    handleInstantSlotSwap(itemId, buttonEl);
}

function hideRecCard(itemId, buttonEl) {
    const isMovie = (currentUniverse === 'MOVIES');
    if (isMovie) {
        if (typeof HIDDEN_MOVIES_IDS !== 'undefined' && !HIDDEN_MOVIES_IDS.includes(itemId)) {
            HIDDEN_MOVIES_IDS.push(itemId);
        }
    } else {
        if (typeof HIDDEN_SERIES_IDS !== 'undefined' && !HIDDEN_SERIES_IDS.includes(itemId)) {
            HIDDEN_SERIES_IDS.push(itemId);
        }
    }
    handleInstantSlotSwap(itemId, buttonEl);
}

/* ==========================================================================
   📌 2 AŞAMALI HİBRİT ARAMA & AKILLI TAVSİYE MOTORU (RETRIEVAL + RERANKING)
   ========================================================================== */
function isCatalogItemOngoing(itemOrId) {
    if (!itemOrId) return false;
    const id = typeof itemOrId === 'string' ? itemOrId : (itemOrId.id || '');
    let status = '';
    if (typeof itemOrId === 'object') {
        status = String(itemOrId.status || itemOrId.durum || '');
    }
    if (!status && id && typeof REAL_SERIES_DATA !== 'undefined') {
        const found = REAL_SERIES_DATA.find(d => d.id === id || d.id === `series_${String(id).replace(/^series_/, '')}`);
        if (found) status = String(found.status || '');
    }
    const s = status.toLowerCase();
    if (!s) return false;
    if (s.includes('bitmiş') || s.includes('bitmis') || s.includes('final')) return false;
    return s.includes('devam') || s.includes('ongoing');
}

function filterEndedOnlyRecommendations(items, onlyEnded, isMovie) {
    if (!onlyEnded || isMovie || !Array.isArray(items)) return items || [];
    return items.filter(item => {
        const candidate = item.candidate || item;
        return !isCatalogItemOngoing(candidate);
    });
}

function getAIOnlyEndedPref() {
    const username = CURRENT_USER && CURRENT_USER !== 'Kullanıcı' ? CURRENT_USER.toLowerCase() : 'guest';
    const key = `AI_ONLY_ENDED_${username}`;
    const saved = localStorage.getItem(key);
    if (saved === '1' || saved === 'true') return true;
    if (saved === '0' || saved === 'false') return false;

    // Eski anahtardan migrasyon
    const legacy = localStorage.getItem(`AI_INCLUDE_ONGOING_${username}`);
    if (legacy === '1' || legacy === 'true') return false;
    if (legacy === '0' || legacy === 'false') return true;

    // Varsayılan: kitaplık çoğunlukla bitmişse sadece bitmiş öner
    return !inferIncludeOngoingFromLibrary();
}

function setAIOnlyEndedPref(value) {
    const username = CURRENT_USER && CURRENT_USER !== 'Kullanıcı' ? CURRENT_USER.toLowerCase() : 'guest';
    localStorage.setItem(`AI_ONLY_ENDED_${username}`, value ? '1' : '0');
    window.BACKEND_REC_CACHE = {};
    window.CURRENT_REC_STATE = { visible: [], overflowQueue: [], isMovie: currentUniverse === 'MOVIES' };
    clearPersistedAIRecCache(currentUniverse);
}

/** Kitaplık parmak izi — değişince AI tavsiye cache geçersiz */
function buildAIRecLibraryFingerprint(libraryItemsPayload, onlyEnded) {
    const libPart = (libraryItemsPayload || [])
        .map(x => `${x.id}:${Number(x.weight) || 1}:${Number(x.user_rating) || 0}`)
        .sort()
        .join('_');
    return `v2_${currentUniverse}_${onlyEnded ? 1 : 0}_${libPart}`;
}

function getAIRecPersistStorageKey() {
    const user = (CURRENT_USER && CURRENT_USER !== 'Kullanıcı') ? CURRENT_USER.toLowerCase() : 'guest';
    return `AI_REC_PERSIST_v2_${user}`;
}

function loadPersistedAIRecCache(fingerprint) {
    try {
        const raw = localStorage.getItem(getAIRecPersistStorageKey());
        if (!raw) return null;
        const bag = JSON.parse(raw);
        const slot = bag && bag[currentUniverse];
        if (!slot || slot.fp !== fingerprint || !slot.data) return null;
        // 30 gün — kitaplık aynıysa sonuç geçerli
        if (slot.savedAt && (Date.now() - Number(slot.savedAt)) > 30 * 24 * 60 * 60 * 1000) return null;
        return slot.data;
    } catch (e) {
        return null;
    }
}

function savePersistedAIRecCache(fingerprint, data) {
    if (!data || data === 'FALLBACK' || data === 'LOADING') return;
    try {
        const key = getAIRecPersistStorageKey();
        let bag = {};
        try { bag = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (e) { bag = {}; }
        bag[currentUniverse] = {
            fp: fingerprint,
            savedAt: Date.now(),
            data
        };
        localStorage.setItem(key, JSON.stringify(bag));
    } catch (e) {
        // kota / private mode — sessiz
    }
}

function clearPersistedAIRecCache(universeOverride) {
    try {
        const key = getAIRecPersistStorageKey();
        const uni = universeOverride || currentUniverse;
        const raw = localStorage.getItem(key);
        if (!raw) return;
        const bag = JSON.parse(raw) || {};
        if (uni && bag[uni]) {
            delete bag[uni];
            localStorage.setItem(key, JSON.stringify(bag));
        }
    } catch (e) { /* ignore */ }
}

/** Fallback motorunda Oz tekelliğini kır — az kullanılmış referansı tercih et */
function pickDiverseReferenceItem(candidate, referencePool, usedRefCounts, nearMargin = 4) {
    if (!referencePool || !referencePool.length) return { ref: null, reason: '', score: 0 };
    const scored = [];
    for (const refItem of referencePool) {
        const refGenres = refItem.genres || [];
        const candGenres = candidate.genres || [];
        let refScore = 50;
        let matchReason = '';
        let bestThemeBonus = 0;
        let bestThemeLabel = '';
        for (const theme of CONCEPT_THEMES) {
            const refThemeScore = scoreCandidateForCluster(refItem, theme);
            const candThemeScore = scoreCandidateForCluster(candidate, theme);
            if (refThemeScore >= 8 && candThemeScore >= 3) {
                const themeBonus = Math.min(35, refThemeScore + candThemeScore);
                if (themeBonus > bestThemeBonus) {
                    bestThemeBonus = themeBonus;
                    bestThemeLabel = `${theme.icon} ${theme.label}`;
                }
            }
        }
        if (bestThemeBonus > 0) {
            refScore += bestThemeBonus;
            matchReason = `${bestThemeLabel} temasında örtüşüyor`;
        } else {
            const sharedGenres = candGenres.filter(g => refGenres.includes(g));
            refScore += sharedGenres.length * 6;
            matchReason = sharedGenres.length > 0
                ? `${sharedGenres[0]} türünde benzer atmosfer`
                : `${candGenres[0] || 'Dram'} türünde önerildi`;
        }
        scored.push({ refItem, refScore, matchReason });
    }
    scored.sort((a, b) => b.refScore - a.refScore);
    const best = scored[0].refScore;
    const near = scored.filter(s => s.refScore >= best - nearMargin);
    near.sort((a, b) => {
        const ua = usedRefCounts[a.refItem.id] || 0;
        const ub = usedRefCounts[b.refItem.id] || 0;
        const oa = ua >= 3 ? 1 : 0;
        const ob = ub >= 3 ? 1 : 0;
        return oa - ob || ua - ub || b.refScore - a.refScore;
    });
    const pick = near[0];
    usedRefCounts[pick.refItem.id] = (usedRefCounts[pick.refItem.id] || 0) + 1;
    return { ref: pick.refItem, reason: pick.matchReason, score: pick.refScore };
}

function getAIIncludeOngoingPref() {
    return !getAIOnlyEndedPref();
}

function setAIIncludeOngoingPref(value) {
    setAIOnlyEndedPref(!value);
}

function inferIncludeOngoingFromLibrary() {
    if (currentUniverse === 'MOVIES') return true;
    const lib = (typeof getActiveLibrary === 'function') ? getActiveLibrary() : [];
    const dataset = (typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : [];
    if (!lib.length || !dataset.length) return false;
    let ended = 0;
    let ongoing = 0;
    const byId = new Map(dataset.map(d => [d.id, d]));
    for (const item of lib) {
        const full = byId.get(item.id);
        const st = (full && full.status) ? String(full.status) : '';
        if (st.includes('Devam')) ongoing += 1;
        else if (st.includes('Bitmiş') || st.includes('Final')) ended += 1;
    }
    const total = ended + ongoing;
    if (total < 4) return false;
    return (ongoing / total) >= 0.30;
}

function syncAIOngoingPrefUI() {
    const wrap = document.getElementById('ai-ongoing-pref-wrap');
    const checkbox = document.getElementById('check-ai-only-ended') || document.getElementById('check-ai-include-ongoing');
    const titleEl = document.getElementById('ai-ongoing-pref-title');
    const descEl = document.getElementById('ai-ongoing-pref-desc');
    if (!wrap || !checkbox) return;

    const isSeries = currentUniverse !== 'MOVIES';

    if (!isSeries) {
        wrap.style.display = 'none';
        return;
    }

    wrap.style.display = 'flex';
    wrap.style.opacity = '1';
    checkbox.disabled = false;
    checkbox.style.opacity = '1';
    checkbox.checked = getAIOnlyEndedPref();
    if (titleEl) titleEl.textContent = 'Sadece bitmiş / final dizileri öner';
    if (descEl) descEl.textContent = 'Açıkken Dead City gibi devam eden yapımlar ve güncel spin-off’lar önerilmez.';
}

function generateAIRecommendations() {
    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        const resultsContainer = document.getElementById('ai-results-container');
        if (resultsContainer) renderGuestLockBanner(resultsContainer, 'AI Tavsiyeler', currentUniverse === 'MOVIES');
        return;
    }

    const resultsContainer = document.getElementById('ai-results-container');
    if (!resultsContainer) return;

    const isMovie = (currentUniverse === 'MOVIES');
    const activeLibEarly = (typeof getActiveLibrary === 'function') ? (getActiveLibrary() || []) : [];
    if (activeLibEarly.length < MIN_LIBRARY_FOR_AI) {
        renderLibraryMinBanner(resultsContainer, activeLibEarly.length, isMovie);
        const submitBtn = document.getElementById('btn-submit-ai');
        if (submitBtn) submitBtn.disabled = true;
        return;
    }

    syncAIOngoingPrefUI();

    // Tema arama metni kaldırıldı — öneriler yalnızca kitaplık/favori profiline göre
    const userQuery = '';
    const onlyEnded = isMovie ? false : getAIOnlyEndedPref();
    const includeOngoing = !onlyEnded;

    const dataset = isMovie 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const activeLib = activeLibEarly;
    const hiddenIds = isMovie ? (HIDDEN_MOVIES_IDS || []) : (HIDDEN_SERIES_IDS || []);
    const likedIds = isMovie ? (LIKED_MOVIES_IDS || []) : (LIKED_SERIES_IDS || []);

    const libraryItemsPayload = activeLib.map(item => {
        let weight = 1.0;
        const isFav = USER_FAVORITES.includes(item.id);
        const isLiked = likedIds.includes(item.id);
        const userRating = Number(item.user_rating || 0);

        if (isFav) weight = 1.3;
        else if (isLiked) weight = 1.5;
        else if (item.status && String(item.status).includes('İzledim')) weight = 1.25;
        else if (item.status && String(item.status).includes('İzliyorum')) weight = 0.7;
        else if (item.status && String(item.status).includes('Yarıda')) weight = -0.6;

        if (userRating >= 5) weight = Math.max(weight, 1.65);
        else if (userRating >= 4) weight = Math.max(weight, 1.45);
        else if (userRating >= 3) weight = Math.max(weight, 1.15);
        else if (userRating === 2) weight = Math.min(weight > 0 ? weight : 1, 0.75);
        else if (userRating === 1) weight = -0.35;

        return {
            id: item.id,
            weight,
            title: item.title,
            status: item.status,
            user_rating: userRating,
            liked: isLiked,
            favorite: isFav
        };
    });

    if (typeof window.BACKEND_REC_CACHE === 'undefined') {
        window.BACKEND_REC_CACHE = {};
    }
    const recFingerprint = buildAIRecLibraryFingerprint(libraryItemsPayload, onlyEnded);
    const recCacheKey = recFingerprint;
    let recBackendData = window.BACKEND_REC_CACHE[recCacheKey];

    // Kitaplık değişmediyse F5 / yeniden girişte API'yi tekrar çağırma
    if (recBackendData === undefined) {
        const persisted = loadPersistedAIRecCache(recFingerprint);
        if (persisted) {
            window.BACKEND_REC_CACHE[recCacheKey] = persisted;
            recBackendData = persisted;
        }
    }

    if (recBackendData === undefined || recBackendData === 'LOADING') {
        if (recBackendData === undefined) {
            window.BACKEND_REC_CACHE[recCacheKey] = 'LOADING';
            getRecommendationsViaBackend(
                libraryItemsPayload,
                currentUniverse === 'MOVIES' ? 'MOVIES' : 'SERIES',
                userQuery,
                includeOngoing
            ).then(data => {
                if (data && (data.visible || data.recommendations || data.results)) {
                    window.BACKEND_REC_CACHE[recCacheKey] = data;
                    savePersistedAIRecCache(recFingerprint, data);
                } else {
                    window.BACKEND_REC_CACHE[recCacheKey] = 'FALLBACK';
                }
                generateAIRecommendations();
            }).catch(err => {
                window.BACKEND_REC_CACHE[recCacheKey] = 'FALLBACK';
                generateAIRecommendations();
            });
        }

        resultsContainer.innerHTML = `
            <div style="grid-column: 1 / -1; background: rgba(22, 18, 42, 0.95); border: 2px dashed #a855f7; border-radius: 20px; padding: 45px 20px; text-align: center; box-shadow: 0 0 35px rgba(168, 85, 247, 0.3);">
                <div style="width: 58px; height: 58px; border: 4px solid rgba(168, 85, 247, 0.2); border-top-color: #facc15; border-right-color: #a855f7; border-radius: 50%; animation: spin 0.7s linear infinite; margin: 0 auto 18px;"></div>
                <div style="font-size: 1.25rem; font-weight: 900; color: #fff; letter-spacing: 0.5px; display: flex; align-items: center; justify-content: center; gap: 10px;">
                    <span>🧠 Yapay Zeka Öneri Motoru Arıyor...</span>
                </div>
                <div style="font-size: 0.92rem; color: #c084fc; font-weight: 700; margin-top: 8px;">
                    "${userQuery || 'Kişiselleştirilmiş İzleme Tercihleriniz'}" temasına uygun adaylar analiz ediliyor...
                </div>
                <div style="font-size: 0.82rem; color: #9ca3af; margin-top: 8px;">
                    ✨ Zevk profiliniz ve arama niyetiniz eşleştiriliyor. Lütfen bekleyin.
                </div>
            </div>
        `;
        return;
    }

    if (recBackendData && recBackendData !== 'LOADING' && recBackendData !== 'FALLBACK') {
        renderAIRecommendationsCards(recBackendData, userQuery, resultsContainer, isMovie, onlyEnded);
        return;
    }


    // 1. AŞAMA: İLERİ SEVİYE SİNONİM VE SÖZCÜK GENİŞLETME (RETRIEVAL)
    const expandedQuery = expandQueryText(userQuery);
    const queryTokens = expandedQuery.split(/\s+/).filter(w => w.length > 2);
    const libraryIds = new Set(activeLib.map(i => i && i.id).filter(Boolean));
    const requestedPlatformKey = (typeof parsePlatformQuery === 'function') ? parsePlatformQuery(userQuery) : null;
    const negativeKeywords = (typeof parseNegativeTerms === 'function') ? parseNegativeTerms(userQuery) : [];

    // 🔧 ADAY HAVUZU: Kullanıcının kütüphanesinde olmayan tüm yapımlar
    const candidates = dataset.filter(item => {
        if (libraryIds.has(item.id)) return false;
        if (hiddenIds.includes(item.id)) return false;
        if (onlyEnded && isCatalogItemOngoing(item)) return false;
        if (requestedPlatformKey) {
            const p = (item.platform || '').toLowerCase();
            const aliases = PLATFORM_ALIASES[requestedPlatformKey] || [requestedPlatformKey];
            if (!aliases.some(alias => p.includes(alias))) return false;
        }
        // Temalı sorgu (hapishane vb.): alakasız adayları (Avengers vs.) ele
        if (userQuery && !candidateMatchesActiveThemeQuery(item, userQuery)) return false;
        return true;
    });

    // 🔧 REFERANS HAVUZU: Kullanıcının izlediği / beğendiği yapımlar (Cosine benzeri ağırlıklı)
    const referencePool = activeLib.length > 0
        ? activeLib.map(item => dataset.find(d => d.id === item.id) || item).filter(Boolean)
        : dataset.slice(0, 5);

    if (candidates.length === 0) {
        resultsContainer.innerHTML = `<div style="text-align:center;padding:40px;color:#9ca3af;">Kriterlerinize uygun yeni öneri bulunamadı. Kütüphanenizi genişletin veya filtrelerinizi değiştirin.</div>`;
        return;
    }

    // Kapsamlı Akıllı Vektör ve Kelime Skorlaması (Stage 1 Candidate Retrieval)
    const usedRefCounts = {};
    let stage1ScoredCandidates = candidates.map(candidate => {
        const candGenres = candidate.genres || [];
        const candSummary = (candidate.summary || '').toLowerCase();
        const candWhyWatch = (Array.isArray(candidate.why_watch) ? candidate.why_watch.join(' ') : '').toLowerCase();
        const candDuo = (candidate.duo || '').toLowerCase();
        const candFullText = `${candidate.title} ${candSummary} ${candWhyWatch} ${candDuo} ${candGenres.join(' ')}`.toLowerCase();

        // NEGATİF FİLTRELEME CEZASI (-60 Puan)
        let isPenalized = false;
        if (negativeKeywords.length > 0) {
            isPenalized = negativeKeywords.some(neg => candFullText.includes(neg));
        }

        // 1. ARAMA SORGU CÜMLESİ ÖNCELİKLİ SKORLAMASI (FIELD WEIGHTED SCORING)
        let queryMatchScore = 0;
        let queryMatchedWords = [];
        queryTokens.forEach(token => {
            if (candFullText.includes(token)) {
                let weight = 12;
                if ((candidate.title || '').toLowerCase().includes(token)) weight = 25;
                else if (candGenres.some(g => g.toLowerCase().includes(token))) weight = 18;
                queryMatchScore += weight;
                if (!queryMatchedWords.includes(token)) queryMatchedWords.push(token);
            }
        });

        // Bilinen tema başlıklarına ekstra boost (Vis a Vis, OITNB…)
        for (const theme of CONCEPT_THEMES) {
            const titleHit = (theme.titleHints || []).some(h => {
                const hint = String(h || '').toLowerCase();
                const t = (candidate.title || '').toLowerCase();
                if (!hint) return false;
                if (t === hint) return true;
                if (hint.length <= 3) return new RegExp(`(?:^|[\\s\\-:/])${hint}(?:$|[\\s\\-:/])`).test(t);
                return t.includes(hint);
            });
            if (titleHit) {
                const themeInQuery = theme.keywords.some(kw => userQuery.includes(kw))
                    || userQuery.includes(theme.id)
                    || (theme.id === 'hapishane' && (userQuery.includes('hapishane') || userQuery.includes('prison')));
                if (themeInQuery) queryMatchScore += 40;
            }
        }

        // Temalı sorguda kütüphane benzerliği niyeti ezmesin
        const hasThemeQuery = CONCEPT_THEMES.some(th =>
            th.keywords.some(kw => userQuery.includes(kw)) || userQuery.includes(th.id)
            || (th.id === 'hapishane' && (userQuery.includes('hapishane') || userQuery.includes('prison')))
        );

        // Referans çeşitliliği: Oz her kartta kazanmasın
        const picked = pickDiverseReferenceItem(candidate, referencePool, usedRefCounts);
        const bestReferenceItem = picked.ref || referencePool[0];
        const bestReasonText = picked.reason || '';
        const maxRefScore = picked.score || 50;

        let totalScore = (hasThemeQuery ? Math.min(maxRefScore, 55) : maxRefScore) + queryMatchScore;
        if (likedIds.includes(candidate.id)) totalScore += 8;
        if (isPenalized) totalScore -= 60;

        // Gerekçe metni
        let customQueryReason = '';
        if (requestedPlatformKey) {
            const pName = candidate.platform || 'Netflix';
            customQueryReason = `${pName} platformunda erişilebilir olduğu ve "${userQuery}" kriterlerinizle eşleştiği için önerildi`;
        } else if (userQuery && queryMatchedWords.length > 0) {
            customQueryReason = `Aradığınız "${userQuery}" temasına birebir uygun olduğu için önerildi`;
        } else {
            customQueryReason = `<strong>${bestReferenceItem.title}</strong> ile ${bestReasonText} — birlikte izlemeye değer`;
        }

        return {
            candidate,
            score: totalScore,
            refItem: bestReferenceItem,
            reasonText: customQueryReason
        };
    });

    stage1ScoredCandidates.sort((a, b) => b.score - a.score);

    // 🧠 KÜME BAZLI ÇEŞİTLENDİRME (max theme.maxRecs öneri her kümeden)
    // Önce aktif kümeleri tespit et
    const activeClusters = detectLibraryClusters(activeLib, dataset);
    const clusterRecCount = {};  // cluster_id → kaç tane önerildi
    const usedCandidateIds = new Set();
    const finalTopRecommendations = [];

    // PASS 1: Her kümeden sırayla en iyi adayı seç
    for (const scored of stage1ScoredCandidates) {
        if (finalTopRecommendations.length >= 15) break;
        if (usedCandidateIds.has(scored.candidate.id)) continue;

        // Bu adayın hangi kümeye girdiğini bul
        let assignedClusterId = 'generic';
        for (const theme of CONCEPT_THEMES) {
            const candScore = scoreCandidateForCluster(scored.candidate, theme);
            if (candScore >= 3) {
                assignedClusterId = theme.id;
                break;  // en yüksek uyumlu temayı al (CONCEPT_THEMES sıralı)
            }
        }

        // Kümeden max izin verilen sayıyı bul
        const themeObj = CONCEPT_THEMES.find(t => t.id === assignedClusterId);
        const maxForCluster = themeObj ? themeObj.maxRecs : 3;
        const currentCount = clusterRecCount[assignedClusterId] || 0;

        if (currentCount < maxForCluster) {
            clusterRecCount[assignedClusterId] = currentCount + 1;
            usedCandidateIds.add(scored.candidate.id);
            finalTopRecommendations.push(scored);
        }
    }

    // PASS 2: Doldurmak için kalan adayları ekle
    if (finalTopRecommendations.length < 15) {
        for (const scored of stage1ScoredCandidates) {
            if (finalTopRecommendations.length >= 15) break;
            if (!usedCandidateIds.has(scored.candidate.id)) {
                usedCandidateIds.add(scored.candidate.id);
                finalTopRecommendations.push(scored);
            }
        }
    }


    const isUserLoggedIn = (!!CURRENT_USER && CURRENT_USER !== 'Kullanıcı');

    const topBannerHTML = `<div style="background: linear-gradient(135deg, rgba(168, 85, 247, 0.15), rgba(6, 182, 212, 0.15)); border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 12px; padding: 12px 18px; margin-bottom: 22px; font-size: 0.9rem; color: #c084fc; display: flex; align-items: center; justify-content: space-between;">
               <span>✨ <strong>Yapay Zeka Öneri Motoru Aktif</strong>. Kişisel izleme geçmişiniz ve arama niyetiniz analiz ediliyor.</span>
               <span class="badge-purple" style="background: rgba(168, 85, 247, 0.3); border-color: #c084fc; color: #fff;"><i class="fa-solid fa-brain"></i> Yapay Zeka</span>
           </div>`;

    const cardsHTML = finalTopRecommendations.map(({ candidate, score, refItem, reasonText }, idx) => {
        // score 50-120 arasında → %65-%97 aralığına normalize et (gerçekçi değişen skor)
        const normalizedScore = score > 0
            ? Math.round(65 + Math.min(32, ((score - 50) / 70) * 32))
            : 75;
        const displayScore = Math.min(97, Math.max(65, normalizedScore - idx));  // sıra cezası ile azalır


        const seasonsOrDuration = !isMovie 
            ? `${candidate.total_seasons || candidate.seasons_num || 1} Sezon (${candidate.total_episodes || (candidate.season_episodes_map || [10]).reduce((a,b)=>a+b,0)} Bölüm)`
            : `${candidate.ep_duration || 120} dk`;
        
        const isFav = USER_FAVORITES.includes(candidate.id);
        const isLiked = likedIds.includes(candidate.id);

        const badgeHTML = `<span class="badge-purple" style="background: linear-gradient(135deg, rgba(168, 85, 247, 0.25), rgba(6, 182, 212, 0.25)); border: 1px solid #c084fc; color: #e9d5ff;"><i class="fa-solid fa-brain"></i> %${displayScore} Yapay Zeka Uyumu</span>`;

        const reasonBoxHTML = `<div style="background: rgba(168, 85, 247, 0.12); border: 1px solid rgba(168, 85, 247, 0.4); border-radius: 10px; padding: 10px 14px; margin-top: 10px; font-size: 0.85rem; color: #e9d5ff;">
                   <strong>✨ Yapay Zeka Analizi:</strong> 
                   <em>${reasonText || `"${userQuery || (candidate.genres ? candidate.genres[0] : 'Dram')}" kriteriniz ve izleme tercihlerinizle yüksek uyum gösterdiği için seçildi.`}</em>
               </div>`;

        return `
            <div class="media-horizontal-card" style="margin-bottom: 20px;">
                <div class="card-top-row">
                    <div class="card-left-poster">
                        ${posterImgHtml(resolvePosterUrl(candidate), candidate.title)}
                    </div>

                    <div class="card-right-details">
                        <h2 class="card-item-title">${candidate.title}</h2>

                        <div class="card-badges-row">
                            <span class="badge-yellow"><i class="fa-solid fa-star"></i> Puan: ${candidate.rating_num ? candidate.rating_num.toFixed(1) : candidate.rating}</span>
                            <span class="badge-purple"><i class="fa-solid fa-${isMovie ? 'clock' : 'film'}"></i> ${seasonsOrDuration}</span>
                            ${badgeHTML}
                        </div>

                        <div class="card-platform-status" style="margin-top: 8px;">
                            📺 ${formatPlatformLinks(candidate.platform, candidate.title)}
                        </div>

                        ${reasonBoxHTML}

                        <p class="card-summary-text" style="margin-top: 10px; font-size: 0.85rem; color: #d1d5db;">
                            📝 <strong>Özet:</strong> ${candidate.summary || 'Özet bilgisi bulunmuyor.'}
                        </p>

                        <!-- AKSİYON BUTONLARI -->
                        <div style="display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap;">
                            <button onclick="addToLibraryFromExplore('${candidate.id}')" class="primary-gradient-btn" style="padding: 8px 16px; font-size: 0.85rem;">
                                <i class="fa-solid fa-plus"></i> Kitaplığa Ekle
                            </button>
                            <button onclick="toggleFavorite('${candidate.id}')" class="secondary-gradient-btn" style="padding: 8px 16px; font-size: 0.85rem;">
                                <i class="fa-solid fa-heart" style="color: ${isFav ? '#ef4444' : '#fff'};"></i> ${isFav ? 'Favorilerde' : 'Favori'}
                            </button>
                            <button onclick="likeItemPreference('${candidate.id}')" class="secondary-gradient-btn" style="padding: 8px 16px; font-size: 0.85rem; background: ${isLiked ? 'rgba(16, 185, 129, 0.4)' : 'rgba(16, 185, 129, 0.2)'}; border-color: #10b981;">
                                <i class="fa-solid fa-thumbs-up" style="color: #10b981;"></i> ${isLiked ? 'Beğenildi' : 'Beğen'}
                            </button>
                            <button onclick="hideItemPreference('${candidate.id}')" class="secondary-gradient-btn" style="padding: 8px 16px; font-size: 0.85rem; background: rgba(239, 68, 68, 0.15); border-color: #ef4444;">
                                <i class="fa-solid fa-eye-slash" style="color: #ef4444;"></i> Gizle
                            </button>
                            <button onclick="openErrorReportModal('${candidate.id}')" class="secondary-gradient-btn" style="padding: 8px 16px; font-size: 0.85rem; background: rgba(13, 148, 136, 0.18); border-color: #0d9488;">
                                <i class="fa-solid fa-flag" style="color: #2dd4bf;"></i> Hatayı Bildir
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    resultsContainer.innerHTML = topBannerHTML + cardsHTML;

    // Fallback sonuçlarını da kalıcı cache'le (F5'te tekrar hesaplanmasın)
    try {
        const fallbackPayload = {
            visible: finalTopRecommendations.map(({ candidate, score, reasonText }, idx) => {
                const normalizedScore = score > 0
                    ? Math.round(65 + Math.min(32, ((score - 50) / 70) * 32))
                    : 75;
                const displayScore = Math.min(97, Math.max(65, normalizedScore - idx));
                return {
                    id: candidate.id,
                    title: candidate.title,
                    aiMatchScore: displayScore,
                    aiReason: String(reasonText || '').replace(/<\/?strong>/g, ''),
                    poster_url: candidate.poster_url,
                    summary: candidate.summary,
                    genres: Array.isArray(candidate.genres) ? candidate.genres.join(', ') : (candidate.genres || ''),
                    rating: candidate.rating_num || candidate.rating,
                    platform: candidate.platform,
                    channel: 'FALLBACK_LOCAL'
                };
            }),
            overflowQueue: [],
            meta: { engineVersion: 'fallback-local-v2', fromFallback: true }
        };
        if (typeof recCacheKey !== 'undefined') {
            window.BACKEND_REC_CACHE[recCacheKey] = fallbackPayload;
        }
        if (typeof recFingerprint !== 'undefined') {
            savePersistedAIRecCache(recFingerprint, fallbackPayload);
        }
    } catch (e) { /* ignore */ }
}

function forceRefreshAIRecommendations() {
    window.BACKEND_REC_CACHE = {};
    clearPersistedAIRecCache(currentUniverse);
    generateAIRecommendations();
}

function setupAIRecommenderListeners() {
    const submitBtn = document.getElementById('btn-submit-ai');
    const endedCheck = document.getElementById('check-ai-only-ended') || document.getElementById('check-ai-include-ongoing');

    if (submitBtn) {
        submitBtn.addEventListener('click', forceRefreshAIRecommendations);
    }

    if (endedCheck && !endedCheck.dataset.bound) {
        endedCheck.dataset.bound = '1';
        endedCheck.addEventListener('change', () => {
            setAIOnlyEndedPref(!!endedCheck.checked);
            forceRefreshAIRecommendations();
        });
    }
}

// 4. VE 5. FOTOĞRAFTAKİ BİREBİR 'DİZİYİ İNCELE' EKRANI CONTROLÜ
function toggleInspectView() {
    if (!currentRecommendedItem) return;

    const formBody = document.getElementById('assistant-form-body');
    const inspectBody = document.getElementById('inspect-details-body');
    const inspectShowBtn = document.getElementById('btn-inspect-show');

    const isMovie = (currentUniverse === 'MOVIES');

    const inspectTitle = document.getElementById('inspect-title');
    const inspectPoster = document.getElementById('inspect-poster');
    const inspectWhyWatch = document.getElementById('inspect-why-watch');
    const inspectSummary = document.getElementById('inspect-summary');
    const inspectPlatform = document.getElementById('inspect-platform');
    const inspectStatus = document.getElementById('inspect-status');
    const inspectExtraInfo = document.getElementById('inspect-extra-info');

    if (inspectTitle) inspectTitle.innerHTML = `${isMovie ? '🎬' : '🎥'} ${currentRecommendedItem.title}`;
    if (inspectPoster) inspectPoster.src = currentRecommendedItem.poster_url;
    if (inspectSummary) inspectSummary.textContent = `Özet: ${currentRecommendedItem.summary || 'Özet bilgisi bulunmuyor.'}`;
    if (inspectPlatform) inspectPlatform.innerHTML = formatPlatformLinks(currentRecommendedItem.platform, currentRecommendedItem.title);
    if (inspectStatus) inspectStatus.textContent = currentRecommendedItem.status || 'Devam Ediyor';

    if (inspectExtraInfo) {
        if (isMovie) {
            inspectExtraInfo.innerHTML = `<strong>Yayın Yılı / Süre:</strong> ${currentRecommendedItem.year || '2022'} (${currentRecommendedItem.ep_duration || 135} dk)`;
        } else {
            const map = currentRecommendedItem.season_episodes_map || [10];
            const totalEps = currentRecommendedItem.total_episodes || map.reduce((a, b) => a + b, 0);
            inspectExtraInfo.innerHTML = `<strong>Yayın Yılı / Sezon:</strong> ${currentRecommendedItem.year || '2020'} (${currentRecommendedItem.total_seasons || map.length} Sezon ${totalEps} Bölüm)`;
        }
    }

    // 4. Fotoğraftaki Neden İzlemelisin? 3 Maddesi
    if (inspectWhyWatch) {
        if (!isMovie && currentRecommendedItem.why_watch && Array.isArray(currentRecommendedItem.why_watch)) {
            inspectWhyWatch.innerHTML = currentRecommendedItem.why_watch.map(w => `<li style="margin-bottom: 6px;">${w}</li>`).join('');
        } else {
            inspectWhyWatch.innerHTML = `
                <li style="margin-bottom: 6px;">Sıra dışı hikaye kurgusu ve harika oyunculuk performansları.</li>
                <li style="margin-bottom: 6px;">Türü sevenlerin mutlaka deneyimlemesi gereken popüler yapım.</li>
                <li style="margin-bottom: 6px;">Unutulmaz karakter dinamikleri ve sürükleyici atmosfer.</li>
            `;
        }
    }

    if (formBody) formBody.style.display = 'none';
    if (inspectShowBtn) inspectShowBtn.style.display = 'none';
    if (inspectBody) inspectBody.style.display = 'flex';
}

function closeInspectView() {
    const formBody = document.getElementById('assistant-form-body');
    const inspectBody = document.getElementById('inspect-details-body');
    const inspectShowBtn = document.getElementById('btn-inspect-show');

    if (inspectBody) inspectBody.style.display = 'none';
    if (formBody) formBody.style.display = 'block';
    if (inspectShowBtn) inspectShowBtn.style.display = 'block';
}

function getThemeColorForMedia(item, isMovie) {
    const genres = Array.isArray(item.genres) ? item.genres : (item.genres ? [item.genres] : []);
    const gStr = genres.join(' ').toLowerCase();

    if (gStr.includes('aksiyon') || gStr.includes('macera') || gStr.includes('korku')) {
        return { primary: '#ef4444', secondary: '#f97316', bgGlow: 'rgba(239, 68, 68, 0.35)', border: 'rgba(239, 68, 68, 0.6)', tag: '🔥 Aksiyon & Heyecan' };
    }
    if (gStr.includes('bilim') || gStr.includes('fantastik') || gStr.includes('gizem')) {
        return { primary: '#06b6d4', secondary: '#3b82f6', bgGlow: 'rgba(6, 182, 212, 0.35)', border: 'rgba(6, 182, 212, 0.6)', tag: '🚀 Bilim-Kurgu & Evren' };
    }
    if (gStr.includes('komedi') || gStr.includes('animasyon')) {
        return { primary: '#facc15', secondary: '#f59e0b', bgGlow: 'rgba(250, 204, 21, 0.35)', border: 'rgba(250, 204, 21, 0.6)', tag: '💛 Komedi & Eğlence' };
    }
    if (gStr.includes('suç') || gStr.includes('polisiye') || gStr.includes('gerilim')) {
        return { primary: '#10b981', secondary: '#059669', bgGlow: 'rgba(16, 185, 129, 0.35)', border: 'rgba(16, 185, 129, 0.6)', tag: '🔍 Suç & Polisiye' };
    }
    if (gStr.includes('romantik')) {
        return { primary: '#ec4899', secondary: '#f43f5e', bgGlow: 'rgba(236, 72, 153, 0.35)', border: 'rgba(236, 72, 153, 0.6)', tag: '💖 Romantizm' };
    }

    if (isMovie) {
        return { primary: '#f97316', secondary: '#ef4444', bgGlow: 'rgba(249, 115, 22, 0.35)', border: 'rgba(249, 115, 22, 0.6)', tag: '🎬 Sinema Dünyası' };
    } else {
        return { primary: '#a855f7', secondary: '#8b5cf6', bgGlow: 'rgba(168, 85, 247, 0.35)', border: 'rgba(168, 85, 247, 0.6)', tag: '📺 TV Dizisi' };
    }
}

function openItemDetailModal(itemId) {
    const modal = document.getElementById('item-detail-modal');
    if (!modal) return;

    let isMovie = (currentUniverse === 'MOVIES') || String(itemId).startsWith('movie_');
    const moviesPool = (typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES;
    const seriesPool = (typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES;

    let item = moviesPool.find(i => i.id === itemId);
    if (item) {
        isMovie = true;
    } else {
        item = seriesPool.find(i => i.id === itemId);
        if (item) isMovie = false;
    }

    if (!item) {
        const rawNum = String(itemId).replace(/\D/g, '');
        if (rawNum) {
            item = [...moviesPool, ...seriesPool].find(i => String(i.id).replace(/\D/g, '') === rawNum);
        }
    }
    if (!item) return;

    const theme = getThemeColorForMedia(item, isMovie);
    const contentBox = modal.querySelector('.modal-content-box');
    if (contentBox) {
        contentBox.style.borderColor = theme.border;
        contentBox.style.boxShadow = `0 25px 60px rgba(0,0,0,0.95), 0 0 50px ${theme.bgGlow}`;
    }

    const backdropElem = document.getElementById('detail-modal-backdrop');
    const posterElem = document.getElementById('detail-modal-poster');
    const titleElem = document.getElementById('detail-modal-title');
    const sloganElem = document.getElementById('detail-modal-slogan');
    const badgesElem = document.getElementById('detail-modal-badges');
    const summaryElem = document.getElementById('detail-modal-summary');
    const extraGridElem = document.getElementById('detail-modal-extra-grid');
    const actionsElem = document.getElementById('detail-modal-actions');

    const backdropUrl = optimizeTmdbBackdropUrl(item.backdrop_url || item.poster_url || 'https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1280');
    if (backdropElem) {
        backdropElem.referrerPolicy = 'no-referrer';
        backdropElem.src = backdropUrl;
    }
    if (posterElem) {
        posterElem.referrerPolicy = 'no-referrer';
        posterElem.onerror = function () { window.__posterImgError(this); };
        const rawPoster = String(item.poster_url || item.afis_url || '').trim();
        const directPoster = toDirectTmdbUrl(rawPoster, 'w342') || rawPoster;
        posterElem.setAttribute('data-direct', directPoster || '');
        posterElem.setAttribute('data-fallback', TMDB_POSTER_FALLBACK);
        posterElem.removeAttribute('data-proxy');
        posterElem.src = resolvePosterUrl(item);
    }
    if (titleElem) titleElem.textContent = item.title;

    if (sloganElem) {
        if (item.slogan && item.slogan.trim()) {
            sloganElem.innerHTML = `"${escapeHtml(item.slogan)}"`;
            sloganElem.style.display = 'block';
        } else {
            sloganElem.style.display = 'none';
        }
    }

    if (badgesElem) {
        badgesElem.innerHTML = `
            <span class="badge-cyan" style="background: ${theme.bgGlow}; border-color: ${theme.primary}; color: ${theme.primary}; font-weight: 800;">${theme.tag}</span>
            <span class="badge-yellow"><i class="fa-solid fa-star"></i> Puan: ${item.rating_num ? item.rating_num.toFixed(1) : item.rating}</span>
            <span class="badge-purple" style="background: rgba(168, 85, 247, 0.15); border-color: #a855f7; color: #c084fc;"><i class="fa-solid ${isMovie ? 'fa-clock' : 'fa-layer-group'}"></i> ${isMovie ? (item.ep_duration || item.runtime || 120) + ' dk' : (item.seasons || '1 Sezon')}</span>
            ${item.year ? `<span class="badge-cyan" style="background: rgba(14, 165, 233, 0.15); border-color: #0ea5e9; color: #38bdf8;"><i class="fa-solid fa-calendar-days"></i> ${item.year}</span>` : ''}
            ${item.collection ? `<span class="badge-cyan" style="background: rgba(234, 179, 8, 0.15); border-color: #eab308; color: #facc15;">🎬 ${escapeHtml(item.collection)}</span>` : ''}
        `;
    }

    if (summaryElem) {
        summaryElem.textContent = item.summary || 'Özet bilgisi bulunmuyor.';
    }

    if (extraGridElem) {
        let bStr = (item.budget && item.budget > 0) ? `$${(item.budget / 1000000).toFixed(0)}M` : 'Veri Yok';
        let rStr = (item.revenue && item.revenue > 0) ? `$${(item.revenue / 1000000).toFixed(0)}M` : 'Veri Yok';
        let roiStr = (item.budget > 0 && item.revenue > 0) ? `${(item.revenue / item.budget).toFixed(2)}x ROI` : 'Bağımsız / Veri Yok';
        let companiesStr = (Array.isArray(item.companies) && item.companies.length > 0) ? item.companies.join(', ') : 'Bilinmiyor';
        let countriesStr = (Array.isArray(item.countries) && item.countries.length > 0) ? item.countries.join(', ') : 'US';

        extraGridElem.innerHTML = `
            <div><strong>📺 Platform:</strong> ${formatPlatformLinks(item.platform, item.title)}</div>
            <div><strong>📌 Durum:</strong> ${escapeHtml(item.status || 'Devam Ediyor')}</div>
            <div><strong>🌐 Ülke / Dil:</strong> ${escapeHtml(countriesStr)} (${(item.language || 'en').toUpperCase()})</div>
            <div><strong>🏢 Yapım Şirketleri:</strong> ${escapeHtml(companiesStr)}</div>
            ${isMovie ? `
                <div><strong>💰 Yapım Bütçesi:</strong> ${bStr}</div>
                <div><strong>💵 Gişe Hasılatı:</strong> ${rStr}</div>
                <div><strong>🔥 Yatırım Kar Oranı:</strong> <span style="color: #34d399; font-weight: 800;">${roiStr}</span></div>
            ` : `
                <div><strong>⏱️ Bölüm Süresi:</strong> ${item.ep_duration || 45} dk/bölüm</div>
                <div><strong>🔢 Toplam Bölüm:</strong> ${item.total_episodes || 10} Bölüm</div>
            `}
        `;
    }

    if (actionsElem) {
        const hasTrailer = (isValidTrailerUrl(item.trailer_dub_url) || isValidTrailerUrl(item.trailer_sub_url) || isValidTrailerUrl(item.trailer_url));
        actionsElem.innerHTML = `
            ${hasTrailer ? `
                <button onclick="closeItemDetailModal(); openTrailerModal('${item.id}', '${escapeQuotes(item.title)}', 'tr', '${escapeQuotes(item.trailer_dub_url || '')}', '${escapeQuotes(item.trailer_sub_url || '')}', ${!isMovie})" class="primary-gradient-btn" style="padding: 10px 20px; font-size: 0.9rem;">
                    <i class="fa-solid fa-play"></i> Fragman İzle
                </button>
            ` : ''}
            <button onclick="addToLibraryFromExplore('${item.id}')" class="secondary-gradient-btn" style="padding: 10px 18px; font-size: 0.9rem;">
                <i class="fa-solid fa-plus"></i> Kitaplığa Ekle
            </button>
            <button onclick="likeItemPreference('${item.id}')" class="secondary-gradient-btn" style="padding: 10px 18px; font-size: 0.9rem; background: rgba(16, 185, 129, 0.2); border-color: #10b981;">
                <i class="fa-solid fa-thumbs-up" style="color: #10b981;"></i> Beğen
            </button>
            <button onclick="closeItemDetailModal(); openErrorReportModal('${item.id}')" class="secondary-gradient-btn" style="padding: 10px 18px; font-size: 0.9rem; background: rgba(13, 148, 136, 0.18); border-color: #0d9488;">
                <i class="fa-solid fa-flag" style="color: #2dd4bf;"></i> Hatayı Bildir
            </button>
        `;
    }

    modal.style.display = 'flex';
}

function closeItemDetailModal() {
    const modal = document.getElementById('item-detail-modal');
    if (modal) modal.style.display = 'none';
}


/* ==========================================================================
   📌 BAŞLIK: KARŞILAŞTIRMA (VERSUS) SEKMESİ SEÇİM VE ANLAMSAL BENZERLİK MOTORU
   ========================================================================== */
function updateVersusUI() {
    const versusTitle = document.getElementById('versus-panel-title');
    const versusSubtitle = document.getElementById('versus-panel-subtitle');
    const lblVersus1 = document.getElementById('lbl-versus-1');
    const lblVersus2 = document.getElementById('lbl-versus-2');
    const input1 = document.getElementById('input-versus-1');
    const input2 = document.getElementById('input-versus-2');
    const resultWrapper = document.getElementById('versus-result-wrapper');

    const isMovie = (currentUniverse === 'MOVIES');

    if (versusTitle) {
        versusTitle.innerHTML = `<span style="background: #f97316; color: #fff; padding: 2px 8px; border-radius: 6px; font-size: 0.9rem; font-weight: 900; margin-right: 8px;">VS</span> Premium ${isMovie ? 'Film' : 'Dizi'} Karşılaştırma Paneli`;
    }

    if (versusSubtitle) {
        versusSubtitle.textContent = `İki ${isMovie ? 'filmi' : 'diziyi'} seçerek yapay zeka anlamsal uyumunu karşılaştırın.`;
    }

    if (lblVersus1) lblVersus1.textContent = `🎯 1. ${isMovie ? 'Filmi' : 'Diziyi'} Seçiniz`;
    if (lblVersus2) lblVersus2.textContent = `🔥 2. ${isMovie ? 'Filmi' : 'Diziyi'} Seçiniz`;

    if (input1) input1.placeholder = `İlk yapım...`;
    if (input2) input2.placeholder = `İkinci yapım...`;

    // Evren değiştiğinde eski arama ve kart sonuçlarını temizle
    clearVersusInput(1);
    clearVersusInput(2);
    if (resultWrapper) resultWrapper.style.display = 'none';
}

function setupVersusSearchDropdowns() {
    [1, 2].forEach(slot => {
        const input = document.getElementById(`input-versus-${slot}`);
        const dropdown = document.getElementById(`dropdown-versus-${slot}`);
        const clearBtn = document.getElementById(`btn-clear-versus-${slot}`);

        if (!input || !dropdown) return;

        input.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase().trim();
            if (clearBtn) clearBtn.style.display = query ? 'block' : 'none';

            if (!query) {
                dropdown.style.display = 'none';
                return;
            }

            const dataset = (currentUniverse === 'MOVIES') 
                ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
                : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

            const matches = dataset.filter(i => i.title.toLowerCase().includes(query)).slice(0, 8);

            if (matches.length === 0) {
                dropdown.innerHTML = `<div class="dropdown-item" style="color: #9ca3af;">Sonuç bulunamadı</div>`;
            } else {
                dropdown.innerHTML = matches.map(item => `
                    <div class="dropdown-item" onclick="selectVersusItem(${slot}, '${item.id}', '${item.title.replace(/'/g, "\\'")}')">
                        <span>🎬 ${item.title}</span>
                        <span style="font-size: 0.75rem; color: #a855f7;">${item.rating || '8.5/10'}</span>
                    </div>
                `).join('');
            }
            dropdown.style.display = 'block';
        });

        // Tıklandığında tüm listeyi göster
        input.addEventListener('focus', () => {
            const dataset = (currentUniverse === 'MOVIES') 
                ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
                : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

            const query = input.value.toLowerCase().trim();
            const matches = query ? dataset.filter(i => i.title.toLowerCase().includes(query)).slice(0, 8) : dataset.slice(0, 8);

            dropdown.innerHTML = matches.map(item => `
                <div class="dropdown-item" onclick="selectVersusItem(${slot}, '${item.id}', '${item.title.replace(/'/g, "\\'")}')">
                    <span>🎬 ${item.title}</span>
                    <span style="font-size: 0.75rem; color: #a855f7;">${item.rating || '8.5/10'}</span>
                </div>
            `).join('');
            dropdown.style.display = 'block';
        });
    });

    document.addEventListener('click', (e) => {
        [1, 2].forEach(slot => {
            const input = document.getElementById(`input-versus-${slot}`);
            const dropdown = document.getElementById(`dropdown-versus-${slot}`);
            if (input && dropdown && !input.contains(e.target) && !dropdown.contains(e.target)) {
                dropdown.style.display = 'none';
            }
        });
    });
}

function selectVersusItem(slot, itemId, itemTitle) {
    const input = document.getElementById(`input-versus-${slot}`);
    const dropdown = document.getElementById(`dropdown-versus-${slot}`);
    const clearBtn = document.getElementById(`btn-clear-versus-${slot}`);

    if (input) {
        input.value = itemTitle;
        input.setAttribute('data-selected-id', itemId);
    }
    if (clearBtn) clearBtn.style.display = 'block';
    if (dropdown) dropdown.style.display = 'none';
}

function clearVersusInput(slot) {
    const input = document.getElementById(`input-versus-${slot}`);
    const clearBtn = document.getElementById(`btn-clear-versus-${slot}`);
    const dropdown = document.getElementById(`dropdown-versus-${slot}`);

    if (input) {
        input.value = '';
        input.removeAttribute('data-selected-id');
    }
    if (clearBtn) clearBtn.style.display = 'none';
    if (dropdown) dropdown.style.display = 'none';
}

// ANLAMSAL BENZERLİK HESAPLAMA ALGORİTMASI (TÜR, PUAN VE İÇERİK UYUMU)
function calculateSemanticSimilarity(item1, item2) {
    if (!item1 || !item2) return 0;
    let score = 50;

    // Tür Çakışması (+25 Puan)
    if (item1.genres && item2.genres) {
        const sharedGenres = item1.genres.filter(g => item2.genres.includes(g));
        score += sharedGenres.length * 12;
    }

    // Puan Yakınlığı (+15 Puan)
    const r1 = parseFloat(item1.rating) || 8.0;
    const r2 = parseFloat(item2.rating) || 8.0;
    const diff = Math.abs(r1 - r2);
    if (diff < 0.5) score += 15;
    else if (diff < 1.2) score += 8;

    // Platform Yakınlığı (+10 Puan)
    if (item1.platform && item2.platform && item1.platform === item2.platform) {
        score += 10;
    }

    // Sınırlandırma (%65 - %96 Arası Gerçekçi Skor)
    return Math.min(96, Math.max(65, Math.floor(score)));
}

// BİREBİR KARŞILAŞTIRMA ÇALIŞTIRMA VE SÜTUNLU KART RENDERİ (4. FOTOĞRAF BİREBİR)
function runVersusComparison() {
    const input1 = document.getElementById('input-versus-1');
    const input2 = document.getElementById('input-versus-2');

    const val1 = input1 ? input1.value.trim() : '';
    const val2 = input2 ? input2.value.trim() : '';

    if (!val1 || !val2) {
        showToast('⚠️ Lütfen karşılaştırmak için 2 adet yapım seçiniz!', 2000);
        return;
    }

    const dataset = (currentUniverse === 'MOVIES') 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const id1 = input1.getAttribute('data-selected-id');
    const id2 = input2.getAttribute('data-selected-id');

    const item1 = dataset.find(i => i.id === id1 || i.title.toLowerCase() === val1.toLowerCase()) || dataset[0];
    const item2 = dataset.find(i => i.id === id2 || i.title.toLowerCase() === val2.toLowerCase()) || dataset[1] || dataset[0];

    if (item1.id === item2.id || item1.title.toLowerCase() === item2.title.toLowerCase()) {
        showToast('⚠️ Bir diziyi / filmi kendisiyle kıyaslayamazsınız! Lütfen 2 farklı yapım seçiniz.', 2800);
        return;
    }

    const isMovie = (currentUniverse === 'MOVIES');
    const score = calculateSemanticSimilarity(item1, item2);

    // --- YARDIMCI FONKSİYONLAR ---
    const getRating = (item) => parseFloat((item.rating || '0').replace(/[^\d.]/g,'')) || 0;
    const getVotes  = (item) => item.votes_num || parseInt((item.votes || '0').replace(/[^\d]/g,'')) || 0;
    const getEps    = (item) => isMovie ? 1 : (item.total_episodes || (item.season_episodes_map||[10]).reduce((a,b)=>a+b,0));
    const getDur    = (item) => item.ep_duration || (isMovie ? 120 : 45);
    const getTotalMins = (item) => getEps(item) * getDur(item);
    const getSeasons = (item) => isMovie ? 1 : (item.total_seasons || item.seasons_num || 1);
    const getGenres  = (item) => Array.isArray(item.genres) ? item.genres : [];

    const r1 = getRating(item1), r2 = getRating(item2);
    const v1 = getVotes(item1),  v2 = getVotes(item2);
    const t1 = getTotalMins(item1), t2 = getTotalMins(item2);
    const s1 = getSeasons(item1), s2 = getSeasons(item2);
    const g1 = getGenres(item1), g2 = getGenres(item2);

    const categories = [
        { label: '⭐ IMDb Puanı',      v1: r1,  v2: r2,  fmt: (v)=>`${v.toFixed(1)}/10`, higherWins: true  },
        { label: '🗳️ Oy Sayısı',       v1: v1,  v2: v2,  fmt: (v)=>v>=1000?`${(v/1000).toFixed(0)}K`:`${v}`, higherWins: true },
        { label: '⏱️ Bölüm Süresi',    v1: getDur(item1), v2: getDur(item2), fmt:(v)=>`${v} dk`, higherWins: false },
        { label: `📺 ${isMovie?'Film':'Sezon'} Sayısı`, v1: s1, v2: s2, fmt:(v)=>`${v}`, higherWins: false },
        { label: '🕰️ Toplam Süre',     v1: t1,  v2: t2,  fmt:(v)=>`${Math.round(v/60)} saat`, higherWins: false },
    ];

    let roiHtml = '';
    if (isMovie) {
        const b1 = item1.budget || 0, r1_rev = item1.revenue || 0;
        const b2 = item2.budget || 0, r2_rev = item2.revenue || 0;

        const roi1 = (b1 > 0 && r1_rev > 0) ? (r1_rev / b1).toFixed(2) : null;
        const roi2 = (b2 > 0 && r2_rev > 0) ? (r2_rev / b2).toFixed(2) : null;

        const b1Str = b1 > 0 ? `$${(b1/1000000).toFixed(0)}M` : 'Veri Yok';
        const r1Str = r1_rev > 0 ? `$${(r1_rev/1000000).toFixed(0)}M` : 'Veri Yok';
        const roi1Str = roi1 ? `${roi1}x Kat (ROI)` : 'Bağımsız / Veri Yok';

        const b2Str = b2 > 0 ? `$${(b2/1000000).toFixed(0)}M` : 'Veri Yok';
        const r2Str = r2_rev > 0 ? `$${(r2_rev/1000000).toFixed(0)}M` : 'Veri Yok';
        const roi2Str = roi2 ? `${roi2}x Kat (ROI)` : 'Bağımsız / Veri Yok';

        roiHtml = `
            <div class="versus-roi-bar-wrapper">
                <div style="font-weight: 800; color: #facc15; font-size: 0.9rem; margin-bottom: 8px; text-align: center;">
                    💰 Gişe & Finansal ROI (Yatırım Kar Oranı) Düellosu
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; text-align: center;">
                    <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 8px;">
                        <strong style="color: #fff;">${escapeHtml(item1.title)}</strong>
                        <div style="font-size: 0.8rem; color: #9ca3af; margin-top: 4px;">Bütçe: ${b1Str} | Hasılat: ${r1Str}</div>
                        <div style="font-weight: 800; color: #34d399; font-size: 0.88rem; margin-top: 4px;">🔥 ROI: ${roi1Str}</div>
                    </div>
                    <div style="background: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.3); border-radius: 8px; padding: 8px;">
                        <strong style="color: #fff;">${escapeHtml(item2.title)}</strong>
                        <div style="font-size: 0.8rem; color: #9ca3af; margin-top: 4px;">Bütçe: ${b2Str} | Hasılat: ${r2Str}</div>
                        <div style="font-weight: 800; color: #fb923c; font-size: 0.88rem; margin-top: 4px;">🔥 ROI: ${roi2Str}</div>
                    </div>
                </div>
            </div>
        `;
    }

    let wins1 = 0, wins2 = 0;
    const duelRows = categories.map(cat => {
        let w1=false, w2=false, tie=false;
        if (cat.v1 === cat.v2) { tie=true; wins1+=0.5; wins2+=0.5; }
        else if (cat.higherWins ? cat.v1>cat.v2 : cat.v1<cat.v2) { w1=true; wins1++; }
        else { w2=true; wins2++; }

        const crown = '👑';
        return `
        <div style="display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:10px; 
                    padding:10px 14px; background:rgba(255,255,255,0.04); border-radius:10px; border:1px solid rgba(255,255,255,0.07);">
            <div style="text-align:right; font-weight:${w1?'800':'500'}; color:${w1?'#a78bfa':tie?'#facc15':'#9ca3af'}; font-size:0.92rem;">
                ${w1?crown:''} ${cat.fmt(cat.v1)}
            </div>
            <div style="text-align:center; font-size:0.75rem; color:#6b7280; font-weight:700; min-width:110px;">${cat.label}</div>
            <div style="text-align:left; font-weight:${w2?'800':'500'}; color:${w2?'#f97316':tie?'#facc15':'#9ca3af'}; font-size:0.92rem;">
                ${cat.fmt(cat.v2)} ${w2?crown:''}
            </div>
        </div>`;
    }).join('');

    // --- KAZANAN ROZET ---
    let winnerHtml = '';
    if (wins1 > wins2) {
        winnerHtml = `<div style="text-align:center; padding:16px; background:linear-gradient(135deg,rgba(167,139,250,0.2),rgba(139,92,246,0.1)); border:2px solid #a78bfa; border-radius:14px; margin-bottom:20px;">
            <div style="font-size:1.8rem; margin-bottom:4px;">🏆</div>
            <div style="font-weight:900; color:#a78bfa; font-size:1.1rem;">${item1.title} KAZANDI</div>
            <div style="font-size:0.82rem; color:#9ca3af; margin-top:4px;">${wins1} - ${wins2} kategori</div>
        </div>`;
    } else if (wins2 > wins1) {
        winnerHtml = `<div style="text-align:center; padding:16px; background:linear-gradient(135deg,rgba(249,115,22,0.2),rgba(234,88,12,0.1)); border:2px solid #f97316; border-radius:14px; margin-bottom:20px;">
            <div style="font-size:1.8rem; margin-bottom:4px;">🏆</div>
            <div style="font-weight:900; color:#f97316; font-size:1.1rem;">${item2.title} KAZANDI</div>
            <div style="font-size:0.82rem; color:#9ca3af; margin-top:4px;">${wins2} - ${wins1} kategori</div>
        </div>`;
    } else {
        winnerHtml = `<div style="text-align:center; padding:16px; background:rgba(250,204,21,0.1); border:2px solid #facc15; border-radius:14px; margin-bottom:20px;">
            <div style="font-size:1.8rem; margin-bottom:4px;">🤝</div>
            <div style="font-weight:900; color:#facc15; font-size:1.1rem;">BERABERE!</div>
            <div style="font-size:0.82rem; color:#9ca3af; margin-top:4px;">${wins1} - ${wins2} kategori</div>
        </div>`;
    }

    // --- COSINE → SÖZEL ---
    let simText = '', simColor = '';
    if (score >= 90)      { simText = 'Neredeyse aynı his — birini sevdiysen diğeri kesin seni yakalar.'; simColor='#10b981'; }
    else if (score >= 75) { simText = 'Çok benzer — türe ve havaya yakın, güvenli seçim.'; simColor='#22d3ee'; }
    else if (score >= 55) { simText = 'Farklı ama aynı türde — değiştirici bir deneyim yaşarsın.'; simColor='#f59e0b'; }
    else                  { simText = 'Bambaşka iki dünya — ruh haline göre seçim yap.'; simColor='#ef4444'; }

    // --- HIZLANDIRILMIŞ SÜRE ---
    const fmt = (m) => { const h=Math.floor(m/60); const mn=m%60; return h>0?`${h}s ${mn}dk`:`${mn}dk`; };
    const speedHtml = `
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:20px;">
            <div style="background:rgba(167,139,250,0.1); border:1px solid rgba(167,139,250,0.3); border-radius:12px; padding:14px; text-align:center;">
                <div style="font-size:1.5rem; margin-bottom:4px;">⏳</div>
                <div style="font-weight:800; color:#a78bfa; font-size:1.1rem;">${fmt(t1)}</div>
                <div style="font-size:0.78rem; color:#9ca3af; margin-top:2px;">${item1.title}</div>
            </div>
            <div style="background:rgba(249,115,22,0.1); border:1px solid rgba(249,115,22,0.3); border-radius:12px; padding:14px; text-align:center;">
                <div style="font-size:1.5rem; margin-bottom:4px;">⏳</div>
                <div style="font-weight:800; color:#f97316; font-size:1.1rem;">${fmt(t2)}</div>
                <div style="font-size:0.78rem; color:#9ca3af; margin-top:2px;">${item2.title}</div>
            </div>
        </div>
        <div style="font-size:0.85rem; color:#d1d5db; text-align:center; padding:10px; background:rgba(255,255,255,0.04); border-radius:8px; margin-bottom:20px;">
            ${t1 < t2
                ? `⚡ <strong style="color:#a78bfa">${item1.title}</strong> ${fmt(t2-t1)} daha kısa — acelen varsa bu tercih.`
                : t2 < t1
                ? `⚡ <strong style="color:#f97316">${item2.title}</strong> ${fmt(t1-t2)} daha kısa — acelen varsa bu tercih.`
                : `🤝 İkisi de aynı toplam süre!`
            }
        </div>`;

    // --- YAPAY ZEKA YORUMU ---
    const genreOverlap = g1.filter(g => g2.includes(g));
    const uniqueG1 = g1.filter(g => !g2.includes(g));
    const uniqueG2 = g2.filter(g => !g1.includes(g));

    let aiLines = [];
    // Puan karşılaştırması
    if (Math.abs(r1-r2) < 0.3) aiLines.push(`📊 Her iki yapım da çok yakın puanlara sahip — izleme kalitesi açısından fark gözetmeksizin seçebilirsin.`);
    else if (r1>r2) aiLines.push(`📊 <strong>${item1.title}</strong> ${(r1-r2).toFixed(1)} puan öndede — IMDb kitlesine göre daha başarılı bir yapım.`);
    else aiLines.push(`📊 <strong>${item2.title}</strong> ${(r2-r1).toFixed(1)} puan önde — IMDb kitlesine göre daha başarılı bir yapım.`);

    // Süre yorumu
    if (t1 < 200 && t2 > 800) aiLines.push(`⚡ Vaktin kısıtlıysa <strong>${item1.title}</strong> çok daha hızlı biter.`);
    else if (t2 < 200 && t1 > 800) aiLines.push(`⚡ Vaktin kısıtlıysa <strong>${item2.title}</strong> çok daha hızlı biter.`);

    // Tür yorumu
    if (genreOverlap.length > 0) aiLines.push(`🎭 İkisi de <strong>${genreOverlap.slice(0,2).join(' ve ')}</strong> türünde — birini sevdiysen diğeri de seni yakalayacak.`);
    if (uniqueG1.length > 0 && uniqueG2.length > 0) aiLines.push(`🔀 <strong>${item1.title}</strong> ${uniqueG1[0]} ağırlıklıyken, <strong>${item2.title}</strong> daha çok ${uniqueG2[0]} hissettiriyor.`);

    // Sezon yorumu
    if (!isMovie) {
        if (s1 <= 2 && s2 > 5) aiLines.push(`📺 <strong>${item1.title}</strong> daha kompakt — uzun bağlılık istemiyorsan bu seçim.`);
        else if (s2 <= 2 && s1 > 5) aiLines.push(`📺 <strong>${item2.title}</strong> daha kompakt — uzun bağlılık istemiyorsan bu seçim.`);
    }

    // Final öneri
    if (wins1 > wins2) aiLines.push(`✅ Genel dengede <strong style="color:#a78bfa">${item1.title}</strong> biraz daha öne çıkıyor — ama ${item2.title} de güçlü bir alternatif.`);
    else if (wins2 > wins1) aiLines.push(`✅ Genel dengede <strong style="color:#f97316">${item2.title}</strong> biraz daha öne çıkıyor — ama ${item1.title} de güçlü bir alternatif.`);
    else aiLines.push(`✅ İkisi de birbirinden güçlü. Hangisini ilk sırada görürsen onu başlat — pişman olmazsın.`);

    const aiHtml = aiLines.map(l=>`<div style="padding:9px 12px; background:rgba(255,255,255,0.03); border-left:3px solid rgba(168,85,247,0.5); border-radius:0 8px 8px 0; font-size:0.86rem; color:#d1d5db; line-height:1.5;">${l}</div>`).join('');

    // --- RADAR CHART ---
    const radarCanvasId = `versus-radar-${Date.now()}`;
    const normalize = (val, min, max) => max===min ? 50 : Math.round(((val-min)/(max-min))*100);
    const radarData1 = [
        normalize(r1, 1, 10),
        normalize(Math.min(v1,500000), 0, 500000),
        normalize(100-Math.min(getDur(item1),180), 0, 100), // kısa = iyi
        normalize(Math.min(s1,10), 0, 10),
        normalize(g1.length, 0, 10),
    ];
    const radarData2 = [
        normalize(r2, 1, 10),
        normalize(Math.min(v2,500000), 0, 500000),
        normalize(100-Math.min(getDur(item2),180), 0, 100),
        normalize(Math.min(s2,10), 0, 10),
        normalize(g2.length, 0, 10),
    ];

    // --- ANA SONUÇ HTML ---
    const resultWrapper = document.getElementById('versus-result-wrapper');
    const scoreVal = document.getElementById('versus-score-val');
    if (scoreVal) scoreVal.textContent = `%${score}`;

    if (!resultWrapper) return;

    resultWrapper.innerHTML = `
    <div style="width:100%; display:flex; flex-direction:column; gap:20px;">

        <!-- POSTER KARŞILAŞTIRMA -->
        <div style="display:grid; grid-template-columns:1fr 60px 1fr; gap:10px; align-items:start;">
            <!-- Item 1 -->
            <div style="background:rgba(167,139,250,0.08); border:2px solid rgba(167,139,250,0.3); border-radius:16px; padding:16px; text-align:center;">
                <img src="${resolvePosterUrl(item1)}" style="width:100%; max-width:180px; height:250px; object-fit:cover; border-radius:10px; box-shadow:0 8px 25px rgba(0,0,0,0.5); margin-bottom:12px;" onerror="this.src='https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500'">
                <div style="font-weight:800; color:#fff; font-size:1rem;">${item1.title}</div>
                <div style="font-size:0.78rem; color:#a78bfa; margin-top:4px;">${g1.slice(0,2).join(' · ') || ''}</div>
            </div>
            <!-- VS -->
            <div style="display:flex; align-items:center; justify-content:center; height:100%;">
                <div style="font-size:1.6rem; font-weight:900; color:#facc15; text-shadow:0 0 20px rgba(250,204,21,0.6);">VS</div>
            </div>
            <!-- Item 2 -->
            <div style="background:rgba(249,115,22,0.08); border:2px solid rgba(249,115,22,0.3); border-radius:16px; padding:16px; text-align:center;">
                <img src="${resolvePosterUrl(item2)}" style="width:100%; max-width:180px; height:250px; object-fit:cover; border-radius:10px; box-shadow:0 8px 25px rgba(0,0,0,0.5); margin-bottom:12px;" onerror="this.src='https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500'">
                <div style="font-weight:800; color:#fff; font-size:1rem;">${item2.title}</div>
                <div style="font-size:0.78rem; color:#f97316; margin-top:4px;">${g2.slice(0,2).join(' · ') || ''}</div>
            </div>
        </div>

        <!-- KAZANAN ROZET -->
        ${winnerHtml}

        <!-- DÜELLO TABLOSU -->
        <div>
            <h3 style="font-size:0.95rem; font-weight:800; color:#fff; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                🥊 Kategori Düellosu
            </h3>
            <div style="display:grid; gap:8px;">
                <!-- Başlık satırı -->
                <div style="display:grid; grid-template-columns:1fr auto 1fr; gap:10px; padding:6px 14px;">
                    <div style="text-align:right; font-size:0.8rem; font-weight:800; color:#a78bfa;">${item1.title}</div>
                    <div style="min-width:110px;"></div>
                    <div style="text-align:left; font-size:0.8rem; font-weight:800; color:#f97316;">${item2.title}</div>
                </div>
                ${duelRows}
            </div>
        </div>

        <!-- HIZLANDIRILMIŞ SÜRE -->
        <div>
            <h3 style="font-size:0.95rem; font-weight:800; color:#fff; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                ⚡ Hız Skoru — Kaç Saatin Gider?
            </h3>
            ${speedHtml}
        </div>

        <!-- RADAR CHART -->
        <div>
            <h3 style="font-size:0.95rem; font-weight:800; color:#fff; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                📊 Radar Analizi
            </h3>
            <div style="background:rgba(18,15,38,0.8); border:1px solid var(--border-card); border-radius:14px; padding:16px; display:flex; justify-content:center;">
                <canvas id="${radarCanvasId}" style="max-width:340px; max-height:280px;"></canvas>
            </div>
            <div style="display:flex; justify-content:center; gap:24px; margin-top:10px; font-size:0.8rem; font-weight:700;">
                <span style="color:#a78bfa;">■ ${item1.title}</span>
                <span style="color:#f97316;">■ ${item2.title}</span>
            </div>
        </div>

        <!-- UYUM SKORU -->
        <div style="background:rgba(18,15,38,0.8); border:1px solid var(--border-card); border-radius:14px; padding:18px;">
            <h3 style="font-size:0.95rem; font-weight:800; color:#fff; margin-bottom:10px; display:flex; align-items:center; gap:8px;">
                🔗 İçerik Uyum Skoru: <span style="color:${simColor}; margin-left:4px;">%${score}</span>
            </h3>
            <div style="font-size:0.88rem; color:${simColor}; font-weight:700; margin-bottom:8px;">${simText}</div>
            <div style="background:rgba(255,255,255,0.08); height:8px; border-radius:4px; overflow:hidden;">
                <div style="background:linear-gradient(90deg,${simColor},${simColor}88); width:${score}%; height:100%; border-radius:4px; transition:width 1s;"></div>
            </div>
        </div>

        <!-- YAPAY ZEKA YORUMU -->
        <div>
            <h3 style="font-size:0.95rem; font-weight:800; color:#fff; margin-bottom:12px; display:flex; align-items:center; gap:8px;">
                🤖 Yapay Zeka Kıyaslaması
            </h3>
            <div style="display:flex; flex-direction:column; gap:8px;">
                ${aiHtml}
            </div>
        </div>

        <!-- ÖZET AKORDEONLAR -->
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:14px;">
            <div style="background:rgba(167,139,250,0.06); border:1px solid rgba(167,139,250,0.2); border-radius:12px; padding:14px;">
                <div style="font-weight:800; color:#a78bfa; font-size:0.88rem; margin-bottom:8px;">📝 ${item1.title} — Özet</div>
                <div style="font-size:0.82rem; color:#d1d5db; line-height:1.5;">${item1.summary || 'Özet bulunmuyor.'}</div>
            </div>
            <div style="background:rgba(249,115,22,0.06); border:1px solid rgba(249,115,22,0.2); border-radius:12px; padding:14px;">
                <div style="font-weight:800; color:#f97316; font-size:0.88rem; margin-bottom:8px;">📝 ${item2.title} — Özet</div>
                <div style="font-size:0.82rem; color:#d1d5db; line-height:1.5;">${item2.summary || 'Özet bulunmuyor.'}</div>
            </div>
        </div>

    </div>`;

    resultWrapper.style.display = 'block';
    resultWrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    // Radar Chart çizimi (Chart.js)
    setTimeout(() => {
        const ctx = document.getElementById(radarCanvasId);
        if (!ctx || typeof Chart === 'undefined') return;
        new Chart(ctx, {
            type: 'radar',
            data: {
                labels: ['Puan', 'Popülerlik', 'Kısalık', 'Sezon', 'Tür Zen.'],
                datasets: [
                    {
                        label: item1.title,
                        data: radarData1,
                        backgroundColor: 'rgba(167,139,250,0.25)',
                        borderColor: '#a78bfa',
                        pointBackgroundColor: '#a78bfa',
                        borderWidth: 2,
                    },
                    {
                        label: item2.title,
                        data: radarData2,
                        backgroundColor: 'rgba(249,115,22,0.20)',
                        borderColor: '#f97316',
                        pointBackgroundColor: '#f97316',
                        borderWidth: 2,
                    }
                ]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    r: {
                        min: 0, max: 100,
                        ticks: { display: false },
                        grid: { color: 'rgba(255,255,255,0.1)' },
                        angleLines: { color: 'rgba(255,255,255,0.1)' },
                        pointLabels: { color: '#9ca3af', font: { size: 11, weight: '700' } }
                    }
                }
            }
        });
    }, 100);
}


/* ==========================================================================
   📌 BAŞLIK: SOSYAL KATMAN VE ORTAK ZEVK FÜZYONU MOTORU
   ========================================================================== */
const REGISTERED_USERS = ['ahmet_matrix', 'zeynep_dizi', 'can_cinephile', 'neo_matrix', 'selin_cinema'];

function isLocalRegisteredUsername(username) {
    const needle = String(username || '').trim().toLowerCase();
    if (!needle) return false;
    if (REGISTERED_USERS.some(u => String(u).toLowerCase() === needle)) return true;
    if (typeof REGISTERED_ACCOUNTS !== 'undefined' && Array.isArray(REGISTERED_ACCOUNTS)) {
        if (REGISTERED_ACCOUNTS.some(a => String(a.username || '').toLowerCase() === needle)) return true;
    }
    return false;
}

async function lookupRegisteredUsername(username) {
    const needle = String(username || '').trim();
    if (!needle) return { exists: false, username: '' };

    if (typeof loadRegisteredAccounts === 'function') loadRegisteredAccounts();

    let apiReachable = false;

    try {
        const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
        const res = await fetch(`${baseUrl}/api/auth/user-exists?username=${encodeURIComponent(needle)}`);
        apiReachable = true;
        if (res.ok) {
            const data = await res.json();
            if (data && data.exists) {
                return { exists: true, username: data.username || needle, source: 'server' };
            }
        } else if (res.status === 404) {
            apiReachable = false;
        }
    } catch (e) {
        apiReachable = false;
    }

    if (isLocalRegisteredUsername(needle)) {
        return { exists: true, username: needle, source: 'local' };
    }

    return { exists: false, username: needle, apiReachable };
}

let USER_FRIENDS = [];
let PENDING_REQUESTS = []; // { id, from } | string (legacy)
let PENDING_FUSION_REQUESTS = [];
let OUTGOING_FUSION_REQUESTS = [];
let COMPLETED_FUSION_INVITES = [];
let ACTIVE_FUSION_RESPOND_ID = null;

function getSocialApiBase() {
    return (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
}

async function socialApiFetch(path, options = {}) {
    await ensureSignedAuthToken();
    const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    const signed = getSignedAuthToken();
    if (signed) headers['Authorization'] = `Bearer ${signed}`;
    const res = await fetch(`${getSocialApiBase()}${path}`, {
        ...options,
        headers
    });
    let data = null;
    try { data = await res.json(); } catch (e) { data = null; }
    return { ok: res.ok, status: res.status, data };
}

function normalizePendingFriendList(list) {
    if (!Array.isArray(list)) return [];
    return list.map(item => {
        if (item && typeof item === 'object') {
            return { id: item.id || item.requestId || 0, from: item.from || item.gonderen || item.username || '' };
        }
        return { id: 0, from: String(item || '') };
    }).filter(x => x.from);
}

function getFusionDataset() {
    return (currentUniverse === 'MOVIES')
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);
}

/** Füzyon seçimleri yalnızca kullanıcının kitaplığından */
function getFusionLibraryItems(universeOverride) {
    const uni = String(universeOverride || currentUniverse || 'MOVIES').toUpperCase();
    const isMovie = uni === 'MOVIES';
    const lib = isMovie
        ? (typeof USER_MOVIES_LIBRARY !== 'undefined' ? USER_MOVIES_LIBRARY : [])
        : (typeof USER_SERIES_LIBRARY !== 'undefined' ? USER_SERIES_LIBRARY : []);
    const catalog = isMovie
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    return (lib || []).map(item => {
        if (!item || !item.id) return null;
        const hit = (catalog || []).find(c => c && String(c.id) === String(item.id));
        return {
            id: item.id,
            title: item.title || (hit && hit.title) || item.id
        };
    }).filter(Boolean);
}

function fusionMediaWord(universeOverride) {
    const uni = String(universeOverride || currentUniverse || 'MOVIES').toUpperCase();
    return uni === 'SERIES' ? 'dizi' : 'film';
}

function resolveFusionTitleById(itemId, universeOverride) {
    const uni = String(universeOverride || currentUniverse || 'MOVIES').toUpperCase();
    const catalog = uni === 'MOVIES'
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);
    const lib = getFusionLibraryItems(uni);
    const fromLib = lib.find(i => String(i.id) === String(itemId));
    if (fromLib) return fromLib.title;
    const hit = (catalog || []).find(c => c && String(c.id) === String(itemId));
    return (hit && hit.title) || String(itemId);
}

function readFusionSlotValues(selector) {
    return Array.from(document.querySelectorAll(selector)).map(s => s.value).filter(Boolean);
}

/**
 * Kitaplıktan 5 seçim slotu (+ arama ile filtre).
 * @returns {boolean} kitaplıkta en az 5 yapım varsa true
 */
function buildFusionSelectSlots(containerId, selectClass, selectedIds, universeOverride) {
    const container = document.getElementById(containerId);
    if (!container) return false;

    const lib = getFusionLibraryItems(universeOverride);
    const mediaWord = fusionMediaWord(universeOverride);

    if (lib.length < 5) {
        container.innerHTML = `
            <div style="color:#fbbf24;font-size:0.9rem;line-height:1.45;padding:4px 0;">
                Kitaplığınızda yeterli ${mediaWord} yok. Ortak zevk füzyonu için kitaplığınıza en az <strong>5 ${mediaWord}</strong> eklemeniz gerekmektedir.
            </div>`;
        return false;
    }

    const preferred = Array.isArray(selectedIds) ? selectedIds : [];
    container.innerHTML = [0, 1, 2, 3, 4].map(idx => {
        const pref = preferred[idx] || '';
        return `
            <select class="custom-select ${selectClass} fusion-pick-select" style="font-size: 0.85rem; padding: 8px;">
                <option value="">— ${idx + 1}. ${mediaWord} seçin —</option>
                ${lib.map(item => {
                    const sel = String(item.id) === String(pref) ? 'selected' : '';
                    const title = item.title || item.id;
                    return `<option value="${escapeHtml(String(item.id))}" data-title="${escapeHtml(String(title).toLowerCase())}" ${sel}>🎬 ${escapeHtml(title)}</option>`;
                }).join('')}
            </select>
        `;
    }).join('');
    return true;
}

/** Kitaplık seçim listelerinde arama + öneri dropdown (a | respond) */
function filterFusionPickerOptions(which) {
    const inputId = which === 'respond' ? 'fusion-lib-search-respond' : 'fusion-lib-search-a';
    const suggestId = which === 'respond' ? 'fusion-lib-suggest-respond' : 'fusion-lib-suggest-a';
    const selectClass = which === 'respond' ? 'fusion-select-respond' : 'fusion-select-a';
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(suggestId);
    const q = String(input?.value || '').toLowerCase().trim();

    const lib = getFusionLibraryItems(which === 'respond'
        ? ((PENDING_FUSION_REQUESTS || []).find(r => Number(r.id) === Number(ACTIVE_FUSION_RESPOND_ID)) || {}).universe
        : undefined);

    document.querySelectorAll(`select.${selectClass}`).forEach(sel => {
        Array.from(sel.options).forEach((opt, i) => {
            if (i === 0) { opt.hidden = false; return; }
            const title = (opt.getAttribute('data-title') || opt.textContent || '').toLowerCase();
            opt.hidden = q ? !title.includes(q) : false;
        });
    });

    if (!dropdown) return;
    if (!q) {
        dropdown.style.display = 'none';
        dropdown.innerHTML = '';
        return;
    }

    const selectedIds = new Set(readFusionSlotValues(`select.${selectClass}`).map(String));
    const matches = (lib || []).filter(item => {
        const title = String(item.title || '').toLowerCase();
        return title.includes(q) && !selectedIds.has(String(item.id));
    }).slice(0, 8);

    if (!matches.length) {
        dropdown.innerHTML = `<div class="dropdown-item" style="color:#9ca3af;">"${escapeHtml(q)}" için kitaplıkta eşleşme yok</div>`;
    } else {
        dropdown.innerHTML = matches.map(item => {
            const safeTitle = String(item.title || '').replace(/\\/g, '\\\\').replace(/'/g, "\\'");
            return `
                <div class="dropdown-item" onclick="pickFusionLibrarySuggestion('${which}', '${escapeQuotes(String(item.id))}', '${safeTitle}')">
                    <span>🎬 ${escapeHtml(item.title || item.id)}</span>
                    <span style="font-size:0.75rem;color:#ec4899;">Seç</span>
                </div>`;
        }).join('');
    }
    dropdown.style.display = 'block';
}

function pickFusionLibrarySuggestion(which, itemId, itemTitle) {
    const selectClass = which === 'respond' ? 'fusion-select-respond' : 'fusion-select-a';
    const inputId = which === 'respond' ? 'fusion-lib-search-respond' : 'fusion-lib-search-a';
    const suggestId = which === 'respond' ? 'fusion-lib-suggest-respond' : 'fusion-lib-suggest-a';
    const selects = Array.from(document.querySelectorAll(`select.${selectClass}`));
    const already = selects.some(sel => String(sel.value) === String(itemId));
    if (already) {
        showToast('⚠️ Bu yapım zaten seçili.', 1600);
        return;
    }
    const empty = selects.find(sel => !sel.value);
    const target = empty || selects[0];
    if (target) {
        const opt = Array.from(target.options).find(o => String(o.value) === String(itemId));
        if (opt) opt.hidden = false;
        target.value = String(itemId);
        target.dispatchEvent(new Event('change', { bubbles: true }));
    }
    const input = document.getElementById(inputId);
    const dropdown = document.getElementById(suggestId);
    if (input) input.value = '';
    if (dropdown) {
        dropdown.style.display = 'none';
        dropdown.innerHTML = '';
    }
    filterFusionPickerOptions(which);
    if (itemTitle) showToast(`✅ ${itemTitle} seçildi`, 1400);
}

document.addEventListener('click', (e) => {
    ['a', 'respond'].forEach(which => {
        const inputId = which === 'respond' ? 'fusion-lib-search-respond' : 'fusion-lib-search-a';
        const suggestId = which === 'respond' ? 'fusion-lib-suggest-respond' : 'fusion-lib-suggest-a';
        const input = document.getElementById(inputId);
        const dropdown = document.getElementById(suggestId);
        if (!input || !dropdown) return;
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
});

function getActiveLibraryIdsForFusion() {
    const lib = (typeof getActiveLibrary === 'function' ? getActiveLibrary() : []) || [];
    return lib.map(i => i && i.id).filter(Boolean);
}

function fusionResultsPersistKey(inviteId) {
    const user = (CURRENT_USER && CURRENT_USER !== 'Kullanıcı') ? CURRENT_USER.toLowerCase() : 'guest';
    return `FUSION_RESULTS_v1_${user}_${inviteId}`;
}

function saveFusionResultsLocal(inviteId, payload) {
    try {
        localStorage.setItem(fusionResultsPersistKey(inviteId), JSON.stringify({
            savedAt: Date.now(),
            ...payload
        }));
    } catch (e) { /* ignore */ }
}

function loadFusionResultsLocal(inviteId) {
    try {
        const raw = localStorage.getItem(fusionResultsPersistKey(inviteId));
        if (!raw) return null;
        return JSON.parse(raw);
    } catch (e) {
        return null;
    }
}

let FORCE_SHOW_FUSION_PICKS = false;

function hideFusionPicksSection() {
    const section = document.getElementById('fusion-picks-section');
    if (section) section.style.display = 'none';
    const warn = document.getElementById('fusion-library-min-warn');
    if (warn) warn.style.display = 'none';
    const suggest = document.getElementById('fusion-lib-suggest-a');
    if (suggest) {
        suggest.style.display = 'none';
        suggest.innerHTML = '';
    }
}

function hasPendingOutgoingTo(friend) {
    if (!friend) return false;
    const f = String(friend).toLowerCase();
    return (OUTGOING_FUSION_REQUESTS || []).some(
        x => x && x.status === 'bekliyor' && String(x.to || '').toLowerCase() === f
    );
}

function startNewFusionRequest() {
    FORCE_SHOW_FUSION_PICKS = true;
    onFusionFriendSelected();
}

function onFusionFriendSelected() {
    const friend = document.getElementById('select-fusion-friend')?.value || '';
    const section = document.getElementById('fusion-picks-section');
    const warn = document.getElementById('fusion-library-min-warn');
    const sendBtn = document.getElementById('btn-send-fusion-invite');
    const newBtn = document.getElementById('btn-new-fusion-request');

    if (!friend) {
        FORCE_SHOW_FUSION_PICKS = false;
        hideFusionPicksSection();
        if (newBtn) newBtn.style.display = 'none';
        return;
    }

    const waiting = hasPendingOutgoingTo(friend);
    const hasCompleted = (COMPLETED_FUSION_INVITES || []).some(inv => {
        if (!inv || inv.status !== 'tamamlandi') return false;
        const me = String(CURRENT_USER || '').toLowerCase();
        const peer = String(inv.from || '').toLowerCase() === me ? inv.to : inv.from;
        return String(peer || '').toLowerCase() === String(friend).toLowerCase();
    });

    // Bekleyen istek veya tamamlanmış füzyon varken formu kapat (gönderen tarafı temiz kalsın)
    const shouldHidePicks = (waiting || hasCompleted) && !FORCE_SHOW_FUSION_PICKS;
    if (shouldHidePicks) {
        FORCE_SHOW_FUSION_PICKS = false;
        hideFusionPicksSection();
        if (newBtn) newBtn.style.display = waiting ? 'none' : 'inline-flex';
        return;
    }

    if (section) section.style.display = 'flex';
    if (newBtn) newBtn.style.display = 'none';

    const mediaWord = fusionMediaWord();
    const lib = getFusionLibraryItems();
    const searchA = document.getElementById('fusion-lib-search-a');
    if (searchA) searchA.value = '';
    const suggestA = document.getElementById('fusion-lib-suggest-a');
    if (suggestA) {
        suggestA.style.display = 'none';
        suggestA.innerHTML = '';
    }
    const ok = buildFusionSelectSlots('user-a-fusion-slots', 'fusion-select-a');

    if (warn) {
        if (!ok) {
            warn.style.display = 'block';
            warn.innerHTML = `Kitaplığınızda şu an <strong>${lib.length}</strong> ${mediaWord} var. Ortak zevk için en az <strong>5 ${mediaWord}</strong> eklemeniz gerekmektedir. (Dizi evreni → dizi, film evreni → film)`;
        } else {
            warn.style.display = 'none';
        }
    }
    if (sendBtn) {
        sendBtn.disabled = !ok;
        sendBtn.style.opacity = ok ? '1' : '0.55';
        sendBtn.style.pointerEvents = ok ? 'auto' : 'none';
    }
}

async function syncSocialFromServer() {
    if (!isUserLoggedInStrict()) return false;
    try {
        const localFriendsBefore = Array.isArray(USER_FRIENDS) ? [...USER_FRIENDS] : [];

        const [friendsRes, incomingRes, fusionInRes, fusionOutRes] = await Promise.all([
            socialApiFetch('/api/friends'),
            socialApiFetch('/api/friends/incoming'),
            socialApiFetch('/api/fusion/incoming'),
            socialApiFetch('/api/fusion/outgoing')
        ]);

        let synced = false;
        if (friendsRes.ok && friendsRes.data && Array.isArray(friendsRes.data.friends)) {
            let serverFriends = friendsRes.data.friends;

            // Render free disk wipe: sunucu [] döner, yerelde arkadaş vardır → geri yaz
            if (serverFriends.length === 0 && localFriendsBefore.length > 0) {
                const rehyd = await socialApiFetch('/api/friends/rehydrate', {
                    method: 'POST',
                    body: JSON.stringify({ friends: localFriendsBefore })
                });
                if (rehyd.ok && rehyd.data && Array.isArray(rehyd.data.friends) && rehyd.data.friends.length > 0) {
                    serverFriends = rehyd.data.friends;
                    console.info('[sosyal] Arkadaş listesi sunucuya geri yüklendi (ephemeral wipe koruması).');
                } else {
                    // Sunucu hâlâ boş / hata — yereli ezme
                    serverFriends = localFriendsBefore;
                    console.warn('[sosyal] Sunucu boş; yerel arkadaş listesi korundu.');
                }
            } else if (serverFriends.length > 0 && localFriendsBefore.length > 0) {
                // Birleştir: iki tarafta da olan + sunucu (silme ayrı API ile)
                const merged = [];
                const seen = new Set();
                [...serverFriends, ...localFriendsBefore].forEach(f => {
                    const k = String(f || '').toLowerCase();
                    if (!k || seen.has(k)) return;
                    seen.add(k);
                    merged.push(f);
                });
                if (merged.length > serverFriends.length) {
                    const rehyd = await socialApiFetch('/api/friends/rehydrate', {
                        method: 'POST',
                        body: JSON.stringify({ friends: merged })
                    });
                    if (rehyd.ok && Array.isArray(rehyd.data?.friends)) {
                        serverFriends = rehyd.data.friends;
                    } else {
                        serverFriends = merged;
                    }
                }
            }

            USER_FRIENDS = serverFriends;
            synced = true;
        }
        if (incomingRes.ok && incomingRes.data && Array.isArray(incomingRes.data.requests)) {
            PENDING_REQUESTS = normalizePendingFriendList(incomingRes.data.requests);
            synced = true;
        }
        if (fusionInRes.ok && fusionInRes.data && Array.isArray(fusionInRes.data.requests)) {
            PENDING_FUSION_REQUESTS = fusionInRes.data.requests;
            synced = true;
        }
        if (fusionOutRes.ok && fusionOutRes.data) {
            OUTGOING_FUSION_REQUESTS = fusionOutRes.data.outgoing || [];
            const serverCompleted = fusionOutRes.data.completed || [];
            // Ephemeral wipe: sunucu sonuçsuz dönerse localStorage sonuçlarını koru
            COMPLETED_FUSION_INVITES = serverCompleted.map(inv => {
                if (inv && inv.results && inv.results.length) {
                    saveFusionResultsLocal(inv.id, {
                        inviteId: inv.id,
                        recommendations: inv.results,
                        universe: inv.universe,
                        from: inv.from,
                        to: inv.to
                    });
                    return inv;
                }
                const local = loadFusionResultsLocal(inv && inv.id);
                if (local && local.recommendations && local.recommendations.length) {
                    return { ...inv, results: local.recommendations };
                }
                return inv;
            });
            synced = true;
        }
        if (synced && CURRENT_USER) saveUserData(CURRENT_USER);
        return synced;
    } catch (e) {
        console.warn('Sosyal senkronizasyon başarısız:', e);
        return false;
    }
}

function _buildIncomingRequestsHtml() {
    PENDING_REQUESTS = normalizePendingFriendList(PENDING_REQUESTS);
    const friendRows = PENDING_REQUESTS.map(req => `
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; background: rgba(0, 0, 0, 0.3); padding: 10px 14px; border-radius: 10px; border: 1px solid var(--border-card); margin-bottom: 8px; flex-wrap: wrap;">
            <span>👤 <strong style="color: #fff;">${escapeHtml(req.from)}</strong> size arkadaşlık isteği gönderdi.</span>
            <div style="display: flex; gap: 8px;">
                <button onclick="acceptFriendRequest(${Number(req.id) || 0}, '${escapeQuotes(req.from)}')" style="background: #10b981; color: #fff; border: none; padding: 6px 12px; border-radius: 8px; font-weight: 700; cursor: pointer;">✅ Onayla</button>
                <button onclick="rejectFriendRequest(${Number(req.id) || 0}, '${escapeQuotes(req.from)}')" style="background: #ef4444; color: #fff; border: none; padding: 6px 12px; border-radius: 8px; font-weight: 700; cursor: pointer;">❌ Reddet</button>
            </div>
        </div>
    `).join('');

    const fusionRows = (PENDING_FUSION_REQUESTS || []).map(req => {
        const uniLabel = String(req.universe || '').toUpperCase() === 'SERIES' ? 'dizi' : 'film';
        return `
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; background: rgba(236, 72, 153, 0.12); padding: 10px 14px; border-radius: 10px; border: 1px solid rgba(236,72,153,0.45); margin-bottom: 8px; flex-wrap: wrap;">
            <span>🧠 <strong style="color: #fff;">${escapeHtml(req.from)}</strong> sizinle ortak zevk füzyonunu kullanmak istiyor (${uniLabel}).</span>
            <div style="display: flex; gap: 8px;">
                <button onclick="openFusionRespondPanel(${Number(req.id)})" style="background: #ec4899; color: #fff; border: none; padding: 6px 12px; border-radius: 8px; font-weight: 700; cursor: pointer;">Yanıtla</button>
                <button onclick="rejectFusionInvite(${Number(req.id)})" style="background: #ef4444; color: #fff; border: none; padding: 6px 12px; border-radius: 8px; font-weight: 700; cursor: pointer;">❌ Reddet</button>
            </div>
        </div>`;
    }).join('');

    return (friendRows + fusionRows).trim() || 'Bekleyen istek yok.';
}

function _paintSocialLists() {
    const incomingContainer = document.getElementById('incoming-requests-list');
    const friendsContainer = document.getElementById('friends-list-container');
    const noFriendsAlert = document.getElementById('fusion-no-friends-alert');
    const fusionActivePanel = document.getElementById('fusion-active-panel');
    const fusionRespondPanel = document.getElementById('fusion-respond-panel');

    if (incomingContainer) incomingContainer.innerHTML = _buildIncomingRequestsHtml();

    if (friendsContainer) {
        if (USER_FRIENDS.length === 0) {
            friendsContainer.innerHTML = 'Henüz arkadaş listeniz boş.';
        } else {
            friendsContainer.innerHTML = USER_FRIENDS.map(friend => `
                <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0, 0, 0, 0.3); padding: 10px 14px; border-radius: 10px; border: 1px solid var(--border-card); margin-bottom: 8px;">
                    <span style="color: #fff; font-weight: 700;">👤 ${escapeHtml(friend)}</span>
                    <button onclick="removeFriend('${escapeQuotes(friend)}')" style="background: transparent; border: 1px solid rgba(239,68,68,0.5); color: #f87171; padding: 4px 10px; border-radius: 8px; cursor: pointer; font-size: 0.78rem;">Çıkar</button>
                </div>
            `).join('');
        }
    }

    if (USER_FRIENDS.length === 0) {
        if (noFriendsAlert) noFriendsAlert.style.display = 'block';
        if (fusionActivePanel) fusionActivePanel.style.display = 'none';
        hideFusionPicksSection();
    } else {
        if (noFriendsAlert) noFriendsAlert.style.display = 'none';
        if (fusionActivePanel) {
            fusionActivePanel.style.display = 'flex';
            populateFusionWizard();
        }
    }

    const outStatus = document.getElementById('fusion-outgoing-status');
    if (outStatus) {
        const pendingOut = (OUTGOING_FUSION_REQUESTS || []).filter(x => x.status === 'bekliyor');
        if (pendingOut.length) {
            outStatus.style.display = 'block';
            outStatus.textContent = `⏳ ${pendingOut.map(p => p.to).join(', ')} kullanıcısından füzyon yanıtı bekleniyor.`;
        } else {
            outStatus.style.display = 'none';
        }
    }

    if (fusionRespondPanel && !ACTIVE_FUSION_RESPOND_ID) {
        fusionRespondPanel.style.display = 'none';
    }

    const latestDone = (COMPLETED_FUSION_INVITES || []).find(x => x.status === 'tamamlandi');
    if (latestDone) {
        const warningBox = document.getElementById('fusion-overlap-warning');
        if (warningBox) {
            const ov = latestDone.overlap;
            if (ov && ov.count > 0) {
                warningBox.style.display = 'block';
                warningBox.textContent = `⚠️ ${ov.count} ortak seçim var — aynı film/dizi her iki tarafta da işaretlenmiş!`;
            } else {
                warningBox.style.display = 'none';
            }
        }
    }
    // Kalıcı füzyon sonuçları — GPT yeniden çağrılmaz; sunucu/local cache kullanılır
    renderCompletedFusions();
}

function renderSocialUI() {
    const socialTab = document.getElementById('tab-social');

    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        if (socialTab) {
            renderGuestLockBanner(socialTab, 'Sosyal', currentUniverse === 'MOVIES');
        }
        return;
    }

    if (socialTab && ORIGINAL_SOCIAL_TAB_HTML && !document.getElementById('input-friend-username')) {
        socialTab.innerHTML = ORIGINAL_SOCIAL_TAB_HTML;
    }

    // Önce yerel listeyi boya (anında), sonra sunucudan senkron
    _paintSocialLists();

    if (!renderSocialUI._syncing) {
        renderSocialUI._syncing = true;
        syncSocialFromServer().then(changed => {
            renderSocialUI._syncing = false;
            if (changed) renderSocialUIPaintOnly();
        }).catch(() => { renderSocialUI._syncing = false; });
    }
}

function renderSocialUIPaintOnly() {
    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') return;
    const socialTab = document.getElementById('tab-social');
    if (socialTab && ORIGINAL_SOCIAL_TAB_HTML && !document.getElementById('input-friend-username')) {
        socialTab.innerHTML = ORIGINAL_SOCIAL_TAB_HTML;
    }
    _paintSocialLists();
}

/** Aynı tarayıcıda kayıtlı hedefe yerel arkadaşlık isteği yazar. */
function sendLocalFriendRequest(targetUsername) {
    const from = CURRENT_USER;
    const target = String(targetUsername || '').trim();
    if (!from || !target) return false;

    try {
        const key = `MATRIX_USER_DATA_${target.toLowerCase()}`;
        let data = {};
        try { data = JSON.parse(localStorage.getItem(key) || '{}') || {}; } catch (e) { data = {}; }
        const pending = normalizePendingFriendList(data.PENDING_REQUESTS || []);
        const already = pending.some(p => String(p.from || '').toLowerCase() === String(from).toLowerCase());
        if (!already) {
            pending.push({ id: Date.now(), from });
            data.PENDING_REQUESTS = pending;
            localStorage.setItem(key, JSON.stringify(data));
        }
        return true;
    } catch (e) {
        console.warn('Yerel arkadaşlık isteği yazılamadı:', e);
        return false;
    }
}

async function sendFriendRequest() {
    const input = document.getElementById('input-friend-username');
    if (!input) return;

    if (!isUserLoggedInStrict()) {
        showToast('🔒 Arkadaşlık isteği için giriş yapın.', 2200);
        openAuthModal('LOGIN');
        return;
    }

    const raw = input.value.trim();
    if (!raw) {
        showToast('⚠️ Lütfen arkadaşınızın kullanıcı adını giriniz.', 2000);
        return;
    }

    const needle = raw.toLowerCase();
    if (CURRENT_USER && String(CURRENT_USER).toLowerCase() === needle) {
        showToast('⚠️ Kendinizi arkadaş olarak ekleyemezsiniz.', 2200);
        return;
    }

    if (USER_FRIENDS.some(f => String(f).toLowerCase() === needle)) {
        showToast(`ℹ️ ${raw} zaten arkadaş listenizde kayıtlı.`, 2000);
        return;
    }

    if (typeof loadRegisteredAccounts === 'function') loadRegisteredAccounts();
    const lookup = await lookupRegisteredUsername(raw);
    const localKnown = isLocalRegisteredUsername(raw) || !!(lookup && lookup.exists);

    showToast('⏳ İstek gönderiliyor...', 1200);

    let res = { ok: false, status: 0, data: null };
    try {
        res = await socialApiFetch('/api/friends/request', {
            method: 'POST',
            body: JSON.stringify({ username: raw })
        });
    } catch (e) {
        res = { ok: false, status: 0, data: null };
    }

    if (res.ok && res.data && res.data.ok) {
        // Aynı tarayıcıda karşı taraf da görsün diye yerel yedeği de yaz
        if (localKnown) sendLocalFriendRequest(lookup.username || raw);
        input.value = '';
        showToast(`✅ ${res.data.message || 'İstek gönderildi!'}`, 2800);
        await syncSocialFromServer();
        renderSocialUIPaintOnly();
        if (CURRENT_USER) saveUserData(CURRENT_USER);
        return;
    }

    if (res.status === 401) {
        showToast('🔒 Oturum doğrulanamadı. Tekrar giriş yapın.', 2800);
        openAuthModal('LOGIN');
        return;
    }

    // Sunucu reddetti / boş DB / offline → yerel kayıtlı kullanıcıya yedek istek
    if (localKnown) {
        const canonical = (lookup && lookup.username) ? lookup.username : raw;
        const wrote = sendLocalFriendRequest(canonical);
        if (wrote) {
            input.value = '';
            showToast(`✅ ${canonical} kullanıcısına istek gönderildi!`, 2800);
            renderSocialUIPaintOnly();
            if (CURRENT_USER) saveUserData(CURRENT_USER);
            return;
        }
    }

    // Bilinen kullanıcı değilse ve sunucu da kabul etmediyse net hata
    const serverMsg = res.data && (res.data.message || res.data.error);
    if (serverMsg && /kayıtlı değil|bulunamadı|not found/i.test(String(serverMsg))) {
        // Sunucu "yok" dese bile istek artık kabul edilmeli — yine de yerel bilinmiyorsa uyar
        showToast(`⚠️ '${raw}' adında kayıtlı bir kullanıcı bulunamadı. Karşı tarafın bu sitede kayıtlı olduğundan emin olun.`, 3500);
        return;
    }

    showToast(`⚠️ ${serverMsg || 'İstek gönderilemedi.'}`, 3000);
}

async function acceptFriendRequest(requestId, username) {
    const res = await socialApiFetch('/api/friends/respond', {
        method: 'POST',
        body: JSON.stringify({ requestId: requestId, accept: true })
    });
    if (res.ok && res.data && res.data.ok) {
        if (Array.isArray(res.data.friends)) USER_FRIENDS = res.data.friends;
        PENDING_REQUESTS = PENDING_REQUESTS.filter(r => {
            const from = typeof r === 'object' ? r.from : r;
            return String(from).toLowerCase() !== String(username).toLowerCase()
                && Number(typeof r === 'object' ? r.id : 0) !== Number(requestId);
        });
        if (username && !USER_FRIENDS.some(f => String(f).toLowerCase() === String(username).toLowerCase())) {
            USER_FRIENDS.push(username);
        }
        showToast(`✅ ${username} arkadaşlık isteği onaylandı!`, 2000);
        renderSocialUIPaintOnly();
        if (CURRENT_USER) saveUserData(CURRENT_USER);
        return;
    }
    showToast(`⚠️ ${(res.data && res.data.message) || 'İstek onaylanamadı.'}`, 2500);
}

async function rejectFriendRequest(requestId, username) {
    await socialApiFetch('/api/friends/respond', {
        method: 'POST',
        body: JSON.stringify({ requestId: requestId, accept: false })
    });
    PENDING_REQUESTS = PENDING_REQUESTS.filter(r => {
        const from = typeof r === 'object' ? r.from : r;
        return String(from).toLowerCase() !== String(username).toLowerCase()
            && Number(typeof r === 'object' ? r.id : 0) !== Number(requestId);
    });
    showToast(`❌ ${username} arkadaşlık isteği reddedildi.`, 2000);
    renderSocialUIPaintOnly();
    if (CURRENT_USER) saveUserData(CURRENT_USER);
}

async function removeFriend(friendUsername) {
    const res = await socialApiFetch('/api/friends/remove', {
        method: 'POST',
        body: JSON.stringify({ username: friendUsername })
    });
    USER_FRIENDS = USER_FRIENDS.filter(f => String(f).toLowerCase() !== String(friendUsername).toLowerCase());
    if (res.ok && res.data && Array.isArray(res.data.friends)) USER_FRIENDS = res.data.friends;
    showToast(`👋 ${friendUsername} arkadaş listesinden çıkarıldı.`, 2000);
    renderSocialUIPaintOnly();
    if (CURRENT_USER) saveUserData(CURRENT_USER);
}

function populateFusionWizard() {
    const selectFriend = document.getElementById('select-fusion-friend');
    if (selectFriend) {
        const prev = selectFriend.value;
        selectFriend.innerHTML = `<option value="">— Arkadaş seçin —</option>`
            + USER_FRIENDS.map(f => `<option value="${escapeHtml(f)}">${escapeHtml(f)}</option>`).join('');
        // Önceki seçim geçerliyse koru; yoksa boş kalsın (5 yapım paneli kapalı)
        if (prev && USER_FRIENDS.some(f => String(f) === String(prev))) {
            selectFriend.value = prev;
        } else {
            selectFriend.value = '';
        }
    }
    // Arkadaş seçilmeden 5 yapım paneli açılmaz
    onFusionFriendSelected();
}

let FUSION_PEER_PICKS_VISIBLE = false;

function toggleFusionPeerPicks() {
    const invite = (PENDING_FUSION_REQUESTS || []).find(r => Number(r.id) === Number(ACTIVE_FUSION_RESPOND_ID));
    const wrap = document.getElementById('fusion-peer-picks-wrap');
    const list = document.getElementById('fusion-peer-picks-list');
    const btn = document.getElementById('btn-reveal-peer-picks');
    if (!invite || !wrap || !list) return;

    FUSION_PEER_PICKS_VISIBLE = !FUSION_PEER_PICKS_VISIBLE;
    if (FUSION_PEER_PICKS_VISIBLE) {
        const uni = invite.universe || currentUniverse;
        const picks = invite.senderSelections || [];
        list.innerHTML = picks.map((id, i) =>
            `<li>${i + 1}. ${escapeHtml(resolveFusionTitleById(id, uni))}</li>`
        ).join('') || '<li>Seçim bilgisi yok</li>';
        wrap.style.display = 'block';
        if (btn) btn.innerHTML = '<i class="fa-solid fa-eye-slash"></i> Karşı tarafın seçimlerini gizle';
    } else {
        wrap.style.display = 'none';
        if (btn) btn.innerHTML = '<i class="fa-solid fa-eye"></i> Karşı tarafın dizi/filmlerini gör';
    }
}

function openFusionRespondPanel(inviteId) {
    const invite = (PENDING_FUSION_REQUESTS || []).find(r => Number(r.id) === Number(inviteId));
    if (!invite) {
        showToast('⚠️ Füzyon isteği bulunamadı.', 2000);
        return;
    }
    ACTIVE_FUSION_RESPOND_ID = Number(inviteId);
    FUSION_PEER_PICKS_VISIBLE = false;

    const panel = document.getElementById('fusion-respond-panel');
    const title = document.getElementById('fusion-respond-title');
    const hint = document.getElementById('fusion-respond-hint');
    const peerWrap = document.getElementById('fusion-peer-picks-wrap');
    const revealBtn = document.getElementById('btn-reveal-peer-picks');
    const libWarn = document.getElementById('fusion-respond-lib-warn');
    const acceptBtn = document.getElementById('btn-fusion-accept');

    const uni = invite.universe || currentUniverse;
    const mediaWord = fusionMediaWord(uni);

    if (title) title.textContent = `${invite.from} ile ortak zevk füzyonu`;
    if (hint) {
        hint.textContent = `${invite.from} size füzyon isteği gönderdi. Kitaplığınızdan 5 ${mediaWord} seçin. İsterseniz karşı tarafın seçimlerini görebilirsiniz.`;
    }
    if (peerWrap) peerWrap.style.display = 'none';
    if (revealBtn) {
        revealBtn.style.display = 'inline-flex';
        revealBtn.innerHTML = '<i class="fa-solid fa-eye"></i> Karşı tarafın dizi/filmlerini gör';
    }

    const lib = getFusionLibraryItems(uni);
    const searchWrap = document.getElementById('fusion-respond-search-wrap');
    const searchEl = document.getElementById('fusion-lib-search-respond');
    if (searchWrap) searchWrap.style.display = 'block';
    if (searchEl) {
        searchEl.value = '';
        searchEl.style.display = 'block';
    }
    const suggestR = document.getElementById('fusion-lib-suggest-respond');
    if (suggestR) {
        suggestR.style.display = 'none';
        suggestR.innerHTML = '';
    }
    const ok = buildFusionSelectSlots('fusion-respond-slots', 'fusion-select-respond', null, uni);
    if (libWarn) {
        if (!ok) {
            libWarn.style.display = 'block';
            libWarn.innerHTML = `Kitaplığınızda yeterli ${mediaWord} yok (şu an ${lib.length}). En az <strong>5 ${mediaWord}</strong> ekleyin; dizi evreni isteği için dizi, film evreni için film gerekir.`;
            if (searchWrap) searchWrap.style.display = 'none';
            if (searchEl) searchEl.style.display = 'none';
        } else {
            libWarn.style.display = 'none';
            if (searchWrap) searchWrap.style.display = 'block';
        }
    }
    if (acceptBtn) {
        acceptBtn.disabled = !ok;
        acceptBtn.style.opacity = ok ? '1' : '0.55';
        acceptBtn.style.pointerEvents = ok ? 'auto' : 'none';
    }

    if (panel) {
        panel.style.display = 'flex';
        panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

async function rejectFusionInvite(inviteId) {
    await socialApiFetch('/api/fusion/respond', {
        method: 'POST',
        body: JSON.stringify({ requestId: inviteId, accept: false })
    });
    PENDING_FUSION_REQUESTS = (PENDING_FUSION_REQUESTS || []).filter(r => Number(r.id) !== Number(inviteId));
    if (ACTIVE_FUSION_RESPOND_ID === Number(inviteId)) {
        ACTIVE_FUSION_RESPOND_ID = null;
        const panel = document.getElementById('fusion-respond-panel');
        if (panel) panel.style.display = 'none';
    }
    showToast('❌ Füzyon isteği reddedildi.', 2000);
    renderSocialUIPaintOnly();
}

async function submitFusionResponse(accept) {
    if (!ACTIVE_FUSION_RESPOND_ID) {
        showToast('⚠️ Yanıtlanacak füzyon isteği yok.', 2000);
        return;
    }
    if (!accept) {
        await rejectFusionInvite(ACTIVE_FUSION_RESPOND_ID);
        return;
    }
    const pendingInvite = (PENDING_FUSION_REQUESTS || []).find(r => Number(r.id) === Number(ACTIVE_FUSION_RESPOND_ID));
    const uni = (pendingInvite && pendingInvite.universe) || currentUniverse;
    const mediaWord = fusionMediaWord(uni);
    const lib = getFusionLibraryItems(uni);
    if (lib.length < 5) {
        showToast(`⚠️ Kitaplığınıza en az 5 ${mediaWord} eklemeniz gerekmektedir.`, 3000);
        return;
    }
    const selections = readFusionSlotValues('.fusion-select-respond');
    if (selections.length !== 5 || new Set(selections).size !== 5) {
        showToast(`⚠️ Kitaplığınızdan tam olarak 5 farklı ${mediaWord} seçin.`, 2500);
        return;
    }

    showToast('⏳ Füzyon yanıtı gönderiliyor...', 1200);
    const fullLibrary = getActiveLibraryIdsForFusion();
    const res = await socialApiFetch('/api/fusion/respond', {
        method: 'POST',
        body: JSON.stringify({
            requestId: ACTIVE_FUSION_RESPOND_ID,
            accept: true,
            selections,
            library: fullLibrary,
            fullLibrary
        })
    });

    if (!res.ok || !res.data || !res.data.ok) {
        showToast(`⚠️ ${(res.data && res.data.message) || 'Füzyon yanıtı başarısız.'}`, 3000);
        return;
    }

    let invite = res.data.invite;
    const serverResults = (res.data.results && res.data.results.length)
        ? res.data.results
        : (invite && invite.results) || null;

    PENDING_FUSION_REQUESTS = (PENDING_FUSION_REQUESTS || []).filter(r => Number(r.id) !== Number(ACTIVE_FUSION_RESPOND_ID));
    ACTIVE_FUSION_RESPOND_ID = null;
    const panel = document.getElementById('fusion-respond-panel');
    if (panel) panel.style.display = 'none';

    if (res.data.overlap && res.data.overlap.count > 0) {
        const warningBox = document.getElementById('fusion-overlap-warning');
        if (warningBox) {
            warningBox.style.display = 'block';
            warningBox.textContent = `⚠️ ${res.data.overlap.count} ortak seçim var — aynı film/dizi her iki tarafta da işaretlenmiş!`;
        }
        showToast(`⚠️ ${res.data.message}`, 3200);
    } else {
        showToast('✅ Seçimler kaydedildi, füzyon hesaplanıyor...', 2200);
    }

    if (invite && invite.id) {
        if (serverResults && serverResults.length) {
            invite = { ...invite, results: serverResults };
            saveFusionResultsLocal(invite.id, {
                inviteId: invite.id,
                recommendations: serverResults,
                universe: invite.universe,
                from: invite.from,
                to: invite.to
            });
        } else {
            invite = await ensureFusionResultsComputed(invite);
        }
        upsertCompletedFusionInvite(invite);
    }
    await syncSocialFromServer();
    renderSocialUIPaintOnly();
}

async function sendFusionInvite() {
    if (!isUserLoggedInStrict()) {
        showToast('🔒 Füzyon için giriş yapın.', 2200);
        openAuthModal('LOGIN');
        return;
    }
    const friend = document.getElementById('select-fusion-friend')?.value;
    if (!friend) {
        showToast('⚠️ Önce bir arkadaş seçin.', 2000);
        return;
    }

    const mediaWord = fusionMediaWord();
    const lib = getFusionLibraryItems();
    if (lib.length < 5) {
        showToast(`⚠️ Kitaplığınıza en az 5 ${mediaWord} eklemeniz gerekmektedir.`, 3000);
        return;
    }

    const selections = readFusionSlotValues('.fusion-select-a');
    if (selections.length !== 5 || new Set(selections).size !== 5) {
        showToast(`⚠️ Kitaplığınızdan tam olarak 5 farklı ${mediaWord} seçin.`, 2500);
        return;
    }

    const universe = currentUniverse === 'MOVIES' ? 'MOVIES' : 'SERIES';
    const fullLibrary = getActiveLibraryIdsForFusion();
    showToast('⏳ Füzyon isteği gönderiliyor...', 1200);
    const res = await socialApiFetch('/api/fusion/invite', {
        method: 'POST',
        body: JSON.stringify({
            friend,
            universe,
            selections,
            library: fullLibrary,
            fullLibrary
        })
    });

    if (res.ok && res.data && res.data.ok) {
        FORCE_SHOW_FUSION_PICKS = false;
        showToast(`✅ ${res.data.message || 'Füzyon isteği gönderildi!'}`, 2800);
        await syncSocialFromServer();
        renderSocialUIPaintOnly();
        return;
    }
    showToast(`⚠️ ${(res.data && res.data.message) || 'Füzyon isteği gönderilemedi.'}`, 3000);
}

function likeItemPreference(itemId) {
    const isMovie = (currentUniverse === 'MOVIES');
    const targetArr = isMovie ? LIKED_MOVIES_IDS : LIKED_SERIES_IDS;

    if (targetArr.includes(itemId)) {
        showToast('⚠️ Bu yapım zaten Beğenilenler tercihlerinizde kayıtlı!', 2000);
        return;
    }

    targetArr.unshift(itemId);
    showToast('👍 Yapım Beğenilenler tercihleriniz arasına eklendi!', 2400);
    renderFeedbackUI();
}

function hideItemPreference(itemId) {
    const isMovie = (currentUniverse === 'MOVIES');
    const targetArr = isMovie ? HIDDEN_MOVIES_IDS : HIDDEN_SERIES_IDS;

    if (targetArr.includes(itemId)) {
        showToast('⚠️ Bu yapım zaten Gizlenenler tercihlerinizde kayıtlı!', 2000);
        return;
    }

    targetArr.unshift(itemId);

    const cardEl = document.getElementById(`fusion-card-${itemId}`);
    if (cardEl) {
        cardEl.style.opacity = '0';
        cardEl.style.transform = 'scale(0.95)';
        setTimeout(() => {
            cardEl.remove();
        }, 300);
    }

    showToast('👁️‍🗨️ Yapım Gizlenenler tercihleriniz arasına eklendi.', 2400);
    renderFeedbackUI();
}

function likeFusionRecommendation(itemId) {
    likeItemPreference(itemId);
}

function hideFusionRecommendation(itemId) {
    hideItemPreference(itemId);
}

/* ==========================================================================
   📌 BAŞLIK: GERİ BİLDİRİM VE TERCİH YÖNETİMİ MOTORU (BEĞENİLENLER & GİZLENENLER)
   ========================================================================== */
let LIKED_SERIES_IDS = ['series_01']; 
let LIKED_MOVIES_IDS = ['tt1375666']; 
let HIDDEN_SERIES_IDS = ['series_02']; 
let HIDDEN_MOVIES_IDS = [];

let currentLikedPage = 1;
let currentHiddenPage = 1;
const PREF_PER_PAGE = 5;

// --------------------------------------------------------------------------
// 🔒 HESAP GEÇİŞLERİNDE VERİ SIZINTISINI ÖNLEMEK İÇİN VARSAYILAN (DEMO) STATE YEDEĞİ
// --------------------------------------------------------------------------
const DEFAULT_USER_SERIES_LIBRARY = JSON.parse(JSON.stringify(USER_SERIES_LIBRARY));
const DEFAULT_USER_MOVIES_LIBRARY = JSON.parse(JSON.stringify(USER_MOVIES_LIBRARY));
const DEFAULT_USER_FAVORITES = [...USER_FAVORITES];
const DEFAULT_USER_FRIENDS = [...USER_FRIENDS];
const DEFAULT_PENDING_REQUESTS = [...PENDING_REQUESTS];
const DEFAULT_PENDING_FUSION_REQUESTS = [...PENDING_FUSION_REQUESTS];
const DEFAULT_LIKED_SERIES_IDS = [...LIKED_SERIES_IDS];
const DEFAULT_LIKED_MOVIES_IDS = [...LIKED_MOVIES_IDS];
const DEFAULT_HIDDEN_SERIES_IDS = [...HIDDEN_SERIES_IDS];
const DEFAULT_HIDDEN_MOVIES_IDS = [...HIDDEN_MOVIES_IDS];

// Yeni bir hesaba geçmeden/çıkış yapmadan önce bellekteki state'i temiz demo
// varsayılanlarına döndürür; böylece bir kullanıcının verisi başka bir
// kullanıcıya (veya misafire) hiç sızmaz.
function resetUserDataToDefaults() {
    USER_SERIES_LIBRARY = JSON.parse(JSON.stringify(DEFAULT_USER_SERIES_LIBRARY));
    USER_MOVIES_LIBRARY = JSON.parse(JSON.stringify(DEFAULT_USER_MOVIES_LIBRARY));
    USER_FAVORITES = [...DEFAULT_USER_FAVORITES];
    USER_FRIENDS = [...DEFAULT_USER_FRIENDS];
    PENDING_REQUESTS = [...DEFAULT_PENDING_REQUESTS];
    PENDING_FUSION_REQUESTS = [...DEFAULT_PENDING_FUSION_REQUESTS];
    OUTGOING_FUSION_REQUESTS = [];
    COMPLETED_FUSION_INVITES = [];
    ACTIVE_FUSION_RESPOND_ID = null;
    LIKED_SERIES_IDS = [...DEFAULT_LIKED_SERIES_IDS];
    LIKED_MOVIES_IDS = [...DEFAULT_LIKED_MOVIES_IDS];
    HIDDEN_SERIES_IDS = [...DEFAULT_HIDDEN_SERIES_IDS];
    HIDDEN_MOVIES_IDS = [...DEFAULT_HIDDEN_MOVIES_IDS];
}

function renderFeedbackUI() {
    const feedbackTab = document.getElementById('tab-feedback');
    const isMovie = (currentUniverse === 'MOVIES');

    if (!CURRENT_USER || CURRENT_USER === 'Kullanıcı') {
        if (feedbackTab) {
            renderGuestLockBanner(feedbackTab, 'Geri Bildirim', isMovie);
        }
        return;
    }

    if (feedbackTab && ORIGINAL_FEEDBACK_TAB_HTML && !document.getElementById('feedback-text-input')) {
        feedbackTab.innerHTML = ORIGINAL_FEEDBACK_TAB_HTML;
    }

    const feedbackTitle = document.getElementById('feedback-panel-title');
    const likedContainer = document.getElementById('liked-items-container');
    const hiddenContainer = document.getElementById('hidden-items-container');

    const likedPagination = document.getElementById('liked-pagination');
    const hiddenPagination = document.getElementById('hidden-pagination');

    if (feedbackTitle) {
        feedbackTitle.innerHTML = `<i class="fa-solid fa-gear" style="color: var(--primary-color);"></i> Geri Bildirim ve Tercih Yönetimi (${isMovie ? 'Filmler' : 'Diziler'})`;
    }

    // Veri Kümesini Hazırla
    const dataset = isMovie 
        ? ((typeof REAL_MOVIES_DATA !== 'undefined') ? REAL_MOVIES_DATA : SAMPLE_MOVIES)
        : ((typeof REAL_SERIES_DATA !== 'undefined') ? REAL_SERIES_DATA : SAMPLE_SERIES);

    const likedIds = isMovie ? LIKED_MOVIES_IDS : LIKED_SERIES_IDS;
    const hiddenIds = isMovie ? HIDDEN_MOVIES_IDS : HIDDEN_SERIES_IDS;

    // 1. BEĞENİLENLER LİSTESİ VE SAYFALAMASI
    const likedItems = dataset.filter(item => likedIds.includes(item.id));
    if (likedContainer) {
        if (likedItems.length === 0) {
            likedContainer.innerHTML = `<div style="font-size: 0.9rem; color: #9ca3af;">Henüz bir işlem yok.</div>`;
            if (likedPagination) likedPagination.style.display = 'none';
        } else {
            const totalLikedPages = Math.ceil(likedItems.length / PREF_PER_PAGE) || 1;
            if (currentLikedPage > totalLikedPages) currentLikedPage = totalLikedPages;
            if (currentLikedPage < 1) currentLikedPage = 1;

            const startIndex = (currentLikedPage - 1) * PREF_PER_PAGE;
            const paginatedLiked = likedItems.slice(startIndex, startIndex + PREF_PER_PAGE);

            likedContainer.innerHTML = paginatedLiked.map(item => renderPreferenceCardHtml(item, 'LIKED', isMovie)).join('');

            const shownLiked = fillNumberedPaginationNav(
                'liked-numbered-pagination',
                currentLikedPage,
                totalLikedPages,
                'goToLikedPage'
            );
            if (likedPagination) likedPagination.style.display = shownLiked ? 'flex' : 'none';
        }
    }

    // 2. GİZLENENLER LİSTESİ VE SAYFALAMASI
    const hiddenItems = dataset.filter(item => hiddenIds.includes(item.id));
    if (hiddenContainer) {
        if (hiddenItems.length === 0) {
            hiddenContainer.innerHTML = `<div style="font-size: 0.9rem; color: #9ca3af;">Henüz bir işlem yok.</div>`;
            if (hiddenPagination) hiddenPagination.style.display = 'none';
        } else {
            const totalHiddenPages = Math.ceil(hiddenItems.length / PREF_PER_PAGE) || 1;
            if (currentHiddenPage > totalHiddenPages) currentHiddenPage = totalHiddenPages;
            if (currentHiddenPage < 1) currentHiddenPage = 1;

            const startIndex = (currentHiddenPage - 1) * PREF_PER_PAGE;
            const paginatedHidden = hiddenItems.slice(startIndex, startIndex + PREF_PER_PAGE);

            hiddenContainer.innerHTML = paginatedHidden.map(item => renderPreferenceCardHtml(item, 'HIDDEN', isMovie)).join('');

            const shownHidden = fillNumberedPaginationNav(
                'hidden-numbered-pagination',
                currentHiddenPage,
                totalHiddenPages,
                'goToHiddenPage'
            );
            if (hiddenPagination) hiddenPagination.style.display = shownHidden ? 'flex' : 'none';
        }
    }

    if (CURRENT_USER) saveUserData(CURRENT_USER);
}

/* ==========================================================================
   🛡️ YÖNETİM PANELİ (YALNIZCA SUNUCU ONAYLI ADMİN OTURUMU)
   ========================================================================== */
function setAdminSessionFlag(isAdmin) {
    IS_ADMIN_SESSION = !!isAdmin;
    if (CURRENT_USER && CURRENT_USER !== 'Kullanıcı') {
        sessionStorage.setItem(`MATRIX_ADMIN_${CURRENT_USER.toLowerCase()}`, IS_ADMIN_SESSION ? '1' : '0');
    } else {
        IS_ADMIN_SESSION = false;
    }
    applyAdminNavVisibility();
}

function applyAdminNavVisibility() {
    const navBtn = document.getElementById('nav-admin-inbox');
    const adminTab = document.getElementById('tab-admin-inbox');
    const show = IS_ADMIN_SESSION && isUserLoggedInStrict();

    if (navBtn) {
        navBtn.hidden = !show;
        navBtn.style.display = show ? '' : 'none';
    }

    if (!show && adminTab && adminTab.classList.contains('active')) {
        adminTab.classList.remove('active');
        const exploreTab = document.getElementById('tab-explore');
        const exploreNav = document.querySelector('.nav-item[data-tab="tab-explore"]');
        if (exploreTab) exploreTab.classList.add('active');
        if (exploreNav) exploreNav.classList.add('active');
        document.querySelectorAll('.nav-item').forEach(n => {
            if (n !== exploreNav) n.classList.remove('active');
        });
    }
}

async function adminAuthorizedFetch(path, options = {}) {
    const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
    const token = await ensureSignedAuthToken();
    if (!token) return { ok: false, status: 401, data: null };
    const headers = {
        ...(options.headers || {}),
        'Authorization': `Bearer ${token}`
    };
    if (options.body && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }
    try {
        const res = await fetch(`${baseUrl}${path}`, { ...options, headers });
        let data = null;
        try { data = await res.json(); } catch (e) { data = null; }
        return { ok: res.ok, status: res.status, data };
    } catch (e) {
        return { ok: false, status: 0, data: null };
    }
}

async function refreshAdminSessionFromServer() {
    if (!isUserLoggedInStrict()) {
        IS_ADMIN_SESSION = false;
        applyAdminNavVisibility();
        return;
    }
    const cached = sessionStorage.getItem(`MATRIX_ADMIN_${CURRENT_USER.toLowerCase()}`);
    if (cached === '1') IS_ADMIN_SESSION = true;

    const res = await adminAuthorizedFetch('/api/auth/session');
    if (res.ok && res.data && res.data.ok) {
        setAdminSessionFlag(!!res.data.isAdmin);
    } else if (res.status === 403 || res.status === 401) {
        setAdminSessionFlag(false);
    } else {
        applyAdminNavVisibility();
    }
}

function parseAdminItemTimestamp(item) {
    const raw = item.createdAt || item.created_at || item.date || '';
    const t = Date.parse(String(raw).replace(' ', 'T'));
    return Number.isFinite(t) ? t : 0;
}

function renderAdminErrorReportCard(r) {
    const fieldPills = (r.fields || []).map(fid =>
        `<span class="error-report-field-pill">${escapeHtml(ERROR_REPORT_FIELD_LABELS[fid] || fid)}</span>`
    ).join('');
    const when = r.createdAt || r.created_at || '';
    const who = r.username ? `@${escapeHtml(r.username)}` : 'Misafir';
    const typeLabel = r.mediaType === 'MOVIES' ? 'Film' : 'Dizi';
    const status = r.status || 'open';
    const statusClass = status === 'resolved' ? 'is-resolved' : (status === 'ignored' ? 'is-ignored' : 'is-open');

    return `
        <div class="admin-inbox-card ${statusClass}" data-admin-kind="error">
            <div class="admin-inbox-card-top">
                <div>
                    <span class="admin-type-badge admin-type-error"><i class="fa-solid fa-flag"></i> Hata Bildirimi</span>
                    <div class="admin-inbox-card-title">${escapeHtml(r.itemTitle || r.itemId || 'Bilinmeyen yapım')}</div>
                    <div class="admin-inbox-card-meta">${typeLabel} · ${who} · ${escapeHtml(String(when).replace('T', ' ').slice(0, 19))}</div>
                </div>
                <span class="admin-status-badge ${statusClass}">${escapeHtml(status)}</span>
            </div>
            <div class="admin-inbox-card-fields">${fieldPills || '<span class="admin-inbox-empty-note">Alan seçilmedi</span>'}</div>
            ${r.note ? `<div class="admin-inbox-card-note">📝 ${escapeHtml(r.note)}</div>` : ''}
            ${r.id && String(r.id).match(/^\d+$/) && status === 'open' ? `
                <div class="admin-inbox-card-actions">
                    <button type="button" class="admin-action-btn admin-action-resolve" onclick="updateErrorReportStatus(${r.id}, 'resolved')">✓ Çözüldü</button>
                    <button type="button" class="admin-action-btn admin-action-ignore" onclick="updateErrorReportStatus(${r.id}, 'ignored')">Yoksay</button>
                </div>
            ` : ''}
        </div>
    `;
}

function renderAdminFeedbackCard(f) {
    const when = f.createdAt || f.created_at || '';
    const who = f.username ? `@${escapeHtml(f.username)}` : 'Anonim';
    const uni = f.mediaType === 'MOVIES' ? 'Film evreni' : 'Dizi evreni';
    return `
        <div class="admin-inbox-card admin-feedback-card" data-admin-kind="feedback">
            <div class="admin-inbox-card-top">
                <div>
                    <span class="admin-type-badge admin-type-feedback"><i class="fa-solid fa-comment-dots"></i> Geri Bildirim Mesajı</span>
                    <div class="admin-inbox-card-title">${who}</div>
                    <div class="admin-inbox-card-meta">${uni} · ${escapeHtml(String(when).replace('T', ' ').slice(0, 19))}</div>
                </div>
            </div>
            <div class="admin-inbox-card-note admin-feedback-message">${escapeHtml(f.message || '')}</div>
        </div>
    `;
}

async function renderAdminInboxUI(forceRefresh) {
    if (!IS_ADMIN_SESSION || !isUserLoggedInStrict()) return;

    const unifiedInbox = document.getElementById('admin-unified-inbox');
    const typeFilterEl = document.getElementById('admin-inbox-type-filter');
    const filterEl = document.getElementById('admin-error-status-filter');
    const typeFilter = typeFilterEl ? typeFilterEl.value : 'ALL';
    const statusFilter = filterEl ? filterEl.value : 'ALL';

    if (unifiedInbox && forceRefresh) {
        unifiedInbox.innerHTML = `<div class="admin-inbox-loading"><i class="fa-solid fa-spinner fa-spin"></i> Yükleniyor...</div>`;
    }

    let reports = [];
    let feedbackItems = [];

    const errRes = await adminAuthorizedFetch('/api/error-reports?limit=100');
    if (errRes.ok && errRes.data && Array.isArray(errRes.data.reports)) {
        reports = errRes.data.reports;
    } else if (!errRes.ok && errRes.status !== 403) {
        reports = readLocalErrorReports();
    }

    const fbRes = await adminAuthorizedFetch('/api/feedback?limit=100');
    if (fbRes.ok && fbRes.data && Array.isArray(fbRes.data.feedback)) {
        feedbackItems = fbRes.data.feedback;
    }

    const openCount = reports.filter(r => (r.status || 'open') === 'open').length;
    const resolvedCount = reports.filter(r => r.status === 'resolved').length;
    const statOpen = document.getElementById('admin-stat-open');
    const statResolved = document.getElementById('admin-stat-resolved');
    const statFeedback = document.getElementById('admin-stat-feedback');
    if (statOpen) statOpen.textContent = String(openCount);
    if (statResolved) statResolved.textContent = String(resolvedCount);
    if (statFeedback) statFeedback.textContent = String(feedbackItems.length);

    let unified = [
        ...reports.map(r => ({ kind: 'error', sortDate: parseAdminItemTimestamp(r), data: r })),
        ...feedbackItems.map(f => ({ kind: 'feedback', sortDate: parseAdminItemTimestamp(f), data: f }))
    ].sort((a, b) => b.sortDate - a.sortDate);

    if (typeFilter === 'error') {
        unified = unified.filter(item => item.kind === 'error');
    } else if (typeFilter === 'feedback') {
        unified = unified.filter(item => item.kind === 'feedback');
    }

    if (statusFilter && statusFilter !== 'ALL') {
        unified = unified.filter(item => {
            if (item.kind !== 'error') return typeFilter === 'feedback';
            return (item.data.status || 'open') === statusFilter;
        });
    }

    if (!unifiedInbox) return;

    if (!unified.length) {
        unifiedInbox.innerHTML = `<div class="admin-inbox-empty">Bu filtreye uygun geri bildirim yok.</div>`;
        return;
    }

    unifiedInbox.innerHTML = unified.map(item =>
        item.kind === 'error'
            ? renderAdminErrorReportCard(item.data)
            : renderAdminFeedbackCard(item.data)
    ).join('');
}

// TERCİH KART HTML ŞABLONU (FOTOĞRAFTAKİ BİREBİR MİMARİ - ÖZET VARSAYILAN KAPALI GELİR!)
function renderPreferenceCardHtml(item, prefType, isMovie) {
    const seasonsOrDuration = !isMovie 
        ? `${item.total_seasons || item.seasons_num || 1} Sezon (${item.total_episodes || (item.season_episodes_map || [10]).reduce((a,b)=>a+b,0)} Bölüm)`
        : `${item.ep_duration || 120} dk`;

    const statusText = item.status || item.status_text || 'Devam Ediyor';
    const genresText = (item.genres && Array.isArray(item.genres)) ? item.genres.join(', ') : 'Dram, Suç';

    return `
        <div class="media-horizontal-card" style="padding: 12px; transition: all 0.3s ease; position: relative; overflow: hidden;">
            ${renderCardBackdropHtml(item.backdrop_url)}

            <!-- SOL AFİŞ -->
            <div class="card-left-poster" style="width: 110px; height: 165px; flex-shrink: 0; position: relative; z-index: 2;">
                ${posterImgHtml(resolvePosterUrl(item), item.title, 'card-poster-img', false)}
            </div>

            <!-- SAĞ DETAYLAR VE BİREBİR AKORDEON PANELLERİ -->
            <div class="card-right-details" style="gap: 6px; position: relative; z-index: 2;">
                <h2 class="card-item-title" style="font-size: 1.1rem; margin: 0;">${item.title}</h2>

                <div class="card-badges-row">
                    <span class="badge-yellow"><i class="fa-solid fa-star"></i> ${item.rating || '8.5/10'}</span>
                    <span class="badge-purple"><i class="fa-solid fa-${isMovie ? 'clock' : 'film'}"></i> ${seasonsOrDuration}</span>
                    <span class="badge-cyan">🎭 ${genresText}</span>
                </div>

                <div class="card-platform-status" style="font-size: 0.8rem; margin-top: 4px;">
                    📺 ${formatPlatformLinks(item.platform, item.title)} | 📌 Durum: <strong style="color: #10b981;">${escapeHtml(statusText)}</strong>
                </div>

                <!-- AKORDEON MENÜLERİ (3. FOTOĞRAF BİREBİR - ÖZET VARSAYILAN KAPALI GELİR!) -->
                <div class="fav-accordion-details" style="margin: 6px 0;">
                    <!-- EFSANEVİ İKİLİ AI TAVSİYE - GİZLENDİ
                    ${item.duo ? `
                        <div class="fav-accordion-item">
                            <div class="fav-accordion-header" onclick="toggleFavAccordion('pref-duo-${item.id}')" style="padding: 6px 12px; font-size: 0.8rem;">
                                <i class="fa-solid fa-chevron-right" id="arrow-pref-duo-${item.id}"></i>
                                <span>👥 Efsanevi İkili: ${item.duo}</span>
                            </div>
                            <div id="body-pref-duo-${item.id}" class="fav-accordion-body" style="display: none; padding: 8px 12px; font-size: 0.8rem;">
                                ${item.duo_desc || 'Karakter ikilisi uyumu.'}
                            </div>
                        </div>
                    ` : ''}
                    -->

                    <div class="fav-accordion-item">
                        <div class="fav-accordion-header" onclick="toggleFavAccordion('pref-sum-${item.id}')" style="padding: 6px 12px; font-size: 0.8rem;">
                            <i class="fa-solid fa-chevron-right" id="arrow-pref-sum-${item.id}"></i>
                            <span>📝 Özet</span>
                        </div>
                        <!-- KULLANICI İSTEĞİ: ÖZET KAPALI GELİR (display: none) -->
                        <div id="body-pref-sum-${item.id}" class="fav-accordion-body" style="display: none; padding: 8px 12px; font-size: 0.8rem;">
                            ${item.summary || 'Özet bilgisi bulunmuyor.'}
                        </div>
                    </div>
                </div>

                <!-- GERİ AL BUTONU (3. FOTOĞRAFTAKİ BİREBİR PURPLE BUTON) -->
                <div style="margin-top: 6px;">
                    <button onclick="undoPreference('${item.id}', '${prefType}')" class="fav-remove-btn" style="background: linear-gradient(135deg, #a855f7 0%, #6366f1 100%); padding: 6px 16px; font-size: 0.8rem; border-radius: 8px;">
                        Geri Al
                    </button>
                </div>
            </div>
        </div>
    `;
}

async function submitFeedback() {
    const input = document.getElementById('feedback-text-input');
    if (!input) return;

    const message = input.value.trim();
    if (!message) {
        showToast('⚠️ Lütfen geri bildirim mesajınızı yazınız.', 2000);
        return;
    }

    const username = CURRENT_USER || 'Anonim';
    let savedRemote = false;
    try {
        const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
        const res = await fetch(`${baseUrl}/api/feedback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                username,
                mediaType: currentUniverse || 'SERIES'
            })
        });
        if (res.ok) savedRemote = true;
    } catch (e) {
        // offline
    }

    input.value = '';
    showToast(savedRemote
        ? '✅ Geri bildiriminiz kaydedildi. Teşekkür ederiz!'
        : '⚠️ Sunucuya ulaşılamadı; mesajınız kaydedilemedi. Lütfen tekrar deneyin.', 2200);
}

/* ==========================================================================
   🚩 HATAYI BİLDİR — Kart alanlarını tek tıkla işaretleyerek içerik hatası gönder
   ========================================================================== */
const ERROR_REPORT_FIELD_DEFS = {
    visual: [
        { id: 'poster', label: 'Afiş / Poster', icon: 'fa-image' },
        { id: 'trailer', label: 'Fragman', icon: 'fa-play' }
    ],
    info: [
        { id: 'title', label: 'Başlık', icon: 'fa-heading' },
        { id: 'slogan', label: 'Slogan', icon: 'fa-quote-left' },
        { id: 'rating', label: 'Puan', icon: 'fa-star' },
        { id: 'year', label: 'Yıl', icon: 'fa-calendar-days' },
        { id: 'platform', label: 'Platformlar', icon: 'fa-tv' },
        { id: 'status', label: 'Durum', icon: 'fa-circle-info' }
    ],
    seriesInfo: [
        { id: 'seasons', label: 'Sezon sayısı', icon: 'fa-layer-group' },
        { id: 'episodes', label: 'Bölüm sayısı', icon: 'fa-list-ol' },
        { id: 'ep_duration', label: 'Bölüm süresi', icon: 'fa-clock' }
    ],
    moviesInfo: [
        { id: 'duration', label: 'Film süresi', icon: 'fa-clock' }
    ],
    content: [
        { id: 'genres', label: 'Türler', icon: 'fa-masks-theater' },
        { id: 'summary', label: 'Özet', icon: 'fa-align-left' },
        { id: 'why_watch', label: 'Neden İzlemeli?', icon: 'fa-lightbulb' }
    ]
};

const ERROR_REPORT_FIELD_LABELS = {};
[
    ...ERROR_REPORT_FIELD_DEFS.visual,
    ...ERROR_REPORT_FIELD_DEFS.info,
    ...ERROR_REPORT_FIELD_DEFS.seriesInfo,
    ...ERROR_REPORT_FIELD_DEFS.moviesInfo,
    ...ERROR_REPORT_FIELD_DEFS.content
].forEach(f => { ERROR_REPORT_FIELD_LABELS[f.id] = f.label; });
ERROR_REPORT_FIELD_LABELS.other = 'Diğer';

const ERROR_REPORT_NOTE_MAX = 300;
let ERROR_REPORT_STATE = { itemId: null, itemTitle: '', mediaType: 'SERIES', posterUrl: '', selected: new Set() };
const ERROR_REPORT_COOLDOWN_MS = 20000;
const ERROR_REPORT_LAST_SENT = {};

function resolveItemForErrorReport(itemId) {
    const id = String(itemId || '');
    let resolvedType = 'SERIES';
    if (id.startsWith('movies_') || id.startsWith('movie_') || /^tt\d+/i.test(id)) {
        resolvedType = 'MOVIES';
    } else if (id.startsWith('series_')) {
        resolvedType = 'SERIES';
    } else if (typeof currentUniverse !== 'undefined' && currentUniverse === 'MOVIES') {
        resolvedType = 'MOVIES';
    }

    const seriesData = (typeof REAL_SERIES_DATA !== 'undefined' && REAL_SERIES_DATA)
        ? REAL_SERIES_DATA
        : (typeof SAMPLE_SERIES !== 'undefined' ? SAMPLE_SERIES : []);
    const moviesData = (typeof REAL_MOVIES_DATA !== 'undefined' && REAL_MOVIES_DATA)
        ? REAL_MOVIES_DATA
        : (typeof SAMPLE_MOVIES !== 'undefined' ? SAMPLE_MOVIES : []);

    const primary = resolvedType === 'MOVIES' ? moviesData : seriesData;
    const secondary = resolvedType === 'MOVIES' ? seriesData : moviesData;
    const libs = [
        ...(Array.isArray(USER_MOVIES_LIBRARY) ? USER_MOVIES_LIBRARY : []),
        ...(Array.isArray(USER_SERIES_LIBRARY) ? USER_SERIES_LIBRARY : [])
    ];

    let found = null;
    for (const pool of [primary, libs, secondary]) {
        if (!Array.isArray(pool)) continue;
        found = pool.find(d => d && String(d.id) === id);
        if (found) break;
    }

    if (found) {
        const fid = String(found.id || '');
        if (fid.startsWith('series_')) resolvedType = 'SERIES';
        else if (fid.startsWith('movies_') || fid.startsWith('movie_') || /^tt\d+/i.test(fid)) resolvedType = 'MOVIES';
    }

    const posterUrl = (found && (found.poster_url || found.afis_url))
        ? (found.poster_url || found.afis_url)
        : 'https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=200';

    return {
        item: found,
        title: (found && found.title) ? found.title : id,
        mediaType: resolvedType,
        posterUrl
    };
}

function getErrorReportGroupsForMedia(mediaType) {
    const infoExtra = mediaType === 'MOVIES'
        ? ERROR_REPORT_FIELD_DEFS.moviesInfo
        : ERROR_REPORT_FIELD_DEFS.seriesInfo;

    return [
        { title: 'Görsel Sorunları', fields: ERROR_REPORT_FIELD_DEFS.visual },
        { title: 'Künye Bilgileri', fields: [...ERROR_REPORT_FIELD_DEFS.info, ...infoExtra] },
        { title: 'İçerik Detayları', fields: ERROR_REPORT_FIELD_DEFS.content }
    ];
}

function renderErrorReportChip(field) {
    return `
        <button type="button" class="error-report-chip" data-field="${field.id}" onclick="toggleErrorReportField('${field.id}')" aria-pressed="false">
            <i class="fa-solid fa-check er-check" aria-hidden="true"></i>
            <i class="fa-solid ${field.icon} er-icon"></i>
            ${escapeHtml(field.label)}
        </button>
    `;
}

function updateErrorReportNoteCount() {
    const noteEl = document.getElementById('error-report-note');
    const countEl = document.getElementById('error-report-char-count');
    if (!noteEl || !countEl) return;
    const len = noteEl.value.length;
    countEl.textContent = `${len}/${ERROR_REPORT_NOTE_MAX}`;
    countEl.style.color = len >= ERROR_REPORT_NOTE_MAX ? '#f87171' : '#6b7280';
}

function updateErrorReportSelectionUI() {
    const count = ERROR_REPORT_STATE.selected ? ERROR_REPORT_STATE.selected.size : 0;
    const countEl = document.getElementById('error-report-selection-count');
    const submitBtn = document.getElementById('error-report-submit-btn');

    if (countEl) {
        if (count === 0) {
            countEl.textContent = 'Henüz alan seçilmedi';
            countEl.classList.add('is-empty');
        } else {
            countEl.textContent = `${count} alan seçildi`;
            countEl.classList.remove('is-empty');
        }
    }

    if (submitBtn) {
        const enabled = count > 0;
        submitBtn.disabled = !enabled;
        submitBtn.classList.toggle('is-disabled', !enabled);
    }
}

function openErrorReportModal(itemId) {
    if (!isUserLoggedInStrict()) {
        showToast('🔒 Hata bildirmek için önce giriş yap / kayıt ol.', 2800);
        if (typeof openAuthModal === 'function') {
            openAuthModal('LOGIN');
        } else if (typeof toggleAuthAccordion === 'function') {
            toggleAuthAccordion();
        }
        return;
    }

    const resolved = resolveItemForErrorReport(itemId);
    ERROR_REPORT_STATE = {
        itemId: String(itemId),
        itemTitle: resolved.title,
        mediaType: resolved.mediaType,
        posterUrl: resolved.posterUrl,
        selected: new Set()
    };

    const modal = document.getElementById('error-report-modal');
    const chipsEl = document.getElementById('error-report-chips');
    const subtitle = document.getElementById('error-report-modal-subtitle');
    const noteEl = document.getElementById('error-report-note');
    const thumbEl = document.getElementById('error-report-thumb');

    if (subtitle) {
        subtitle.textContent = `${resolved.title} — Nerede sorun var?`;
        subtitle.title = resolved.title;
    }
    if (thumbEl) {
        thumbEl.src = resolved.posterUrl;
        thumbEl.alt = resolved.title;
    }
    if (noteEl) {
        noteEl.value = '';
        noteEl.maxLength = ERROR_REPORT_NOTE_MAX;
    }
    updateErrorReportNoteCount();

    if (chipsEl) {
        const groups = getErrorReportGroupsForMedia(resolved.mediaType);
        chipsEl.innerHTML = groups.map(g => `
            <div class="error-report-group">
                <h4 class="error-report-group-title">${escapeHtml(g.title)}</h4>
                <div class="error-report-group-chips">
                    ${g.fields.map(renderErrorReportChip).join('')}
                </div>
            </div>
        `).join('');
    }

    updateErrorReportSelectionUI();

    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        requestAnimationFrame(() => {
            modal.classList.add('is-open');
        });
    }
}

function closeErrorReportModal() {
    const modal = document.getElementById('error-report-modal');
    if (!modal) return;

    modal.classList.remove('is-open');
    setTimeout(() => {
        modal.style.display = 'none';
        document.body.style.overflow = '';
    }, 200);
    ERROR_REPORT_STATE.selected = new Set();
}

function toggleErrorReportField(fieldId) {
    if (!ERROR_REPORT_STATE.selected) ERROR_REPORT_STATE.selected = new Set();
    if (ERROR_REPORT_STATE.selected.has(fieldId)) {
        ERROR_REPORT_STATE.selected.delete(fieldId);
    } else {
        ERROR_REPORT_STATE.selected.add(fieldId);
    }

    const chip = document.querySelector(`#error-report-chips .error-report-chip[data-field="${fieldId}"]`);
    if (chip) {
        const on = ERROR_REPORT_STATE.selected.has(fieldId);
        chip.classList.toggle('is-selected', on);
        chip.setAttribute('aria-pressed', on ? 'true' : 'false');
    }
    updateErrorReportSelectionUI();
}

function readLocalErrorReports() {
    try {
        return JSON.parse(localStorage.getItem('MATRIX_CONTENT_ERROR_REPORTS') || '[]');
    } catch (e) {
        return [];
    }
}

function writeLocalErrorReport(report) {
    const list = readLocalErrorReports();
    list.unshift(report);
    localStorage.setItem('MATRIX_CONTENT_ERROR_REPORTS', JSON.stringify(list.slice(0, 200)));
}

async function submitErrorReport() {
    const { itemId, itemTitle, mediaType, selected } = ERROR_REPORT_STATE;
    if (!itemId) return;

    const fields = Array.from(selected || []);
    if (fields.length === 0) {
        showToast('⚠️ Lütfen en az bir alan seç.', 2000);
        updateErrorReportSelectionUI();
        return;
    }

    const now = Date.now();
    if (ERROR_REPORT_LAST_SENT[itemId] && (now - ERROR_REPORT_LAST_SENT[itemId]) < ERROR_REPORT_COOLDOWN_MS) {
        showToast('⏳ Bu yapım için az önce bildirim gönderdin. Biraz bekle.', 2200);
        return;
    }

    const noteEl = document.getElementById('error-report-note');
    const note = noteEl ? noteEl.value.trim().slice(0, ERROR_REPORT_NOTE_MAX) : '';
    const username = (CURRENT_USER && CURRENT_USER !== 'Kullanıcı') ? CURRENT_USER : null;
    const submitBtn = document.getElementById('error-report-submit-btn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.classList.add('is-disabled');
        submitBtn.style.opacity = '0.7';
    }

    const payload = { itemId, itemTitle, mediaType, fields, note, username };
    let savedRemote = false;

    try {
        const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
        const res = await fetch(`${baseUrl}/api/error-reports`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) savedRemote = true;
    } catch (e) {
        // offline / backend down → local fallback
    }

    const localReport = {
        id: `local_${Date.now()}`,
        itemId,
        itemTitle,
        mediaType,
        fields,
        note,
        username,
        status: 'open',
        createdAt: new Date().toISOString(),
        savedRemote
    };
    writeLocalErrorReport(localReport);
    ERROR_REPORT_LAST_SENT[itemId] = now;

    if (submitBtn) {
        submitBtn.style.opacity = '';
    }

    closeErrorReportModal();
    showToast(savedRemote
        ? '✅ Teşekkürler! Hatayı inceleyeceğiz.'
        : '✅ Bildirim kaydedildi (çevrimdışı yedek).', 2400);
}

async function loadErrorReportsInbox() {
    // Eski public inbox kaldırıldı — yönetim paneli kullanılır
    if (IS_ADMIN_SESSION) renderAdminInboxUI(true);
}

async function updateErrorReportStatus(reportId, status) {
    const res = await adminAuthorizedFetch(`/api/error-reports/${reportId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status })
    });
    if (!res.ok) {
        showToast('⚠️ Durum güncellenemedi.', 2000);
        return;
    }
    showToast('✅ Rapor durumu güncellendi.', 1600);
    renderAdminInboxUI(true);
}

function undoPreference(itemId, type) {
    const isMovie = (currentUniverse === 'MOVIES');

    if (type === 'LIKED') {
        if (isMovie) LIKED_MOVIES_IDS = LIKED_MOVIES_IDS.filter(id => id !== itemId);
        else LIKED_SERIES_IDS = LIKED_SERIES_IDS.filter(id => id !== itemId);
        showToast('↩️ Beğeni tercihi geri alındı.', 1800);
    } else {
        if (isMovie) HIDDEN_MOVIES_IDS = HIDDEN_MOVIES_IDS.filter(id => id !== itemId);
        else HIDDEN_SERIES_IDS = HIDDEN_SERIES_IDS.filter(id => id !== itemId);
        showToast('↩️ Gizleme tercihi geri alındı.', 1800);
    }

    renderFeedbackUI();
}

function goToLikedPage(page) {
    const target = parseInt(page, 10);
    if (!Number.isFinite(target) || target < 1 || target === currentLikedPage) return;
    currentLikedPage = target;
    renderFeedbackUI();
}

function goToHiddenPage(page) {
    const target = parseInt(page, 10);
    if (!Number.isFinite(target) || target < 1 || target === currentHiddenPage) return;
    currentHiddenPage = target;
    renderFeedbackUI();
}

function changeLikedPage(delta) {
    goToLikedPage(currentLikedPage + delta);
}

function changeHiddenPage(delta) {
    goToHiddenPage(currentHiddenPage + delta);
}

function resetFusionUI() {
    // Anlık sonuç grid'ini temizle; tamamlanan füzyon bölümüne dokunma (F5 / sekme geçişi)
    const resultsWrapper = document.getElementById('fusion-results-wrapper');
    const cardsGrid = document.getElementById('fusion-cards-grid');

    if (cardsGrid) cardsGrid.innerHTML = '';
    if (resultsWrapper) resultsWrapper.style.display = 'none';
}

function toggleFusionAccordion() {
    const cardsGrid = document.getElementById('fusion-cards-grid');
    const arrow = document.getElementById('arrow-fusion-accordion');
    if (!cardsGrid) return;

    if (cardsGrid.style.display === 'none') {
        cardsGrid.style.display = 'grid';
        if (arrow) arrow.className = 'fa-solid fa-chevron-down';
    } else {
        cardsGrid.style.display = 'none';
        if (arrow) arrow.className = 'fa-solid fa-chevron-right';
    }
}

function toggleCompletedFusionBlock(inviteId) {
    const id = Number(inviteId);
    if (!Number.isFinite(id)) return;
    const grid = document.getElementById(`fusion-completed-grid-${id}`);
    const arrow = document.getElementById(`arrow-fusion-completed-${id}`);
    if (!grid) return;

    const willExpand = grid.style.display === 'none' || !grid.style.display;
    grid.style.display = willExpand ? 'grid' : 'none';
    if (arrow) arrow.className = willExpand ? 'fa-solid fa-chevron-down' : 'fa-solid fa-chevron-right';
}

function upsertCompletedFusionInvite(invite) {
    if (!invite || !invite.id) return;
    const list = Array.isArray(COMPLETED_FUSION_INVITES) ? COMPLETED_FUSION_INVITES.slice() : [];
    const idx = list.findIndex(x => Number(x.id) === Number(invite.id));
    if (idx >= 0) list[idx] = { ...list[idx], ...invite };
    else list.unshift(invite);
    COMPLETED_FUSION_INVITES = list;
    if (CURRENT_USER) {
        try { saveUserData(CURRENT_USER); } catch (e) { /* ignore */ }
    }
}

function normalizeFusionRecItems(recs, universe) {
    const isMovie = String(universe || '').toUpperCase() === 'MOVIES';
    const dataset = isMovie
        ? ((typeof MOVIES_DATASET !== 'undefined' && MOVIES_DATASET) || [])
        : ((typeof SERIES_DATASET !== 'undefined' && SERIES_DATASET) || (typeof getFusionDataset === 'function' ? getFusionDataset() : []) || []);
    return (recs || []).slice(0, 5).map(r => {
        const full = (typeof getMediaItemFullDetails === 'function')
            ? getMediaItemFullDetails(r, dataset)
            : (dataset.find(d => String(d.id) === String(r.id)) || r);
        return {
            ...(full || {}),
            ...r,
            id: r.id,
            title: r.title || (full && full.title),
            poster_url: r.poster_url || (full && (full.poster_url || full.afis_url)),
            summary: r.summary || (full && (full.summary || full.ozet)),
            rating: r.rating || (full && full.rating),
            platform: r.platform || (full && full.platform),
            status: r.status || (full && (full.status || full.status_text)),
            backdrop_url: r.backdrop_url || (full && full.backdrop_url) || '',
            trailer_dub_url: r.trailer_dub_url || (full && full.trailer_dub_url) || '',
            trailer_sub_url: r.trailer_sub_url || (full && full.trailer_sub_url) || '',
            aiMatchScore: r.aiMatchScore || 90,
            aiReason: r.aiReason || ''
        };
    }).filter(x => x && x.id);
}

function personalizeFusionReasonText(rawReason, nameA, nameB) {
    let text = String(rawReason || '').trim();
    if (!text) return '';
    const a = String(nameA || '').trim();
    const b = String(nameB || '').trim();
    if (a) {
        text = text
            .replace(/\bA'nın\b/g, `${a}'nın`)
            .replace(/\bA'ya\b/g, `${a}'ya`)
            .replace(/\bA'yı\b/g, `${a}'yı`)
            .replace(/\bA ile\b/g, `${a} ile`)
            .replace(/\bA'nın\b/gi, `${a}'nın`);
        // Tek harf A (kelime sınırı) — dikkatli: başlık/cümle başı
        text = text.replace(/(^|[^\wçğıöşüÇĞİÖŞÜ])A([^\wçğıöşüÇĞİÖŞÜ]|$)/g, `$1${a}$2`);
    }
    if (b) {
        text = text
            .replace(/\bB'nin\b/g, `${b}'nın`)
            .replace(/\bB'ya\b/g, `${b}'ya`)
            .replace(/\bB'yı\b/g, `${b}'yı`)
            .replace(/\bB ile\b/g, `${b} ile`);
        text = text.replace(/(^|[^\wçğıöşüÇĞİÖŞÜ])B([^\wçğıöşüÇĞİÖŞÜ]|$)/g, `$1${b}$2`);
    }
    // Eski teknik ifadeleri yumuşat
    text = text
        .replace(/AI\s*Cosine\s*Uyum/gi, 'Yapay Zeka Uyumu')
        .replace(/Cosine\s*Uyum/gi, 'Yapay Zeka Uyumu')
        .replace(/Cosine\s*Similarity/gi, 'Yapay Zeka')
        .replace(/cosine/gi, 'yapay zeka uyumu');
    return text.trim();
}

function buildFusionRecCardsHtml(items, isMovie, nameA, nameB) {
    const aName = nameA || CURRENT_USER || 'Siz';
    const bName = nameB || 'arkadaşınız';
    return (items || []).map(item => {
        const score = item.aiMatchScore || 90;
        const personalized = personalizeFusionReasonText(item.aiReason, aName, bName);
        const reason = personalized
            ? `💡 <strong>İkinizin ortak zevkine göre şunu önerdik:</strong> ${escapeHtml(personalized)}`
            : `💡 <strong>İkinizin ortak zevkine göre şunu önerdik.</strong> ${escapeHtml(aName)} ve ${escapeHtml(bName)} zevklerinin kesişimine yakın bir yapım.`;
        const card = (typeof buildAICardHTML === 'function')
            ? buildAICardHTML(item, score, reason, isMovie)
            : `<div class="media-horizontal-card"><h3>${escapeHtml(item.title || item.id)}</h3></div>`;
        return `<div id="fusion-card-${escapeHtml(String(item.id))}" class="fusion-rec-card-wrap">${card}</div>`;
    }).join('');
}

/** Sunucu/local cache yoksa bir kez hesapla, kaydet; varsa GPT'yi tekrar çağırma. */
async function ensureFusionResultsComputed(invite) {
    if (!invite || !invite.id) return invite;

    if (Array.isArray(invite.results) && invite.results.length) {
        saveFusionResultsLocal(invite.id, {
            inviteId: invite.id,
            recommendations: invite.results,
            universe: invite.universe,
            from: invite.from,
            to: invite.to
        });
        return invite;
    }

    const cached = loadFusionResultsLocal(invite.id);
    if (cached && Array.isArray(cached.recommendations) && cached.recommendations.length) {
        try {
            await socialApiFetch(`/api/fusion/${invite.id}/results`, {
                method: 'POST',
                body: JSON.stringify({ recommendations: cached.recommendations })
            });
        } catch (e) { /* ignore */ }
        return { ...invite, results: cached.recommendations };
    }

    const idsA = invite.senderSelections || [];
    const idsB = invite.receiverSelections || [];
    if (idsA.length !== 5 || idsB.length !== 5) return invite;

    const universe = String(invite.universe || currentUniverse || 'MOVIES').toUpperCase() === 'SERIES' ? 'SERIES' : 'MOVIES';
    const me = String(CURRENT_USER || '').toLowerCase();
    const myLib = getActiveLibraryIdsForFusion();
    let fullA = invite.senderLibrary || [];
    let fullB = invite.receiverLibrary || [];
    if (String(invite.from || '').toLowerCase() === me && myLib.length) fullA = myLib;
    if (String(invite.to || '').toLowerCase() === me && myLib.length) fullB = myLib;
    if (!fullA.length) fullA = idsA;
    if (!fullB.length) fullB = idsB;

    let fusionItems = [];
    try {
        const backend = await getSocialRecommendationsViaBackend(idsA, idsB, universe, {
            userASelected5: idsA,
            userBSelected5: idsB,
            userAFullLibrary: fullA,
            userBFullLibrary: fullB,
            userAName: invite.from || '',
            userBName: invite.to || ''
        });
        const recs = (backend && (backend.recommendations || backend.results)) || [];
        fusionItems = normalizeFusionRecItems(recs, universe);
    } catch (e) { /* ignore */ }

    if (!fusionItems.length) {
        const dataset = (typeof getFusionDataset === 'function' ? getFusionDataset() : []) || [];
        const excl = new Set([...fullA, ...fullB, ...idsA, ...idsB].map(String));
        fusionItems = dataset
            .filter(d => d && d.id && !excl.has(String(d.id)))
            .sort(() => 0.5 - Math.random())
            .slice(0, 5)
            .map(item => ({ ...item, aiMatchScore: Math.floor(88 + Math.random() * 10), aiReason: '' }));
    }

    if (fusionItems.length) {
        saveFusionResultsLocal(invite.id, {
            inviteId: invite.id,
            recommendations: fusionItems,
            universe,
            from: invite.from,
            to: invite.to
        });
        try {
            const saveRes = await socialApiFetch(`/api/fusion/${invite.id}/results`, {
                method: 'POST',
                body: JSON.stringify({ recommendations: fusionItems })
            });
            if (saveRes.ok && saveRes.data && saveRes.data.invite) {
                return saveRes.data.invite;
            }
        } catch (e) { /* ignore */ }
        return { ...invite, results: fusionItems };
    }
    return invite;
}

/** Tamamlanan füzyonları kalıcı bölümde göster (her iki kullanıcı). */
async function renderCompletedFusions() {
    const section = document.getElementById('fusion-completed-section');
    const list = document.getElementById('fusion-completed-list');
    if (!section || !list) return;

    let invites = (COMPLETED_FUSION_INVITES || []).filter(x => x && x.status === 'tamamlandi');
    if (!invites.length) {
        section.style.display = 'none';
        list.innerHTML = '';
        return;
    }

    // Sunucu sonuçsuzsa (ephemeral wipe) localStorage yedeklerini birleştir — GPT yeniden çağrılmaz
    const enriched = invites.slice(0, 5).map(inv => {
        if (inv.results && inv.results.length) return inv;
        const local = loadFusionResultsLocal(inv.id);
        if (local && Array.isArray(local.recommendations) && local.recommendations.length) {
            return { ...inv, results: local.recommendations };
        }
        return inv;
    });

    const me = String(CURRENT_USER || '').toLowerCase();
    const blocks = enriched.map(inv => {
        const peer = String(inv.from || '').toLowerCase() === me ? inv.to : inv.from;
        const uni = String(inv.universe || '').toUpperCase() === 'SERIES' ? 'SERIES' : 'MOVIES';
        const isMovie = uni === 'MOVIES';
        const nameA = inv.from || CURRENT_USER || 'Kullanıcı';
        const nameB = inv.to || peer || 'Arkadaş';
        const items = normalizeFusionRecItems(inv.results || [], uni);
        const cards = items.length
            ? buildFusionRecCardsHtml(items, isMovie, nameA, nameB)
            : `<div style="color:#9ca3af;font-size:0.9rem;">Sonuçlar henüz hazır değil. Karşı taraf kabul ettiğinde veya sayfayı yenilediğinizde görünecek.</div>`;
        const ov = inv.overlap && inv.overlap.count > 0
            ? `<div style="color:#fbbf24;font-size:0.82rem;margin-bottom:8px;">⚠️ ${inv.overlap.count} ortak seçim vardı.</div>`
            : '';
        const inviteId = Number(inv.id);
        return `
            <div class="fusion-completed-block" data-fusion-id="${inviteId}" style="background:rgba(0,0,0,0.25);border:1px solid rgba(236,72,153,0.35);border-radius:14px;padding:0;overflow:hidden;">
                <div class="fav-accordion-header" onclick="toggleCompletedFusionBlock(${inviteId})" style="background:rgba(236,72,153,0.12);border:none;border-bottom:1px solid rgba(236,72,153,0.25);padding:14px 16px;border-radius:14px 14px 0 0;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:10px;">
                    <div style="color:#fff;font-weight:800;font-size:1rem;">
                        <i class="fa-solid fa-user-group" style="color:#ec4899;"></i>
                        ${escapeHtml(peer || 'Arkadaş')} ile ortak öneriler
                        <span style="color:#9ca3af;font-weight:600;font-size:0.82rem;"> · ${isMovie ? 'Film' : 'Dizi'} · ${items.length} sonuç — görmek için tıkla</span>
                    </div>
                    <i id="arrow-fusion-completed-${inviteId}" class="fa-solid fa-chevron-right"></i>
                </div>
                <div style="padding:16px;">
                    ${ov}
                    <div id="fusion-completed-grid-${inviteId}" class="fusion-cards-grid" style="display:none;grid-template-columns:1fr;gap:16px;">
                        ${cards}
                    </div>
                </div>
            </div>
        `;
    }).join('');

    list.innerHTML = blocks;
    section.style.display = 'flex';

    const resultsWrapper = document.getElementById('fusion-results-wrapper');
    if (resultsWrapper) resultsWrapper.style.display = 'none';
}

// 🧠 ORTAK ZEVK FÜZYONU — backend cosine (+ üye GPT notları), yoksa yerel fallback
async function runJointTasteFusion(idsAOverride, idsBOverride, inviteMeta) {
    const invite = inviteMeta && inviteMeta.id
        ? await ensureFusionResultsComputed({
            ...inviteMeta,
            senderSelections: idsAOverride || inviteMeta.senderSelections,
            receiverSelections: idsBOverride || inviteMeta.receiverSelections
        })
        : null;

    if (invite) {
        upsertCompletedFusionInvite(invite);
        await renderCompletedFusions();
        showToast('🎉 Ortak Zevk Füzyonu hazır!', 2200);
        const section = document.getElementById('fusion-completed-section');
        if (section) section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        return;
    }

    // Legacy: invite yoksa eski grid'e boya (nadir)
    const dataset = getFusionDataset();
    const resultsWrapper = document.getElementById('fusion-results-wrapper');
    const cardsGrid = document.getElementById('fusion-cards-grid');
    const isMovie = (currentUniverse === 'MOVIES');
    const universe = isMovie ? 'MOVIES' : 'SERIES';
    const libA = (typeof getActiveLibrary === 'function' ? getActiveLibrary() : []) || [];
    const idsA = (Array.isArray(idsAOverride) && idsAOverride.length)
        ? idsAOverride
        : readFusionSlotValues('.fusion-select-a');
    const idsB = (Array.isArray(idsBOverride) && idsBOverride.length) ? idsBOverride : [];
    if (!idsA.length || !idsB.length) {
        showToast('⚠️ Füzyon için her iki tarafın da 5 seçimi gerekli.', 2800);
        return;
    }
    const fullA = libA.map(i => i && i.id).filter(Boolean);
    const fullB = idsB;

    if (cardsGrid) {
        cardsGrid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:28px;color:#c084fc;">🧠 Ortak zevk uyumu hesaplanıyor...</div>`;
    }
    if (resultsWrapper) resultsWrapper.style.display = 'flex';

    let fusionItems = [];
    const legacyNameA = (inviteMeta && inviteMeta.from) || CURRENT_USER || 'Siz';
    const legacyNameB = (inviteMeta && inviteMeta.to) || 'Arkadaş';
    try {
        const backend = await getSocialRecommendationsViaBackend(idsA, idsB, universe, {
            userASelected5: idsA,
            userBSelected5: idsB,
            userAFullLibrary: fullA.length ? fullA : idsA,
            userBFullLibrary: fullB,
            userAName: legacyNameA,
            userBName: legacyNameB
        });
        const recs = (backend && (backend.recommendations || backend.results)) || [];
        fusionItems = normalizeFusionRecItems(recs, universe);
    } catch (e) {}

    if (!fusionItems.length) {
        const excl = new Set([...(fullA.length ? fullA : idsA), ...fullB].map(String));
        fusionItems = [...dataset]
            .filter(d => d && d.id && !excl.has(String(d.id)))
            .sort(() => 0.5 - Math.random())
            .slice(0, 5)
            .map(item => ({ ...item, aiMatchScore: Math.floor(88 + Math.random() * 10), aiReason: '' }));
    }

    if (cardsGrid) {
        cardsGrid.innerHTML = buildFusionRecCardsHtml(fusionItems, isMovie, legacyNameA, legacyNameB);
        cardsGrid.style.display = 'grid';
    }
    if (resultsWrapper) {
        resultsWrapper.style.display = 'flex';
        resultsWrapper.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    showToast('🎉 5 adet Ortak Zevk Füzyonu tavsiyesi başarıyla hesaplandı!', 2200);
}

/* ==========================================================================
   📌 BAŞLIK: KULLANICI KİMLİK DOĞRULAMA VE OTURUM MOTORU (AUTH & REMEMBER ME)
   ========================================================================== */
let CURRENT_USER = null;
let IS_ADMIN_SESSION = false;

let REGISTERED_ACCOUNTS = [
    { username: 'sancopancoo', password: 'password123', email: 'sanco@example.com' },
    { username: 'adm', password: '123', email: 'admin@dizimibul.com' },
    { username: 'ahmet_matrix', password: '123', email: 'ahmet@matrix.com' },
    { username: 'zeynep_dizi', password: '123', email: 'zeynep@matrix.com' }
];

function loadRegisteredAccounts() {
    try {
        const saved = localStorage.getItem('MATRIX_REGISTERED_ACCOUNTS');
        if (saved) {
            const list = JSON.parse(saved);
            if (Array.isArray(list)) {
                list.forEach(acc => {
                    if (acc && acc.username && !REGISTERED_ACCOUNTS.some(a => a.username.toLowerCase() === acc.username.toLowerCase())) {
                        REGISTERED_ACCOUNTS.push(acc);
                    }
                });
            }
        }
    } catch (e) {
        console.warn('Registered accounts load warning:', e);
    }
}

function saveRegisteredAccounts() {
    try {
        localStorage.setItem('MATRIX_REGISTERED_ACCOUNTS', JSON.stringify(REGISTERED_ACCOUNTS));
    } catch (e) {
        console.warn('Registered accounts save warning:', e);
    }
}

function toggleAuthAccordion() {
    const authBody = document.getElementById('auth-accordion-body');
    const arrowIcon = document.getElementById('auth-accordion-arrow');
    if (!authBody) return;

    if (authBody.style.display === 'none') {
        authBody.style.display = 'flex';
        if (arrowIcon) arrowIcon.className = 'fa-solid fa-chevron-down';
    } else {
        authBody.style.display = 'none';
        if (arrowIcon) arrowIcon.className = 'fa-solid fa-chevron-right';
    }
}

function switchAuthTab(tabName) {
    const loginForm = document.getElementById('form-auth-login');
    const regForm = document.getElementById('form-auth-register');
    const btnLogin = document.getElementById('tab-btn-login');
    const btnReg = document.getElementById('tab-btn-register');

    if (!loginForm || !regForm) return;

    if (tabName === 'LOGIN') {
        loginForm.style.display = 'flex';
        regForm.style.display = 'none';
        if (btnLogin) {
            btnLogin.className = 'primary-gradient-btn';
            btnLogin.style.background = '';
        }
        if (btnReg) {
            btnReg.className = 'secondary-gradient-btn';
        }
    } else {
        loginForm.style.display = 'none';
        regForm.style.display = 'flex';
        if (btnReg) {
            btnReg.className = 'primary-gradient-btn';
        }
        if (btnLogin) {
            btnLogin.className = 'secondary-gradient-btn';
        }
    }
}

function togglePasswordVisibility() {
    const pwdInput = document.getElementById('auth-login-password');
    const icon = document.getElementById('toggle-pwd-icon');
    if (!pwdInput || !icon) return;

    if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        icon.className = 'fa-solid fa-eye-slash';
    } else {
        pwdInput.type = 'password';
        icon.className = 'fa-solid fa-eye';
    }
}

async function performRegister() {
    loadRegisteredAccounts();
    const usernameInput = document.getElementById('auth-reg-username');
    const emailInput = document.getElementById('auth-reg-email');
    const pwdInput = document.getElementById('auth-reg-password');
    const secInput = document.getElementById('auth-reg-security');

    const username = usernameInput ? usernameInput.value.trim() : '';
    const email = emailInput ? emailInput.value.trim() : '';
    const password = pwdInput ? pwdInput.value : '';
    const security = secInput ? secInput.value.trim() : '';

    if (!username) {
        showToast('⚠️ Lütfen bir kullanıcı adı giriniz!', 2000);
        return;
    }

    if (REGISTERED_ACCOUNTS.some(a => a.username.toLowerCase() === username.toLowerCase())) {
        showToast('⚠️ Bu kullanıcı adı zaten sistemde kayıtlı! Lütfen başka bir ad seçiniz.', 2500);
        return;
    }

    if (!password || password.length < 6) {
        showToast('⚠️ Şifreniz en az 6 karakter olmalıdır!', 2200);
        return;
    }

    if (security !== '8') {
        showToast('⚠️ Doğrulama sorusunun cevabı hatalı! (5 + 3 = 8 olmalıdır)', 2500);
        return;
    }

    // E-posta opsiyonel — boşsa sunucu placeholder üretir
    const emailForServer = email || `${username.toLowerCase()}@local.dizimibul`;

    // Önce sunucuya yaz — arkadaş ekleme / ortak özellikler için zorunlu
    let serverOk = false;
    let serverMsg = '';
    try {
        const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
        const res = await fetch(`${baseUrl}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, email: emailForServer })
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.ok !== false) {
            serverOk = true;
            if (data.token) {
                localStorage.setItem(`MATRIX_SIGNED_TOKEN_${username.toLowerCase()}`, data.token);
            }
        } else {
            serverMsg = data.error || `Sunucu kayıt hatası (${res.status})`;
        }
    } catch (e) {
        serverMsg = 'Sunucu API erişilemiyor (Render kapalı veya yanlış URL).';
    }

    if (!serverOk) {
        showToast(`⚠️ Kayıt sunucuya yazılamadı: ${serverMsg}`, 4500);
        return;
    }

    // Sunucu OK → yerel yedek
    const newAcc = { username, password, email: email || emailForServer };
    REGISTERED_ACCOUNTS.push(newAcc);
    saveRegisteredAccounts();

    if (typeof REGISTERED_USERS !== 'undefined' && !REGISTERED_USERS.some(u => String(u).toLowerCase() === username.toLowerCase())) {
        REGISTERED_USERS.push(username);
    }

    showToast('🎉 Kayıt başarılı! Hesap sunucuya kaydedildi.', 2500);

    if (usernameInput) usernameInput.value = '';
    if (emailInput) emailInput.value = '';
    if (pwdInput) pwdInput.value = '';
    if (secInput) secInput.value = '';

    const loginUserField = document.getElementById('auth-login-username');
    if (loginUserField) loginUserField.value = username;

    switchAuthTab('LOGIN');
}

async function performLogin() {
    loadRegisteredAccounts();
    const userField = document.getElementById('auth-login-username');
    const pwdField = document.getElementById('auth-login-password');
    const remCheck = document.getElementById('auth-remember-me');

    const username = userField ? userField.value.trim() : '';
    const password = pwdField ? pwdField.value : '';
    const rememberMe = remCheck ? remCheck.checked : false;

    if (!username || !password) {
        showToast('⚠️ Kullanıcı adı ve şifre zorunludur!', 2000);
        return;
    }

    const acc = REGISTERED_ACCOUNTS.find(a => a.username.toLowerCase() === username.toLowerCase() && a.password === password);

    if (!acc) {
        showToast('⚠️ Kullanıcı adı veya şifre hatalı!', 2200);
        return;
    }

    CURRENT_USER = acc.username;

    // Sunucu Tarafı İmzalı Token Al (+ DB'ye köprüle; arkadaşlık için şart)
    let serverSynced = false;
    try {
        const baseUrl = (typeof API_BASE_URL !== 'undefined' && API_BASE_URL) ? API_BASE_URL : 'http://localhost:4000';
        const res = await fetch(`${baseUrl}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: acc.username, password: acc.password, email: acc.email || '' })
        });
        if (res.ok) {
            const data = await res.json();
            if (data.token) {
                localStorage.setItem(`MATRIX_SIGNED_TOKEN_${acc.username.toLowerCase()}`, data.token);
                serverSynced = true;
            }
            setAdminSessionFlag(!!data.isAdmin);
            await refreshAdminSessionFromServer();
        }
    } catch(e) {}

    if (rememberMe) {
        localStorage.setItem('MATRIX_SAVED_USER', JSON.stringify({ username: acc.username, password: acc.password }));
    } else {
        localStorage.removeItem('MATRIX_SAVED_USER');
    }

    if (serverSynced) {
        showToast(`👋 Hoş geldin, ${acc.username}! Giriş yapıldı.`, 2200);
    } else {
        showToast(`👋 Hoş geldin, ${acc.username}! (Sunucu senkronu yok — arkadaş ekleme için API gerekli)`, 3200);
    }
    updateAuthUI();
}

function performLogout() {
    const prevUser = CURRENT_USER;
    CURRENT_USER = null;
    IS_ADMIN_SESSION = false;
    if (prevUser && prevUser !== 'Kullanıcı') {
        sessionStorage.removeItem(`MATRIX_ADMIN_${prevUser.toLowerCase()}`);
    }
    localStorage.removeItem('MATRIX_SAVED_USER');
    resetUserDataToDefaults();
    applyAdminNavVisibility();
    showToast('🚪 Oturum başarıyla kapatıldı.', 2000);
    updateAuthUI();
}

function saveUserData(username) {
    if (!username) return;

    const dataObj = {
        USER_SERIES_LIBRARY: USER_SERIES_LIBRARY,
        USER_MOVIES_LIBRARY: USER_MOVIES_LIBRARY,
        USER_FAVORITES: USER_FAVORITES,
        USER_FRIENDS: USER_FRIENDS,
        PENDING_REQUESTS: PENDING_REQUESTS,
        PENDING_FUSION_REQUESTS: PENDING_FUSION_REQUESTS,
        OUTGOING_FUSION_REQUESTS: OUTGOING_FUSION_REQUESTS,
        COMPLETED_FUSION_INVITES: COMPLETED_FUSION_INVITES,
        LIKED_SERIES_IDS: LIKED_SERIES_IDS,
        LIKED_MOVIES_IDS: LIKED_MOVIES_IDS,
        HIDDEN_SERIES_IDS: HIDDEN_SERIES_IDS,
        HIDDEN_MOVIES_IDS: HIDDEN_MOVIES_IDS
    };

    localStorage.setItem(`MATRIX_USER_DATA_${username.toLowerCase()}`, JSON.stringify(dataObj));
}

function loadUserData(username) {
    if (!username || username === 'Kullanıcı') return;

    // 🔒 GÜVENLİK: Giriş yapmadan önce eklenen taslak yapımları koru ve hesaba birleştir!
    const draftSeriesLib = [...USER_SERIES_LIBRARY];
    const draftMoviesLib = [...USER_MOVIES_LIBRARY];
    const draftFavorites = [...USER_FAVORITES];

    const savedStr = localStorage.getItem(`MATRIX_USER_DATA_${username.toLowerCase()}`);
    if (savedStr) {
        try {
            const data = JSON.parse(savedStr);
            if (data) {
                if (data.USER_SERIES_LIBRARY) USER_SERIES_LIBRARY = data.USER_SERIES_LIBRARY;
                if (data.USER_MOVIES_LIBRARY) USER_MOVIES_LIBRARY = data.USER_MOVIES_LIBRARY;
                if (data.USER_FAVORITES) USER_FAVORITES = data.USER_FAVORITES;
                if (data.USER_FRIENDS) USER_FRIENDS = data.USER_FRIENDS;
                if (data.PENDING_REQUESTS) PENDING_REQUESTS = normalizePendingFriendList(data.PENDING_REQUESTS);
                if (data.PENDING_FUSION_REQUESTS) PENDING_FUSION_REQUESTS = data.PENDING_FUSION_REQUESTS;
                if (data.OUTGOING_FUSION_REQUESTS) OUTGOING_FUSION_REQUESTS = data.OUTGOING_FUSION_REQUESTS;
                if (data.COMPLETED_FUSION_INVITES) COMPLETED_FUSION_INVITES = data.COMPLETED_FUSION_INVITES;
                if (data.LIKED_SERIES_IDS) LIKED_SERIES_IDS = data.LIKED_SERIES_IDS;
                if (data.LIKED_MOVIES_IDS) LIKED_MOVIES_IDS = data.LIKED_MOVIES_IDS;
                if (data.HIDDEN_SERIES_IDS) HIDDEN_SERIES_IDS = data.HIDDEN_SERIES_IDS;
                if (data.HIDDEN_MOVIES_IDS) HIDDEN_MOVIES_IDS = data.HIDDEN_MOVIES_IDS;
            }
        } catch (e) {
            console.error('Error parsing user data:', e);
        }
    }

    // Birleştirme (Draft + Account Merge)
    draftSeriesLib.forEach(item => {
        if (item && item.id && !USER_SERIES_LIBRARY.some(i => i.id === item.id)) {
            USER_SERIES_LIBRARY.push(item);
        }
    });
    draftMoviesLib.forEach(item => {
        if (item && item.id && !USER_MOVIES_LIBRARY.some(i => i.id === item.id)) {
            USER_MOVIES_LIBRARY.push(item);
        }
    });
    draftFavorites.forEach(id => {
        if (id && !USER_FAVORITES.includes(id)) {
            USER_FAVORITES.push(id);
        }
    });

    saveUserData(username);
}

function openAuthModal(targetTab = 'LOGIN') {
    // 1. Sidebar kapalı veya gizliyse güvenli bir şekilde toggleSidebar çağırarak aç
    const sidebar = document.getElementById('filter-sidebar');
    const isHidden = !sidebar || sidebar.classList.contains('collapsed') || sidebar.style.display === 'none';
    if (isHidden) {
        toggleSidebar();
    }

    // 2. Akordeonu aç ve görünür yap
    const authBody = document.getElementById('auth-accordion-body');
    const arrowIcon = document.getElementById('auth-accordion-arrow');
    if (authBody) {
        authBody.style.display = 'flex';
        if (arrowIcon) arrowIcon.className = 'fa-solid fa-chevron-down';
    }

    switchAuthTab(targetTab);

    // 3. Evrene (Film / Dizi) göre dinamik tema parıltısı ve vurgulama
    const isMovie = (currentUniverse === 'MOVIES');
    const glowColor = isMovie ? 'rgba(239, 68, 68, 0.95)' : 'rgba(14, 165, 233, 0.95)';
    const borderColor = isMovie ? '#ef4444' : '#0ea5e9';

    const authPanel = document.getElementById('sidebar-auth-panel');
    if (authPanel) {
        authPanel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        authPanel.style.transition = 'box-shadow 0.3s ease, border-color 0.3s ease';
        authPanel.style.boxShadow = `0 0 35px ${glowColor}`;
        authPanel.style.borderColor = borderColor;
        setTimeout(() => {
            authPanel.style.boxShadow = 'none';
            authPanel.style.borderColor = 'var(--border-card)';
        }, 2200);
    }
}

function renderGuestLockBanner(containerEl, tabName, isMovie) {
    if (!containerEl) return;
    const mediaType = isMovie ? 'filmlerinizi' : 'dizilerinizi';
    let msg = `🔒 ${tabName} listelemek için giriş yapmalısınız.`;

    if (tabName === 'Favoriler') {
        msg = `🔒 Favori ${mediaType} listelemek için giriş yapmalısınız.`;
    } else if (tabName === 'Kitaplığım') {
        msg = `🔒 Kitaplığınızı ve takip ettiğiniz ${mediaType} listelemek için giriş yapmalısınız.`;
    } else if (tabName === 'AI Tavsiyeler') {
        msg = `🔒 Kişiselleştirilmiş AI tavsiyelerini görmek için giriş yapmalısınız.`;
    } else if (tabName === 'Sosyal') {
        msg = `🔒 Sosyal katmanı ve Ortak Zevk Füzyonunu kullanabilmek için giriş yapmalısınız.`;
    } else if (tabName === 'Geri Bildirim') {
        msg = `🔒 Tercihlerinizi yönetmek ve geri bildirim göndermek için giriş yapmalısınız.`;
    }

    containerEl.innerHTML = `
        <div style="background: rgba(18, 15, 38, 0.85); border: 1px solid var(--border-card); border-radius: 20px; padding: 40px 20px; text-align: center; margin-top: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
            <i class="fa-solid fa-lock" style="font-size: 3rem; color: var(--primary-color); margin-bottom: 15px; display: block;"></i>
            <h3 style="color: #fff; font-weight: 800; font-size: 1.2rem; margin-bottom: 10px;">${msg}</h3>
            <button onclick="openAuthModal('LOGIN')" class="primary-gradient-btn" style="padding: 10px 24px; font-size: 0.9rem; border-radius: 50px; margin-top: 12px; cursor: pointer; border: none; font-weight: 800; display: inline-flex; align-items: center; gap: 8px;">
                <i class="fa-solid fa-right-to-bracket"></i> Giriş Yap / Kaydol
            </button>
        </div>
    `;
}

function updateAuthUI() {
    const loggedOutView = document.getElementById('auth-logged-out-view');
    const loggedInView = document.getElementById('auth-logged-in-view');
    const loggedInName = document.getElementById('logged-in-user-name');
    const headerUserText = document.getElementById('header-user-text');
    const authTitleText = document.getElementById('auth-accordion-title-text');

    if (!CURRENT_USER) {
        CURRENT_USER = 'Kullanıcı';
    }

    if (CURRENT_USER && CURRENT_USER !== 'Kullanıcı') {
        loadUserData(CURRENT_USER);
        if (loggedOutView) loggedOutView.style.display = 'none';
        if (loggedInView) loggedInView.style.display = 'flex';
        if (loggedInName) loggedInName.textContent = CURRENT_USER;
        if (headerUserText) headerUserText.textContent = `${CURRENT_USER} (Çevrimiçi)`;
        if (authTitleText) authTitleText.textContent = `Hoş geldin, ${CURRENT_USER}!`;
    } else {
        loadUserData(CURRENT_USER);
        if (loggedOutView) loggedOutView.style.display = 'flex';
        if (loggedInView) loggedInView.style.display = 'none';
        if (headerUserText) headerUserText.textContent = 'Giriş Yap';
        if (authTitleText) authTitleText.textContent = 'Giriş Yap / Kayıt Ol';
    }

    // Landing'deyken ağır sekme renderlarını ertele
    if (!isMainAppVisible()) {
        window._libraryNeedsRefresh = true;
        window._favoritesNeedsRefresh = true;
        return;
    }
    updateLibraryUI();
    renderFavorites();
    renderSocialUI();
    renderFeedbackUI();
    renderAIRecommenderUI();
    refreshAdminSessionFromServer();
}

function checkSavedSession() {
    loadRegisteredAccounts();
    const savedData = localStorage.getItem('MATRIX_SAVED_USER');
    if (savedData) {
        try {
            const parsed = JSON.parse(savedData);
            if (parsed && parsed.username && parsed.password) {
                const userField = document.getElementById('auth-login-username');
                const pwdField = document.getElementById('auth-login-password');
                const remCheck = document.getElementById('auth-remember-me');

                if (userField) userField.value = parsed.username;
                if (pwdField) pwdField.value = parsed.password;
                if (remCheck) remCheck.checked = true;

                // Otomatik Oturumu Aç (Beni Hatırla Aktif)
                CURRENT_USER = parsed.username;
                // GPT için imzalı token arka planda yenilenir
                ensureSignedAuthToken().catch(() => {});
            }
        } catch (e) {
            console.error('Saved session parse error:', e);
        }
    }

    if (!CURRENT_USER) {
        CURRENT_USER = 'Kullanıcı';
    }

    updateAuthUI();
    if (CURRENT_USER && CURRENT_USER !== 'Kullanıcı') {
        ensureSignedAuthToken().then(() => refreshAdminSessionFromServer()).catch(() => {});
    }
}

function forgotPasswordNotice() {
    showToast('🔑 Şifre sıfırlama bağlantısı e-posta adresinize gönderildi.', 2500);
}

let ORIGINAL_SOCIAL_TAB_HTML = '';
let ORIGINAL_FEEDBACK_TAB_HTML = '';
let ORIGINAL_LIBRARY_TAB_HTML = '';

/* ==========================================================================
   🚀 UYGULAMA BAŞLATMA
   ========================================================================== */
document.addEventListener('DOMContentLoaded', () => {
    bindLandingHeroReady();
    loadRegisteredAccounts();
    const sTab = document.getElementById('tab-social');
    const fTab = document.getElementById('tab-feedback');
    const lTab = document.getElementById('tab-library');

    if (sTab) ORIGINAL_SOCIAL_TAB_HTML = sTab.innerHTML;
    if (fTab) ORIGINAL_FEEDBACK_TAB_HTML = fTab.innerHTML;
    if (lTab) ORIGINAL_LIBRARY_TAB_HTML = lTab.innerHTML;

    initMatrixCanvas();
    setupUniverseSelection();
    setupTabNavigation();
    setupFilterListeners();
    setupLibraryListeners();
    setupVersusSearchDropdowns();
    setupAIRecommenderListeners();
    applyAdminNavVisibility();
    window._libraryNeedsRefresh = true;
    window._exploreNeedsRefresh = true;
    // Landing'de kart/sosyal render YOK — hap seçilince yüklenir
    checkSavedSession();
});