"""
==============================================================================
🍿 FULL RICH PLATFORM CATALOG SYNC TOOL (ZENGİN VERİ ÇEKME MOTORU)
==============================================================================
Çekilen Her Bir Yapım İçin Eksiksiz Veri Kümesi:
  - 📺 Diziler İçin: İsim, Özet, Sezon Sayısı, Toplam Bölüm Sayısı, Bölüm Süreleri (dk),
                     Çıkış Tarihi, Türler, Platformlar (Disney+, Netflix vb.), Afiş (500px),
                     Kapak Banner (1280px), Yapım Şirketleri, Ülkeler, Orijinal Dil,
                     Önerilen ID'ler (TMDB Graph), Benzer ID'ler (TMDB Graph).
  - 🎬 Filmler İçin: İsim, Orijinal İsim, Vizyon Tarihi, Film Süresi (dk), Türler, Özet,
                     Slogan, Bütçe ($), Hasılat ($), Afiş (500px), Kapak Banner (1280px),
                     Yapım Şirketleri, Ülkeler, Orijinal Dil, Puan, Platformlar,
                     Önerilen ID'ler (TMDB Graph), Benzer ID'ler (TMDB Graph).
==============================================================================
"""

import sqlite3
import json
import urllib.request
import argparse
import sys
import subprocess

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TMDB_KEYS = [
    '802b2c4b88ea1183e50e6b285a27696e',
    '3fd2be69067701ae820e7b94e17a4670',
    'fa155f635119344d33fcb84fb807649b'
]

PLATFORM_PROVIDERS = {
    'disney': {'id': 337, 'name': 'Disney+'},
    'netflix': {'id': 8, 'name': 'Netflix'},
    'hbo': {'id': 1899, 'name': 'HBO Max'},
    'prime': {'id': 119, 'name': 'Amazon Prime Video'},
    'apple': {'id': 350, 'name': 'Apple TV+'}
}

