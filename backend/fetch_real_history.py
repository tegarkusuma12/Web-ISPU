import requests
import os
import time
import pytz
from dotenv import load_dotenv
from datetime import datetime, timedelta
from app import app, db, DataHistoris, WilayahDetails
from ispu_logic import kalkulasi_ispu_final

load_dotenv()

API_KEY = os.getenv("OPENWEATHER_API_KEY")
TZ_WIB = pytz.timezone('Asia/Jakarta')

def tarik_sejarah_asli():
    print(f"[{datetime.now(TZ_WIB)}] Menyambung ke Satelit OpenWeatherMap...")
    print("Menarik data sejarah organik 29 hari terakhir sesuai standar Permen LHK 14/2020...\n")
    
    with app.app_context():
        # Mengambil daftar kota langsung dari Supabase
        daftar_wilayah = WilayahDetails.query.all()
        
        if not daftar_wilayah:
            print("❌ Tabel wilayah_details masih kosong!")
            return

        waktu_sekarang = datetime.now(TZ_WIB)
        # Ambil rentang waktu dalam timestamp untuk API
        waktu_awal = int((waktu_sekarang - timedelta(days=29)).timestamp()) 
        waktu_akhir = int(waktu_sekarang.timestamp())
        
        for wilayah in daftar_wilayah:
            print(f"[*] Mengunduh riwayat {wilayah.nama_wilayah}...")
            url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={wilayah.latitude}&lon={wilayah.longitude}&start={waktu_awal}&end={waktu_akhir}&appid={API_KEY}"
            
            try:
                respon = requests.get(url)
                if respon.status_code != 200:
                    print(f"    [!] Gagal akses API (Kode {respon.status_code}). Skip...")
                    time.sleep(2) 
                    continue
                    
                respon_json = respon.json()
                data_list = respon_json.get('list', [])
                
                # Mengelompokkan data per jam ke dalam grup tanggal
                data_per_hari = {}
                for item in data_list:
                    tanggal = datetime.fromtimestamp(item['dt'], TZ_WIB).date()
                    if tanggal not in data_per_hari:
                        data_per_hari[tanggal] = []
                    data_per_hari[tanggal].append(item['components'])
                
                for tanggal, komponen_list in data_per_hari.items():
                    # Jangan ambil data hari ini jika belum selesai harinya (biar rata-rata 24 jam akurat)
                    if tanggal >= waktu_sekarang.date():
                        continue
                        
                    waktu_aktual_dt = datetime.combine(tanggal, datetime.min.time()).replace(tzinfo=TZ_WIB)
                    
                    # Cek duplikasi di Supabase
                    data_ada = DataHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah, waktu_aktual=waktu_aktual_dt).first()
                    if data_ada:
                        continue 

                    # --- LOGIKA AGREGASI SESUAI PERMEN LHK 14/2020 ---
                    
                    # 1. PM2.5 & PM10: Rata-rata 24 Jam
                    avg_pm25 = sum([c.get('pm2_5', 0) for c in komponen_list]) / len(komponen_list)
                    avg_pm10 = sum([c.get('pm10', 0) for c in komponen_list]) / len(komponen_list)
                    
                    # 2. O3, NO2, SO2: Nilai Maksimum 1 Jam dalam sehari
                    max_o3 = max([c.get('o3', 0) for c in komponen_list])
                    max_no2 = max([c.get('no2', 0) for c in komponen_list])
                    max_so2 = max([c.get('so2', 0) for c in komponen_list])

                    # 3. CO: Maksimum Rata-rata Bergerak 8 Jam (Sliding Window)
                    co_values = [c.get('co', 0) for c in komponen_list]
                    max_co_8h = 0
                    for i in range(len(co_values)):
                        window = co_values[max(0, i-7) : i+1]
                        avg_window = sum(window) / len(window)
                        if avg_window > max_co_8h:
                            max_co_8h = avg_window
                    
                    dict_polutan = {
                        'PM25': avg_pm25, 'PM10': avg_pm10,
                        'CO': max_co_8h, 'NO2': max_no2, 
                        'O3': max_o3, 'SO2': max_so2 
                    }
                    
                    
                    # Hitung Skor ISPU Akhir
                    hasil_ispu = kalkulasi_ispu_final(dict_polutan)
                    
                    # Simpan ke DataHistoris
                    data_baru = DataHistoris(
                        id_wilayah=wilayah.id_wilayah,
                        waktu_aktual=waktu_aktual_dt,
                        pm25=avg_pm25, 
                        pm10=avg_pm10, 
                        so2=max_so2, 
                        co=max_co_8h, 
                        no2=max_no2, 
                        ozon=max_o3, 
                        skor_ispu=hasil_ispu['nilai_ispu'],
                        kategori_ispu=hasil_ispu['kategori']
                    )
                    db.session.add(data_baru)
                    
            except Exception as e:
                print(f"    [!] Error di {wilayah.nama_wilayah}: {e}")
            
            time.sleep(1.5) # Jeda sopan untuk API
                
        db.session.commit()
        print("\nBerhasil ambil data!")

if __name__ == '__main__':
    tarik_sejarah_asli()