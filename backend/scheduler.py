import os
import time
import requests
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler # type: ignore

# Sesuaikan import dengan struktur proyekmu
from app import app, db, DataHistoris, Predictions, WilayahDetails, ModelRegistry, ValidationsLogs, IspuHistoris
from ispu_logic import siapkan_fitur_prediksi, kalkulasi_ispu_final

load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")
TZ_WIB = pytz.timezone('Asia/Jakarta')

# ==============================================================================
# MUAT MODEL ML SAAT STARTUP
# ==============================================================================
MODEL_PATH = 'models/xgb_ispu_jatim_multi_otak.pkl'
if os.path.exists(MODEL_PATH):
    paket_model = joblib.load(MODEL_PATH)
    dict_model_spesialis = paket_model['dict_model_spesialis']
    fitur_model = paket_model['fitur']
    print(f"✅ Model ML berhasil dimuat dari {MODEL_PATH}")
else:
    print(f"⚠️ Peringatan: File model {MODEL_PATH} tidak ditemukan!")

# ==============================================================================
# LANGKAH 1: TARIK DATA RIIL (Dengan Retry Mechanism)
# ==============================================================================
def tarik_data_per_jam(waktu_jam_ini):
    print(f" 🔹 [1/4] Menarik data riil terbaru...")
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        for wilayah in daftar_wilayah:
            data_ada = DataHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah, waktu_aktual=waktu_jam_ini).first()
            if data_ada:
                continue 

            url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={wilayah.latitude}&lon={wilayah.longitude}&appid={API_KEY}"
            
            # Sistem Retry Anti-Badai (Maksimal 3 Kali Coba)
            for percobaan in range(3):
                try:
                    respon = requests.get(url, timeout=10).json()
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
                    break # Keluar dari loop retry jika sukses
                except Exception as e:
                    db.session.rollback()
                    if percobaan == 2:
                        print(f"   [!] Gagal total menarik data {wilayah.nama_wilayah}: {e}")
                    time.sleep(5) # Tunggu 5 detik sebelum coba lagi

# ==============================================================================
# LANGKAH 2: AUDIT AKURASI AI 
# ==============================================================================
def evaluasi_akurasi_per_jam(waktu_jam_ini):
    print(f" 🔹 [2/4] Mengevaluasi akurasi prediksi jam ini...")
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        for wilayah in daftar_wilayah:
            try:
                prediksi_jam_ini = Predictions.query.filter_by(id_wilayah=wilayah.id_wilayah, target_waktu=waktu_jam_ini).first()
                realita_jam_ini = DataHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah, waktu_aktual=waktu_jam_ini).first()

                if prediksi_jam_ini and realita_jam_ini:
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
                    prediksi_jam_ini.status = 'VALIDATED'
                    db.session.add(log_baru)
                    db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"   [!] Gagal mengevaluasi {wilayah.nama_wilayah}: {e}")

