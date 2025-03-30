import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory, session
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, NumberRange, Optional
from werkzeug.utils import secure_filename
from datetime import datetime
import json
import csv
import io
import time
import urllib.parse
from flask_socketio import SocketIO, emit

from googlemaps import GoogleMapsScraper

# Datetime nesnelerini JSON'a uygun formata dönüştürmek için yardımcı fonksiyon
def json_serializable(obj):
    """Datetime ve diğer JSON-olmayan nesneleri string'e çevirir"""
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# Özel JSONEncoder sınıfı
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return super().default(obj)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'googlemapsscraper2024'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'input')
app.config['OUTPUT_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
app.json_encoder = CustomJSONEncoder  # Özel JSON encoder'ı ayarla

# WebSocket için SocketIO oluştur
# Özel encoder ile JSON yapılandırması
def _json_encoder(obj):
    if isinstance(obj, datetime):
        return obj.strftime('%Y-%m-%d %H:%M:%S')
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

# SocketIO için doğrudan json kütüphanesini kullan, ancak özel serileştirme fonksiyonu tanımla
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    json=json,
    json_encoder=_json_encoder,
    ping_timeout=60,           # 60 saniye ping time-out
    ping_interval=25,          # 25 saniyede bir ping gönder
    max_http_buffer_size=10e6, # 10MB maksimum buffer
    async_mode='threading',    # Threading modu kullan
    logger=True,               # Logging aktif
    engineio_logger=True       # Engine.IO logları aktif
)

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Form classes
class ScraperForm(FlaskForm):
    url = StringField('Google Maps URL', validators=[Optional()])
    urls_file = TextAreaField('URLs (Her satıra bir URL)', validators=[Optional()])
    num_reviews = IntegerField('Yorum Sayısı', validators=[NumberRange(min=1, max=1000)], default=100)
    sort_by = SelectField('Sıralama', 
                          choices=[
                              ('newest', 'En Yeni'),
                              ('most_relevant', 'En İlgili'),
                              ('highest_rating', 'En Yüksek Puan'),
                              ('lowest_rating', 'En Düşük Puan')
                          ],
                          default='newest')
    place_info = SelectField('İşletme Bilgisi',
                           choices=[('false', 'Hayır (Yorumları getir)'), ('true', 'Evet (İşletme bilgisi getir)')],
                           default='false')
    submit = SubmitField('Başlat')

class PlacesScraperForm(FlaskForm):
    keyword = StringField('Arama Kelimesi', validators=[DataRequired()])
    submit = SubmitField('İşletmeleri Ara')

class MonitorForm(FlaskForm):
    urls_file = TextAreaField('URLs (Her satıra bir URL)', validators=[DataRequired()])
    from_date = StringField('Başlangıç Tarihi (YYYY-MM-DD)', validators=[DataRequired()])
    submit = SubmitField('İzlemeyi Başlat')

# Sort option mapping
sort_mapping = {'most_relevant': 0, 'newest': 1, 'highest_rating': 2, 'lowest_rating': 3}

@app.route('/')
def index():
    scraper_form = ScraperForm()
    places_form = PlacesScraperForm()
    monitor_form = MonitorForm()
    return render_template('index.html', 
                          scraper_form=scraper_form, 
                          places_form=places_form, 
                          monitor_form=monitor_form)

@app.route('/scrape', methods=['POST'])
def scrape():
    form = ScraperForm()
    if form.validate_on_submit():
        # Create temporary URL file if needed
        urls = []
        if form.url.data:
            temp_url_file = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_urls.txt')
            with open(temp_url_file, 'w') as f:
                f.write(form.url.data + '\n')
            urls = [form.url.data]
        elif form.urls_file.data:
            temp_url_file = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_urls.txt')
            with open(temp_url_file, 'w') as f:
                f.write(form.urls_file.data)
            urls = [line for line in form.urls_file.data.split('\n') if line.strip()]
        else:
            flash('En az bir URL veya URLs dosyası gereklidir', 'danger')
            return redirect(url_for('index'))
            
        # Session'a form verilerini ekle
        session['form_data'] = {
            'sort_by': form.sort_by.data,
            'num_reviews': form.num_reviews.data,
            'place_info': form.place_info.data,
            'urls': urls
        }
            
        # İlk olarak işleme sayfasını döndür
        return render_template('processing.html', 
                               action='review',
                               title='Yorumlar Çekiliyor',
                               message='Google Maps yorumları çekiliyor. Lütfen bekleyin...')
            
    return redirect(url_for('index'))

