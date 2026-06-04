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
MODEL_PATH = 'models/xgb_optuna_multioutput.pkl'
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
# LANGKAH 3: PREDIKSI POLUTAN
# ==============================================================================
def eksekusi_prediksi_rolling(waktu_jam_ini):
    print(f" 🔹 [3/4] Menjalankan prediksi Rolling Horizon 24 Jam...")
    with app.app_context():
        model_aktif = ModelRegistry.query.filter_by(is_active=True).first()
        
        if not model_aktif:
            print(f" 💡 [Database Info] Mendaftarkan model otomatis...")
            model_aktif = ModelRegistry(
                algoritma='XGBoost Multi-Output Optuna', 
                versi_model='v1.0',
                hyperparameter={}, #  tuliskan hyperparameter
                is_active=True
            )
            db.session.add(model_aktif)
            db.session.commit()
            print(f" ✅ Model terdaftar dengan ID: {model_aktif.id_model}")
        
        daftar_wilayah = WilayahDetails.query.all()
        prediksi_baru_massal = []
        
        for wilayah in daftar_wilayah:
            batas_waktu_input = waktu_jam_ini - timedelta(days=4)
            riwayat = DataHistoris.query.filter(
                DataHistoris.id_wilayah == wilayah.id_wilayah,
                DataHistoris.waktu_aktual >= batas_waktu_input
            ).order_by(DataHistoris.waktu_aktual.asc()).all()

            if not riwayat: # Jika benar-benar kosong (0), baru lewati
                continue

            # PERBAIKAN NAMA: Ubah 'O3' menjadi 'OZON' agar sama dengan Notebook
            data_list = [{'waktu_aktual': r.waktu_aktual, 'id_wilayah': wilayah.id_wilayah,
                          'pm25': r.pm25, 'pm10': r.pm10, 'so2': r.so2, 
                          'co': r.co, 'no2': r.no2, 'ozon': r.ozon} for r in riwayat]
            
            df_history_jam = pd.DataFrame(data_list)
            
            # PANGGIL FUNGSI MODULAR DARI ISPU_LOGIC 
            df_temp = siapkan_fitur_prediksi(df_history_jam)

            try:
                dict_prediksi_array = {}
                
                # --- CETAK NAMA ASLI MODEL KE TERMINAL ---
                if wilayah.id_wilayah == 1: 
                    print(f" [DEBUG DETEKTIF] Kunci asli model di .pkl: {list(dict_model_spesialis.keys())}")
                
                print("\n" + "="*50)
                print("DEBUG MODEL")
                # print(f"Model meminta {len(fitur_model)} fitur. Contoh:")
                # print("=>", fitur_model[:15])
                # print(f"Kita membuat {len(df_temp.columns)} fitur. Contoh:")
                # print("=>", df_temp.columns.tolist()[:15])
                
                hilang = set(fitur_model) - set(df_temp.columns)
                print(f"\n[!] ADA {len(hilang)} FITUR YANG TIDAK COCOK! Wilayah : {wilayah.nama_wilayah}")
                # print("Contoh yang hilang/salah eja:", list(hilang)[:10])
                print("="*50 + "\n")

                for nama_target, model_ai in dict_model_spesialis.items():
                    # Filter super agresif: buang spasi, titik, dan underscore
                    nama_bersih = nama_target.upper().replace('.', '').replace('_', '').replace(' ', '')
                    if 'PM25' in nama_bersih: polutan = 'PM25'
                    elif 'PM10' in nama_bersih: polutan = 'PM10'
                    elif 'SO2' in nama_bersih: polutan = 'SO2'
                    elif 'CO' in nama_bersih: polutan = 'CO'
                    elif 'NO2' in nama_bersih: polutan = 'NO2'
                    elif 'O3' in nama_bersih or 'OZON' in nama_bersih: polutan = 'OZON' 
                    else: polutan = nama_bersih 
                    
                    # Pastikan semua fitur yang diminta model (termasuk 37 id_wilayah lainnya) diisi dengan angka 0 jika tidak ada.
                    df_input_terurut = df_temp.reindex(columns=fitur_model, fill_value=0)
                    
                    # Pastikan tipe datanya adalah angka (float32) 
                    df_input_terurut = df_input_terurut.astype('float32')
                    
                    # Baris terakhir berisi rekap fitur lag/rolling yang sudah matang untuk jam ini
                    df_baris_terakhir = df_input_terurut.iloc[[-1]]

                    # ========================================================
                    # INTIP ISI DATA SEBELUM MASUK KE AI
                    # ========================================================
                    if wilayah.id_wilayah == 1 and polutan == 'PM25':
                        print(f"\nWUJUD DATA YANG DITERIMA XGBOOST UNTUK SURABAYA:")
                        # Print 5 kolom penting: pm25 mentah jam ini, lag 1 jam, lag 24 jam, rata2, dan jam
                        cek_kolom = ['pm25', 'pm25_H-1', 'pm25_H-24', 'pm25_RollMean_72', 'Jam']
                        # Pastikan kolomnya ada agar tidak error saat di-print
                        kolom_tersedia = [k for k in cek_kolom if k in df_baris_terakhir.columns]
                        print(df_baris_terakhir[kolom_tersedia].to_string(index=False))
                        print("========================================================\n")
                    # ========================================================

                    # Ubah ke NumPy
                    X_pred_np = np.ascontiguousarray(df_baris_terakhir.values)

                    # AI hanya menebak dari 1 baris, hasilnya pasti murni 24 angka
                    pred_raw_log = model_ai.predict(X_pred_np)
                    pred_raw_asli = np.expm1(pred_raw_log)
                    
                    # Sisanya tetap sama
                    pred_list = np.array(pred_raw_asli).flatten().tolist()
                    
                    if len(pred_list) < 24:
                        pred_list.extend([pred_list[-1]] * (24 - len(pred_list)))
                        
                    dict_prediksi_array[polutan] = pred_list

                waktu_mulai = waktu_jam_ini + timedelta(hours=1)
                waktu_akhir = waktu_jam_ini + timedelta(hours=24)
                
                data_eksisting = Predictions.query.filter(
                    Predictions.id_wilayah == wilayah.id_wilayah,
                    Predictions.target_waktu >= waktu_mulai,
                    Predictions.target_waktu <= waktu_akhir
                ).all()
                kamus_eksisting = {pred.target_waktu.strftime('%Y-%m-%d %H:%M:%S'): pred for pred in data_eksisting}

                for jam_ke in range(1, 25):
                    target_waktu_jam = waktu_jam_ini + timedelta(hours=jam_ke)
                    key_waktu = target_waktu_jam.strftime('%Y-%m-%d %H:%M:%S')
                    idx = jam_ke - 1
                    
                    val_pm25 = float(max(0, dict_prediksi_array.get('PM25', [0]*24)[idx]))
                    val_pm10 = float(max(0, dict_prediksi_array.get('PM10', [0]*24)[idx]))
                    val_so2  = float(max(0, dict_prediksi_array.get('SO2', [0]*24)[idx]))
                    val_co   = float(max(0, dict_prediksi_array.get('CO', [0]*24)[idx]))
                    val_no2  = float(max(0, dict_prediksi_array.get('NO2', [0]*24)[idx]))
                    val_ozon_array = dict_prediksi_array.get('OZON', dict_prediksi_array.get('O3', [0]*24))
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
                        pred_eksisting.waktu_dibuat = datetime.utcnow()
                    else:
                        prediksi_baru = Predictions(
                            id_model=model_aktif.id_model, id_wilayah=wilayah.id_wilayah,
                            target_waktu=target_waktu_jam, pred_pm25=val_pm25, pred_pm10=val_pm10, 
                            pred_so2=val_so2, pred_co=val_co, pred_no2=val_no2, pred_ozon=val_ozon, 
                            status="PENDING"
                        )
                        prediksi_baru_massal.append(prediksi_baru)
            except Exception as e:
                import traceback
                print(f"   [!] Gagal memprediksi rolling {wilayah.nama_wilayah}: {e}")
                print(traceback.format_exc())

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
        
        # Kita cari apakah di database sudah ada perhitungan ISPU untuk jam ini
        data_eksisting = IspuHistoris.query.filter_by(waktu_kalkulasi=waktu_jam_ini).all()
        kamus_eksisting = {rekam.id_wilayah: rekam for rekam in data_eksisting}

        # NAMA LIST untuk data yang benar-benar baru
        ispu_aktual_baru = [] 
        
        for wilayah in daftar_wilayah:
            batas_waktu_24j = waktu_jam_ini - timedelta(hours=23) 
            riwayat_24j = DataHistoris.query.filter(
                DataHistoris.id_wilayah == wilayah.id_wilayah,
                DataHistoris.waktu_aktual >= batas_waktu_24j,
                DataHistoris.waktu_aktual <= waktu_jam_ini
            ).order_by(DataHistoris.waktu_aktual.asc()).all()
            
            if not riwayat_24j:
                continue
                
            dict_raw_riil = {
                'PM25': [r.pm25 for r in riwayat_24j],
                'PM10': [r.pm10 for r in riwayat_24j],
                'SO2':  [r.so2 for r in riwayat_24j],
                'CO':   [r.co for r in riwayat_24j],
                'NO2':  [r.no2 for r in riwayat_24j],
                'O3':   [r.ozon for r in riwayat_24j]
            }
            
            hasil_ispu = kalkulasi_ispu_final(dict_raw_riil)
            data_terakhir = riwayat_24j[-1]
            
            # LOGIKA PEMISAHAN 
            rekam_eksisting = kamus_eksisting.get(wilayah.id_wilayah)
            
            if rekam_eksisting:
                # UPDATE: Jika data jam ini sudah ada, timpa nilainya (Tidak perlu append ke list)
                rekam_eksisting.id_data = data_terakhir.id_data
                rekam_eksisting.nilai_ispu = hasil_ispu['skor_ispu_final']
                rekam_eksisting.kategori_ispu = hasil_ispu['kategori_ispu']
                rekam_eksisting.parameter_kritis = hasil_ispu['polutan_kritis']
            else:
                # INSERT: Jika belum ada sama sekali, buat objek baru dan masukkan ke list
                catatan_ispu = IspuHistoris(
                    id_wilayah=wilayah.id_wilayah,
                    id_data=data_terakhir.id_data,
                    waktu_kalkulasi=waktu_jam_ini, 
                    nilai_ispu=hasil_ispu['skor_ispu_final'],
                    kategori_ispu=hasil_ispu['kategori_ispu'],
                    parameter_kritis=hasil_ispu['polutan_kritis']
                )
                ispu_aktual_baru.append(catatan_ispu)
            
        try:
            # Simpan HANYA yang baru ke database
            if ispu_aktual_baru:
                db.session.bulk_save_objects(ispu_aktual_baru)
            
            # Commit akan menyimpan bulk_save (INSERT) dan perubahan rekam_eksisting (UPDATE) sekaligus
            db.session.commit()
            print(f"  [+] Berhasil menyimpan/memperbarui data ISPU Aktual ke Supabase.")
        except Exception as e:
            db.session.rollback()
            print(f"  [!] Gagal menyimpan data ISPU Aktual: {e}")

# ==============================================================================
# MASTER SIKLUS (PIPELINE)
# ==============================================================================
def siklus_utama_per_jam():
    sekarang = datetime.now(TZ_WIB)
    waktu_jam_ini_wib = sekarang.replace(minute=0, second=0, microsecond=0)
    waktu_jam_ini_utc = waktu_jam_ini_wib.astimezone(pytz.UTC).replace(tzinfo=None)
    
    print(f"\n[{sekarang.strftime('%Y-%m-%d %H:%M:%S')}] === MEMULAI SIKLUS UTAMA ===")
    
    tarik_data_per_jam(waktu_jam_ini_utc)           
    evaluasi_akurasi_per_jam(waktu_jam_ini_utc)     
    eksekusi_prediksi_rolling(waktu_jam_ini_utc)    
    hitung_ispu_aktual_per_jam(waktu_jam_ini_utc)   
    
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