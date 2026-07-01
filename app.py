import os
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
import yt_dlp

app = Flask(__name__)

# مجلد التخزين داخل static لسهولة الوصول والاستعراض
DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

download_status = {}


def get_video_info(video_url: str) -> dict | None:
    """تحليل الرابط وجلب بيانات الميديا ليوتيوب وتيك توك"""
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "playlist_items": "1"
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {
                "title": info.get("title", "Multi-Platform Video"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", info.get("extractor_key", "Unknown")),
                "thumbnail": info.get("thumbnail",
                                      "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?q=80&w=500"),
            }
    except Exception:
        return None


def download_video_task(video_url: str, task_id: str, quality_preset: str, codec: str):
    """خيط معالجة منفصل للتحميل والرندرة في الخلفية دون تجميد الموقع"""

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                download_status[task_id]["progress"] = percent
                download_status[task_id]["message_en"] = f"Downloading assets... {percent}%"
                download_status[task_id]["message_ar"] = f"جاري تحميل الملفات... {percent}%"
        elif d['status'] == 'finished':
            download_status[task_id]["progress"] = 95
            download_status[task_id]["message_en"] = "Rendering video via FFmpeg engine..."
            download_status[task_id]["message_ar"] = "جاري رندرة الفيديو عبر محرك FFmpeg..."

    try:
        is_audio = (quality_preset == "mp3")

        # اختيار الجودة المناسبة
        format_selector = "bestaudio/best" if is_audio else {
            "4k": "bestvideo[height<=2160]+bestaudio/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best",
            "720p": "bestvideo[height<=720]+bestaudio/best",
            "best": "bestvideo+bestaudio/best"
        }.get(quality_preset, "best")

        ydl_opts = {
            "format": format_selector,
            "outtmpl": os.path.join(DOWNLOAD_FOLDER, "%(title)s.%(ext)s"),
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True
        }

        if is_audio:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            ydl_opts["merge_output_format"] = "mp4"
            ydl_opts["recode_video"] = "mp4"

            # تطبيق الترميز المختار بشكل احترافي
            if codec == "h264":
                ydl_opts["postprocessor_args"] = {
                    "merger": ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"],
                    "video_convertor": ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac"]
                }
            elif codec == "hevc":
                ydl_opts["postprocessor_args"] = {
                    "merger": ["-c:v", "libx265", "-preset", "ultrafast", "-c:a", "aac"],
                    "video_convertor": ["-c:v", "libx265", "-preset", "ultrafast", "-c:a", "aac"]
                }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            filename = ydl.prepare_filename(info)

            final_ext = "mp3" if is_audio else "mp4"
            filename = os.path.splitext(filename)[0] + f".{final_ext}"

            download_status[task_id] = {
                "status": "completed",
                "progress": 100,
                "message_en": "Success! Optimization completed.",
                "message_ar": "تم التحميل والرندرة بنجاح واكتملت المعالجة!",
                "filename": os.path.basename(filename),
            }
    except Exception as e:
        download_status[task_id] = {
            "status": "error",
            "progress": 0,
            "message_en": f"Error: {str(e)}",
            "message_ar": f"حدث خطأ: {str(e)}",
            "filename": None,
        }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/video-info", methods=["POST"])
def video_info():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "Invalid URL"}), 400
    info = get_video_info(url)
    if not info:
        return jsonify({"error": "Could not fetch metadata"}), 400
    return jsonify(info)


@app.route("/api/download", methods=["POST"])
def download():
    data = request.json or {}
    url = data.get("url", "").strip()
    quality = data.get("quality", "best")
    codec = data.get("codec", "h264")

    if not url:
        return jsonify({"error": "URL is missing"}), 400

    task_id = f"task_{int(datetime.now().timestamp())}"
    download_status[task_id] = {
        "status": "downloading",
        "progress": 0,
        "message_en": "Allocating download worker...",
        "message_ar": "جاري حجز سيرفر التنزيل...",
        "filename": None,
    }

    thread = threading.Thread(target=download_video_task, args=(url, task_id, quality, codec))
    thread.daemon = True
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/download-status/<task_id>", methods=["GET"])
def check_status(task_id):
    if task_id not in download_status:
        return jsonify({"status": "unknown"}), 404
    return jsonify(download_status[task_id])


@app.route("/api/downloads", methods=["GET"])
def list_downloads():
    try:
        files = []
        if os.path.exists(DOWNLOAD_FOLDER):
            for filename in os.listdir(DOWNLOAD_FOLDER):
                filepath = os.path.join(DOWNLOAD_FOLDER, filename)
                if os.path.isfile(filepath):
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    files.append({"name": filename, "size": f"{size_mb:.2f} MB"})
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download-file/<path:filename>", methods=["GET"])
def download_file(filename):
    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)