# -*- coding: utf-8 -*-
"""
🎬 dizimibul - Stil Kodları Kütüphanesi (styles.py)
Bu dosya arayüzde kullanılan tüm inline CSS ve HTML stil şablonlarını barındırır.
"""

MAIN_CSS = """
    <style>
    /* Uygulama Arka Planı */
    .stApp { background: linear-gradient(135deg, #0f0c1b 0%, #15102a 50%, #06040a 100%) !important; }

    /* Dizi Kartları (Hafif ve hızlı) */
    .dizi-kart {
        background: rgba(25, 22, 47, 0.85) !important;
        border: 1px solid rgba(168, 85, 247, 0.3) !important;
        border-radius: 20px !important;
        padding: 24px !important;
        margin-bottom: 25px !important;
        transition: transform 0.2s ease, border-color 0.2s ease !important;
    }
    .dizi-kart:hover {
        transform: translateY(-5px);
        border-color: rgba(168, 85, 247, 0.6) !important;
        backdrop-filter: blur(8px) !important;
    }

    /* Container Tabanlı Dizi Kartı (Taşma/Boşluk sızıntısı engelleyici) */
    .dizi-kart-wrapper div[data-testid="stVerticalBlockBorder"] {
        background: rgba(25, 22, 47, 0.85) !important;
        border: 1px solid rgba(168, 85, 247, 0.3) !important;
        border-radius: 20px !important;
        padding: 24px !important;
        margin-bottom: 25px !important;
        transition: transform 0.2s ease, border-color 0.2s ease !important;
    }
    .dizi-kart-wrapper div[data-testid="stVerticalBlockBorder"]:hover {
        transform: translateY(-5px) !important;
        border-color: rgba(168, 85, 247, 0.6) !important;
        box-shadow: 0 8px 30px rgba(168, 85, 247, 0.25) !important;
    }

    /* Arama Çubuğu (TextInput) Güzelleştirme */
    div[data-testid="stTextInput"] [data-baseweb="input"] {
        background-color: rgba(30, 27, 57, 0.6) !important;
        border: 2px solid rgba(168, 85, 247, 0.65) !important;
        border-radius: 12px !important;
        padding: 6px 12px !important;
        box-shadow: 0 0 15px rgba(168, 85, 247, 0.15) !important;
        transition: all 0.3s ease !important;
    }
    div[data-testid="stTextInput"] [data-baseweb="input"]:focus-within {
        border-color: #c084fc !important;
        box-shadow: 0 0 25px rgba(168, 85, 247, 0.5) !important;
        background-color: rgba(30, 27, 57, 0.95) !important;
    }
    div[data-testid="stTextInput"] input {
        color: #f3f4f6 !important;
        font-size: 16px !important;
    }
    div[data-testid="stTextInput"] label p {
        color: #c084fc !important;
        font-weight: 700 !important;
        font-size: 16px !important;
        text-shadow: 0 0 8px rgba(168, 85, 247, 0.4) !important;
    }

    /* Modern Hap/Pill Etiket Tasarımları (Glassmorphism esintisi) */
    .etiket-puan, .etiket-surec, .etiket-sure, .etiket-ai {
        display: inline-block;
        padding: 5px 12px;
        border-radius: 12px;
        font-size: 13px;
        font-weight: 600;
        margin-right: 8px;
        margin-bottom: 8px;
    }
    .etiket-puan {
        background: rgba(234, 179, 8, 0.15) !important;
        color: #facc15 !important;
        border: 1px solid rgba(234, 179, 8, 0.3) !important;
    }
    .etiket-surec {
        background: rgba(168, 85, 247, 0.15) !important;
        color: #c084fc !important;
        border: 1px solid rgba(168, 85, 247, 0.3) !important;
    }
    .etiket-sure {
        background: rgba(14, 165, 233, 0.15) !important;
        color: #38bdf8 !important;
        border: 1px solid rgba(14, 165, 233, 0.3) !important;
    }
    .etiket-ai {
        background: rgba(16, 185, 129, 0.15) !important;
        color: #34d399 !important;
        border: 1px solid rgba(16, 185, 129, 0.3) !important;
    }

    /* Butonlar (Modern ve yumuşak geçişli) */
    div.stButton > button {
        background: linear-gradient(135deg, #a855f7 0%, #6d28d9 100%) !important;
        color: white !important;
        border-radius: 12px !important;
        border: none !important;
        padding: 10px 20px !important;
        font-weight: 700 !important;
        box-shadow: 0 4px 15px rgba(168, 85, 247, 0.3) !important;
        transition: all 0.3s ease !important;
    }
    div.stButton > button:hover {
        transform: translateY(-3px) scale(1.02) !important;
        box-shadow: 0 6px 20px rgba(168, 85, 247, 0.5) !important;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: rgba(10, 7, 18, 0.95) !important;
        border-right: 1px solid rgba(168, 85, 247, 0.2) !important;
    }
    </style>
"""

