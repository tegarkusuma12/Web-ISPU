import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
from ispu_logic import kalkulasi_ispu_final

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, '.env')

# Memuat variabel dari file .env untuk keamanan API Key dan kredensial DB
load_dotenv(ENV_PATH) 

app = Flask(__name__)
CORS(app) # Mengizinkan akses dari antarmuka frontend HTML

# Konfigurasi Database PostgreSQL (Siap untuk integrasi Supabase via ENV, fallback ke Docker lokal)
db_url = os.getenv('DATABASE_URL_POOLER')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ==========================================
# SKEMA DATABASE (Tabel)
# ==========================================

class WilayahDetails(db.Model):
    __tablename__ = 'wilayah_details'
    id_wilayah = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nama_wilayah = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    
    data_historis = db.relationship('DataHistoris', backref='wilayah', lazy=True)
    prediksi = db.relationship('Predictions', backref='wilayah', lazy=True)

class ModelRegistry(db.Model):
    __tablename__ = 'model_registry'
    id_model = db.Column(db.Integer, primary_key=True, autoincrement=True)
    algoritma = db.Column(db.String(50), nullable=False)
    versi_model = db.Column(db.String(20), nullable=False)
    hyperparameter = db.Column(db.JSON)
    training_date = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=False)
    
    prediksi = db.relationship('Predictions', backref='model', lazy=True)

class DataHistoris(db.Model):
    __tablename__ = 'data_historis'
    id_data = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_wilayah = db.Column(db.Integer, db.ForeignKey('wilayah_details.id_wilayah'), nullable=False)
    waktu_aktual = db.Column(db.DateTime, nullable=False)
    pm25 = db.Column(db.Float)
    pm10 = db.Column(db.Float)
    so2 = db.Column(db.Float)
    co = db.Column(db.Float)
    no2 = db.Column(db.Float)
    ozon = db.Column(db.Float)
    skor_ispu = db.Column(db.Integer)
    kategori_ispu = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Predictions(db.Model):
    __tablename__ = 'predictions'
    id_prediksi = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_model = db.Column(db.Integer, db.ForeignKey('model_registry.id_model'), nullable=False)
    id_wilayah = db.Column(db.Integer, db.ForeignKey('wilayah_details.id_wilayah'), nullable=False)
    waktu_dibuat = db.Column(db.DateTime, default=datetime.utcnow)
    target_waktu = db.Column(db.DateTime, nullable=False)
    pred_pm25 = db.Column(db.Float)
    pred_pm10 = db.Column(db.Float)
    pred_so2 = db.Column(db.Float)
    pred_co = db.Column(db.Float)
    pred_no2 = db.Column(db.Float)
    pred_ozon = db.Column(db.Float)
    pred_skor_ispu = db.Column(db.Integer)
    pred_kategori_ispu = db.Column(db.String(50))
    status = db.Column(db.String(50), default='PENDING')
    
    validasi = db.relationship('ValidationsLogs', backref='prediksi_sumber', uselist=False)

class ValidationsLogs(db.Model):
    __tablename__ = 'validations_logs'
    id_validasi = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_prediksi = db.Column(db.Integer, db.ForeignKey('predictions.id_prediksi'), unique=True, nullable=False)
    id_data = db.Column(db.Integer, db.ForeignKey('data_historis.id_data'), nullable=False)
    err_pm25 = db.Column(db.Float)
    err_pm10 = db.Column(db.Float)
    err_so2 = db.Column(db.Float)
    err_co = db.Column(db.Float)
    err_no2 = db.Column(db.Float)
    err_ozon = db.Column(db.Float)
    validated_at = db.Column(db.DateTime, default=datetime.utcnow)

# ==========================================
# ENDPOINT API (Untuk Frontend)
# ==========================================
from flask import jsonify, request
from datetime import datetime, timedelta
# Pastikan db, Predictions, DataHistoris, dan WilayahDetails sudah di-import di atas file app.py
from ispu_logic import kalkulasi_ispu_final

@app.route('/api/status', methods=['GET'])
def cek_status():
    return jsonify({"pesan": "Server Backend ISPU Jatim Aktif!"}), 200

@app.route('/api/ispu/all_besok', methods=['GET'])
def get_all_ispu_besok():
    """
    Endpoint Sapu Jagat: 
    Menarik prediksi hari esok untuk seluruh wilayah menggunakan metode JOIN.
    """
    besok = datetime.now().date() + timedelta(days=1)
    besok_dt = datetime.combine(besok, datetime.min.time()) # Ubah ke datetime agar cocok dengan database
    
    # Tarik data prediksi gabung dengan data wilayah (JOIN)
    data_prediksi = db.session.query(Predictions, WilayahDetails)\
                      .join(WilayahDetails, Predictions.id_wilayah == WilayahDetails.id_wilayah)\
                      .filter(Predictions.target_waktu == besok_dt).all()
    
    hasil = []
    for prediksi, wilayah in data_prediksi:
        # Hitung parameter kritis on-the-fly (karena tidak disimpan di DB baru)
        dict_polutan = {
            'PM25': prediksi.pred_pm25, 'PM10': prediksi.pred_pm10, 
            'CO': prediksi.pred_co, 'NO2': prediksi.pred_no2, 
            'O3': prediksi.pred_ozon, 'SO2': prediksi.pred_so2
        }
        ispu_calc = kalkulasi_ispu_final(dict_polutan)
        
        hasil.append({
            "kota": wilayah.nama_wilayah, # Diambil dari tabel WilayahDetails
            "nilai_ispu": prediksi.pred_skor_ispu,
            "kategori": prediksi.pred_kategori_ispu,
            "parameter_kritis": ispu_calc['parameter_kritis'],
            "pm25": prediksi.pred_pm25, "pm10": prediksi.pred_pm10, 
            "co": prediksi.pred_co, "no2": prediksi.pred_no2, 
            "o3": prediksi.pred_ozon, "so2": prediksi.pred_so2
        })
        
    return jsonify({
        "tanggal_prediksi": str(besok),
        "total_kota": len(hasil),
        "data": hasil
    }), 200

