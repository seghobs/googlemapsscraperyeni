# -*- coding: utf-8 -*-
import itertools
import logging
import re
import time
import traceback
from datetime import datetime

import numpy as np
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver import ChromeOptions as Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

GM_WEBPAGE = 'https://www.google.com/maps/'
MAX_WAIT = 10
MAX_RETRY = 5
MAX_SCROLLS = 40

class GoogleMapsScraper:

    def __init__(self, debug=False):
        self.debug = debug
        self.driver = self.__get_driver()
        self.logger = self.__get_logger()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_value, tb)

        self.driver.close()
        self.driver.quit()

        return True

    def sort_by(self, url, ind):

        self.driver.get(url)
        self.__click_on_cookie_agreement()

        wait = WebDriverWait(self.driver, MAX_WAIT)

        # open dropdown menu
        clicked = False
        tries = 0
        while not clicked and tries < MAX_RETRY:
            try:
                menu_bt = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[@data-value=\'Sort\']')))
                menu_bt.click()

                clicked = True
                time.sleep(3)
            except Exception as e:
                tries += 1
                self.logger.warn('Failed to click sorting button')

            # failed to open the dropdown
            if tries == MAX_RETRY:
                return -1

        #  element of the list specified according to ind
        recent_rating_bt = self.driver.find_elements(By.XPATH, '//div[@role=\'menuitemradio\']')[ind]
        recent_rating_bt.click()

        # wait to load review (ajax call)
        time.sleep(5)

        return 0

    def get_places(self, keyword_list=None):

        df_places = pd.DataFrame()
        search_point_url_list = self._gen_search_points_from_square(keyword_list=keyword_list)

        for i, search_point_url in enumerate(search_point_url_list):
            print(search_point_url)

            if (i+1) % 10 == 0:
                print(f"{i}/{len(search_point_url_list)}")
                # Periyodik kaydetme işleminde sadece mevcut sütunları kullan
                # İlk seçimi yapmadan tüm DataFrame'i kaydet
                df_places.to_csv('output/places_wax.csv', index=False)

            try:
                self.driver.get(search_point_url)
            except NoSuchElementException:
                self.driver.quit()
                self.driver = self.__get_driver()
                self.driver.get(search_point_url)

            # Sayfanın yüklenmesi için bekle
            time.sleep(5)
            
            try:
                # Daha esnek bir yaklaşım - birden fazla olası seçiciyi dene
                scrollable_div = None
                possible_selectors = [
                    "div.m6QErb.DxyBCb.kA9KIf.dS8AEf > div[aria-label*='Results for']",
                    "div[role='feed']",
                    "div[role='region'][aria-label*='results']",
                    "div.m6QErb.DxyBCb.kA9KIf.dS8AEf > div[aria-label*='Results']",
                    ".section-scrollbox"
                ]
                
                for selector in possible_selectors:
                    try:
                        scrollable_div = self.driver.find_element(By.CSS_SELECTOR, selector)
                        print(f"Başarılı seçici: {selector}")
                        break
                    except:
                        continue
                
                if scrollable_div is None:
                    # Seçiciler başarısız olursa, görünür tüm sonuçları almaya çalış
                    print("CSS seçiciler başarısız oldu, JavaScript ile kaydırma deneniyor...")
                    # Sayfayı doğrudan scroll et
                    for _ in range(10):
                        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                else:
                    # Kaydırma işlemi
                    for _ in range(10):
                        self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
                        time.sleep(1)
            except Exception as e:
                print(f"Kaydırma hatası: {str(e)}")
                # Sayfayı doğrudan scroll et
                for _ in range(10):
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)

            # Get places names and href - daha esnek yaklaşım
            time.sleep(2)
            response = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Birden fazla seçici dene
            div_places = []
            try:
                div_places = response.select('div[jsaction] > a[href]')
                if not div_places:
                    div_places = response.select('a[href*="/maps/place/"]')
                if not div_places:
                    div_places = response.select('a[href][aria-label]')
                if not div_places:
                    div_places = response.select('div.Nv2PK > a')
            except Exception as e:
                print(f"Yer seçme hatası: {str(e)}")

            print(f"{len(div_places)} işletme bulundu")
            for div_place in div_places:
                try:
                    href = div_place.get('href', '')
                    name = div_place.get('aria-label', '')
                    
                    # Link Google Maps'e ait değilse atla
                    if not href or not '/maps/' in href:
                        continue
                        
                    # Ad boşsa atla    
                    if not name:
                        continue
                        
                    place_info = {
                        'search_point_url': search_point_url.replace('https://www.google.com/maps/search/', ''),
                        'href': href,
                        'name': name
                    }

                    df_places = pd.concat([df_places, pd.DataFrame([place_info])], ignore_index=True)
                except Exception as e:
                    print(f"Yer işleme hatası: {str(e)}")

            # TODO: implement click to handle > 20 places

        # Minimum gerekli sütunları garanti et
        required_columns = ['search_point_url', 'href', 'name']
        for col in required_columns:
            if col not in df_places.columns:
                df_places[col] = ""
                
        # Yalnızca mevcut sütunları kaydet
        # İlave olma ihtimali olan diğer sütunları da ekleyelim eğer varsa
        possible_columns = ['search_point_url', 'href', 'name', 'rating', 'num_reviews', 'close_time', 'other']
        output_columns = [col for col in possible_columns if col in df_places.columns]
        
        if output_columns:
            df_places = df_places[output_columns]
        
        df_places.to_csv('output/places_wax.csv', index=False)



    def get_reviews(self, offset):

        # scroll to load reviews
        self.__scroll()

        # wait for other reviews to load (ajax)
        time.sleep(4)

        # expand review text
        self.__expand_reviews()

        # parse reviews
        response = BeautifulSoup(self.driver.page_source, 'html.parser')
        # TODO: Subject to changes
        rblock = response.find_all('div', class_='jftiEf fontBodyMedium')
        parsed_reviews = []
        for index, review in enumerate(rblock):
            if index >= offset:
                r = self.__parse(review)
                parsed_reviews.append(r)

                # logging to std out
                print(r)
                
                # Her yorum işlendiğinde ekleriz, ama toplu olarak döndürürüz

        return parsed_reviews



    # need to use different url wrt reviews one to have all info
    def get_account(self, url):

        self.driver.get(url)
        self.__click_on_cookie_agreement()

        # ajax call also for this section
        time.sleep(2)

        resp = BeautifulSoup(self.driver.page_source, 'html.parser')

        place_data = self.__parse_place(resp, url)

        return place_data


    def __parse(self, review):

        item = {}

        try:
            # TODO: Subject to changes
            id_review = review['data-review-id']
        except Exception as e:
            id_review = None

        try:
            # TODO: Subject to changes
            username = review['aria-label']
        except Exception as e:
            username = None

        try:
            # TODO: Subject to changes
            review_text = self.__filter_string(review.find('span', class_='wiI7pd').text)
        except Exception as e:
            review_text = None

        try:
            # TODO: Subject to changes
            rating = float(review.find('span', class_='kvMYJc')['aria-label'].split(' ')[0])
        except Exception as e:
            rating = None

        try:
            # TODO: Subject to changes
            relative_date = review.find('span', class_='rsqaWe').text
        except Exception as e:
            relative_date = None

        try:
            n_reviews = review.find('div', class_='RfnDt').text.split(' ')[3]
        except Exception as e:
            n_reviews = 0

        try:
            user_url = review.find('button', class_='WEBjve')['data-href']
        except Exception as e:
            user_url = None

        item['id_review'] = id_review
        item['caption'] = review_text

        # depends on language, which depends on geolocation defined by Google Maps
        # custom mapping to transform into date should be implemented
        item['relative_date'] = relative_date

        # store datetime of scraping and apply further processing to calculate
        # correct date as retrieval_date - time(relative_date)
        item['retrieval_date'] = datetime.now()
        item['rating'] = rating
        item['username'] = username
        item['n_review_user'] = n_reviews
        #item['n_photo_user'] = n_photos  ## not available anymore
        item['url_user'] = user_url

        return item


    def __parse_place(self, response, url):

        place = {}

        try:
            place['name'] = response.find('h1', class_='DUwDvf fontHeadlineLarge').text.strip()
        except Exception as e:
            place['name'] = None

        try:
            place['overall_rating'] = float(response.find('div', class_='F7nice ').find('span', class_='ceNzKf')['aria-label'].split(' ')[1])
        except Exception as e:
            place['overall_rating'] = None

        try:
            place['n_reviews'] = int(response.find('div', class_='F7nice ').text.split('(')[1].replace(',', '').replace(')', ''))
        except Exception as e:
            place['n_reviews'] = 0

        try:
            place['n_photos'] = int(response.find('div', class_='YkuOqf').text.replace('.', '').replace(',','').split(' ')[0])
        except Exception as e:
            place['n_photos'] = 0

        try:
            place['category'] = response.find('button', jsaction='pane.rating.category').text.strip()
        except Exception as e:
            place['category'] = None

        try:
            place['description'] = response.find('div', class_='PYvSYb').text.strip()
        except Exception as e:
            place['description'] = None

        b_list = response.find_all('div', class_='Io6YTe fontBodyMedium')
        try:
            place['address'] = b_list[0].text
        except Exception as e:
            place['address'] = None

        try:
            place['website'] = b_list[1].text
        except Exception as e:
            place['website'] = None

        try:
            place['phone_number'] = b_list[2].text
        except Exception as e:
            place['phone_number'] = None
    
        try:
            place['plus_code'] = b_list[3].text
        except Exception as e:
            place['plus_code'] = None

        try:
            place['opening_hours'] = response.find('div', class_='t39EBf GUrTXd')['aria-label'].replace('\u202f', ' ')
        except:
            place['opening_hours'] = None

        place['url'] = url

        lat, long, z = url.split('/')[6].split(',')
        place['lat'] = lat[1:]
        place['long'] = long

        return place


    def _gen_search_points_from_square(self, keyword_list=None):
        # TODO: Generate search points from corners of square

        keyword_list = [] if keyword_list is None else keyword_list

        try:
            square_points = pd.read_csv('input/square_points.csv')
        except FileNotFoundError:
            # Alternatif yolları dene
            try:
                import os
                current_dir = os.path.dirname(os.path.abspath(__file__))
                square_points = pd.read_csv(os.path.join(current_dir, 'input', 'square_points.csv'))
            except FileNotFoundError:
                # Son çare olarak basit bir varsayılan nokta oluştur
                print("square_points.csv dosyası bulunamadı, varsayılan değerler kullanılıyor...")
                square_points = pd.DataFrame({
                    'city': ['Istanbul', 'Istanbul', 'Istanbul', 'Istanbul'],
                    'latitude': [41.0082, 41.0082, 40.9916, 40.9916],
                    'longitude': [28.9784, 29.0247, 28.9784, 29.0247]
                })

        cities = square_points['city'].unique()

        search_urls = []

        for city in cities:

            df_aux = square_points[square_points['city'] == city]
            latitudes = df_aux['latitude'].unique()
            longitudes = df_aux['longitude'].unique()
            coordinates_list = list(itertools.product(latitudes, longitudes, keyword_list))

            search_urls += [f"https://www.google.com/maps/search/{coordinates[2]}/@{str(coordinates[1])},{str(coordinates[0])},{str(15)}z"
             for coordinates in coordinates_list]

        return search_urls


    # expand review description
    def __expand_reviews(self):
        try:
            # Birden fazla olası seçiciyi dene
            possible_selectors = [
                'button.w8nwRe.kyuRq',
                'button[jsaction="pane.review.expandReview"]',
                'button[aria-label*="more"]',
                'button.M77dve',
                'jsl button'
            ]
            
            for selector in possible_selectors:
                try:
                    buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if buttons:
                        print(f"Yorum genişletme için başarılı seçici: {selector}")
                        for button in buttons:
                            self.driver.execute_script("arguments[0].click();", button)
                        return
                except Exception as e:
                    print(f"Seçici {selector} için hata: {str(e)}")
                    
            print("Yorum genişletme butonları bulunamadı")
        except Exception as e:
            print(f"Yorum genişletme hatası: {str(e)}")


    def __scroll(self):
        try:
            # Birden fazla olası seçiciyi dene
            possible_selectors = [
                'div.m6QErb.DxyBCb.kA9KIf.dS8AEf',
                'div[role="feed"]',
                'div.section-layout.section-scrollbox',
                '.section-layout-root'
            ]
            
            scrollable_div = None
            for selector in possible_selectors:
                try:
                    scrollable_div = self.driver.find_element(By.CSS_SELECTOR, selector)
                    print(f"Scroll için başarılı seçici: {selector}")
                    break
                except:
                    continue
                    
            if scrollable_div:
                # Kaydırma işlemi
                self.driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
                return True
        except Exception as e:
            print(f"Scroll hatası: {str(e)}")
            
        # Hiçbir seçici çalışmadıysa genel sayfa kaydırmayı dene
        print("Standart sayfa kaydırması deneniyor...")
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        return False


    def __get_logger(self):
        # create logger
        logger = logging.getLogger('googlemaps-scraper')
        logger.setLevel(logging.DEBUG)

        # create console handler and set level to debug
        fh = logging.FileHandler('gm-scraper.log')
        fh.setLevel(logging.DEBUG)

        # create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

        # add formatter to ch
        fh.setFormatter(formatter)

        # add ch to logger
        logger.addHandler(fh)

        return logger


    def __get_driver(self, debug=False):
        options = Options()

        if not self.debug:
            options.add_argument("--headless")
        else:
            options.add_argument("--window-size=1366,768")

        options.add_argument("--disable-notifications")
        #options.add_argument("--lang=en-GB")
        options.add_argument("--accept-lang=en-GB")
        input_driver = webdriver.Chrome(service=Service(), options=options)

         # click on google agree button so we can continue (not needed anymore)
         # EC.element_to_be_clickable((By.XPATH, '//span[contains(text(), "I agree")]')))
        input_driver.get(GM_WEBPAGE)

        return input_driver

    # cookies agreement click
    def __click_on_cookie_agreement(self):
        try:
            # Birden fazla olası metin ve seçici dene
            possible_texts = [
                'Reject all', 
                'I agree',
                'Agree',
                'Accept all',
                'Accept',
                'Tümünü reddet',
                'Kabul ediyorum',
                'Tümünü kabul et'
            ]
            
            for text in possible_texts:
                try:
                    xpath = f'//span[contains(text(), "{text}")]'
                    agree = WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                    agree.click()
                    print(f"Cookie butonu tıklandı: {text}")
                    time.sleep(1)
                    return True
                except:
                    try:
                        # Buton etrafında div veya başka bir öğe olabilir
                        xpath = f'//*[contains(text(), "{text}")]'
                        agree = WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable((By.XPATH, xpath)))
                        agree.click()
                        print(f"Cookie butonu tıklandı (alternatif): {text}")
                        time.sleep(1)
                        return True
                    except:
                        continue
            
            print("Cookie uyarısı bulunamadı veya zaten kabul edilmiş")
            return False
        except Exception as e:
            print(f"Cookie uyarısı hatası: {str(e)}")
            return False

    # util function to clean special characters
    def __filter_string(self, str):
        strOut = str.replace('\r', ' ').replace('\n', ' ').replace('\t', ' ')
        return strOut
