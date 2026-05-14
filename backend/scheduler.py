import requests
import pandas as pd
from datetime import datetime, timedelta
import joblib
import os
import time
import pytz
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler # type: ignore
from app import app, db, DataHistoris, Predictions, WilayahDetails, ModelRegistry, ValidationsLogs
from ispu_logic import kalkulasi_ispu_final, siapkan_fitur_prediksi

load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Set Zona Waktu Baku (Persiapan Server/Docker)
TZ_WIB = pytz.timezone('Asia/Jakarta')

# 1. Muat Model XGBoost 6 Otak (Multi-Output)
MODEL_PATH = 'data_training/xgb_ispu_jatim_multi_otak.pkl' # Pastikan path ini sesuai
if os.path.exists(MODEL_PATH):
    paket_model = joblib.load(MODEL_PATH)
    dict_model_spesialis = paket_model['dict_model_spesialis']
    fitur_model = paket_model['fitur']
    print(f"✅ Model ML berhasil dimuat dari {MODEL_PATH}")
else:
    print(f"⚠️ Peringatan: File model {MODEL_PATH} tidak ditemukan!")

def tarik_data_per_jam():
    """Menarik data polusi udara saat ini untuk seluruh wilayah (Real-time Snapshot)"""
    sekarang = datetime.now(TZ_WIB)
    print(f"[{sekarang.strftime('%Y-%m-%d %H:%M:%S')}] Memulai penarikan data API per jam...")
    
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        
        for wilayah in daftar_wilayah:
            # Normalisasi waktu ke jam 00 
            waktu_jam_ini = sekarang.replace(minute=0, second=0, microsecond=0)
            
            data_ada = DataHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah, waktu_aktual=waktu_jam_ini).first()
            if data_ada:
                continue 

            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={wilayah.latitude}&lon={wilayah.longitude}&appid={API_KEY}"
            try:
                respon = requests.get(url).json()
                data_polusi = respon['list'][0]['components']
                
                dict_polutan = {
                    'PM25': data_polusi.get('pm2_5', 0), 'PM10': data_polusi.get('pm10', 0),
                    'CO': data_polusi.get('co', 0), 'NO2': data_polusi.get('no2', 0), 
                    'O3': data_polusi.get('o3', 0), 'SO2': data_polusi.get('so2', 0)
                }
                hasil_ispu = kalkulasi_ispu_final(dict_polutan)

                catatan_baru = DataHistoris(
                    id_wilayah=wilayah.id_wilayah,
                    waktu_aktual=waktu_jam_ini,
                    pm25=dict_polutan['PM25'], pm10=dict_polutan['PM10'],
                    so2=dict_polutan['SO2'], co=dict_polutan['CO'],
                    no2=dict_polutan['NO2'], ozon=dict_polutan['O3'],
                    skor_ispu=hasil_ispu['nilai_ispu'], kategori_ispu=hasil_ispu['kategori']
                )
                db.session.add(catatan_baru)
                print(f"   [+] Data disimpan: {wilayah.nama_wilayah} (Jam {waktu_jam_ini.strftime('%H:%M')})")
                time.sleep(0.5)
                
            except Exception as e:
                print(f"   [!] Gagal menarik data {wilayah.nama_wilayah}: {e}")
                
        db.session.commit()
    print("--- Penarikan per jam selesai ---")


