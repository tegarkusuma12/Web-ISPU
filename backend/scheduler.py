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

load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Lengkap 38 Kota dan Kabupaten di Jawa Timur
# PASTIKAN penamaan ini SAMA PERSIS dengan teks di kolom 'Kota' pada dataset CSV-mu
DAFTAR_KOTA = {
    "Surabaya": {"lat": -7.2504, "lon": 112.7688},
    "Malang": {"lat": -7.9839, "lon": 112.6214},
    "Kabupaten Malang": {"lat": -8.1667, "lon": 112.5833},
    "Batu": {"lat": -7.8671, "lon": 112.5239},
    "Sidoarjo": {"lat": -7.4478, "lon": 112.7183},
    "Gresik": {"lat": -7.1558, "lon": 112.6550},
    "Bangkalan": {"lat": -7.0255, "lon": 112.9397},
    "Sampang": {"lat": -7.0500, "lon": 113.2500},
    "Pamekasan": {"lat": -7.1667, "lon": 113.4833},
    "Sumenep": {"lat": -7.0167, "lon": 113.8667},
    "Mojokerto": {"lat": -7.4667, "lon": 112.4333},
    "Kabupaten Mojokerto": {"lat": -7.5500, "lon": 112.4333},
    "Jombang": {"lat": -7.5500, "lon": 112.2333},
    "Bojonegoro": {"lat": -7.1500, "lon": 111.8833},
    "Tuban": {"lat": -6.8976, "lon": 112.0649},
    "Lamongan": {"lat": -7.1167, "lon": 112.4167},
    "Madiun": {"lat": -7.6298, "lon": 111.5239},
    "Kabupaten Madiun": {"lat": -7.6167, "lon": 111.6500},
    "Ngawi": {"lat": -7.4000, "lon": 111.4500},
    "Magetan": {"lat": -7.6500, "lon": 111.3333},
    "Ponorogo": {"lat": -7.8667, "lon": 111.4667},
    "Pacitan": {"lat": -8.2000, "lon": 111.1167},
    "Kediri": {"lat": -7.8167, "lon": 112.0167},
    "Kabupaten Kediri": {"lat": -7.8167, "lon": 112.0000},
    "Nganjuk": {"lat": -7.6000, "lon": 111.9000},
    "Blitar": {"lat": -8.0983, "lon": 112.1681},
    "Kabupaten Blitar": {"lat": -8.1333, "lon": 112.2167},
    "Tulungagung": {"lat": -8.0667, "lon": 111.9000},
    "Trenggalek": {"lat": -8.0500, "lon": 111.7167},
    "Pasuruan": {"lat": -7.6453, "lon": 112.9075},
    "Kabupaten Pasuruan": {"lat": -7.7333, "lon": 112.8333},
    "Probolinggo": {"lat": -7.7500, "lon": 113.2167},
    "Kabupaten Probolinggo": {"lat": -7.7667, "lon": 113.3333},
    "Lumajang": {"lat": -8.1333, "lon": 113.2167},
    "Jember": {"lat": -8.1700, "lon": 113.7000},
    "Bondowoso": {"lat": -7.9167, "lon": 113.8167},
    "Situbondo": {"lat": -7.7167, "lon": 114.0000},
    "Banyuwangi": {"lat": -8.2192, "lon": 114.3692}
}

# Muat Model XGBoost 6 Otak dan Daftar Fitur
paket_model = joblib.load('models/xgb_ispu_jatim_multi_otak.pkl')
dict_model_spesialis = paket_model['dict_model_spesialis'] # Ini dictionary berisi 6 model
fitur_model = paket_model['fitur'] # Daftar kolom X saat training

