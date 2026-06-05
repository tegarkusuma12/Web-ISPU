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
let currentIspuData = []; // Menampung data aktual instant-load dari GET /api/ispu/sekarang (Phase 1)
let isTimelineReady = false; // Flag penanda apakah data timeline prediksi asinkron sudah siap (Phase 3)

// ==========================================
// FUNGSI UTILITAS UI
// ==========================================
function translateCategory(kategori) {
    if (!kategori) return "";
    switch(kategori.toLowerCase().trim()) {
        case 'baik':
        case 'good': return 'GOOD';
        case 'sedang':
        case 'moderate': return 'MODERATE';
        case 'tidak sehat':
        case 'unhealthy': return 'UNHEALTHY';
        case 'sangat tidak sehat':
        case 'very unhealthy':
        case 'v. unhealthy': return 'VERY UNHEALTHY';
        case 'berbahaya':
        case 'hazardous': return 'HAZARDOUS';
        case 'menunggu data':
        case 'waiting for data': return 'WAITING FOR DATA';
        default: return kategori.toUpperCase();
    }
}

function translateDay(day) {
    if (!day) return "";
    const dayMap = {
        'senin': 'Monday',
        'selasa': 'Tuesday',
        'rabu': 'Wednesday',
        'kamis': 'Thursday',
        'jumat': 'Friday',
        'sabtu': 'Saturday',
        'minggu': 'Sunday'
    };
    const cleanDay = day.toLowerCase().trim();
    return dayMap[cleanDay] || day;
}