TAB_CSS = """
<style>
    [data-testid="stExpander"] {
        border: none !important;
        background-color: transparent !important;
    }
    [data-testid="stExpanderDetails"] {
        padding: 5px !important;
        background-color: #1e1e26 !important;
        border-radius: 8px;
    }
    .login-box {
        background-color: transparent !important;
        padding: 5px !important;
        border: none !important;
    }
    div.stButton > button {
        width: 100% !important;
        margin-top: 10px;
    }
</style>
"""

ASISTAN_CSS = """
<style>
/* --- NE İZLESİM BUTONU --- */
div.element-container:has(.asistan-marker) + div.element-container button {
    position: fixed !important;
    bottom: 30px !important;
    right: 30px !important;  
    left: auto !important;   
    width: 160px !important;
    height: 50px !important;
    z-index: 999999 !important;
    background-color: #a855f7 !important;
    color: white !important;
    font-weight: bold !important;
    border-radius: 25px !important;
    border: 2px solid #c084fc !important;
    box-shadow: 0 8px 24px rgba(168, 85, 247, 0.4) !important;
    transition: all 0.3s ease !important;
}
div.element-container:has(.asistan-marker) + div.element-container button:hover {
    background-color: #c084fc !important;
    transform: scale(1.05) !important;
}
/* --- GİZLE BUTONU --- */
div.element-container:has(.asistan-gizle-marker) + div.element-container button {
    position: fixed !important;
    bottom: 35px !important;
    right: 200px !important;  
    width: 40px !important;
    height: 40px !important;
    z-index: 999999 !important;
    background-color: rgba(25, 22, 47, 0.7) !important;
    color: #a855f7 !important;
    font-weight: bold !important;
    font-size: 15px !important;
    border-radius: 50% !important;
    border: 1px solid rgba(168, 85, 247, 0.4) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
    transition: all 0.3s ease !important;
    padding: 0 !important;
    line-height: 40px !important;
}
div.element-container:has(.asistan-gizle-marker) + div.element-container button:hover {
    background-color: #f43f5e !important;
    color: white !important;
    border-color: #fda4af !important;
    transform: scale(1.1) rotate(90deg) !important;
}
/* --- GÖSTER SEKME TABI --- */
div.element-container:has(.asistan-goster-marker) + div.element-container button {
    position: fixed !important;
    bottom: 35px !important;
    right: 0px !important;  
    left: auto !important;   
    width: 40px !important;
    height: 40px !important;
    z-index: 999999 !important;
    background: linear-gradient(135deg, #a855f7 0%, #6d28d9 100%) !important;
    color: white !important;
    font-size: 16px !important;
    border-radius: 20px 0px 0px 20px !important;
    border: 1px solid #c084fc !important;
    border-right: none !important;
    box-shadow: -4px 4px 15px rgba(168, 85, 247, 0.4) !important;
    transition: all 0.3s ease !important;
    padding-left: 0px !important;
}
div.element-container:has(.asistan-goster-marker) + div.element-container button:hover {
    width: 50px !important;
    background-color: #c084fc !important;
}
/* --- ASİSTAN PANELİ --- */
div.st-key-asistan_panel_container, div[class*="st-key-asistan_panel_container"] {
    position: fixed !important;
    bottom: 95px !important;     
    top: auto !important;        
    right: 30px !important;    
    left: auto !important;   
    width: 380px !important;     
    max-height: 70vh !important; 
    overflow-y: auto !important; 
    z-index: 999998 !important;
    background-color: #0e1117 !important;
    border: 1px solid #4a4a5a !important;
    padding: 20px !important;
    border-radius: 15px !important;
    box-shadow: 0 10px 35px rgba(0,0,0,0.6) !important;
    animation: slideUp 0.3s ease-out forwards;
}
div.st-key-asistan_panel_container::-webkit-scrollbar, div[class*="st-key-asistan_panel_container"]::-webkit-scrollbar {
    width: 6px !important;
}
div.st-key-asistan_panel_container::-webkit-scrollbar-thumb, div[class*="st-key-asistan_panel_container"]::-webkit-scrollbar-thumb {
    background: #4a4a5a !important;
    border-radius: 10px !important;
}
div.st-key-asistan_panel_container::-webkit-scrollbar-thumb:hover, div[class*="st-key-asistan_panel_container"]::-webkit-scrollbar-thumb:hover {
    background: #a855f7 !important;
}
@keyframes slideUp {
    from {
        transform: translateY(15px);
        opacity: 0;
    }
    to {
        transform: translateY(0);
        opacity: 1;
    }
}
</style>
"""

