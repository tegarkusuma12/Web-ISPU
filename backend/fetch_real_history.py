# backend/fetch_real_history.py
import requests
import os
import time  # <-- TAMBAHAN: Modul waktu untuk memberi jeda
from dotenv import load_dotenv
from datetime import datetime, timedelta
from app import app, db, HasilPrediksi
from ispu_logic import kalkulasi_ispu_final
from scheduler import DAFTAR_KOTA

load_dotenv()

API_KEY = os.getenv("OPENWEATHER_API_KEY")

def tarik_sejarah_asli():
    print("Menyambung ke Satelit OpenWeatherMap...")
    print("Menarik data sejarah organik 6 hari terakhir...\n")
    
    with app.app_context():
        waktu_sekarang = datetime.now()
        waktu_awal = int((waktu_sekarang - timedelta(days=6)).timestamp()) 
        waktu_akhir = int(waktu_sekarang.timestamp())
        
        for nama_kota, kordinat in DAFTAR_KOTA.items():
            print(f"[*] Mengunduh riwayat kota {nama_kota}...")
            url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={kordinat['lat']}&lon={kordinat['lon']}&start={waktu_awal}&end={waktu_akhir}&appid={API_KEY}"
            
            try:
                respon = requests.get(url)
                
                # Pengaman: Cek apakah API marah (diblokir)
                if respon.status_code != 200:
                    print(f"    [!] Satelit menolak akses (Kode {respon.status_code}). Melewati kota ini...")
                    time.sleep(2) # Beri jeda lebih lama jika mulai ditolak
                    continue
                    
                respon_json = respon.json()
                data_list = respon_json.get('list', [])
                
                data_per_hari = {}
                for item in data_list:
                    tanggal = datetime.fromtimestamp(item['dt']).date()
                    if tanggal not in data_per_hari:
                        data_per_hari[tanggal] = []
                    data_per_hari[tanggal].append(item['components'])
                
                for tanggal, komponen_list in data_per_hari.items():
                    if tanggal >= waktu_sekarang.date():
                        continue
                        
                    data_ada = HasilPrediksi.query.filter_by(kota=nama_kota, tanggal_prediksi=tanggal).first()
                    if data_ada:
                        continue 
                        
                    avg_pm25 = sum([c.get('pm2_5', 0) for c in komponen_list]) / len(komponen_list)
                    avg_pm10 = sum([c.get('pm10', 0) for c in komponen_list]) / len(komponen_list)
                    avg_co = sum([c.get('co', 0) for c in komponen_list]) / len(komponen_list)
                    avg_no2 = sum([c.get('no2', 0) for c in komponen_list]) / len(komponen_list)
                    avg_o3 = sum([c.get('o3', 0) for c in komponen_list]) / len(komponen_list)
                    avg_so2 = sum([c.get('so2', 0) for c in komponen_list]) / len(komponen_list)
                    
                    dict_polutan = {
                        'PM25': avg_pm25, 'PM10': avg_pm10,
                        'CO': avg_co, 'NO2': avg_no2, 'O3': avg_o3, 'SO2': avg_so2 
                    }
                    
                    hasil_ispu = kalkulasi_ispu_final(dict_polutan)
                    
                    prediksi_baru = HasilPrediksi(
                        tanggal_prediksi=tanggal,
                        kota=nama_kota,
                        pm25=avg_pm25, pm10=avg_pm10, co=avg_co, no2=avg_no2, o3=avg_o3, so2=avg_so2, 
                        nilai_ispu=hasil_ispu['nilai_ispu'],
                        kategori=hasil_ispu['kategori'],
                        parameter_kritis=hasil_ispu['parameter_kritis']
                    )
                    db.session.add(prediksi_baru)
                    
            except Exception as e:
                print(f"Gagal menarik riwayat {nama_kota}: {e}")
            
            # <-- TAMBAHAN UTAMA: Napas 1.5 detik sebelum menembak kota selanjutnya
            time.sleep(1.5) 
                
        db.session.commit()
        print("\nSelesai! Database kini sudah berisi data riwayat 100% Organik.")

if __name__ == '__main__':
    tarik_sejarah_asli()