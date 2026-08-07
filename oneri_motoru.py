import sqlite3
import pandas as pd
import streamlit as st
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

# 🧠 Model ve Veritabanı Cache
@st.cache_resource
def model_yukle():
    return SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

@st.cache_data
def veritabani_baslangik_yukle():
    conn = sqlite3.connect("katalog.db")
    df = pd.read_sql_query("SELECT * FROM diziler", conn)
    conn.close()
    return df

@st.cache_data
def veritabani_vektorlerini_kodla(zengin_metinler_listesi):
    model = model_yukle()
    return model.encode(zengin_metinler_listesi, show_progress_bar=False)


# 🔍 Sinonim Genişletme Sözlüğü (İsteğe bağlı, artırılmış anlamlılık)
from sozlukler import SINONIM_MAP

def arama_metnini_genislet(arama_metni):
    """
    Sözlük varsa kullanır, yoksa orijinal metni olduğu gibi bırakır.
    Sistem asla 'patlamaz', sadece 'daha iyi anlar'.
    """
    genisletilmis = arama_metni
    for kelime, sinonimler in SINONIM_MAP.items():
        # Sadece tam kelime eşleşmesi durumunda "destek" ekliyoruz
        if f" {kelime} " in f" {arama_metni.lower()} ":
            genisletilmis += " " + sinonimler
    return genisletilmis

# 🧠 Ana AI Fonksiyonu (Motor) - Sadece Vektörel Benzerlik
def yapay_zeka_semantik_oner_yeni(kullanici_mesaji, min_puan, max_sezon, min_oy, 
                                 secilen_turler, min_yil, otomatik_izlenenler, 
                                 secilen_platformlar, sadece_bitmis, siralama_tipi):
    
    # Veriyi çek (Havuzun hazır)
    df = veritabani_baslangik_yukle()
    if df.empty: return pd.DataFrame()
    
    # 1. Filtrelemeler (Önce filtreler, sonra arama)
    df['yil'] = pd.to_numeric(df['cikis_tarihi'].fillna("0000").astype(str).str[:4], errors='coerce').fillna(0).astype(int)
    df = df[(df['puan_ortalamasi'] >= min_puan) & (df['sezon_sayisi'] <= max_sezon) &
            (df['oy_sayisi'] >= min_oy) & (df['yil'] >= min_yil)]

    if secilen_turler: df = df[df['tur'].fillna("").apply(lambda x: any(t.lower() in x.lower() for t in secilen_turler))]
    if secilen_platformlar: df = df[df['platformlar'].fillna("").apply(lambda x: any(p.lower() in x.lower() for p in secilen_platformlar))]
    if sadece_bitmis: df = df[df['durum'].fillna("").str.contains("Bitmiş|Final", case=False, na=False)]
    if otomatik_izlenenler: df = df[~df['isim'].isin(otomatik_izlenenler)]
    
    # 2. Eğer arama metni yoksa veya boşsa, filtrelenmiş listeyi puana göre dön
    if not kullanici_mesaji or not kullanici_mesaji.strip():
        return df.sort_values(by='puan_ortalamasi', ascending=False).reset_index(drop=True)
    
    # 3. Arama Varsa Semantik İşlemler
    df['temiz_ozet'] = df['ozet'].fillna("")
    
    # --- YENİ KARAKTER BİRLEŞTİRME MANTIĞI ---
    def karakterleri_birlestir(row):
        try:
            gercekler = str(row['oyuncular_gercek']).split(',')
            roller = str(row['oyuncular_rol']).split(',')
            # İlk 4 oyuncu-rol çiftini alıp metne dönüştür
            metin = ""
            for i in range(min(len(gercekler), len(roller), 4)):
                metin += f"{gercekler[i].strip()} rolünde {roller[i].strip()} "
            return metin
        except:
            return ""

    df['karakter_detay'] = df.apply(karakterleri_birlestir, axis=1)

    # Zengin metni artık karakterlerle güçlendiriyoruz
    df['zengin_metin'] = (
        df['isim'].fillna("") + " " + 
        df['tur'].fillna("") + " " + df['tur'].fillna("") + " " + 
        df['karakter_detay'] + " " + 
        df['temiz_ozet'].str[:200]
    )
    
    # 🎯 BURADA GENİŞLETME İŞLEMİ VAR
    genisletilmis_sorgu = arama_metnini_genislet(kullanici_mesaji)
    
    model = model_yukle()
    sorgu_vektoru = model.encode([genisletilmis_sorgu], show_progress_bar=False)
    dizi_vektorleri = veritabani_vektorlerini_kodla(df['zengin_metin'].tolist())
    
    benzerlikler = cosine_similarity(sorgu_vektoru, dizi_vektorleri).flatten()
    df['benzerlik_orani'] = benzerlikler
    
    # 4. Sıralama ve Eşik Değeri
    if siralama_tipi == "⭐ Dizi Puanı":
        df['oner_skoru'] = df['puan_ortalamasi']
    elif siralama_tipi == "🗳️ Popülerlik":
        df['oner_skoru'] = df['oy_sayisi']
    else:
        # Yapay Zeka Uyumu (Eşik değer 0.35)
        df = df[df['benzerlik_orani'] >= 0.35]
        df['oner_skoru'] = (df['benzerlik_orani'] * 0.7) + ((df['puan_ortalamasi'] / 10) * 0.3)
        
    return df.sort_values(by='oner_skoru', ascending=False).reset_index(drop=True)


