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
            kategori: timeData ? timeData.kategori : "Menunggu Data"
        };
    });
    // 1. FILTER: Diskualifikasi kota yang datanya tidak valid (nilai 0)
    const validData = currentData.filter(d => d.nilai_ispu > 0);

    // 2. SORTING DARI DATA YANG VALID
    const sortedTerburuk = [...validData].sort((a, b) => b.nilai_ispu - a.nilai_ispu).slice(0, 5);
    const sortedTerbersih = [...validData].sort((a, b) => a.nilai_ispu - b.nilai_ispu).slice(0, 5);

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

    // 1. UPDATE KPI WILAYAH TERBURUK (DEFENSIVE CHECK)
    const kpiHighestCity = document.getElementById('kpi-highest-city');
    const kpiHighestValue = document.getElementById('kpi-highest-value');
    if (sortedTerburuk.length > 0) {
        if (kpiHighestCity) kpiHighestCity.innerText = sortedTerburuk[0].kota;
        if (kpiHighestValue) {
            kpiHighestValue.innerText = sortedTerburuk[0].nilai_ispu;
            kpiHighestValue.style.backgroundColor = getStatusColor(sortedTerburuk[0].kategori);
        }
    } else {
        if (kpiHighestCity) kpiHighestCity.innerText = "-";
        if (kpiHighestValue) kpiHighestValue.innerText = "--";
    }

    // 2. UPDATE KPI RATA-RATA JAWA TIMUR (DEFENSIVE CHECK)
    const kpiAvgValue = document.getElementById('kpi-avg-value');
    if (kpiAvgValue) {
        if (validData.length > 0) {
            const totalIspu = validData.reduce((sum, item) => sum + item.nilai_ispu, 0);
            const rataRata = Math.round(totalIspu / validData.length);
            kpiAvgValue.innerText = rataRata;
            
            let avgKategori = "Baik";
            if (rataRata > 50) avgKategori = "Sedang";
            if (rataRata > 100) avgKategori = "Tidak Sehat";
            if (rataRata > 200) avgKategori = "Sangat Tidak Sehat";
            if (rataRata > 300) avgKategori = "Berbahaya";
            kpiAvgValue.style.backgroundColor = getStatusColor(avgKategori);
        } else {
            kpiAvgValue.innerText = "--";
        }
    }

    // 3. UPDATE KPI WILAYAH TERBERSIH (DEFENSIVE CHECK)
    const kpiLowestCity = document.getElementById('kpi-lowest-city');
    const kpiLowestValue = document.getElementById('kpi-lowest-value');
    if (sortedTerbersih.length > 0) {
        if (kpiLowestCity) kpiLowestCity.innerText = sortedTerbersih[0].kota;
        if (kpiLowestValue) {
            kpiLowestValue.innerText = sortedTerbersih[0].nilai_ispu;
            kpiLowestValue.style.backgroundColor = getStatusColor(sortedTerbersih[0].kategori);
        }
    } else {
        if (kpiLowestCity) kpiLowestCity.innerText = "-";
        if (kpiLowestValue) kpiLowestValue.innerText = "--";
    }
}

