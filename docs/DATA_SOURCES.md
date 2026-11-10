# AKÇA veri kaynakları, kapsam ve erişim durumu

Bu kayıt, kodda kullanılan veya planlanan dış veri kaynaklarını birbirinden ayırır. Bir kaynak adaptörünün bulunması tek başına veri lisansını, kalitesini veya gerçek zamanlı erişimi garanti etmez.

| Kaynak | Kullanım | Erişim / anahtar | Üretim sınırlaması | AKÇA durumu |
|---|---|---|---|---|
| Yahoo Finance / yfinance | İkincil fiyat geçmişi, piyasa profili, bazı şirket verileri; BIST .IS sembolleri dahil | Resmî belgelenmiş Yahoo Finance API'si değildir; topluluk istemcisi | Gecikme, sembol eşleşmesi, eksik veri ve kullanım şartları değişebilir. Lisanslı BIST feed'i veya yeniden dağıtım hakkı sayılmaz. | Kod adaptörü var; yalnızca gösterge/araştırma kaynağı |
| SEC EDGAR | ABD bildirimleri, XBRL temel finansallar, 10-K/10-Q/8-K | Ücretsiz açık API; API key gerekmez; tanımlayıcı ve gerçek iletişim e-postalı User-Agent zorunlu | Yalnızca EDGAR bildirimcilerini kapsar. XBRL etiketleri şirketler arasında aynı anlama gelmeyebilir. Fair-access isteği sınırına uyulmalı. | Kod adaptörü var; gerçek User-Agent yapılandırılmalı |
| Borsa İstanbul veri dağıtıcıları | BIST hisse, endeks ve işlem verisi | Borsa İstanbul lisansı ve yetkili veri dağıtıcısı sözleşmesi gerekir | Ücretsiz web ekranındaki gecikmeli bilgi, gerçek zamanlı/tarihsel veri indirme veya yeniden dağıtım hakkı değildir. | Henüz lisanslı sağlayıcı adaptörü yapılandırılmadı |
| KAP / MKK API Portal | BIST ihraççı bildirimleri, finansallar, kurumsal aksiyonlar | MKK API Portal uygulama kaydı, anahtar ve ilgili veri ürünü erişimi gerekir | İlgili API ürününe erişim olmadan otomatik veri çekildiği iddia edilmez. | Entegrasyon noktası ve kaynak kaydı mevcut; gerçek kimlik bilgisi/ürün izni bekleniyor |
| TCMB EVDS 3 | Türkiye döviz, faiz ve makro serileri | EVDS hesabı ve API anahtarı; HTTP header adı key | Seri kodu, frekans, birim, metodoloji ve beta servis davranışı metadata ile doğrulanmalı. | Adaptör var; TCMB_EVDS_API_KEY kullanıcı sunucusunda ayarlanmalı |
| FRED | ABD faiz, tahvil, enflasyon, işsizlik ve makro seriler | Ücretsiz API anahtarı | Serilerin yayımlanma frekansı ve revizyon politikası farklıdır. | Adaptör var; FRED_API_KEY gerekli |
| World Bank Pink Sheet | Aylık uluslararası emtia benchmark serileri | Herkese açık aylık XLSX indirme | Gün içi/spot fiyat değildir. Seri birimi ve benchmark Excel'in açıklama sayfasından alınmalı; CC BY 4.0 atfı korunmalı. | Adaptör var; workbook şema kontrolü canlı testte izlenmeli |
| CoinGecko | Kripto varlık keşfi, fiyat, piyasa değeri, dönemsel değişimler | Public API; Demo key tavsiye edilir | Kotalar, planlar, yeniden dağıtım ve ticari kullanım şartları kontrol edilmeli. | Adaptör var; Demo key isteğe bağlı |
| TÜİK 2022 madde listesi | AKÇA sabit referans sepeti | Kullanıcının sağladığı çalışma kitabı | 409 madde kodu/adı var; bu dosyada 2022 madde ağırlıkları yok. Geçmiş fiyatlar AKÇA baz fiyatı olarak kullanılmaz. | 409 madde aktarıldı; resmî ağırlık eşleştirmesi eksik |

## Veri kabul politikası

1. Her kayıt kaynak URL'si, kaynağın adı, alındığı an, ilgili dönem, para birimi/birim ve erişim koşulunu taşır.
2. Fiyat ile finansal dönem aynı zaman kesitinde değilse birleştirilip tek dönemmiş gibi gösterilmez.
3. Canlı ibaresi yalnızca sağlayıcı sözleşmesi ve veri zaman damgası bunu doğruluyorsa kullanılır.
4. İkincil veya lisans durumu belirsiz kaynaklar bağımsız resmî kaynakla teyit edilmeden kesin finansal olgu sayılmaz.
5. Kaynağa erişilemiyorsa sentetik fiyat ya da finansal veri üretilmez; eksik kapsam raporlanır.
6. BIST resmî bildirimleri ile fiyatları iki farklı erişim katmanı olarak tutulur: KAP/MKK dosya erişimi ve Borsa İstanbul lisanslı piyasa verisi.

## Dış erişim olmadan tam otomasyona geçilemeyecek modüller

- BIST/KAP otomatik şirket finansalları ve açıklama taraması: MKK API Portal uygulama/ürün yetkisi gerekir.
- Resmî ve yeniden dağıtılabilir BIST fiyatları: yetkili veri dağıtıcısı sözleşmesi ve anahtar gerekir.
- FRED reel USD ve ABD makro karşılaştırmaları: FRED API key gerekir.
- TCMB EVDS Türkiye makro/FX: EVDS API key gerekir.
- CoinGecko kotalarının istikrarlı kullanımı: Demo veya uygun ücretli API anahtarı gerekir.
- Aracı kurum araştırmaları: rapor URL'leri, kullanıcı tarafından temin edilen veya lisanslı erişilen araştırma belgeleri gerekir. Konsensüs yalnızca doğrulanmış raporlardan hesaplanır.
