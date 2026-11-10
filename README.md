# AKÇA — Bağımsız Finansal Araştırma Terminali

AKÇA; BIST şirketleri, ABD ve küresel halka açık şirketler, dünya endeksleri, döviz, emtia, kripto varlıklar, fonlar, makro göstergeler ve portföy riskini aynı araştırma disiplini içinde incelemek için geliştirilen bağımsız finansal araştırma sistemidir.

**AKÇA aracı kuruma bağlanıp emir göndermez ve işlem gerçekleştirmez.** Kaynaklı araştırma ve karar desteği üretir. İlk sürümde AL/TUT/AZALT/SAT karar eşikleri geriye dönük testle doğrulanmadığı için araştırma motorunun güvenli varsayılanı BEKLE'dir.

## İlk kullanılabilir alpha

- Şirket araştırması: fiyat, şirket profili, mevcut finansal veriler, değerleme, teknik göstergeler, risk işaretleri ve 33 adımlı inceleme protokolü.
- Piyasalar: BIST 100/30, ABD, Avrupa ve Asya endeksleri; döviz pariteleri ve dolar endeksi.
- Emtia: altın, gümüş, bakır, WTI/Brent petrol, doğalgaz ve tarımsal vadeli işlem sembolleri; ayrıca Dünya Bankası aylık benchmark tarihçesi.
- Kripto: CoinGecko araması, fiyat, piyasa değeri ve dönemsel değişimler.
- Makro: FRED ve TCMB EVDS için sunucu tarafı API anahtarı desteği.
- Değer tarayıcı: değerleme, kârlılık, büyüme, bilanço ve nakit akışı için açıkça geçici olarak işaretlenmiş aday puan.
- Kurum araştırmaları: hedef fiyat ve tavsiye kaydı, rapor bağımlılığı, doğrulanmış konsensüs ve gerçekleşen tahmin isabeti takibi.
- Dolar bazlı performans: TRY hisselerinde tarihsel USD/TRY ile dönüşüm; FRED CPI erişimi varsa reel USD getiri.
- Halka arzlar: kullanıcının/araştırmacının kaynakla kaydettiği halka arzlar için nominal, USD ve uygun veri varsa reel USD performansı; bölünme ve temettü kapsamı.
- Portföy: yerel portföy ve pozisyon kaydı, aynı para biriminde ağırlık ve konsantrasyon; farklı para birimleri FX dönüşümü olmadan asla toplanmaz.
- Türkiye bağımsız fiyat araştırması: TÜİK 2022 referans sepetindeki 409 madde kodu, satıcı fiyat gözlemleri, kalite kontrol, varyant ve birim normalizasyonu. Ağırlıklar eksikse endeks kilitlenir.
- Web terminali, API, SQLite veritabanı, CLI, PWA dosyaları, Docker başlangıcı ve otomatik test.

## Canlı erişim ile veri kapsamının ayrımı

AKÇA çeşitli kaynaklara bağlanabilen adaptörler içerir; bu, tüm piyasalarda lisanslı gerçek zamanlı veri hakkı olduğu anlamına gelmez.

- Yahoo Finance / yfinance: topluluk istemcisiyle alınan ikincil/gösterge veridir; resmî veya lisanslı BIST gerçek zamanlı akışı değildir.
- SEC EDGAR: ABD bildirimcileri için ücretsiz açık veri; gerçek iletişim bilgisi içeren User-Agent gerekir. BIST şirketlerini kapsamaz.
- Borsa İstanbul: resmî piyasa fiyatı/işlem geçmişi için uygun lisanslı veri dağıtıcısı bağlantısı gerekir.
- KAP/MKK: otomatik bildirim ve finansal dosya erişimi için MKK API Portal uygulaması, API anahtarı ve ilgili veri ürünü yetkisi gerekir.
- TCMB EVDS ve FRED: API anahtarı gerekir.
- CoinGecko: API kotası ve ticari kullanım koşulları plana göre değişir.
- World Bank Pink Sheet: aylık benchmark serisidir; gün içi spot/futures fiyatı değildir.

