#!/usr/bin/env python3
"""
Scaler Companion - Backend API Server
FastAPI server for handling downloads and AI processing
"""

import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Import local modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from downloader import VideoDownloader

# ============================================
# Configuration
# ============================================

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ============================================
# Models
# ============================================

class StreamInfo(BaseModel):
    baseUrl: Optional[str] = None
    streamUrl: Optional[str] = None
    keyPairId: Optional[str] = None
    policy: Optional[str] = None
    signature: Optional[str] = None
    detectedChunk: Optional[int] = None

class DownloadRequest(BaseModel):
    title: str
    url: str
    streamInfo: StreamInfo
    devMode: bool = False
    startTime: Optional[int] = None  # Start time in seconds
    endTime: Optional[int] = None    # End time in seconds

class ProcessRequest(BaseModel):
    title: str
    videoPath: str
    options: dict

class DownloadStatus(BaseModel):
    downloadId: str
    status: str  # 'pending', 'downloading', 'complete', 'error'
    progress: float
    message: Optional[str] = None
    path: Optional[str] = None
    error: Optional[str] = None

# ============================================
# State Management
# ============================================

downloads: dict[str, DownloadStatus] = {}
processes: dict[str, dict] = {}

# ============================================
# Lifespan
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Scaler Companion Backend starting...")
    yield
    print("👋 Scaler Companion Backend shutting down...")

# ============================================
# App Setup
# ============================================

