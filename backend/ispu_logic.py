# backend/ispu_logic.py

# Tabel Referensi Batas ISPU (Berdasarkan Gambar User)
# Format: [Batas_Bawah, Batas_Atas]
ISPU_RANGES = [
    [0, 50],      # Baik
    [51, 100],    # Sedang
    [101, 200],   # Tidak Sehat
    [201, 300],   # Sangat Tidak Sehat
    [301, 500]    # Berbahaya (Kita asumsikan max 500 untuk perhitungan atas)
]

# Tabel Batas Polutan (Diambil murni dari tabel gambarmu)
POLUTAN_LIMITS = {
    'PM10': [[0, 50], [51, 150], [151, 350], [351, 420], [421, 500]],
    'PM25': [[0, 15.5], [15.6, 55.4], [55.5, 150.4], [150.5, 250.4], [250.5, 500]],
    'CO':   [[0, 4000], [4001, 8000], [8001, 15000], [15001, 30000], [30001, 45000]],
    'O3':   [[0, 120], [121, 235], [236, 400], [401, 800], [801, 1000]],
    'NO2':  [[0, 80], [81, 200], [201, 1130], [1131, 2260], [2261, 3000]]
}

def hitung_ispu_per_polutan(nama_polutan, konsentrasi):
    """Fungsi Interpolasi Matematika ISPU"""
    if konsentrasi < 0:
        return 0
        
    limits = POLUTAN_LIMITS.get(nama_polutan)
    if not limits:
        return 0
        
    # Mencari nilai konsentrasi masuk di rentang ke-berapa
    for i in range(len(limits)):
        batas_bawah_c = limits[i][0]
        batas_atas_c = limits[i][1]
        
        if batas_bawah_c <= konsentrasi <= batas_atas_c:
            batas_bawah_i = ISPU_RANGES[i][0]
            batas_atas_i = ISPU_RANGES[i][1]
            
            # Rumus Interpolasi Linier ISPU
            ispu = ((batas_atas_i - batas_bawah_i) / (batas_atas_c - batas_bawah_c)) * (konsentrasi - batas_bawah_c) + batas_bawah_i
            return round(ispu)
            
    # Jika melebihi batas maksimal di tabel (Kondisi Ekstrem)
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
    
    # Hitung ISPU untuk setiap polutan, lalu cari yang angkanya paling tinggi
    for polutan, konsentrasi in hasil_prediksi_dict.items():
        ispu_item = hitung_ispu_per_polutan(polutan, konsentrasi)
        if ispu_item > ispu_tertinggi:
            ispu_tertinggi = ispu_item
            polutan_kritis = polutan
            
    status = tentukan_status_ispu(ispu_tertinggi)
    
    return {
        "nilai_ispu": ispu_tertinggi,
        "parameter_kritis": polutan_kritis,
        "kategori": status
    }