# 🌍 Prediksi ISPU (Indeks Standar Pencemar Udara) Jawa Timur 24 Jam

Proyek *End-to-End Machine Learning* untuk memprediksi tingkat kualitas udara (PM2.5, PM10, SO2, CO, NO2, Ozon) secara *real-time* hingga 24 jam ke depan untuk 38 Kabupaten/Kota di Provinsi Jawa Timur.

---

## 📌 Latar Belakang & Flow Arsitektur
Polusi udara adalah ancaman diam-diam bagi kesehatan masyarakat. Proyek ini dikembangkan sebagai sistem peringatan dini (*early warning system*) kualitas udara di Jawa Timur dengan memadukan data aktual dari stasiun cuaca, model prediksi cerdas *Machine Learning*, dan visualisasi dasbor interaktif.

```mermaid
flowchart TD
    subgraph Pengumpulan Data
        API[OpenWeather Air Pollution API] -->|Tarik Data Polusi Per Jam| SCH[APScheduler / scheduler.py]
    end

    subgraph Penyimpanan & Validasi
        SCH -->|1. Simpan Data Aktual| DB[(Supabase PostgreSQL)]
        SCH -->|2. Bandingkan Aktual vs Prediksi Lama| AUD[Audit Akurasi / ValidationsLogs]
        AUD -->|Simpan Nilai MAE Dinamis| DB
    end

    subgraph Inferensi Machine Learning
        DB -->|Ambil Riwayat Data 4 Hari| FE[Feature Engineering / ispu_logic.py]
        FE -->|Lag & Rolling Features| XGB[XGBoost Multi-Output Model]
        XGB -->|3. Hasilkan Proyeksi 24 Jam Ke Depan| DB
        FE -->|4. Hitung ISPU Aktual Kemenlhk| DB
    end

    subgraph Antarmuka Pengguna
        DB -->|Endpoints API| Flask[Flask API / app.py]
        Flask -->|AJAX Fetch / HTTPS| FE_UI[Dashboard Frontend / HTML + JS + Leaflet]
    end
```

---

## 🚀 Fitur Utama
* **Automated Data Pipeline (Rolling Horizon):** Scheduler otomatis (`scheduler.py`) berjalan setiap jam menggunakan **APScheduler** untuk menarik data cuaca riil terbaru dari OpenWeather API.
* **Model ML XGBoost Spesialis:** Prediksi multi-output yang memproyeksikan konsentrasi 6 parameter polutan (PM2.5, PM10, SO2, CO, NO2, O3) untuk 24 jam ke depan menggunakan XGBoost dengan transformasi logaritmik (mencegah nilai negatif).
* **Audit Akurasi Real-Time:** Menghitung skor R² dan MAE (Mean Absolute Error) secara dinamis dengan mencocokkan tebakan AI jam lalu terhadap data riil yang baru ditarik.
* **Kalkulator ISPU Standar Kemenlhk:** Konversi otomatis konsentrasi polutan mikrogram menjadi indeks ISPU berdasarkan Peraturan Kemenlhk P.14/2020 (menggunakan aturan minimal 18 jam data valid / 75%).
* **Interactive Choropleth Dashboard:** Dasbor modern berbasis Glassmorphism menggunakan **Leaflet.js** untuk peta interaktif wilayah Jawa Timur dan **Chart.js** untuk visualisasi tren historis (24 jam, 7 hari, 30 hari).
* **Fitur Time-Slider (Mesin Waktu):** Mengizinkan pengguna menggeser slider waktu dari "+0 Jam (Sekarang)" hingga "+24 Jam" untuk melihat proyeksi visual kualitas udara di masa depan pada peta.

---

## 🛠️ Tech Stack & Struktur File

### Teknologi Utama:
* **Backend:** Python 3.10+, Flask, Flask-SQLAlchemy (PostgreSQL / Supabase)
* **Frontend:** Vanilla HTML5, CSS3 (Glassmorphism), JavaScript (ES6+), Leaflet.js, Chart.js
* **Machine Learning & Pipeline:** XGBoost, Pandas, NumPy, Joblib, APScheduler, requests

