# backend/fetch_real_history.py
import requests
from datetime import datetime, timedelta
from app import app, db, HasilPrediksi
from ispu_logic import kalkulasi_ispu_final
from scheduler import DAFTAR_KOTA

# PENTING: Masukkan API Key aslimu di sini
API_KEY = "a5053916414d07c5d4b4f88de911e561" 

def tarik_sejarah_asli():
    print("Menyambung ke Satelit OpenWeatherMap...")
    print("Menarik data sejarah organik 6 hari terakhir...\n")
    
    with app.app_context():
        waktu_sekarang = datetime.now()
        # Mundur 6 hari ke belakang
        waktu_awal = int((waktu_sekarang - timedelta(days=30)).timestamp()) 
        waktu_akhir = int(waktu_sekarang.timestamp())
        
        for nama_kota, kordinat in DAFTAR_KOTA.items():
            print(f"[*] Mengunduh riwayat kota {nama_kota}...")
            # Endpoint khusus History Air Pollution API
            url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={kordinat['lat']}&lon={kordinat['lon']}&start={waktu_awal}&end={waktu_akhir}&appid={API_KEY}"
            
            try:
                respon = requests.get(url).json()
                data_list = respon.get('list', [])
                
                # API mengembalikan data per JAM. Kita harus mengelompokkannya per HARI.
                data_per_hari = {}
                for item in data_list:
                    # Konversi timestamp ke tanggal manusia
                    tanggal = datetime.fromtimestamp(item['dt']).date()
                    if tanggal not in data_per_hari:
                        data_per_hari[tanggal] = []
                    data_per_hari[tanggal].append(item['components'])
                
                # Menghitung nilai Rata-Rata harian
                for tanggal, komponen_list in data_per_hari.items():
                    # Kita hanya simpan data masa lalu (bukan data hari ini/besok)
                    if tanggal >= waktu_sekarang.date():
                        continue
                        
                    avg_pm25 = sum([c['pm2_5'] for c in komponen_list]) / len(komponen_list)
                    avg_pm10 = sum([c['pm10'] for c in komponen_list]) / len(komponen_list)
                    avg_co = sum([c['co'] for c in komponen_list]) / len(komponen_list)
                    avg_no2 = sum([c['no2'] for c in komponen_list]) / len(komponen_list)
                    avg_o3 = sum([c['o3'] for c in komponen_list]) / len(komponen_list)
                    
                    dict_polutan = {
                        'PM25': avg_pm25, 'PM10': avg_pm10,
                        'CO': avg_co, 'NO2': avg_no2, 'O3': avg_o3
                    }
                    
                    # Konversi Rata-rata Polusi menjadi Status ISPU
                    hasil_ispu = kalkulasi_ispu_final(dict_polutan)
                    
                    # Simpan ke Brankas Database
                    prediksi_baru = HasilPrediksi(
                        tanggal_prediksi=tanggal,
                        kota=nama_kota,
                        pm25=avg_pm25, pm10=avg_pm10, co=avg_co, no2=avg_no2, o3=avg_o3,
                        nilai_ispu=hasil_ispu['nilai_ispu'],
                        kategori=hasil_ispu['kategori'],
                        parameter_kritis=hasil_ispu['parameter_kritis']
                    )
                    db.session.add(prediksi_baru)
                    
            except Exception as e:
                print(f"Gagal menarik riwayat {nama_kota}: {e}")
                
        # Konfirmasi penyimpanan ke PostgreSQL
        db.session.commit()
        print("\nSelesai! Database kini sudah berisi data riwayat 100% Organik.")

if __name__ == '__main__':
    tarik_sejarah_asli()