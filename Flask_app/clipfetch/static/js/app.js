(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const els = {
    tally: $("tally"), statusLine: $("statusLine"),
    urlInput: $("urlInput"), analyzeBtn: $("analyzeBtn"),
    loadingPanel: $("loadingPanel"), loadingText: $("loadingText"),
    errorPanel: $("errorPanel"), errorTitle: $("errorTitle"), errorMessage: $("errorMessage"), retryBtn: $("retryBtn"),
    mediaPanel: $("mediaPanel"), thumb: $("thumb"), thumbEmpty: $("thumbEmpty"),
    platformBadge: $("platformBadge"), mediaTitle: $("mediaTitle"),
    mediaDuration: $("mediaDuration"), mediaUploader: $("mediaUploader"),
    formatGrid: $("formatGrid"), downloadBtn: $("downloadBtn"), resetBtn: $("resetBtn"),
    progressPanel: $("progressPanel"), progressStage: $("progressStage"),
    progressFill: $("progressFill"), progressPct: $("progressPct"),
    successPanel: $("successPanel"), successFile: $("successFile"),
    successExpiry: $("successExpiry"), saveBtn: $("saveBtn"), startOverBtn: $("startOverBtn"),
  };

  const PANELS = ["loadingPanel", "errorPanel", "mediaPanel", "progressPanel", "successPanel"];
  let selectedFormat = null;
  let pollTimer = null;

  function showOnly(...names) {
    for (const name of PANELS) els[name].classList.toggle("is-hidden", !names.includes(name));
  }

  function formatBytes(n) {
    if (!n || n <= 0) return null;
    const units = ["B", "KB", "MB", "GB"];
    let i = 0, v = n;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
  }

  function formatDuration(seconds) {
    if (seconds == null) return "";
    const s = Math.max(0, Math.round(seconds));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
  }

  async function api(path, options) {
    let res, body;
    try {
      res = await fetch(path, options);
    } catch {
      throw { message: "Couldn't reach the server. Check your connection and try again." };
    }
    try {
      body = await res.json();
    } catch {
      throw { message: "The server sent back something unexpected." };
    }
    if (!res.ok || body.success === false) {
      throw (body.error || { message: "That request failed." });
    }
    return body;
  }

  function showError(err, retryAction) {
    els.errorTitle.textContent = "Couldn't fetch this video";
    els.errorMessage.textContent = err.message || "Something went wrong. Please try again.";
    els.retryBtn.onclick = retryAction;
    showOnly("errorPanel");
  }

  function renderFormats(formats) {
    els.formatGrid.innerHTML = "";
    selectedFormat = null;
    formats.forEach((fmt, idx) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "format-chip";
      chip.setAttribute("role", "radio");
      chip.setAttribute("aria-checked", "false");
      const size = formatBytes(fmt.filesize);
      chip.textContent = size ? `${fmt.label} · ~${size}` : fmt.label;
      chip.dataset.id = fmt.id;
      chip.addEventListener("click", () => selectFormat(fmt.id));
      els.formatGrid.appendChild(chip);
      if (idx === 0) selectFormat(fmt.id);
    });
  }

  function selectFormat(id) {
    selectedFormat = id;
    for (const chip of els.formatGrid.children) {
      chip.setAttribute("aria-checked", String(chip.dataset.id === id));
    }
  }

  async function analyze() {
    const url = els.urlInput.value.trim();
    if (!url) {
      showError({ message: "Paste a video link first." }, analyze);
      return;
    }
    els.loadingText.textContent = "Reading the link…";
    showOnly("loadingPanel");
    try {
      const info = await api("/api/info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      els.platformBadge.textContent = info.platform;
      els.mediaTitle.textContent = info.title;
      els.mediaDuration.textContent = formatDuration(info.duration);
      els.mediaUploader.textContent = info.uploader || "";
      if (info.thumbnail) {
        els.thumb.src = info.thumbnail;
        els.thumb.hidden = false;
        els.thumbEmpty.hidden = true;
      } else {
        els.thumb.hidden = true;
        els.thumbEmpty.hidden = false;
      }
      renderFormats(info.formats || []);
      showOnly("mediaPanel");
    } catch (err) {
      showError(err, analyze);
    }
  }

  async function startDownload() {
    const url = els.urlInput.value.trim();
    if (!selectedFormat) return;
    els.progressStage.textContent = "Starting…";
    els.progressFill.style.width = "0%";
    els.progressPct.textContent = "—";
    showOnly("progressPanel");
    try {
      const res = await api("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, format_id: selectedFormat }),
      });
      pollJob(res.job_id);
    } catch (err) {
      showError(err, () => showOnly("mediaPanel"));
    }
  }

  const STAGE_LABELS = { queued: "Queued…", starting: "Starting…", downloading: "Downloading…", processing: "Processing…" };

  function pollJob(jobId) {
    clearTimeout(pollTimer);
    const tick = async () => {
      let status;
      try {
        status = await api(`/api/download/${jobId}`);
      } catch (err) {
        showError(err, () => showOnly("mediaPanel"));
        return;
      }
      if (status.status === "failed") {
        showError(status.error || { message: "The download failed." }, () => showOnly("mediaPanel"));
        return;
      }
      if (status.status === "completed") {
        els.successFile.textContent = `${status.file_name} · ${formatBytes(status.file_size) || ""}`;
        const mins = Math.max(1, Math.round(status.expires_in / 60));
        els.successExpiry.textContent = `Available for about ${mins} minute${mins === 1 ? "" : "s"} before it's removed from the server.`;
        els.saveBtn.href = `/api/download/${jobId}/file`;
        showOnly("successPanel");
        return;
      }
      els.progressStage.textContent = STAGE_LABELS[status.stage] || "Working…";
      els.progressFill.style.width = `${status.progress ?? (status.status === "queued" ? 0 : 15)}%`;
      els.progressPct.textContent = status.progress != null ? `${Math.round(status.progress)}%` : "…";
      pollTimer = setTimeout(tick, 1200);
    };
    tick();
  }

  function reset() {
    clearTimeout(pollTimer);
    els.urlInput.value = "";
    showOnly();
    els.urlInput.focus();
  }

  async function checkHealth() {
    try {
      const health = await api("/api/health");
      els.tally.classList.add("is-ready");
      els.statusLine.textContent = health.ffmpeg
        ? "ready"
        : "ready · audio-only quality merges unavailable";
    } catch {
      els.tally.classList.add("is-down");
      els.statusLine.textContent = "server unreachable";
    }
  }

  els.analyzeBtn.addEventListener("click", analyze);
  els.urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") analyze(); });
  els.downloadBtn.addEventListener("click", startDownload);
  els.resetBtn.addEventListener("click", reset);
  els.startOverBtn.addEventListener("click", reset);

  checkHealth();
})();
