# Scaler Companion

> 🎓 A Chrome browser extension to download Scaler Academy lectures and generate AI-powered notes locally.

## Features

- **📥 One-Click Download** - Download recorded lectures directly from Scaler Academy
- **🎤 Audio Transcription** - Transcribe lectures using local Whisper model
- **📝 AI Notes Generation** - Generate detailed Markdown notes with GPT-OSS 20B
- **📢 Announcement Extraction** - Automatically extract deadlines and announcements
- **⏩ Smart Filtering** - Skip blank screens, attendance, and irrelevant parts

## Project Structure

```
lecture_processor/
├── extension/               # Chrome Extension
│   ├── manifest.json       # Extension manifest (V3)
│   ├── popup/              # Extension popup UI
│   ├── content/            # Content scripts for Scaler pages
│   ├── background/         # Service worker
│   └── icons/              # Extension icons
│
├── backend/                 # Python Backend
│   ├── server.py           # FastAPI server
│   ├── downloader.py       # Video download module
│   └── requirements.txt    # Python dependencies
│
├── output/                  # Generated outputs
│   ├── videos/             # Downloaded lectures
│   ├── transcripts/        # Audio transcripts
│   ├── notes/              # Generated notes
│   └── announcements/      # Extracted announcements
│
└── main.py                  # Legacy standalone downloader
```

## Quick Start

### 1. Install Backend

```bash
cd backend
pip install -r requirements.txt
python server.py
```

### 2. Load Chrome Extension

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select the `extension/` folder

### 3. Use the Extension

1. Navigate to a Scaler Academy lecture
2. Click the Scaler Companion extension icon
3. Click "Download Lecture"
4. After download, click "Process with AI"

## Requirements

- **Python 3.10+**
- **FFmpeg** - For video processing (`brew install ffmpeg`)
- **Chrome Browser** - For the extension

### For AI Processing (Phase 2+)

- **Ollama** - For local LLM inference
- **GPU (optional)** - For faster transcription

## Development Status

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Chrome Extension Skeleton | ✅ Complete |
| 1 | Backend API | ✅ Complete |
| 2 | Audio Transcription | 🔜 Planned |
| 3 | Video Analysis | 🔜 Planned |
| 4 | LLM Notes Generation | 🔜 Planned |
| 5 | Polish & UX | 🔜 Planned |

## Legacy Downloader

The original standalone video downloader is still available:

```bash
python main.py
```

Configure the video URL and CloudFront credentials in the `main()` function.

## License

MIT
