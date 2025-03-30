from app_module import app, socketio

if __name__ == '__main__':
    print("Google Maps Scraper Web Uygulaması başlatılıyor...")
    print("Bu uygulamayı kullanmak için tarayıcınızda http://localhost:5000 adresini açın.")
    socketio.run(
        app, 
        debug=True, 
        host='0.0.0.0', 
        port=5000,
        allow_unsafe_werkzeug=True,  # Geliştirme için
        use_reloader=False  # Geliştirme sırasında yeniden yüklemeyi devre dışı bırak (WebSocket bağlantılarını etkileyebilir)
    ) 