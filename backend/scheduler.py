# backend/scheduler.py
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
from ispu_logic import siapkan_fitur_prediksi

load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")

# Set Zona Waktu Baku 
TZ_WIB = pytz.timezone('Asia/Jakarta')

# 1. Muat Model XGBoost
MODEL_PATH = 'models/xgb_ispu_jatim_multi_otak.pkl'
if os.path.exists(MODEL_PATH):
    paket_model = joblib.load(MODEL_PATH)
    dict_model_spesialis = paket_model['dict_model_spesialis']
    fitur_model = paket_model['fitur']
    print(f"✅ Model ML berhasil dimuat dari {MODEL_PATH}")
else:
    print(f"⚠️ Peringatan: File model {MODEL_PATH} tidak ditemukan!")


def tarik_data_per_jam(waktu_jam_ini):
    """LANGKAH 1: Menarik data riil terbaru untuk jam ini"""
    print(f" 🔹 [1/3] Menarik data API riil...")
    
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        for wilayah in daftar_wilayah:
            data_ada = DataHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah, waktu_aktual=waktu_jam_ini).first()
            if data_ada:
                continue 

            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={wilayah.latitude}&lon={wilayah.longitude}&appid={API_KEY}"
            try:
                respon = requests.get(url).json()
                data_polusi = respon['list'][0]['components']
                
                catatan_baru = DataHistoris(
                    id_wilayah=wilayah.id_wilayah,
                    waktu_aktual=waktu_jam_ini,
                    pm25=data_polusi.get('pm2_5', 0), pm10=data_polusi.get('pm10', 0),
                    so2=data_polusi.get('so2', 0), co=data_polusi.get('co', 0),
                    no2=data_polusi.get('no2', 0), ozon=data_polusi.get('o3', 0)
                )
                db.session.add(catatan_baru)
                db.session.commit()
                time.sleep(0.5)
            except Exception as e:
                db.session.rollback()
                print(f"   [!] Gagal menarik data {wilayah.nama_wilayah}: {e}")


def evaluasi_akurasi_per_jam(waktu_jam_ini):
    """LANGKAH 2: Memvalidasi tebakan AI untuk jam ini dengan data riil yang baru ditarik"""
    print(f" 🔹 [2/3] Mengevaluasi akurasi prediksi jam ini...")
    
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        for wilayah in daftar_wilayah:
            try:
                # Cari 1 Baris Prediksi untuk Jam Ini
                prediksi_jam_ini = Predictions.query.filter_by(
                    id_wilayah=wilayah.id_wilayah, 
                    target_waktu=waktu_jam_ini
                ).first()
                
                # Cari 1 Baris Realita untuk Jam Ini
                realita_jam_ini = DataHistoris.query.filter_by(
                    id_wilayah=wilayah.id_wilayah, 
                    waktu_aktual=waktu_jam_ini
                ).first()

                if prediksi_jam_ini and realita_jam_ini:
                    # Cek apakah sudah pernah dievaluasi agar tidak dobel
                    log_ada = ValidationsLogs.query.filter_by(id_prediksi=prediksi_jam_ini.id_prediksi).first()
                    if log_ada:
                        continue
                        
                    log_baru = ValidationsLogs(
                        id_prediksi=prediksi_jam_ini.id_prediksi,
                        id_data=realita_jam_ini.id_data, 
                        err_pm25=abs(prediksi_jam_ini.pred_pm25 - realita_jam_ini.pm25),
                        err_pm10=abs(prediksi_jam_ini.pred_pm10 - realita_jam_ini.pm10),
                        err_so2=abs(prediksi_jam_ini.pred_so2 - realita_jam_ini.so2),
                        err_co=abs(prediksi_jam_ini.pred_co - realita_jam_ini.co),
                        err_no2=abs(prediksi_jam_ini.pred_no2 - realita_jam_ini.no2),
                        err_ozon=abs(prediksi_jam_ini.pred_ozon - realita_jam_ini.ozon)
                    )
                    
                    # Update status prediksi menjadi Selesai/Tervalidasi
                    prediksi_jam_ini.status = 'VALIDATED'
                    
                    db.session.add(log_baru)
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"   [!] Gagal mengevaluasi {wilayah.nama_wilayah}: {e}")


