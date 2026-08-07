# sozlukler.py
SINONIM_MAP = {
    # --------------------------------------------------------------------------
    # 1. CORE GENRES & CHARACTER TYPES (Temel Türler ve Karakter Tipleri)
    # --------------------------------------------------------------------------
    "zeki": "zeki akıllı dahi stratejik analitik kurnaz zekice manipülatif plan kuran akıl oyunları deha sherlock tarzı zeka oyunları zeki ana karakter",
    "başrol": "ana karakter başrol oyuncusu merkezdeki karakter anti-kahraman ana odak noktası",
    "bilimkurgu": "bilimkurgu bilim kurgu uzay distopya gelecek teknoloji sibernetik cyberpunk siberpunk yapay zeka robot android klon uzaylı galaksi retro-futurism",
    "aksiyon": "aksiyon macera savaş dövüş yüksek tempo adrenalin silah patlama çatışma kovalamaca dövüş sanatları kavga",
    "dram": "dram drama duygusal derin hikaye hayat hikayesi acıklı hüzünlü trajedi yaşanmış olaylar ağır dram gözyaşı dokunaklı",
    "komedi": "komedi komik mizah eğlenceli durum komedisi sitcom kahkaha parodi absürt espri güldürü",
    "macera": "macera keşif yolculuk serüven arayış hazine harita serüven dolu yol hikayesi",
    "polisiye": "polisiye suç dedektif cinayet gizem soruşturma şerif ajan fbi cia soruşturma ipucu dava çözme kanıt polis teşkilatı katil kim",
    "gerilim": "gerilim korku psikolojik gizem karanlık atmosfer tedirgin edici tekinsiz gergin süspans tırnak yedirten gerginlik",
    "korku": "korku dehşet ürkütücü kabus canavar yaratık slasher katil maskeli tehlike ani korku unsurları klasik korku gerçek korku hikayeleri",
    "psikolojik": "psikolojik zihinsel derin karakter analiz travma akıl sağlığı şizofreni bilinçaltı rüya illüzyon akıl hastanesi sanrı kişilik bozukluğu",
    "hukuk": "hukuk mahkeme avukat adalet savunma dava savcı duruşma kanun yasa hakim baro hukuk bürosu adli",
    "intikam": "intikam adalet hesaplaşma kanunsuzluk kurnazlık intikamcı öc alma ceza vendetta hesap sorma intikam hikayesi",
    "savaş": "savaş cephe ordu asker cephe hattı silahlı çatışma dünya savaşı topçu siperler savaş dönemi askeri operasyon askeri dizi",
    "müzikal": "müzikal şarkılı dans müzik odaklı sahne performansı şarkı sözleri müzik endüstrisi konser turne",
    "spor": "spor futbol basketbol boks güreş yarış antrenman şampiyonluk takım ruhu rekabet sporcu hayatı spor draması",
    "western": "western kovboy vahşi batı çöl at silahlı düello şerif haydut altın çağı amerika sınır kasabası",
    "gerçek_suç": "gerçek suç true crime gerçek olaylar cinayet belgeseli seri katil gerçek dava araştırmacı gazetecilik dosya",
    "belgesel": "belgesel documentary gerçek olaylar röportaj tarihsel kayıt doğa belgeseli bilgilendirici içerik arşiv görüntüleri",
    "reality": "reality şov yarışma realite programı gerçek katılımcılar rekabet elenme jüri performans yarışması",

    # --------------------------------------------------------------------------
    # 2. POPULAR THEMES & COLLOQUIAL SEARCHES (Popüler Temalar ve Arama Kalıpları)
    # --------------------------------------------------------------------------
    "aşk": "aşk romantik duygusal ilişki tutku dramatik romantizm sevgili flört evlilik kalp kırıklığı yasak aşk platonik romantik komedi",
    "suç": "suç polisiye dedektif mafya yasa dışı illegal çete hesaplaşma katil soygun hırsızlık uyuşturucu kartel cartel organize suç karapara kara para aklama kaçakçılık",
    "tarihi": "tarihi dönem antik epik krallık imparatorluk geçmiş devir ortaçağ tarihsel belgesel biyografi saray hanedan padişah kral kraliçe savaşçı kılıç zırh",
    "fantastik": "fantastik büyü mitoloji efsane ejderha doğaüstü masalsı sihir cadı büyücü canavar elf cüce paralel evren vampir kurtadam",
    "zamanda_yolculuk": "zamanda yolculuk zaman makinesi geçmiş gelecek paradoks zaman döngüsü time travel kelebek etkisi zaman atlaması zaman yolculuğu",
    "hayatta_kalma": "hayatta kalma survival zombi virüs salgın kıyamet mahsur kalma adada mahsur ıssız doğada mücadele açlık kıyamet sonrası",
    "zombi": "zombi yürüyen ölüler salgın virüs enfekte kıyamet sonrası undead apocalypse last of us walking dead ısırma zombiler",
    "casusluk": "casusluk ajan casus fbi cia mi6 kgb gizli görev operasyon köstebek sızma şifre diplomatik kriz soğuk savaş çifte ajan",
    "politika": "politika siyaset devlet parlamento başkan seçim yolsuzluk güç savaşı diplomasi saray entrikaları hükümet beyaz saray entrika",
    "teknoloji": "teknoloji hacker yazılımcı kodlama bilişim yapay zeka robot yazılım internet siber saldırı sanal gerçeklik vr bilgisayar teknolojik karanlık gelecek",
    "tıbbi": "tıbbi medikal hastane doktor cerrah ameliyat tıp teşhis hasta acil servis hemşire house grey's anatomy tıp dünyası",
    "hapishane": "hapishane cezaevi mahkum firar kaçış parmaklıklar arkasında gardiyan prison break suçlular koğuş hücre parmaklık",
    "finans": "finans para borsa şirket zengin milyarder milyonlarca dolar ticaret hisse senedi banka wall street açgözlülük zenginlik holding patron",
    "mitoloji": "mitoloji efsane tanrılar yunan mitolojisi iskandinav mitolojisi thor zeus yaratıklar antik inanışlar mitolojik canavarlar iskandinav tanrıları",
    "doğaüstü": "doğaüstü doğa üstü supernatural hayalet ruhlar şeytan paranormal iblis medyum musallat hayaletli ev paranormal olaylar korkunç varlıklar",
    "post_apokaliptik": "post apokaliptik kıyamet sonrası harabe uygarlığın çöküşü hayatta kalanlar yıkılmış dünya nükleer felaket medeniyetin sonu",
    "uzay_operası": "uzay operası galaksi imparatorluğu yıldız savaşları uzay gemisi filo galaktik keşif uzaylı medeniyet uzay filosu",
    "doğal_afet": "doğal afet deprem sel kasırga volkan felaket doğa olayları hayatta kalma mücadelesi afet sonrası",
    "göç": "göç mülteci sınır yeni ülke uyum sorunu kimlik arayışı kültürel çatışma göçmen hayatı yeni bir hayat kurma",
    "bağımlılık": "bağımlılık uyuşturucu alkol rehabilitasyon iyileşme süreci mücadele terapi kurtuluş bağımlılıkla mücadele",
    "ahlaki_ikilem": "ahlaki ikilem etik sorgulama vicdan doğru yanlış zor kararlar gri alan ahlaki çıkmaz zor seçimler",
    "tarikat": "tarikat kült cemaat lider beyin yıkama fanatizm gizli topluluk manipülasyon sekt kapalı toplum",
    "aile_sırları": "aile sırları gizli geçmiş saklı gerçekler aile draması miras kavgası aile içi ihanet gizli aile bağları",
    "komplo_teorisi": "komplo teorisi gizli örgüt derin devlet sır saklama örtbas gizli ajanda gerçek ortaya çıkarma gizli güçler",
    "uzaylı_istilası": "uzaylı istilası dünya dışı yaşam işgal ilk temas uzaylı tehdit invasion dünya dışı varlık",
    "iş_dünyası": "iş dünyası şirket kurumsal hayat ceo patron ofis politikaları kurumsal entrika girişimcilik startup şirket savaşları",
    "gastronomi": "gastronomi yemek şef mutfak restoran yemek pişirme culinary aşçılık gurme yemek yarışması",
    "kampüs": "kampüs okul üniversite öğrenci hayatı sınav arkadaşlık grupları okul draması yurt hayatı",

    # --------------------------------------------------------------------------
    # 3. ATMOSPHERE & TONE (Atmosfer ve Ton Katmanları)
    # --------------------------------------------------------------------------
    "karanlık": "karanlık kasvetli gotik depresif korku gerilim puslu distopik ürpertici tekinsiz noir karanlık atmosfer boğucu",
    "eğlenceli": "eğlenceli komik mizah keyifli kafa dağıtmalık neşeli hafif sitcom çıtır çerezlik kafa yormayan çerezlik eğlence",
    "beyin_yakan": "beyin yakan kafa karıştırıcı karmaşık gizemli teoriler kurduran paradoks şaşırtıcı son twist plot twist akıl sınırlarını zorlayan beyin yakıcı",
    "karamsar": "karamsar umutsuz karanlık trajik son melankolik buruk çaresiz nihilist pesimist karamsarlık",
    "umutlu": "umutlu iyimser ilham verici pozitif aydınlık motive edici içinizi ısıtacak sıcacık umut verici moral düzelten",
    "ironik": "ironik alaycı mizah dolu çelişkili sarkastik iğneleyici kara komedi taşlama",
    "ciddi": "ciddi ağırbaşlı gerçekçi dramatik gerçek hayat ciddiyet politik ağır felsefi felsefe içeren",
    "melankolik": "melankolik hüzünlü nostaljik duygusal buruk acı tatlı yalnızlık melankoli hüzün yavaş sakin sonbahar havası",
    "rahatsız_edici": "rahatsız edici rahatsızlık veren ürkütücü tedirgin edici şiddet içeren vahşet kanlı psikolojik baskı kabus gibi vahşi rahatsızlık",
    "epik": "epik görkemli büyük ölçekli destansı çarpıcı sahneler görsel şölen büyüleyici anlatım geniş kapsamlı hikaye",
    "sıcak": "sıcak samimi içten sevecen aile sıcaklığı yakın dostluk pozitif enerji ferahlatıcı huzurlu",

    # --------------------------------------------------------------------------
    # 4. CHARACTER ARCHETYPES (Karakter Arketipleri)
    # --------------------------------------------------------------------------
    "anti_kahraman": "anti-kahraman anti kahraman kusurlu gri karakter kötücül iyi walter white dexter jesse pinkman karanlık geçmiş suçlu kahraman",
    "kahraman": "kahraman idealist cesur ahlaklı dürüst kurtarıcı fedakar süper kahraman",
    "kötü": "kötü karakter antagonist kötücül zalim düşman psikopat sosyopat canavar kötü adam şeytani planlar",
    "karmaşık": "karmaşık karakter derin katmanlı çelişkili gizemli iki yüzlü sırları olan çözülemeyen çok boyutlu karakter",
    "kadın_kahraman": "kadın kahraman güçlü kadın karakter female lead kadın başrol güçlü kadın figürü öncü kadın karakter",
    "mentor": "mentor akıl hocası öğretmen yol gösterici deneyimli usta çırak ilişkisi bilge figür",
    "femme_fatale": "femme fatale tehlikeli kadın baştan çıkarıcı manipülatif kadın gizemli kadın karakter tuzak kuran kadın",
    "ikili_kahraman": "ikili kahraman dostluk ikilisi partner buddy ilişkisi iki ana karakter ortak macera",
    "ensemble": "ensemble kadro geniş karakter kadrosu çok karakterli grup dinamiği takım hikayesi kalabalık kadro",
    "çocuk_kahraman": "çocuk kahraman genç karakter çocuk gözünden büyüme hikayesi çocukluk anlatısı çocuk bakış açısı",

    # --------------------------------------------------------------------------
    # 5. FORMAT & TARGET AUDIENCE (Format ve İzleyici Kitlesi)
    # --------------------------------------------------------------------------
    "antoloji": "antoloji bağımsız bölümler farklı konular bağımsız hikayeler her bölüm başka hikaye black mirror her bölüm farklı oyuncu",
    "mini_dizi": "mini dizi mini-dizi kısa sezonlu kısa seriler tek sezonluk biten hikaye tek seferde izlemelik tek sezonda biten",
    "gençlik": "gençlik genç yetişkin içerik gençlik temaları lise üniversite ergenlik arkadaşlık okul gençleri teen drama lise gençliği",
    "aile": "aile dostane içerik aileyle izlenebilir zararsız komik sıcak ev ortamı childlu aileler aile dizisi",
    "yetişkin": "yetişkin odaklı olgun temalar şiddet cinsellik küfür kan çıplaklık +18 olgun içerik argo çıplaklık içeren",
    "çocuk": "çocuklara uygun eğitici eğlenceli içerik çizgi film animasyon zararsız komedi pedogojik onaylı",
    "uyarlama": "uyarlama kitaptan uyarlama roman uyarlaması oyun uyarlaması gerçek hikaye uyarlaması based on kaynak eserden",
    "uzun_soluklu": "uzun soluklu çok sezonlu uzun süren dizi yıllarca devam eden klasikleşmiş efsane dizi",
    "kısa_bölümlü": "kısa bölümlü az bölümlü hızlı bitecek kısa sezon tek oturuşta izlenecek",

    # --------------------------------------------------------------------------
    # 6. SETTING & TIMELINES (Zaman, Mekan ve Anlatı Yapısı)
    # --------------------------------------------------------------------------
    "modern": "modern günümüz çağdaş 21. yüzyıl şehir hayatı metropol modern dünya günümüz dünyası",
    "ortaçağ": "ortaçağ medieval tarihi krallık feodal şövalye zırh kılıç taht savaşları kaleler hanedanlar feodalite",
    "gelecek": "gelecek distopya ütopya bilimkurgu fütüristik uzay çağı ileri teknoloji yüzyıllar sonrası yeni dünya",
    "alternatif": "alternatif tarih ne olurdu if senaryosu paralel evren zaman çizgisi sapması paralel zaman",
    "gerçekçi": "gerçekçi gerçek hayat sade doğal belgeselvari biyografik kurgu dışı yaşanmış hikayeler gerçek olaylardan esinlenen",
    "stilize": "stilize abartılı sanatsal görsel şov estetik neon ışıklı çizgi roman tarzı sanatsal sinematografi sanatsal çekimler",
    "absürt": "absürt saçma mantıksız uçuk kaçık gerçek dışı gerçeküstü sürreal gerçeklikten uzak absürd komedi absürt mizah",

    # --------------------------------------------------------------------------
    # 7. NARRATIVE SPEED & BUDGET (Anlatı Yapısı, Tempo, Prodüksiyon Ölçeği)
    # --------------------------------------------------------------------------
    "doğrusal": "doğrusal kronolojik basit anlatım düz hikaye sırasıyla giden olay örgüsü düz kronoloji",
    "zaman_atlamalı": "zaman atlamalı flashback flashforward kronolojik olmayan geçmiş gelecek zaman sıçraması doğrusal olmayan paralel zamanlar",
    "çoklu_bakış": "çoklu bakış açısı farklı karakterler paralel hikayeler perspektif koro anlatım mozaik hikaye kesişen hayatlar",
    "yavaş_tempolu": "yavaş tempolu ağır akan derinlemesine sakin atmosfer sanat filmi tarzı karakter odaklı yavaş yavaş işlenen yavaş tempo ağır ilerleyen",
    "orta_tempolu": "orta tempolu dengeli ne hızlı ne yavaş akıcı hikaye anlatımı dengeli tempo akıcı",
    "hızlı_tempolu": "hızlı tempolu yüksek adrenalin kesintisiz aksiyon sürükleyici soluksuz izlenecek heyecanlı dinamik tempolu hızlı akan bol aksiyonlu",
    "yüksek_bütçe": "yüksek bütçeli büyük prodüksiyon gişe canavarı epik büyük bütçe hollywood görsel efekt cgi devasa yapım blockbuster",
    "bağımsız": "bağımsız indie düşük bütçe sanatsal yönetmen filmi özgün hikaye klişelerden uzak festival filmi sanatsal sinema bağımsız yapım",
    "doğu": "doğu kültürü asya uzak doğu anime dorama k-drama japon kore çin yapımı uzakdoğu k-dizisi",
    "batı": "batı kültürü amerika avrupa hollywood ingiliz amerikan batılı yabancı batı yapımı",
    "yerli": "yerli türk türkiye türk yapımı yerli dizi türkçe içerik türk dizileri yerli yapımlar"
}