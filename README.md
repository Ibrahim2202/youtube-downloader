# YouTube Video Downloader & Transcoder

A Flask web application for downloading and transcoding YouTube videos in high-quality formats.

## Overview

A simple web interface that lets a user paste a YouTube link and download the video, with server-side transcoding to efficient modern codecs.

## Approach

- **Downloading:** Uses `yt-dlp` to fetch and stream video content from YouTube.
- **Transcoding:** Integrates FFmpeg on the backend to re-encode downloaded video into high-efficiency formats (H.264 and HEVC/H.265), balancing quality and file size.
- **Web interface:** Built with Flask, providing a straightforward UI for submitting a link and retrieving the processed file.

## Tech Stack

Python · Flask · yt-dlp · FFmpeg

## Status

Functional web app — end-to-end flow from URL input to downloadable, transcoded video file.

## Disclaimer

Intended for personal/educational use. Downloading copyrighted content without permission may violate YouTube's Terms of Service and applicable copyright law.
