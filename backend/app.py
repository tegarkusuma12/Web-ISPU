# backend/app.py
import os
import pytz
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from datetime import datetime, timedelta
from dotenv import load_dotenv
from ispu_logic import kalkulasi_ispu_final

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, '.env')

load_dotenv(ENV_PATH) 

app = Flask(__name__)
CORS(app) 

app.config['CACHE_TYPE'] = 'SimpleCache'
app.config['CACHE_DEFAULT_TIMEOUT'] = 900
cache = Cache(app)

TZ_WIB = pytz.timezone('Asia/Jakarta')

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

class IspuHistoris(db.Model):
    __tablename__ = 'ispu_historis'
    id_ispu = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_wilayah = db.Column(db.Integer, db.ForeignKey('wilayah_details.id_wilayah'))
    id_data = db.Column(db.Integer, db.ForeignKey('data_historis.id_data'))
    
    nilai_ispu = db.Column(db.Integer, nullable=False)
    kategori_ispu = db.Column(db.String(50), nullable=False)
    parameter_kritis = db.Column(db.String(10), nullable=False)
    waktu_kalkulasi = db.Column(db.DateTime, nullable=False)

# ==========================================
# ENDPOINT API (Untuk Frontend)
# ==========================================

@app.route('/api/status', methods=['GET'])
def cek_status():
    return jsonify({"pesan": "Server Backend ISPU Jatim Aktif!"}), 200