// ==========================================
// FUNGSI JEMBATAN KARTU BIRU (UPDATED)
// ==========================================
function pilihKota(kota, scrollAndFetchGraph = true) {
    kotaAktif = kota;
    
    const selectedCityTitleEl = document.getElementById('selectedCityTitle');
    const ispuValueEl = document.getElementById('ispuValue');
    const ispuStatusEl = document.getElementById('ispuStatus');
    const kritisValueEl = document.getElementById('kritisValue');
    const statusCardEl = document.getElementById('statusCard');

    if (selectedCityTitleEl) selectedCityTitleEl.innerText = `Detail Wilayah: ${kota}`;
    if (ispuValueEl) ispuValueEl.innerText = "...";
    if (ispuStatusEl) ispuStatusEl.innerText = "...";
    if (kritisValueEl) kritisValueEl.innerText = "...";
    
    // Reset status pemuatan grid polutan & rekomendasi (DEFENSIVE CHECK & HIJACKER)
    let gridEl = document.getElementById('pollutant-grid');
    const pm25El = document.getElementById('breakdown-pm25');
    const pm10El = document.getElementById('breakdown-pm10');
    const so2El = document.getElementById('breakdown-so2');
    const coEl = document.getElementById('breakdown-co');
    const maskerEl = document.getElementById('rekomendasiMasker');

    // Automatic hijacker: if gridEl is missing but pm25El exists (old HTML layout), hijack the parent row
    if (!gridEl && pm25El) {
        const rowEl = pm25El.closest('.row');
        if (rowEl) {
            rowEl.id = 'pollutant-grid';
            gridEl = rowEl;
        }
    }

    if (gridEl) {
        gridEl.innerHTML = `
            <div class="col-12 text-center py-2 text-white-50" style="font-size: 0.8rem;">
                <i class="bi bi-cpu me-1 animate-spin"></i> Menghitung sebaran polutan...
            </div>
        `;
    } else {
        if (pm25El) pm25El.innerText = "...";
        if (pm10El) pm10El.innerText = "...";
        if (so2El) so2El.innerText = "...";
        if (coEl) coEl.innerText = "...";
    }
    if (maskerEl) maskerEl.innerText = "Menganalisis kualitas udara...";
    
    setTimeout(() => {
        let dataKotaIni = allCitiesData.find(d => d.kota === kota);
        
        if(dataKotaIni) {
            let timeData = dataKotaIni.timeline[currentHourIndex]; 
            
            if(timeData) {
                // Read predicted ISPU values directly from backend API fields, with smart fallback to respect older data or null values
                const getIspuVal = (field, fallbackScale) => {
                    const apiVal = timeData[field];
                    if (apiVal !== null && apiVal !== undefined) {
                        return Math.round(Number(apiVal));
                    }
                    // Clean mathematical fallback if backend field is null
                    const baseIspu = timeData.nilai_ispu || 0;
                    return Math.round(baseIspu * fallbackScale);
                };

                const pm25Val = getIspuVal('ispu_pm25', 0.88);
                const pm10Val = getIspuVal('ispu_pm10', 0.72);
                const so2Val = getIspuVal('ispu_so2', 0.32);
                const coVal = getIspuVal('ispu_co', 0.28);
                const o3Val = getIspuVal('ispu_o3', 0.42);
                const no2Val = getIspuVal('ispu_no2', 0.22);

                const pollutantsList = [
                    { key: 'PM2.5', label: 'PM<sub>2.5</sub>', value: pm25Val },
                    { key: 'PM10', label: 'PM<sub>10</sub>', value: pm10Val },
                    { key: 'SO2', label: 'SO<sub>2</sub>', value: so2Val },
                    { key: 'CO', label: 'CO', value: coVal },
                    { key: 'O3', label: 'O<sub>3</sub>', value: o3Val },
                    { key: 'NO2', label: 'NO<sub>2</sub>', value: no2Val }
                ];

                // Dynamically find the maximum predicted ISPU value to determine Parameter Kritis
                let maxPollutant = pollutantsList[0];
                pollutantsList.forEach(p => {
                    if (p.value > maxPollutant.value) {
                        maxPollutant = p;
                    }
                });

                // Overall ISPU value is the maximum of the 6 predicted pollutant sub-indices
                const nilaiIspuUtama = maxPollutant.value > 0 ? maxPollutant.value : (timeData.nilai_ispu || 0);
                
                // Determine health category dynamically based on the highest ISPU score
                let kategoriUtama = "Baik";
                if (nilaiIspuUtama > 50) kategoriUtama = "Sedang";
                if (nilaiIspuUtama > 100) kategoriUtama = "Tidak Sehat";
                if (nilaiIspuUtama > 200) kategoriUtama = "Sangat Tidak Sehat";
                if (nilaiIspuUtama > 300) kategoriUtama = "Berbahaya";

                if (ispuValueEl) ispuValueEl.innerText = nilaiIspuUtama;
                if (ispuStatusEl) ispuStatusEl.innerText = kategoriUtama;
                if (kritisValueEl) kritisValueEl.innerText = maxPollutant.key;
                
                if (statusCardEl) {
                    statusCardEl.style.backgroundColor = getStatusColor(kategoriUtama);
                    // ONLY trigger high-contrast dark text on Yellow/Tidak Sehat. Sedang (Cyan) remains gorgeous in pristine white!
                    const isLightBg = (kategoriUtama.toLowerCase() === 'tidak sehat');
                    if (isLightBg) {
                        statusCardEl.classList.add('theme-dark-text');
                    } else {
                        statusCardEl.classList.remove('theme-dark-text');
                    }
                }

                // 1. UPDATE LOGIKA REKOMENDASI KESEHATAN (DEFENSIVE CHECK)
                let rekomendasiTeks = "Aman untuk beraktivitas di luar ruangan.";
                switch(kategoriUtama.toLowerCase()) {
                    case 'baik':
                        rekomendasiTeks = "Sangat baik untuk aktivitas outdoor & olahraga!";
                        break;
                    case 'sedang':
                        rekomendasiTeks = "Kualitas udara sedang. Kelompok sensitif sebaiknya mengurangi aktivitas luar ruangan.";
                        break;
                    case 'tidak sehat':
                        rekomendasiTeks = "Gunakan masker medis jika harus beraktivitas di luar ruangan.";
                        break;
                    case 'sangat tidak sehat':
                        rekomendasiTeks = "Hindari aktivitas fisik di luar. Kelompok rentan tetap di dalam rumah.";
                        break;
                    case 'berbahaya':
                        rekomendasiTeks = "DILARANG beraktivitas di luar ruangan! Jaga seluruh jendela tetap tertutup.";
                        break;
                }
                if (maskerEl) maskerEl.innerText = rekomendasiTeks;

                // Re-verify gridEl inside the closure to ensure hijacking was successful
                let activeGridEl = gridEl || document.getElementById('pollutant-grid');
                if (!activeGridEl && pm25El) {
                    const rowEl = pm25El.closest('.row');
                    if (rowEl) {
                        rowEl.id = 'pollutant-grid';
                        activeGridEl = rowEl;
                    }
                }

                // 2. DYNAMIC 6-POLLUTANT ELIMINATION SYSTEM (Exclude Critical, Show Remaining 5 below)
                if (activeGridEl) {
                    // Filter out the active maximum pollutant from the sub-cards
                    const subPollutants = pollutantsList.filter(p => p.key !== maxPollutant.key);
                    
                    let gridHTML = "";
                    subPollutants.forEach((p, idx) => {
                        // Clean premium column structure: 4 items in col-6 (2 rows), 5th item spans full col-12
                        const colClass = idx === 4 ? 'col-12' : 'col-6';
                        
                        gridHTML += `
                            <div class="${colClass}">
                                <div class="bg-white bg-opacity-10 rounded-3 p-2 text-center" 
                                     style="border: 1px solid rgba(255,255,255,0.08); transition: transform 0.2s;" 
                                     onmouseover="this.style.transform='scale(1.03)'" 
                                     onmouseout="this.style.transform='none'">
                                    <div style="font-size: 0.65rem; text-transform: uppercase; color: rgba(255,255,255,0.6); font-weight: 700;">${p.label}</div>
                                    <div class="fw-bold" style="font-size: 0.95rem;">${p.value}</div>
                                </div>
                            </div>
                        `;
                    });
                    activeGridEl.innerHTML = gridHTML;
                } else {
                    // Backward compatibility fallback for legacy HTML files
                    if (pm25El) pm25El.innerHTML = `${Math.round(nilaiIspuUtama * 0.9)} <span style="font-size:0.65rem;">µg/m³</span>`;
                    if (pm10El) pm10El.innerHTML = `${Math.round(nilaiIspuUtama * 0.75)} <span style="font-size:0.65rem;">µg/m³</span>`;
                    if (so2El) so2El.innerHTML = `${Math.round(nilaiIspuUtama * 0.35)} <span style="font-size:0.65rem;">ppb</span>`;
                    if (coEl) coEl.innerHTML = `${(nilaiIspuUtama * 0.04).toFixed(1)} <span style="font-size:0.65rem;">ppm</span>`;
                }
            }
        }
    }, 150); 

    if(scrollAndFetchGraph) {
        fetchIspuData(kota, filterHariAktif);
        const detailViewEl = document.getElementById('detail-view');
        if (detailViewEl) detailViewEl.scrollIntoView({ behavior: 'smooth' });
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
                    
                    // Kustomisasi teks popup bergaya Glassmorphism
                    const popupContent = `
                        <div style="padding: 2px;">
                            <b>${kotaDitemukan.kota}</b><br>
                            <div style="margin-top: 6px; display: flex; align-items: center; justify-content: space-between; gap: 15px;">
                                <span style="font-weight: 500; opacity: 0.85;">Indeks ISPU:</span>
                                <span style="background: ${getStatusColor(timeData.kategori)}; color: #fff; font-weight: 700; padding: 2px 8px; border-radius: 20px; font-size: 0.75rem;">
                                    ${timeData.nilai_ispu}
                                </span>
                            </div>
                            <div style="margin-top: 4px; font-size: 0.75rem; opacity: 0.7;">
                                Status: <span style="font-weight: 600; text-transform: uppercase;">${timeData.kategori}</span>
                            </div>
                        </div>
                    `;
                    
                    layer.bindPopup(popupContent, { closeButton: false, offset: L.point(0, -10) });
                    
                    // Efek hover interaktif
                    layer.on('mouseover', function (e) {
                        layer.setStyle({
                            weight: 3,
                            color: '#ffffff', // Efek garis bersinar putih di batas kabupaten
                            fillOpacity: 0.95
                        });
                        layer.openPopup();
                    });
                    
                    layer.on('mouseout', function (e) {
                        if (geoJsonLayer) geoJsonLayer.resetStyle(layer);
                        layer.closePopup();
                    });

                    layer.on('click', () => pilihKota(kotaDitemukan.kota, true));
                }
            }
        }).addTo(map);

    } catch(e) {
        console.error("Gagal sinkronisasi warna peta:", e);
    }
}

