# ClipFetch

A production-oriented web app for downloading public videos (YouTube, TikTok, Instagram,
Facebook, X/Twitter, Reddit, and anything else [yt-dlp](https://github.com/yt-dlp/yt-dlp)
has a dedicated extractor for) through a clean analyze → choose quality → download flow.

It does **not** bypass CAPTCHAs, logins, DRM, geo-blocks, or rate limits. When a platform
rejects a request, the app detects that and says so — it doesn't try to get around it.

## Architecture

```
wsgi.py                  # entry point (dev: `python wsgi.py`; prod: gunicorn)
gunicorn.conf.py
app/
  config.py              # all settings, env-driven, validated at startup
  errors.py              # typed exception hierarchy + yt-dlp failure classifier
  extensions.py          # shared Flask-Limiter instance
  routes/
    pages.py             # GET /
    api.py                # /api/info, /api/download, /api/download/<id>[/file], /api/health
  services/
    validation.py        # URL parsing, SSRF host check, platform detection, preset validation
    downloader.py         # DownloaderService: the only thing that knows about yt-dlp
    media_info.py          # raw yt-dlp JSON -> safe MediaInfo + server-defined quality presets
    ffmpeg.py             # locate + health-check ffmpeg
    jobs.py               # JobManager: bounded thread pool, in-memory job state/lifecycle
    cleanup.py            # disk-space guard, orphan sweep, TTL expiry
  utils/
    security.py           # SSRF: only public IPs are allowed to be fetched
    helpers.py             # filename sanitizing, job-id validation, etc.
    logging.py              # structured JSON/text logging
templates/index.html, static/css/style.css, static/js/app.js   # frontend (vanilla JS)
tests/                    # pytest, all network/download calls mocked or stubbed
```

`DownloaderService` is the only module that talks to yt-dlp, as a subprocess. Everything
above it (routes, jobs) only sees `validate_url() / extract_info() / download() / cleanup()`.
Upgrading yt-dlp, or swapping it for another extractor, never touches Flask code.

### Request/download lifecycle

1. `POST /api/info {url}` → validate → SSRF-check host → detect platform → run
   `yt-dlp --dump-single-json` → return title/thumbnail/duration/formats. Synchronous:
   metadata lookups are fast (bounded by `INFO_TIMEOUT`).
2. `POST /api/download {url, format_id}` → validate → `JobManager.submit()` returns a
   `job_id` immediately (HTTP 202) and runs the actual download on a worker thread.
   Downloads can take minutes, so the request is never held open for the whole job.
3. `GET /api/download/<job_id>` → poll `queued | processing | completed | failed`, with a
   safe, classified error message on failure.
4. `GET /api/download/<job_id>/file` → streams the finished file once, with a TTL
   (`FILE_TTL_SECONDS`) after which it's deleted automatically.

Job state is **in-memory**, in one process (see "Why one process" below), which is why a
custom job/thread model is used instead of Celery/Redis: at the scale this is built for
(a personal or small-team tool, a couple of concurrent downloads), that infrastructure
would add operational weight without solving a problem this project actually has.

### Why downloads from a cloud server sometimes fail (and Flask code can't fix it)

This was the main problem to diagnose. In rough order of likelihood:

1. **Datacenter IP reputation.** YouTube, TikTok, Instagram etc. treat traffic from AWS/
   GCP/Azure/Render/Hetzner ranges with far more suspicion than a residential IP. This is
   the single most common cause of "works on my laptop, fails on the server." No amount
   of Flask code fixes it — it's the network origin, not the request shape.
2. **Shared-IP rate limiting.** If many users share one server IP, the platform sees a
   burst of automated-looking traffic.
3. **An outdated extractor.** Platforms change their internal APIs often; yt-dlp is
   updated correspondingly often. A version even a few weeks old can start failing.
4. **Missing runtime pieces on the host.** FFmpeg often isn't installed by default on
   PaaS build images, and YouTube's newer player responses need a JS interpreter
   (`yt-dlp-ejs`, pinned in `requirements.txt`) to decode signatures.
5. **Ephemeral filesystems and restricted outbound networking** on some hosting
   platforms (see Deployment below).

This app **classifies** these situations (`PlatformAccessDenied`, `RateLimitError`,
`ExtractionError`, `NetworkError`, ...) instead of hiding them behind "Download failed,"
and refuses to add proxy rotation, cookie theft, or anti-bot evasion to work around them —
that would just be building an abuse tool.

## Security

- **SSRF**: `app/utils/security.py` resolves the URL's host and rejects it unless every
  resolved address is public (blocks loopback, private ranges, link-local/cloud-metadata
  `169.254.169.254`, etc.). The generic yt-dlp extractor (which fetches arbitrary pages) is
  never used — only URLs matching a *named* platform extractor are accepted, which bounds
  what the server will ever fetch.
- **No arbitrary subprocess input**: yt-dlp and FFmpeg run via argument lists (never
  `shell=True`), with a scrubbed environment, in their own process group, with a hard
  timeout that kills the whole group. The client never sends a format string — only a
  preset id (`v720`, `audio`) that the server maps to a fixed, safe `-f` selector.
- **Filesystem safety**: every job gets a UUID directory; filenames are derived from a
  server-generated UUID plus a sanitized display name, never from raw user input.
- **Limits**: request body size, max file size, max duration, max concurrent + queued
  jobs, and per-route rate limits are all enforced (`Flask-Limiter`, in-memory storage —
  swap `storage_uri` for Redis if you run more than one process).
- **Error hygiene**: tracebacks never reach the client; `AppError.to_dict()` is the only
  thing serialized to JSON, and the full diagnostic goes to the structured server log.

## Configuration

Copy `.env.example` to `.env` and fill it in — see that file for every variable and its
meaning. Never commit `.env` (already in `.gitignore`).

Two variables are for troubleshooting specifically, not normal setup:
- **`EXTRA_YTDLP_ARGS`**: raw extra yt-dlp arguments (e.g.
  `--extractor-args "tiktok:app_name=trill"`), parsed once at startup and validated. Leave
  empty unless actively diagnosing something with `scripts/diagnose.py` below.
- **`CHECK_YTDLP_UPDATES`**: logs a warning at startup if yt-dlp is outdated (checks PyPI,
  never blocks startup if that check can't reach the network).

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env      # REQUIRED -- see note below. FLASK_ENV=development is fine as-is.
python wsgi.py
```

`wsgi.py` loads `.env` automatically (via `python-dotenv`) if the file exists next to it,
so you don't need to export variables manually for local development. Without a `.env`
file at all, `Config` falls back to its defaults, which means `FLASK_ENV` defaults to
`production` and the app will refuse to start without a `SECRET_KEY` — so make sure you
actually copied `.env.example` to `.env` before running. Real environment variables set by
your shell or hosting platform always take priority over `.env`.

### Opening it from your phone (same Wi-Fi)

`python wsgi.py` binds `0.0.0.0` and prints two links on startup:

```
On this machine:        http://127.0.0.1:5000
On your phone/Wi-Fi:    http://192.168.x.x:5000
```

Open the second link in your phone's browser while it's on the same Wi-Fi network as your
PC. If it doesn't load, Windows Firewall is almost certainly blocking the inbound
connection the first time a new server binds a port — accept the "Allow access" prompt, or
add a rule manually (Windows Defender Firewall → Advanced settings → Inbound Rules → New
Rule → Port → TCP 5000 → Allow). This LAN link only works while your PC and phone share the
same network; it is **not** a public internet link — for that, see Deployment below.



FFmpeg must be installed and on `PATH` (or point `FFMPEG_PATH` at it), unless you set
`REQUIRE_FFMPEG=false` — the app then still runs but can only offer progressive
(single-file) formats and can't produce MP3 audio.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

All network/download calls are mocked or stubbed — tests never hit a real platform.

### Diagnosing a specific URL

```bash
python scripts/diagnose.py "https://www.tiktok.com/@user/video/123..."
```

Runs the exact yt-dlp command the app would, with verbose output, so a platform-specific
failure can be diagnosed precisely instead of guessed at.

## Production deployment (Linux)

```bash
sudo apt update && sudo apt install -y python3-venv ffmpeg
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: FLASK_ENV=production, a real SECRET_KEY
#   python -c "import secrets; print(secrets.token_hex(32))"
mkdir -p downloads temp && chmod 700 downloads temp
export $(grep -v '^#' .env | xargs)   # or use a process manager that loads .env
gunicorn -c gunicorn.conf.py wsgi:app
```

- **WSGI server**: Gunicorn, `gthread` workers (`gunicorn.conf.py`). Never use Flask's
  own dev server (`app.run()`) in production — it's single-threaded and not hardened.
- **Why one process**: job state lives in memory (`app/services/jobs.py`). Running
  `workers > 1` would split that state across processes — a job started on worker A would
  404 when polled on worker B. Scale by raising `threads` and `MAX_CONCURRENT_JOBS`
  instead. Multi-process would need a shared job store (SQLite/Redis) first.
- **Reverse proxy**: put Nginx or Caddy in front for TLS termination and to serve as the
  public entry point; set `TRUSTED_PROXIES=1` so `X-Forwarded-For` is honored for rate
  limiting. Terminate HTTPS at the proxy; don't serve plain HTTP to the internet.
- **Filesystem**: `DOWNLOAD_DIR`/`TEMP_DIR` need real, persistent-during-the-process disk.
  **Platforms with an ephemeral/read-only filesystem (some PaaS free tiers) won't work
  reliably** — set both to a writable, non-ephemeral path, or use a host with a real disk.
- **Outbound networking**: yt-dlp needs unrestricted outbound HTTPS to the video
  platforms. Locked-down egress (common on some PaaS/enterprise networks) will surface as
  `network_error`/`platform_access_denied` even though the app itself is fine — check the
  platform's egress rules first if every platform fails identically.
- **IP reputation**: see "Why downloads sometimes fail" above — this is a property of the
  network you deploy to, not something the app configures away.
- **Process manager**: run Gunicorn under systemd (or your platform's process supervisor)
  so it restarts on crash and on boot. On restart, the app wipes `TEMP_DIR`/`DOWNLOAD_DIR`
  of orphaned job folders automatically (in-memory job records don't survive a restart
  anyway, so their files would otherwise leak).
- **Resource limits**: `MAX_FILE_SIZE_MB`, `MAX_CONCURRENT_JOBS`, `MAX_QUEUE_SIZE`,
  `DOWNLOAD_TIMEOUT` and `MIN_FREE_DISK_MB` all exist to keep one server from being taken
  down by a handful of large or hung downloads — tune them to your actual hardware.

### Windows

Gunicorn doesn't support Windows. Use `waitress` instead (already in `requirements.txt`
behind a platform marker):

```powershell
waitress-serve --listen=0.0.0.0:8000 wsgi:app
```

Install FFmpeg via `winget install ffmpeg` or point `FFMPEG_PATH` at `ffmpeg.exe`.

## Known limitations

- Playlists and channel URLs are rejected on purpose — only single-video links are
  supported.
- Platform support depends entirely on yt-dlp's current extractors; a platform that works
  today can break when the platform changes its site, until yt-dlp is updated
  (`pip install -U yt-dlp` — it's pinned in `requirements.txt` on purpose, so upgrade
  deliberately and re-test rather than floating the version).
- No accounts, no history, no persistence beyond a file's TTL — this is a stateless
  utility, not a media library.
- **Facebook/fb.watch share links** (`facebook.com/share/...`, `fb.watch/...`) are resolved
  through one extra, tightly-scoped redirect-following step (`app/utils/redirect.py`)
  before extraction, because yt-dlp itself has no dedicated extractor for that exact URL
  shape — only its generic (unrestricted) extractor does, which this app deliberately
  doesn't enable. Only that specific whitelist of hosts is ever redirect-followed, and every
  hop is re-checked against the SSRF guard.
- **TikTok extraction can fail even with the latest yt-dlp.** As of this build, the real
  cause was found and fixed: TikTok's extractor asks yt-dlp to impersonate a real browser's
  network fingerprint, which needs the `curl_cffi` package — without it, yt-dlp logs
  `attempting impersonation, but no impersonate target is available` and falls back to a
  plain fingerprint that TikTok is far more likely to block. `curl_cffi` is now pinned in
  `requirements.txt`, and the app checks for it at startup (see the `clipfetch.startup`
  log lines). If TikTok *still* fails after this, it's genuinely platform-side, not a gap
  in this app — run `python scripts/diagnose.py "<the tiktok url>"` for the exact raw
  yt-dlp error, and `pip install -U yt-dlp` if it's been a while since the last update.
- `MAX_HEIGHT`/`MAX_FILE_SIZE_MB` in `.env` default to 2160p/1 GB (raised from the initial
  1080p/500 MB), which is why the app can now show a 4K option when a video has one — lower
  them if you're deploying to a small server with limited disk/bandwidth.

## Storage and cost on a hosted server

This is worth understanding before you deploy — it's the direct answer to "won't the
server fill up with videos and cost me money":

- **Files are never meant to be permanent.** Every finished download is deleted
  automatically after `FILE_TTL_SECONDS` (default 15 min), whether or not anyone picked it
  up, and `TEMP_DIR`/`DOWNLOAD_DIR` are wiped on every restart.
- **`MAX_TOTAL_STORAGE_MB`** (default 2 GB) is a hard, explicit ceiling on the combined
  size of `downloads/` + `temp/`. Once a new job's worst-case size would cross it, the app
  refuses new downloads with a clean `507 storage_error` instead of ever letting disk usage
  run away — this is the actual lever for "don't let the server fill up," independent of
  how much disk your hosting plan gives you. Lower it to match your plan.
- **Because of the above, this app does not need a paid persistent disk**, and
  `render.yaml` deliberately doesn't provision one. Render's default ephemeral filesystem
  (free, included with every plan) is exactly what "temporary by design" storage needs;
  paying for durability this app never uses would be pure waste. Free-tier web services on
  Render can't attach a persistent disk at all, for what it's worth.
- **The cost that actually scales with usage is bandwidth, not storage.** Every file this
  app serves is outbound bandwidth; most hosts include a monthly amount and bill roughly
  $0.10–0.15/GB beyond it. That's inherent to a video-downloading service and isn't
  something a storage setting can reduce — if this gets real traffic, budget for bandwidth.

## Deploying for real (Render, or any Docker host)

Render's native Python buildpack has no `ffmpeg`, so this ships as a container instead:

- `Dockerfile` — installs ffmpeg, installs `requirements.txt`, runs Gunicorn.
- `render.yaml` — a Render Blueprint: push this repo to GitHub, then in Render pick
  **New → Blueprint** and select it. It provisions a Docker web service, a 1 GB persistent
  disk for `downloads/`, and a generated `SECRET_KEY`.

Read the comments at the top of `render.yaml` before you rely on this for anything beyond
personal use — specifically: Render's free/starter tiers use **shared datacenter IPs**
(see "Why downloads sometimes fail" above — some platforms will reject requests from these
regardless of how correct the app's code is), and idle instances spin down, so the first
request after inactivity is slow and any job mid-download when that happens is lost. Both
are properties of the hosting tier, not bugs in the app.

Any other Docker-capable host (Fly.io, Railway, a VPS with `docker run`) works the same way
via the `Dockerfile` directly — the general Linux instructions above still apply if you'd
rather run it without Docker.