@app.route('/api/ispu/<nama_kota>')
def get_ispu_kota(nama_kota):
    # 1. Tangkap parameter filter ('24jam', '7', atau '30')
    filter_tipe = request.args.get('days', '7') 
    
    # 2. Cari ID Wilayah berdasarkan nama kota
    wilayah = WilayahDetails.query.filter_by(nama_wilayah=nama_kota).first()
    if not wilayah:
        return jsonify({"error": "Kota tidak terdaftar di database kami."}), 404

    # ==============================================================
    # KARTU BIRU: SELALU AMBIL PREDIKSI AI BESOK DARI DATABASE
    # ==============================================================
    besok = datetime.now().date() + timedelta(days=1)
    besok_dt = datetime.combine(besok, datetime.min.time())
    
    db_prediksi = Predictions.query.filter_by(
        id_wilayah=wilayah.id_wilayah, 
        target_waktu=besok_dt
    ).first()
    
    data_prediksi = {}
    if db_prediksi:
        dict_polutan = {
            'PM25': db_prediksi.pred_pm25, 'PM10': db_prediksi.pred_pm10, 
            'CO': db_prediksi.pred_co, 'NO2': db_prediksi.pred_no2, 
            'O3': db_prediksi.pred_ozon, 'SO2': db_prediksi.pred_so2
        }
        ispu_calc = kalkulasi_ispu_final(dict_polutan)
        
        data_prediksi = {
            "nilai_ispu": db_prediksi.pred_skor_ispu,
            "kategori": db_prediksi.pred_kategori_ispu,
            "parameter_kritis": ispu_calc['parameter_kritis']
        }

    # ==============================================================
    # KANVAS GRAFIK: AMBIL DARI TABEL DATA_HISTORIS
    # ==============================================================
    hasil_grafik = []
    waktu_sekarang = datetime.now()

    if filter_tipe == '24jam':
        # Tarik data 24 jam terakhir (Realita) dari Database
        batas_waktu = waktu_sekarang - timedelta(hours=24)
        
        data_historis = DataHistoris.query.filter(
            DataHistoris.id_wilayah == wilayah.id_wilayah,
            DataHistoris.waktu_aktual >= batas_waktu,
            DataHistoris.waktu_aktual <= waktu_sekarang
        ).order_by(DataHistoris.waktu_aktual.asc()).all()
        
        for row in data_historis:
            hasil_grafik.append({
                "tanggal": row.waktu_aktual.strftime("%H:00"), 
                "nilai_ispu": row.skor_ispu
            })
                
    else:
        # Tarik data harian (7 atau 30 hari) dari Database
        days_filter = int(filter_tipe)
        batas_waktu = waktu_sekarang.date() - timedelta(days=days_filter)
        batas_waktu_dt = datetime.combine(batas_waktu, datetime.min.time())
        
        data_historis = DataHistoris.query.filter(
            DataHistoris.id_wilayah == wilayah.id_wilayah,
            DataHistoris.waktu_aktual >= batas_waktu_dt,
            DataHistoris.waktu_aktual < datetime.combine(waktu_sekarang.date(), datetime.min.time()) # Hanya sampai kemarin
        ).order_by(DataHistoris.waktu_aktual.asc()).all()
        
        # Kelompokkan data jam-jaman menjadi rata-rata harian
        harian_dict = {}
        for row in data_historis:
            tgl_str = row.waktu_aktual.strftime("%d %b")
            if tgl_str not in harian_dict:
                harian_dict[tgl_str] = []
            harian_dict[tgl_str].append(row.skor_ispu)
            
        for tgl_str, list_ispu in harian_dict.items():
            avg_ispu = sum(list_ispu) / len(list_ispu)
            hasil_grafik.append({
                "tanggal": tgl_str, 
                "nilai_ispu": round(avg_ispu)
            })

    # ==============================================================
    # KEMBALIKAN DATA KE FRONTEND
    # ==============================================================
    return jsonify({
        "kota": nama_kota,
        "prediksi_besok": data_prediksi,
        "grafik": hasil_grafik
    }), 200

if __name__ == '__main__':
    # 1. Bagian untuk mencetak struktur ERD ke Supabase
    with app.app_context():
        #db.create_all()
        print("✅ Semua tabel proyek prediksi ISPU berhasil dicetak di Supabase!")
    
    # 2. Tetap gunakan settingan host dan port asli milikmu
    app.run(debug=True, host='0.0.0.0', port=5000)