# ------------------------------------------------------------------------------
# SKENARIO B: ON-THE-FLY PREDIKSI 24 JAM KE DEPAN (PENJAHITAN WAKTU)
# ------------------------------------------------------------------------------
@app.route('/api/ispu/rolling_24h', methods=['GET'])
@cache.cached(timeout=900)
def get_ispu_rolling_24h():
    """Menarik prediksi 24 jam ke depan dengan Rolling Average KEMENLHK P.14/2020"""
    try:
        sekarang_wib = datetime.now(TZ_WIB).replace(minute=0, second=0, microsecond=0)
        sekarang_utc = sekarang_wib.astimezone(pytz.UTC).replace(tzinfo=None)
        
        akhir_utc = sekarang_utc + timedelta(hours=24)
        batas_historis_utc = sekarang_utc - timedelta(hours=23) # Mundur 23 jam
        
        # 1. Tarik Data Historis 24 Jam terakhir untuk SEMUA kota sekaligus
        data_historis = db.session.query(DataHistoris, WilayahDetails)\
                          .join(WilayahDetails, DataHistoris.id_wilayah == WilayahDetails.id_wilayah)\
                          .filter(DataHistoris.waktu_aktual >= batas_historis_utc, DataHistoris.waktu_aktual <= sekarang_utc)\
                          .order_by(WilayahDetails.nama_wilayah, DataHistoris.waktu_aktual.asc()).all()
        
        # 2. Tarik Tebakan AI 24 Jam ke depan untuk SEMUA kota sekaligus
        data_prediksi = db.session.query(Predictions, WilayahDetails)\
                          .join(WilayahDetails, Predictions.id_wilayah == WilayahDetails.id_wilayah)\
                          .filter(Predictions.target_waktu > sekarang_utc, Predictions.target_waktu <= akhir_utc)\
                          .order_by(WilayahDetails.nama_wilayah, Predictions.target_waktu.asc()).all()
        
        from collections import defaultdict
        hist_dict = defaultdict(list)
        pred_dict = defaultdict(list)
        
        for hist, wil in data_historis:
            hist_dict[wil.nama_wilayah].append(hist)
            
        for pred, wil in data_prediksi:
            pred_dict[wil.nama_wilayah].append(pred)
            
        grouped_data = defaultdict(list)
        daftar_kota = set(list(hist_dict.keys()) + list(pred_dict.keys()))
        
        # 3. Proses Penjahitan Waktu (Sliding Window) per Kota
        for kota in daftar_kota:
            h_list = hist_dict[kota]
            p_list = pred_dict[kota]
            
            # Ekstrak menjadi array/list
            h_pm25 = [h.pm25 for h in h_list]; p_pm25 = [p.pred_pm25 for p in p_list]
            h_pm10 = [h.pm10 for h in h_list]; p_pm10 = [p.pred_pm10 for p in p_list]
            h_so2  = [h.so2 for h in h_list];  p_so2  = [p.pred_so2 for p in p_list]
            h_co   = [h.co for h in h_list];   p_co   = [p.pred_co for p in p_list]
            h_no2  = [h.no2 for h in h_list];  p_no2  = [p.pred_no2 for p in p_list]
            h_o3   = [h.ozon for h in h_list]; p_o3   = [p.pred_ozon for p in p_list]
            
            for i, pred in enumerate(p_list):
                waktu_target_utc = pytz.UTC.localize(pred.target_waktu)
                waktu_target_wib = waktu_target_utc.astimezone(TZ_WIB)
                
                selisih_jam = int((waktu_target_wib - sekarang_wib).total_seconds() / 3600)
                hari_str = "Hari Ini" if waktu_target_wib.date() == sekarang_wib.date() else "Besok"
                
                # Menjahit Array: (Sisa Masa Lalu) + (Tebakan Masa Depan sampai jam ke-i)
                potong_historis = 23 - i 
                
                # Fungsi potong_historis > 0 mencegah array kosong jika jam ke-24 (dimana riwayat tidak dipakai lagi)
                gabung_pm25 = (h_pm25[-potong_historis:] if potong_historis > 0 else []) + p_pm25[:i+1]
                gabung_pm10 = (h_pm10[-potong_historis:] if potong_historis > 0 else []) + p_pm10[:i+1]
                gabung_so2  = (h_so2[-potong_historis:] if potong_historis > 0 else []) + p_so2[:i+1]
                gabung_co   = (h_co[-potong_historis:] if potong_historis > 0 else []) + p_co[:i+1]
                gabung_no2  = (h_no2[-potong_historis:] if potong_historis > 0 else []) + p_no2[:i+1]
                gabung_o3   = (h_o3[-potong_historis:] if potong_historis > 0 else []) + p_o3[:i+1]

                # Keranjang berisi 24 angka siap diserahkan ke Dosen Utama (ispu_logic)
                dict_polutan_24h = {
                    'PM25': gabung_pm25, 'PM10': gabung_pm10, 
                    'CO': gabung_co, 'NO2': gabung_no2, 
                    'O3': gabung_o3, 'SO2': gabung_so2
                }
                
                ispu_calc = kalkulasi_ispu_final(dict_polutan_24h)
                
                grouped_data[kota].append({
                    "indeks_waktu": selisih_jam,
                    "jam": waktu_target_wib.strftime("%H:00"),
                    "hari": hari_str,
                    "nilai_ispu": ispu_calc['skor_ispu_final'],
                    "kategori": ispu_calc['kategori_ispu'],
                    "parameter_kritis": ispu_calc['polutan_kritis'],
                    # Biarkan frontend menerima angka raw juga untuk keperluan tooltip
                    "pm25": pred.pred_pm25, "pm10": pred.pred_pm10, 
                    "co": pred.pred_co, "no2": pred.pred_no2, 
                    "o3": pred.pred_ozon, "so2": pred.pred_so2
                })
                
        hasil_akhir = [{"kota": kota, "timeline": timeline} for kota, timeline in grouped_data.items()]
            
        return jsonify({
            "waktu_buka_web": sekarang_wib.strftime("%Y-%m-%d %H:%M WIB"),
            "total_kota": len(hasil_akhir),
            "data": hasil_akhir
        }), 200

    except Exception as e:
        import traceback
        print(f"DEBUG: Error fatal pada rolling_24h: {str(e)}")
        print(traceback.format_exc()) # Agar jika ada error, terminalmu memunculkan lokasi persisnya
        return jsonify({"error": "Gagal memproses data timeline per jam."}), 500

