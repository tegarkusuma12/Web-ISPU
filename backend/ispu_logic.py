# backend/ispu_logic.py
import pandas as pd

# Tabel Referensi Batas ISPU (Berdasarkan Gambar User)
# Format: [Batas_Bawah, Batas_Atas]
ISPU_RANGES = [
    [0, 50],      # Baik
    [51, 100],    # Sedang
    [101, 200],   # Tidak Sehat
    [201, 300],   # Sangat Tidak Sehat
    [301, 500]    # Berbahaya (Kita asumsikan max 500 untuk perhitungan atas)
]

# Tabel Batas Polutan 
# (Ditambahkan SO2 agar genap 6 polutan sesuai model AI)
POLUTAN_LIMITS = {
    'PM10': [[0, 50], [51, 150], [151, 350], [351, 420], [421, 500]],
    'PM25': [[0, 15.5], [15.6, 55.4], [55.5, 150.4], [150.5, 250.4], [250.5, 500]],
    'CO':   [[0, 4000], [4001, 8000], [8001, 15000], [15001, 30000], [30001, 45000]],
    'O3':   [[0, 120], [121, 235], [236, 400], [401, 800], [801, 1000]],
    'NO2':  [[0, 80], [81, 200], [201, 1130], [1131, 2260], [2261, 3000]],
    'SO2':  [[0, 52], [53, 180], [181, 400], [401, 800], [801, 1200]] # Asumsi batas standar, mohon dicek kembali dengan dosen/panduan
}

def hitung_ispu_per_polutan(nama_polutan, konsentrasi):
    """Fungsi Interpolasi Matematika ISPU"""
    if konsentrasi < 0:
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
    Fungsi ini akan dipanggil oleh Flask nanti.
    hasil_prediksi_dict contoh: {'PM25': 16.2, 'PM10': 40.5, 'CO': 4100, ...}
    """
    ispu_tertinggi = 0
    polutan_kritis = ""
    
    for polutan, konsentrasi in hasil_prediksi_dict.items():
        # Pastikan format teks cocok dengan keys di POLUTAN_LIMITS
        kunci_polutan = polutan.split(' ')[0].replace('.', '') if ' ' in polutan else polutan
        
        ispu_item = hitung_ispu_per_polutan(kunci_polutan, konsentrasi)
        if ispu_item > ispu_tertinggi:
            ispu_tertinggi = ispu_item
            polutan_kritis = kunci_polutan
            
    status = tentukan_status_ispu(ispu_tertinggi)
    
    return {
        "nilai_ispu": ispu_tertinggi,
        "parameter_kritis": polutan_kritis,
        "kategori": status
    }

# ======================================================================
# BAGIAN BARU: REKAYASA FITUR (PENYAMBUNG LIDAH AI)
# ======================================================================

def siapkan_fitur_prediksi(df_history_4_hari, daftar_polutan, kolom_training_asli):
    """
    Fungsi untuk meracik raw data dari Supabase menjadi format yang persis
    sama dengan yang dipelajari XGBoost saat training.
    """
    df_temp = df_history_4_hari.copy()
    
    # 1. Sesuaikan dengan kolom ERD Baru (waktu_aktual)
    df_temp['waktu_aktual'] = pd.to_datetime(df_temp['waktu_aktual'])
    df_temp = df_temp.sort_values(by='waktu_aktual').reset_index(drop=True)
    
    # 2. Fitur Temporal
    df_temp['Bulan'] = df_temp['waktu_aktual'].dt.month
    df_temp['Is_Weekend'] = df_temp['waktu_aktual'].dt.dayofweek.isin([5, 6]).astype(int)
    
    # 3. Fitur History & Rolling (Mundur 3 Hari)
    for p in daftar_polutan:
        for i in range(1, 4):
            df_temp[f'{p}_H-{i}'] = df_temp[p].shift(i)
            
        df_temp[f'{p}_RollMean_3'] = df_temp[p].shift(1).rolling(window=3).mean()
        df_temp[f'{p}_RollMax_3'] = df_temp[p].shift(1).rolling(window=3).max()
        
    # 4. One-Hot Encoding (Sesuaikan dengan ERD Baru: nama_wilayah)
    df_temp = pd.get_dummies(df_temp, columns=['nama_wilayah'])
    
    # pd.get_dummies akan menghasilkan nama kolom seperti 'nama_wilayah_Kota Surabaya'.
    # Kita harus mengubah teks 'nama_wilayah_' menjadi 'Kota_' agar model AI mengenalinya
    df_temp.columns = [col.replace('nama_wilayah_', 'Kota_') for col in df_temp.columns]
    
    # 5. Ambil BARIS TERAKHIR SAJA (Hari Ini)
    X_prediksi_besok = df_temp.iloc[[-1]].copy()
    
    # 6. PENYELAMAT DIMENSI: Menambahkan kolom kota lain yang kosong
    for col in kolom_training_asli:
        if col not in X_prediksi_besok.columns:
            X_prediksi_besok[col] = 0
            
    # Hapus kolom yang tidak berguna dan urutkan sesuai saat training
    X_prediksi_besok = X_prediksi_besok[kolom_training_asli]
    
    return X_prediksi_besok