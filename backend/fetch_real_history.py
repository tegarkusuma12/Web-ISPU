# backend/fetch_real_history.py
import os
import requests
from datetime import datetime, timedelta
from app import app, db, WilayahDetails, DataHistoris, IspuHistoris
from ispu_logic import kalkulasi_ispu_final

def fetch_and_save_raw_data():
    """
    Menarik data polutan mentah dari API.
    """
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        API_KEY = os.getenv("OPENWEATHER_API_KEY")
        
        # 1. Tentukan rentang waktu 
        end_date = datetime.now().replace(minute=0, second=0, microsecond=0)
        start_date = end_date - timedelta(days=30) # 30 hari terakhir sampai jam ini
        
        # OpenWeatherMap API History membutuhkan format Unix Timestamp
        start_unix = int(start_date.timestamp())
        end_unix = int(end_date.timestamp())
        
        for wilayah in daftar_wilayah:
            print(f"Menarik data historis untuk: {wilayah.nama_wilayah}...")
            
            try:
                # ---------------------------------------------------------
                # 2. GANTI ENDPOINT KE HISTORICAL API
                # ---------------------------------------------------------
                url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={wilayah.latitude}&lon={wilayah.longitude}&start={start_unix}&end={end_unix}&appid={API_KEY}"
                response = requests.get(url)
                response.raise_for_status()
                data_json = response.json()
                
                # ---------------------------------------------------------
                # 3. CEK ANTI-DUPLIKAT (Menggunakan Set Memori)
                # ---------------------------------------------------------
                # Daripada mengecek DB satu-satu untuk 720 jam, kita tarik semua 
                # tanggal yang sudah ada di DB untuk kota ini ke dalam Python Set.
                existing_records = DataHistoris.query.filter(
                    DataHistoris.id_wilayah == wilayah.id_wilayah,
                    DataHistoris.waktu_aktual >= start_date
                ).with_entities(DataHistoris.waktu_aktual).all()
                
                existing_dates = {record[0] for record in existing_records}
                
                data_baru_count = 0
                
                # ---------------------------------------------------------
                # 4. LOOPING DATA PER JAM DARI API
                # ---------------------------------------------------------
                # data_json['list'] sekarang berisi array data dari H-30 sampai hari ini
                for item in data_json['list']:
                    waktu_aktual = datetime.utcfromtimestamp(item['dt'])
                    
                    # Cek duplikat menggunakan Set (jauh lebih cepat dari query DB)
                    if waktu_aktual in existing_dates:
                        continue
                        
                    komponen = item['components']
                    
                    data_mentah = DataHistoris(
                        id_wilayah=wilayah.id_wilayah,
                        waktu_aktual=waktu_aktual,
                        pm25=komponen.get('pm2_5', 0),
                        pm10=komponen.get('pm10', 0),
                        co=komponen.get('co', 0),
                        no2=komponen.get('no2', 0),
                        so2=komponen.get('so2', 0),
                        ozon=komponen.get('o3', 0)
                    )
                    
                    db.session.add(data_mentah)
                    data_baru_count += 1
                    
                print(f"Menambahkan {data_baru_count} data jam baru untuk {wilayah.nama_wilayah}.")
                
                db.session.commit()
                print(f"✅ Data {wilayah.nama_wilayah} berhasil diamankan ke database.")

            except Exception as e:
                db.session.rollback()
                print(f"Gagal menarik data historis untuk {wilayah.nama_wilayah}: {e}")

# ==============================================================================
# FUNGSI BACKFILL: MENGHITUNG ISPU MUNDUR UNTUK 30 HARI
# ==============================================================================
def backfill_ispu_historis_30_hari():
    print("\n🚀 Memulai Proses Backfilling ISPU Historis (Aturan 24 Jam KEMENLHK)...")
    
    with app.app_context():
        daftar_wilayah = WilayahDetails.query.all()
        
        for wilayah in daftar_wilayah:
            print(f" ⏳ Memproses riwayat kota: {wilayah.nama_wilayah}...")
            
            # 1. Ambil seluruh data mentah yang baru saja di-download, urut dari terlama ke terbaru
            riwayat_mentah = DataHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah)\
                                               .order_by(DataHistoris.waktu_aktual.asc()).all()
            
            if len(riwayat_mentah) < 18:
                print(f"   [!] Data historis kurang dari 18 jam, lewati.")
                continue

            ispu_massal = []
            
            # Tarik tanggal yang sudah ada di IspuHistoris untuk menghindari duplikat
            existing_ispu_records = IspuHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah)\
                                                      .with_entities(IspuHistoris.waktu_kalkulasi).all()
            existing_ispu_dates = {record[0] for record in existing_ispu_records}

            # 2. Lakukan Sliding Window (Jendela Geser) maju dari jam ke-1 hingga terakhir
            for i in range(len(riwayat_mentah)):
                data_terakhir = riwayat_mentah[i]
                
                # Cek duplikasi menggunakan Set agar proses backfill berjalan kilat
                if data_terakhir.waktu_aktual in existing_ispu_dates:
                    continue

                # Mundur 24 jam ke belakang dari titik 'i'
                start_idx = max(0, i - 23)
                jendela_24j = riwayat_mentah[start_idx : i+1]
                
                # Kita butuh minimal 18 data agar valid (hukum 75%)
                if len(jendela_24j) < 18:
                    continue 

                # 3. Bungkus 24 data ke dalam keranjang List
                dict_raw = {
                    'PM25': [r.pm25 for r in jendela_24j],
                    'PM10': [r.pm10 for r in jendela_24j],
                    'SO2':  [r.so2 for r in jendela_24j],
                    'CO':   [r.co for r in jendela_24j],
                    'NO2':  [r.no2 for r in jendela_24j],
                    'O3':   [r.ozon for r in jendela_24j]
                }
                
                # 4. Lempar ke kalkulator Dosen Utama
                hasil_ispu = kalkulasi_ispu_final(dict_raw)
                
                if hasil_ispu['skor_ispu_final'] > 0:
                    catatan = IspuHistoris(
                        id_wilayah=wilayah.id_wilayah,
                        id_data=data_terakhir.id_data,
                        waktu_kalkulasi=data_terakhir.waktu_aktual,
                        nilai_ispu=hasil_ispu['skor_ispu_final'],
                        kategori_ispu=hasil_ispu['kategori_ispu'],
                        parameter_kritis=hasil_ispu['polutan_kritis']
                    )
                    ispu_massal.append(catatan)
            
            # 5. Simpan massal ke Supabase
            try:
                if ispu_massal:
                    db.session.bulk_save_objects(ispu_massal)
                    db.session.commit()
                    print(f"   [+] Berhasil mencetak {len(ispu_massal)} riwayat ISPU ke database.")
                else:
                    print(f"   [-] Tidak ada data baru untuk ditambahkan.")
            except Exception as e:
                db.session.rollback()
                print(f"   [!] Gagal menyimpan data: {e}")

if __name__ == "__main__":
    fetch_and_save_raw_data()
    backfill_ispu_historis_30_hari()