# ------------------------------------------------------------------------------
# SKENARIO A: KARTU BIRU & GRAFIK (MENGGUNAKAN ISPU HISTORIS)
# ------------------------------------------------------------------------------
@app.route('/api/ispu/<nama_kota>', methods=['GET'], strict_slashes=False)
@cache.cached(timeout=900, query_string=True)
def get_ispu_kota(nama_kota):
    print(f"DEBUG: Backend menerima request untuk kota: {nama_kota}")
    filter_tipe = request.args.get('days', '7') 
    
    try:
        wilayah = WilayahDetails.query.filter(WilayahDetails.nama_wilayah.ilike(f"%{nama_kota}%")).first()
        if not wilayah:
            return jsonify({"error": "Kota tidak terdaftar di database kami."}), 404

        # ==============================================================
        # KARTU BIRU: ISPU SAAT INI (Ambil dari Skenario A / Data Riil)
        # ==============================================================
        # PERBAIKAN: Bukan dari Predictions, tapi dari IspuHistoris terbaru
        db_ispu_aktual = IspuHistoris.query.filter_by(id_wilayah=wilayah.id_wilayah)\
                                     .order_by(IspuHistoris.waktu_kalkulasi.desc()).first()
        
        data_sekarang = {}
        if db_ispu_aktual:
            data_sekarang = {
                "nilai_ispu": db_ispu_aktual.nilai_ispu,
                "kategori": db_ispu_aktual.kategori_ispu,
                "parameter_kritis": db_ispu_aktual.parameter_kritis
            }

        # ==============================================================
        # KANVAS GRAFIK: HISTORIS (Ambil Matang dari Database)
        # ==============================================================
        hasil_grafik = []
        sekarang_wib = datetime.now(TZ_WIB).replace(minute=0, second=0, microsecond=0)
        sekarang_utc = sekarang_wib.astimezone(pytz.UTC).replace(tzinfo=None)

        if filter_tipe == '24jam':
            batas_waktu_utc = sekarang_utc - timedelta(hours=24)
            # PERBAIKAN: Langsung query IspuHistoris, tidak perlu kalkulasi on-the-fly lagi!
            data_historis = IspuHistoris.query.filter(
                IspuHistoris.id_wilayah == wilayah.id_wilayah,
                IspuHistoris.waktu_kalkulasi >= batas_waktu_utc,
                IspuHistoris.waktu_kalkulasi <= sekarang_utc
            ).order_by(IspuHistoris.waktu_kalkulasi.asc()).all()
            
            for row in data_historis:
                waktu_wib = pytz.UTC.localize(row.waktu_kalkulasi).astimezone(TZ_WIB)
                hasil_grafik.append({
                    "tanggal": waktu_wib.strftime("%H:00"), 
                    "nilai_ispu": row.nilai_ispu
                })
                    
        else:
            days_filter = int(filter_tipe) if filter_tipe.isdigit() else 7
            batas_waktu_utc = sekarang_utc - timedelta(days=days_filter)
            
            data_historis = IspuHistoris.query.filter(
                IspuHistoris.id_wilayah == wilayah.id_wilayah,
                IspuHistoris.waktu_kalkulasi >= batas_waktu_utc,
                IspuHistoris.waktu_kalkulasi <= sekarang_utc
            ).order_by(IspuHistoris.waktu_kalkulasi.asc()).all()
            
            # Pengelompokan harian
            harian_dict = {}
            for row in data_historis:
                waktu_wib = pytz.UTC.localize(row.waktu_kalkulasi).astimezone(TZ_WIB)
                tgl_str = waktu_wib.strftime("%d %b")
                
                if tgl_str not in harian_dict:
                    harian_dict[tgl_str] = []
                harian_dict[tgl_str].append(row.nilai_ispu)
                
            for tgl_str, list_ispu in harian_dict.items():
                if len(list_ispu) > 0:
                    avg_ispu = sum(list_ispu) / len(list_ispu)
                    hasil_grafik.append({
                        "tanggal": tgl_str, 
                        "nilai_ispu": round(avg_ispu) # Cukup di-rata-rata angkanya saja
                    })

        return jsonify({
            "kota": wilayah.nama_wilayah, 
            # Ubah key json "prediksi_besok" menjadi "kondisi_sekarang" agar UI tidak bingung
            "kondisi_sekarang": data_sekarang, 
            "grafik": hasil_grafik
        }), 200

    except Exception as e:
        print(f"DEBUG: Error fatal saat memproses /api/ispu/{nama_kota}: {str(e)}")
        return jsonify({"error": "Terjadi kesalahan internal pada server backend."}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("✅ Semua tabel proyek prediksi ISPU berhasil dicetak di Supabase!")
    
    app.run(debug=True, host='0.0.0.0', port=5000)