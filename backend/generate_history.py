# backend/generate_history.py
import random
from datetime import datetime, timedelta
from app import app, db, HasilPrediksi
from ispu_logic import kalkulasi_ispu_final
from scheduler import DAFTAR_KOTA

def suntik_data_masa_lalu():
    print("Memulai proses penyuntikan data 6 hari terakhir...")
    
    with app.app_context():
        # Kita mundur 6 hari ke belakang dari hari ini
        for i in range(6, 0, -1):
            tanggal_mundur = datetime.now().date() - timedelta(days=i)
            print(f"Memproses data untuk tanggal: {tanggal_mundur}")
            
            for nama_kota in DAFTAR_KOTA.keys():
                # Membuat angka polusi acak namun masih dalam batas masuk akal (Kategori Baik/Sedang)
                dict_prediksi = {
                    'PM25': round(random.uniform(10.0, 45.0), 2),
                    'PM10': round(random.uniform(20.0, 70.0), 2),
                    'CO': round(random.uniform(500.0, 3000.0), 2),
                    'NO2': round(random.uniform(2.0, 15.0), 2),
                    'O3': round(random.uniform(40.0, 110.0), 2)
                }
                
                # Mengubah angka acak tadi menjadi status ISPU resmi menggunakan rumusmu
                hasil_ispu = kalkulasi_ispu_final(dict_prediksi)
                
                # Masukkan ke brankas database
                prediksi_baru = HasilPrediksi(
                    tanggal_prediksi=tanggal_mundur,
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
                
        # Simpan seluruh perubahan
        db.session.commit()
        print("Selesai! Database kini sudah berisi data riwayat 7 hari.")

if __name__ == '__main__':
    suntik_data_masa_lalu()