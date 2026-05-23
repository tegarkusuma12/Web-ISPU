# backend/fetch_real_history.py
import os
import requests
from datetime import datetime, timedelta
from app import app, db, WilayahDetails, DataHistoris

def fetch_and_save_raw_data():
    """
    Menarik data polutan mentah dari API.
    """
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        API_KEY = os.getenv("OPENWEATHER_API_KEY")
        
        # 1. Tentukan rentang waktu 
        end_date = datetime.now().replace(minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=30) # 30 hari terakhir sampai jam ini
        
        # OpenWeatherMap API History membutuhkan format Unix Timestamp
        start_unix = int(start_date.timestamp())
        end_unix = int(end_date.timestamp())
        
        for wilayah in daftar_wilayah:
            print(f"Menarik data historis untuk: {wilayah.nama_wilayah}...")
            
            try:
                # ---------------------------------------------------------
                # 2. GANTI ENDPOINT KE HISTORICAL API
                # ---------------------------------------------------------
                url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={wilayah.latitude}&lon={wilayah.longitude}&start={start_unix}&end={end_unix}&appid={API_KEY}"
                response = requests.get(url)
                response.raise_for_status()
                data_json = response.json()
                
                # ---------------------------------------------------------
                # 3. CEK ANTI-DUPLIKAT (Menggunakan Set Memori)
                # ---------------------------------------------------------
                # Daripada mengecek DB satu-satu untuk 720 jam, kita tarik semua 
                # tanggal yang sudah ada di DB untuk kota ini ke dalam Python Set.
                existing_records = DataHistoris.query.filter(
                    DataHistoris.id_wilayah == wilayah.id_wilayah,
                    DataHistoris.waktu_aktual >= start_date
                ).with_entities(DataHistoris.waktu_aktual).all()
                
                existing_dates = {record[0] for record in existing_records}
                
                data_baru_count = 0
                
                # ---------------------------------------------------------
                # 4. LOOPING DATA PER JAM DARI API
                # ---------------------------------------------------------
                # data_json['list'] sekarang berisi array data dari H-30 sampai hari ini
                for item in data_json['list']:
                    waktu_aktual = datetime.fromtimestamp(item['dt'])
                    
                    # Cek duplikat menggunakan Set (jauh lebih cepat dari query DB)
                    if waktu_aktual in existing_dates:
                        continue
                        
                    komponen = item['components']
                    
                    data_mentah = DataHistoris(
                        id_wilayah=wilayah.id_wilayah,
                        waktu_aktual=waktu_aktual,
                        pm25=komponen.get('pm2_5', 0),
                        pm10=komponen.get('pm10', 0),
                        co=komponen.get('co', 0),
                        no2=komponen.get('no2', 0),
                        so2=komponen.get('so2', 0),
                        ozon=komponen.get('o3', 0)
                    )
                    
                    db.session.add(data_mentah)
                    data_baru_count += 1
                    
                print(f"Menambahkan {data_baru_count} data jam baru untuk {wilayah.nama_wilayah}.")
                
                db.session.commit()
                print(f"✅ Data {wilayah.nama_wilayah} berhasil diamankan ke database.")

            except Exception as e:
                db.session.rollback()
                print(f"Gagal menarik data historis untuk {wilayah.nama_wilayah}: {e}")

if __name__ == "__main__":
    fetch_and_save_raw_data()