# ==============================================================================
# LANGKAH 3: PREDIKSI MASA DEPAN (Murni Microgram, Tanpa Hitung ISPU)
# ==============================================================================
def eksekusi_prediksi_rolling(waktu_jam_ini):
    print(f" 🔹 [3/4] Menjalankan prediksi Rolling Horizon 24 Jam...")
    with app.app_context():
        model_aktif = ModelRegistry.query.filter_by(is_active=True).first()
        if not model_aktif:
            model_aktif = ModelRegistry(algoritma='XGBoost Multi-Otak', versi_model='v1.0', is_active=True)
            db.session.add(model_aktif)
            db.session.commit()
        
        daftar_wilayah = WilayahDetails.query.all()
        prediksi_baru_massal = []
        
        for wilayah in daftar_wilayah:
            batas_waktu_input = waktu_jam_ini - timedelta(days=4)
            riwayat = DataHistoris.query.filter(
                DataHistoris.id_wilayah == wilayah.id_wilayah,
                DataHistoris.waktu_aktual >= batas_waktu_input
            ).order_by(DataHistoris.waktu_aktual.asc()).all()

            if len(riwayat) < 72:
                continue

            data_list = [{'waktu_aktual': r.waktu_aktual, 'nama_wilayah': wilayah.nama_wilayah,
                          'PM25': r.pm25, 'PM10': r.pm10, 'SO2': r.so2, 
                          'CO': r.co, 'NO2': r.no2, 'O3': r.ozon} for r in riwayat]
            
            df_history_jam = pd.DataFrame(data_list)
            
            # Imputasi: Menambal data API yang mungkin bolong dengan nilai sebelumnya
            df_history_jam = df_history_jam.ffill().fillna(0)
            
            daftar_polutan = ['PM25', 'PM10', 'SO2', 'CO', 'NO2', 'O3']
            df_input = siapkan_fitur_prediksi(df_history_jam, daftar_polutan, fitur_model)

            try:
                dict_prediksi_array = {}
                for nama_target, model_ai in dict_model_spesialis.items():
                    polutan = nama_target.split('_')[1].split(' ')[0].replace('.', '').upper()
                    # XGBoost menebak 24 angka
                    dict_prediksi_array[polutan] = model_ai.predict(df_input)[0]

                waktu_mulai = waktu_jam_ini + timedelta(hours=1)
                waktu_akhir = waktu_jam_ini + timedelta(hours=24)
                
                data_eksisting = Predictions.query.filter(
                    Predictions.id_wilayah == wilayah.id_wilayah,
                    Predictions.target_waktu >= waktu_mulai,
                    Predictions.target_waktu <= waktu_akhir
                ).all()
                kamus_eksisting = {pred.target_waktu.strftime('%Y-%m-%d %H:%M:%S'): pred for pred in data_eksisting}

                # Menyebar tebakan Microgram ke 24 jam
                for jam_ke in range(1, 25):
                    target_waktu_jam = waktu_jam_ini + timedelta(hours=jam_ke)
                    key_waktu = target_waktu_jam.strftime('%Y-%m-%d %H:%M:%S')
                    idx = jam_ke - 1
                    
                    val_pm25 = float(max(0, dict_prediksi_array.get('PM25', [0]*24)[idx]))
                    val_pm10 = float(max(0, dict_prediksi_array.get('PM10', [0]*24)[idx]))
                    val_so2  = float(max(0, dict_prediksi_array.get('SO2', [0]*24)[idx]))
                    val_co   = float(max(0, dict_prediksi_array.get('CO', [0]*24)[idx]))
                    val_no2  = float(max(0, dict_prediksi_array.get('NO2', [0]*24)[idx]))
                    val_ozon_array = dict_prediksi_array.get('O3', dict_prediksi_array.get('OZON', [0]*24))
                    val_ozon = float(max(0, val_ozon_array[idx]))

                    pred_eksisting = kamus_eksisting.get(key_waktu)

                    if pred_eksisting:
                        pred_eksisting.pred_pm25 = val_pm25
                        pred_eksisting.pred_pm10 = val_pm10
                        pred_eksisting.pred_so2 = val_so2
                        pred_eksisting.pred_co = val_co
                        pred_eksisting.pred_no2 = val_no2
                        pred_eksisting.pred_ozon = val_ozon
                        pred_eksisting.status = "PENDING"
                        pred_eksisting.waktu_dibuat = datetime.now(pytz.UTC)
                    else:
                        prediksi_baru = Predictions(
                            id_model=model_aktif.id_model, id_wilayah=wilayah.id_wilayah,
                            target_waktu=target_waktu_jam, pred_pm25=val_pm25, pred_pm10=val_pm10, 
                            pred_so2=val_so2, pred_co=val_co, pred_no2=val_no2, pred_ozon=val_ozon, 
                            status="PENDING"
                        )
                        prediksi_baru_massal.append(prediksi_baru)
            except Exception as e:
                print(f"   [!] Gagal memprediksi rolling {wilayah.nama_wilayah}: {e}")

        try:
            if prediksi_baru_massal:
                db.session.bulk_save_objects(prediksi_baru_massal)
            db.session.commit()
            print(f"   [+] Berhasil menyimpan prediksi Microgram ke Supabase.")
        except Exception as e:
            db.session.rollback()
            print(f"   [!] Gagal komit prediksi: {e}")

