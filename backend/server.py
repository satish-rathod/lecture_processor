#!/usr/bin/env python3
"""
Scaler Companion - Backend API Server
FastAPI server for handling downloads and AI processing
"""

import os
import uuid
import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager
import subprocess

def prevent_sleep():
    """Prevent macOS from sleeping while this process is running using caffeinate"""
    try:
        # -i: Prevent idle sleep
        # -w <pid>: Wait for process <pid> to exit
        subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())])
        print("☕️ Sleep prevention enabled (caffeinate)")
    except Exception as e:
        print(f"⚠️ Failed to enable sleep prevention: {e}")

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Import local modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from downloader import VideoDownloader
from pipeline import ProcessingPipeline

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
    # devMode removed - time controls are now standard
    startTime: Optional[int] = None  # Start time in seconds
    endTime: Optional[int] = None    # End time in seconds

class ProcessRequest(BaseModel):
    title: str
    videoPath: str
    options: dict = {}
    whisperModel: str = "medium"
    ollamaModel: str = "gpt-oss:20b"
    skipTranscription: bool = False
    skipFrames: bool = False
    skipNotes: bool = False
    skipSlideAnalysis: bool = False

class ProcessStatus(BaseModel):
    processId: str
    status: str  # 'pending', 'processing', 'complete', 'error'
    progress: float
    stage: Optional[str] = None
    message: Optional[str] = None
    outputDir: Optional[str] = None
    error: Optional[str] = None
    title: Optional[str] = None # Added for UI matching

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


# ============================================
# State Management
# ============================================

downloads: dict[str, DownloadStatus] = {}
processes: dict[str, dict] = {}

# Job Queue for sequential processing
JOB_QUEUE: list[dict] = []  # List of {"id": str, "request": ProcessRequest}
CURRENT_PROCESS_ID: Optional[str] = None

# ============================================
# Lifespan & Worker
# ============================================

async def process_worker():
    """Background worker to process jobs sequentially"""
    global CURRENT_PROCESS_ID
    print("👷 Starting process worker...")
    
    while True:
        try:
            if JOB_QUEUE and CURRENT_PROCESS_ID is None:
                # Pick next job
                job = JOB_QUEUE.pop(0)
                process_id = job["id"]
                request = job["request"]
                
                print(f"👷 Worker picking up job: {process_id} ({request.title})")
                CURRENT_PROCESS_ID = process_id
                
                try:
                    # Run processing (this is async wrapper but runs blocking code in thread pool)
                    await run_processing(process_id, request)
                except Exception as e:
                    print(f"❌ Worker error processing {process_id}: {e}")
                finally:
                    print(f"👷 Worker finished job: {process_id}")
                    CURRENT_PROCESS_ID = None
            
            # Wait before next check
            await asyncio.sleep(1)
            
        except Exception as e:
            print(f"CRITICAL WORKER ERROR: {e}")
            await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Scaler Companion Backend starting...")
    prevent_sleep()
    
    # Start worker task
    worker_task = asyncio.create_task(process_worker())
    
    yield
    
    print("👋 Scaler Companion Backend shutting down...")
    worker_task.cancel()

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (artifacts)
from fastapi.staticfiles import StaticFiles
app.mount("/content", StaticFiles(directory=str(OUTPUT_DIR)), name="content")

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
    print(f"[API] Download request received - startTime: {request.startTime}, endTime: {request.endTime}")
    
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
async def start_processing(request: ProcessRequest):
    """Enqueue a lecture for AI processing"""
    process_id = str(uuid.uuid4())
    
    # Validate video path exists
    video_path = Path(request.videoPath)
    if not video_path.exists():
        raise HTTPException(status_code=400, detail="Video file not found")
    
    # Initialize status
    processes[process_id] = ProcessStatus(
        processId=process_id,
        status="queued",
        progress=0.0,
        message="Waiting in queue...",
        title=request.title
    )
    
    # Add to queue
    JOB_QUEUE.append({
        "id": process_id,
        "request": request
    })
    
    print(f"📥 Enqueued job {process_id} for '{request.title}'. Queue length: {len(JOB_QUEUE)}")
    
    return {
        "processId": process_id,
        "message": "Job queued successfully",
        "position": len(JOB_QUEUE)
    }

