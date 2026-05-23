# backend/fetch_real_history.py
import os
import requests
from datetime import datetime
from app import app, db, WilayahDetails, DataHistoris

def fetch_and_save_raw_data():
    """
    HANYA menarik data polutan mentah dari API.
    """
    # Masuk ke dalam konteks aplikasi Flask agar bisa memakai SQLAlchemy
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        
        # Ganti dengan URL dan Key API sensor yang kamu pakai
        API_KEY = os.getenv("OPENWEATHER_API_KEY")
        
        for wilayah in daftar_wilayah:
            print(f"Menarik data sensor untuk: {wilayah.nama_wilayah}...")
            
            try:
                # ---------------------------------------------------------
                # 1. PROSES PENARIKAN DATA (Sesuaikan dengan API aslimu)
                # ---------------------------------------------------------
                # Contoh endpoint (misal OpenWeather Air Pollution)
                url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={wilayah.latitude}&lon={wilayah.longitude}&appid={API_KEY}"
                response = requests.get(url)
                response.raise_for_status()
                data_json = response.json()
                
                komponen = data_json['list'][0]['components']
                
                # Kita bulatkan waktunya ke jam terdekat agar rapi (00:00, 01:00, dst)
                waktu_sekarang = datetime.now().replace(minute=0, second=0, microsecond=0)
                
                # ---------------------------------------------------------
                # 2. LAPIS PERTAHANAN ANTI-DUPLIKAT (Pengecekan Waktu)
                # ---------------------------------------------------------
                cek_duplikat = DataHistoris.query.filter_by(
                    id_wilayah=wilayah.id_wilayah,
                    waktu_aktual=waktu_sekarang
                ).first()
                
                if cek_duplikat:
                    print(f"Data {wilayah.nama_wilayah} pada {waktu_sekarang} sudah ada. Melewati proses insert.")
                    continue # Langsung lanjut ke kota berikutnya
                
                # ---------------------------------------------------------
                # 3. MURNI MENYIMPAN DATA MENTAH
                # ---------------------------------------------------------
                data_mentah = DataHistoris(
                    id_wilayah=wilayah.id_wilayah,
                    waktu_aktual=waktu_sekarang,
                    pm25=komponen.get('pm2_5', 0),
                    pm10=komponen.get('pm10', 0),
                    co=komponen.get('co', 0),
                    no2=komponen.get('no2', 0),
                    so2=komponen.get('so2', 0),
                    ozon=komponen.get('o3', 0)
                    # Perhatikan: skor_ispu dan kategori_ispu dibiarkan KOSONG/None
                )
                
                db.session.add(data_mentah)
                print(f"Data mentah {wilayah.nama_wilayah} disiapkan untuk disimpan.")
                
            except Exception as e:
                print(f"Gagal menarik data untuk {wilayah.nama_wilayah}: {e}")
                
        # 4. Simpan semua perubahan ke database Supabase
        try:
            db.session.commit()
            print("Proses fetch data mentah selesai dan tersimpan ke database!")
        except Exception as e:
            db.session.rollback()
            print(f"Terjadi kesalahan fatal saat menyimpan ke database: {e}")

if __name__ == "__main__":
    fetch_and_save_raw_data()