### 📁 Struktur Proyek:
```text
Proyek ISPU/
│
├── backend/                  # REST API & Data Pipeline
│   ├── app.py                # Server Flask API utama & Skema Database
│   ├── scheduler.py          # Script cron job penarik data & inferensi ML
│   ├── ispu_logic.py         # Logika hitung ISPU Kemenlhk & Feature Engineering
│   ├── mass_seeder.py        # Utility pengunggah dataset CSV awal ke database
│   ├── fetch_real_history.py # Utility untuk backup/tarik data historis
│   ├── Dockerfile            # Blueprint Docker Image
│   ├── requirements.txt      # Daftar dependensi Python
│   └── models/               # Menyimpan file XGBoost model .pkl
│
├── frontend/                 # Dasbor Antarmuka Web (UI)
│   ├── index.html            # Struktur halaman web
│   ├── app.js                # Logic AJAX fetch, peta Leaflet, & grafik Chart.js
│   └── jatim.json            # GeoJSON batas geografis kabupaten/kota Jawa Timur
│
├── data_training/            # Proses Riset & Training ML
│   ├── eda.ipynb             # Analisis awal data polusi
│   ├── baseline_automl.ipynb # Eksperimen model pembanding
│   └── best_model.ipynb      # Finalisasi model & rekayasa fitur XGBoost
│
├── docker-compose.yml        # Konfigurasi orkestrasi kontainer Docker
└── .env                      # File konfigurasi env (tidak di-commit)
```

---

## ⚙️ Cara Menjalankan Proyek Secara Lokal

### 1. Prasyarat:
* Pastikan komputer Anda telah terinstal **Python 3.10+** dan **Git**.
* Buat akun di **Supabase** untuk database PostgreSQL gratis.
* Daftarkan akun di **OpenWeather** untuk mendapatkan API Key polusi udara gratis.

### 2. Konfigurasi Environment:
Buat file bernama `.env` di folder utama proyek, lalu isi dengan format berikut:
```env
OPENWEATHER_API_KEY=isi_api_key_openweather_anda
DATABASE_URL_POOLER=postgresql://user:password@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres
DATABASE_URL_DIRECT=postgresql://user:password@db.supabase.co:5432/postgres
DAGSHUB_REPO_OWNER=username_anda
DAGSHUB_REPO_NAME=Proyek-ISPU
```

### 3. Instalasi Backend:
1. Masuk ke folder backend:
   ```bash
   cd backend
   ```
2. Buat & aktifkan virtual environment (opsional tapi direkomendasikan):
   ```bash
   python -m venv venv
   # Di Windows:
   venv\Scripts\activate
   # Di Linux/macOS:
   source venv/bin/activate
   ```
3. Instal semua dependensi:
   ```bash
   pip install -r requirements.txt
   ```
4. Jalankan seeder data historis awal (opsional, pastikan file CSV ada):
   ```bash
   python mass_seeder.py
   ```
5. Jalankan Flask API:
   ```bash
   python app.py
   ```
   *API akan aktif di `http://100.75.93.73:5000` atau `http://localhost:5000`.*

### 4. Jalankan Scheduler (di terminal terpisah):
```bash
cd backend
# Aktifkan virtual environment
python scheduler.py
```

### 5. Jalankan Frontend:
Cukup buka file `frontend/index.html` menggunakan browser Anda, atau jalankan menggunakan VS Code Live Server.

---

## 🐋 Panduan Docker Deployment (Production)

Proyek ini telah didukung sepenuhnya oleh Docker untuk deployment di server VPS.

### 1. Menjalankan secara Lokal / Server menggunakan Docker Compose:
Jika file `.env` sudah lengkap, jalankan perintah di bawah ini pada folder utama proyek:
```bash
docker compose up -d --build
```
Perintah ini akan menyalakan dua kontainer:
1. `backend_api_ispu`: Berjalan di port 5000 menyajikan API.
2. `scheduler_api_ispu`: Menjalankan cron job scheduler penarik data di latar belakang.

### 2. Deployment Terkelola via Portainer (Web Stacks):
Jika Anda menggunakan Portainer untuk mengelola server Anda:
1. Buat **Stack** baru di Portainer.
2. Hapus baris `env_file:` pada kode docker-compose dan daftarkan variabel lingkungan Anda langsung di form input Portainer.
3. Gunakan `network_mode: host` jika server Anda menggunakan **Tailscale** untuk menghindari masalah resolusi DNS.

---
*Dikembangkan dengan dedikasi untuk mendukung analisis kualitas udara Jawa Timur secara real-time.*
