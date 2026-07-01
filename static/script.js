let currentLang = 'en';
let currentTaskId = null;
let statusInterval = null;

const uiDictionary = {
    en: {
        appName: "VortexDL Pro",
        appSubtitle: "Premium Video & Audio Extractor for YouTube & TikTok",
        langName: "العربية",
        fetchBtn: "Analyze Link",
        fetchBtnLoading: "Analyzing Engine...",
        inputPlaceholder: "Paste YouTube or TikTok link here...",
        duration: "Duration:",
        source: "Source:",
        configTitle: "Configure Output Quality",
        qualityLabel: "Resolution Preference",
        codecLabel: "Video Codec Engine",
        h264Desc: "High Compatibility (Recommended for older devices & editing)",
        hevcDesc: "Smaller Size & Pro Quality (Advanced Compression)",
        downloadBtn: "Generate & Download Media",
        downloadBtnLoading: "Allocating Worker...",
        progressTitle: "Server Rendering Engine",
        readyTitle: "Your file is optimized and ready!",
        downloadDeviceBtn: "Download to Device",
        historyTitle: "Cloud Server Core Storage",
        noFiles: "No cloud assets generated yet."
    },
    ar: {
        appName: "فورتكس دي إل برو",
        appSubtitle: "الأداة الاحترافية لاستخراج مقاطع الفيديو والصوت من يوتيوب وتيك توك",
        langName: "English",
        fetchBtn: "تحليل الرابط",
        fetchBtnLoading: "جاري الفحص المتقدم...",
        inputPlaceholder: "الصق رابط يوتيوب أو تيك توك هنا...",
        duration: "المدة:",
        source: "المصدر:",
        configTitle: "تخصيص جودة استخراج الملف",
        qualityLabel: "تفضيل دقة العرض",
        codecLabel: "محرك ترميز الفيديو (Codec)",
        h264Desc: "H.264 (أكثر توافقية ودعم كامل لجميع برامج المونتاج والأجهزة القياسية)",
        hevcDesc: "HEVC / H.265 (حجم أقل وجودة احترافية ممتازة - ضغط متقدم)",
        downloadBtn: "بدء معالجة وتحميل الميديا",
        downloadBtnLoading: "جاري حجز سيرفر التنزيل...",
        progressTitle: "محرك الرندرة والمعالجة السحابي",
        readyTitle: "تم ضغط ومعالجة ملفك وهو جاهز الآن!",
        downloadDeviceBtn: "تحميل الملف إلى جهازك 📲",
        historyTitle: "وحدة التخزين السحابية للسيرفر",
        noFiles: "لا توجد ملفات في وحدة التخزين حالياً."
    }
};

document.addEventListener("DOMContentLoaded", () => {
    loadCloudStorageFiles();

    document.getElementById("langToggleBtn").addEventListener("click", switchInterfaceLanguage);
    document.getElementById("fetchBtn").addEventListener("click", processVideoLink);
    document.getElementById("downloadBtn").addEventListener("click", executeServerDownload);

    document.getElementById("qualitySelect").addEventListener("change", (e) => {
        const codecGroup = document.getElementById("codecGroup");
        if (e.target.value === "mp3") {
            codecGroup.classList.add("hidden");
        } else {
            codecGroup.classList.remove("hidden");
        }
    });
});

function switchInterfaceLanguage() {
    currentLang = currentLang === 'en' ? 'ar' : 'en';
    const dict = uiDictionary[currentLang];

    document.documentElement.dir = currentLang === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.lang = currentLang;

    document.getElementById("txt-app-title").innerText = dict.appName;
    document.getElementById("txt-app-subtitle").innerText = dict.appSubtitle;
    document.getElementById("txt-lang-name").innerText = dict.langName;
    document.getElementById("txt-fetch-btn").innerText = dict.fetchBtn;
    document.getElementById("videoUrl").placeholder = dict.inputPlaceholder;
    document.getElementById("lbl-duration").innerText = dict.duration;
    document.getElementById("lbl-source").innerText = dict.source;
    document.getElementById("txt-config-title").innerText = dict.configTitle;
    document.getElementById("lbl-quality-select").innerText = dict.qualityLabel;
    document.getElementById("lbl-codec-select").innerText = dict.codecLabel;
    document.getElementById("txt-desc-h264").innerText = dict.h264Desc;
    document.getElementById("txt-desc-hevc").innerText = dict.hevcDesc;
    document.getElementById("txt-download-btn").innerText = dict.downloadBtn;
    document.getElementById("txt-progress-title").innerText = dict.progressTitle;
    document.getElementById("txt-result-ready").innerText = dict.readyTitle;
    document.getElementById("downloadLink").innerText = dict.downloadDeviceBtn;
    document.getElementById("txt-history-title").innerText = dict.historyTitle;

    loadCloudStorageFiles();
}

