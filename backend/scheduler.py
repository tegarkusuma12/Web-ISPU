import requests
import pandas as pd
from datetime import datetime, timedelta
import joblib
import os
import time
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler # type: ignore
from app import app, db, DataHistoris, Predictions, WilayahDetails, ModelRegistry
from ispu_logic import kalkulasi_ispu_final

load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")

# 1. Muat Model XGBoost 6 Otak (Multi-Output)
MODEL_PATH = 'models/xgb_ispu_jatim_multi_otak.pkl'
if os.path.exists(MODEL_PATH):
    paket_model = joblib.load(MODEL_PATH)
    dict_model_spesialis = paket_model['dict_model_spesialis']
    fitur_model = paket_model['fitur']
    print(f"✅ Model ML berhasil dimuat dari {MODEL_PATH}")
else:
    print(f"⚠️ Peringatan: File model {MODEL_PATH} tidak ditemukan!")

def tarik_data_per_jam():
    """Menarik data polusi udara saat ini untuk seluruh wilayah di pangkalan data"""
    print(f"[{datetime.now()}] Memulai penarikan data API per jam...")
    
    with app.app_context():
        # Ambil daftar wilayah langsung dari database
        daftar_wilayah = WilayahDetails.query.all()
        
        for wilayah in daftar_wilayah:
            # --- PENGAMAN ANTI-DUPLIKASI ---
            # Normalisasi waktu ke jam 00 (Misal narik jam 12:05:30 -> dianggap 12:00:00)
            sekarang = datetime.now()
            waktu_jam_ini = sekarang.replace(minute=0, second=0, microsecond=0)
            
            # Cek ke database, apakah jam ini sudah ada datanya?
            data_ada = DataHistoris.query.filter_by(
                id_wilayah=wilayah.id_wilayah, 
                waktu_aktual=waktu_jam_ini
            ).first()
            
            if data_ada:
                # Jika sudah ada, lewati kota ini (continue ke kota berikutnya)
                continue 
            # -------------------------------

            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={wilayah.latitude}&lon={wilayah.longitude}&appid={API_KEY}"
            try:
                respon = requests.get(url).json()
                data_polusi = respon['list'][0]['components']
                
                # Hitung ISPU untuk data real-time saat ini
                dict_polutan = {
                    'PM25': data_polusi.get('pm2_5', 0), 
                    'PM10': data_polusi.get('pm10', 0),
                    'CO': data_polusi.get('co', 0), 
                    'NO2': data_polusi.get('no2', 0), 
                    'O3': data_polusi.get('o3', 0), 
                    'SO2': data_polusi.get('so2', 0)
                }
                hasil_ispu = kalkulasi_ispu_final(dict_polutan)

                # Simpan ke tabel DataHistoris (sebagai catatan real-time)
                catatan_baru = DataHistoris(
                    id_wilayah=wilayah.id_wilayah,
                    waktu_aktual=waktu_jam_ini, # Menggunakan waktu normalisasi
                    pm25=dict_polutan['PM25'],
                    pm10=dict_polutan['PM10'],
                    so2=dict_polutan['SO2'],
                    co=dict_polutan['CO'],
                    no2=dict_polutan['NO2'],
                    ozon=dict_polutan['O3'],
                    skor_ispu=hasil_ispu['nilai_ispu'],
                    kategori_ispu=hasil_ispu['kategori']
                )
                db.session.add(catatan_baru)
                # Tambahkan info jam di terminal agar tahu data jam berapa yang masuk
                print(f"   [+] Data disimpan: {wilayah.nama_wilayah} (Jam {waktu_jam_ini.strftime('%H:%M')})")
                
                # Jeda singkat agar tidak kena blokir dari OpenWeatherMap
                time.sleep(0.5)
                
            except Exception as e:
                print(f"   [!] Gagal menarik data {wilayah.nama_wilayah}: {e}")
                
        db.session.commit()
    print("--- Penarikan per jam selesai ---")

