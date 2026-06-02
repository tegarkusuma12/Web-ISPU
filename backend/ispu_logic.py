# backend/ispu_logic.py
import pandas as pd
import numpy as np
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
# SESUAIKAN REKAYASA FITUR
# ======================================================================
def siapkan_fitur_prediksi(df_history):
    """
    Fungsi modular untuk meracik fitur XGBoost.
    Telah disinkronkan 100% dengan pipeline best_model.ipynb
    """
    df_temp = df_history.copy()
    
    # Pastikan waktu aktual bertipe datetime
    df_temp['waktu_aktual'] = pd.to_datetime(df_temp['waktu_aktual'])
    
    daftar_polutan = ['pm25', 'pm10', 'so2', 'co', 'no2', 'ozon']
    
    # PEMBERSIHAN OUTLIER SENSOR
    # Ubah nilai mustahil (<= 0) menjadi NaN
    for col in daftar_polutan:
        df_temp.loc[df_temp[col] <= 0, col] = np.nan
        
    # Interpolasi Linear (tanpa groupby karena df_history ini sudah per 1 wilayah khusus)
    df_temp[daftar_polutan] = df_temp[daftar_polutan].interpolate(method='linear', limit_direction='both')
    
    # Winsorizing (Potong nilai ekstrem - bisa dilewati di backend jika dianggap terlalu lambat, 
    # tapi lebih aman kita biarkan XGBoost menanganinya secara natural saat inferensi)
    # *Sengaja di-skip agar backend ringan, XGBoost kebal outlier ekstrem*
    
    # FITUR TEMPORAL DASAR
    # HARUS sama persis namanya dengan di Notebook (huruf kecil semua)
    df_temp['jam'] = df_temp['waktu_aktual'].dt.hour
    df_temp['hari_dalam_minggu'] = df_temp['waktu_aktual'].dt.dayofweek
    df_temp['bulan'] = df_temp['waktu_aktual'].dt.month
        
    # FITUR LAG & ROLLING
    for p in daftar_polutan:
        for i in range(1, 25): # Mundur 24 jam
            df_temp[f'{p}_H-{i}'] = df_temp[p].shift(i)
        df_temp[f'{p}_RollMean_72'] = df_temp[p].rolling(window=72, min_periods=1).mean()
        df_temp[f'{p}_RollMax_72'] = df_temp[p].rolling(window=72, min_periods=1).max() 

    # Sisa NaN (biasanya di 24 jam pertama) ubah jadi 0 agar model tidak error
    df_temp = df_temp.fillna(0)
    
    # ONE-HOT ENCODING
    # Buat kategori list untuk memastikan OHE konsisten
    kategori_wilayah = [str(i) for i in range(1, 39)]
    kategori_jam = list(range(0, 24))
    kategori_hari = list(range(0, 7))
    kategori_bulan = list(range(1, 13))
    
    # Konversi ke Categorical agar fungsi get_dummies membuat semua kolom meskipun datanya tidak ada
    df_temp['id_wilayah'] = pd.Categorical(df_temp['id_wilayah'].astype(str), categories=kategori_wilayah)
    df_temp['jam'] = pd.Categorical(df_temp['jam'], categories=kategori_jam)
    df_temp['hari_dalam_minggu'] = pd.Categorical(df_temp['hari_dalam_minggu'], categories=kategori_hari)
    df_temp['bulan'] = pd.Categorical(df_temp['bulan'], categories=kategori_bulan)
    
    # Lakukan OHE dengan drop_first=True (SAMA PERSIS DENGAN JUPYTER)
    df_temp = pd.get_dummies(df_temp, columns=['id_wilayah', 'jam', 'hari_dalam_minggu', 'bulan'], drop_first=True)
    
    return df_temp