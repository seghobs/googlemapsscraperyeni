# Google Maps Scraper Web Uygulaması

Bu web uygulaması, orijinal Google Maps Scraper komut satırı aracının Flask ile oluşturulmuş kullanıcı dostu bir web arayüzüdür. Tailwind CSS ile modern bir tasarıma sahiptir.

## Özellikler

- 🔍 **Google Maps Yorumlarını Çekme**: Belirli bir mekan için en son yorumları çeker
- 🏪 **İşletme Arama**: Belirli bir anahtar kelimeye göre işletmeleri arar
- 📊 **İzleme Modu**: MongoDB ile yorum izleme (tam işlevsellik için ek kurulum gerektirir)
- 📁 **CSV Dışa Aktarma**: Tüm sonuçlar CSV formatında dışa aktarılabilir
- 🌐 **Kullanıcı Dostu Arayüz**: Tailwind CSS ile modern ve duyarlı tasarım

## Kurulum

### Gereksinimler
- Python 3.9 veya üstü
- Chrome tarayıcısı
- ChromeDriver (otomatik indirme için webdriver-manager kullanılır)

### Adımlar

1. Gereksinimleri yükleyin:
   ```
   pip install -r app/requirements.txt
   ```

2. Uygulamayı başlatın:
   ```
   run.bat
   ```
   
   veya manuel olarak:
   ```
   cd app
   python run.py
   ```

3. Tarayıcınızda aşağıdaki adresi açın:
   ```
   http://localhost:5000
   ```

## Kullanım Kılavuzu

### 1. Yorumları Çekme

1. "Yorum Çekme" sekmesini seçin
2. Google Maps URL'sini girin veya birden fazla URL'yi metin kutusuna yapıştırın
3. İstediğiniz yorum sayısını belirleyin (varsayılan: 100)
4. Sıralama tercihini seçin (En Yeni, En İlgili, En Yüksek Puan, En Düşük Puan)
5. İşletme bilgisi veya yorumları çekmek istediğinizi seçin
6. "Başlat" düğmesine tıklayın
7. Sonuçlar bir tabloda gösterilecek ve CSV olarak indirilebilecektir

### 2. İşletme Arama

1. "İşletme Arama" sekmesini seçin
2. Arama anahtar kelimesini girin (örn. "romantik restoran")
3. "İşletmeleri Ara" düğmesine tıklayın
4. Sonuçlar bir tabloda gösterilecek ve CSV olarak indirilebilecektir

### 3. İzleme Modu

**Not**: İzleme modu tam işlevsellik için MongoDB kurulumu gerektirir.

1. "İzleme Modu" sekmesini seçin
2. İzlemek istediğiniz URL'leri girin (her satıra bir URL)
3. Başlangıç tarihini YYYY-MM-DD formatında girin
4. "İzlemeyi Başlat" düğmesine tıklayın

## Teknik Notlar

- Bu uygulama, orijinal Google Maps Scraper'ın işlevlerine web arayüzü eklemektedir
- Selenium ile tarayıcı otomasyonu kullanılmaktadır
- Veriler CSV dosyalarında veya MongoDB'de (izleme modu için) saklanır
- Tailwind CSS CDN kullanılmaktadır, internet bağlantısı gereklidir

## Uyarılar

- Google'ın hizmet şartlarını ihlal etmemeye dikkat edin
- Aşırı kullanım IP engellemelerine yol açabilir
- Bu araç yalnızca eğitim amaçlıdır

## Lisans

Orijinal Google Maps Scraper lisansı geçerlidir. 