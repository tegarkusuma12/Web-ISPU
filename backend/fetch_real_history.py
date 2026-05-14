import requests
import os
import time  
from dotenv import load_dotenv
from datetime import datetime, timedelta
from app import app, db, DataHistoris, WilayahDetails
from ispu_logic import kalkulasi_ispu_final

load_dotenv()

API_KEY = os.getenv("OPENWEATHER_API_KEY")

def tarik_sejarah_asli():
    print("Menyambung ke Satelit OpenWeatherMap...")
    print("Menarik data sejarah organik 29 hari terakhir...\n")
    
    with app.app_context():
        # Mengambil daftar kota langsung dari Supabase
        daftar_wilayah = WilayahDetails.query.all()
        
        if not daftar_wilayah:
            print("❌ Tabel wilayah_details masih kosong! Harap isi data kota terlebih dahulu.")
            return

        waktu_sekarang = datetime.now()
        waktu_awal = int((waktu_sekarang - timedelta(days=29)).timestamp()) 
        waktu_akhir = int(waktu_sekarang.timestamp())
        
        for wilayah in daftar_wilayah:
            print(f"[*] Mengunduh riwayat {wilayah.nama_wilayah}...")
            url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={wilayah.latitude}&lon={wilayah.longitude}&start={waktu_awal}&end={waktu_akhir}&appid={API_KEY}"
            
            try:
                respon = requests.get(url)
                
                # Pengaman: Cek apakah API marah (diblokir)
                if respon.status_code != 200:
                    print(f"    [!] Satelit menolak akses (Kode {respon.status_code}). Melewati kota ini...")
                    time.sleep(2) 
                    continue
                    
                respon_json = respon.json()
                data_list = respon_json.get('list', [])
                
                data_per_hari = {}
                for item in data_list:
                    # Mengelompokkan berdasarkan tanggal
                    tanggal = datetime.fromtimestamp(item['dt']).date()
                    if tanggal not in data_per_hari:
                        data_per_hari[tanggal] = []
                    data_per_hari[tanggal].append(item['components'])
                
                for tanggal, komponen_list in data_per_hari.items():
                    # Jangan ambil data hari ini jika belum selesai harinya
                    if tanggal >= waktu_sekarang.date():
                        continue
                        
                    # Konversi date menjadi datetime (jam 00:00:00) untuk kolom waktu_aktual
                    waktu_aktual_dt = datetime(tanggal.year, tanggal.month, tanggal.day)
                        
                    # Cek duplikasi berdasarkan id_wilayah (Foreign Key) dan waktu
                    data_ada = DataHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah, waktu_aktual=waktu_aktual_dt).first()
                    if data_ada:
                        continue 
                        
                    # Kalkulasi rata-rata harian
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
                    
                    # Hitung ISPU
                    hasil_ispu = kalkulasi_ispu_final(dict_polutan)
                    
                    # Simpan ke tabel DataHistoris
                    data_baru = DataHistoris(
                        id_wilayah=wilayah.id_wilayah,
                        waktu_aktual=waktu_aktual_dt,
                        pm25=avg_pm25, 
                        pm10=avg_pm10, 
                        so2=avg_so2, 
                        co=avg_co, 
                        no2=avg_no2, 
                        ozon=avg_o3, 
                        skor_ispu=hasil_ispu['nilai_ispu'],
                        kategori_ispu=hasil_ispu['kategori']
                    )
                    db.session.add(data_baru)
                    
            except Exception as e:
                print(f"Gagal menarik riwayat {wilayah.nama_wilayah}: {e}")
            
            # Napas 1.5 detik sebelum menembak kota selanjutnya
            time.sleep(1.5) 
                
        db.session.commit()
        print("\nSelesai! Database Supabase kini sudah terisi penuh dengan data historis ISPU.")

if __name__ == '__main__':
    tarik_sejarah_asli()