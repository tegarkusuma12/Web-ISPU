# backend/ispu_logic.py
import pandas as pd

# Tabel Referensi Batas ISPU 
# Format: [Batas_Bawah, Batas_Atas]
ISPU_RANGES = [
    [0, 50],      # Baik
    [51, 100],    # Sedang
    [101, 200],   # Tidak Sehat
    [201, 300],   # Sangat Tidak Sehat
    [301, 500]    # Berbahaya 
]

# Tabel Batas Polutan 
POLUTAN_LIMITS = {
    'PM10': [[0, 50], [51, 150], [151, 350], [351, 420], [421, 500]],
    'PM25': [[0, 15.5], [15.6, 55.4], [55.5, 150.4], [150.5, 250.4], [250.5, 500]],
    'CO':   [[0, 4000], [4001, 8000], [8001, 15000], [15001, 30000], [30001, 45000]],
    'O3':   [[0, 120], [121, 235], [236, 400], [401, 800], [801, 1000]],
    'NO2':  [[0, 80], [81, 200], [201, 1130], [1131, 2260], [2261, 3000]],
    'SO2':  [[0, 52], [53, 180], [181, 400], [401, 800], [801, 1200]] 
}

def hitung_ispu_per_polutan(nama_polutan, konsentrasi):
    """Fungsi Interpolasi Matematika ISPU"""
    if konsentrasi is None or konsentrasi < 0:
        return 0
        
    limits = POLUTAN_LIMITS.get(nama_polutan)
    if not limits:
        return 0
        
    for i in range(len(limits)):
        batas_bawah_c = limits[i][0]
        batas_atas_c = limits[i][1]
        
        if batas_bawah_c <= konsentrasi <= batas_atas_c:
            batas_bawah_i = ISPU_RANGES[i][0]
            batas_atas_i = ISPU_RANGES[i][1]
            
            ispu = ((batas_atas_i - batas_bawah_i) / (batas_atas_c - batas_bawah_c)) * (konsentrasi - batas_bawah_c) + batas_bawah_i
            return round(ispu)
            
    return 500

def tentukan_status_ispu(nilai_ispu):
    if nilai_ispu <= 50:
        return "Baik"
    elif nilai_ispu <= 100:
        return "Sedang"
    elif nilai_ispu <= 200:
        return "Tidak Sehat"
    elif nilai_ispu <= 300:
        return "Sangat Tidak Sehat"
    else:
        return "Berbahaya"

def kalkulasi_ispu_final(hasil_prediksi_dict):
    """
    Input : {'PM25': 45.2, 'CO': 120.0, ...}
    Output: Dictionary lengkap berisi seluruh skor individu & final 
            untuk dimasukkan ke tabel interpolasi_ispu di Supabase.
    """
    # Siapkan template skor individu
    skor_individu: dict = {
        'skor_pm25': None,
        'skor_pm10': None,
        'skor_so2': None,
        'skor_co': None,
        'skor_o3': None,
        'skor_no2': None
    }
    
    ispu_tertinggi = 0
    polutan_kritis = ""
    
    for polutan, konsentrasi in hasil_prediksi_dict.items():
        kunci_polutan = polutan.split(' ')[0].replace('.', '').upper()
        
        # Hitung skor
        ispu_item = hitung_ispu_per_polutan(kunci_polutan, konsentrasi)
        
        # Masukkan ke dalam dictionary skor individu
        key_db = f"skor_{kunci_polutan.lower()}"
        if key_db in skor_individu:
            skor_individu[key_db] = ispu_item
            
        # Tentukan polutan kritis (pemenang)
        if ispu_item > ispu_tertinggi:
            ispu_tertinggi = ispu_item
            polutan_kritis = kunci_polutan
            
    status = tentukan_status_ispu(ispu_tertinggi)
    
    # Gabungkan hasil akhir dengan skor individu
    hasil_akhir = {
        "skor_ispu_final": ispu_tertinggi,
        "polutan_kritis": polutan_kritis,
        "kategori_ispu": status
    }
    hasil_akhir.update(skor_individu)
    
    return hasil_akhir


# ======================================================================
# BAGIAN BARU: REKAYASA FITUR 
# ======================================================================

def siapkan_fitur_prediksi(df_history_jam, daftar_polutan, kolom_training_asli):
    """
    Fungsi untuk meracik raw data dari Supabase menjadi format yang persis
    sama dengan yang dipelajari AI saat training (Sekarang berbasis JAM).
    """
    df_temp = df_history_jam.copy()
    
    # 1. Sesuaikan dengan kolom ERD Baru (waktu_aktual)
    df_temp['waktu_aktual'] = pd.to_datetime(df_temp['waktu_aktual'])
    df_temp = df_temp.sort_values(by='waktu_aktual').reset_index(drop=True)
    
    # 2. Fitur Temporal (Sekarang bisa menambahkan Jam)
    df_temp['Bulan'] = df_temp['waktu_aktual'].dt.month
    df_temp['Jam'] = df_temp['waktu_aktual'].dt.hour
    df_temp['Is_Weekend'] = df_temp['waktu_aktual'].dt.dayofweek.isin([5, 6]).astype(int)
    
    # 3. Fitur History & Rolling 
    # Karena data per jam, mundur 3 hari = 72 Jam.
    n_lags = 3  # Opsional: ubah ke 24 jika kamu melatih H-1 hingga H-24
    window_3_hari = 72 
    
    for p in daftar_polutan:
        for i in range(1, n_lags + 1):
            df_temp[f'{p}_H-{i}'] = df_temp[p].shift(i)
            
        # Rolling rata-rata dan max untuk 72 jam terakhir (3 Hari)
        df_temp[f'{p}_RollMean_3'] = df_temp[p].shift(1).rolling(window=window_3_hari).mean()
        df_temp[f'{p}_RollMax_3'] = df_temp[p].shift(1).rolling(window=window_3_hari).max()
        
    # 4. One-Hot Encoding 
    if 'nama_wilayah' in df_temp.columns:
        df_temp = pd.get_dummies(df_temp, columns=['nama_wilayah'])
        df_temp.columns = [col.replace('nama_wilayah_', 'Kota_') for col in df_temp.columns]
    
    # 5. Ambil BARIS TERAKHIR SAJA (Jam Ini / Prediksi untuk Jam Berikutnya)
    X_prediksi_besok = df_temp.iloc[[-1]].copy()
    
    # 6. PENYELAMAT DIMENSI: Menambahkan kolom kota lain yang kosong
    for col in kolom_training_asli:
        if col not in X_prediksi_besok.columns:
            X_prediksi_besok[col] = 0
            
    # Hapus kolom yang tidak berguna dan urutkan sesuai saat training
    X_prediksi_besok = X_prediksi_besok[kolom_training_asli]
    
    return X_prediksi_besok