def profil_bazli_tavsiye_uret_akilli(username, kullanici_puan, kullanici_sezon, min_oy_sayisi, 
                                     min_yil, secilen_platformlar, dizi_havuzu_df, dizi_vektorleri):
    """
    Kullanıcının detaylı zevk profilini çeker.
    Negatif havuzu eler, ardından Vektörel Benzerlik, Tür Uyumu, Anahtar Kelime Uyumu,
    Süre ve Sezon Uyumlarını birleştirerek hibrit bir tavsiye skoru oluşturur.
    """
    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity
    from fonksiyonlar import get_user_profile
    
    # 1. Kullanıcı Profilini ve geçmişini çek
    profile = get_user_profile(username)
    izlenenler = profile["izlenen_diziler"]
    gizlenenler = profile["gizlenen_diziler"]
    gercekten_izlenenler = profile["gercekten_izlenen_diziler"] # 🚀 Düzeltme: Profilleme için izlenenler
    
    # 2. Havuz filtrelemesi (Tüm kitaplıktakiler ve gizlenenler tamamen eleniyor)
    havuz_df = dizi_havuzu_df[~dizi_havuzu_df['isim'].isin(izlenenler) & ~dizi_havuzu_df['isim'].isin(gizlenenler)].copy()
    if havuz_df.empty:
        return None
        
    # Temel Kriter Filtreleri
    havuz_df['yil'] = pd.to_numeric(havuz_df['cikis_tarihi'].fillna("0000").astype(str).str[:4], errors='coerce').fillna(0).astype(int)
    havuz_df = havuz_df[
        (havuz_df['puan_ortalamasi'] >= kullanici_puan) & 
        (havuz_df['sezon_sayisi'] <= kullanici_sezon) & 
        (havuz_df['oy_sayisi'] >= min_oy_sayisi) & 
        (havuz_df['yil'] >= min_yil)
    ]
    
    # Platform Filtresi (Arayüzde seçilmişse)
    if secilen_platformlar:
        havuz_df = havuz_df[havuz_df['platformlar'].fillna("").apply(lambda x: any(p.lower() in x.lower() for p in secilen_platformlar))]
        
    if havuz_df.empty:
        return None
        
    # 3. Vektörel Benzerlik (Sadece gerçekten izlenen diziler zevk profilini çıkarır)
    # 3. Vektörel Benzerlik (🚀 PUAN AĞIRLIKLI HİBRİT VEKTÖR)
    izlenen_indeksler = dizi_havuzu_df[dizi_havuzu_df['isim'].isin(gercekten_izlenenler)].index.tolist()
    if not izlenen_indeksler:
        return havuz_df.sort_values(by='puan_ortalamasi', ascending=False).head(5)
        
    # Her izlenen dizinin zevk ağırlık katsayısını hesaplıyoruz
    aktif_kitaplik = profile["gercekten_izlenen_diziler"]
    hizali_agirliklar = []
    for idx in izlenen_indeksler:
        name = dizi_havuzu_df.loc[idx, 'isim']
        lib_row = get_user_profile(username) # Alternatif olarak library tablosundan doğrudan çekebilirsiniz
        # Kütüphanedeki detayları sorguluyoruz:
        conn = sqlite3.connect("katalog.db")
        cursor = conn.cursor()
        cursor.execute("SELECT puan, favori FROM kitaplik WHERE user_id=? AND dizi_isim=?", (username, name))
        db_res = cursor.fetchone()
        conn.close()
        
        puan = db_res[0] if (db_res and db_res[0]) else 0
        favori = db_res[1] if (db_res and db_res[1]) else 0
        
        weight = puan if puan > 0 else 3.0
        if favori == 1:
            weight += 1.5
        hizali_agirliklar.append(weight)
        
    izlenen_vektorler = dizi_vektorleri[izlenen_indeksler]
    
    # 🚀 Yüksek puanlı dizilerin vektörleri, ortalamaya daha güçlü etki eder (np.average kullanıldı)
    kullanici_profil_vektoru = np.average(izlenen_vektorler, weights=hizali_agirliklar, axis=0).reshape(1, -1)
    
    kalan_indeksler = havuz_df.index.tolist()
    tavsiye_skorlari = cosine_similarity(kullanici_profil_vektoru, dizi_vektorleri[kalan_indeksler])[0]
    havuz_df['profil_benzerligi'] = tavsiye_skorlari
    
    # 4. Tablosal ve İnce Ayar Skorlama (Tür, Süre, Sezon ve Etiket Uyumu)
    genre_weights = profile["tur_dagilimi"]
    fav_keywords = profile["favori_anahtar_kelimeler"]
    ideal_sure = profile["ortalama_sure"]
    ideal_sezon = profile["ortalama_sezon"]
    
    def detayli_skorla(row):
        # A. Tür Uyumu (Dizinin türlerinin zevk pastası yüzdeleri toplamı)
        tur_skor = 0.0
        dizi_turleri = [t.strip() for t in str(row['tur']).split(',') if t.strip()]
        for t in dizi_turleri:
            tur_skor += genre_weights.get(t, 0.0)
        tur_skor = min(1.0, tur_skor) # Max 1.0
        
        # B. Süre Uyumu (Tercih edilen ideal bölüm süresine yakınlık)
        sure_farki = abs(int(row['gercek_bolum_sureleri']) - ideal_sure)
        sure_skor = max(0.0, 1.0 - (sure_farki / 60.0)) # 60 dk farkta 0 olur
        
        # C. Sezon Uyumu (Tercih edilen ideal sezon sayısına yakınlık)
        sezon_farki = abs(int(row['sezon_sayisi']) - ideal_sezon)
        sezon_skor = max(0.0, 1.0 - (sezon_farki / 10.0)) # 10 sezon farkta 0 olur
        
        # D. Anahtar Kelime Uyumu (Kullanıcının en sevdiği etiketlerle çakışma)
        keyword_skor = 0.0
        if 'anahtar_kelimeler' in row and pd.notna(row['anahtar_kelimeler']):
            dizi_kws = [kw.strip() for kw in str(row['anahtar_kelimeler']).split(',') if kw.strip()]
            ortak_kws = set(dizi_kws).intersection(fav_keywords)
            if fav_keywords:
                keyword_skor = len(ortak_kws) / len(fav_keywords)
                
        # E. Hibrit Skor Hesaplama (Ağırlıklar)
        final_skor = (
            (row['profil_benzerligi'] * 0.40) +  # Vektör Benzerliği %40
            (tur_skor * 0.25) +                  # Tür Dağılımı (Zevk Pastası) %25
            (keyword_skor * 0.15) +              # Anahtar Kelime Uyumu %15
            (sure_skor * 0.10) +                 # Süre Uyumu %10
            (sezon_skor * 0.10)                  # Sezon Uyumu %10
        )
        return final_skor, tur_skor, sure_skor, keyword_skor
    
    skorlar = havuz_df.apply(detayli_skorla, axis=1)
    
    havuz_df['nihai_tavsiye_skoru'] = [s[0] for s in skorlar]
    havuz_df['tur_uyumu_yuzde'] = [round(s[1] * 100, 1) for s in skorlar]
    havuz_df['sure_uyumu_yuzde'] = [round(s[2] * 100, 1) for s in skorlar]
    
    # 5. En yakın izlediği dizi gerekçesini bulma (Sadece izlenmiş diziler referans alınır)
    gerekceler = []
    izlenen_vektorler = dizi_vektorleri[izlenen_indeksler]
    for idx, row in havuz_df.iterrows():
        tekli_vektor = dizi_vektorleri[idx].reshape(1, -1)
        bireysel_benzerlikler = cosine_similarity(tekli_vektor, izlenen_vektorler)[0]
        
        # En yüksek benzerliğe sahip olan indis sırasını alıyoruz
        en_yakin_sira = np.argmax(bireysel_benzerlikler)
        # Bu sırayı veritabanındaki gerçek satır indeksiyle eşleştiriyoruz
        en_yakin_dizi_db_idx = izlenen_indeksler[en_yakin_sira]
        # Gerçek dizi adını veritabanı DataFrame'inden çekiyoruz
        en_yakin_dizi = dizi_havuzu_df.loc[en_yakin_dizi_db_idx, 'isim']
        
        gerekceler.append(en_yakin_dizi)
        
    havuz_df['en_yakin_dizi_gerekce'] = gerekceler
    
    return havuz_df.sort_values(by='nihai_tavsiye_skoru', ascending=False).head(5)