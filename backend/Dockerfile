# Menggunakan OS Linux Debian ramping dengan Python 3.10 bawaan
FROM python:3.10-slim

# Menghindari Python menulis file .pyc yang tidak perlu
ENV PYTHONDONTWRITEBYTECODE=1
# Memastikan log error Python langsung tampil di terminal Docker
ENV PYTHONUNBUFFERED=1

# Menentukan folder kerja di dalam mesin virtual Docker
WORKDIR /app

# Meng-copy HANYA requirements.txt terlebih dahulu (Strategi Caching Docker)
COPY requirements.txt .

# Menginstal semua pustaka yang dibutuhkan
RUN pip install --no-cache-dir -r requirements.txt

# Meng-copy seluruh sisa kode Python ke dalam folder /app di Docker
COPY . .

# Membuka port 5000 agar API bisa diakses oleh Frontend
EXPOSE 5000

# Perintah default saat container menyala (Bisa ditimpa oleh docker-compose)
CMD ["python", "app.py"]