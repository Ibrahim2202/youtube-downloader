let currentLang = 'en';
let currentTaskId = null;
let statusInterval = null;
let selectedQuality = '4k'; // تم تعيين 4K كافتراضي

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
        urlError: "Please paste a valid URL first",
        failFetch: "Analysis engine failed to process link. Rate limit or protected video.",
        serverError: "Server Synchronization Error",
        downloadedNotice: "File downloaded! Server cache cleared successfully.",
        q4k: "2160p Cinematic",
        q1080: "1080p Crystal",
        q720: "720p Balanced",
        qMp3: "HQ Studio 320kbps"
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
        urlError: "يرجى إضافة رابط صحيح أولاً",
        failFetch: "فشل محرك التحليل في جلب البيانات. قد يكون هناك حظر مؤقت من المنصة.",
        serverError: "خطأ في الاتصال بالسيرفر المركزي",
        downloadedNotice: "تم تحميل الملف لجهازك بنجاح! وتم مسحه تلقائياً من السيرفر لتخفيف الضغط.",
        q4k: "دقة 4K سينمائي",
        q1080: "دقة 1080p كاملة",
        q720: "دقة 720p متوازنة",
        qMp3: "ملف صوتي استوديو"
    }
};

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("langToggleBtn").addEventListener("click", switchInterfaceLanguage);
    document.getElementById("fetchBtn").addEventListener("click", processVideoLink);
    document.getElementById("downloadBtn").addEventListener("click", executeServerDownload);

    const qualityCards = document.querySelectorAll(".quality-card");
    qualityCards.forEach(card => {
        card.addEventListener("click", () => {
            qualityCards.forEach(c => c.classList.remove("active"));
            card.classList.add("active");
            selectedQuality = card.getAttribute("data-value");

            const codecGroup = document.getElementById("codecGroup");
            if (selectedQuality === "mp3") {
                codecGroup.classList.add("hidden");
            } else {
                codecGroup.classList.remove("hidden");
            }
        });
    });

    document.getElementById("downloadLink").addEventListener("click", () => {
        setTimeout(() => {
            showSystemMessage(uiDictionary[currentLang].downloadedNotice, "success");
            document.getElementById("progressSection").classList.add("hidden");
            document.getElementById("videoInfo").classList.add("hidden");
            document.getElementById("configSection").classList.add("hidden");
        }, 500);
    });
});

function showSystemMessage(msg, type = "error") {
    const card = document.getElementById("statusMessageCard");
    card.innerText = msg;
    card.className = `message-card ${type}`;
    card.classList.remove("hidden");
}

function clearSystemMessage() {
    document.getElementById("statusMessageCard").classList.add("hidden");
}

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

    document.getElementById("txt-q-4k").innerText = dict.q4k;
    document.getElementById("txt-q-1080").innerText = dict.q1080;
    document.getElementById("txt-q-720").innerText = dict.q720;
    document.getElementById("txt-q-mp3").innerText = dict.qMp3;

    clearSystemMessage();
}

async function processVideoLink() {
    const url = document.getElementById("videoUrl").value.trim();
    const fetchBtn = document.getElementById("fetchBtn");
    const txtBtn = document.getElementById("txt-fetch-btn");

    clearSystemMessage();
    if (!url) {
        showSystemMessage(uiDictionary[currentLang].urlError, "error");
        return;
    }

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
            showSystemMessage(uiDictionary[currentLang].failFetch, "error");
        } else {
            document.getElementById("thumbnail").src = data.thumbnail;
            document.getElementById("videoTitle").innerText = data.title;
            document.getElementById("videoDuration").innerText = data.duration;
            document.getElementById("videoUploader").innerText = data.uploader;

            document.getElementById("videoInfo").classList.remove("hidden");
            document.getElementById("configSection").classList.remove("hidden");
        }
    } catch (err) {
        showSystemMessage(uiDictionary[currentLang].failFetch, "error");
    } finally {
        fetchBtn.disabled = false;
        txtBtn.innerText = uiDictionary[currentLang].fetchBtn;
    }
}

async function executeServerDownload() {
    const url = document.getElementById("videoUrl").value.trim();

    const codecElement = document.querySelector('input[name="codec"]:checked');
    const codec = (selectedQuality === "mp3" || !codecElement) ? "h264" : codecElement.value;

    const downloadBtn = document.getElementById("downloadBtn");
    const txtBtn = document.getElementById("txt-download-btn");

    clearSystemMessage();
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
            body: JSON.stringify({ url, quality: selectedQuality, codec })
        });
        const data = await response.json();

        if (data.error) {
            showSystemMessage(data.error, "error");
            downloadBtn.disabled = false;
            txtBtn.innerText = uiDictionary[currentLang].downloadBtn;
        } else {
            currentTaskId = data.task_id;
            statusInterval = setInterval(trackLiveDownloadProgress, 1000);
        }
    } catch (err) {
        showSystemMessage(uiDictionary[currentLang].serverError, "error");
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

        if (data.status === "downloading") {
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
        } else if (data.status === "error") {
            clearInterval(statusInterval);
            messageTxt.innerText = currentLang === 'ar' ? data.message_ar : data.message_en;
            showSystemMessage(currentLang === 'ar' ? data.message_ar : data.message_en, "error");
            document.getElementById("downloadBtn").disabled = false;
            document.getElementById("txt-download-btn").innerText = uiDictionary[currentLang].downloadBtn;
        }
    } catch (err) {
        console.error("Progress synchronization exception");
    }
}