def eksekusi_prediksi_harian():
    """Memprediksi kualitas udara besok dengan Rekayasa Fitur AI yang tepat"""
    sekarang = datetime.now(TZ_WIB)
    besok = sekarang.date() + timedelta(days=1)
    print(f"[{sekarang.strftime('%Y-%m-%d %H:%M:%S')}] Menjalankan siklus prediksi harian...")
    
    with app.app_context():
        model_aktif = ModelRegistry.query.filter_by(is_active=True).first()
        if not model_aktif:
            model_aktif = ModelRegistry(algoritma='XGBoost Multi-Otak', versi_model='v1.0', is_active=True)
            db.session.add(model_aktif)
            db.session.commit()
        
        daftar_wilayah = WilayahDetails.query.all()
        
        for wilayah in daftar_wilayah:
            besok_dt = datetime.combine(besok, datetime.min.time()).replace(tzinfo=TZ_WIB)
            
            if Predictions.query.filter_by(id_wilayah=wilayah.id_wilayah, target_waktu=besok_dt).first():
                continue # Skip jika sudah ada
            
            # 1. Ambil Data Historis 4 Hari ke belakang (Untuk fitur AI: H-1, H-2, H-3)
            batas_waktu_h4 = datetime.combine(besok - timedelta(days=4), datetime.min.time()).replace(tzinfo=TZ_WIB)
            
            riwayat = DataHistoris.query.filter(
                DataHistoris.id_wilayah == wilayah.id_wilayah,
                DataHistoris.waktu_aktual >= batas_waktu_h4
            ).order_by(DataHistoris.waktu_aktual.asc()).all()

            if len(riwayat) < 4:
                print(f"   [!] Data riwayat {wilayah.nama_wilayah} belum cukup. Skip prediksi.")
                continue

            # 2. Konversi ke DataFrame dan Agregasi Harian
            data_list = []
            for r in riwayat:
                data_list.append({
                    'waktu_aktual': r.waktu_aktual.date(),
                    'nama_wilayah': wilayah.nama_wilayah,
                    'PM25': r.pm25, 'PM10': r.pm10, 'SO2': r.so2, 
                    'CO': r.co, 'NO2': r.no2, 'O3': r.ozon
                })
            
            df_history_raw = pd.DataFrame(data_list)
            # Rata-ratakan per hari supaya formatnya cocok dengan AI
            df_history_harian = df_history_raw.groupby(['waktu_aktual', 'nama_wilayah']).mean().reset_index()

            # 3. Panggil Otak AI (Rekayasa Fitur)
            daftar_polutan = ['PM25', 'PM10', 'SO2', 'CO', 'NO2', 'O3']
            df_input = siapkan_fitur_prediksi(df_history_harian, daftar_polutan, fitur_model)

            # 4. Lakukan Prediksi Multi-Otak
            dict_prediksi = {}
            try:
                for nama_target, model_ai in dict_model_spesialis.items():
                    polutan = nama_target.split('_')[1].split(' ')[0].replace('.', '').upper()
                    pred_val = model_ai.predict(df_input)[0]
                    dict_prediksi[polutan] = float(max(0, pred_val)) 

                hasil_ispu = kalkulasi_ispu_final(dict_prediksi)
                
                prediksi_baru = Predictions(
                    id_model=model_aktif.id_model, id_wilayah=wilayah.id_wilayah,
                    target_waktu=besok_dt,
                    pred_pm25=dict_prediksi.get('PM25', 0), pred_pm10=dict_prediksi.get('PM10', 0),
                    pred_so2=dict_prediksi.get('SO2', 0), pred_co=dict_prediksi.get('CO', 0),
                    pred_no2=dict_prediksi.get('NO2', 0), pred_ozon=dict_prediksi.get('O3', 0),
                    pred_skor_ispu=hasil_ispu['nilai_ispu'], pred_kategori_ispu=hasil_ispu['kategori']
                )
                db.session.add(prediksi_baru)
                print(f"   [OK] Prediksi {wilayah.nama_wilayah}: ISPU {hasil_ispu['nilai_ispu']} ({hasil_ispu['kategori']})")
                
            except Exception as e:
                print(f"   [!] Gagal memprediksi {wilayah.nama_wilayah}: {e}")
                
        db.session.commit()
    print("--- Siklus prediksi harian selesai ---")


def evaluasi_akurasi_harian():
    """Membandingkan prediksi dengan realita hari ini (Diperbaiki kolom databasenya)"""
    sekarang = datetime.now(TZ_WIB)
    hari_ini = sekarang.date()
    hari_ini_dt = datetime.combine(hari_ini, datetime.min.time()).replace(tzinfo=TZ_WIB)
    print(f"[{sekarang.strftime('%Y-%m-%d %H:%M:%S')}] Menjalankan evaluasi akurasi model...")

    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        
        for wilayah in daftar_wilayah:
            prediksi = Predictions.query.filter_by(id_wilayah=wilayah.id_wilayah, target_waktu=hari_ini_dt).first()
            realita_rows = DataHistoris.query.filter(
                DataHistoris.id_wilayah == wilayah.id_wilayah,
                DataHistoris.waktu_aktual >= hari_ini_dt,
                DataHistoris.waktu_aktual < hari_ini_dt + timedelta(days=1)
            ).all()

            if prediksi and realita_rows:
                # Ambil ID Data referensi (jam 12 siang atau data pertama yang mewakili hari itu)
                ref_id_data = realita_rows[0].id_data 
                
                # Rata-rata realita hari ini
                avg_pm25 = sum([r.pm25 for r in realita_rows]) / len(realita_rows)
                avg_pm10 = sum([r.pm10 for r in realita_rows]) / len(realita_rows)
                avg_so2 = sum([r.so2 for r in realita_rows]) / len(realita_rows)
                avg_co = sum([r.co for r in realita_rows]) / len(realita_rows)
                avg_no2 = sum([r.no2 for r in realita_rows]) / len(realita_rows)
                avg_ozon = sum([r.ozon for r in realita_rows]) / len(realita_rows)

                # Menyelamatkan dari Crash: Gunakan kolom sesuai Model SQLAlchemy app.py
                log_baru = ValidationsLogs(
                    id_prediksi=prediksi.id_prediksi,
                    id_data=ref_id_data, # Butuh foreign key id_data dari historis
                    err_pm25=abs(prediksi.pred_pm25 - avg_pm25),
                    err_pm10=abs(prediksi.pred_pm10 - avg_pm10),
                    err_so2=abs(prediksi.pred_so2 - avg_so2),
                    err_co=abs(prediksi.pred_co - avg_co),
                    err_no2=abs(prediksi.pred_no2 - avg_no2),
                    err_ozon=abs(prediksi.pred_ozon - avg_ozon)
                )
                db.session.add(log_baru)
                print(f"   [Checked] Evaluasi {wilayah.nama_wilayah} berhasil dicatat.")
        
        db.session.commit()
    print("--- Evaluasi akurasi harian selesai ---")

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    
    scheduler.add_job(tarik_data_per_jam, 'cron', minute=0)
    scheduler.add_job(evaluasi_akurasi_harian, 'cron', hour=23, minute=50)
    scheduler.add_job(eksekusi_prediksi_harian, 'cron', hour=23, minute=55)
    
    print("--- Scheduler ISPU Jatim telah aktif dan berjalan ---")
    
    tarik_data_per_jam() 
    eksekusi_prediksi_harian()
    # evaluasi_akurasi_harian() # Jangan dinyalakan dulu di tes awal biar tidak dobel record
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass