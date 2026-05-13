import os
import joblib
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, Float, String, Date
from sqlalchemy.orm import declarative_base, sessionmaker, Session

load_dotenv()

# ==========================================
# 1. INISIALISASI FASTAPI & MODEL AI
# ==========================================
app = FastAPI(title="Proyek Prediksi Polutan Fast API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    MODEL_PATH = os.path.join(BASE_DIR, 'models', 'xgb_ispu_jatim_multi_otak.pkl')
    
    paket_model = joblib.load(MODEL_PATH)
    model_spesialis = paket_model['dict_model_spesialis']
    print(f"✅ Otak AI berhasil dimuat dari: {MODEL_PATH}")
except Exception as e:
    print(f"⚠️ Gagal memuat model. Error: {e}")
    model_spesialis = {}

# ==========================================
# 2. KONFIGURASI DATABASE POSTGRESQL
# ==========================================
DATABASE_URL = os.getenv(
    'DATABASE_URL', 
    'postgresql://ispu_admin:rahasia_ispu@localhost:5433/ispu_jatim_db'
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class HasilPrediksi(Base):
    __tablename__ = 'hasil_prediksi'
    id = Column(Integer, primary_key=True, index=True)
    tanggal_prediksi = Column(Date)
    kota = Column(String(50))
    pm25 = Column(Float)
    pm10 = Column(Float)
    co = Column(Float)
    no2 = Column(Float)
    o3 = Column(Float)
    so2 = Column(Float, default=0.0)
    nilai_ispu = Column(Integer)
    kategori = Column(String(50))
    parameter_kritis = Column(String(50))

Base.metadata.create_all(bind=engine)

# ==========================================
# 3. SKEMA INPUT
# ==========================================
class InputPolutan(BaseModel):
    pm25: float = Field(..., example=45.5)
    pm10: float = Field(..., example=50.2)
    so2: float = Field(..., example=12.0)
    co: float = Field(..., example=1.5)
    no2: float = Field(..., example=20.1)
    ozon: float = Field(..., example=30.0)

# ==========================================
# 4. ENDPOINT API
# ==========================================

@app.post("/predict", tags=["AI Prediction"])
async def prediksi_ispu_besok(data: InputPolutan):
    """ Menerima data polutan hari ini dan menebak nilai untuk besok (dengan Padding Fitur) """
    if not model_spesialis:
        return {"error": "Model tidak ditemukan"}

    semua_fitur = [
        'PM2.5 (µg/m³)', 'PM10 (µg/m³)', 'SO2 (µg/m³)', 'CO (µg/m³)', 'NO2 (µg/m³)', 'Ozon (µg/m³)', 
        'Bulan', 'Is_Weekend', 'PM2.5 (µg/m³)_H-1', 'PM2.5 (µg/m³)_H-2', 'PM2.5 (µg/m³)_H-3', 
        'PM2.5 (µg/m³)_RollMean_3', 'PM2.5 (µg/m³)_RollMax_3', 'PM10 (µg/m³)_H-1', 'PM10 (µg/m³)_H-2', 
        'PM10 (µg/m³)_H-3', 'PM10 (µg/m³)_RollMean_3', 'PM10 (µg/m³)_RollMax_3', 'SO2 (µg/m³)_H-1', 
        'SO2 (µg/m³)_H-2', 'SO2 (µg/m³)_H-3', 'SO2 (µg/m³)_RollMean_3', 'SO2 (µg/m³)_RollMax_3', 
        'CO (µg/m³)_H-1', 'CO (µg/m³)_H-2', 'CO (µg/m³)_H-3', 'CO (µg/m³)_RollMean_3', 'CO (µg/m³)_RollMax_3', 
        'NO2 (µg/m³)_H-1', 'NO2 (µg/m³)_H-2', 'NO2 (µg/m³)_H-3', 'NO2 (µg/m³)_RollMean_3', 'NO2 (µg/m³)_RollMax_3', 
        'Ozon (µg/m³)_H-1', 'Ozon (µg/m³)_H-2', 'Ozon (µg/m³)_H-3', 'Ozon (µg/m³)_RollMean_3', 'Ozon (µg/m³)_RollMax_3', 
        'Kota_Kabupaten Bangkalan', 'Kota_Kabupaten Banyuwangi', 'Kota_Kabupaten Blitar', 'Kota_Kabupaten Bojonegoro', 
        'Kota_Kabupaten Bondowoso', 'Kota_Kabupaten Gresik', 'Kota_Kabupaten Jember', 'Kota_Kabupaten Jombang', 
        'Kota_Kabupaten Kediri', 'Kota_Kabupaten Lamongan', 'Kota_Kabupaten Lumajang', 'Kota_Kabupaten Madiun', 
        'Kota_Kabupaten Magetan', 'Kota_Kabupaten Malang', 'Kota_Kabupaten Mojokerto', 'Kota_Kabupaten Nganjuk', 
        'Kota_Kabupaten Ngawi', 'Kota_Kabupaten Pacitan', 'Kota_Kabupaten Pamekasan', 'Kota_Kabupaten Pasuruan', 
        'Kota_Kabupaten Ponorogo', 'Kota_Kabupaten Probolinggo', 'Kota_Kabupaten Sampang', 'Kota_Kabupaten Sidoarjo', 
        'Kota_Kabupaten Situbondo', 'Kota_Kabupaten Sumenep', 'Kota_Kabupaten Trenggalek', 'Kota_Kabupaten Tuban', 
        'Kota_Kabupaten Tulungagung', 'Kota_Kota Batu', 'Kota_Kota Blitar', 'Kota_Kota Kediri', 'Kota_Kota Madiun', 
        'Kota_Kota Malang', 'Kota_Kota Mojokerto', 'Kota_Kota Pasuruan', 'Kota_Kota Probolinggo', 'Kota_Kota Surabaya'
    ]

    data_lengkap = {fitur: 0.0 for fitur in semua_fitur}

    data_lengkap['PM2.5 (µg/m³)'] = data.pm25
    data_lengkap['PM10 (µg/m³)'] = data.pm10
    data_lengkap['SO2 (µg/m³)'] = data.so2
    data_lengkap['CO (µg/m³)'] = data.co
    data_lengkap['NO2 (µg/m³)'] = data.no2
    data_lengkap['Ozon (µg/m³)'] = data.ozon

    data_lengkap['Kota_Kota Surabaya'] = 1.0
    data_lengkap['Bulan'] = float(datetime.now().month)

    input_df = pd.DataFrame([data_lengkap])
    input_df = input_df[semua_fitur]
    
    hasil_tebakan = {}
    
    try:
        for polutan, model in model_spesialis.items():
            tebakan = model.predict(input_df)[0]
            hasil_tebakan[polutan] = max(0.0, round(float(tebakan), 2))
            
        return {
            "status": "sukses",
            "pesan": "Berhasil menebak dengan fitur bayangan",
            "prediksi_besok": hasil_tebakan
        }
    except Exception as e:
        return {"status": "gagal", "pesan_error": str(e)}

@app.get('/api/ispu/all_besok', tags=["Database"])
def get_all_ispu_besok(db: Session = Depends(get_db)):
    """ Mengambil seluruh data prediksi dari PostgreSQL """
    besok = datetime.now().date() + timedelta(days=1)
    data = db.query(HasilPrediksi).filter(HasilPrediksi.tanggal_prediksi == besok).all()
    
    return {
        "tanggal_prediksi": str(besok),
        "total_data": len(data),
        "data": data
    }

@app.get('/api/status', tags=["System"])
def cek_status():
    return {"pesan": "Backend FastAPI Aktif!"}