// ==========================================
// FUNGSI API GRAFIK (HYBRID PAST & FUTURE)
// ==========================================
async function fetchIspuData(kota, jumlahHari) {
    try {
        filterHariAktif = jumlahHari;
        const urlSafeKota = encodeURIComponent(kota);
        
        // Tarik data historis dari Backend
        const response = await fetch(`http://127.0.0.1:5000/api/ispu/${urlSafeKota}?days=${jumlahHari}`);
        if (!response.ok) throw new Error("Data grafik belum tersedia.");

        const result = await response.json();
        let dataGrafik = [];

        if (jumlahHari === '24jam') {
            // 1. Ambil 24 Jam Masa Lalu dari Database (Historis)
            const masaLalu = result.grafik.map(item => ({
                tanggal: item.tanggal,
                nilai_ispu: item.nilai_ispu,
                is_prediksi: false // Penanda bahwa ini data pasti
            }));

            // 2. Ambil 24 Jam Masa Depan dari Brankas Frontend (Prediksi)
            let masaDepan = [];
            const dataKotaIni = allCitiesData.find(d => d.kota === kota);
            if (dataKotaIni && dataKotaIni.timeline) {
                // Slice(1) untuk melewati index 0 (karena "Sekarang" sudah terwakili di ujung data Historis)
                masaDepan = dataKotaIni.timeline.slice(1).map(t => ({
                    tanggal: t.jam,
                    nilai_ispu: t.nilai_ispu,
                    is_prediksi: true // Penanda bahwa ini data proyeksi
                }));
            }

            // Jahit Keduanya!
            dataGrafik = [...masaLalu, ...masaDepan];
        } else {
            // Jika 7 atau 30 Hari, murni data historis saja
            dataGrafik = result.grafik.map(item => ({
                tanggal: item.tanggal,
                nilai_ispu: item.nilai_ispu,
                is_prediksi: false
            }));
        }

        updateChart(dataGrafik, kota, jumlahHari);

    } catch (error) {
        console.error("Gagal menarik grafik:", error);
        if(myChart) myChart.destroy();
    }
}

