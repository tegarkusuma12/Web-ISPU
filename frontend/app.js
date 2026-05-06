// VARIABEL GLOBAL
let myChart = null; // Penampung grafik Chart.js
let kotaAktif = 'Surabaya'; // Default awal
let filterHariAktif = 7; 
let allCitiesData = []; // Penampung data 38 kota
let map = null; // Penampung objek Leaflet Map

// ==========================================
// FUNGSI UTILITAS UI
// ==========================================
function getStatusColor(kategori) {
    if (!kategori) return '#6c757d'; 
    switch(kategori.toLowerCase()) {
        case 'baik': return '#198754'; 
        case 'sedang': return '#0dcaf0'; 
        case 'tidak sehat': return '#ffc107'; 
        case 'sangat tidak sehat': return '#dc3545'; 
        case 'berbahaya': return '#212529'; 
        default: return '#6c757d'; 
    }
}

// ==========================================
// INISIALISASI PETA DASAR (PERSIAPAN LANGKAH 4)
// ==========================================
function initMap() {
    // Kordinat tengah Jawa Timur
    map = L.map('map').setView([-7.75, 112.75], 7);
    
    // Memuat visual peta dari OpenStreetMap
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(map);
}

// ==========================================
// FITUR BARU: TARIK SEMUA DATA (DASHBOARD)
// ==========================================
async function loadDashboard() {
    try {
        const response = await fetch('http://127.0.0.1:5000/api/ispu/all_besok');
        const result = await response.json();
        allCitiesData = result.data;

        populateSearch(allCitiesData);
        updateLeaderboard(allCitiesData);
        
        // Panggil fungsi pewarnaan peta di sini!
        renderPetaWarna(allCitiesData); 
        
    } catch (error) {
        console.error("Gagal memuat data dashboard:", error);
    }
}

// ==========================================
// FITUR BARU: SMART SEARCH BAR
// ==========================================
function populateSearch(data) {
    const datalist = document.getElementById('daftar-kota');
    datalist.innerHTML = ''; // Kosongkan dulu
    
    // Masukkan 38 kota ke dalam list pencarian
    data.forEach(item => {
        const option = document.createElement('option');
        option.value = item.kota;
        datalist.appendChild(option);
    });

    // Deteksi jika user mengetik atau memilih kota dari dropdown pencarian
    const searchInput = document.getElementById('city-search');
    searchInput.addEventListener('change', (e) => {
        const selected = e.target.value;
        // Pastikan kota yang diketik valid (ada di dalam array data)
        if (data.find(d => d.kota === selected)) {
            pilihKota(selected);
            searchInput.value = ''; // Kosongkan bar pencarian setelah ditekan
        }
    });
}

// ==========================================
// FITUR BARU: LEADERBOARD KOTA
// ==========================================
function updateLeaderboard(data) {
    // Copy data agar tidak merusak array aslinya
    // Urutkan dari ISPU Tertinggi ke Terendah (Buruk -> Baik)
    const sortedTerburuk = [...data].sort((a, b) => b.nilai_ispu - a.nilai_ispu);
    const top5Terburuk = sortedTerburuk.slice(0, 5);
    
    // Urutkan dari ISPU Terendah ke Tertinggi (Baik -> Buruk)
    const sortedTerbersih = [...data].sort((a, b) => a.nilai_ispu - b.nilai_ispu);
    const top5Terbersih = sortedTerbersih.slice(0, 5);

    // Fungsi kecil untuk membuat elemen list HTML
    const renderList = (arrayData, containerId) => {
        const container = document.getElementById(containerId);
        container.innerHTML = '';
        arrayData.forEach(item => {
            const color = getStatusColor(item.kategori);
            container.innerHTML += `
                <li class="list-group-item d-flex justify-content-between align-items-center" 
                    style="cursor: pointer; transition: 0.3s;" 
                    onmouseover="this.style.backgroundColor='#f1f3f5'" 
                    onmouseout="this.style.backgroundColor='white'"
                    onclick="pilihKota('${item.kota}')">
                    <span class="fw-semibold">${item.kota}</span>
                    <span class="badge rounded-pill text-white badge-ispu" style="background-color: ${color}">
                        ${item.nilai_ispu}
                    </span>
                </li>
            `;
        });
    };

    // Cetak ke HTML (Perhatikan ID list-terberish dari HTML sebelumnya)
    renderList(top5Terburuk, 'list-terburuk');
    renderList(top5Terbersih, 'list-terberish');
}

// ==========================================
// FUNGSI JEMBATAN (Menggantikan fungsi Tab 10 Kota)
// ==========================================
function pilihKota(kota) {
    document.getElementById('selectedCityTitle').innerText = `Detail Wilayah: ${kota}`;
    fetchIspuData(kota, filterHariAktif);
    
    // Otomatis menggulir layar ke bagian detail
    document.getElementById('detail-view').scrollIntoView({ behavior: 'smooth' });
}