BADGE_CSS = """
<style>
/* --- ROZETLER EXPANDER GÜZELLEŞTİRME --- */
div[class*="st-key-rozetler_expander"], div.st-key-rozetler_expander {
    border: 1px solid rgba(168, 85, 247, 0.3) !important;
    background: rgba(30, 27, 57, 0.25) !important;
    border-radius: 12px !important;
    margin-top: 15px !important;
    margin-bottom: 20px !important;
    box-shadow: 0 4px 15px rgba(168, 85, 247, 0.1) !important;
}
div[class*="st-key-rozetler_expander"] summary, div.st-key-rozetler_expander summary {
    padding: 10px 15px !important;
}
div[class*="st-key-rozetler_expander"] summary span p, div.st-key-rozetler_expander summary span p,
div[class*="st-key-rozetler_expander"] summary p, div.st-key-rozetler_expander summary p {
    font-size: 18px !important;
    font-weight: 700 !important;
    color: #c084fc !important;
    text-shadow: 0 0 10px rgba(168, 85, 247, 0.3) !important;
}
div[class*="st-key-rozetler_expander"] summary:hover span p, div.st-key-rozetler_expander summary:hover span p,
div[class*="st-key-rozetler_expander"] summary:hover p, div.st-key-rozetler_expander summary:hover p {
    color: #e9d5ff !important;
}

/* --- KOMPAKT HIZLI BÖLÜM EKLEME (➕) BUTONU --- */
div[class*="st-key-inc_"] {
    display: inline-block !important;
    vertical-align: middle !important;
    margin-top: -3px !important;
}
div[class*="st-key-inc_"] button, div[class*="st-key-inc_"] button:active, div[class*="st-key-inc_"] button:focus {
    width: 32px !important;
    height: 32px !important;
    min-height: 32px !important;
    max-height: 32px !important;
    min-width: 32px !important;
    max-width: 32px !important;
    padding: 0 !important;
    line-height: 30px !important;
    font-size: 14px !important;
    border-radius: 50% !important;
    background: rgba(168, 85, 247, 0.15) !important;
    border: 1px solid rgba(168, 85, 247, 0.4) !important;
    box-shadow: 0 0 10px rgba(168, 85, 247, 0.2) !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    color: #c084fc !important;
    transition: all 0.2s ease-in-out !important;
}
div[class*="st-key-inc_"] button:hover {
    background: rgba(168, 85, 247, 0.4) !important;
    border-color: #a855f7 !important;
    box-shadow: 0 0 15px rgba(168, 85, 247, 0.5) !important;
    color: white !important;
    transform: scale(1.1) !important;
}

/* --- ROZET KARTLARI --- */
.rozet-kart {
    background: rgba(30, 27, 57, 0.4) !important;
    border: 1px solid rgba(168, 85, 247, 0.15) !important;
    border-radius: 16px !important;
    padding: 20px 15px !important;
    text-align: center !important;
    transition: all 0.3s ease-in-out !important;
    margin-bottom: 20px !important;
    height: 250px !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: space-between !important;
}
.rozet-kart:hover {
    transform: translateY(-5px) !important;
    border-color: rgba(168, 85, 247, 0.5) !important;
    box-shadow: 0 8px 24px rgba(168, 85, 247, 0.2) !important;
    background: rgba(30, 27, 57, 0.6) !important;
}

.rozet-daire {
    width: 75px !important;
    height: 75px !important;
    border-radius: 50% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 32px !important;
    background: rgba(255, 255, 255, 0.05) !important;
    border: 2px solid rgba(255, 255, 255, 0.1) !important;
    transition: all 0.3s ease !important;
}

/* Kademeli Filtre Renkleri ve Gölgeleri */
.rozet-bronz {
    background: rgba(205, 127, 50, 0.15) !important;
    border: 2px solid #cd7f32 !important;
    box-shadow: 0 0 15px rgba(205, 127, 50, 0.3) !important;
    filter: sepia(0.8) saturate(1.8) contrast(1.1);
}
.rozet-gumus {
    background: rgba(192, 192, 192, 0.15) !important;
    border: 2px solid #c0c0c0 !important;
    box-shadow: 0 0 15px rgba(192, 192, 192, 0.3) !important;
    filter: grayscale(1) brightness(1.2);
}
.rozet-altin {
    background: rgba(255, 215, 0, 0.15) !important;
    border: 2px solid #ffd700 !important;
    box-shadow: 0 0 20px rgba(255, 215, 0, 0.4) !important;
    filter: sepia(0.3) saturate(3.5) hue-rotate(-10deg) brightness(1.1);
}
.rozet-elmas {
    background: rgba(0, 229, 255, 0.15) !important;
    border: 2px solid #00e5ff !important;
    box-shadow: 0 0 25px rgba(0, 229, 255, 0.5) !important;
    filter: saturate(1.8) hue-rotate(185deg) brightness(1.3);
}
.rozet-kilitli {
    background: rgba(255, 255, 255, 0.02) !important;
    border: 2px dashed rgba(255, 255, 255, 0.1) !important;
    filter: grayscale(1) opacity(0.35);
}

/* Başarım Popup Animasyonu */
.achievement-popup {
    position: fixed !important;
    top: 30px !important;
    right: 30px !important;
    z-index: 1000000 !important;
    background: rgba(21, 16, 42, 0.95) !important;
    border: 2px solid #a855f7 !important;
    border-radius: 16px !important;
    padding: 16px 24px !important;
    display: flex !important;
    align-items: center !important;
    gap: 15px !important;
    box-shadow: 0 10px 30px rgba(168, 85, 247, 0.4) !important;
    animation: slideInFadeOut 4.5s cubic-bezier(0.16, 1, 0.3, 1) forwards !important;
    backdrop-filter: blur(10px) !important;
}

@keyframes slideInFadeOut {
    0% { transform: translateX(130%); opacity: 0; }
    10% { transform: translateX(0); opacity: 1; }
    90% { transform: translateX(0); opacity: 1; }
    100% { transform: translateX(130%); opacity: 0; }
}
</style>
"""