# ==============================================================================
# LANGKAH 4: HITUNG ISPU AKTUAL (Dari Data Riil)
# ==============================================================================
def hitung_ispu_aktual_per_jam(waktu_jam_ini):
    print(f" 🔹 [4/4] Menghitung ISPU Aktual dari Data Riil...")
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        ispu_aktual_massal = []
        
        for wilayah in daftar_wilayah:
            batas_waktu_24j = waktu_jam_ini - timedelta(hours=23) 
            riwayat_24j = DataHistoris.query.filter(
                DataHistoris.id_wilayah == wilayah.id_wilayah,
                DataHistoris.waktu_aktual >= batas_waktu_24j,
                DataHistoris.waktu_aktual <= waktu_jam_ini
            ).all()
            
            if not riwayat_24j:
                continue
                
            jumlah_data = len(riwayat_24j)
            dict_rata_riil = {
                'PM25': sum(r.pm25 for r in riwayat_24j) / jumlah_data,
                'PM10': sum(r.pm10 for r in riwayat_24j) / jumlah_data,
                'SO2': sum(r.so2 for r in riwayat_24j) / jumlah_data,
                'CO': sum(r.co for r in riwayat_24j) / jumlah_data,
                'NO2': sum(r.no2 for r in riwayat_24j) / jumlah_data,
                'OZON': sum(r.ozon for r in riwayat_24j) / jumlah_data 
            }
            
            hasil_ispu = kalkulasi_ispu_final(dict_rata_riil)
            
            catatan_ispu = IspuHistoris(
                id_wilayah=wilayah.id_wilayah,
                waktu_kalkulasi=waktu_jam_ini,
                skor_pm25=hasil_ispu['skor_pm25'], skor_pm10=hasil_ispu['skor_pm10'],
                skor_so2=hasil_ispu['skor_so2'], skor_co=hasil_ispu['skor_co'],
                skor_no2=hasil_ispu['skor_no2'], skor_ozon=hasil_ispu['skor_ozon'],
                ispu_final=hasil_ispu['skor_ispu_final'],
                polutan_kritis=hasil_ispu['polutan_kritis'],
                kategori_ispu=hasil_ispu['kategori_ispu']
            )
            ispu_aktual_massal.append(catatan_ispu)
            
        try:
            if ispu_aktual_massal:
                db.session.bulk_save_objects(ispu_aktual_massal)
                db.session.commit()
                print(f"   [+] Berhasil menyimpan {len(ispu_aktual_massal)} data ISPU Aktual.")
        except Exception as e:
            db.session.rollback()
            print(f"   [!] Gagal menyimpan data ISPU Aktual: {e}")

# ==============================================================================
# MASTER SIKLUS (PIPELINE)
# ==============================================================================
def siklus_utama_per_jam():
    sekarang = datetime.now(TZ_WIB)
    waktu_jam_ini = sekarang.replace(minute=0, second=0, microsecond=0)
    
    print(f"\n[{sekarang.strftime('%Y-%m-%d %H:%M:%S')}] === MEMULAI SIKLUS UTAMA ===")
    
    tarik_data_per_jam(waktu_jam_ini)           
    evaluasi_akurasi_per_jam(waktu_jam_ini)     
    eksekusi_prediksi_rolling(waktu_jam_ini)    
    hitung_ispu_aktual_per_jam(waktu_jam_ini)   
    
    print(f"[{datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M:%S')}] === SIKLUS SELESAI ===\n")

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(siklus_utama_per_jam, 'cron', minute=0)
    
    print("--- Scheduler ISPU Jatim (Rolling Horizon) telah aktif ---")
    siklus_utama_per_jam() # Run testing 1x saat file dinyalakan
    
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass