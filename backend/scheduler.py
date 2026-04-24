# backend/scheduler.py
import requests
import pandas as pd
from datetime import datetime, timedelta
import joblib
import os
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler # type: ignore
from app import app, db, RiwayatCuaca, HasilPrediksi
from ispu_logic import kalkulasi_ispu_final

API_KEY = os.getenv("OPENWEATHER_API_KEY")

DAFTAR_KOTA = {
    "Surabaya": {"lat": -7.2504, "lon": 112.7688},
    "Malang": {"lat": -7.9839, "lon": 112.6214},
    "Sidoarjo": {"lat": -7.4478, "lon": 112.7183},
    "Gresik": {"lat": -7.1558, "lon": 112.6550},
    "Bojonegoro": {"lat": -7.1500, "lon": 111.8833},
    "Tulungagung": {"lat": -8.0667, "lon": 111.9000},
    "Kediri": {"lat": -7.8167, "lon": 112.0000},
    "Madiun": {"lat": -7.6298, "lon": 111.5239},
    "Jember": {"lat": -8.1700, "lon": 113.7000},
    "Banyuwangi": {"lat": -8.2192, "lon": 114.3692}
}

# Muat Model XGBoost dan Daftar Fitur
paket_model = joblib.load('models/xgb_ispu_jatim.pkl')
model_xgb = paket_model['model']
fitur_model = paket_model['fitur'] # Daftar kolom x saat training

def tarik_data_per_jam():
    """Dijalankan setiap jam untuk menarik data saat ini"""
    print(f"[{datetime.now()}] Memulai penarikan data API per jam...")
    with app.app_context():
        for nama_kota, kordinat in DAFTAR_KOTA.items():
            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={kordinat['lat']}&lon={kordinat['lon']}&appid={API_KEY}"
            try:
                respon = requests.get(url).json()
                data_polusi = respon['list'][0]['components']
                
                # Simpan ke Database
                catatan_baru = RiwayatCuaca(
                    kota=nama_kota,
                    pm25=data_polusi.get('pm2_5', 0),
                    pm10=data_polusi.get('pm10', 0),
                    co=data_polusi.get('co', 0),
                    no2=data_polusi.get('no2', 0),
                    o3=data_polusi.get('o3', 0)
                )
                db.session.add(catatan_baru)
                print(f" Berhasil menyimpan data cuaca: {nama_kota}")
            except Exception as e:
                print(f" Gagal menarik data kota {nama_kota}: {e}")
                
        db.session.commit()
    print("Penarikan selesai!")

def eksekusi_prediksi_harian():
    """Dijalankan setiap 23:55 untuk memprediksi besok berdasarkan data 3 hari terakhir"""
    print(f"[{datetime.now()}] Mengeksekusi Prediksi XGBoost yang Dinamis untuk Besok...")
    besok = datetime.now().date() + timedelta(days=1)
    
    with app.app_context():
        for nama_kota in DAFTAR_KOTA.keys():
            # 1. Ambil Riwayat 3 Hari Terakhir dari Database untuk Kota ini
            riwayat = HasilPrediksi.query.filter_by(kota=nama_kota).order_by(HasilPrediksi.tanggal_prediksi.desc()).limit(3).all()
            
            # 2. Hitung Rata-rata Polusinya (Jika data kosong, beri nilai aman)
            if riwayat:
                avg_pm25 = sum([r.pm25 for r in riwayat]) / len(riwayat)
                avg_pm10 = sum([r.pm10 for r in riwayat]) / len(riwayat)
                avg_co = sum([r.co for r in riwayat]) / len(riwayat)
                avg_no2 = sum([r.no2 for r in riwayat]) / len(riwayat)
                avg_o3 = sum([r.o3 for r in riwayat]) / len(riwayat)
            else:
                avg_pm25, avg_pm10, avg_co, avg_no2, avg_o3 = 15.0, 50.0, 1000.0, 5.0, 50.0
            
            # 3. Siapkan DataFrame untuk AI
            df_input = pd.DataFrame(0, index=[0], columns=fitur_model)
            
            # 4. Masukkan Rata-rata tersebut ke kolom fitur AI secara otomatis
            for col in fitur_model:
                col_lower = col.lower()
                if 'kota' in col_lower:
                    continue # Lewati kolom kota
                if 'pm25' in col_lower or 'pm2.5' in col_lower:
                    df_input[col] = avg_pm25
                elif 'pm10' in col_lower:
                    df_input[col] = avg_pm10
                elif 'co' in col_lower:
                    df_input[col] = avg_co
                elif 'no2' in col_lower:
                    df_input[col] = avg_no2
                elif 'o3' in col_lower or 'ozon' in col_lower:
                    df_input[col] = avg_o3
                    
            # 5. Nyalakan nilai One-Hot Encoding untuk kota saat ini
            nama_kolom_kota = f"kota_{nama_kota}"
            if nama_kolom_kota in df_input.columns:
                df_input[nama_kolom_kota] = 1
                
            # 6. AI Melakukan Prediksi dengan Data Historis
            prediksi = model_xgb.predict(df_input)[0] 
            
            # (Pastikan tipe data dikonversi ke float bawaan Python agar Database tidak menolak)
            dict_prediksi = {
                'PM25': float(prediksi[0]), 'PM10': float(prediksi[1]), 
                'CO': float(prediksi[2]), 'NO2': float(prediksi[3]), 'O3': float(prediksi[4])
            }
            
            # 7. Konversi ke ISPU Resmi
            hasil_ispu = kalkulasi_ispu_final(dict_prediksi)
            
            # 8. Simpan ke Database
            prediksi_baru = HasilPrediksi(
                tanggal_prediksi=besok,
                kota=nama_kota,
                pm25=dict_prediksi['PM25'],
                pm10=dict_prediksi['PM10'],
                co=dict_prediksi['CO'],
                no2=dict_prediksi['NO2'],
                o3=dict_prediksi['O3'],
                nilai_ispu=hasil_ispu['nilai_ispu'],
                kategori=hasil_ispu['kategori'],
                parameter_kritis=hasil_ispu['parameter_kritis']
            )
            db.session.add(prediksi_baru)
            print(f" [XGBoost] Prediksi {nama_kota} selesai (ISPU: {hasil_ispu['nilai_ispu']} - {hasil_ispu['kategori']})")
            
        db.session.commit()

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    # Jadwalkan fungsi tarik data setiap menit ke-0 pada setiap jam (misal: 01:00, 02:00)
    scheduler.add_job(tarik_data_per_jam, 'cron', minute=0)
    # Jadwalkan prediksi harian jam 23:55 setiap malam
    scheduler.add_job(eksekusi_prediksi_harian, 'cron', hour=23, minute=55)
    
    print("Scheduler ISPU Jatim mulai berjalan...")
    
    # [OPSIONAL] Panggil manual sekali saat file di-run untuk menguji API
    tarik_data_per_jam() 
    eksekusi_prediksi_harian()
    
    scheduler.start()