// ==========================================
// VARIABEL GLOBAL
// ==========================================
let myChart = null; 
let kotaAktif = 'Surabaya'; 
let filterHariAktif = 7; 
let allCitiesData = []; 
let map = null; 

// VARIABEL BARU UNTUK FITUR TIME SLIDER
let currentHourIndex = 0; // 0 = Sekarang, 1 = +1 Jam, dst hingga 24
let geoJsonLayer = null; // Penampung layer warna peta agar bisa dihapus & digambar ulang
let jatimGeoJSON = null; // Penampung file jatim.json agar tidak perlu didownload berulang kali

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
// INISIALISASI PETA DASAR
// ==========================================
function initMap() {
    map = L.map('map').setView([-7.75, 112.75], 7);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap &copy; CartoDB'
    }).addTo(map);
}

// ==========================================
// TARIK SEMUA DATA (DASHBOARD ROLLING 24H)
// ==========================================
async function loadDashboard() {
    try {
        // KOREKSI: Panggil endpoint baru yang berisi array 24 jam
        const response = await fetch('http://127.0.0.1:5000/api/ispu/rolling_24h');
        const result = await response.json();
        
        allCitiesData = result.data; // Simpan ke brankas global
        
        // Opsional: Tampilkan kapan web terakhir narik data
        let updateText = document.getElementById('update-time-info');
        if(updateText) updateText.innerText = "Terakhir diperbarui: " + result.waktu_buka_web;

        populateSearch(allCitiesData);
        
        // Panggil fungsi penyegaran UI serentak
        refreshUI();
        
    } catch (error) {
        console.error("Gagal memuat data dashboard:", error);
    }
}

// ==========================================
// MESIN WAKTU (FUNGSI PENYEGARAN UI INSTAN)
// ==========================================
function refreshUI() {
    // 1. Update teks keterangan di atas slider
    updateSliderLabel();
    // 2. Update urutan Leaderboard berdasarkan jam terpilih
    updateLeaderboard();
    // 3. Warnai ulang peta berdasarkan jam terpilih
    renderPetaWarna();
    // 4. Update angka di Kartu Biru (tanpa men-scroll layar atau narik grafik baru)
    pilihKota(kotaAktif, false);
}

// Terpicu setiap kali tuas slider HTML digeser
function handleSliderChange(val) {
    currentHourIndex = parseInt(val);
    refreshUI(); // Segarkan semua elemen secara real-time!
}

function updateSliderLabel() {
    const labelEl = document.getElementById('slider-label');
    if(!labelEl || allCitiesData.length === 0) return;
    
    // Ambil sampel waktu dari kota pertama untuk label
    const sampelWaktu = allCitiesData[0].timeline[currentHourIndex];
    
    if(sampelWaktu) {
        let teks = `${sampelWaktu.hari} - ${sampelWaktu.jam} WIB `;
        if(currentHourIndex === 0) teks += `<span class="badge bg-primary ms-2">Sekarang</span>`;
        else teks += `<span class="badge bg-secondary ms-2">+${currentHourIndex} Jam</span>`;
        
        labelEl.innerHTML = teks;
    }
}

// ==========================================
// SMART SEARCH BAR
// ==========================================
function populateSearch(data) {
    const datalist = document.getElementById('daftar-kota');
    datalist.innerHTML = ''; 
    
    data.forEach(item => {
        const option = document.createElement('option');
        option.value = item.kota;
        datalist.appendChild(option);
    });

    const searchInput = document.getElementById('city-search');
    searchInput.addEventListener('input', (e) => {
        const selected = e.target.value;
        const kotaCocok = data.find(d => d.kota.toLowerCase() === selected.toLowerCase());
        
        if (kotaCocok) {
            pilihKota(kotaCocok.kota, true); // true = scroll & load grafik
            searchInput.value = ''; 
            searchInput.blur(); 
        }
    });
}

// ==========================================
// LEADERBOARD KOTA (DINAMIS BERDASARKAN JAM)
// ==========================================
function updateLeaderboard() {
    // Ekstrak data spesifik HANYA untuk jam yang sedang dipilih di slider
    const currentData = allCitiesData.map(d => {
        const timeData = d.timeline[currentHourIndex];
        return {
            kota: d.kota,
            nilai_ispu: timeData ? timeData.nilai_ispu : 0,
            kategori: timeData ? timeData.kategori : "Menunggu"
        };
    });

    const sortedTerburuk = [...currentData].sort((a, b) => b.nilai_ispu - a.nilai_ispu).slice(0, 5);
    const sortedTerbersih = [...currentData].sort((a, b) => a.nilai_ispu - b.nilai_ispu).slice(0, 5);

const renderList = (arrayData, containerId) => {
    const container = document.getElementById(containerId);
    if(!container) return;
    container.innerHTML = '';
    arrayData.forEach(item => {
        const color = getStatusColor(item.kategori);
        // Hitung persentase bar (anggap batas atas aman ISPU adalah 150)
        const percent = Math.min((item.nilai_ispu / 150) * 100, 100);
        
        container.innerHTML += `
            <li class="list-group-item d-flex flex-column align-items-stretch" 
                style="cursor: pointer; transition: 0.3s; border-radius: 8px; margin-bottom: 4px;" 
                onmouseover="this.style.backgroundColor='#f1f3f5'" 
                onmouseout="this.style.backgroundColor='transparent'"
                onclick="pilihKota('${item.kota}', true)">
                
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span class="fw-semibold" style="font-size: 0.9rem;">${item.kota}</span>
                    <span class="badge rounded-pill text-white" style="background-color: ${color}; font-size: 0.75rem; padding: 0.25rem 0.6rem;">
                        ${item.nilai_ispu}
                    </span>
                </div>
                
                <!-- Progress Bar Kualitas Udara Mini -->
                <div class="progress" style="height: 5px; background: rgba(0,0,0,0.06); border-radius: 50px;">
                    <div class="progress-bar" style="width: ${percent}%; background-color: ${color}; border-radius: 50px; transition: width 0.6s ease;"></div>
                </div>
            </li>
        `;
    });
};

    renderList(sortedTerburuk, 'list-terburuk');
    renderList(sortedTerbersih, 'list-terbersih');
}

