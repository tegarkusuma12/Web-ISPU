// Daftar 10 Kota Sesuai Dataset
const cities = [
    "Surabaya", "Malang", "Sidoarjo", "Gresik", "Bojonegoro", 
    "Tulungagung", "Kediri", "Madiun", "Jember", "Banyuwangi"
];

let myChart = null; // Variabel penampung grafik agar bisa di-reset

// VARIABEL GLOBAL: Untuk mengingat state (posisi) pengguna saat ini
let kotaAktif = cities[0]; // Default: Surabaya
let filterHariAktif = 7;   // Default: 7 Hari

// Fungsi untuk menentukan warna latar belakang kartu berdasarkan status ISPU
function getStatusColor(kategori) {
    if (!kategori) return '#6c757d'; // Abu-abu jika kosong
    
    switch(kategori.toLowerCase()) {
        case 'baik': return '#198754'; // Hijau
        case 'sedang': return '#0dcaf0'; // Biru Muda
        case 'tidak sehat': return '#ffc107'; // Kuning/Oranye
        case 'sangat tidak sehat': return '#dc3545'; // Merah
        case 'berbahaya': return '#212529'; // Hitam
        default: return '#6c757d'; // Abu-abu
    }
}

// Fungsi utama untuk menarik data dari Backend Flask
async function fetchIspuData(kota, jumlahHari) {
    try {
        // Update memori global setiap kali fungsi ini dipanggil
        kotaAktif = kota;
        filterHariAktif = jumlahHari;

        // Tembak API Backend dengan tambahan query parameter ?days=
        const response = await fetch(`http://127.0.0.1:5000/api/ispu/${kota}?days=${jumlahHari}`);
        
        if (!response.ok) {
            throw new Error("Data belum tersedia untuk kota ini.");
        }

        const result = await response.json();
        
        // Data kini sudah dipisah rapi oleh Backend Flask-mu
        const prediksiBesok = result.prediksi_besok;
        const dataGrafik = result.grafik;

        // 1. Update Teks di Kartu Indikator Biru (Selalu data besok)
        document.getElementById('ispuValue').innerText = prediksiBesok.nilai_ispu || "--";
        document.getElementById('ispuStatus').innerText = prediksiBesok.kategori || "Menunggu Data AI";
        document.getElementById('kritisValue').innerText = prediksiBesok.parameter_kritis || "--";
        
        // 2. Update Warna Kartu
        document.getElementById('statusCard').style.backgroundColor = getStatusColor(prediksiBesok.kategori);

        // 3. Update Grafik (Chart.js) dengan data fluktuasi
        updateChart(dataGrafik, kota);

    } catch (error) {
        console.error("Gagal menarik data:", error);
        // Jika data kosong/error, kembalikan ke setelan abu-abu
        document.getElementById('ispuValue').innerText = "--";
        document.getElementById('ispuStatus').innerText = "Data Belum Tersedia";
        document.getElementById('kritisValue').innerText = "--";
        document.getElementById('statusCard').style.backgroundColor = '#6c757d';
        if(myChart) myChart.destroy(); // Hapus grafik lama
    }
}

// Fungsi khusus saat tombol filter hari ditekan
function ubahFilterHari(hari) {
    // Matikan semua warna tombol dulu (Hapus class 'active')
    document.getElementById('btn-24-jam').classList.remove('active');
    document.getElementById('btn-7-hari').classList.remove('active');
    document.getElementById('btn-30-hari').classList.remove('active');

    // Nyalakan hanya tombol yang sedang diklik
    if (hari === '24jam') {
        document.getElementById('btn-24-jam').classList.add('active');
    } else if (hari === 7) {
        document.getElementById('btn-7-hari').classList.add('active');
    } else if (hari === 30) {
        document.getElementById('btn-30-hari').classList.add('active');
    }
    
    // Muat ulang data menggunakan kota yang sedang menyala dan filter yang baru
    fetchIspuData(kotaAktif, hari);
}

// Fungsi untuk menggambar grafik garis
function updateChart(dataGrafik, kota) {
    const ctx = document.getElementById('ispuChart').getContext('2d');
    
    // Jika data kosong, jangan gambar grafik
    if (!dataGrafik || dataGrafik.length === 0) {
        if (myChart) myChart.destroy();
        return;
    }
    
    // Ekstrak label tanggal/jam dan nilai ISPU untuk sumbu X dan Y
    const labelsWaktu = dataGrafik.map(row => row.tanggal);
    const dataIspu = dataGrafik.map(row => row.nilai_ispu);

    // Hancurkan grafik sebelumnya jika ada (agar tidak tertumpuk)
    if (myChart) {
        myChart.destroy();
    }

    // Buat grafik baru
    myChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labelsWaktu,
            datasets: [{
                label: `Nilai ISPU ${kota}`,
                data: dataIspu,
                borderColor: '#0d6efd',
                backgroundColor: 'rgba(13, 110, 253, 0.2)',
                borderWidth: 3,
                // Logika Pintar: Titik besar (5) untuk 7 hari. Titik kecil (2) untuk 24 jam dan 30 hari agar tidak sumpek.
                pointRadius: dataGrafik.length > 10 ? 2 : 5, 
                fill: true,
                tension: 0.3 // Membuat garisnya agak melengkung mulus
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: {
                    beginAtZero: true,
                    suggestedMax: 150 // Nilai Y maksimal yang disarankan
                }
            }
        }
    });
}

// Fungsi untuk membuat tombol-tombol kota secara dinamis
function setupCityButtons() {
    const tabContainer = document.getElementById('cityTabs');
    
    cities.forEach((kota, index) => {
        const li = document.createElement('li');
        li.className = 'nav-item';
        
        const a = document.createElement('a');
        a.className = `nav-link fw-bold ${index === 0 ? 'active' : ''}`; // Aktifkan kota pertama
        a.innerText = kota;
        a.onclick = (e) => {
            // Hapus class 'active' dari semua tombol kota, pindahkan ke yang diklik
            document.querySelectorAll('#cityTabs .nav-link').forEach(btn => btn.classList.remove('active'));
            e.target.classList.add('active');
            
            // Panggil fungsi tarik data dengan mempertahankan opsi rentang waktu yang sedang aktif
            fetchIspuData(kota, filterHariAktif);
        };
        
        li.appendChild(a);
        tabContainer.appendChild(li);
    });
}

// Dijalankan pertama kali saat halaman web selesai dimuat
window.onload = () => {
    setupCityButtons();
    // Tarik data secara default menggunakan kota pertama (Surabaya) dan mode 7 hari
    fetchIspuData(kotaAktif, filterHariAktif); 
};