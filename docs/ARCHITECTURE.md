# AKÇA mimari başlangıç

## Bağımsızlık
AKÇA kendi deposu, veritabanı, API'si ve arayüzüne sahip ayrı projedir. ÜLGEN'e çalışma zamanı bağımlılığı yoktur.

## Katmanlar
- `agents/` (sonraki aşama): piyasa, şirket, kurum, makro ve risk araştırma ajanları.
- `src/akca/`: domain ve uygulama servisleri.
- `data/`: referans ve yerel veri.
- SQLite ilk prototip; çok kullanıcılı/uzak üretim aşamasında PostgreSQL.
- FastAPI ilk API; daha sonra kimlik doğrulama ve yetkilendirme.
- `web/`: statik tanıtım sayfası; devamında web/PWA terminali.

## İlk geliştirme dilimi
2022 sepeti -> doğrudan fiyat gözlemleri -> kalite kontrol -> aylık ürün istatistikleri -> ağırlıklı sabit sepet endeksi.
