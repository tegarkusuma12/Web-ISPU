import os
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
from ispu_logic import kalkulasi_ispu_final

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, '.env')

load_dotenv(ENV_PATH) 

app = Flask(__name__)
CORS(app) 

# Konfigurasi Zona Waktu
TZ_WIB = pytz.timezone('Asia/Jakarta')

# Konfigurasi Database
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

@app.route('/api/status', methods=['GET'])
def cek_status():
    return jsonify({"pesan": "Server Backend ISPU Jatim Aktif!"}), 200

@app.route('/api/ispu/all_besok', methods=['GET'])
def get_all_ispu_besok():
    """Menarik prediksi jam pertama hari esok untuk seluruh wilayah"""
    sekarang_wib = datetime.now(TZ_WIB)
    besok = sekarang_wib.date() + timedelta(days=1)
    besok_dt = datetime.combine(besok, datetime.min.time()) 
    
    data_prediksi = db.session.query(Predictions, WilayahDetails)\
                      .join(WilayahDetails, Predictions.id_wilayah == WilayahDetails.id_wilayah)\
                      .filter(Predictions.target_waktu == besok_dt).all()
    
    hasil = []
    for prediksi, wilayah in data_prediksi:
        dict_polutan = {
            'PM25': prediksi.pred_pm25, 'PM10': prediksi.pred_pm10, 
            'CO': prediksi.pred_co, 'NO2': prediksi.pred_no2, 
            'O3': prediksi.pred_ozon, 'SO2': prediksi.pred_so2
        }
        ispu_calc = kalkulasi_ispu_final(dict_polutan)
        
        hasil.append({
            "kota": wilayah.nama_wilayah,
            "nilai_ispu": ispu_calc['nilai_ispu'],      # KOREKSI: Ambil dari hasil hitung dinamis
            "kategori": ispu_calc['kategori'],          # KOREKSI: Ambil dari hasil hitung dinamis
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

@app.route('/api/ispu/<nama_kota>', methods=['GET'], strict_slashes=False)
def get_ispu_kota(nama_kota):
    print(f"DEBUG: Backend menerima request untuk kota: {nama_kota}")
    filter_tipe = request.args.get('days', '7') 
    
    wilayah = WilayahDetails.query.filter_by(nama_wilayah=nama_kota).first()
    if not wilayah:
        return jsonify({"error": "Kota tidak terdaftar di database kami."}), 404

    # ==============================================================
    # KARTU BIRU: AMBIL PREDIKSI JAM PERTAMA BESOK
    # ==============================================================
    sekarang_wib = datetime.now(TZ_WIB)
    besok = sekarang_wib.date() + timedelta(days=1)
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
            "nilai_ispu": ispu_calc['nilai_ispu'],      # KOREKSI: Pakai hitung dinamis
            "kategori": ispu_calc['kategori'],          # KOREKSI: Pakai hitung dinamis
            "parameter_kritis": ispu_calc['parameter_kritis']
        }

    # ==============================================================
    # KANVAS GRAFIK: HITUNG ISPU HISTORIS SECARA DINAMIS
    # ==============================================================
    hasil_grafik = []
    waktu_sekarang = datetime.now(TZ_WIB)

    if filter_tipe == '24jam':
        batas_waktu = waktu_sekarang - timedelta(hours=24)
        
        data_historis = DataHistoris.query.filter(
            DataHistoris.id_wilayah == wilayah.id_wilayah,
            DataHistoris.waktu_aktual >= batas_waktu,
            DataHistoris.waktu_aktual <= waktu_sekarang
        ).order_by(DataHistoris.waktu_aktual.asc()).all()
        
        for row in data_historis:
            # KOREKSI: Hitung skor ISPU historis per jam secara langsung
            dict_polutan_hist = {
                'PM25': row.pm25, 'PM10': row.pm10, 'CO': row.co,
                'NO2': row.no2, 'O3': row.ozon, 'SO2': row.so2
            }
            ispu_hist = kalkulasi_ispu_final(dict_polutan_hist)
            
            hasil_grafik.append({
                "tanggal": row.waktu_aktual.strftime("%H:00"), 
                "nilai_ispu": ispu_hist['nilai_ispu']
            })
                
    else:
        days_filter = int(filter_tipe)
        batas_waktu = waktu_sekarang.date() - timedelta(days=days_filter)
        batas_waktu_dt = datetime.combine(batas_waktu, datetime.min.time())
        
        data_historis = DataHistoris.query.filter(
            DataHistoris.id_wilayah == wilayah.id_wilayah,
            DataHistoris.waktu_aktual >= batas_waktu_dt,
            DataHistoris.waktu_aktual < datetime.combine(waktu_sekarang.date(), datetime.min.time())
        ).order_by(DataHistoris.waktu_aktual.asc()).all()
        
        harian_dict = {}
        for row in data_historis:
            tgl_str = row.waktu_aktual.strftime("%d %b")
            if tgl_str not in harian_dict:
                harian_dict[tgl_str] = []
            
            # KOREKSI: Hitung skor ISPU harian secara langsung sebelum dirata-rata
            dict_polutan_hist = {
                'PM25': row.pm25, 'PM10': row.pm10, 'CO': row.co,
                'NO2': row.no2, 'O3': row.ozon, 'SO2': row.so2
            }
            ispu_hist = kalkulasi_ispu_final(dict_polutan_hist)
            harian_dict[tgl_str].append(ispu_hist['nilai_ispu'])
            
        for tgl_str, list_ispu in harian_dict.items():
            avg_ispu = sum(list_ispu) / len(list_ispu)
            hasil_grafik.append({
                "tanggal": tgl_str, 
                "nilai_ispu": round(avg_ispu)
            })

    return jsonify({
        "kota": nama_kota,
        "prediksi_besok": data_prediksi,
        "grafik": hasil_grafik
    }), 200

if __name__ == '__main__':
    with app.app_context():
        print("✅ Semua tabel proyek prediksi ISPU berhasil dicetak di Supabase!")
    
    app.run(debug=True, host='0.0.0.0', port=5000)