async function processVideoLink() {
    const url = document.getElementById("videoUrl").value.trim();
    const fetchBtn = document.getElementById("fetchBtn");
    const txtBtn = document.getElementById("txt-fetch-btn");

    if (!url) return alert(currentLang === 'ar' ? "يرجى إضافة رابط صحيح أولاً" : "Please paste a valid URL first");

    fetchBtn.disabled = true;
    txtBtn.innerText = uiDictionary[currentLang].fetchBtnLoading;

    try {
        const response = await fetch("/api/video-info", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: url })
        });
        const data = await response.json();

        if (data.error) {
            alert(data.error);
        } else {
            document.getElementById("thumbnail").src = data.thumbnail;
            document.getElementById("videoTitle").innerText = data.title;
            document.getElementById("videoDuration").innerText = data.duration;
            document.getElementById("videoUploader").innerText = data.uploader;

            document.getElementById("videoInfo").classList.remove("hidden");
            document.getElementById("configSection").classList.remove("hidden");
        }
    } catch (err) {
        alert(currentLang === 'ar' ? "فشل محرك التحليل في جلب الميديا" : "Analysis engine failed to process link");
    } finally {
        fetchBtn.disabled = false;
        txtBtn.innerText = uiDictionary[currentLang].fetchBtn;
    }
}

async function executeServerDownload() {
    const url = document.getElementById("videoUrl").value.trim();
    const quality = document.getElementById("qualitySelect").value;
    const codec = document.querySelector('input[name="codec"]:checked').value;
    const downloadBtn = document.getElementById("downloadBtn");
    const txtBtn = document.getElementById("txt-download-btn");

    downloadBtn.disabled = true;
    txtBtn.innerText = uiDictionary[currentLang].downloadBtnLoading;

    document.getElementById("progressSection").classList.remove("hidden");
    document.getElementById("downloadResult").classList.add("hidden");
    document.getElementById("progressBar").style.width = "0%";
    document.getElementById("progressPercent").innerText = "0%";

    try {
        const response = await fetch("/api/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url, quality, codec })
        });
        const data = await response.json();

        if (data.error) {
            alert(data.error);
            downloadBtn.disabled = false;
            txtBtn.innerText = uiDictionary[currentLang].downloadBtn;
        } else {
            currentTaskId = data.task_id;
            statusInterval = setInterval(trackLiveDownloadProgress, 1000);
        }
    } catch (err) {
        alert("Server Sync Error");
        downloadBtn.disabled = false;
        txtBtn.innerText = uiDictionary[currentLang].downloadBtn;
    }
}

async function trackLiveDownloadProgress() {
    if (!currentTaskId) return;

    try {
        const response = await fetch(`/api/download-status/${currentTaskId}`);
        const data = await response.json();

        const barFill = document.getElementById("progressBar");
        const percentTxt = document.getElementById("progressPercent");
        const messageTxt = document.getElementById("progressMessage");

        if (data.status === "downloading" || data.status === "processing") {
            barFill.style.width = data.progress + "%";
            percentTxt.innerText = data.progress + "%";
            messageTxt.innerText = currentLang === 'ar' ? data.message_ar : data.message_en;
        } else if (data.status === "completed") {
            clearInterval(statusInterval);
            barFill.style.width = "100%";
            percentTxt.innerText = "100%";
            messageTxt.innerText = currentLang === 'ar' ? data.message_ar : data.message_en;

            document.getElementById("downloadLink").href = `/api/download-file/${encodeURIComponent(data.filename)}`;
            document.getElementById("downloadResult").classList.remove("hidden");

            const downloadBtn = document.getElementById("downloadBtn");
            document.getElementById("txt-download-btn").innerText = uiDictionary[currentLang].downloadBtn;
            downloadBtn.disabled = false;

            loadCloudStorageFiles();
        } else if (data.status === "error") {
            clearInterval(statusInterval);
            messageTxt.innerText = currentLang === 'ar' ? data.message_ar : data.message_en;
            document.getElementById("downloadBtn").disabled = false;
        }
    } catch (err) {
        console.error("Progress synchronization exception");
    }
}

async function loadCloudStorageFiles() {
    const listContainer = document.getElementById("filesList");
    try {
        const response = await fetch("/api/downloads");
        const files = await response.json();
        listContainer.innerHTML = "";

        if (files.length === 0) {
            listContainer.innerHTML = `<p style="text-align:center;color:var(--text-secondary);font-size:0.95rem;">${uiDictionary[currentLang].noFiles}</p>`;
            return;
        }

        files.forEach(file => {
            const row = document.createElement("div");
            row.className = "file-row";
            row.innerHTML = `
                <div class="file-main-info">
                    <span class="file-title-text">${file.name}</span>
                    <span class="file-size-tag">${file.size}</span>
                </div>
                <a href="/api/download-file/${encodeURIComponent(file.name)}" class="btn-file-dl">${currentLang === 'ar' ? 'تحميل 📥' : 'Download 📥'}</a>
            `;
            listContainer.appendChild(row);
        });
    } catch (err) {
        listContainer.innerHTML = '<p style="text-align:center;color:#ef4444;">Storage Sync Fail</p>';
    }
}