@app.get("/api/process/{process_id}")
async def get_process_status(process_id: str):
    """Get processing status by ID"""
    if process_id not in processes:
        raise HTTPException(status_code=404, detail="Process not found")
    
    return processes[process_id]

@app.get("/api/models")
async def list_ollama_models():
    """List available Ollama models"""
    try:
        from notes_generator import NotesGenerator
        generator = NotesGenerator()
        models = generator.list_available_models()
        return {"models": models}
    except Exception as e:
        return {"models": [], "error": str(e)}

@app.get("/api/recordings")
async def list_recordings():
    """List all recordings (downloaded & processed) - merged into single cards"""
    recordings = {}
    
    # Helper to normalize title for matching
    def normalize_title(title: str) -> str:
        import re
        # Replace underscores and dashes with spaces, collapse multiple spaces, lowercase
        normalized = title.lower().replace("_", " ").replace("-", " ")
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized
    
    # 1. First, scan for processed outputs (these are the "complete" records)
    for output_folder in OUTPUT_DIR.iterdir():
        if output_folder.is_dir() and output_folder.name != "videos":
            # Format: YYYY-MM-DD_Title
            folder_name = output_folder.name
            parts = folder_name.split("_", 1)
            
            if len(parts) < 2:
                continue
                
            date_str, safe_title = parts[0], parts[1]
            display_title = safe_title.replace("_", " ")
            normalized = normalize_title(safe_title)
            
            is_processed = (output_folder / "lecture_notes.md").exists()
            is_processing = (output_folder / "transcript.txt").exists() and not is_processed
            
            status = "processed" if is_processed else ("processing" if is_processing else "pending")
            
            # Find matching video in videos folder
            video_path = None
            videos_dir = OUTPUT_DIR / "videos"
            if videos_dir.exists():
                for video_folder in videos_dir.iterdir():
                    if video_folder.is_dir():
                        if normalize_title(video_folder.name) == normalized or \
                           normalized in normalize_title(video_folder.name) or \
                           normalize_title(video_folder.name) in normalized:
                            video_file = video_folder / "full_video.mp4"
                            if video_file.exists():
                                video_path = str(video_file)
                                break
            
            recordings[normalized] = {
                "id": folder_name,
                "title": display_title,
                "status": status,
                "date": date_str,
                "path": str(output_folder),
                "videoPath": video_path,
                "processed": is_processed,
                "artifacts": {
                    "notes": f"/content/{folder_name}/lecture_notes.md" if (output_folder / "lecture_notes.md").exists() else None,
                    "summary": f"/content/{folder_name}/summary.md" if (output_folder / "summary.md").exists() else None,
                    "announcements": f"/content/{folder_name}/announcements.md" if (output_folder / "announcements.md").exists() else None,
                    "qa_cards": f"/content/{folder_name}/qa_cards.md" if (output_folder / "qa_cards.md").exists() else None,
                    "slides": f"/content/{folder_name}/slides/" if (output_folder / "slides").exists() else None,
                    "transcript": f"/content/{folder_name}/transcript_with_slides.md" if (output_folder / "transcript_with_slides.md").exists() else (f"/content/{folder_name}/transcript.md" if (output_folder / "transcript.md").exists() else (f"/content/{folder_name}/transcript.txt" if (output_folder / "transcript.txt").exists() else None)),
                }
            }
    
    # 2. Add downloaded videos that DON'T have processed output yet
    videos_dir = OUTPUT_DIR / "videos"
    if videos_dir.exists():
        for video_folder in videos_dir.iterdir():
            if video_folder.is_dir():
                title = video_folder.name
                normalized = normalize_title(title)
                
                # Skip if we already have this from processed outputs
                if normalized in recordings:
                    continue
                
                video_file = video_folder / "full_video.mp4"
                if video_file.exists():
                    recordings[normalized] = {
                        "id": title,
                        "title": title,
                        "status": "downloaded",
                        "date": datetime.fromtimestamp(video_file.stat().st_mtime).strftime("%Y-%m-%d"),
                        "downloadDate": datetime.fromtimestamp(video_file.stat().st_mtime).isoformat(),
                        "videoPath": str(video_file),
                        "processed": False,
                        "progress": 0,
                        "artifacts": None
                    }
    
    # 3. OVERLAY: Check active processes and queue to update status
    
    # helper to update recording in map
    def update_recording_status(rec_title, status, progress, message, pid=None):
        norm = normalize_title(rec_title)
        
        # If we don't have a record for this yet (e.g. processing a file not in videos or output), create placeholder
        if norm not in recordings:
            recordings[norm] = {
                "id": rec_title, # Fallback ID
                "title": rec_title,
                "status": status,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "path": None,
                "videoPath": None,
                "processed": False,
                "progress": progress,
                "message": message,
                "artifacts": None
            }
        else:
            # Update existing record
            recordings[norm]["status"] = status
            recordings[norm]["progress"] = progress
            if message:
                recordings[norm]["message"] = message
    
    # Check running/queued processes
    for pid, p_data in processes.items():
        # p_data is ProcessStatus object
        if p_data.title:
            update_recording_status(
                p_data.title, 
                p_data.status, 
                p_data.progress, 
                p_data.message,
                pid
            )

    # Sort by date descending
    sorted_recordings = sorted(
        recordings.values(), 
        key=lambda x: x.get("date", ""), 
        reverse=True
    )
    
    return {"recordings": sorted_recordings}


