# Scaler Academy Video Downloader & Converter

A Python script to download HLS video chunks from Scaler Academy, merge them into a single video file, and split them into 2-minute clips.

## Prerequisites

- **Python 3.x**
- **FFmpeg** and **FFprobe** must be installed and accessible in your system PATH.
  - MacOS: `brew install ffmpeg`

## Installation

1. Clone this repository.
2. Install Python dependencies:
   ```bash
   pip install requests
   ```

## Usage

1. Open `main.py` and configure the following variables in the `main()` function with values from your browser's Network tab (look for `.ts` file requests):
   - `BASE_URL`: The URL path to the video segments.
   - `START_CHUNK`: The first chunk index.
   - `END_CHUNK`: The last chunk index.
   - `KEY_PAIR_ID`: CloudFront Key-Pair-Id.
   - `POLICY`: CloudFront Policy.
   - `SIGNATURE`: CloudFront Signature.

2. Run the script:
   ```bash
   python main.py
   ```

## Output

The script will create a `scaler_videos` directory containing:
- `chunks/`: Individual `.ts` video segments.
- `clips/`: The final video split into 2-minute segments (e.g., `clip_001.mp4`, `clip_002.mp4`).
- `full_video.mp4`: The complete merged video.