app = FastAPI(
    title="Scaler Companion API",
    description="Backend API for Scaler Companion browser extension",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for extension access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "chrome-extension://*",
        "http://localhost:*",
        "https://*.scaler.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================
# Routes
# ============================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@app.post("/api/download")
async def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    """Start a lecture download"""
    download_id = str(uuid.uuid4())
    
    # Debug: Log the incoming request parameters
    print(f"[API] Download request received - devMode: {request.devMode}, startTime: {request.startTime}, endTime: {request.endTime}")
    
    # Create download status
    downloads[download_id] = DownloadStatus(
        downloadId=download_id,
        status="pending",
        progress=0.0,
        message="Starting download..."
    )
    
    # Start download in background
    background_tasks.add_task(
        run_download,
        download_id,
        request
    )
    
    return {
        "downloadId": download_id,
        "message": "Download started"
    }

@app.get("/api/status/{download_id}")
async def get_download_status(download_id: str):
    """Get download status by ID"""
    if download_id not in downloads:
        raise HTTPException(status_code=404, detail="Download not found")
    
    return downloads[download_id]

@app.post("/api/process")
async def start_processing(request: ProcessRequest, background_tasks: BackgroundTasks):
    """Start AI processing on a downloaded lecture"""
    process_id = str(uuid.uuid4())
    
    # Validate video path exists
    video_path = Path(request.videoPath)
    if not video_path.exists():
        raise HTTPException(status_code=400, detail="Video file not found")
    
    processes[process_id] = {
        "status": "pending",
        "progress": 0,
        "title": request.title,
        "options": request.options
    }
    
    # Start processing in background
    background_tasks.add_task(
        run_processing,
        process_id,
        request
    )
    
    return {
        "processId": process_id,
        "message": "Processing started"
    }

@app.get("/api/process/{process_id}")
async def get_process_status(process_id: str):
    """Get processing status by ID"""
    if process_id not in processes:
        raise HTTPException(status_code=404, detail="Process not found")
    
    return processes[process_id]

# ============================================
# Background Tasks
# ============================================

async def run_download(download_id: str, request: DownloadRequest):
    """Run the download in background"""
    import concurrent.futures
    
    try:
        downloads[download_id].status = "downloading"
        downloads[download_id].message = "Preparing download..."
        
        # Sanitize title for folder name
        safe_title = "".join(c for c in request.title if c.isalnum() or c in " -_")[:50]
        if not safe_title:
            safe_title = f"lecture_{download_id[:8]}"
        
        output_dir = OUTPUT_DIR / "videos" / safe_title
        output_dir.mkdir(parents=True, exist_ok=True)
        
        stream_info = request.streamInfo
        
        # Log the stream info for debugging
        print(f"[Download {download_id}] Stream info: {stream_info}")
        
        if not stream_info.baseUrl:
            raise ValueError("No base URL provided. Please play the video first to capture the stream URL.")
        
        # Create downloader with progress callback
        downloader = VideoDownloader(
            output_dir=str(output_dir),
            clip_duration=120
        )
        
        # Set up progress callback
        def progress_callback(current: int, total: int, message: str):
            progress = (current / total) * 70 if total > 0 else 0
            downloads[download_id].progress = progress
            downloads[download_id].message = f"Downloading: {message}"
            print(f"[Download {download_id}] Progress: {progress:.1f}% - {message}")
        
        downloader.set_progress_callback(progress_callback)
        
        # Calculate chunk range based on dev mode settings
        # HLS chunks are typically ~10 seconds each
        CHUNK_DURATION = 10  # seconds per chunk
        
        if request.devMode:
            # Developer mode: use specified times or defaults
            start_time = request.startTime or 0
            end_time = request.endTime or 600  # Default 10 minutes in dev mode
            
            start_chunk = start_time // CHUNK_DURATION
            end_chunk = end_time // CHUNK_DURATION
            
            # Limit to 20 chunks in dev mode
            if end_chunk - start_chunk > 20:
                end_chunk = start_chunk + 20
                print(f"[Download {download_id}] DEV MODE: Limiting to 20 chunks")
            
            print(f"[Download {download_id}] DEV MODE: chunks {start_chunk}-{end_chunk} (times {start_time}s-{end_time}s)")
        else:
            # Normal mode: full lecture
            start_chunk = 0
            end_chunk = stream_info.detectedChunk + 100 if stream_info.detectedChunk else 500
            print(f"[Download {download_id}] Normal mode: chunks {start_chunk}-{end_chunk}")
        
        # Run the synchronous download in a thread pool to not block the event loop
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            # Step 1: Download chunks
            downloads[download_id].message = "Downloading video chunks..."
            success = await loop.run_in_executor(
                pool,
                lambda: downloader.download_chunks(
                    base_url=stream_info.baseUrl,
                    start_chunk=start_chunk,
                    end_chunk=end_chunk,
                    key_pair_id=stream_info.keyPairId,
                    policy=stream_info.policy,
                    signature=stream_info.signature
                )
            )
            
            if not success:
                raise ValueError("Failed to download video chunks. Check the stream URL and credentials.")
            
            downloads[download_id].progress = 75
            downloads[download_id].message = "Merging video chunks..."
            
            # Step 2: Merge chunks
            full_video_path = await loop.run_in_executor(
                pool,
                downloader.merge_chunks_to_video
            )
            
            if not full_video_path:
                raise ValueError("Failed to merge video chunks. FFmpeg may have encountered an error.")
            
            downloads[download_id].progress = 90
            downloads[download_id].message = "Finalizing..."
        
        # Complete
        downloads[download_id].status = "complete"
        downloads[download_id].progress = 100
        downloads[download_id].message = "Download complete!"
        downloads[download_id].path = full_video_path
        
        print(f"[Download {download_id}] Complete! Video saved to: {full_video_path}")
        
    except Exception as e:
        print(f"[Download {download_id}] Error: {e}")
        import traceback
        traceback.print_exc()
        downloads[download_id].status = "error"
        downloads[download_id].error = str(e)
        downloads[download_id].message = f"Download failed: {e}"

async def run_processing(process_id: str, request: ProcessRequest):
    """Run AI processing in background"""
    try:
        processes[process_id]["status"] = "processing"
        
        options = request.options
        steps = []
        
        if options.get("transcribe"):
            steps.append(("transcribe", "Transcribing audio..."))
        if options.get("notes"):
            steps.append(("notes", "Generating notes with AI..."))
        if options.get("announcements"):
            steps.append(("announcements", "Extracting announcements..."))
        if options.get("filter"):
            steps.append(("filter", "Filtering irrelevant content..."))
        
        total_steps = len(steps)
        
        for i, (step_id, message) in enumerate(steps):
            processes[process_id]["currentStep"] = step_id
            processes[process_id]["message"] = message
            processes[process_id]["progress"] = int((i / total_steps) * 100)
            
            # TODO: Call actual processing functions
            await asyncio.sleep(2)  # Placeholder
        
        # Complete
        processes[process_id]["status"] = "complete"
        processes[process_id]["progress"] = 100
        processes[process_id]["message"] = "Processing complete"
        processes[process_id]["results"] = {
            "transcriptPath": str(OUTPUT_DIR / "transcripts" / f"{process_id}.txt"),
            "notesPath": str(OUTPUT_DIR / "notes" / f"{process_id}.md"),
            "announcementsPath": str(OUTPUT_DIR / "announcements" / f"{process_id}.json")
        }
        
    except Exception as e:
        processes[process_id]["status"] = "error"
        processes[process_id]["error"] = str(e)

# ============================================
# Run Server
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