def fetch_json(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def clean_platform_string(plat_str):
    if not plat_str: return ''
    parts = [p.strip() for p in plat_str.split(',') if p.strip()]
    seen = []
    for p in parts:
        name = p
        if 'Amazon' in p or 'Prime' in p: name = 'Amazon Prime'
        elif 'Disney' in p: name = 'Disney+'
        elif 'Netflix' in p: name = 'Netflix'
        elif 'HBO' in p or 'Max' in p: name = 'HBO Max'
        elif 'Apple' in p: name = 'Apple TV+'
        elif 'Diğer' in p: name = 'Diğer Platform'
        if name not in seen:
            seen.append(name)
    if len(seen) > 1 and 'Diğer Platform' in seen:
        seen.remove('Diğer Platform')
    return ', '.join(seen)

def sync_single_platform_media(platform_key, media_type, max_pages=15, api_key=None):
    if platform_key not in PLATFORM_PROVIDERS:
        return 0, 0

    api_key = api_key or TMDB_KEYS[0]
    provider_info = PLATFORM_PROVIDERS[platform_key]
    provider_id = provider_info['id']
    platform_name = provider_info['name']

    db_file = 'katalog.db'
    table_name = 'filmler' if media_type == 'movie' else 'diziler'

    print(f"\n========================================================================")
    print(f"🚀 ZENGİN VERİ TARAMASI: {platform_name} ({media_type.upper()}) | Hedef DB: {db_file}")
    print(f"========================================================================\n")

    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    c.execute(f"SELECT id, {'tmdb_id, ' if media_type == 'movie' else ''}isim, platformlar FROM {table_name}")
    rows = c.fetchall()

    existing_titles = {}
    for row in rows:
        if media_type == 'movie':
            item_id, tmdb_id, title, platforms = row[0], row[1], row[2], row[3]
        else:
            item_id, title, platforms = row[0], row[1], row[2]
        
        if title:
            existing_titles[title.strip().lower()] = {
                'id': item_id,
                'tmdb_id': tmdb_id if media_type == 'movie' else None,
                'platforms': platforms or ''
            }

    c.execute(f"SELECT MAX(id) FROM {table_name}")
    max_id = c.fetchone()[0] or (4400 if media_type == 'movie' else 2000)

    added_count = 0
    updated_count = 0

    for page in range(1, max_pages + 1):
        try:
            endpoint = 'discover/movie' if media_type == 'movie' else 'discover/tv'
            url = f"https://api.themoviedb.org/3/{endpoint}?api_key={api_key}&with_watch_providers={provider_id}&language=tr-TR&page={page}"
            
            data = fetch_json(url)
            results = data.get('results', [])
            total_tmdb_pages = data.get('total_pages', 1)
            
            if page > total_tmdb_pages:
                print(f"🛑 Toplam sayfa doldu ({total_tmdb_pages} sayfa).")
                break

            print(f"📄 Sayfa {page}/{min(max_pages, total_tmdb_pages)} işleniyor ({len(results)} {media_type} ZENGİN verileriyle taranıyor)...")

            for item in results:
                tmdb_id = item.get('id')
                title = item.get('title') if media_type == 'movie' else item.get('name')
                if not title: continue

                title_key = title.strip().lower()

                if title_key in existing_titles:
                    cur_info = existing_titles[title_key]
                    cur_platforms = cur_info['platforms']
                    if platform_name not in cur_platforms:
                        new_platforms = clean_platform_string(f"{cur_platforms}, {platform_name}")
                        c.execute(f"UPDATE {table_name} SET platformlar = ? WHERE id = ?", (new_platforms, cur_info['id']))
                        cur_info['platforms'] = new_platforms
                        updated_count += 1
                else:
                    try:
                        # 1. Ana Detay Çekimi
                        detail_url = f"https://api.themoviedb.org/3/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}?api_key={api_key}&language=tr-TR"
                        d_data = fetch_json(detail_url)

                        # 2. Önerilen ve Benzer ID Graph Çekimi
                        recs_url = f"https://api.themoviedb.org/3/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}/recommendations?api_key={api_key}&language=tr-TR"
                        sims_url = f"https://api.themoviedb.org/3/{'movie' if media_type == 'movie' else 'tv'}/{tmdb_id}/similar?api_key={api_key}&language=tr-TR"
                        
                        rec_ids = []
                        sim_ids = []
                        try:
                            r_data = fetch_json(recs_url)
                            rec_ids = [r['id'] for r in r_data.get('results', [])[:12]]
                        except: pass
                        try:
                            s_data = fetch_json(sims_url)
                            sim_ids = [s['id'] for s in s_data.get('results', [])[:12]]
                        except: pass

                        ppath = d_data.get('poster_path')
                        bpath = d_data.get('backdrop_path')
                        poster = f"https://image.tmdb.org/t/p/w500{ppath}" if ppath else "https://images.unsplash.com/photo-1598899134739-24c46f58b8c0?w=500"
                        backdrop = f"https://image.tmdb.org/t/p/w1280{bpath}" if bpath else "https://images.unsplash.com/photo-1574375927938-d5a98e8ffe85?w=1280"
                        
                        genres = ', '.join([g['name'] for g in d_data.get('genres', [])])
                        overview = d_data.get('overview') or f"{title} yapımı."
                        slogan = d_data.get('tagline') or ''
                        companies = json.dumps([comp['name'] for comp in d_data.get('production_companies', [])], ensure_ascii=False)
                        countries = json.dumps([cnt['iso_3166_1'] for cnt in d_data.get('production_countries', [])], ensure_ascii=False)
                        lang = d_data.get('original_language', 'en')
                        rating = round(d_data.get('vote_average', 7.5), 1)
                        votes = d_data.get('vote_count', 500)
                        rel_date = (d_data.get('release_date') if media_type == 'movie' else d_data.get('first_air_date')) or ''

                        recs_json_str = json.dumps(rec_ids)
                        sims_json_str = json.dumps(sim_ids)

                        max_id += 1

                        if media_type == 'movie':
                            budget = d_data.get('budget', 0)
                            revenue = d_data.get('revenue', 0)
                            runtime = d_data.get('runtime', 110)
                            orig_title = d_data.get('original_title', title)
                            
                            c.execute('''
                                INSERT INTO filmler (id, tmdb_id, isim, orijinal_isim, vizyon_tarihi, sure, turler, ozet, poster_url, backdrop_url, slogan, butce, hasilat, yapim_sirketleri, yapim_ulkeleri, orijinal_dil, puan, oy_sayisi, platformlar, onerilen_idleri, benzer_idleri)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (max_id, str(tmdb_id), title, orig_title, rel_date, runtime, genres, overview, poster, backdrop, slogan, budget, revenue, companies, countries, lang, rating, votes, platform_name, recs_json_str, sims_json_str))
                        else:
                            seasons = d_data.get('number_of_seasons', 1)
                            episodes = d_data.get('number_of_episodes', 10)
                            ep_dur = d_data.get('episode_run_time', [45])[0] if d_data.get('episode_run_time') else 45
                            status = 'Bitmiş / Final Yapmış' if d_data.get('status') == 'Ended' else 'Devam Ediyor'
                            
                            c.execute('''
                                INSERT INTO diziler (id, isim, ozet, puan_ortalamasi, oy_sayisi, sezon_sayisi, toplam_bolum_sayisi, gercek_bolum_sureleri, cikis_tarihi, tur, afis_url, durum, platformlar, backdrop_url, yapim_ulkeleri, yayin_aglari, yapim_sirketleri, orijinal_dil, onerilen_idleri, benzer_idleri)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (max_id, title, overview, rating, votes, seasons, episodes, ep_dur, rel_date, genres, poster, status, platform_name, backdrop, countries, platform_name, companies, lang, recs_json_str, sims_json_str))

                        existing_titles[title_key] = {'id': max_id, 'platforms': platform_name}
                        added_count += 1
                        print(f"  ✨ EKLENDİ [{media_type.upper()}]: {title} | Sezon/Süre: {seasons if media_type=='show' else runtime} | Platform: {platform_name}")
                    except Exception as ex:
                        pass

        except Exception as e:
            print(f"❌ Sayfa Hatalı ({page}): {e}")

    conn.commit()
    conn.close()
    return updated_count, added_count

def run_sync(platform_arg='all', type_arg='all', pages_arg=15, api_key=None):
    platforms = list(PLATFORM_PROVIDERS.keys()) if platform_arg == 'all' else [platform_arg]
    types = ['movie', 'show'] if type_arg == 'all' else [type_arg]

    total_up = 0
    total_add = 0

    for p in platforms:
        for t in types:
            up, add = sync_single_platform_media(p, t, pages_arg, api_key)
            total_up += up
            total_add += add

    print(f"\n========================================================================")
    print(f"🎉 ZENGİN VERİ ÇEKİMİ VE GRAPH İLİŞKİLENDİRME TAMAMLANDI!")
    print(f"  👉 Güncellenen (Platform Etiketi Eklenen): {total_up}")
    print(f"  👉 Tüm Zengin Detaylarıyla Sıfırdan Eklenen: {total_add}")
    print(f"========================================================================\n")

    try:
        subprocess.run([sys.executable, 'export_data_store.py'], check=True)
        print("✅ data_store.js otomatik güncellendi!")
    except Exception as e:
        print(f"⚠️ data_store.js aktarım uyarısı: {e}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Full Rich Platform Catalog Sync Tool')
    parser.add_argument('--platform', choices=['all', 'disney', 'netflix', 'hbo', 'prime', 'apple'], default='all')
    parser.add_argument('--type', choices=['all', 'movie', 'show'], default='all')
    parser.add_argument('--pages', type=int, default=15)
    parser.add_argument('--api_key', type=str, default=None)
    args = parser.parse_args()

    run_sync(args.platform, args.type, args.pages, args.api_key)