// ==========================================
// FUNGSI JEMBATAN KARTU BIRU
// ==========================================
function pilihKota(kota, scrollAndFetchGraph = true) {
    kotaAktif = kota;
    document.getElementById('selectedCityTitle').innerText = `Detail Wilayah: ${kota}`;
    
    document.getElementById('ispuValue').innerText = "...";
    document.getElementById('ispuStatus').innerText = "...";
    document.getElementById('kritisValue').innerText = "...";
    
    setTimeout(() => {
        let dataKotaIni = allCitiesData.find(d => d.kota === kota);
        
        if(dataKotaIni) {
            // TARIK DATA BERDASARKAN INDEKS JAM SLIDER
            let timeData = dataKotaIni.timeline[currentHourIndex]; 
            
            if(timeData) {
                document.getElementById('ispuValue').innerText = timeData.nilai_ispu || 0;
                document.getElementById('ispuStatus').innerText = timeData.kategori || "Menunggu Data";
                document.getElementById('kritisValue').innerText = timeData.parameter_kritis || "-";
                document.getElementById('statusCard').style.backgroundColor = getStatusColor(timeData.kategori);
            }
        }
    }, 150); 

    // Jika dipanggil dari klik Peta/Search/Leaderboard, tarik grafik tren & scroll.
    // Jika dipanggil oleh geseran Slider, JANGAN tarik grafik ulang agar tidak lag.
    if(scrollAndFetchGraph) {
        fetchIspuData(kota, filterHariAktif);
        document.getElementById('detail-view').scrollIntoView({ behavior: 'smooth' });
    }
}

// ==========================================
// PEMBERSIH NAMA EKSTREM (Sapu Jagat)
// ==========================================
function sanitizeName(name) {
    if (!name) return "";
    return String(name).toUpperCase()
        .replace(/KABUPATEN/g, '')
        .replace(/KOTA/g, '')
        .replace(/KAB\./g, '')
        .replace(/[^A-Z]/g, '') // Menghapus spasi dan simbol non-huruf
        .trim();
}

// ==========================================
// FITUR PETA CHOROPLETH (DINAMIS BERDASARKAN JAM)
// ==========================================
async function renderPetaWarna() {
    try {
        // Cache file jatim.json agar tidak perlu didownload berulang kali saat tuas digeser
        if (!jatimGeoJSON) {
            const response = await fetch('jatim.json');
            if (!response.ok) throw new Error("File jatim.json tidak ditemukan");
            jatimGeoJSON = await response.json();
        }

        // Hapus warna layer sebelumnya (mencegah bug menumpuk)
        if (geoJsonLayer) {
            map.removeLayer(geoJsonLayer);
        }

        geoJsonLayer = L.geoJSON(jatimGeoJSON, {
            style: function (feature) {
                let namaPetaBersih = sanitizeName(feature.properties.kabkot || "");
                let kotaDitemukan = allCitiesData.find(d => sanitizeName(d.kota) === namaPetaBersih);

                let warnaArea = '#cccccc'; // Default Abu-abu
                if (kotaDitemukan && kotaDitemukan.timeline[currentHourIndex]) {
                    warnaArea = getStatusColor(kotaDitemukan.timeline[currentHourIndex].kategori);
                }

                return {
                    fillColor: warnaArea,
                    weight: 1.5,
                    opacity: 1,
                    color: 'white', 
                    fillOpacity: 0.8
                };
            },
            onEachFeature: function (feature, layer) {
                let namaPetaBersih = sanitizeName(feature.properties.kabkot || "");
                let kotaDitemukan = allCitiesData.find(d => sanitizeName(d.kota) === namaPetaBersih);
                
                if (kotaDitemukan && kotaDitemukan.timeline[currentHourIndex]) {
                    let timeData = kotaDitemukan.timeline[currentHourIndex];
                    layer.bindPopup(`<b>${kotaDitemukan.kota}</b><br>ISPU: ${timeData.nilai_ispu} (${timeData.kategori})`);
                    layer.on('click', () => pilihKota(kotaDitemukan.kota, true));
                }
            }
        }).addTo(map);

    } catch(e) {
        console.error("Gagal sinkronisasi warna peta:", e);
    }
}

// ==========================================
// FUNGSI API GRAFIK 
// ==========================================
async function fetchIspuData(kota, jumlahHari) {
    try {
        filterHariAktif = jumlahHari;
        const urlSafeKota = encodeURIComponent(kota);
        const response = await fetch(`http://127.0.0.1:5000/api/ispu/${urlSafeKota}?days=${jumlahHari}`);
        
        if (!response.ok) throw new Error("Data grafik belum tersedia.");

        const result = await response.json();
        updateChart(result.grafik, kota);

    } catch (error) {
        console.error("Gagal menarik grafik:", error);
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
    initMap(); 
    await loadDashboard(); 
    pilihKota('Surabaya', true); 
};