def eksekusi_prediksi_rolling(waktu_jam_ini):
    """LANGKAH 3: Memprediksi 24 jam ke depan menggunakan konsep UPSERT (Update/Insert)"""
    print(f" 🔹 [3/3] Menjalankan prediksi Rolling Horizon 24 Jam...")
    
    with app.app_context():
        model_aktif = ModelRegistry.query.filter_by(is_active=True).first()
        if not model_aktif:
            model_aktif = ModelRegistry(algoritma='XGBoost Multi-Otak', versi_model='v1.0', is_active=True)
            db.session.add(model_aktif)
            db.session.commit()
        
        daftar_wilayah = WilayahDetails.query.all()
        
        for wilayah in daftar_wilayah:
            batas_waktu_input = waktu_jam_ini - timedelta(days=4)
            riwayat = DataHistoris.query.filter(
                DataHistoris.id_wilayah == wilayah.id_wilayah,
                DataHistoris.waktu_aktual >= batas_waktu_input
            ).order_by(DataHistoris.waktu_aktual.asc()).all()

            if len(riwayat) < 72:
                continue

            # Siapkan Data Input AI
            data_list = [{'waktu_aktual': r.waktu_aktual, 'nama_wilayah': wilayah.nama_wilayah,
                          'PM25': r.pm25, 'PM10': r.pm10, 'SO2': r.so2, 
                          'CO': r.co, 'NO2': r.no2, 'O3': r.ozon} for r in riwayat]
            df_history_jam = pd.DataFrame(data_list)
            
            daftar_polutan = ['PM25', 'PM10', 'SO2', 'CO', 'NO2', 'O3']
            df_input = siapkan_fitur_prediksi(df_history_jam, daftar_polutan, fitur_model)

            try:
                dict_prediksi_scalar = {}
                for nama_target, model_ai in dict_model_spesialis.items():
                    polutan = nama_target.split('_')[1].split(' ')[0].replace('.', '').upper()
                    # CATATAN: Menggunakan [0] karena model saat ini baru memuntahkan 1 scalar
                    # Nanti jika sudah dilatih ulang jadi Multi-Output, hapus [0] ini.
                    pred_scalar = model_ai.predict(df_input)[0] 
                    dict_prediksi_scalar[polutan] = pred_scalar

                # UPSERT: Menyebarkan tebakan ke 24 jam ke depan
                for jam_ke in range(1, 25):
                    target_waktu_jam = waktu_jam_ini + timedelta(hours=jam_ke)
                    
                    # Cek apakah jam ini sudah pernah diprediksi sebelumnya
                    pred_eksisting = Predictions.query.filter_by(
                        id_wilayah=wilayah.id_wilayah, target_waktu=target_waktu_jam
                    ).first()

                    val_pm25 = float(max(0, dict_prediksi_scalar.get('PM25', 0)))
                    val_pm10 = float(max(0, dict_prediksi_scalar.get('PM10', 0)))
                    val_so2  = float(max(0, dict_prediksi_scalar.get('SO2', 0)))
                    val_co   = float(max(0, dict_prediksi_scalar.get('CO', 0)))
                    val_no2  = float(max(0, dict_prediksi_scalar.get('NO2', 0)))
                    val_ozon = dict_prediksi_scalar.get('O3', dict_prediksi_scalar.get('OZON', 0))
                    val_ozon = float(max(0, val_ozon))

                    if pred_eksisting:
                        # UPDATE: Timpa angka lama dengan tebakan yang lebih baru/fresh
                        pred_eksisting.pred_pm25 = val_pm25
                        pred_eksisting.pred_pm10 = val_pm10
                        pred_eksisting.pred_so2 = val_so2
                        pred_eksisting.pred_co = val_co
                        pred_eksisting.pred_no2 = val_no2
                        pred_eksisting.pred_ozon = val_ozon
                        pred_eksisting.status = "PENDING"
                        pred_eksisting.waktu_dibuat = datetime.now(pytz.UTC) # Perbarui waktu stempel
                    else:
                        # INSERT: Jika belum ada, buat baru
                        prediksi_baru = Predictions(
                            id_model=model_aktif.id_model,
                            id_wilayah=wilayah.id_wilayah,
                            target_waktu=target_waktu_jam, 
                            pred_pm25=val_pm25, pred_pm10=val_pm10, pred_so2=val_so2,
                            pred_co=val_co, pred_no2=val_no2, pred_ozon=val_ozon, status="PENDING"
                        )
                        db.session.add(prediksi_baru)
                
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"   [!] Gagal memprediksi rolling {wilayah.nama_wilayah}: {e}")


def siklus_utama_per_jam():
    """Fungsi Master yang merantai seluruh proses"""
    sekarang = datetime.now(TZ_WIB)
    waktu_jam_ini = sekarang.replace(minute=0, second=0, microsecond=0)
    
    print(f"\n[{sekarang.strftime('%Y-%m-%d %H:%M:%S')}] === MEMULAI SIKLUS ROLLING HORIZON ===")
    
    tarik_data_per_jam(waktu_jam_ini)
    evaluasi_akurasi_per_jam(waktu_jam_ini)
    eksekusi_prediksi_rolling(waktu_jam_ini)
    
    print(f"[{datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M:%S')}] === SIKLUS SELESAI ===\n")


if __name__ == '__main__':
    scheduler = BlockingScheduler()
    
    # Hanya 1 Jadwal: Berjalan setiap menit ke-0 (Pergantian Jam)
    scheduler.add_job(siklus_utama_per_jam, 'cron', minute=0)
    
    print("--- Scheduler ISPU Jatim (Rolling Horizon) telah aktif ---")
    
    # Jalankan 1 kali saat script pertama kali dihidupkan untuk testing langsung
    siklus_utama_per_jam() 
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass