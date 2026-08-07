import os
import json
import time
import random
import html
import datetime
import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
import importlib
import altair as alt

# 3. Parti Kütüphaneler
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from streamlit_cookies_controller import CookieController
from streamlit_javascript import st_javascript

# Yeni Merkezi Kütüphaneden Importlar
import fonksiyonlar_yeni as f_yeni
from fonksiyonlar_yeni import (
    yapay_zeka_semantik_oner_yeni,
    profil_bazli_tavsiye_uret_akilli,
    platform_linklerini_olustur, ozet_getir_veya_uret,
    kitapliga_dizi_ekle_veya_güncelle, kullanıcı_kitaplığını_getir,
    toplam_izleme_suresini_hesapla, kitapliktan_kayit_sil,
    kullanıcı_favorilerini_getir,
    profil_bazli_tavsiye_uret, iki_dizi_karsilastir_meta_uret,
    arkadas_ekle, arkadas_listesini_getir, arkadas_sil,
    arkadas_istekleri_yukle, ortak_zevk_fuzyon_tavsiyesi_uret,
    get_dizi_info, turleri_ve_platformlari_getir, dizi_bul,
    yapay_zeka_modelini_yukle, verileri_ve_vektorleri_hazirla,
    kitaplik_ilerleme_guncelle, kullanicinin_listesini_getir, 
    dizi_islem_kaydet, dizi_listeden_sil, tum_dizi_verilerini_getir,
    veritabani_sutunlarini_guncelle, db_satir_sayisi_getir,
    hybrid_arama_skorla, metni_anlamli_kelimeye_cevir, 
    yapay_zeka_icin_anlamli_sorgu_olustur,
    yapay_zeka_neden_izlemeli_uret,
    favori_sil, favoriye_ekle, bekleyen_istekleri_getir, istek_yanitla,
    geri_bildirim_kaydet, kullanici_rozetlerini_hesapla
)
import styles

# Geriye dönük uyumluluk takma adları (Alias)
auth_utils = f_yeni
db = f_yeni
db_utils_yeni = f_yeni
fonksiyonlar = f_yeni

# --- BAŞLANGIÇ AYARLARI ---
st.set_page_config(page_title="dizimibul — Yapay Zeka Dizi Asistanı", page_icon="🎬", layout="wide")


if "db_initialized" not in st.session_state:
    f_yeni.init_auth_db()
    veritabani_sutunlarini_guncelle()
    st.session_state.db_initialized = True

def efsanevi_ikili_goster(efsanevi_ikili_str, key_suffix=""):
    """Efsanevi ikili verisini parse eder ve şık, açılır-kapanır bir başlık altında sunar."""
    if not efsanevi_ikili_str or pd.isna(efsanevi_ikili_str) or str(efsanevi_ikili_str).strip() == "":
        return
    try:
        import html
        parts = [p.strip() for p in str(efsanevi_ikili_str).split('|')]
        if len(parts) >= 1:
            ikili = html.escape(parts[0])
            tur = html.escape(parts[1]) if len(parts) > 1 else "Karakter Dinamiği"
            aciklama = html.escape(parts[2]) if len(parts) > 2 else ""
            
            # Benzersiz anahtar oluştur
            exp_key = f"duo_exp_{ikili.replace(' ', '_').replace('\"', '_').replace('&', '_')}_{key_suffix}"
            
            with st.expander(f"👥 Efsanevi İkili: {ikili}", expanded=False, key=exp_key):
                card_html = f"""
                <div style="background: rgba(168, 85, 247, 0.08); border-left: 4px solid #a855f7; padding: 12px 16px; border-radius: 6px; margin: 5px 0;">
                    <div style="font-size: 14px; color: #a855f7; font-weight: bold; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.8px;">🎭 {tur}</div>
                    {f'<div style="font-size: 14px; color: #e5e7eb; line-height: 1.5; font-weight: 500;">{aciklama}</div>' if aciklama else ''}
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)
    except Exception as e:
        import logging
        logging.error(f"Hata (Efsanevi İkili Gösterimi): {str(e)}", exc_info=True)



def cerez_yaz_ve_yeniden_baslat(username=None, auto_login=False):
    """Tarayıcı çerezlerini CookieController üzerinden yazar/siler ve Streamlit'in kendi
    rerun mekanizmasıyla sayfayı tazeler (Session Token Sürümü).

    🔧 DÜZELTME (Çift Tıklama Hatası): Önceki sürüm, çerez yazıldıktan sonra JS ile tam
    sayfa yeniden yüklemesi (location.reload()) tetikliyordu. Bu, tarayıcıda TAMAMEN YENİ
    bir Streamlit oturumu başlatıyor ve mevcut session_state'i (logged_in, rozetler vb.)
    sıfırlıyordu. Çerez tarayıcıya tam olarak yazılmadan reload tetiklenirse (yarış durumu),
    kullanıcı "giriş yapmamış" gibi görünüyor ve tekrar tıklaması gerekiyordu.
    Artık: çerezin tarayıcıya işlenmesi için kısa bir süre tanıyoruz, ardından tam sayfa
    yenilemesi yerine st.rerun() kullanıyoruz. Bu, mevcut session_state'i korur ve
    giriş/çıkışın tek tıklamada anında yansımasını sağlar.
    """
    if username and auto_login:
        # Oturum token'ı oluştur ve DB'ye kaydet
        token = f_yeni.oturum_olustur(username)
        # 🔧 DÜZELTME (Beni Hatırla 1 günde düşüyordu): streamlit_cookies_controller,
        # 'expires' parametresi verilmezse bunu SESSİZCE "şu an + 1 gün" olarak
        # sabitliyor; max_age=30 gün göndersek bile tarayıcıya çelişkili bir çerez
        # (expires=1 gün, maxAge=30 gün) gidiyor ve pratikte çok daha kısa sürede
        # düşüyordu. Artık expires'ı da max_age ile AYNI (30 gün) veriyoruz.
        son_gecerlilik = datetime.datetime.now() + datetime.timedelta(days=30)
        controller.set("session_token", token, max_age=30*24*60*60, expires=son_gecerlilik, path="/")
        controller.set("remembered_username", username, max_age=30*24*60*60, expires=son_gecerlilik, path="/")
    else:
        # Çıkış yaparken DB'den oturumu sil
        current_token = controller.get("session_token")
        if current_token:
            f_yeni.oturum_sil(current_token)
        try:
            controller.remove("session_token", path="/")
        except Exception:
            pass

    # 🍪 Çerez bileşeninin tarayıcıyla senkronize olması için kısa bir süre tanıyoruz
    # (dosyanın başındaki "cerez_senkronizasyonu" mantığıyla aynı prensip).
    time.sleep(0.1)
    st.rerun()

def init_session_state():
    defaults = {
        'sayfa': 1,
        'son_arama': "",
        'username': None,
        'logged_in': False,
        'gosterim_adedi': 5,
        'show_login_trigger': False,
        'sifre_unuttum_ekrani': False,
        'kod_bekleniyor': False,
        'temp_remembered_user': "",
        'ai_sorgu_zamanlari': [],
        'captcha_num1': random.randint(1, 10),
        'captcha_num2': random.randint(1, 10)
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()


# --- SESSION VE VERİ YÜKLEME ---

# --- Her rerun'da çalışacak güncel liste çekme bloğu ---
if st.session_state.get("logged_in") and st.session_state.get("username"):
    st.session_state.pozitif_feedbacks = kullanicinin_listesini_getir(st.session_state.username, "begenilenler")
    st.session_state.negatif_feedbacks = kullanicinin_listesini_getir(st.session_state.username, "gizlenenler")
else:
    st.session_state.pozitif_feedbacks = []
    st.session_state.negatif_feedbacks = []

import streamlit.components.v1 as components

if st.session_state.get("scroll_to_top", False):
    # 🚀 Use components.html (one-way) so it does not send values back to Python and trigger a second automatic rerun.
    # This keeps the iframe mounted in the DOM, allowing all setTimeout delays and MutationObserver to complete.
    js_scroll = """
    <script>
        (function() {
            var scroll = function() {
                var targets = [
                    window.parent.document.querySelector('.main'),
                    window.parent.document.querySelector('section.main'),
                    window.parent.document.querySelector('[data-testid="stAppViewContainer"]'),
                    window.parent.document.querySelector('[data-testid="stMain"]'),
                    window.parent.document.documentElement,
                    window.parent.document.body
                ];
                targets.forEach(function(el) { if(el) el.scrollTop = 0; });
                window.parent.scrollTo(0,0);
            };
            [0, 50, 100, 200, 350, 500, 800, 1200, 1800, 2500, 3000].forEach(function(delay) {
                setTimeout(scroll, delay);
            });
            var kokEl = window.parent.document.querySelector('[data-testid="stAppViewContainer"]') || window.parent.document.body;
            var gozlemci = new window.parent.MutationObserver(function() { scroll(); });
            gozlemci.observe(kokEl, { childList: true, subtree: true });
            setTimeout(function() { gozlemci.disconnect(); }, 3000);
        })();
    </script>
    """
    components.html(js_scroll, height=0, width=0)
    st.session_state.scroll_to_top = False

# CookieController'ı her döngüde bir kez çağırarak widget'ın aktif kalmasını sağlıyoruz
controller = CookieController()
if getattr(controller, "_CookieController__cookies", None) is None:
    controller._CookieController__cookies = {}

# 🍪 KRİTİK DÜZELTME: streamlit_cookies_controller, tarayıcıdaki çerezleri anında değil,
# arka planda bir JS bileşeni yükleyip tarayıcıyla haberleştikten SONRA okuyabiliyor.
# Bu yüzden bir oturumun (session) İLK çalıştırmasında controller.get(...) çağrıları
# çerez fiilen var olsa bile None dönebiliyor — "Beni Hatırla" çalışmıyormuş gibi
# görünmesinin asıl sebebi budur. Çözüm: oturum başına SADECE BİR KEZ, bileşenin
# tarayıcıyla senkronize olması için sessiz bir "ısınma" rerun'u yapıyoruz; asıl
# otomatik giriş kararını bu senkronizasyondan SONRAKİ çalıştırmada veriyoruz.
if "cerez_senkronizasyonu_tamam" not in st.session_state:
    st.session_state.cerez_senkronizasyonu_tamam = True
    time.sleep(0.1)  # 🍪 Tarayıcıyla senkronize olabilmesi için ilk yüklemede 100ms süre tanıyoruz
    st.rerun()

session_token = controller.get("session_token")

if session_token and not st.session_state.logged_in:
    saved_username = f_yeni.oturum_dogrula(session_token)
    if saved_username:
        st.session_state.logged_in = True
        st.session_state.username = saved_username
        st.session_state.pozitif_feedbacks = kullanicinin_listesini_getir(saved_username, "begenilenler")
        st.session_state.negatif_feedbacks = kullanicinin_listesini_getir(saved_username, "gizlenenler")
        st.session_state.kullanici_rozetleri = kullanici_rozetlerini_hesapla(saved_username)
        st.rerun()
    else:
        # Geçersiz/süresi dolmuş çerezi temizliyoruz
        try:
            controller.remove("session_token", path="/")
        except Exception:
            pass

# 🏆 Kullanıcı rozetlerini oturum boyunca bellekte tutmak için session state önbelleği kuruyoruz
if st.session_state.logged_in and "kullanici_rozetleri" not in st.session_state:
    st.session_state.kullanici_rozetleri = kullanici_rozetlerini_hesapla(st.session_state.username)


# ==============================================================================
# 🌟 TEKLİ ÜYELİK PANELİ FONKSİYONU 🌟
# ==============================================================================
def tekli_uyelik_paneli_goster(panel_id, controller=None):
    if controller is None:
        controller = globals().get("controller")
    
    temp_remembered_user = controller.get("remembered_username") or ""
    
    # Oturum bazlı aktif sekmeyi session_state ile yönetiyoruz (Kayıt olunca otomatik geçebilmek için)
    active_tab_key = f"active_tab_{panel_id}"
    if active_tab_key not in st.session_state:
        st.session_state[active_tab_key] = "Giriş Yap"
        
    # Yan yana butonlarla tab tasarımı
    col_tab1, col_tab2 = st.columns(2)
    with col_tab1:
        is_active_login = st.session_state[active_tab_key] == "Giriş Yap"
        if st.button("🔑 Giriş Yap", key=f"tab_btn_login_{panel_id}", type="primary" if is_active_login else "secondary", use_container_width=True):
            st.session_state[active_tab_key] = "Giriş Yap"
            st.rerun()
            
    with col_tab2:
        is_active_register = st.session_state[active_tab_key] == "Kayıt Ol"
        if st.button("📝 Kayıt Ol", key=f"tab_btn_reg_{panel_id}", type="primary" if is_active_register else "secondary", use_container_width=True):
            st.session_state[active_tab_key] = "Kayıt Ol"
            st.rerun()
            
    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
    
    if st.session_state[active_tab_key] == "Giriş Yap":
        # Giriş Yap Ekranı
        reg_username = st.session_state.get(f"reg_success_username_{panel_id}", temp_remembered_user)
        l_user = st.text_input("Kullanıcı Adı", value=reg_username, key=f"login_user_{panel_id}")
        l_pass = st.text_input("Şifre", type="password", key=f"login_pass_{panel_id}")
        beni_hatirla = st.checkbox("Beni Hatırla", value=True if reg_username != "" else False, key=f"remember_{panel_id}")
        
        col_g1, col_g2 = st.columns([1, 1])
        with col_g1:
            giris_butonu = st.button("Giriş Yap", key=f"login_btn_{panel_id}", use_container_width=True)
        with col_g2:
            sifre_butonu = st.button("Şifremi Unuttum", key=f"forgot_{panel_id}", use_container_width=True)

        if giris_butonu:
            if not l_user.strip() or not l_pass.strip():
                st.warning("⚠️ Lütfen tüm alanları doldurun.")
            else:
                try:
                    if f_yeni.kullanici_kontrol_et(l_user.strip(), l_pass.strip()):
                        st.session_state.logged_in = True
                        st.session_state.username = l_user.strip()
                        
                        # Eski oturum verilerini temizle ki yeni kullanıcının verileri yüklensin
                        st.session_state.pop("kitaplik_df", None)
                        st.session_state.pop("kullanici_rozetleri", None)
                        
                        # Başarımları (rozetleri) giriş anında bir kez hesaplayıp session_state'e cache'liyoruz (Performans)
                        st.session_state.kullanici_rozetleri = f_yeni.kullanici_rozetlerini_hesapla(l_user.strip())
                        st.session_state.pozitif_feedbacks = kullanicinin_listesini_getir(l_user.strip(), "begenilenler")
                        st.session_state.negatif_feedbacks = kullanicinin_listesini_getir(l_user.strip(), "gizlenenler")
                        
                        st.toast("🎉 Giriş başarılı!", icon="✅")
                        if beni_hatirla:
                            cerez_yaz_ve_yeniden_baslat(l_user.strip(), True)
                        else:
                            cerez_yaz_ve_yeniden_baslat(None, False)
                    else:
                        st.error("❌ Kullanıcı adı veya şifre hatalı!")
                except PermissionError as pe:
                    st.error(str(pe))
                except Exception as e:
                    st.error("❌ Giriş işlemi sırasında sistemsel bir hata oluştu!")

        if sifre_butonu:
            st.session_state.sifre_unuttum_ekrani = True

        if st.session_state.sifre_unuttum_ekrani:
            st.divider()
            email_input = st.text_input("Kayıtlı E-postanızı girin:", key="sifre_reset_mail")
            
            if st.button("Kod Gönder"):
                try:
                    if f_yeni.sifre_sifirlama_talebi(email_input.strip()):
                        st.success("Kod mail adresinize gönderildi!")
                        st.session_state.kod_bekleniyor = True
                    else:
                        st.error("Bu e-posta kayıtlı değil!")
                except PermissionError as pe:
                    st.error(str(pe))
                except Exception:
                    st.error("❌ E-posta gönderimi sırasında sistemsel bir hata oluştu!")
                    
            if st.session_state.kod_bekleniyor:
                kod_input = st.text_input("Gelen Kodu Girin:", key="sifre_reset_kod")
                yeni_sifre = st.text_input("Yeni Şifre:", type="password", key="sifre_reset_yeni")
                
                if st.button("Şifreyi Güncelle"):
                    basari, mesaj = f_yeni.sifre_dogrula_ve_guncelle(email_input.strip(), kod_input, yeni_sifre)
                    if basari: 
                        st.success(mesaj)
                        st.session_state.sifre_unuttum_ekrani = False 
                        st.session_state.kod_bekleniyor = False
                        st.rerun()
                    else: 
                        st.error(mesaj)

    else:
        # Kayıt Ol Ekranı
        r_user = st.text_input("Yeni Kullanıcı Adı", key=f"reg_user_{panel_id}")
        r_email = st.text_input("E-posta (Opsiyonel)", key=f"reg_email_{panel_id}")
        r_pass = st.text_input("Yeni Şifre", type="password", key=f"reg_pass_{panel_id}")
        
        # 🤖 Bot / Otomasyon Koruması Captcha
        c_num1 = st.session_state.captcha_num1
        c_num2 = st.session_state.captcha_num2
        r_captcha = st.number_input(f"Doğrulama Sorusu: {c_num1} + {c_num2} = ?", min_value=0, key=f"reg_captcha_{panel_id}")
        
        if st.button("Kayıt Ol", key=f"reg_btn_{panel_id}", use_container_width=True):
            if not r_user.strip() or not r_pass.strip():
                st.warning("⚠️ Lütfen kullanıcı adı ve şifre alanlarını doldurun.")
            elif r_captcha != c_num1 + c_num2:
                st.error("❌ Yanlış cevap! Lütfen doğrulama sorusunu tekrar cevaplayın.")
                # Captcha sayılarını yenile
                st.session_state.captcha_num1 = random.randint(1, 10)
                st.session_state.captcha_num2 = random.randint(1, 10)
                st.rerun()
            else:
                basari, mesaj = f_yeni.kayit_ol(r_user, r_pass, r_email)
                if basari:
                    st.toast("🎉 Kayıt başarılı! Giriş Yap sekmesinden oturum açabilirsiniz.", icon="✅")
                    # Otomatik olarak Giriş Yap sekmesine yönlendir ve kullanıcı adını doldur
                    st.session_state[active_tab_key] = "Giriş Yap"
                    st.session_state[f"reg_success_username_{panel_id}"] = r_user.strip()
                    # Başarı sonrası captchayı da sıfırla
                    st.session_state.captcha_num1 = random.randint(1, 10)
                    st.session_state.captcha_num2 = random.randint(1, 10)
                    st.rerun()
                else:
                    st.error(f"❌ {mesaj}")


# ==============================================================================
# --- 2. CSS (Performans Odaklı & Zenginleştirilmiş Tasarım) ---
# ==============================================================================
st.markdown(styles.MAIN_CSS, unsafe_allow_html=True)
st.markdown(styles.BADGE_CSS, unsafe_allow_html=True)

# --- 3. SESSION STATE VE FEEDBACK KONTROLLERİ ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'username' not in st.session_state: st.session_state.username = None
if 'show_login_trigger' not in st.session_state: st.session_state.show_login_trigger = False
if 'pozitif_feedbacks' not in st.session_state: st.session_state.pozitif_feedbacks = []
if 'negatif_feedbacks' not in st.session_state: st.session_state.negatif_feedbacks = []

# --- 3B. ROZET TAKİBİ VE POPUP BİLDİRİM MOTORU ---
if st.session_state.get("logged_in") and st.session_state.get("username"):
    rozet_data = st.session_state.kullanici_rozetleri
    
    if "rozetler_onceki" not in st.session_state:
        st.session_state.rozetler_onceki = {k: v["seviye"] for k, v in rozet_data.items()}
        st.session_state.rozet_popuplar = []
    else:
        # Yeni başarımları kontrol et
        yeni_kazanilanlar = []
        for k, v in rozet_data.items():
            onceki = st.session_state.rozetler_onceki.get(k)
            simdiki = v["seviye"]
            if simdiki is not None and onceki != simdiki:
                yeni_kazanilanlar.append((k, simdiki))
                st.session_state.rozetler_onceki[k] = simdiki
                
        if yeni_kazanilanlar:
            for r_key, r_sev in yeni_kazanilanlar:
                st.session_state.rozet_popuplar.append((r_key, r_sev, time.time()))
                
    # 5 saniyeden eski popupları temizle
    st.session_state.rozet_popuplar = [
        p for p in st.session_state.get("rozet_popuplar", []) 
        if time.time() - p[2] < 5.0
    ]
    
    # Popup bildirimlerini HTML olarak sayfaya bas
    if st.session_state.rozet_popuplar:
        rozet_bilgisi = {
            "ekran_bagimlisi": ("🍿", "Ekran Bağımlısı"),
            "koltuk_patatesi": ("📺", "Koltuk Patatesi"),
            "netflix_gurmesi": ("🎬", "Netflix Gurmesi"),
            "prime_secici": ("🎁", "Prime Seçici"),
            "disney_seyyahi": ("🏰", "Disney Seyyahı"),
            "gizli_cevher": ("💎", "Gizli Cevher Avcısı"),
            "dram_sever": ("🎭", "Dram Sever"),
            "bilimkurgu_kasifi": ("🚀", "Bilimkurgu Kaşifi"),
            "kahkaha_makinesi": ("😂", "Kahkaha Makinesi"),
            "suc_ortagi": ("🕵️", "Suç Ortağı"),
            "sosyal_kelebek": ("🤝", "Sosyal Kelebek"),
            "kritik_zihin": ("✍️", "Kritik Zihin"),
            "koleksiyoner": ("🏆", "Koleksiyoner"),
            "efsane": ("👑", "Efsane")
        }
        
        popup_html = ""
        for r_key, r_sev, ts in st.session_state.rozet_popuplar:
            emoji, isim = rozet_bilgisi.get(r_key, ("🏅", r_key.replace("_", " ").title()))
            seviye_str = r_sev.upper()
            popup_html += f"""
            <div class="achievement-popup">
                <div class="rozet-daire rozet-{r_sev}" style="width: 48px !important; height: 48px !important; font-size: 22px !important; margin: 0 !important; line-height: 48px !important; min-width: 48px !important;">
                    {emoji}
                </div>
                <div>
                    <div style="font-size: 10px; color: #c084fc; font-weight: 700; letter-spacing: 1px;">BAŞARIM KAZANILDI!</div>
                    <div style="font-size: 14px; color: white; font-weight: 700;">{isim}</div>
                    <div style="font-size: 11px; color: #ffd700; font-weight: 700;">{seviye_str} SEVİYE</div>
                </div>
            </div>
            """
        st.markdown(popup_html, unsafe_allow_html=True)

# --- 4. MOTOR VE VERİ (Nihai ve Optimize Edilmiş) ---
with st.spinner("🧠 Yapay Zeka Arama Motoru Hazırlanıyor... (İlk açılışta 5-10 saniye sürebilir, sonrakiler anlık olacaktır)"):
    model = yapay_zeka_modelini_yukle() 
    db_version = db_satir_sayisi_getir()
    dizi_havuzu_df, dizi_vektorleri = verileri_ve_vektorleri_hazirla(model, db_version)
tum_diziler = dizi_havuzu_df['isim'].tolist()

# --- 5. CORE ENGINE FONKSİYONLARI (MERKEZİ KÖPRÜ TETİKLEYİCİLERİ) ---

def semantik_oner_wrapper(kullanici_mesaji, **kwargs):
    return yapay_zeka_semantik_oner_yeni(
        kullanici_mesaji, 
        **kwargs, 
        dizi_havuzu_df=dizi_havuzu_df, 
        dizi_vektorleri=dizi_vektorleri, 
        model=model
    )

def sure_hesapla_wrapper(kitaplik_df):
    return toplam_izleme_suresini_hesapla(kitaplik_df, dizi_havuzu_df=dizi_havuzu_df)

def link_olustur_wrapper(platform_metni):
    return platform_linklerini_olustur(platform_metni)


# --- 6. SIDEBAR (Sol Panel - Filtreleme Odaklı) ---

otomatik_izlenenler, aktif_izlenenler = [], []

if st.session_state.logged_in and st.session_state.username:
    if "kitaplik_df" not in st.session_state:
        st.session_state.kitaplik_df = kullanıcı_kitaplığını_getir(st.session_state.username)
    kitaplik_tumu_df = st.session_state.kitaplik_df
    if not kitaplik_tumu_df.empty:
        otomatik_izlenenler = kitaplik_tumu_df['dizi_isim'].tolist()
        aktif_izlenenler = kitaplik_tumu_df[kitaplik_tumu_df['durum'].isin(["İzledim", "İzliyorum"])]['dizi_isim'].tolist()
    
    gizlenen_diziler = st.session_state.get('negatif_feedbacks', [])
    otomatik_izlenenler = sorted(list(set(otomatik_izlenenler + gizlenen_diziler)))
else:
    kitaplik_tumu_df = pd.DataFrame()

# Logo dosyasını base64 formatına çevirip kenar çubuğunda şık bir ikon kartı olarak gösteriyoruz
logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo.png")
logo_html = ""
if os.path.exists(logo_path):
    import base64
    with open(logo_path, "rb") as f:
        logo_b64 = base64.b64encode(f.read()).decode()
    logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="width: 80px; height: 80px; border-radius: 20px; box-shadow: 0 4px 15px rgba(168, 85, 247, 0.4); margin-bottom: 10px;">'
else:
    logo_html = '<span style="font-size: 40px; margin-bottom: 10px;">🎬</span>'

st.sidebar.markdown(
    f"<div style='display: flex; flex-direction: column; align-items: center; justify-content: center; margin-bottom: 20px;'>"
    f"{logo_html}"
    f"<h1 style='color: #a855f7; font-size: 28px; font-weight: 800; letter-spacing: 1px; margin: 0; padding: 0;'>dizimibul</h1>"
    f"<p style='color: #94a3b8; font-size: 12px; margin: 5px 0 0 0; padding: 0;'>Yapay Zeka Dizi Öneri Motoru</p>"
    f"</div>",
    unsafe_allow_html=True
)

if not st.session_state.logged_in:
    with st.sidebar.expander("🔑 Giriş Yap / Kayıt Ol", expanded=False):
        st.write("İzleme geçmişi için giriş yapmalısın.")
        tekli_uyelik_paneli_goster(panel_id="sidebar_expander")
else:
    st.sidebar.success(f"Hoş geldin, {st.session_state.username}!")
    if st.sidebar.button("🚪 Oturumu Kapat", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.username = None
        st.session_state.pop("kullanici_rozetleri", None)
        st.session_state.pop("kitaplik_df", None)
        st.session_state.pop("pozitif_feedbacks", None)
        st.session_state.pop("negatif_feedbacks", None)
        cerez_yaz_ve_yeniden_baslat(None, False)

st.sidebar.markdown("---")

st.sidebar.subheader("⚙️ Ayarlar ve Filtreler")

kullanici_puan = st.sidebar.slider("Minimum Dizi Puanı", 1.0, 10.0, 7.0, 0.1)
kullanici_esik = st.sidebar.slider("🎯 Arama Hassasiyeti (%)", 30, 60, 35, 5, help="Semantik aramanın ne kadar sıkı eşleşeceğini belirler. Düşük değerler daha çok alternatif sunar, yüksek değerler nokta atışı sonuçlar getirir.")
siralam_secenegi = st.sidebar.selectbox("🔝 Sıralama", ["🎯 Yapay Zeka Uyumu", "⭐ Dizi Puanı", "🗳️ Popülerlik", "🔍 Gizli Cevherler", "🔀 Şansımı Dene (Rastgele)"], key="siralama_filtre")
secilen_turler = st.sidebar.multiselect("🎭 Türler", ["Aksiyon & Macera", "Animasyon", "Komedi", "Suç", "Belgesel", "Dram", "Aile", "Gizem", "Bilim Kurgu & Fantastik"])
secilen_platformlar = st.sidebar.multiselect("📺 Platform", ["Netflix", "Amazon Prime", "Disney Plus", "HBO / Max", "Diğer"])
min_yil = st.sidebar.number_input("📅 Min. Yayın Yılı", 1950, 2026, 1990)
kullanici_sezon = st.sidebar.number_input("Maksimum Sezon Sayısı", min_value=1, max_value=50, value=20)
min_oy_sayisi = st.sidebar.number_input("🗳️ Min. Oy Sayısı", 0, 50000, 300, 50)

options_list = [5, 10, 15]
st.session_state.gosterim_adedi = st.sidebar.selectbox(
    "📄 Sayfa Başına Dizi",
    options=options_list,
    index=options_list.index(st.session_state.gosterim_adedi) if st.session_state.gosterim_adedi in options_list else 0,
    key="gosterim_secimi_side",
    help="Bir sayfada kaç dizi gösterileceğini seçin."
)

sadece_bitmis = st.sidebar.checkbox("🏁 Sadece Bitmiş Diziler")


# ==============================================================================
# --- 7. SEKMELER (Master Blok) ---
# ==============================================================================

st.markdown(styles.TAB_CSS, unsafe_allow_html=True)

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🚀 Keşfet", "📚 Kitaplığım", "❤️ Favoriler", 
    "✨ Tavsiyeler", "⚙️ Geri Bildirim", "🆚 Versus", "👥 Sosyal"
], key="ana_sekmeler")


# ==============================================================================
# --- 8. KEŞFET SEKMEDE BULUNAN ARAMA & SAYFALAMA MOTORU ---
# ==============================================================================

with tab1:
    st.subheader("🔍 Yapay Zeka ile Dizi Keşfet")
    def arama_degisti():
        st.session_state.sayfa = 1
        st.session_state.scroll_to_top = True
        st.session_state.pop("arama_sonuclari", None)
        st.session_state.pop("last_search_state", None)

    arama_metni = st.text_input(
        "Ne tür bir dizi arıyorsun?", 
        placeholder="Örn: Sürükleyici dedektiflik polisiyeleri...", 
        key="son_arama",
        on_change=arama_degisti
    )
    
    if st.button("🚀 Dizileri Listele"):
        arama_degisti()
        st.rerun()
    
    # 🧠 Akıllı Arama Önbellekleme: Sayfa geçişlerinde yapay zekayı ve random sıralamayı korumak için durum kontrolü yapıyoruz
    current_search_state = {
        "arama_metni": arama_metni,
        "kullanici_puan": kullanici_puan,
        "kullanici_sezon": kullanici_sezon,
        "min_oy_sayisi": min_oy_sayisi,
        "secilen_turler": secilen_turler,
        "secilen_platformlar": secilen_platformlar,
        "sadece_bitmis": sadece_bitmis,
        "siralam_secenegi": siralam_secenegi,
        "kullanici_esik": kullanici_esik,
        "otomatik_izlenenler": otomatik_izlenenler
    }
    
    if st.session_state.get("last_search_state") == current_search_state and "arama_sonuclari" in st.session_state:
        sonuclar = st.session_state.arama_sonuclari
    else:
        sonuclar = yapay_zeka_semantik_oner_yeni(
            arama_metni, kullanici_puan, kullanici_sezon, min_oy_sayisi, 
            secilen_turler, min_yil, otomatik_izlenenler, 
            secilen_platformlar, sadece_bitmis, siralam_secenegi,
            dizi_havuzu_df, dizi_vektorleri, model, esik_degeri=kullanici_esik / 100
        )
        
        # 🧠 GPT-4o mini Entegrasyonu (Huni Modeli)
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        
        # Sadece arama metni girilmişse, API anahtarı varsa, sonuç boş değilse ve kullanıcı GİRİŞ YAPMIŞSA çalıştır
        is_logged_in = st.session_state.get("logged_in", False)
        if api_key and arama_metni.strip() and sonuclar is not None and not sonuclar.empty and is_logged_in:
            username_str = st.session_state.get("username") or "Dizi Sever"
            
            # 🛡️ KALICI HIZ SINIRLAYICI (DB-Backed Rate Limiter): Dakikada maks 5 AI sorgusu
            if not f_yeni.ai_sorgusu_limitle_ve_kaydet(username_str):
                st.toast("⚠️ Yapay zeka arama limiti aşıldı (Dakikada maks. 5 arama). Normal arama sonuçları gösteriliyor.", icon="⏳")
            else:
                reasons_dict, ordered_names = {}, None
                # Sinonim/doğrudan eşleşme durumunda gereksiz API çağrısını engellemek için kontrol
                # Eğer sorgu doğrudan bir dizinin ismiyle birebir eşleşiyorsa GPT'yi çağırmıyoruz
                tam_eslesme = sonuclar[sonuclar['isim'].str.lower() == arama_metni.strip().lower()]
                if tam_eslesme.empty:
                    # İlk 15 diziyi seç
                    top_15 = sonuclar.head(15).copy()
                    username_str = st.session_state.get("username") or "Dizi Sever"
                    
                    # GPT-4o mini'ye gönder
                    reasons_dict, ordered_names = f_yeni.gpt4o_ile_arama_sirala_ve_yorumla(
                        arama_metni, top_15, username_str
                    )
                
                if ordered_names:
                    # Yeni bir 'ai_reason' kolonu ekle
                    sonuclar['ai_reason'] = None
                    for d_name, reason in reasons_dict.items():
                        sonuclar.loc[sonuclar['isim'] == d_name, 'ai_reason'] = reason
                    
                    # İlk 15 diziyi GPT-4o mini'nin sıralamasına göre yeniden diz
                    order_mapping = {name: idx for idx, name in enumerate(ordered_names)}
                    
                    # Sıralanan dizilerin geçici DataFrame'ini al
                    top_15_reordered = sonuclar[sonuclar['isim'].isin(ordered_names)].copy()
                    top_15_reordered['temp_rank'] = top_15_reordered['isim'].map(order_mapping)
                    top_15_reordered = top_15_reordered.sort_values('temp_rank').drop(columns=['temp_rank'])
                    
                    # Align similarity percentages to match the new GPT rank order descendingly
                    sorted_sims = sorted(top_15_reordered['benzerlik_orani'].tolist(), reverse=True)
                    sorted_eslesme = sorted(top_15_reordered['Eşleşme Oranı'].tolist(), reverse=True)
                    top_15_reordered['benzerlik_orani'] = sorted_sims
                    top_15_reordered['Eşleşme Oranı'] = sorted_eslesme
                    
                    # Geri kalan dizileri al
                    others = sonuclar[~sonuclar['isim'].isin(ordered_names)].copy()
                    
                    # Birleştirerek nihai DataFrame'i oluştur
                    sonuclar = pd.concat([top_15_reordered, others], ignore_index=True)
                    
        st.session_state.arama_sonuclari = sonuclar
        st.session_state.last_search_state = current_search_state
    
    kesfet_sonuc_alani = st.empty()
    with kesfet_sonuc_alani.container():
        if sonuclar is None or sonuclar.empty:
            st.info("Bu kriterlere uygun dizi bulunamadı.")
        else:
            toplam_dizi = len(sonuclar)
            limit = st.session_state.get('gosterim_adedi', 5)
            toplam_sayfa = max(1, (toplam_dizi + limit - 1) // limit)

            if st.session_state.get('sayfa', 1) > toplam_sayfa:
                st.session_state.sayfa = toplam_sayfa
            if st.session_state.get('sayfa', 1) < 1:
                st.session_state.sayfa = 1

            baslangic = (st.session_state.sayfa - 1) * limit
            sonuclar_slice = sonuclar.iloc[baslangic : baslangic + limit]
        
            if not st.session_state.get("logged_in", False) and arama_metni.strip():
                st.markdown("""
                <div style="background: rgba(168, 85, 247, 0.05); border: 1px solid rgba(168, 85, 247, 0.2); padding: 12px 16px; border-radius: 8px; margin-bottom: 20px;">
                    <span style="font-size: 14px; color: #c084fc; font-weight: bold; display: flex; align-items: center; gap: 6px;">
                        ✨ Yapay Zeka Keşif Motoru Pasif
                    </span>
                    <div style="font-size: 13px; color: #e5e7eb; margin-top: 4px; line-height: 1.4;">
                        Dizileri yapay zeka ile kişiselleştirip analiz ettirmek için lütfen giriş yapın. Şu an ücretsiz ve standart yerel vektör araması sonuçlarını görüyorsunuz.
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown(
                f"<p style='color:#a855f7; font-weight:bold; margin-bottom:15px;'>"
                f"Toplam {toplam_dizi} sonuçtan {baslangic + 1}-{min(baslangic + limit, toplam_dizi)} arası gösteriliyor.</p>",
                unsafe_allow_html=True
            )

            for idx, row in sonuclar_slice.iterrows():
                st.markdown('<div class="dizi-kart-wrapper">', unsafe_allow_html=True)
                with st.container(border=True):
                    col1, col2 = st.columns([1.2, 4])
                
                    with col1:
                        st.image(row['afis_url'], use_container_width=True)
                
                    with col2:
                        escaped_isim = html.escape(str(row['isim']))
                        st.markdown(f"<h2>{escaped_isim}</h2>", unsafe_allow_html=True)
                    
                        toplam_bolum = row.get('toplam_bolum_sayisi')
                        toplam_bolum = int(float(toplam_bolum)) if pd.notna(toplam_bolum) else '?'
                    
                        st.markdown(f"""
                        <div style="display: flex; gap: 10px; margin: 8px 0; flex-wrap: wrap;">
                            <span class="etiket-puan">⭐ {row.get('puan_ortalamasi', '?')}/10</span>
                            <span class="etiket-surec">📅 {row.get('sezon_sayisi', '?')} Sezon ({toplam_bolum} Bölüm)</span>
                            <span class="etiket-sure">⏳ {row.get('gercek_bolum_sureleri', '?')} dk</span>
                        </div>
                        """, unsafe_allow_html=True)

                        platform_html = platform_linklerini_olustur(row.get('platformlar', ''), row.get('isim', ''))
                        escaped_durum = html.escape(str(row.get('durum', 'Bilinmiyor')))
                        st.markdown(f"📺 {platform_html} | 📌 `{escaped_durum}`", unsafe_allow_html=True)
                        st.write(f"🎭 {row.get('tur', 'Tür yok')}")

                        if row.get('Eşleşme Oranı', 0) > 0:
                            st.markdown(f'<span class="etiket-ai">🎯 %{row["Eşleşme Oranı"]}</span>', unsafe_allow_html=True)

                        ozet_metni = row.get('ozet')
                        if not ozet_metni or ozet_metni == 'None':
                            ozet_metni = ozet_getir_veya_uret(row.get('isim', ''), row.get('tur', ''))
                    
                        st.write(f"**Özet:** {ozet_metni}")
                        efsanevi_ikili_goster(row.get('efsanevi_ikili'), key_suffix=f"tab1_{row.get('id', row.get('isim'))}")
                    
                        # ✨ Yapay Zeka Analizi mor kutusu
                        if 'ai_reason' in row and pd.notna(row['ai_reason']) and row['ai_reason']:
                            escaped_ai_reason = html.escape(str(row['ai_reason']))
                            st.markdown(f"""
                            <div style="background: rgba(168, 85, 247, 0.08); border-left: 4px solid #a855f7; padding: 10px 14px; border-radius: 6px; margin: 10px 0 15px 0;">
                                <span style="font-size: 11px; color: #c084fc; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;">✨ Yapay Zeka Analizi</span>
                                <div style="font-size: 13.5px; color: #e5e7eb; margin-top: 3px; font-weight: 500; line-height: 1.4;">{escaped_ai_reason}</div>
                            </div>
                            """, unsafe_allow_html=True)
                    
                        # Neden İzlemelisin Bilgisi (Önbellekten Hızlı Gösterim / İstek Üzerine Canlı Üretim)
                        neden_veri = row.get('neden_izlemeli')
                        maddeler = []
                        if neden_veri and str(neden_veri).strip() and neden_veri != "None":
                            try:
                                maddeler = json.loads(neden_veri)
                            except Exception:
                                pass
                    
                        if isinstance(maddeler, list) and len(maddeler) == 3:
                            st.markdown("##### 💡 Neden İzlemelisin?")
                            for m in maddeler:
                                st.markdown(f"- {m}")
                        else:
                            if st.button("💡 Neden İzlemeliyim? (AI'a Sor)", key=f"ask_ai_neden_{row['isim']}_{idx}"):
                                with st.spinner("Yapay zeka neden izlemen gerektiğini analiz ediyor..."):
                                    maddeler = yapay_zeka_neden_izlemeli_uret(row['isim'], row['tur'])
                                    if maddeler and len(maddeler) == 3 and "özel değerlendirme hazırlanıyor" not in maddeler[0]:
                                        st.toast(f"✅ {row['isim']} için neden izlemelisin maddeleri başarıyla oluşturuldu!", icon="✨")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error("⚠️ Yapay zeka şu an yoğun, lütfen birazdan tekrar deneyin.")
                
                    # Butonları konteynerin içinde alt kısma yerleştir
                    btn1, btn2, btn3 = st.columns([1.5, 1.5, 1.5]) 
                    with btn1:
                        if st.button("➕ Kitaplığa Ekle", key=f"add_{row['isim']}_{idx}", use_container_width=True):
                            if not st.session_state.logged_in:
                                st.session_state.show_login_trigger = True
                                st.rerun()
                            else:
                                basarili_mi = kitapliga_dizi_ekle_veya_güncelle(st.session_state.username, row['isim'], 'İzleyeceğim', 1, 1)
                                if basarili_mi:
                                    st.toast(f"✅ {row['isim']} kitaplığına eklendi!")
                                else:
                                    st.toast("⚠️ Bu dizi zaten kitaplığında mevcut!")
                                st.session_state.pop("kitaplik_df", None)
                                st.session_state.pop("kullanici_rozetleri", None)
                                st.rerun()
                            
                    with btn2:
                        is_liked = row['isim'] in st.session_state.pozitif_feedbacks
                        if st.button("👍 Beğen", key=f"like_{row['isim']}_{idx}", disabled=is_liked, use_container_width=True):
                            dizi_islem_kaydet(st.session_state.username, row['isim'], "begenilenler")
                            st.session_state.pozitif_feedbacks = kullanicinin_listesini_getir(st.session_state.username, "begenilenler")
                            st.rerun()
                            
                    with btn3:
                        is_disliked = row['isim'] in st.session_state.negatif_feedbacks
                        if st.button("👎 Gizle", key=f"dislike_{row['isim']}_{idx}", disabled=is_disliked, use_container_width=True):
                            dizi_islem_kaydet(st.session_state.username, row['isim'], "gizlenenler")
                            if row['isim'] in st.session_state.pozitif_feedbacks:
                                dizi_listeden_sil(st.session_state.username, row['isim'], "begenilenler")
                                st.session_state.pozitif_feedbacks = kullanicinin_listesini_getir(st.session_state.username, "begenilenler")
                            st.session_state.negatif_feedbacks = kullanicinin_listesini_getir(st.session_state.username, "gizlenenler")
                            st.rerun()
            
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("---")
            col1, col2, col3 = st.columns([1, 2, 1])
        
            with col1:
                if st.session_state.sayfa > 1:
                    if st.button("⬅️ Önceki", key="kesfet_prev_bottom", use_container_width=True):
                        st.session_state.sayfa -= 1
                        st.session_state.scroll_to_top = True
                        st.rerun()
                    
            with col2:
                st.markdown(f"<p style='text-align:center; color:#a855f7; font-weight:bold; margin-top:8px;'>Sayfa {st.session_state.sayfa} / {toplam_sayfa}</p>", unsafe_allow_html=True)
            
            with col3:
                if st.session_state.sayfa < toplam_sayfa:
                    if st.button("Sonraki ➡️", key="kesfet_next_bottom", use_container_width=True):
                        st.session_state.sayfa += 1
                        st.session_state.scroll_to_top = True
                        st.rerun()


