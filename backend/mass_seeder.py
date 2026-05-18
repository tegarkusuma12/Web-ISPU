import os
import time
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

def mass_insert_data(csv_path):
    # 1. Ambil URL Koneksi Direct dari .env
    load_dotenv('../.env', override=True) 
    db_url = os.getenv("DATABASE_URL_DIRECT")

    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    if not db_url:
        raise ValueError("🚨 DATABASE_URL_DIRECT tidak ditemukan di file .env!")

    engine = create_engine(db_url)

    # 2. Baca Dataset Masif dari CSV lokal
    print(f"📖 Membaca file CSV: {csv_path} ...")
    start_time = time.time()
    df = pd.read_csv(csv_path)
    
    # ------------------ BAGIAN PENERJEMAH (MAPPING) ------------------
    print("🔍 Mengambil kamus id_wilayah dari tabel wilayah_details di Supabase...")
    
    # Menarik data dari tabel wilayah_details untuk mencocokkan ID
    df_wilayah = pd.read_sql("SELECT id_wilayah, nama_wilayah FROM wilayah_details", engine)
    
    # Membuat kamus (dictionary) { 'Kota Surabaya': 1, 'Kabupaten Malang': 2, dst }
    kamus_wilayah = dict(zip(df_wilayah['nama_wilayah'], df_wilayah['id_wilayah']))
    
    # Membuat kolom baru 'id_wilayah' berdasarkan terjemahan kolom 'Kota'
    df['id_wilayah'] = df['Kota'].map(kamus_wilayah)
    
    # CEK KEAMANAN: Apakah ada kota di CSV yang namanya tidak sama persis dengan di Supabase?
    kota_tak_dikenal = df[df['id_wilayah'].isna()]['Kota'].unique()
    if len(kota_tak_dikenal) > 0:
        print(f"⚠️ PERINGATAN! Ada kota di CSV yang tidak ditemukan di database: {kota_tak_dikenal}")
        print("Pastikan penulisan namanya sama persis (misal: 'Kota Surabaya' bukan 'Surabaya').")
        print("Menghapus baris yang kotanya tidak dikenali agar tidak error...")
        df = df.dropna(subset=['id_wilayah'])
    
    # ------------------ BAGIAN RENAME KOLOM ------------------
    # Mengubah nama kolom CSV agar sama persis dengan kolom Supabase
    df = df.rename(columns={
        'Waktu': 'waktu_aktual',
        'PM2.5 (µg/m³)': 'pm25',
        'PM10 (µg/m³)': 'pm10',
        'SO2 (µg/m³)': 'so2',
        'CO (µg/m³)': 'co',
        'NO2 (µg/m³)': 'no2',
        'Ozon (µg/m³)': 'ozon'
    })
    
    # Membuang kolom 'Kota' karena kita sudah punya 'id_wilayah'
    df = df.drop(columns=['Kota'])
    
    # Pastikan tipe id_wilayah adalah integer (bukan float)
    df['id_wilayah'] = df['id_wilayah'].astype(int)
    # -----------------------------------------------------------------
    
    print(f"📊 Total amunisi data yang siap disetor: {len(df)} baris.")

    # Nama tabel staging sementara
    staging_table = "temp_staging_historis"

    try:
        # Menggunakan konteks transaksi engine.begin() agar jika gagal, otomatis rollback (aman)
        with engine.begin() as conn:
            print("\n🚀 Langkah 1: Mengunggah data ke tabel staging sementara...")
            # Mengunggah data masif ke tabel sementara (Sangat cepat dibanding insert satu per satu)
            df.to_sql(staging_table, conn, if_exists="replace", index=False)
            
            print("🔄 Langkah 2: Memulai proses sinkronisasi (Bulk Upsert) ke tabel utama...")
            # Kueri SQL tingkat lanjut untuk memindahkan data dari tabel sementara ke tabel utama.
            # CATATAN: Kolom skor_ispu dan kategori_ispu sudah dihapus dari kueri ini.
            query_upsert = """
                INSERT INTO public.data_historis (
                    waktu_aktual, id_wilayah, pm25, pm10, so2, co, no2, ozon
                )
                SELECT 
                    CAST(waktu_aktual AS TIMESTAMP WITH TIME ZONE), 
                    id_wilayah, pm25, pm10, so2, co, no2, ozon
                FROM temp_staging_historis
                ON CONFLICT (id_wilayah, waktu_aktual) 
                DO UPDATE SET 
                    pm25 = EXCLUDED.pm25,
                    pm10 = EXCLUDED.pm10,
                    so2 = EXCLUDED.so2,
                    co = EXCLUDED.co,
                    no2 = EXCLUDED.no2,
                    ozon = EXCLUDED.ozon;
            """
            conn.execute(text(query_upsert))
            print("✅ Langkah 3: Sinkronisasi selesai! Data berhasil masuk tanpa duplikat.")

    except Exception as e:
        print(f"❌ Proses gagal! Terjadi kesalahan: {e}")

    finally:
        # Menghapus tabel staging sementara agar database Supabase kembali bersih
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {staging_table};"))
            print("🧹 Tabel staging sementara berhasil dibersihkan dari Supabase.")
            
    end_time = time.time()
    print(f"\n⏱️  Selesai dalam {end_time - start_time:.2f} detik! Database-mu sekarang sudah gendut.")

if __name__ == "__main__":
    # GANTI dengan nama file CSV masif milikmu yang berada di folder lokal
    NAMA_FILE_CSV = "dataset_polutan_jatim.csv" 
    
    if os.path.exists(NAMA_FILE_CSV):
        mass_insert_data(NAMA_FILE_CSV)
    else:
        print(f"⚠️ File '{NAMA_FILE_CSV}' tidak ditemukan. Taruh file CSV di folder yang sama dengan script ini!")