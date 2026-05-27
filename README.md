# 🌍 Prediksi ISPU (Indeks Standar Pencemar Udara) Jawa Timur 24 Jam

Proyek *End-to-End Machine Learning* untuk memprediksi tingkat kualitas udara (PM2.5, PM10, SO2, CO, NO2, Ozon) secara *real-time* hingga 24 jam ke depan untuk 38 Kabupaten/Kota di Jawa Timur.

## 📌 Latar Belakang
Polusi udara adalah ancaman diam-diam bagi kesehatan masyarakat. Proyek ini dikembangkan untuk memberikan peringatan dini (*early warning system*) mengenai kualitas udara di Jawa Timur. Dengan memanfaatkan data riwayat cuaca dan algoritma *Machine Learning*, sistem ini mampu memproyeksikan pergerakan polutan secara presisi.

Proyek ini dibangun sebagai bagian dari implementasi keilmuan Sains Data Terapan (Applied Data Science).

## 🚀 Fitur Utama
* **Automated Data Pipeline:** Ekstraksi data polusi secara berkala menggunakan penjadwalan otomatis (*Rolling Horizon*).
* **Advanced Machine Learning:** Menggunakan XGBoost dengan arsitektur *Native Multi-Output Tree* dan Transformasi Logaritmik untuk mencegah prediksi anomali (nilai negatif).
* **MLOps Tracking:** Pelacakan eksperimen *Hyperparameter Tuning* (Optuna) secara rapi menggunakan MLflow/Dagshub.
* **Interactive Dashboard:** Antarmuka visual menggunakan Streamlit untuk memantau pergerakan ISPU secara spasial dan temporal.

## 🛠️ Tech Stack
* **Bahasa Utama:** Python 3.11+
* **Data Science & ML:** Pandas, Scikit-Learn, XGBoost, Optuna, MLflow
* **Database & Cloud:** PostgreSQL, Supabase
* **Frontend:** Streamlit

<img src="https://i.pinimg.com/736x/d5/15/0e/d5150e9b9938a738b5d965469d9e7dd3.jpg" alt="Nyoba" width="250">
