# backend/ispu_logic.py
import pandas as pd
import warnings

# Mengabaikan warning performa (fragmented dataframe) jika masih muncul
warnings.simplefilter(action='ignore', category=pd.errors.PerformanceWarning)

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
    'PM10': [[0, 50], [50, 150], [150, 350], [350, 420], [420, 500]],
    'PM25': [[0, 15.5], [15.5, 55.4], [55.4, 150.4], [150.4, 250.4], [250.4, 500]],
    'CO':   [[0, 4000], [4000, 8000], [8000, 15000], [15000, 30000], [30000, 45000]],
    'O3':   [[0, 120], [120, 235], [235, 400], [400, 800], [800, 1000]],
    'NO2':  [[0, 80], [80, 200], [200, 1130], [1130, 2260], [2260, 3000]],
    'SO2':  [[0, 52], [52, 180], [180, 400], [400, 800], [800, 1200]] 
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
        
        # PERBAIKAN: Gunakan <= untuk indeks pertama (i==0) untuk mencakup angka 0
        # Gunakan batas_bawah_c < konsentrasi untuk menghindari tumpang tindih (overlap)
        if (i == 0 and batas_bawah_c <= konsentrasi <= batas_atas_c) or (i > 0 and batas_bawah_c < konsentrasi <= batas_atas_c):
            batas_bawah_i = ISPU_RANGES[i][0]
            batas_atas_i = ISPU_RANGES[i][1]
            
            ispu = ((batas_atas_i - batas_bawah_i) / (batas_atas_c - batas_bawah_c)) * (konsentrasi - batas_bawah_c) + batas_bawah_i
            return round(ispu)
            
    # Jika melebihi batas indeks berbahaya
    return 500

def tentukan_status_ispu(nilai_ispu):
    if nilai_ispu == 0:
        return "Menunggu Data"
    elif nilai_ispu <= 50:
        return "Baik"
    elif nilai_ispu <= 100:
        return "Sedang"
    elif nilai_ispu <= 200:
        return "Tidak Sehat"
    elif nilai_ispu <= 300:
        return "Sangat Tidak Sehat"
    else:
        return "Berbahaya"

def kalkulasi_ispu_final(hasil_prediksi_dict_list):
    """
    Input : Dictionary of Lists berisi 24 jam data mundur.
            {'PM25': [45.2, 42.1, ...], 'CO': [1200, 1150, ...], ...}
    Output: Dictionary lengkap berisi skor final rata-rata 24 jam (Aturan KEMENLHK).
    """
    skor_individu: dict = {
        'skor_pm25': None,
        'skor_pm10': None,
        'skor_so2': None,
        'skor_co': None,
        'skor_o3': None,
        'skor_no2': None
    }
    
    ispu_tertinggi = 0
    polutan_kritis = "-"
    
    # Eksekusi List Comprehension & Aturan 75%
    for polutan, list_konsentrasi in hasil_prediksi_dict_list.items():
        kunci_polutan = polutan.split(' ')[0].replace('.', '').upper()
        
        if not isinstance(list_konsentrasi, list):
            list_konsentrasi = [list_konsentrasi]
            
        data_valid = [x for x in list_konsentrasi if x is not None and x >= 0]
        
        # Validasi Legalitas Data (Minimal 18 jam valid)
        if len(data_valid) < 18:
            ispu_item = 0 
        else:
            rata_rata_konsentrasi = sum(data_valid) / len(data_valid)
            ispu_item = hitung_ispu_per_polutan(kunci_polutan, rata_rata_konsentrasi)
        
        key_db = f"skor_{kunci_polutan.lower()}"
        if key_db in skor_individu:
            skor_individu[key_db] = ispu_item if ispu_item > 0 else None
            
        if ispu_item > ispu_tertinggi:
            ispu_tertinggi = ispu_item
            polutan_kritis = kunci_polutan
            
    if ispu_tertinggi > 0:
        status = tentukan_status_ispu(ispu_tertinggi)
    else:
        ispu_tertinggi = 0
        status = "Data Tidak Valid (<75%)"
    
    hasil_akhir = {
        "skor_ispu_final": ispu_tertinggi,
        "polutan_kritis": polutan_kritis,
        "kategori_ispu": status
    }
    hasil_akhir.update(skor_individu)
    
    return hasil_akhir


# ======================================================================
# BAGIAN BARU: REKAYASA FITUR (Versi Terbaru milikmu)
# ======================================================================

def siapkan_fitur_prediksi(df_history_jam, daftar_polutan, kolom_training_asli):
    """
    Fungsi untuk meracik raw data dari Supabase menjadi format yang persis
    sama dengan yang dipelajari AI saat training (Sekarang berbasis JAM).
    """
    df_temp = df_history_jam.copy()
    
    df_temp['waktu_aktual'] = pd.to_datetime(df_temp['waktu_aktual'])
    df_temp = df_temp.sort_values(by='waktu_aktual').reset_index(drop=True)
    
    df_temp['Bulan'] = df_temp['waktu_aktual'].dt.month
    df_temp['Jam'] = df_temp['waktu_aktual'].dt.hour
    df_temp['Is_Weekend'] = df_temp['waktu_aktual'].dt.dayofweek.isin([5, 6]).astype(int)
    
    n_lags = 24  

    for p in daftar_polutan:
        for i in range(1, n_lags + 1):
            df_temp[f'{p}_H-{i}'] = df_temp[p].shift(i)
            
        df_temp[f'{p}_RollMean_72'] = df_temp[p].rolling(window=72).mean()
        df_temp[f'{p}_RollMax_72'] = df_temp[p].rolling(window=72).max()
        
    if 'nama_wilayah' in df_temp.columns:
        df_temp = pd.get_dummies(df_temp, columns=['nama_wilayah'])
        df_temp.columns = [col.replace('nama_wilayah_', 'Kota_') for col in df_temp.columns]
    
    X_prediksi_besok = df_temp.iloc[[-1]].copy()
    
    missing_cols = [col for col in kolom_training_asli if col not in X_prediksi_besok.columns]
    
    if missing_cols:
        X_prediksi_besok[missing_cols] = 0
            
    X_prediksi_besok = X_prediksi_besok[kolom_training_asli]
    
    return X_prediksi_besok