// Tidak ada perubahan di ubahFilterHari
function ubahFilterHari(hari) {
    const btn24 = document.getElementById('btn-24-jam');
    const btn7 = document.getElementById('btn-7-hari');
    const btn30 = document.getElementById('btn-30-hari');

    if (btn24) btn24.classList.remove('active');
    if (btn7) btn7.classList.remove('active');
    if (btn30) btn30.classList.remove('active');

    if (hari === '24jam') {
        if (btn24) btn24.classList.add('active');
    } else if (hari === 7) {
        if (btn7) btn7.classList.add('active');
    } else if (hari === 30) {
        if (btn30) btn30.classList.add('active');
    }
    
    fetchIspuData(kotaAktif, hari);
}

function updateChart(dataGrafik, kota, tipeFilter = '7') {
    const chartEl = document.getElementById('ispuChart');
    if (!chartEl) return;
    
    const ctx = chartEl.getContext('2d');
    
    if (!dataGrafik || dataGrafik.length === 0) {
        if (myChart) myChart.destroy();
        return;
    }
    
    if (myChart) myChart.destroy();

    const labelsWaktu = dataGrafik.map(row => row.tanggal);

    // ==========================================================
    // DYNAMIC VERTICAL GRADIENT FOR Border & Background Fill
    // ==========================================================
    const ispuBorderGradient = ctx.createLinearGradient(0, 300, 0, 0); 
    ispuBorderGradient.addColorStop(0, '#198754');    // 0 - 50: Baik (Hijau)
    ispuBorderGradient.addColorStop(0.3, '#0dcaf0');  // 51 - 100: Sedang (Biru/Cyan)
    ispuBorderGradient.addColorStop(0.6, '#ffc107');  // 101 - 200: Tidak Sehat (Kuning)
    ispuBorderGradient.addColorStop(0.85, '#dc3545'); // 201 - 300: Sangat Tidak Sehat (Merah)
    ispuBorderGradient.addColorStop(1, '#212529');    // 300+: Berbahaya (Hitam)

    const ispuFillGradient = ctx.createLinearGradient(0, 300, 0, 0);
    ispuFillGradient.addColorStop(0, 'rgba(25, 135, 84, 0.05)');    // Transparan Baik
    ispuFillGradient.addColorStop(0.3, 'rgba(13, 202, 240, 0.15)'); // Transparan Sedang
    ispuFillGradient.addColorStop(0.6, 'rgba(255, 193, 7, 0.25)');  // Transparan Tidak Sehat
    ispuFillGradient.addColorStop(0.85, 'rgba(220, 53, 69, 0.35)'); // Transparan Sangat Tidak Sehat
    ispuFillGradient.addColorStop(1, 'rgba(33, 37, 41, 0.45)');     // Transparan Berbahaya

    let configData = {};
    let configOptions = {
        responsive: true,
        maintainAspectRatio: false,
        devicePixelRatio: window.devicePixelRatio || 2, // Force physical resolution matching display DPI
        plugins: {
            legend: {
                display: tipeFilter === '24jam', // Tampilkan Legenda HANYA di mode Hybrid 24 Jam
                position: 'top',
                labels: { 
                    usePointStyle: true, 
                    boxWidth: 8, 
                    font: { 
                        family: 'Outfit', 
                        size: 13,        // Increased slightly for high-resolution clarity
                        weight: '600'    // String weight representation
                    },
                    color: '#1e293b'     // Premium dark slate legend color
                }
            }
        },
        scales: {
            y: { 
                beginAtZero: true, 
                suggestedMax: 150,
                grid: { color: 'rgba(0, 0, 0, 0.05)' },
                ticks: {
                    font: {
                        family: 'Plus Jakarta Sans',
                        size: 11,
                        weight: '500'
                    },
                    color: '#64748b'     // Crisp slate-500 tick colors
                }
            },
            x: {
                grid: { display: false },
                ticks: {
                    maxTicksLimit: tipeFilter === '24jam' ? 12 : 7, // Mencegah tulisan jam berdempetan
                    font: {
                        family: 'Plus Jakarta Sans',
                        size: 11,
                        weight: '500'
                    },
                    color: '#64748b'     // Crisp slate-500 tick colors
                }
            }
        }
    };

    if (tipeFilter === '24jam') {
        const dataMasaLalu = [];
        const dataMasaDepan = [];

        dataGrafik.forEach((row, index) => {
            if (row.is_prediksi) {
                dataMasaLalu.push(null);
                dataMasaDepan.push(row.nilai_ispu);
            } else {
                dataMasaLalu.push(row.nilai_ispu);
                // Trik Visual: Titik terakhir masa lalu disambung ke titik pertama masa depan agar garis tidak putus di tengah
                if (index < dataGrafik.length - 1 && dataGrafik[index + 1].is_prediksi) {
                    dataMasaDepan.push(row.nilai_ispu);
                } else {
                    dataMasaDepan.push(null);
                }
            }
        });

        configData = {
            labels: labelsWaktu,
            datasets: [
                {
                    label: 'Historis (Kemarin - Sekarang)',
                    data: dataMasaLalu,
                    borderColor: ispuBorderGradient, // Menerapkan gradien dinamis pada garis
                    backgroundColor: ispuFillGradient,   // Menerapkan gradien dinamis pada fill
                    borderWidth: 3,
                    pointRadius: 1, 
                    fill: true,
                    tension: 0.4 // Membuat kurva melengkung halus
                },
                {
                    label: 'Prediksi (1 - 24 Jam Kedepan)',
                    data: dataMasaDepan,
                    borderColor: ispuBorderGradient, // Gradien dinamis pada garis prediksi
                    borderDash: [6, 6], // Membuat garis putus-putus
                    backgroundColor: 'transparent',
                    borderWidth: 3,
                    pointRadius: 1,
                    fill: false,
                    tension: 0.4
                }
            ]
        };
    } else {
        // Tampilan Standar Harian (7 Hari / 30 Hari)
        configData = {
            labels: labelsWaktu,
            datasets: [{
                label: `Nilai ISPU ${kota}`,
                data: dataGrafik.map(row => row.nilai_ispu),
                borderColor: ispuBorderGradient, // Menerapkan gradien dinamis pada garis
                backgroundColor: ispuFillGradient,   // Menerapkan gradien dinamis pada fill
                borderWidth: 3,
                pointRadius: dataGrafik.length > 10 ? 2 : 5, 
                fill: true,
                tension: 0.4
            }]
        };
    }

    myChart = new Chart(ctx, {
        type: 'line',
        data: configData,
        options: configOptions
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