def eksekusi_prediksi_harian():
    """Memprediksi kualitas udara besok menggunakan model XGBoost"""
    print(f"[{datetime.now()}] Menjalankan siklus prediksi harian...")
    besok = datetime.now().date() + timedelta(days=1)
    
    with app.app_context():
        # --- PENGAMAN 1: Cek dan daftarkan model ML ke tabel registry jika kosong ---
        model_aktif = ModelRegistry.query.filter_by(is_active=True).first()
        if not model_aktif:
            model_aktif = ModelRegistry(
                algoritma='XGBoost Multi-Otak',
                versi_model='v1.0',
                is_active=True
            )
            db.session.add(model_aktif)
            db.session.commit()
            print("   [+] Mendaftarkan model XGBoost ke model_registry...")
        # --------------------------------------------------------------------------
        
        daftar_wilayah = WilayahDetails.query.all()
        
        for wilayah in daftar_wilayah:
            # --- PENGAMAN 2: Cek anti-duplikasi prediksi ---
            # Ubah tanggal 'besok' menjadi format datetime (jam 00:00:00)
            besok_dt = datetime.combine(besok, datetime.min.time())
            
            pred_ada = Predictions.query.filter_by(
                id_wilayah=wilayah.id_wilayah, 
                target_waktu=besok_dt
            ).first()
            
            if pred_ada:
                continue # Lewati jika prediksi untuk besok di wilayah ini sudah ada
            # -----------------------------------------------

            # 1. Ambil data historis 3 hari terakhir (72 jam) dari database
            riwayat = DataHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah)\
                        .order_by(DataHistoris.waktu_aktual.desc())\
                        .limit(72).all()
            
            # 2. Hitung Rata-rata Polusinya
            if riwayat:
                avg_pm25 = sum([r.pm25 for r in riwayat]) / len(riwayat)
                avg_pm10 = sum([r.pm10 for r in riwayat]) / len(riwayat)
                avg_co = sum([r.co for r in riwayat]) / len(riwayat)
                avg_no2 = sum([r.no2 for r in riwayat]) / len(riwayat)
                avg_o3 = sum([r.ozon for r in riwayat]) / len(riwayat)
                avg_so2 = sum([r.so2 for r in riwayat]) / len(riwayat)
            else:
                # Nilai default jika database historis suatu kota masih kosong
                avg_pm25, avg_pm10, avg_co, avg_no2, avg_o3, avg_so2 = 15.0, 40.0, 800.0, 10.0, 40.0, 5.0
            
            # 3. Siapkan DataFrame untuk AI
            df_input = pd.DataFrame(0, index=[0], columns=fitur_model)
            df_input['Bulan'] = besok.month
            df_input['Is_Weekend'] = 1 if besok.weekday() >= 5 else 0

            # 4. Masukkan Rata-rata tersebut ke kolom fitur AI secara otomatis
            mapping = {
                'pm25': avg_pm25, 'pm10': avg_pm10, 'co': avg_co,
                'no2': avg_no2, 'o3': avg_o3, 'ozon': avg_o3, 'so2': avg_so2
            }
            
            for col in fitur_model:
                col_lower = col.lower()
                for key, val in mapping.items():
                    if key in col_lower:
                        df_input[col] = val
            
            # 5. Nyalakan nilai One-Hot Encoding untuk kota saat ini
            kolom_kota = f"Kota_{wilayah.nama_wilayah}"
            if kolom_kota in df_input.columns:
                df_input[kolom_kota] = 1
                
            # 6. AI Melakukan Prediksi dengan 6 OTAK BERBEDA
            dict_prediksi = {}
            try:
                for nama_target, model_ai in dict_model_spesialis.items():
                    # Parsing nama polutan dari target model
                    polutan = nama_target.split('_')[1].split(' ')[0].replace('.', '').upper()
                    # Lakukan prediksi dan pastikan nilainya tidak negatif
                    pred_val = model_ai.predict(df_input)[0]
                    dict_prediksi[polutan] = float(max(0, pred_val)) 

                # 7. Konversi ke ISPU Resmi
                hasil_ispu = kalkulasi_ispu_final(dict_prediksi)
                
                # 8. Simpan ke Database
                prediksi_baru = Predictions(
                    id_model=model_aktif.id_model,           # Relasi ke tabel model_registry
                    id_wilayah=wilayah.id_wilayah,           # Relasi ke wilayah
                    target_waktu=besok_dt,                   # Waktu prediksi ditujukan (besok jam 00:00)
                    pred_pm25=dict_prediksi.get('PM25', 0),  
                    pred_pm10=dict_prediksi.get('PM10', 0),
                    pred_so2=dict_prediksi.get('SO2', 0),
                    pred_co=dict_prediksi.get('CO', 0),
                    pred_no2=dict_prediksi.get('NO2', 0),
                    pred_ozon=dict_prediksi.get('O3', 0),
                    pred_skor_ispu=hasil_ispu['nilai_ispu'],
                    pred_kategori_ispu=hasil_ispu['kategori']
                )
                db.session.add(prediksi_baru)
                print(f"   [OK] Prediksi {wilayah.nama_wilayah}: ISPU {hasil_ispu['nilai_ispu']} ({hasil_ispu['kategori']})")
                
            except Exception as e:
                print(f"   [!] Gagal memprediksi {wilayah.nama_wilayah}: {e}")
                
        db.session.commit()
    print("--- Siklus prediksi harian selesai ---")

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    
    # Jalankan setiap jam (menit ke-0)
    scheduler.add_job(tarik_data_per_jam, 'cron', minute=0)
    
    # Jalankan prediksi harian pukul 23:55
    scheduler.add_job(eksekusi_prediksi_harian, 'cron', hour=23, minute=55)
    
    print("--- Scheduler ISPU Jatim telah aktif dan berjalan ---")
    
    # Jalankan sekali saat startup untuk inisialisasi data
    tarik_data_per_jam() 
    eksekusi_prediksi_harian()
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass