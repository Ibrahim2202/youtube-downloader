import os
import threading
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory, after_this_request
from werkzeug.utils import secure_filename
import yt_dlp

app = Flask(__name__)

DOWNLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

download_status = {}


def clean_filename(title: str) -> str:
    """تنظيف اسم الفيديو ليكون آمناً كاسم ملف مع الحفاظ على الكلمات العربية والإنجليزية"""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", title)
    cleaned = cleaned.strip().replace(" ", "_")
    return cleaned if cleaned else "downloaded_media"


def get_advanced_ydl_opts(extra_opts=None):
    base_opts = {
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        }
    }
    if extra_opts:
        base_opts.update(extra_opts)
    return base_opts


def get_video_info(video_url: str) -> dict | None:
    try:
        ydl_opts = get_advanced_ydl_opts({"playlist_items": "1"})
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return {
                "title": info.get("title", "Premium Extracted Media"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", info.get("extractor_key", "Unknown")),
                "thumbnail": info.get("thumbnail",
                                      "https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?q=80&w=500"),
            }
    except Exception as e:
        print(f"Info Fetch Error: {str(e)}")
        return None


def download_video_task(video_url: str, task_id: str, quality_preset: str, codec: str):
    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                percent = int((downloaded / total) * 100)
                download_status[task_id]["progress"] = percent
                download_status[task_id]["message_en"] = f"Downloading premium assets... {percent}%"
                download_status[task_id]["message_ar"] = f"جاري تحميل الملفات بدقة عالية... {percent}%"
        elif d['status'] == 'finished':
            download_status[task_id]["progress"] = 95
            download_status[task_id]["message_en"] = "Optimizing audio/video via FFmpeg engine..."
            download_status[task_id]["message_ar"] = "جاري رندرة ودمج الميديا عبر محرك FFmpeg..."

    try:
        is_audio = (quality_preset == "mp3")

        # هندسة الفلترة الصارمة لدعم 4K بدون قيود الصيغة الأصلية
        format_selector = "bestaudio/best" if is_audio else {
            "4k": "bestvideo[height<=2160]+bestaudio/bestvideo[height<=1440]+bestaudio/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best",
            "720p": "bestvideo[height<=720]+bestaudio/best",
        }.get(quality_preset, "bestvideo[height<=1080]+bestaudio/best")

        meta_opts = get_advanced_ydl_opts({"playlist_items": "1"})
        with yt_dlp.YoutubeDL(meta_opts) as ydl:
            meta = ydl.extract_info(video_url, download=False)
            video_title = meta.get("title", "downloaded_media")

        safe_base_name = clean_filename(video_title)

        # التعديل هنا: إضافة الجودة لاسم الملف (مثال: Name_4k.mp4) لمنع تداخل الملفات
        output_template = os.path.join(DOWNLOAD_FOLDER, f"{safe_base_name}_{quality_preset}.%(ext)s")

        ydl_opts = get_advanced_ydl_opts({
            "format": format_selector,
            "outtmpl": output_template,
            "progress_hooks": [progress_hook],
            "merge_output_format": "mp4",
            "overwrites": True,  # التعديل هنا: إجبار السيرفر على التحميل وعدم استخدام الكاش القديم
        })

        if is_audio:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }]
        else:
            ydl_opts["recode_video"] = "mp4"

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

            safe_name = os.path.basename(filename)

            download_status[task_id] = {
                "status": "completed",
                "progress": 100,
                "message_en": "Success! Optimization completed.",
                "message_ar": "تم التحميل والرندرة بنجاح واكتملت المعالجة!",
                "filename": safe_name,
            }
    except Exception as e:
        print(f"Task Error: {str(e)}")
        download_status[task_id] = {
            "status": "error",
            "progress": 0,
            "message_en": "Error: Could not process video formats.",
            "message_ar": "حدث خطأ: فشل محرك المعالجة في دمج الجودة المطلوبة.",
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
    quality = data.get("quality", "1080p")
    codec = data.get("codec", "h264")

    if not url:
        return jsonify({"error": "URL is missing"}), 400

    task_id = f"{int(datetime.now().timestamp())}"
    download_status[task_id] = {
        "status": "downloading",
        "progress": 0,
        "message_en": "Allocating high-speed download worker...",
        "message_ar": "جاري تخصيص معالج سحابي فائق السرعة...",
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


@app.route("/api/download-file/<filename>", methods=["GET"])
def download_file(filename):
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)

    @after_this_request
    def remove_file(response):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Successfully auto-deleted cache file: {filename}")
        except Exception as e:
            print(f"Error during auto-deletion: {e}")
        return response

    return send_from_directory(DOWNLOAD_FOLDER, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)