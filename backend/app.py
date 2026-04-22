# backend/app.py
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import joblib
import requests
from ispu_logic import kalkulasi_ispu_final

app = Flask(__name__)
CORS(app) # Mengizinkan akses dari antarmuka frontend HTML

# Konfigurasi Database PostgreSQL (Menembak ke Docker di port 5432)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://ispu_admin:rahasia_ispu@localhost:5433/ispu_jatim_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# SKEMA DATABASE (Tabel)
# ==========================================
class RiwayatCuaca(db.Model):
    """Menyimpan data mentah tarikan API setiap jam"""
    __tablename__ = 'riwayat_cuaca'
    id = db.Column(db.Integer, primary_key=True)
    waktu = db.Column(db.DateTime, default=datetime.utcnow)
    kota = db.Column(db.String(50))
    pm25 = db.Column(db.Float)
    pm10 = db.Column(db.Float)
    co = db.Column(db.Float)
    no2 = db.Column(db.Float)
    o3 = db.Column(db.Float)

class HasilPrediksi(db.Model):
    """Menyimpan hasil prediksi harian yang sudah matang + Status ISPU"""
    __tablename__ = 'hasil_prediksi'
    id = db.Column(db.Integer, primary_key=True)
    tanggal_prediksi = db.Column(db.Date) # Untuk hari apa prediksi ini berlaku
    kota = db.Column(db.String(50))
    pm25 = db.Column(db.Float)
    pm10 = db.Column(db.Float)
    co = db.Column(db.Float)
    no2 = db.Column(db.Float)
    o3 = db.Column(db.Float)
    nilai_ispu = db.Column(db.Integer)
    kategori = db.Column(db.String(50))
    parameter_kritis = db.Column(db.String(50))

# Buat tabel jika belum ada
with app.app_context():
    db.create_all()

# ==========================================
# ENDPOINT API (Untuk Frontend)
# ==========================================
@app.route('/api/status', methods=['GET'])
def cek_status():
    return jsonify({"pesan": "Server Backend ISPU Jatim Aktif!"}), 200

@app.route('/api/ispu/<nama_kota>')
def get_ispu_kota(nama_kota):
    from scheduler import DAFTAR_KOTA
    # 1. Tangkap parameter filter ('24jam', '7', atau '30')
    filter_tipe = request.args.get('days', '7') 
    
    # ==============================================================
    # KARTU BIRU: SELALU AMBIL PREDIKSI AI BESOK DARI DATABASE
    # ==============================================================
    besok = datetime.now().date() + timedelta(days=1)
    db_prediksi = HasilPrediksi.query.filter_by(kota=nama_kota, tanggal_prediksi=besok).first()
    
    data_prediksi = {}
    if db_prediksi:
        data_prediksi = {
            "nilai_ispu": db_prediksi.nilai_ispu,
            "kategori": db_prediksi.kategori,
            "parameter_kritis": db_prediksi.parameter_kritis
        }

    # ==============================================================
    # KANVAS GRAFIK: TENTUKAN SUMBER DATA BERDASARKAN FILTER
    # ==============================================================
    hasil_grafik = []

    if filter_tipe == '24jam':
        # --- JALUR BYPASS (LIVE SATELIT) ---
        # PENTING: Ganti tulisan di bawah dengan API Key OpenWeatherMap milikmu!
        API_KEY = "a5053916414d07c5d4b4f88de911e561" 
        kordinat = DAFTAR_KOTA.get(nama_kota)
        
        if kordinat:
            waktu_sekarang = int(datetime.now().timestamp())
            waktu_awal = int((datetime.now() - timedelta(hours=24)).timestamp())
            
            url = f"http://api.openweathermap.org/data/2.5/air_pollution/history?lat={kordinat['lat']}&lon={kordinat['lon']}&start={waktu_awal}&end={waktu_sekarang}&appid={API_KEY}"
            
            try:
                respon = requests.get(url).json()
                for item in respon.get('list', []):
                    # Format menjadi jam, contoh: "14:00"
                    jam = datetime.fromtimestamp(item['dt']).strftime("%H:00")
                    c = item['components']
                    
                    # Hitung ulang ISPU dari data mentah
                    dict_polutan = {'PM25': c['pm2_5'], 'PM10': c['pm10'], 'CO': c['co'], 'NO2': c['no2'], 'O3': c['o3']}
                    ispu = kalkulasi_ispu_final(dict_polutan)
                    
                    hasil_grafik.append({
                        "tanggal": jam, 
                        "nilai_ispu": ispu['nilai_ispu']
                    })
            except Exception as e:
                print(f"Error tarik data 24 jam: {e}")
                
    else:
        # --- JALUR NORMAL (DATABASE POSTGRESQL) ---
        days_filter = int(filter_tipe)
        batas_waktu = datetime.now().date() - timedelta(days=days_filter)
        hari_ini = datetime.now().date()
        
        data = HasilPrediksi.query.filter(
            HasilPrediksi.kota == nama_kota,
            HasilPrediksi.tanggal_prediksi >= batas_waktu,
            HasilPrediksi.tanggal_prediksi <= hari_ini # Jangan sertakan tebakan besok ke dalam grafik sejarah
        ).order_by(HasilPrediksi.tanggal_prediksi.asc()).all()
        
        for row in data:
            hasil_grafik.append({
                # Format menjadi tanggal singkat, contoh: "21 Apr"
                "tanggal": row.tanggal_prediksi.strftime("%d %b"), 
                "nilai_ispu": row.nilai_ispu
            })

    # ==============================================================
    # KEMBALIKAN DATA KE FRONTEND DENGAN FORMAT BARU
    # ==============================================================
    return jsonify({
        "kota": nama_kota,
        "prediksi_besok": data_prediksi,
        "grafik": hasil_grafik
    }), 200

if __name__ == '__main__':
    # Flask berjalan di port 5000
    app.run(debug=True, host='0.0.0.0', port=5000)