# Scaler Companion

> 🎓 A Chrome browser extension to download Scaler Academy lectures and generate AI-powered notes locally.

## Features

- **📥 One-Click Download** - Download recorded lectures directly from Scaler Academy
- **🎤 Audio Transcription** - Transcribe lectures using local Whisper model (via HuggingFace)
- **🖼️ Slide Extraction** - Extract key frames/slides based on scene changes
- **📝 AI Notes Generation** - Generate detailed Markdown notes with Ollama (any model)
- **📚 Obsidian-Ready** - Output in per-recording folders with linked media

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
│   ├── transcriber.py      # Whisper transcription
│   ├── frame_extractor.py  # Slide/frame extraction
│   ├── notes_generator.py  # Ollama LLM notes
│   ├── pipeline.py         # Processing orchestrator
│   └── requirements.txt    # Python dependencies
│
├── output/                  # Generated outputs
│   └── YYYY-MM-DD_Title/   # Per-recording folders
│       ├── video.mp4
│       ├── transcript.md
│       ├── lecture_notes.md
│       ├── qa_cards.md
│       ├── summary.md
│       ├── slides/
│       └── index.md        # Obsidian index
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

### 2. Install Ollama (for notes generation)

```bash
brew install ollama
ollama pull gpt-oss:20b  # Or any model you prefer
```

### 3. Load Chrome Extension

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select the `extension/` folder

### 4. Use the Extension

1. Navigate to a Scaler Academy lecture
2. Click the Scaler Companion extension icon
3. Click "Download Lecture"
4. After download, click "Process with AI"

## Requirements

- **Python 3.10+**
- **FFmpeg** - For video processing (`brew install ffmpeg`)
- **Chrome Browser** - For the extension
- **Ollama** - For local LLM inference
- **24GB+ RAM recommended** - For Whisper + LLM

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/download` | POST | Start lecture download |
| `/api/status/{id}` | GET | Get download status |
| `/api/process` | POST | Start AI processing |
| `/api/process/{id}` | GET | Get processing status |
| `/api/models` | GET | List available Ollama models |

## Development Status

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Chrome Extension | ✅ Complete |
| 1 | Backend API | ✅ Complete |
| 2 | Audio Transcription (Whisper) | ✅ Complete |
| 2 | Frame/Slide Extraction | ✅ Complete |
| 2 | LLM Notes Generation | ✅ Complete |
| 2 | Obsidian Integration | ✅ Complete |
| 3 | Polish & UX | 🔜 Planned |

## License

MIT