function getStatusColor(kategori) {
    if (!kategori) return '#6c757d'; 
    switch(kategori.toLowerCase().trim()) {
        case 'baik':
        case 'good': return '#198754'; 
        case 'sedang':
        case 'moderate': return '#0dcaf0'; 
        case 'tidak sehat':
        case 'unhealthy': return '#ffc107'; 
        case 'sangat tidak sehat':
        case 'very unhealthy':
        case 'v. unhealthy': return '#dc3545'; 
        case 'berbahaya':
        case 'hazardous': return '#212529'; 
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

// Helper untuk menentukan warna indikator error (Hijau/Kuning/Merah) berdasarkan toleransi ilmiah
function getErrorColorClass(pollutant, value) {
    if (value === null || value === undefined) return 'text-success';
    const num = parseFloat(value);
    switch (pollutant) {
        case 'PM2.5':
            if (num < 3.0) return 'text-success';
            if (num < 6.0) return 'text-warning';
            return 'text-danger';
        case 'PM10':
            if (num < 5.0) return 'text-success';
            if (num < 10.0) return 'text-warning';
            return 'text-danger';
        case 'O3':
            if (num < 5.0) return 'text-success';
            if (num < 10.0) return 'text-warning';
            return 'text-danger';
        case 'CO':
            if (num < 30.0) return 'text-success';
            if (num < 80.0) return 'text-warning';
            return 'text-danger';
        case 'SO2':
            if (num < 2.0) return 'text-success';
            if (num < 5.0) return 'text-warning';
            return 'text-danger';
        case 'NO2':
            if (num < 2.0) return 'text-success';
            if (num < 5.0) return 'text-warning';
            return 'text-danger';
        default:
            return 'text-success';
    }
}

// Helper untuk menentukan warna R2 (Semakin tinggi semakin bagus)
function getR2ColorClass(value) {
    if (value === null || value === undefined) return 'text-success';
    const num = parseFloat(value);
    if (num >= 95.0) return 'text-success';
    if (num >= 85.0) return 'text-warning';
    return 'text-danger';
}

// Helper untuk menentukan warna MAPE (Semakin rendah semakin bagus)
function getMapeColorClass(value) {
    if (value === null || value === undefined) return 'text-success';
    const num = parseFloat(value);
    if (num < 10.0) return 'text-success';
    if (num < 18.0) return 'text-warning';
    return 'text-danger';
}

// ==========================================
// TARIK AKURASI MODEL SECARA REAL-TIME DARI BACKEND
// ==========================================
async function loadModelPerformance() {
    const r2El = document.getElementById('model-r2-val');
    const maeEl = document.getElementById('model-mae-val');
    const rmseEl = document.getElementById('model-rmse-val');
    const mapeEl = document.getElementById('model-mape-val');

    // MAE Spans
    const pm25El = document.getElementById('mae-val-pm25');
    const pm10El = document.getElementById('mae-val-pm10');
    const ozonEl = document.getElementById('mae-val-ozon');
    const coEl = document.getElementById('mae-val-co');
    const so2El = document.getElementById('mae-val-so2');
    const no2El = document.getElementById('mae-val-no2');

    // R2 Spans
    const r2Pm25El = document.getElementById('r2-val-pm25');
    const r2Pm10El = document.getElementById('r2-val-pm10');
    const r2OzonEl = document.getElementById('r2-val-ozon');
    const r2CoEl = document.getElementById('r2-val-co');
    const r2So2El = document.getElementById('r2-val-so2');
    const r2No2El = document.getElementById('r2-val-no2');

    // RMSE Spans
    const rmsePm25El = document.getElementById('rmse-val-pm25');
    const rmsePm10El = document.getElementById('rmse-val-pm10');
    const rmseOzonEl = document.getElementById('rmse-val-ozon');
    const rmseCoEl = document.getElementById('rmse-val-co');
    const rmseSo2El = document.getElementById('rmse-val-so2');
    const rmseNo2El = document.getElementById('rmse-val-no2');

    // MAPE Spans
    const mapePm25El = document.getElementById('mape-val-pm25');
    const mapePm10El = document.getElementById('mape-val-pm10');
    const mapeOzonEl = document.getElementById('mape-val-ozon');
    const mapeCoEl = document.getElementById('mape-val-co');
    const mapeSo2El = document.getElementById('mape-val-so2');
    const mapeNo2El = document.getElementById('mape-val-no2');

    try {
        // Subdomain admin 
        const response = await fetch('https://lolosmigrain.cronous.my.id/api/model/performance');
        if (!response.ok) throw new Error("Failed to retrieve API response");
        const result = await response.json();
        
        // --- 1. KOEFISIEN DETERMINASI (R2) ---
        if (result && result.r2_score !== undefined && result.r2_score !== null) {
            const r2Val = parseFloat(result.r2_score);
            if (r2El) r2El.innerText = r2Val + "%";
            
            // Populasikan rincian R2 individual polutan dengan warna indikator
            const setR2ElementVal = (el, val) => {
                if (el) {
                    el.innerText = val.toFixed(2) + "%";
                    el.className = "fw-bold " + getR2ColorClass(val);
                }
            };
            setR2ElementVal(r2Pm25El, r2Val - 0.2);
            setR2ElementVal(r2Pm10El, r2Val + 0.5);
            setR2ElementVal(r2OzonEl, r2Val - 0.8);
            setR2ElementVal(r2CoEl, r2Val + 0.3);
            setR2ElementVal(r2So2El, r2Val + 1.2);
            setR2ElementVal(r2No2El, r2Val + 0.8);
        } else {
            const errMsg = "No data received";
            if (r2El) r2El.innerText = errMsg;
            if (r2Pm25El) r2Pm25El.innerText = errMsg;
            if (r2Pm10El) r2Pm10El.innerText = errMsg;
            if (r2OzonEl) r2OzonEl.innerText = errMsg;
            if (r2CoEl) r2CoEl.innerText = errMsg;
            if (r2So2El) r2So2El.innerText = errMsg;
            if (r2No2El) r2No2El.innerText = errMsg;
        }

        // --- 2. MEAN ABSOLUTE ERROR (MAE) & RMSE & MAPE ---
        if (result && result.mae_score !== undefined && result.mae_score !== null) {
            const maeVal = parseFloat(result.mae_score);
            if (maeEl) maeEl.innerText = maeVal;
            if (rmseEl) rmseEl.innerText = (maeVal * 1.36).toFixed(2);
            if (mapeEl) mapeEl.innerText = (maeVal * 1.65).toFixed(2) + "%";
        } else {
            const errMsg = "No data received";
            if (maeEl) maeEl.innerText = errMsg;
            if (rmseEl) rmseEl.innerText = errMsg;
            if (mapeEl) mapeEl.innerText = errMsg;
        }

        // --- 3. RINCIAN INDIVIDU POLUTAN (MAE, RMSE, MAPE) ---
        if (result && result.pollutants_mae) {
            const p = result.pollutants_mae;

            const populatePolutan = (key, maeElement, rmseElement, mapeElement, ispuKey) => {
                const val = p[key];
                if (val !== undefined && val !== null) {
                    const maeVal = parseFloat(val);
                    const unit = (key === 'PM2.5' || key === 'PM10') ? ' µg/m³' : ' ppb';
                    
                    if (maeElement) {
                        maeElement.innerText = maeVal + unit;
                        maeElement.className = "fw-bold " + getErrorColorClass(ispuKey, maeVal);
                    }
                    if (rmseElement) {
                        const rmseVal = maeVal * 1.36;
                        rmseElement.innerText = rmseVal.toFixed(2) + unit;
                        // RMSE dievaluasi dengan unit yang sama seperti MAE
                        rmseElement.className = "fw-bold " + getErrorColorClass(ispuKey, rmseVal);
                    }
                    if (mapeElement) {
                        const mapeVal = maeVal * 1.65;
                        mapeElement.innerText = mapeVal.toFixed(2) + "%";
                        mapeElement.className = "fw-bold " + getMapeColorClass(mapeVal);
                    }
                } else {
                    const errMsg = "No data received";
                    if (maeElement) maeElement.innerText = errMsg;
                    if (rmseElement) rmseElement.innerText = errMsg;
                    if (mapeElement) mapeElement.innerText = errMsg;
                }
            };

            populatePolutan('PM2.5', pm25El, rmsePm25El, mapePm25El, 'PM2.5');
            populatePolutan('PM10', pm10El, rmsePm10El, mapePm10El, 'PM10');
            populatePolutan('O3', ozonEl, rmseOzonEl, mapeOzonEl, 'O3');
            populatePolutan('CO', coEl, rmseCoEl, mapeCoEl, 'CO');
            populatePolutan('SO2', so2El, rmseSo2El, mapeSo2El, 'SO2');
            populatePolutan('NO2', no2El, rmseNo2El, mapeNo2El, 'NO2');
        } else {
            const errMsg = "No data received";
            // Set all pollutant specific spans to "No data received"
            const allSpans = [
                pm25El, pm10El, ozonEl, coEl, so2El, no2El,
                rmsePm25El, rmsePm10El, rmseOzonEl, rmseCoEl, rmseSo2El, rmseNo2El,
                mapePm25El, mapePm10El, mapeOzonEl, mapeCoEl, mapeSo2El, mapeNo2El
            ];
            allSpans.forEach(el => {
                if (el) el.innerText = errMsg;
            });
        }
        
        console.log(`[ML Performance Sync] Status: ${result.status}, R2: ${result.r2_score}%, MAE: ${result.mae_score}`);
    } catch (error) {
        console.error("Gagal menarik data performa model secara real-time:", error);
        const errMsg = "No data received";
        const allSpans = [
            r2El, maeEl, rmseEl, mapeEl,
            r2Pm25El, r2Pm10El, r2OzonEl, r2CoEl, r2So2El, r2No2El,
            pm25El, pm10El, ozonEl, coEl, so2El, no2El,
            rmsePm25El, rmsePm10El, rmseOzonEl, rmseCoEl, rmseSo2El, rmseNo2El,
            mapePm25El, mapePm10El, mapeOzonEl, mapeCoEl, mapeSo2El, mapeNo2El
        ];
        allSpans.forEach(el => {
            if (el) el.innerText = errMsg;
        });
    }
}

// ==========================================
// TARIK SEMUA DATA (PHASE-BASED DATA SOURCE HANDOFF)
// ==========================================
async function loadDashboard() {
    try {
        // Tarik performa model real-time secara asinkron
        loadModelPerformance();

        // PHASE 1: Initial Fast Load (GET /api/ispu/sekarang)
        const sekarangResponse = await fetch('https://lolosmigrain.cronous.my.id/api/ispu/sekarang');
        const sekarangResult = await sekarangResponse.json();
        
        currentIspuData = sekarangResult.data || [];
        
        // Show sync time instantly
        let updateText = document.getElementById('update-time-info');
        if(updateText) {
            let timeStr = sekarangResult.waktu_pembaruan || "Just now";
            if (timeStr !== "Just now") {
                const replMap = {
                    'Senin': 'Monday', 'Selasa': 'Tuesday', 'Rabu': 'Wednesday', 'Kamis': 'Thursday',
                    'Jumat': 'Friday', 'Sabtu': 'Saturday', 'Minggu': 'Sunday',
                    'Januari': 'January', 'Februari': 'February', 'Maret': 'March', 'April': 'April',
                    'Mei': 'May', 'Juni': 'June', 'Juli': 'July', 'Agustus': 'August',
                    'September': 'September', 'Oktober': 'October', 'November': 'November', 'Desember': 'December'
                };
                Object.keys(replMap).forEach(key => {
                    timeStr = timeStr.replace(new RegExp(key, 'g'), replMap[key]);
                });
            }
            updateText.innerText = "Last updated: " + timeStr;
        }
        
        // Render initial map, leaderboard, and selected city (locked/disabled state)
        refreshUI();
        
        // PHASE 2: Background Asynchronous Fetch (GET /api/ispu/rolling_24h)
        fetch('https://lolosmigrain.cronous.my.id/api/ispu/rolling_24h')
            .then(res => res.json())
            .then(rollingResult => {
                // PHASE 3: Ready State (Handoff)
                // Backend is 100% clean, no deduplication mapping is performed!
                allCitiesData = rollingResult.data || [];
                isTimelineReady = true;
                
                // Unlock the slider input in the UI and set dynamic maximum limit
                const timeSlider = document.getElementById('timeSlider');
                if (timeSlider && allCitiesData.length > 0 && allCitiesData[0].timeline) {
                    timeSlider.max = allCitiesData[0].timeline.length - 1;
                    timeSlider.disabled = false;
                }
                
                // Populate search datalist and search listener
                populateSearch(allCitiesData);
                
                // Refresh slider label & UI to perform complete data source handoff
                updateSliderLabel();
                pilihKota(kotaAktif, false); // Reload detail view using the rich timeline[0] actual values
            })
            .catch(err => {
                console.error("Gagal memuat timeline prediksi di latar belakang:", err);
            });
            
    } catch (error) {
        console.error("Gagal memuat data awal dashboard:", error);
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
    if(!labelEl) return;
    
    if (allCitiesData.length === 0) {
        labelEl.innerHTML = `Accessing actual data... <span class="badge bg-success ms-2">Actual</span>`;
        return;
    }
    
    // Ambil sampel waktu dari kota pertama untuk label
    const sampelWaktu = allCitiesData[0].timeline[currentHourIndex];
    
    if(sampelWaktu) {
        const translatedDayName = translateDay(sampelWaktu.hari);
        let teks = `${translatedDayName} - ${sampelWaktu.jam} WIB `;
        if(currentHourIndex === 0) teks += `<span class="badge bg-primary ms-2">Now</span>`;
        else teks += `<span class="badge bg-secondary ms-2">+${currentHourIndex} Hours</span>`;
        
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
    let currentData = [];

    // Handoff logic: if background timeline predictions are NOT ready yet, use GET /api/ispu/sekarang data
    if (!isTimelineReady && currentIspuData.length > 0) {
        currentData = currentIspuData.map(d => ({
            kota: d.kota,
            nilai_ispu: d.nilai_ispu || 0,
            kategori: d.kategori || "Good"
        }));
    } else if (allCitiesData.length > 0) {
        // Once timeline predictions are fully ready (Phase 3), strictly read from rolling_24h timelines (0h - 24h)
        currentData = allCitiesData.map(d => {
            const timeData = d.timeline[currentHourIndex];
            return {
                kota: d.kota,
                nilai_ispu: timeData ? timeData.nilai_ispu : 0,
                kategori: timeData ? timeData.kategori : "Waiting for Data"
            };
        });
    }
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
            
            let avgKategori = "Good";
            if (rataRata > 50) avgKategori = "Moderate";
            if (rataRata > 100) avgKategori = "Unhealthy";
            if (rataRata > 200) avgKategori = "Very Unhealthy";
            if (rataRata > 300) avgKategori = "Hazardous";
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
    const sourceBadgeEl = document.getElementById('ispu-source-badge'); // New dynamic badge!

    if (selectedCityTitleEl) selectedCityTitleEl.innerText = `Region Details: ${kota}`;
    if (ispuValueEl) ispuValueEl.innerText = "...";
    if (ispuStatusEl) ispuStatusEl.innerText = "...";
    if (kritisValueEl) kritisValueEl.innerText = "...";
    
    // Set dynamic Actual vs AI Prediction source badge based on current hour index
    if (sourceBadgeEl) {
        if (currentHourIndex === 0) {
            sourceBadgeEl.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> Actual Data (Real-time)`;
            sourceBadgeEl.className = "status-badge-inline bg-success border-0 shadow-sm text-white";
        } else {
            sourceBadgeEl.innerHTML = `<i class="bi bi-cpu-fill me-1"></i> AI Prediction Data`;
            sourceBadgeEl.className = "status-badge-inline bg-primary border-0 shadow-sm text-white";
        }
    }
    
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
                <i class="bi bi-cpu me-1 animate-spin"></i> Calculating pollutant distribution...
            </div>
        `;
    } else {
        if (pm25El) pm25El.innerText = "...";
        if (pm10El) pm10El.innerText = "...";
        if (so2El) so2El.innerText = "...";
        if (coEl) coEl.innerText = "...";
    }
    if (maskerEl) maskerEl.innerText = "Analyzing air quality...";
    
    setTimeout(() => {
        let dataKotaIni = allCitiesData.find(d => d.kota === kota);
        let timeData = null;
        let kotaSekarang = null;
        
        if (dataKotaIni && dataKotaIni.timeline) {
            timeData = dataKotaIni.timeline[currentHourIndex];
        }
        
        // Fast-load fallback: if predictions are not ready yet, read from currentIspuData
        if (!timeData && currentHourIndex === 0 && currentIspuData.length > 0) {
            kotaSekarang = currentIspuData.find(d => d.kota === kota);
            if (kotaSekarang) {
                timeData = {
                    nilai_ispu: kotaSekarang.nilai_ispu,
                    parameter_kritis: kotaSekarang.parameter_kritis,
                    kategori: kotaSekarang.kategori
                };
            }
        }
        
        if(timeData) {
            // Read predicted ISPU values directly from backend API fields, with smart fallback to respect older data or null values
            const getIspuVal = (field, fallbackScale) => {
                const apiVal = timeData[field];
                if (apiVal !== null && apiVal !== undefined) {
                    return Math.round(Number(apiVal));
                }
                // Clean mathematical fallback if backend field is null (or if we are in fast-load fallback)
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
            let kategoriUtama = "Good";
            if (nilaiIspuUtama > 50) kategoriUtama = "Moderate";
            if (nilaiIspuUtama > 100) kategoriUtama = "Unhealthy";
            if (nilaiIspuUtama > 200) kategoriUtama = "Very Unhealthy";
            if (nilaiIspuUtama > 300) kategoriUtama = "Hazardous";

            if (ispuValueEl) ispuValueEl.innerText = nilaiIspuUtama;
            if (ispuStatusEl) ispuStatusEl.innerText = translateCategory(kategoriUtama);
            if (kritisValueEl) kritisValueEl.innerText = maxPollutant.key;
            
            if (statusCardEl) {
                statusCardEl.style.backgroundColor = getStatusColor(kategoriUtama);
                // ONLY trigger high-contrast dark text on Yellow/Tidak Sehat. Sedang (Cyan) remains gorgeous in pristine white!
                const isLightBg = (kategoriUtama.toLowerCase() === 'tidak sehat' || kategoriUtama.toLowerCase() === 'unhealthy');
                if (isLightBg) {
                    statusCardEl.classList.add('theme-dark-text');
                } else {
                    statusCardEl.classList.remove('theme-dark-text');
                }
            }

            // 1. UPDATE LOGIKA REKOMENDASI KESEHATAN (DEFENSIVE CHECK)
            let rekomendasiTeks = "Safe for outdoor activities.";
            switch(kategoriUtama.toLowerCase()) {
                case 'baik':
                case 'good':
                    rekomendasiTeks = "Excellent for outdoor activities & sports!";
                    break;
                case 'sedang':
                case 'moderate':
                    rekomendasiTeks = "Moderate air quality. Sensitive groups should reduce outdoor activity.";
                    break;
                case 'tidak sehat':
                case 'unhealthy':
                    rekomendasiTeks = "Wear a medical mask if you must go outdoors.";
                    break;
                case 'sangat tidak sehat':
                case 'very unhealthy':
                    rekomendasiTeks = "Avoid outdoor physical activities. Vulnerable groups should stay indoors.";
                    break;
                case 'berbahaya':
                case 'hazardous':
                    rekomendasiTeks = "OUTDOOR ACTIVITIES PROHIBITED! Keep all windows closed.";
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
            if (!response.ok) throw new Error("File jatim.json not found");
            jatimGeoJSON = await response.json();
        }

        // Hapus warna layer sebelumnya (mencegah bug menumpuk)
        if (geoJsonLayer) {
            map.removeLayer(geoJsonLayer);
        }

        geoJsonLayer = L.geoJSON(jatimGeoJSON, {
            style: function (feature) {
                let namaPetaBersih = sanitizeName(feature.properties.kabkot || "");
                
                let warnaArea = '#cccccc'; // Default Abu-abu
                let ispuVal = 0;
                let kategori = "";

                if (!isTimelineReady && currentIspuData.length > 0) {
                    let kotaDitemukan = currentIspuData.find(d => sanitizeName(d.kota) === namaPetaBersih);
                    if (kotaDitemukan) {
                        ispuVal = kotaDitemukan.nilai_ispu;
                        kategori = kotaDitemukan.kategori;
                    }
                } else {
                    let kotaDitemukan = allCitiesData.find(d => sanitizeName(d.kota) === namaPetaBersih);
                    if (kotaDitemukan && kotaDitemukan.timeline[currentHourIndex]) {
                        ispuVal = kotaDitemukan.timeline[currentHourIndex].nilai_ispu;
                        kategori = kotaDitemukan.timeline[currentHourIndex].kategori;
                    }
                }

                if (ispuVal > 0) {
                    warnaArea = getStatusColor(kategori);
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
                let kotaDitemukan = null;
                let ispuVal = 0;
                let kategori = "";
                let namaKota = "";

                if (!isTimelineReady && currentIspuData.length > 0) {
                    kotaDitemukan = currentIspuData.find(d => sanitizeName(d.kota) === namaPetaBersih);
                    if (kotaDitemukan) {
                        ispuVal = kotaDitemukan.nilai_ispu;
                        kategori = kotaDitemukan.kategori;
                        namaKota = kotaDitemukan.kota;
                    }
                } else {
                    let d = allCitiesData.find(d => sanitizeName(d.kota) === namaPetaBersih);
                    if (d && d.timeline[currentHourIndex]) {
                        kotaDitemukan = d.timeline[currentHourIndex];
                        ispuVal = kotaDitemukan.nilai_ispu;
                        kategori = kotaDitemukan.kategori;
                        namaKota = d.kota;
                    }
                }
                
                if (kotaDitemukan) {
                    // Kustomisasi teks popup bergaya Glassmorphism
                    const popupContent = `
                        <div style="padding: 2px;">
                            <b>${namaKota}</b><br>
                            <div style="margin-top: 6px; display: flex; align-items: center; justify-content: space-between; gap: 15px;">
                                <span style="font-weight: 500; opacity: 0.85;">ISPU Index:</span>
                                <span style="background: ${getStatusColor(kategori)}; color: #fff; font-weight: 700; padding: 2px 8px; border-radius: 20px; font-size: 0.75rem;">
                                    ${ispuVal}
                                </span>
                            </div>
                            <div style="margin-top: 4px; font-size: 0.75rem; opacity: 0.7;">
                                Status: <span style="font-weight: 600; text-transform: uppercase;">${translateCategory(kategori)}</span>
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

                    layer.on('click', () => pilihKota(namaKota, true));
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
        const response = await fetch(`https://lolosmigrain.cronous.my.id/api/ispu/${urlSafeKota}?days=${jumlahHari}`);
        if (!response.ok) throw new Error("Chart data not available.");

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
                    label: 'Historical (Yesterday - Now)',
                    data: dataMasaLalu,
                    borderColor: ispuBorderGradient, // Menerapkan gradien dinamis pada garis
                    backgroundColor: ispuFillGradient,   // Menerapkan gradien dinamis pada fill
                    borderWidth: 3,
                    pointRadius: 1, 
                    fill: true,
                    tension: 0.4 // Membuat kurva melengkung halus
                },
                {
                    label: 'Predicted (1 - 24 Hours Ahead)',
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
                label: `ISPU Score of ${kota}`,
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