// ==========================================
// FUNGSI LAMA: DETAIL KOTA & GRAFIK (DISEMPURNAKAN)
// ==========================================
async function fetchIspuData(kota, jumlahHari) {
    try {
        kotaAktif = kota;
        filterHariAktif = jumlahHari;

        const response = await fetch(`http://127.0.0.1:5000/api/ispu/${kota}?days=${jumlahHari}`);
        if (!response.ok) throw new Error("Data belum tersedia.");

        const result = await response.json();
        const prediksiBesok = result.prediksi_besok;
        const dataGrafik = result.grafik;

        // Update Kartu Biru Detail
        document.getElementById('ispuValue').innerText = prediksiBesok.nilai_ispu || "--";
        document.getElementById('ispuStatus').innerText = prediksiBesok.kategori || "Menunggu Data";
        document.getElementById('kritisValue').innerText = prediksiBesok.parameter_kritis || "--";
        document.getElementById('statusCard').style.backgroundColor = getStatusColor(prediksiBesok.kategori);

        updateChart(dataGrafik, kota);

    } catch (error) {
        console.error("Gagal menarik detail data:", error);
        document.getElementById('ispuValue').innerText = "--";
        document.getElementById('ispuStatus').innerText = "Data Belum Tersedia";
        document.getElementById('kritisValue').innerText = "--";
        document.getElementById('statusCard').style.backgroundColor = '#6c757d';
        if(myChart) myChart.destroy();
    }
}

function ubahFilterHari(hari) {
    document.getElementById('btn-24-jam').classList.remove('active');
    document.getElementById('btn-7-hari').classList.remove('active');
    document.getElementById('btn-30-hari').classList.remove('active');

    if (hari === '24jam') document.getElementById('btn-24-jam').classList.add('active');
    else if (hari === 7) document.getElementById('btn-7-hari').classList.add('active');
    else if (hari === 30) document.getElementById('btn-30-hari').classList.add('active');
    
    fetchIspuData(kotaAktif, hari);
}

function updateChart(dataGrafik, kota) {
    const ctx = document.getElementById('ispuChart').getContext('2d');
    
    if (!dataGrafik || dataGrafik.length === 0) {
        if (myChart) myChart.destroy();
        return;
    }
    
    const labelsWaktu = dataGrafik.map(row => row.tanggal);
    const dataIspu = dataGrafik.map(row => row.nilai_ispu);

    if (myChart) myChart.destroy();

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
                pointRadius: dataGrafik.length > 10 ? 2 : 5, 
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            scales: {
                y: { beginAtZero: true, suggestedMax: 150 }
            }
        }
    });
}

// ==========================================
// EKSEKUSI UTAMA SAAT WEBSITE DIBUKA
// ==========================================
window.onload = async () => {
    initMap(); // 1. Munculkan gambar dasar peta (Langkah 4 menyusul)
    await loadDashboard(); // 2. Tarik 38 kota untuk Leaderboard dan Search
    pilihKota('Surabaya'); // 3. Tampilkan detail Surabaya sebagai default
};

// ==========================================
// FITUR BARU: PEWARNAAN PETA CHOROPLETH (LANGKAH 4)
// ==========================================
async function renderPetaWarna(dataAI) {
    try {
        // Mengambil data GeoJSON public untuk batas Polygon Kabupaten/Kota se-Jatim
        const response = await fetch('https://raw.githubusercontent.com/ans-frendika/geojson-jawa-timur/master/kabupaten-kota.geojson');
        const geojson = await response.json();

        L.geoJSON(geojson, {
            // Fungsi untuk memberi warna wilayah
            style: function (feature) {
                let namaWilayahPeta = feature.properties.KABKOT; // Nama wilayah dari file Peta
                
                // Cari data AI kita yang namanya cocok dengan nama di Peta
                let kotaDitemukan = dataAI.find(d => 
                    d.kota.toUpperCase() === namaWilayahPeta.toUpperCase() || 
                    d.kota.toUpperCase() === `KABUPATEN ${namaWilayahPeta.toUpperCase()}` ||
                    `KABUPATEN ${d.kota.toUpperCase()}` === namaWilayahPeta.toUpperCase()
                );

                // Jika datanya ada, warnai sesuai kategori. Jika tidak, warnai abu-abu.
                let warnaArea = kotaDitemukan ? getStatusColor(kotaDitemukan.kategori) : '#cccccc';

                return {
                    fillColor: warnaArea,
                    weight: 1, // Ketebalan garis batas kota
                    opacity: 1,
                    color: 'white', // Warna garis batas kota
                    fillOpacity: 0.7
                };
            },
            // Fungsi interaksi (Klik dan Hover)
            onEachFeature: function (feature, layer) {
                let namaWilayahPeta = feature.properties.KABKOT;
                let kotaDitemukan = dataAI.find(d => 
                    d.kota.toUpperCase() === namaWilayahPeta.toUpperCase() || 
                    d.kota.toUpperCase() === `KABUPATEN ${namaWilayahPeta.toUpperCase()}`
                );
                
                if (kotaDitemukan) {
                    // Munculkan popup kecil saat di-hover/klik
                    layer.bindPopup(`<b>${kotaDitemukan.kota}</b><br>ISPU: ${kotaDitemukan.nilai_ispu} (${kotaDitemukan.kategori})`);
                    
                    // Jika wilayah di peta diklik, gulir ke bawah dan tampilkan grafiknya
                    layer.on('click', () => {
                        pilihKota(kotaDitemukan.kota);
                    });
                }
            }
        }).addTo(map);

    } catch(e) {
        console.error("Gagal memuat GeoJSON Peta:", e);
    }
}