# ==============================================================================
# --- 9. TAB 2: KİTAPLIĞIM SEKME GİRİŞİ ---
# ==============================================================================
with tab2:
    if not st.session_state.logged_in:
        st.warning("🔒 Kitaplık Cetvelini kullanmak ve izleme sürelerinizi hesaplamak için lütfen sol üst köşeden giriş yapın.")
    else:
        st.subheader("📚 Kişisel Takip Kitaplığınız")
        
        kitaplik_df = kitaplik_tumu_df
        
        if kitaplik_df.empty:
            st.info("Kitaplığınızda henüz kayıtlı bir dizi bulunmamaktadır. Aşağıdaki menüden manuel ekleme yapabilirsiniz.")
        else:
            kitap_meta_df = dizi_havuzu_df[dizi_havuzu_df['isim'].isin(kitaplik_df['dizi_isim'].tolist())].copy()
            
            # İzleme Süresi Göstergesi
            sure_metni, toplam_dizi_sayisi = toplam_izleme_suresini_hesapla(kitaplik_df, dizi_havuzu_df)
            st.markdown("### 📊 Genel İzleme İstatistikleri")
            metric_c1, metric_c2 = st.columns(2)
            metric_c1.metric("⏳ Toplam İzleme Süresi", sure_metni)
            metric_c2.metric("🎬 Takip Edilen Yapım Sayısı", f"{toplam_dizi_sayisi} Adet")
            
            # --- ROZETLER VE BAŞARIMLAR BÖLÜMÜ ---
            with st.expander("🏆 Kazanılan Başarımlar ve Rozetler", expanded=False, key="rozetler_expander"):
                rozet_data = st.session_state.kullanici_rozetleri
                
                rozet_tanimlari = {
                    "ekran_bagimlisi": ("🍿", "Ekran Bağımlısı", "İzlediğin toplam dizi sayısı"),
                    "koltuk_patatesi": ("📺", "Koltuk Patatesi", "Toplam izleme süresi (Saat)"),
                    "netflix_gurmesi": ("🎬", "Netflix Gurmesi", "İzlenen Netflix dizileri"),
                    "prime_secici": ("🎁", "Prime Seçici", "İzlenen Prime Video dizileri"),
                    "disney_seyyahi": ("🏰", "Disney Seyyahı", "İzlenen Disney Plus dizileri"),
                    "gizli_cevher": ("💎", "Gizli Cevher Avcısı", "Popüler olmayan (200-400 oy) dizileri keşfetme"),
                    "dram_sever": ("🎭", "Dram Sever", "İzlenen dram dizileri"),
                    "bilimkurgu_kasifi": ("🚀", "Bilimkurgu Kaşifi", "İzlenen bilimkurgu/gizem dizileri"),
                    "kahkaha_makinesi": ("😂", "Kahkaha Makinesi", "İzlenen komedi/sitcom dizileri"),
                    "suc_ortagi": ("🕵️", "Suç Ortağı", "İzlenen suç/polisiye dizileri"),
                    "sosyal_kelebek": ("🤝", "Sosyal Kelebek", "Kazanılan arkadaş sayısı"),
                    "kritik_zihin": ("✍️", "Kritik Zihin", "Puan verdiğin dizi sayısı"),
                    "koleksiyoner": ("🏆", "Koleksiyoner", "Kazanılan toplam rozet sayısı"),
                    "efsane": ("👑", "Efsane (Gizli)", "Altın/Elmas rozet toplama başarısı")
                }
                
                cols = st.columns(3)
                idx = 0
                for r_key, (emoji, isim, aciklama) in rozet_tanimlari.items():
                    info = rozet_data.get(r_key)
                    if not info: continue
                    
                    seviye = info["seviye"]
                    deger = info["deger"]
                    hedef = info["hedef"]
                    oran = info["oran"]
                    sonraki_seviye = info["sonraki_seviye"]
                    
                    seviye_str = "KİLİTLİ" if seviye is None else seviye.upper()
                    
                    with cols[idx % 3]:
                        resim_yolu = "assets/badges/badge_popcorn.jpg" if r_key == "ekran_bagimlisi" else f"assets/badges/badge_{r_key}.jpg"
                        resim_html = ""
                        
                        if os.path.exists(resim_yolu):
                            abs_path = os.path.abspath(resim_yolu).replace("\\", "/")
                            resim_html = f'<img src="file:///{abs_path}" class="rozet-daire rozet-{seviye or "kilitli"}" style="object-fit: cover !important; border-radius: 50% !important;" />'
                        else:
                            resim_html = f'<div class="rozet-daire rozet-{seviye or "kilitli"}">{emoji}</div>'
                            
                        card_html = f"""
                        <div class="rozet-kart">
                            {resim_html}
                            <div style="font-weight: bold; font-size: 16px; margin-top: 5px; color: white;">{isim}</div>
                            <div style="font-size: 12px; color: #a855f7; font-weight: bold;">{seviye_str}</div>
                            <div style="font-size: 11px; color: #9ca3af; margin: 4px 0;">{aciklama}</div>
                        """
                        st.markdown(card_html, unsafe_allow_html=True)
                        
                        if hedef:
                            st.progress(oran, text=f"{int(deger)} / {hedef} ({sonraki_seviye.upper()})")
                        else:
                            st.progress(1.0, text=f"MAKSİMUM SEVİYE ({int(deger)})")
                            
                        st.markdown("</div>", unsafe_allow_html=True)
                    idx += 1
            
            if not kitap_meta_df.empty:
                def grafik_ciz(df, sutun):
                    data = df[sutun].fillna('').astype(str).str.split(',').explode().str.strip()
                    data = data[data != ''].value_counts().reset_index()
                    data.columns = ['Kategori', 'Adet']
                    
                    chart = alt.Chart(data).mark_bar(color='#76c7ff', size=15).encode(
                        x=alt.X('Adet:Q', title='İzlenme Sayısı', axis=alt.Axis(tickMinStep=1)),
                        y=alt.Y('Kategori:N', sort='-x', title=None, axis=alt.Axis(labelAngle=0)), 
                        tooltip=['Kategori', 'Adet']
                    ).properties(
                        height=250
                    ).configure_axis(
                        labelFontSize=12
                    ).configure_view(
                        strokeWidth=0
                    )
                    return chart

                dash_col1, dash_col2 = st.columns(2)
                
                with dash_col1:
                    st.caption("📺 Platform Tercih Dağılımınız")
                    st.altair_chart(grafik_ciz(kitap_meta_df, 'platformlar'), use_container_width=True)
                
                with dash_col2:
                    st.caption("🎭 Favori Tür Dağılımınız")
                    st.altair_chart(grafik_ciz(kitap_meta_df, 'tur'), use_container_width=True)

        with st.expander("➕ Manuel Dizi Ekleme"):
            eklenecek_dizi = st.selectbox("🔍 Dizi ara...", options=tum_diziler, index=None, key="man_add_select_box")
            
            if eklenecek_dizi:
                eslesen_meta = dizi_havuzu_df[dizi_havuzu_df['isim'] == eklenecek_dizi].iloc[0]
                bolum_listesi = [int(x) for x in str(eslesen_meta.get('sezon_bolum_haritasi', '1')).split(',')]
                
                izledi_checkbox = st.checkbox("✅ İzledim", key="izledim_checkbox")
                durum = "İzledim" if izledi_checkbox else st.selectbox("Durum", ["İzliyorum", "İzleyeceğim", "Yarıda Bıraktım"], key="durum_select")
                
                c_s, c_b = st.columns(2)
                sezon = c_s.number_input("Sezon", 1, int(eslesen_meta['sezon_sayisi']), 1)
                
                max_bolum = bolum_listesi[sezon - 1] if sezon <= len(bolum_listesi) else 1
                bolum = c_b.number_input("Bölüm", 1, int(max_bolum), 1)
                
                if st.button("Kaydı Tamamla", use_container_width=True, key="save_btn"):
                    if izledi_checkbox:
                        kayit_sezon = int(eslesen_meta['sezon_sayisi'])
                        kayit_bolum = bolum_listesi[-1]
                        kayit_durum = "İzledim"
                    else:
                        kayit_sezon, kayit_bolum, kayit_durum = sezon, bolum, durum
                    
                    kitapliga_dizi_ekle_veya_güncelle(st.session_state.username, eklenecek_dizi, kayit_durum, kayit_sezon, kayit_bolum)
                    st.toast(f"{eklenecek_dizi} kitaplığa eklendi!", icon="✅")
                    st.session_state.pop("kitaplik_df", None)
                    st.session_state.pop("kullanici_rozetleri", None)
                    st.rerun()

    if st.session_state.logged_in and not kitaplik_df.empty:
        kitaplik_df = kitaplik_df.sort_values(by='id', ascending=False)
        alt_sekme = st.radio("Duruma Göre Listele:", ["Tümü", "İzliyorum", "İzleyeceğim", "İzledim", "Yarıda Bıraktım"], horizontal=True)
        df_filtreli = kitaplik_df if alt_sekme == "Tümü" else kitaplik_df[kitaplik_df['durum'] == alt_sekme]
        
        if st.session_state.get("last_alt_sekme") != alt_sekme:
            st.session_state.kitaplik_sayfa = 0
            st.session_state.last_alt_sekme = alt_sekme

        sayfa_buyuklugu = 10
        toplam_sayfa = max(1, (len(df_filtreli) + sayfa_buyuklugu - 1) // sayfa_buyuklugu)
        baslangic = st.session_state.get("kitaplik_sayfa", 0) * sayfa_buyuklugu
        df_sayfali = df_filtreli.iloc[baslangic : baslangic + sayfa_buyuklugu]

        favoriler_listesi = kullanıcı_favorilerini_getir(st.session_state.username)['dizi_isim'].tolist() if st.session_state.logged_in else []

        for _, row in df_sayfali.iterrows():
            st.markdown('<div class="dizi-kart-wrapper">', unsafe_allow_html=True)
            with st.container(border=True):
                c_a, c_d = st.columns([1.2, 4])
            
            meta = dizi_havuzu_df[dizi_havuzu_df['isim'] == row['dizi_isim']].iloc[0]
            with c_a:
                st.image(meta.get('afis_url', ''), use_container_width=True)
            
            with c_d:
                col_i, col_u, col_o = st.columns([3, 2, 2])
                col_i.markdown(f"#### {row['dizi_isim']}")
                col_i.write(f"⭐ Genel Puan: {meta.get('puan_ortalamasi', 'N/A')} | 🎞️ {sum([int(x) for x in str(meta['sezon_bolum_haritasi']).split(',')])} Bölüm | 📌 Durum: `{meta.get('durum', 'Bilinmiyor')}`")
                
                # Platform Bilgisi
                plat_html = platform_linklerini_olustur(meta.get('platformlar', ''), row['dizi_isim'])
                col_i.markdown(f"📺 **Yayınlandığı Platformlar:** {plat_html}", unsafe_allow_html=True)
                
                puan = int(row.get('puan', 0)) if pd.notna(row.get('puan')) else 0
                yildizlar = "⭐" * puan if puan > 0 else "Puanlanmadı"
                
                col_u.caption(f"📌 {row['durum']}")
                
                # Bölüm bilgisi ve +1 Bölüm butonu yan yana (Kompakt ve estetik)
                col_u_l, col_u_r = col_u.columns([1, 2.5], gap="small")
                col_u_l.write(f"📺 S{row['izlenen_sezon']} B{row['izlenen_bolum']}")
                
                harita = [int(x) for x in str(meta['sezon_bolum_haritasi']).split(',')]
                curr_s = int(row['izlenen_sezon'])
                curr_b = int(row['izlenen_bolum'])
                son_sezon = len(harita)
                
                if row['durum'] != "İzledim":
                    yeni_s = curr_s
                    yeni_b = curr_b
                    
                    if curr_b < harita[curr_s - 1]:
                        yeni_b = curr_b + 1
                    elif curr_s < son_sezon:
                        yeni_s = curr_s + 1
                        yeni_b = 1
                        
                    if col_u_r.button("➕", key=f"inc_{row['id']}", help="Sonraki bölümü izlendi olarak işaretle"):
                        kitaplik_ilerleme_guncelle(row['id'], yeni_s, yeni_b, row['dizi_isim'], dizi_havuzu_df, yeni_puan=puan, username=st.session_state.username)
                        st.toast(f"⏭️ {row['dizi_isim']} - Yeni İlerleme: S{yeni_s} B{yeni_b}", icon="📺")
                        st.session_state.pop("kitaplik_df", None)
                        st.rerun()
                
                col_u.markdown(f"**Senin Puanın:** {yildizlar}")
                
                is_fav = row['dizi_isim'] in favoriler_listesi
                
                with col_o:
                    with st.popover("⚙️ Düzenle", use_container_width=True):
                        yeni_s = st.number_input("Sezon:", 1, int(meta['sezon_sayisi']), max(1, int(row['izlenen_sezon'])), key=f"s_{row['id']}")
                        yeni_b = st.number_input("Bölüm:", 1, int(harita[yeni_s-1]), max(1, int(row['izlenen_bolum'])), key=f"b_{row['id']}")
                        
                        mevcut_puan = int(row.get('puan', 0)) if pd.notna(row.get('puan')) else 0
                        puan_etiketi = f"Puanınız: {mevcut_puan} ⭐" if mevcut_puan > 0 else "Henüz puanlamadınız"
                        yeni_puan = st.slider("Dizi Puanı (1-5 ⭐):", 1, 5, value=max(1, mevcut_puan) if mevcut_puan > 0 else 5, key=f"puan_sld_{row['id']}", help=puan_etiketi)
                        
                        if st.button("Güncelle", key=f"upd_{row['id']}", use_container_width=True):
                            kitaplik_ilerleme_guncelle(row['id'], yeni_s, yeni_b, row['dizi_isim'], dizi_havuzu_df, yeni_puan=yeni_puan, username=st.session_state.username)
                            st.toast(f"Puan ve İlerleme güncellendi!", icon="✅")
                            st.session_state.pop("kitaplik_df", None)
                            st.rerun()
                    
                    # Diziyi Bitirdim Butonu
                    if row['durum'] != "İzledim":
                        if st.button("✔️ Bitirdim", key=f"complete_{row['id']}", use_container_width=True, help="Diziyi tamamen bitir"):
                            son_s = len(harita)
                            son_b = harita[son_s - 1]
                            kitaplik_ilerleme_guncelle(row['id'], son_s, son_b, row['dizi_isim'], dizi_havuzu_df, yeni_puan=puan, username=st.session_state.username)
                            st.toast(f"🎉 Tebrikler! {row['dizi_isim']} tamamen bitirildi!", icon="🏆")
                            st.session_state.pop("kitaplik_df", None)
                            st.rerun()
                    
                    # Favoriye Ekle / Çıkar
                    if is_fav:
                        if st.button("❤️ Favorilerden Çıkar", key=f"fav_rem_{row['id']}", use_container_width=True):
                            favori_sil(st.session_state.username, row['dizi_isim'])
                            st.toast("Dizi favorilerden kaldırıldı.", icon="💔")
                            st.rerun()
                    else:
                        if st.button("🤍 Favoriye Ekle", key=f"fav_add_{row['id']}", use_container_width=True):
                            favoriye_ekle(st.session_state.username, row['dizi_isim'])
                            st.toast("Dizi favorilere eklendi!", icon="💖")
                            st.rerun()
                    
                    # Sil Butonu
                    if st.button("🗑️ Sil", key=f"del_{row['id']}", use_container_width=True):
                        kitapliktan_kayit_sil(row['id'], st.session_state.username)
                        st.toast("Dizi kitaplıktan silindi.", icon="🗑️")
                        st.session_state.pop("kitaplik_df", None)
                        st.session_state.pop("kullanici_rozetleri", None)
                        st.rerun()
                
                # Açılır kapanır detaylı özet
                st.markdown("---")
                efsanevi_ikili_goster(meta.get('efsanevi_ikili'), key_suffix=f"tab2_{row['id']}")
                with st.expander("📝 Detaylı Özet"):
                    st.write(meta.get('ozet', 'Özet bilgisi bulunamadı.'))
            st.markdown('</div>', unsafe_allow_html=True)
                            
        c_prev, c_page, c_next = st.columns([1, 2, 1])
        if c_prev.button("⬅️ Önceki", disabled=(st.session_state.get("kitaplik_sayfa", 0) == 0)):
            st.session_state.kitaplik_sayfa -= 1
            st.session_state.scroll_to_top = True
            st.rerun()
        c_page.markdown(f"<p style='text-align:center;'>Sayfa {st.session_state.get('kitaplik_sayfa', 0) + 1} / {toplam_sayfa}</p>", unsafe_allow_html=True)
        if c_next.button("Sonraki ➡️", disabled=(st.session_state.get("kitaplik_sayfa", 0) >= toplam_sayfa - 1)):
            st.session_state.kitaplik_sayfa += 1
            st.session_state.scroll_to_top = True
            st.rerun()


# ==============================================================================
# --- 10. TAB 3: FAVORİ DİZİLERİNİZ SEKMESİ ---
# ==============================================================================
with tab3:
    st.subheader("❤️ Favori Dizileriniz")
    
    if not st.session_state.logged_in:
        st.info("🔒 Favori dizilerinizi listelemek için giriş yapmalısınız.")
    else:
        fav_df = kullanıcı_favorilerini_getir(st.session_state.username)
        
        if fav_df is None or fav_df.empty:
            st.info("Favori listeniz henüz boş.")
        else:
            fav_df = fav_df.sort_values(by='kitaplik_id', ascending=False)
            
            if "fav_sayfa" not in st.session_state: 
                st.session_state.fav_sayfa = 0
            
            sayfa_buyuklugu = 10
            toplam_sayfa = max(1, (len(fav_df) // sayfa_buyuklugu) + (1 if len(fav_df) % sayfa_buyuklugu > 0 else 0))
            
            baslangic = st.session_state.fav_sayfa * sayfa_buyuklugu
            fav_df_sayfali = fav_df.iloc[baslangic : baslangic + sayfa_buyuklugu]
            
            for _, row in fav_df_sayfali.iterrows():
                st.markdown('<div class="dizi-kart-wrapper">', unsafe_allow_html=True)
                with st.container(border=True):
                    col1, col2 = st.columns([1, 4])
                
                dizi_ismi = row.get('dizi_isim')
                meta = dizi_havuzu_df[dizi_havuzu_df['isim'] == dizi_ismi]
                
                with col1:
                    if not meta.empty and pd.notna(meta.iloc[0].get('afis_url')):
                        st.image(meta.iloc[0]['afis_url'], use_container_width=True)
                    else:
                        st.write("🖼️")
                
                with col2:
                    st.markdown(f"### {dizi_ismi}")
                    if not meta.empty:
                        dizi_meta = meta.iloc[0]
                        harita = [int(x) for x in str(dizi_meta.get('sezon_bolum_haritasi', '0')).split(',')]
                        toplam_bolum = sum(harita)
                        st.write(f"⭐ **Puan:** {dizi_meta.get('puan_ortalamasi', 'N/A')}/10 | 🎞️ **Bölüm:** {dizi_meta.get('sezon_sayisi', '?')} Sezon ({toplam_bolum} Bölüm) | 📌 **Durum:** `{dizi_meta.get('durum', 'Bilinmiyor')}`")
                        
                        plat_html = platform_linklerini_olustur(dizi_meta.get('platformlar', ''), dizi_ismi)
                        st.markdown(f"📺 **Yayınlandığı Platformlar:** {plat_html}", unsafe_allow_html=True)
                        
                        efsanevi_ikili_goster(dizi_meta.get('efsanevi_ikili'), key_suffix=f"tab3_{row['kitaplik_id']}")
                        with st.expander("📝 Özet"):
                            st.write(dizi_meta.get('ozet', 'Özet bilgisi bulunamadı.'))
                    
                    if st.button("💔 Favorilerden Kaldır", key=f"rem_fav_{row['kitaplik_id']}"):
                        favori_sil(st.session_state.username, dizi_ismi)
                        st.rerun()
                
                st.markdown('</div>', unsafe_allow_html=True)

            c_prev, c_page, c_next = st.columns([1, 2, 1])
            with c_prev:
                if st.button("⬅️ Önceki", key="fav_prev_btn", disabled=(st.session_state.fav_sayfa == 0)):
                    st.session_state.fav_sayfa -= 1
                    st.session_state.scroll_to_top = True
                    st.rerun()
            with c_page:
                st.write(f"Sayfa {st.session_state.fav_sayfa + 1} / {toplam_sayfa}")
            with c_next:
                if st.button("Sonraki ➡️", key="fav_next_btn", disabled=(st.session_state.fav_sayfa >= toplam_sayfa - 1)):
                    st.session_state.fav_sayfa += 1
                    st.session_state.scroll_to_top = True
                    st.rerun()


# ==============================================================================
# --- 11. TAB 4: YAPAY ZEKA PROFİL TAVSİYELERİ ---
# ==============================================================================
with tab4:
    st.subheader("✨ İzleme Geçmişinize Göre Özel Öneriler")
    
    if not st.session_state.logged_in:
        st.info("🔒 İzleme geçmişinize dayalı yapay zeka tavsiyeleri için giriş yapmalısınız.")
    else:
        kullanici_kutuphane = kitaplik_tumu_df
        aktif_izlenenler = []
        if not kullanici_kutuphane.empty:
            aktif_izlenenler = kullanici_kutuphane[kullanici_kutuphane['durum'].isin(["İzledim", "İzliyorum"])]['dizi_isim'].tolist()

        if not aktif_izlenenler:
            st.info("💡 İpucu: Kişiselleştirilmiş öneriler alabilmek için kütüphanenize en az bir diziyi 'İzledim' veya 'İzliyorum' olarak ekleyin.")
        else:
            with st.spinner("İzleme profiliniz derinlemesine analiz ediliyor..."):
                tum_tavsiyeler = profil_bazli_tavsiye_uret_akilli(
                    st.session_state.username,
                    kullanici_puan, 
                    kullanici_sezon, 
                    min_oy_sayisi, 
                    min_yil, 
                    secilen_platformlar,
                    dizi_havuzu_df, 
                    dizi_vektorleri
                )
                
            if tum_tavsiyeler is None or tum_tavsiyeler.empty:
                st.warning("Kriterlerinize uygun yeni bir öneri bulunamadı.")
            else:
                for idx, row in tum_tavsiyeler.iterrows():
                    st.markdown('<div class="dizi-kart-wrapper">', unsafe_allow_html=True)
                    with st.container(border=True):
                        col1, col2 = st.columns([1.2, 4])
                    with col1:
                        st.image(row.get('afis_url', ''), use_container_width=True)
                    
                    with col2:
                        st.markdown(f"### {row['isim']}")
                        
                        toplam_bolum = int(float(row.get('toplam_bolum_sayisi', 0))) if pd.notna(row.get('toplam_bolum_sayisi')) else '?'
                        st.write(f"⭐ **{row['puan_ortalamasi']}** | 📅 **{row['sezon_sayisi']}** Sezon ({toplam_bolum} Bölüm) | 🎭 **{row['tur']}**")
                        
                        plat_html = platform_linklerini_olustur(row.get('platformlar', ''), row['isim'])
                        st.markdown(f"📺 **Yayınlandığı Platformlar:** {plat_html} | 📌 **Durum:** `{row.get('durum', 'Bilinmiyor')}`", unsafe_allow_html=True)
                        
                        st.markdown(f"""
                        <div style="display: flex; gap: 10px; margin: 8px 0; flex-wrap: wrap;">
                            <span style="background-color: #4f46e5; color: white; padding: 3px 8px; border-radius: 5px; font-size: 12px;">🎯 Tür Uyumu: %{row['tur_uyumu_yuzde']}</span>
                            <span style="background-color: #0891b2; color: white; padding: 3px 8px; border-radius: 5px; font-size: 12px;">⏳ Süre Uyumu: %{row['sure_uyumu_yuzde']}</span>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.markdown("##### 💡 Neden İzlemelisin?")
                        nedenler = yapay_zeka_neden_izlemeli_uret(row['isim'], row['tur'])
                        for neden in nedenler:
                            st.markdown(f"- {neden}")
                        
                        st.markdown("---")
                        efsanevi_ikili_goster(row.get('efsanevi_ikili'), key_suffix=f"tab4_{row['isim']}_{idx}")
                        with st.expander("📝 Detaylı Özet"):
                            st.write(row.get('ozet', 'Özet bilgisi bulunamadı.'))
                        
                        st.info(f"👉 Bu yapım, kütüphanendeki **'{row['en_yakin_dizi_gerekce']}'** dizisine olan yüksek benzerliği nedeniyle seçildi.")
                        
                        if st.button("➕ Kitaplığa Ekle", key=f"rec_add_akilli_{row['isim']}_{idx}"):
                            if kitapliga_dizi_ekle_veya_güncelle(st.session_state.username, row['isim'], 'İzleyeceğim', 1, 1):
                                st.toast(f"{row['isim']} kitaplığa eklendi!", icon="✅")
                                st.session_state.pop("kitaplik_df", None)
                                st.session_state.pop("kullanici_rozetleri", None)
                                st.rerun()
                            else:
                                st.warning("Bu dizi zaten kitaplığında!")
                    
                    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# --- 12. TAB 5: GERİ BİLDİRİM VE TERCİH YÖNETİMİ ---
# ==============================================================================
with tab5:
    if not st.session_state.logged_in:
        st.info("🔒 Geri bildirimlerinizi yönetmek için giriş yapmalısınız.")
    else:
        st.subheader("⚙️ Geri Bildirim ve Tercih Yönetimi")
        
        feedback = st.text_area("Sistemi nasıl geliştirebiliriz?", height=150, key="feedback_text_area")
        if st.button("Gönder", key="feedback_btn", use_container_width=True):
            if feedback.strip():
                # 🚀 ÇÖKME HATASI DÜZELTİLDİ: db.db_query yerine f_yeni içindeki geri_bildirim_kaydet çağrılıyor
                geri_bildirim_kaydet(st.session_state.username, feedback)
                st.success("Geri bildiriminiz için teşekkürler! 🎉")
                st.rerun()
            else:
                st.warning("⚠️ Lütfen boş geri bildirim göndermeyin.")
        
        st.markdown("---")
        
        def geri_bildirim_karti_goster(liste, baslik, emoji, key_prefix):
            st.markdown(f"### {emoji} {baslik}")
            if not liste:
                st.caption("Henüz bir işlem yok.")
                return

            if f"{key_prefix}_sayfa" not in st.session_state: 
                st.session_state[f"{key_prefix}_sayfa"] = 0
            
            sayfa = st.session_state[f"{key_prefix}_sayfa"]
            size = 10
            toplam_sayfa = (len(liste) + size - 1) // size
            dilim = liste[sayfa * size : (sayfa + 1) * size]

            for i, p_dizi in enumerate(dilim):
                meta_row = dizi_havuzu_df[dizi_havuzu_df['isim'] == p_dizi]
                meta = meta_row.iloc[0] if not meta_row.empty else None

                c_afis, c_detay = st.columns([1, 3])
                with c_afis:
                    if meta is not None and pd.notna(meta.get('afis_url')):
                        st.image(meta['afis_url'], use_container_width=True)
                
                with c_detay:
                    st.markdown(f"#### {p_dizi}")
                    if meta is not None:
                        # Bölüm, Tür ve Puan Bilgisi
                        toplam_bolum = sum([int(x) for x in str(meta.get('sezon_bolum_haritasi', '0')).split(',') if x.strip()])
                        st.write(f"⭐ **{meta.get('puan_ortalamasi', 'N/A')}** | 🎞️ **{toplam_bolum} Bölüm** | 🎭 **{meta.get('tur', 'Tür yok')}**")
                        
                        # Platform ve Durum Bilgisi
                        plat_html = platform_linklerini_olustur(meta.get('platformlar', ''), p_dizi)
                        st.markdown(f"📺 **Yayınlandığı Platformlar:** {plat_html} | 📌 **Durum:** `{meta.get('durum', 'Bilinmiyor')}`", unsafe_allow_html=True)
                        
                        # Efsanevi İkili Entegrasyonu
                        efsanevi_ikili_goster(meta.get('efsanevi_ikili'), key_suffix=f"{key_prefix}_{i}")
                        
                        # Özet Expander
                        with st.expander("📝 Özet"):
                            st.write(meta.get('ozet', 'Özet bilgisi bulunamadı.'))
                    
                    if st.button("Geri Al", key=f"un_{key_prefix}_{i}_{p_dizi}"):
                        kategori = "begenilenler" if "poz" in key_prefix else "gizlenenler"
                        dizi_listeden_sil(st.session_state.username, p_dizi, kategori)
                        
                        if "poz" in key_prefix:
                            st.session_state.pozitif_feedbacks = kullanicinin_listesini_getir(st.session_state.username, "begenilenler")
                        else:
                            st.session_state.negatif_feedbacks = kullanicinin_listesini_getir(st.session_state.username, "gizlenenler")
                        st.rerun()
                st.markdown("---")

            c_p, c_n = st.columns([1, 1])
            if c_p.button("⬅️", key=f"prev_{key_prefix}", disabled=(sayfa == 0)):
                st.session_state[f"{key_prefix}_sayfa"] -= 1
                st.session_state.scroll_to_top = True
                st.rerun()
            if c_n.button("➡️", key=f"next_{key_prefix}", disabled=(sayfa >= toplam_sayfa - 1)):
                st.session_state[f"{key_prefix}_sayfa"] += 1
                st.session_state.scroll_to_top = True
                st.rerun()

        col1, col2 = st.columns(2)
        with col1:
            geri_bildirim_karti_goster(list(reversed(st.session_state.pozitif_feedbacks)), "Beğenilenler", "🍏", "poz")
        with col2:
            geri_bildirim_karti_goster(list(reversed(st.session_state.negatif_feedbacks)), "Gizlenenler", "🍎", "neg")


# ==============================================================================
# --- 13. TAB 6: VERSUS ---
# ==============================================================================
with tab6:
    st.subheader("🆚 Premium Dizi Karşılaştırma Paneli")
    st.write("İki diziyi seçerek yapay zeka anlamsal uyumunu karşılaştırın.")
    
    col1, col2 = st.columns(2)
    with col1:
        dizi1 = st.selectbox("🎯 1. Diziyi Seçiniz", options=tum_diziler, index=None, placeholder="İlk yapım...", key="vs_dizi_1")
    with col2:
        dizi2 = st.selectbox("🔥 2. Diziyi Seçiniz", options=tum_diziler, index=None, placeholder="İkinci yapım...", key="vs_dizi_2")
    
    if dizi1 and dizi2:
        if dizi1 == dizi2:
            st.warning("⚠️ Aynı diziyi kendisiyle karşılaştıramazsınız.")
        elif st.button("🔍 Karşılaştır", use_container_width=True):
            meta1 = dizi_havuzu_df[dizi_havuzu_df['isim'] == dizi1].iloc[0]
            meta2 = dizi_havuzu_df[dizi_havuzu_df['isim'] == dizi2].iloc[0]
            
            idx1 = meta1.name
            idx2 = meta2.name
            
            vec1 = dizi_vektorleri[idx1].reshape(1, -1)
            vec2 = dizi_vektorleri[idx2].reshape(1, -1)
            benzerlik = round(float(cosine_similarity(vec1, vec2)[0][0]) * 100, 1)
            
            st.markdown(f"""
            <div style='text-align:center; background:rgba(139, 92, 246, 0.15); border:1px solid #a855f7; border-radius:12px; padding:20px; margin:20px 0;'>
                <h3 style='margin:0; color:#ffffff;'>🎯 Anlamsal Benzerlik: <span style='color:#c084fc;'>%{benzerlik}</span></h3>
            </div>
            """, unsafe_allow_html=True)
            
            k1, k2 = st.columns(2)
            for m, k in [(meta1, k1), (meta2, k2)]:
                with k:
                    st.markdown('<div class="dizi-kart-wrapper">', unsafe_allow_html=True)
                    with st.container(border=True):
                        if pd.notna(m.get('afis_url')): 
                            st.image(m['afis_url'], use_container_width=True)
                        
                        st.markdown(f"### {m.get('isim', 'Dizi')}")
                        
                        harita = [int(x) for x in str(m.get('sezon_bolum_haritasi', '0')).split(',') if x.strip()]
                        toplam_bolum = sum(harita)
                        st.write(f"⭐ **Puan:** {m.get('puan_ortalamasi', 0)}/10 | 🎞️ **Bölüm:** {m.get('sezon_sayisi', '?')} Sezon ({toplam_bolum} Bölüm)")
                        
                        plat_html = platform_linklerini_olustur(m.get('platformlar', ''), m.get('isim', ''))
                        st.markdown(f"📺 **Platform:** {plat_html} | 📌 **Durum:** `{m.get('durum', 'Bilinmiyor')}`", unsafe_allow_html=True)
                        st.write(f"🎭 **Tür:** {m.get('tur', 'N/A')}")
                        
                        ozet_metni = m.get('ozet')
                        if not ozet_metni or ozet_metni == 'None':
                            ozet_metni = ozet_getir_veya_uret(m.get('isim', ''), m.get('tur', ''))
                        
                        efsanevi_ikili_goster(m.get('efsanevi_ikili'), key_suffix=f"vs_{m.get('isim')}")
                        with st.expander("📝 Özet"):
                            st.write(ozet_metni)
                    st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# --- 14. TAB 7: SOSYAL KATMAN (İstek Sistemli) ---
# ==============================================================================
with tab7:
    if not st.session_state.logged_in:
        st.info("🔒 Arkadaş listenizi yönetmek için giriş yapmalısınız.")
    else:
        st.subheader("👥 Sosyal Katman Paneli")
        
        s_col1, s_col2 = st.columns(2)
        
        with s_col1:
            st.markdown("### ➕ Arkadaşlık İsteği Gönder")
            yeni_arkadas_adi = st.text_input("Kullanıcı Adı", placeholder="Arkadaşınızın kullanıcı adını yazın...", key="social_add_input")
            if st.button("İstek Gönder", use_container_width=True):
                if yeni_arkadas_adi.strip():
                    basari, mesaj = f_yeni.arkadaslik_istegi_gonder(st.session_state.username, yeni_arkadas_adi.strip())
                    if basari: st.success(mesaj)
                    else: st.error(mesaj)
                else: st.warning("Lütfen bir kullanıcı adı girin.")
            
            st.markdown("### 📩 Gelen İstekler")
            bekleyenler = bekleyen_istekleri_getir(st.session_state.username)
            
            if not bekleyenler:
                st.caption("Bekleyen istek yok.")
            else:
                for istek_id, gonderen in bekleyenler:
                    c1, c2, c3 = st.columns([3, 0.7, 0.7])
                    c1.write(f"👤 {gonderen}")
                    if c2.button("✅", key=f"kabul_{istek_id}", help="Kabul Et"):
                        istek_yanitla(istek_id, True, st.session_state.username)
                        st.toast(f"🎉 {gonderen} ile arkadaş oldunuz!", icon="👥")
                        st.rerun()
                    if c3.button("❌", key=f"red_{istek_id}", help="Reddet"):
                        istek_yanitla(istek_id, False, st.session_state.username)
                        st.toast(f"❌ Arkadaşlık isteği reddedildi.", icon="📩")
                        st.rerun()

        with s_col2:
            st.markdown("### 📜 Arkadaş Listeniz")
            arkadaslar = arkadas_listesini_getir(st.session_state.username)
            if not arkadaslar:
                st.caption("Henüz arkadaş listeniz boş.")
            else:
                for a_name in arkadaslar:
                    a_c1, a_c2 = st.columns([3, 1])
                    a_c1.write(f"👤 {a_name}")
                    if a_c2.button("Sil", key=f"del_friend_{a_name}"):
                        arkadas_sil(st.session_state.username, a_name)
                        st.rerun()

        st.markdown("---")
        st.markdown("### 🧠 Ortak Zevk Füzyonu (Yapay Zeka Ortak Öneri Motoru)")
        
        if not arkadaslar:
            st.info("Bu özelliği kullanabilmek için önce en az 1 arkadaş eklemelisiniz.")
        else:
            secilen_ortak_arkadas = st.selectbox("🍿 Birlikte İzleyeceğiniz Arkadaşınızı Seçin", options=arkadaslar, index=None, placeholder="Ortak analiz yapılacak arkadaşınız...")
            
            if secilen_ortak_arkadas:
                with st.spinner(f"{secilen_ortak_arkadas} ile zevkleriniz analiz ediliyor..."):
                    arkadas_izlenenler = arkadas_istekleri_yukle(secilen_ortak_arkadas)
                    
                    kendi_indeksler = dizi_havuzu_df[dizi_havuzu_df['isim'].isin(aktif_izlenenler)].index.tolist()
                    arkadas_indeksler = dizi_havuzu_df[dizi_havuzu_df['isim'].isin(arkadas_izlenenler)].index.tolist()
                    
                    if not kendi_indeksler and not arkadas_indeksler:
                        st.warning("İkinizin de izleme geçmişi bulunamadı, füzyon yapılamadı.")
                    else:
                        ortak_izlenen_vektorler = dizi_vektorleri[kendi_indeksler + arkadas_indeksler]
                        kolektif_profil_vektoru = np.mean(ortak_izlenen_vektorler, axis=0).reshape(1, -1)
                        
                        yasakli_ortak_havuz = list(set(aktif_izlenenler + arkadas_izlenenler))
                        sosyal_havuz_df = dizi_havuzu_df[~dizi_havuzu_df['isim'].isin(yasakli_ortak_havuz)].copy()
                        
                        sosyal_tavsiye_skorlari = cosine_similarity(kolektif_profil_vektoru, dizi_vektorleri[sosyal_havuz_df.index.tolist()])[0]
                        sosyal_havuz_df['ortak_benzerlik'] = sosyal_tavsiye_skorlari
                        
                        ortak_top_tavsiyeler = sosyal_havuz_df.sort_values(by='ortak_benzerlik', ascending=False).head(5)
                        st.success("🔥 İkinizin zevkine uygun ortak yapımlar:")
                        
                        for idx, row in ortak_top_tavsiyeler.iterrows():
                            st.markdown('<div class="dizi-kart-wrapper">', unsafe_allow_html=True)
                            with st.container(border=True):
                                col_s1, col_s2 = st.columns([1, 3])
                                with col_s1: 
                                    if pd.notna(row.get('afis_url')): 
                                        st.image(row['afis_url'], use_container_width=True)
                                with col_s2:
                                    st.markdown(f"#### {row.get('isim', 'Dizi')}")
                                    st.write(f"⭐ {row.get('puan_ortalamasi', 'N/A')} | 🎭 {row.get('tur', 'N/A')}")
                                    st.info("💡 Ortak zevkinize en yakın yapımlardan biri.")
                            st.markdown('</div>', unsafe_allow_html=True)


# ==============================================================================
# --- 15. SAYFANIN EN SONUNA EKLENEN SABİT DİJİTAL ASİSTAN ---
# ==============================================================================
# 🚀 HIZLANDIRMA: Bu panel artık bir @st.fragment. İçindeki bir butona basmak
# SADECE bu fonksiyonu yeniden çalıştırır — Tab1'in arama motorunu, Tab4'ün
# tavsiye motorunu ve diğer tüm sekmeleri YENİDEN ÇALIŞTIRMAZ. Bu tek değişiklik
# "Ne İzlesem" panelindeki her etkileşimi saniyeler yerine anlık hale getirir.
@st.fragment
def dizi_asistani_paneli():
    st.markdown(styles.ASISTAN_CSS, unsafe_allow_html=True)

    if "asistan_acik" not in st.session_state: st.session_state.asistan_acik = False
    if "asistan_gizli" not in st.session_state: st.session_state.asistan_gizli = False
    if "onerilen_dizi" not in st.session_state: st.session_state.onerilen_dizi = None
    if "dizi_kuyrugu" not in st.session_state: st.session_state.dizi_kuyrugu = []
    if "esnetme_seviyesi" not in st.session_state: st.session_state.esnetme_seviyesi = 0

    if st.session_state.asistan_gizli:
        st.markdown('<div class="asistan-goster-marker"></div>', unsafe_allow_html=True)
        if st.button("◀", key="asistan_goster", help="Dizi Asistanı butonunu geri getir"):
            st.session_state.asistan_gizli = False
            st.rerun(scope="fragment")
    else:
        st.markdown('<div class="asistan-gizle-marker"></div>', unsafe_allow_html=True)
        if st.button("✕", key="asistan_gizle", help="Dizi Asistanı butonunu ekrandan gizle"):
            st.session_state.asistan_gizli = True
            st.session_state.asistan_acik = False
            st.rerun(scope="fragment")
            
        but_metni = "🔎 Ne İzlesem? ▼" if st.session_state.asistan_acik else "🔎 Ne İzlesem? ▲"
        st.markdown('<div class="asistan-marker"></div>', unsafe_allow_html=True)
        if st.button(but_metni, key="asistan_toggle"):
            st.session_state.asistan_acik = not st.session_state.asistan_acik
            st.rerun(scope="fragment")

    if st.session_state.get('asistan_acik', False):
        with st.container(key="asistan_panel_container", border=True):
            st.markdown('<div class="asistan_sabitle"></div>', unsafe_allow_html=True)
            
            col1, col2 = st.columns([4, 1])
            with col1:
                st.subheader("🤖 Dizi Asistanı")
            with col2:
                if st.button("✕", key="kapat_asistan"):
                    st.session_state.asistan_acik = False
                    st.rerun(scope="fragment")
            
            if st.session_state.get('onerilen_dizi'):
                if st.button("📺 Diziyi İncele", key="incele_btn", use_container_width=True):
                    st.session_state.incele_acik = True
                    st.rerun(scope="fragment")

            if st.session_state.get('incele_acik', False):
                dizi_adi = st.session_state.onerilen_dizi
                bilgi = get_dizi_info(dizi_adi)
                
                if bilgi:
                    st.subheader(f"📽️ {dizi_adi}")
                    c_resim, c_yazi = st.columns([1, 3]) 
                                    
                    with c_resim:
                        if bilgi.get('afis_url'):
                            st.image(bilgi.get('afis_url'), width=200)
                        
                    with c_yazi:
                        st.markdown("##### 💡 Neden İzlemelisin?")
                        nedenler = yapay_zeka_neden_izlemeli_uret(dizi_adi, bilgi.get('tur', ''))
                        for neden in nedenler:
                            st.markdown(f"- {neden}")
                        
                        st.markdown("---")
                        st.write(f"**Özet:** {bilgi.get('ozet', 'Bilgi yok')}")
                        st.write(f"**Platform:** {bilgi.get('platformlar', 'Bilgi yok')}") 
                        st.write(f"**Durum:** {bilgi.get('durum', '?')}")
                    st.divider()
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Yayın Yılı", bilgi.get('yayin_yili', '?'))
                    c2.metric("Sezon", bilgi.get('sezon_sayisi', '?'))
                    c3.metric("Bölüm", bilgi.get('toplam_bolum', '?'))
                    st.divider()
                
                if st.button("❌ İncelemeyi Kapat", key="incele_kapat", use_container_width=True):
                    st.session_state.incele_acik = False
                    st.rerun(scope="fragment")
            
            tum_turler, tum_platformlar = turleri_ve_platformlari_getir()
            
            tema = st.multiselect("Türler", tum_turler, key="asistan_tema")
            platform = st.multiselect("Platform", tum_platformlar, key="asistan_plat")
            sezon = st.slider("Maksimum Sezon", 1, 20, 5, key="asistan_sezon")
            
            if st.button("Dizi Öner", key="btn_oner_final", use_container_width=True):
                with st.spinner('Diziler taranıyor...'):
                    sonuc_df = dizi_bul(tema, platform, sezon)
                    if sonuc_df is not None and not sonuc_df.empty:
                        st.session_state.dizi_kuyrugu = sonuc_df['isim'].sample(frac=1).tolist()
                        st.session_state.onerilen_dizi = st.session_state.dizi_kuyrugu.pop(0)
                        st.session_state.esnetme_seviyesi = 0
                    else:
                        st.session_state.onerilen_dizi = None
                        st.warning("Bu kriterlere uygun dizi bulunamadı.")
                st.rerun(scope="fragment")

            if st.session_state.get('onerilen_dizi'):
                st.markdown("---")
                st.info(f"Önerim: **{st.session_state.onerilen_dizi}**")
                
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("👍 Beğen", key="btn_begen_final", use_container_width=True):
                        st.session_state.onerilen_dizi = None
                        st.rerun(scope="fragment")
                with col_b:
                    if st.button("👎 Başka Ara", key="btn_baska_final", use_container_width=True):
                        if st.session_state.dizi_kuyrugu:
                            st.session_state.onerilen_dizi = st.session_state.dizi_kuyrugu.pop(0)
                        else:
                            st.session_state.esnetme_seviyesi += 1
                            yeni_df = None
                            if st.session_state.esnetme_seviyesi == 1:
                                yeni_df = dizi_bul(tema, platform, 20)
                            elif st.session_state.esnetme_seviyesi == 2:
                                yeni_df = dizi_bul(tema, [], 20)
                            
                            if yeni_df is not None and not yeni_df.empty:
                                st.session_state.dizi_kuyrugu = yeni_df['isim'].sample(frac=1).tolist()
                                st.session_state.onerilen_dizi = st.session_state.dizi_kuyrugu.pop(0)
                            else:
                                st.error("Başka dizi kalmadı.")
                        st.rerun(scope="fragment")


dizi_asistani_paneli()