@socketio.on('start_review_scraping')
def handle_review_scraping():
    """WebSocket üzerinden yorum çekme işlemini başlat"""
    form_data = session.get('form_data', {})
    
    if not form_data:
        safe_emit('error', {'message': 'Form verileri bulunamadı'})
        return
        
    try:
        with GoogleMapsScraper(debug=False) as scraper:
            get_place_info = form_data.get('place_info') == 'true'
            results = []
            
            urls = form_data.get('urls', [])
            total_urls = len(urls)
            for idx, url in enumerate(urls):
                url = url.strip()
                if not url:
                    continue
                    
                # URL bilgisini gönder
                safe_emit('status_update', {'message': f'İşleniyor: {url} ({idx + 1}/{total_urls})'})
                    
                if get_place_info:
                    # Get place info
                    try:
                        place_data = scraper.get_account(url)
                        if place_data:
                            results.append(place_data)
                            
                            # Sonucu WebSocket üzerinden anında gönder
                            safe_emit('new_result', {
                                'type': 'place',
                                'data': place_data
                            })
                    except Exception as place_error:
                        safe_emit('error', {'message': f'İşletme bilgisi alınırken hata: {str(place_error)}'})
                else:
                    # Sort reviews
                    try:
                        error = scraper.sort_by(url, sort_mapping[form_data.get('sort_by', 'newest')])
                        if error == 0:
                            n = 0
                            collected_reviews = []
                            max_reviews = form_data.get('num_reviews', 100)
                            
                            # İlerlemeyi takip et
                            progress_interval = max(1, max_reviews // 10)  # En az %10'luk artışlarla bildir
                            
                            while n < max_reviews:
                                reviews = scraper.get_reviews(n)
                                if len(reviews) == 0:
                                    break
                                    
                                for r in reviews:
                                    collected_reviews.append(r)
                                    
                                    # Her yorum için anlık güncelleme gönder
                                    safe_emit('new_result', {
                                        'type': 'review',
                                        'data': r
                                    })
                                    
                                    # İlerleme durumunu güncelle
                                    if len(collected_reviews) % progress_interval == 0 or len(collected_reviews) >= max_reviews:
                                        progress_percentage = min(100, int((len(collected_reviews) / max_reviews) * 100))
                                        safe_emit('status_update', {
                                            'message': f'İşleniyor: {url} - {len(collected_reviews)}/{max_reviews} yorum ({progress_percentage}%)'
                                        })
                                    
                                    # Küçük bir gecikme ekleyerek UI'ın yanıt vermesini sağla
                                    time.sleep(0.05)  # 0.1 saniye yerine 0.05 sn gecikme (daha hızlı)
                                    
                                n += len(reviews)
                            
                            # Add URL and reviews to results
                            results.extend(collected_reviews)
                        else:
                            safe_emit('error', {'message': f'Yorumlar sıralanamadı. Hata kodu: {error}'})
                    except Exception as review_error:
                        safe_emit('error', {'message': f'Yorumlar alınırken hata: {str(review_error)}'})
            
            # Tamamlandı mesajı
            safe_emit('scraping_completed', {
                'message': f'Çekme işlemi tamamlandı. {len(results)} sonuç bulundu.',
                'count': len(results)
            })
            
            # Save to CSV
            if results:
                output_file = os.path.join(app.config['OUTPUT_FOLDER'], 
                                       f"{form_data.get('sort_by', 'newest')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_reviews.csv")
                if get_place_info:
                    # Save place info
                    df = pd.DataFrame(results)
                    df.to_csv(output_file, index=False)
                else:
                    # Save reviews
                    with open(output_file, 'w', newline='', encoding='utf-8') as f:
                        if results:
                            writer = csv.DictWriter(f, fieldnames=results[0].keys())
                            writer.writeheader()
                            writer.writerows(results)
                            
                # Dosya adını da gönder
                safe_emit('file_saved', {
                    'filename': os.path.basename(output_file)
                })
                
    except Exception as e:
        safe_emit('error', {'message': f'Hata: {str(e)}'})

@app.route('/scrape_places', methods=['POST'])
def scrape_places():
    form = PlacesScraperForm()
    if form.validate_on_submit():
        # Keyword'ü session'a ekle
        session['keyword'] = form.keyword.data
        
        # İlk olarak işleme sayfasını döndür
        return render_template('processing.html', 
                               action='place',
                               title='İşletmeler Aranıyor',
                               message='Google Maps\'te işletmeler aranıyor. Lütfen bekleyin...',
                               keyword=form.keyword.data)
            
    return redirect(url_for('index'))

@socketio.on('start_place_scraping')
def handle_place_scraping():
    """WebSocket üzerinden işletme arama işlemini başlat"""
    keyword = session.get('keyword')
    
    if not keyword:
        safe_emit('error', {'message': 'Arama kelimesi bulunamadı'})
        return
        
    try:
        output_file = os.path.join(app.config['OUTPUT_FOLDER'], 
                                   f"places_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        
        # Gerçek zamanlı güncellemeler için özel bir scraper sınıfı
        class RealtimeScraper(GoogleMapsScraper):
            def __init__(self, *args, **kwargs):
                # Ana sınıfın başlatıcısını çağır
                super().__init__(*args, **kwargs)
                
            def _recover_driver(self):
                """Sürücü ile ilgili bir sorun olduğunda, yeni bir sürücü oluştur"""
                try:
                    self.driver.quit()
                except:
                    pass
                # GoogleMapsScraper.__get_driver metodunu doğrudan çağırmak yerine
                # sınıfı yeniden başlatalım
                self.__init__(debug=self.debug)
                
            def get_places(self, keyword_list=None):
                """İşletmeleri çekmek için ana fonksiyon"""
                df_places = pd.DataFrame()
                # Ana sınıfın search_point oluşturma metodunu kullan
                search_point_url_list = self._gen_search_points_from_square(keyword_list=keyword_list)
                total_places = 0
                
                for i, search_point_url in enumerate(search_point_url_list):
                    # URL bilgisini WebSocket üzerinden gönder
                    status_update_data = {'message': f'İşleniyor: {search_point_url} ({i+1}/{len(search_point_url_list)})'}
                    safe_emit('status_update', status_update_data)
                    
                    try:
                        self.driver.get(search_point_url)
                    except Exception as e:
                        safe_emit('status_update', {'message': f'Sürücü hatası, yeniden bağlanılıyor: {str(e)}'})
                        # Sürücüyü kurtarmaya çalış
                        self._recover_driver()
                        try:
                            self.driver.get(search_point_url)
                        except Exception as e:
                            safe_emit('status_update', {'message': f'URL erişim hatası: {str(e)}'})
                            continue  # Sonraki URL'ye geç
                    
                    # Sayfa yüklenene kadar bekle
                    time.sleep(2)
                    
                    # Scroll işlemi için div bul
                    scrollable_div = None
                    try:
                        # Farklı class name kombinasyonlarını dene
                        scroll_selectors = [
                            '//div[contains(@class, "m6QErb DxyBCb kA9KIf dS8AEf")]',
                            '//div[contains(@class, "m6QErb DxyBCb kA9KIf dS8AEf ecceSd")]',
                            '//div[contains(@class, "m6QErb")]',
                            '//div[contains(@class, "DxyBCb")]',
                            '//div[contains(@class, "kA9KIf")]'
                        ]
                        
                        for selector in scroll_selectors:
                            try:
                                scrollable_div = self.driver.find_element("xpath", selector)
                                if scrollable_div:
                                    break
                            except:
                                continue
                                
                        if not scrollable_div:
                            # Son çare: Sayfa gövdesini al
                            scrollable_div = self.driver.find_element("tag name", "body")
                    except Exception as e:
                        print(f"Scroll div bulunamadı: {str(e)}")
                        safe_emit('status_update', {'message': f'Uyarı: Scroll elementi bulunamadı, genel sayfa kaydırma kullanılacak'})
                    
                    places_dict = {}
                    
                    # Scroll yap ve sonuçları topla
                    for scroll_count in range(5):  # 5 kez scroll yap
                        safe_emit('status_update', {'message': f'Sayfa kaydırılıyor ({scroll_count+1}/5)...'})
                        
                        # Scroll et
                        try:
                            if scrollable_div:
                                self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
                            else:
                                # Genel sayfayı scroll et
                                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        except Exception as e:
                            print(f"Scroll hatası: {str(e)}")
                        
                        time.sleep(1.5)  # Scroll sonrası biraz daha bekle
                        
                        # İşletmeleri topla
                        try:
                            # İşletme bağlantılarını bul
                            place_links = self.driver.find_elements("xpath", '//a[contains(@href, "/maps/place/")]')
                            
                            if len(place_links) > 0:
                                safe_emit('status_update', {'message': f'{len(place_links)} adet işletme bağlantısı bulundu, veriler toplanıyor...'})
                            
                            for place in place_links:
                                try:
                                    href = place.get_attribute('href')
                                    if href and href not in places_dict:
                                        # İşletme ismini bul
                                        name = None
                                        try:
                                            # Farklı class name'leri dene
                                            name_selectors = [
                                                './/div[contains(@class, "qBF1Pd")]',
                                                './/div[contains(@class, "fontHeadlineSmall")]',
                                                './/div[contains(@class, "fontBodyMedium")]'
                                            ]
                                            
                                            for selector in name_selectors:
                                                name_elems = place.find_elements("xpath", selector)
                                                if name_elems and len(name_elems) > 0:
                                                    name = name_elems[0].text.strip()
                                                    if name:
                                                        break
                                                        
                                            # İsim bulunamadıysa URL'den çıkarmayı dene
                                            if not name:
                                                url_parts = href.split('/maps/place/')
                                                if len(url_parts) > 1:
                                                    name = url_parts[1].split('/')[0].replace('+', ' ')
                                        except Exception as e:
                                            print(f"İşletme ismi bulunamadı: {str(e)}")
                                            
                                        # İşletmeyi kaydet
                                        if name:
                                            # URL encoded karakterleri decode et
                                            try:
                                                if '%' in name:
                                                    name = urllib.parse.unquote(name)
                                            except Exception as e:
                                                print(f"İsim decode edilirken hata: {str(e)}")
                                                
                                            places_dict[href] = {
                                                'name': name,
                                                'href': href,
                                                'search_point_url': search_point_url,
                                                'timestamp': datetime.now()
                                            }
                                except Exception as e:
                                    print(f"İşletme detayı alınırken hata: {str(e)}")
                        except Exception as e:
                            print(f"İşletme elementleri bulunamadı: {str(e)}")
                    
                    # Her URL'den sonra sonuçları WebSocket ile gönder
                    if places_dict:
                        new_places = list(places_dict.values())
                        # DataFrame'e ekle
                        temp_df = pd.DataFrame(new_places)
                        if df_places.empty:
                            df_places = temp_df
                        else:
                            df_places = pd.concat([df_places, temp_df], ignore_index=True)
                        
                        # Sonuçları WebSocket üzerinden gönder
                        safe_emit('new_place_batch', {
                            'count': len(new_places),
                            'total': total_places + len(new_places),
                            'data': new_places
                        })
                        
                        total_places += len(new_places)
                        safe_emit('status_update', {'message': f'Toplam {total_places} işletme bulundu'})
                    else:
                        safe_emit('status_update', {'message': f'Bu konumda işletme bulunamadı: {search_point_url}'})
                
                # Sonuçları kaydet
                if not df_places.empty:
                    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
                    os.makedirs(output_dir, exist_ok=True)
                    output_file = os.path.join(output_dir, 'places_wax.csv')
                    df_places.to_csv(output_file, index=False)
                    safe_emit('status_update', {'message': f'Sonuçlar kaydedildi: {len(df_places)} işletme bulundu'})
                else:
                    safe_emit('status_update', {'message': 'Arama sonucunda işletme bulunamadı'})
                
                return df_places
        
        # RealtimeScraper ile çalıştır
        with RealtimeScraper(debug=False) as scraper:
            # İlerleme durumunu ekle
            safe_emit('status_update', {'message': f'Aranıyor: {keyword}'})
            
            try:
                # Placeleri getir
                df_places = scraper.get_places(keyword_list=[keyword])
                
                if df_places is not None and not df_places.empty:
                    # Results should be in output/places_wax.csv
                    places_file = os.path.join(app.config['OUTPUT_FOLDER'], 'places_wax.csv')
                    if os.path.exists(places_file):
                        # Rename to our custom output file
                        os.rename(places_file, output_file)
                        
                        # Read and display results
                        df_places = pd.read_csv(output_file)
                        
                        # URL encoded stringleri decode et
                        if 'name' in df_places.columns:
                            df_places['name'] = df_places['name'].apply(lambda x: 
                                urllib.parse.unquote(x) if isinstance(x, str) and '%' in x else x)
                            
                            # CSV'yi tekrar kaydet (decode edilmiş isimlerle)
                            df_places.to_csv(output_file, index=False)
                        
                        places = df_places.to_dict('records')
                        
                        # Sonuçları toplu olarak gönder
                        safe_emit('scraping_completed', {
                            'message': f'İşletme araması tamamlandı! {len(places)} sonuç bulundu.',
                            'count': len(places)
                        })
                        
                        # Dosya adını da gönder
                        safe_emit('file_saved', {
                            'filename': os.path.basename(output_file)
                        })
                    else:
                        safe_emit('error', {'message': 'İşletme araması sonuç bulunamadı.'})
                else:
                    safe_emit('error', {'message': 'İşletme araması sonuç bulunamadı.'})
            except Exception as inner_e:
                safe_emit('error', {'message': f'İşletme araması sırasında hata oluştu: {str(inner_e)}'})
                
    except Exception as e:
        safe_emit('error', {'message': f'İşletme araması sırasında hata oluştu: {str(e)}'})

@app.route('/monitor', methods=['POST'])
def monitor():
    form = MonitorForm()
    if form.validate_on_submit():
        try:
            # Create temporary URL file
            temp_url_file = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_monitor_urls.txt')
            with open(temp_url_file, 'w') as f:
                f.write(form.urls_file.data)
                
            # This is a basic mock of monitor functionality
            # In the original code, this uses MongoDB which would need more setup
            flash(f'İzleme başlatıldı. Başlangıç tarihi: {form.from_date.data}', 'success')
            return redirect(url_for('index'))
            
        except Exception as e:
            flash(f'İzleme başlatılırken hata oluştu: {str(e)}', 'danger')
            
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(app.config['OUTPUT_FOLDER'], filename, as_attachment=True)

@app.route('/input/square_points.csv')
def get_square_points():
    # If square_points.csv doesn't exist, create a basic one for demo
    square_points_file = os.path.join(app.config['UPLOAD_FOLDER'], 'square_points.csv')
    if not os.path.exists(square_points_file):
        df = pd.DataFrame({
            'city': ['Istanbul', 'Istanbul', 'Istanbul', 'Istanbul'],
            'latitude': [41.0082, 41.0082, 40.9916, 40.9916],
            'longitude': [28.9784, 29.0247, 28.9784, 29.0247]
        })
        df.to_csv(square_points_file, index=False)
        
    return send_from_directory(app.config['UPLOAD_FOLDER'], 'square_points.csv')

# WebSocket route'u
@socketio.on('connect')
def test_connect():
    print('Client connected')

@socketio.on('disconnect')
def test_disconnect():
    print('Client disconnected')

def convert_datetime_to_string(data):
    """Bir sözlük veya liste içindeki tüm datetime nesnelerini string formatına dönüştürür
    ve URL encoded stringleri decode eder"""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            result[key] = convert_datetime_to_string(value)
        return result
    elif isinstance(data, list):
        return [convert_datetime_to_string(item) for item in data]
    elif isinstance(data, datetime):
        return data.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(data, str):
        # URL encoded string'leri decode et
        try:
            # '%' işareti içeren ve muhtemelen encoded olan string'leri decode et
            if '%' in data and ('name' in str(data) or 'href' in str(data)):
                return urllib.parse.unquote(data)
        except:
            pass
        return data
    else:
        return data

# Daha güvenli emit fonksiyonu
def safe_emit(event, data, **kwargs):
    """datetime nesnelerini içeren verileri güvenli bir şekilde emit eder"""
    json_safe_data = convert_datetime_to_string(data)
    emit(event, json_safe_data, **kwargs)

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000) 