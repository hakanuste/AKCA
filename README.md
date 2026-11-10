# AKÇA — Bağımsız Finansal Araştırma Sistemi

AKÇA; piyasa verisi, şirket finansalları, kurumsal araştırma, değerleme, risk ve bağımsız fiyat/enflasyon araştırması için geliştirilen bağımsız bir araştırma ve karar destek platformudur.

> AKÇA emir iletmez ve aracı kurum hesabına bağlanarak işlem yapmaz. Çıktıları kaynaklı araştırma ve karar desteğidir; kişiye özel yatırım danışmanlığı değildir.

## Proje ilkeleri
- Kaynak, zaman damgası, veri kapsamı ve lisans bilgisi olmadan veri güvenilir kabul edilmez.
- Eksik veya doğrulanmamış veri tamamlanmış gibi gösterilmez.
- Her analiz; varsayımlar, riskler, karşı tez ve geçersizlik koşullarıyla birlikte sunulur.
- Sermaye koruma ve aşağı yönlü risk, getiri beklentisinden önce değerlendirilir.
- AKÇA ayrı bir depo ve çalışma zamanıdır; ÜLGEN veya ÖTÜKEN'e bağımlılığı yoktur.

## Tanıtım sayfası
Statik tanıtım sitesi `web/` klasöründedir. GitHub Pages için depo ayarlarından **Deploy from a branch** seçilip `main` dalındaki `/web` klasörü kaynak olarak seçilebilir.

## İlk teknik modül: bağımsız fiyat endeksi
- `data/reference/tuik_2022_items.csv`: 2022 madde listesi.
- Madde ağırlıkları henüz doğrulanmış veri olarak eklenmemiştir. Ağırlıklar kod ve kapsam bazında eşleştirilmeden endeks hesaplanmaz.
- Her fiyat gözlemi satıcı, ürün açıklaması, bölge, kanal, birim, kaynak URL ve tarih bilgisi taşır.
- Ürün bazında minimum, maksimum, aritmetik ortalama ve medyan hesaplanır.
- Aylık değişim, aynı ürünün önceki ay fiyatıyla karşılaştırılır.
- Yeterli satıcı, kapsama ve doğrulanmış ağırlık koşulları sağlanmazsa endeks yayımlanmaz.

Bu gösterge AKÇA'nın bağımsız sabit sepet fiyat araştırmasıdır; resmî TÜFE değildir.

## Kurulum (macOS / Linux)
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
```

## API
```bash
uvicorn akca.api:app --reload
```
API: http://127.0.0.1:8000 · Dokümantasyon: http://127.0.0.1:8000/docs

## İlk kullanım
```bash
akca init
akca import-items
akca item-count
akca check-weights
akca calculate-index 2026-11
```

## Yol haritası
1. Temel veri modeli, fiyat gözlemi, kalite kontrol ve endeks hesaplama.
2. İzinli veri sağlayıcıları ve piyasa/finansal veri entegrasyonları.
3. Şirket araştırması, değerleme, kurumsal konsensüs ve risk motoru.
4. Halka arz, dolar bazlı performans, fon ve portföy analizi.
5. Kimlik doğrulama, web/PWA, iPhone arayüzü, raporlar ve bildirimler.
6. Test, güvenlik, izleme ve kontrollü dağıtım.

## Test
`pytest`
