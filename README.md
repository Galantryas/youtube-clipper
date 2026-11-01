# YouTube Clipper Pro

A local tool that turns a YouTube video into short vertical clips: it downloads the source, tracks the speaker's face, reframes to 9:16 (or another ratio), burns in styled subtitles, and writes one folder per source video.

Everything runs on your machine. There is no account, no upload, and no remote processing.

## Features

- **Any YouTube link** — full URL, `youtu.be`, or Shorts. Pulls title, author, duration, thumbnail, available resolutions, and the transcript.
- **Reframing** — 9:16 vertical, 1:1 square, 4:5 portrait, or 16:9 original, at 1080p or 4K.
- **Speaker tracking** — a YuNet face detector with exponential moving average smoothing, so the crop follows the active speaker instead of jumping.
- **Subtitles** — TikTok-style high-contrast captions, clean white captions, exported `.srt`, or no captions at all.
- **Clip control** — 1 to 8 clips, 15 to 90 seconds each.
- **Per-video output** — `output/<title>_<video_id>/` with the MP4s and SRTs, a preview player, and a library view for past runs.
- **Batch mode** — an optional scheduler that picks trending videos and produces clips on a timer, with per-platform publishing through the YouTube, TikTok, and Instagram APIs.

## Requirements

- Python 3.10+
- FFmpeg (bundled through `imageio-ffmpeg`, no separate install needed)

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Start it with the launcher:

```bat
run.bat
```

or directly:

```bash
python run.py
```

The server starts on <http://localhost:8000> and opens your browser.

## Credentials

Nothing sensitive ships with this repository.

`config/` is created at runtime and is ignored by git. It holds `social_auth.json` — OAuth client IDs, secrets, and refresh tokens for the connected YouTube, TikTok, and Instagram accounts — plus the autopilot configuration and publish history. If you connect an account, those files stay local.

If you want to publish clips, create your own API applications with each platform and connect them from the app's settings screen.

## Output

```
output/
  <video_title>_<video_id>/
    clip_01.mp4
    clip_01.srt
    ...
```

Each run is independent; the library view reads this directory.

## Project layout

```
run.py                     Launcher
backend/
  app.py                   FastAPI application and routes
  downloader.py            yt-dlp wrapper
  clip_engine.py           FFmpeg slicing, cropping, subtitle burn-in
  face_tracker.py          YuNet detection and smoothing
  subtitle_engine.py       Transcript to caption styling
  autopilot/               Scheduler, config, trending fetch
  social/                  Per-platform publishers and auth
static/                    Frontend
tests/                     Pytest suite
```

## Tests

```bash
python -m pytest
```

## Notes

Downloading and republishing other people's videos has terms-of-service and copyright implications. Use it on content you own or have permission to clip.

## Licence

Personal project. Not licensed for redistribution.