def tarik_data_per_jam():
    """Dijalankan setiap jam untuk menarik data saat ini"""
    print(f"[{datetime.now()}] Memulai penarikan data API per jam...")
    with app.app_context():
        for nama_kota, kordinat in DAFTAR_KOTA.items():
            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={kordinat['lat']}&lon={kordinat['lon']}&appid={API_KEY}"
            try:
                respon = requests.get(url).json()
                data_polusi = respon['list'][0]['components']
                
                # Simpan ke Database (DITAMBAH SO2)
                catatan_baru = RiwayatCuaca(
                    kota=nama_kota,
                    pm25=data_polusi.get('pm2_5', 0),
                    pm10=data_polusi.get('pm10', 0),
                    co=data_polusi.get('co', 0),
                    no2=data_polusi.get('no2', 0),
                    o3=data_polusi.get('o3', 0),
                    so2=data_polusi.get('so2', 0) # <--- TAMBAHAN SO2
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
            
            # 2. Hitung Rata-rata Polusinya (DITAMBAH SO2)
            if riwayat:
                avg_pm25 = sum([r.pm25 for r in riwayat]) / len(riwayat)
                avg_pm10 = sum([r.pm10 for r in riwayat]) / len(riwayat)
                avg_co = sum([r.co for r in riwayat]) / len(riwayat)
                avg_no2 = sum([r.no2 for r in riwayat]) / len(riwayat)
                avg_o3 = sum([r.o3 for r in riwayat]) / len(riwayat)
                avg_so2 = sum([r.so2 for r in riwayat]) / len(riwayat)
            else:
                avg_pm25, avg_pm10, avg_co, avg_no2, avg_o3, avg_so2 = 15.0, 50.0, 1000.0, 5.0, 50.0, 5.0
            
            # 3. Siapkan DataFrame untuk AI
            df_input = pd.DataFrame(0, index=[0], columns=fitur_model)
            
            # 🌟 FITUR TEMPORAL BARU: Agar AI tidak error dimension mismatch
            df_input['Bulan'] = besok.month
            df_input['Is_Weekend'] = 1 if besok.weekday() >= 5 else 0

            # 4. Masukkan Rata-rata tersebut ke kolom fitur AI secara otomatis
            for col in fitur_model:
                col_lower = col.lower()
                if 'kota' in col_lower or 'bulan' in col_lower or 'weekend' in col_lower:
                    continue 
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
                elif 'so2' in col_lower:
                    df_input[col] = avg_so2
                    
            # 5. Nyalakan nilai One-Hot Encoding untuk kota saat ini
            # Asumsi saat training kolomnya bernama 'Kota_Surabaya', 'Kota_Malang', dst
            nama_kolom_kota = f"Kota_{nama_kota}" 
            if nama_kolom_kota in df_input.columns:
                df_input[nama_kolom_kota] = 1
                
            # 6. AI Melakukan Prediksi dengan 6 OTAK BERBEDA
            dict_prediksi = {}
            for nama_target, model_ai in dict_model_spesialis.items():
                # nama_target contohnya: 'TARGET_PM2.5 (µg/m³)_Besok' -> Kita ambil gasnya saja
                polutan = nama_target.split('_')[1].split(' ')[0].replace('.', '') 
                
                # Lakukan prediksi menggunakan model spesialis gas tersebut
                prediksi_angka = model_ai.predict(df_input)[0]
                dict_prediksi[polutan] = float(prediksi_angka)
            
            # 7. Konversi ke ISPU Resmi
            hasil_ispu = kalkulasi_ispu_final(dict_prediksi)
            
            # 8. Simpan ke Database
            prediksi_baru = HasilPrediksi(
                tanggal_prediksi=besok,
                kota=nama_kota,
                pm25=dict_prediksi.get('PM25', 0),
                pm10=dict_prediksi.get('PM10', 0),
                co=dict_prediksi.get('CO', 0),
                no2=dict_prediksi.get('NO2', 0),
                o3=dict_prediksi.get('O3', 0),
                so2=dict_prediksi.get('SO2', 0), # <--- TAMBAHAN SO2
                nilai_ispu=hasil_ispu['nilai_ispu'],
                kategori=hasil_ispu['kategori'],
                parameter_kritis=hasil_ispu['parameter_kritis']
            )
            db.session.add(prediksi_baru)
            print(f" [XGBoost Multi-Otak] Prediksi {nama_kota} selesai (ISPU: {hasil_ispu['nilai_ispu']} - {hasil_ispu['kategori']})")
            
        db.session.commit()

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    # Jadwalkan fungsi tarik data setiap menit ke-0 pada setiap jam
    scheduler.add_job(tarik_data_per_jam, 'cron', minute=0)
    # Jadwalkan prediksi harian jam 23:55 setiap malam
    scheduler.add_job(eksekusi_prediksi_harian, 'cron', hour=23, minute=55)
    
    print("Scheduler ISPU Jatim mulai berjalan...")
    
    # [OPSIONAL] Panggil manual sekali saat file di-run untuk menguji API
    # tarik_data_per_jam() 
    # eksekusi_prediksi_harian()
    
    scheduler.start()