Kaynakların ayrıntıları ve erişim durumu: docs/DATA_SOURCES.md. Sağlayıcı erişimi yoksa AKÇA sahte veri üretmez; raporda eksikliği işaretler.

## macOS üzerinde kurulum

Python 3.11 veya üzeri gerekir. Depoyu Mac'e klonla:

    git clone https://github.com/hakanuste/AKCA.git
    cd AKCA

Başlatma betiği sanal ortamı, bağımlılıkları, .env dosyasını ve yerel API anahtarını hazırlar:

    bash scripts/start_mac.command

Terminal adresi:

    http://127.0.0.1:8000/terminal.html

API dokümantasyonu:

    http://127.0.0.1:8000/docs

Canlı veri için .env içindeki isteğe bağlı anahtarları yapılandır:
- AKCA_SEC_USER_AGENT: gerçek bir iletişim e-postası içermeli.
- FRED_API_KEY: ABD makro serileri ve reel USD enflasyon ayarı.
- TCMB_EVDS_API_KEY: Türkiye makro/FX, BIST endeks ve tahvil serileri. Varsayılan servis belgelenmiş EVDS 2 REST uyumluluk endpoint'idir; EVDS 3 katalog kodları terminalden girilir.
- COINGECKO_DEMO_API_KEY: CoinGecko API kotası için.
- AKCA_API_KEY betik tarafından yerelde oluşturulur; bunu GitHub'a, terminal ekran görüntüsüne veya herkese açık bir web sayfasına koyma.

### iPhone / aynı Wi-Fi ağı

Mac'te başlatma betiği yerel ağ IP'sini gösterir. iPhone Safari adres çubuğuna şu biçimde gir:

    http://MAC_LAN_IP:8000/terminal.html

Bu erişim yalnızca aynı yerel ağa yöneliktir. Üretim internet erişimi için HTTPS, kimlik doğrulama, güvenli ters proxy, yedekleme ve sunucu kurulumunu ayrıca yapılandırmak gerekir. API'yi güvenlik duvarı/HTTPS olmadan internete açma.

### Docker ile başlatma

    cp .env.example .env
    openssl rand -hex 32

Üretilen anahtarı .env içindeki AKCA_API_KEY satırına yaz, ardından:

    docker compose up --build -d

## Test

    bash scripts/test_mac.command

Aynı kontroller GitHub Actions üzerinde main dalına her push/PR ile çalışır:
- Python kaynak derleme
- Pytest birim/regresyon testleri
- JavaScript sözdizimi kontrolü
- Ruff statik lint kontrolü

## GitHub Pages

Web sayfaları otomatik olarak gh-pages dalına yayınlanır. İlk seferde GitHub deposunda:
1. Settings → Pages
2. Build and deployment → Source: Deploy from a branch
3. Branch: gh-pages, Folder: /(root)
4. Save

Sonrasında sayfa:

    https://hakanuste.github.io/AKCA/

Araştırma terminali:

    https://hakanuste.github.io/AKCA/terminal.html

GitHub Pages yalnızca statik arayüzü barındırır. Gerçek araştırma API'si ve veritabanı Mac'te veya ayrıca seçilmiş güvenli sunucuda çalışmalıdır; tarayıcıdaki statik sayfa tek başına backend yerine geçmez.

## Bağımsız sabit sepet fiyat endeksi

AKÇA'nın doğrudan satıcı fiyat araştırması resmî TÜFE değildir. Referans çalışma kitabında 409 madde adı/kodu vardır; resmî 2022 madde ağırlıkları bulunmaz. Bu ağırlıklar resmî kaynaktan madde kodlarıyla eşleştirilmeden hiçbir ağırlıklı aylık endeks yayımlanmaz. Ürün varyantı ve satıcı fiyatı aynı kalite/paket/birim koşulunda olmalıdır. Yeterli cari ve önceki ay satıcı verisi yoksa hesaplama durdurulur. Detay: docs/METHODOLOGY.md.

## Proje sınırı

AKÇA'nın kendi GitHub deposu, veritabanı, API'si ve çalışma zamanı vardır. ÜLGEN veya ÖTÜKEN koduna ya da veritabanına bağımlı değildir.