@app.get("/api/recordings/check")
async def check_recording(title: str = Query(..., description="Recording title to check")):
    """Check if a recording with this title exists"""
    title_lower = title.lower()
    
    # Check in videos folder (downloaded)
    videos_dir = OUTPUT_DIR / "videos"
    if videos_dir.exists():
        for folder in videos_dir.iterdir():
            if folder.is_dir() and title_lower in folder.name.lower():
                return {"exists": True, "status": "downloaded", "path": str(folder)}
    
    # Check in processed folders
    for folder in OUTPUT_DIR.iterdir():
        if folder.is_dir() and folder.name != "videos":
            if title_lower in folder.name.lower():
                is_processed = (folder / "lecture_notes.md").exists()
                return {
                    "exists": True, 
                    "status": "processed" if is_processed else "processing",
                    "path": str(folder)
                }
    
    return {"exists": False, "status": None, "path": None}

@app.delete("/api/recordings/{recording_id}")
async def delete_recording(recording_id: str):
    """Delete a recording and all its artifacts"""
    deleted = []
    errors = []
    
    # Try to delete from videos folder
    videos_path = OUTPUT_DIR / "videos" / recording_id
    if videos_path.exists():
        try:
            shutil.rmtree(videos_path)
            deleted.append(str(videos_path))
        except Exception as e:
            errors.append(f"Failed to delete {videos_path}: {e}")
    
    # Try to delete processed folder (recording_id might be the full folder name like "2024-01-15_Title")
    processed_path = OUTPUT_DIR / recording_id
    if processed_path.exists() and processed_path.is_dir():
        try:
            shutil.rmtree(processed_path)
            deleted.append(str(processed_path))
        except Exception as e:
            errors.append(f"Failed to delete {processed_path}: {e}")
    
    # Also check for partial title matches in processed folders
    for folder in OUTPUT_DIR.iterdir():
        if folder.is_dir() and folder.name != "videos":
            if recording_id.lower() in folder.name.lower():
                try:
                    shutil.rmtree(folder)
                    deleted.append(str(folder))
                except Exception as e:
                    errors.append(f"Failed to delete {folder}: {e}")
    
    if not deleted and not errors:
        raise HTTPException(status_code=404, detail="Recording not found")
    
    return {
        "success": len(errors) == 0,
        "deleted": deleted,
        "errors": errors
    }

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
        # HLS chunks are typically ~10 seconds each, but user observed ~16s
        CHUNK_DURATION = 16  # seconds per chunk
        
        if request.startTime is not None or request.endTime is not None:
            # Custom range mode
            start_time = request.startTime or 0
            # If no end time, use a safe default or try to detect duration
            # For now, if no end time, we'll download a significant chunk (e.g. 2 hours)
            # or rely on detectedChunk if available? 
            # Better: if endTime is None, go until detectedChunk or 1000 chunks
            
            end_time = request.endTime or 7200 # Default to 2 hours if not specified but start time IS specified?
            # Actually, standard behavior: if endTime is 0/None, we want FULL lecture.
            # But here we are in the "custom range" block.
            
            start_chunk = int(start_time / CHUNK_DURATION) 
            
            if request.endTime:
                end_chunk = int(request.endTime / CHUNK_DURATION)
            else:
                 # No end time specified -> Download to end
                 end_chunk = stream_info.detectedChunk + 100 if stream_info.detectedChunk else 1000
            
            print(f"[Download {download_id}] Custom range: chunks {start_chunk}-{end_chunk} (times {start_time}s-{end_time if request.endTime else 'END'})")
        else:
            # Full lecture mode (no start/end time specified)
            start_chunk = 0
            end_chunk = stream_info.detectedChunk + 100 if stream_info.detectedChunk else 1000
            print(f"[Download {download_id}] Full lecture mode: chunks {start_chunk}-{end_chunk}")
        
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
                lambda: downloader.merge_chunks_to_video(start_chunk, end_chunk)
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
    """Run AI processing using the full pipeline"""
    import concurrent.futures
    
    try:
        processes[process_id].status = "processing"
        processes[process_id].message = "Initializing pipeline..."
        
        # Create pipeline with user's model preferences
        pipeline = ProcessingPipeline(
            output_base=str(OUTPUT_DIR),
            whisper_model=request.whisperModel,
            ollama_model=request.ollamaModel
        )
        
        # Progress callback
        def progress_callback(stage: str, current: int, total: int, message: str):
            progress_map = {
                "transcription": (0, 40),
                "frames": (40, 70),
                "notes": (70, 100)
            }
            base, max_prog = progress_map.get(stage, (0, 100))
            stage_progress = (current / total) * (max_prog - base) if total > 0 else 0
            processes[process_id].progress = base + stage_progress
            processes[process_id].stage = stage
            processes[process_id].message = message
            print(f"[Process {process_id}] {stage}: {message}")
        
        pipeline.set_progress_callback(progress_callback)
        
        # Run processing in thread pool (heavy CPU/GPU work)
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            results = await loop.run_in_executor(
                pool,
                lambda: pipeline.process(
                    video_path=request.videoPath,
                    title=request.title,
                    skip_transcription=request.skipTranscription,
                    skip_frames=request.skipFrames,
                    skip_notes=request.skipNotes,
                    skip_slide_analysis=request.skipSlideAnalysis
                )
            )
        
        # Complete
        processes[process_id].status = "complete"
        processes[process_id].progress = 100
        processes[process_id].message = "Processing complete!"
        processes[process_id].outputDir = results.get("output_dir")
        
        print(f"[Process {process_id}] Complete! Output: {results.get('output_dir')}")
        
    except Exception as e:
        print(f"[Process {process_id}] Error: {e}")
        import traceback
        traceback.print_exc()
        processes[process_id].status = "error"
        processes[process_id].error = str(e)
        processes[process_id].message = f"Processing failed: {e}"

# ============================================
# Run Server
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
