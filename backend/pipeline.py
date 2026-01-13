#!/usr/bin/env python3
"""
Scaler Companion - Processing Pipeline
Orchestrates the full processing workflow: transcription, frame extraction, notes generation
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
import json
import re

from transcriber import WhisperTranscriber
from frame_extractor import FrameExtractor
from notes_generator import NotesGenerator
from slide_analyzer import SlideAnalyzer

logger = logging.getLogger(__name__)


class ProcessingPipeline:
    """
    Orchestrates the complete lecture processing workflow.
    Creates per-recording folders with all outputs.
    """
    
    def __init__(
        self,
        output_base: str = "output",
        whisper_model: str = "medium",
        ollama_model: str = "gpt-oss:20b",
        vision_model: str = "llama3.2-vision:11b"
    ):
        """
        Initialize the processing pipeline
        
        Args:
            output_base: Base directory for all outputs
            whisper_model: Whisper model size (small, medium, large)
            ollama_model: Ollama model name for notes
            vision_model: Ollama vision model for slide analysis
        """
        self.output_base = Path(output_base)
        self.output_base.mkdir(parents=True, exist_ok=True)
        
        self.whisper_model = whisper_model
        self.ollama_model = ollama_model
        self.vision_model = vision_model
        
        # Initialize components (lazy-loaded)
        self._transcriber: Optional[WhisperTranscriber] = None
        self._frame_extractor: Optional[FrameExtractor] = None
        self._notes_generator: Optional[NotesGenerator] = None
        self._slide_analyzer: Optional[SlideAnalyzer] = None
        
        self.progress_callback: Optional[Callable] = None
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    def _update_progress(self, stage: str, current: int, total: int, message: str):
        """Update progress via callback"""
        if self.progress_callback:
            self.progress_callback(stage, current, total, message)
    
    @property
    def transcriber(self) -> WhisperTranscriber:
        """Lazy-load transcriber"""
        if self._transcriber is None:
            self._transcriber = WhisperTranscriber(model_name=self.whisper_model)
        return self._transcriber
    
    @property
    def frame_extractor(self) -> FrameExtractor:
        """Lazy-load frame extractor (30s intervals)"""
        if self._frame_extractor is None:
            self._frame_extractor = FrameExtractor(
                fixed_interval=30.0,  # Extract every 30 seconds
                min_interval=10.0     # Min 10s between frames
            )
        return self._frame_extractor
    
    @property
    def notes_generator(self) -> NotesGenerator:
        """Lazy-load notes generator"""
        if self._notes_generator is None:
            self._notes_generator = NotesGenerator(model=self.ollama_model)
        return self._notes_generator
    
    @property
    def slide_analyzer(self) -> SlideAnalyzer:
        """Lazy-load slide analyzer (OCR-only for speed)"""
        if self._slide_analyzer is None:
            self._slide_analyzer = SlideAnalyzer(
                vision_model=self.vision_model,
                use_ocr=True,
                use_vision=False  # OCR-only for speed
            )
        return self._slide_analyzer
    
    def _sanitize_title(self, title: str) -> str:
        """Convert title to safe folder name"""
        # Remove/replace invalid characters
        safe = re.sub(r'[<>:"/\\|?*]', '', title)
        safe = re.sub(r'\s+', '_', safe)
        safe = safe[:80]  # Limit length
        return safe
    
    def _create_recording_folder(self, title: str) -> Path:
        """Create the per-recording output folder"""
        date_prefix = datetime.now().strftime("%Y-%m-%d")
        safe_title = self._sanitize_title(title)
        folder_name = f"{date_prefix}_{safe_title}"
        
        folder_path = self.output_base / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)
        
        # Create subfolders
        (folder_path / "slides").mkdir(exist_ok=True)
        
        return folder_path
    
    def process(
        self,
        video_path: str,
        title: str,
        skip_transcription: bool = False,
        skip_frames: bool = False,
        skip_notes: bool = False,
        skip_slide_analysis: bool = False
    ) -> dict:
        """
        Process a lecture video through the full pipeline
        
        Args:
            video_path: Path to video file
            title: Lecture title
            skip_transcription: Skip Whisper transcription
            skip_frames: Skip frame extraction
            skip_notes: Skip LLM notes generation
            
        Returns:
            Dict with processing results and paths
        """
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")
        
        logger.info(f"Starting processing: {title}")
        
        # Create recording folder
        recording_dir = self._create_recording_folder(title)
        logger.info(f"Output folder: {recording_dir}")
        
        results = {
            "title": title,
            "video_path": str(video_path),
            "output_dir": str(recording_dir),
            "status": "processing"
        }
        
        # Copy/link video to output folder
        video_dest = recording_dir / "video.mp4"
        if not video_dest.exists():
            shutil.copy2(video_path, video_dest)
            logger.info(f"Copied video to {video_dest}")
        results["video"] = str(video_dest)
        
        transcript_text = ""
        
        # Stage 1: Transcription
        if not skip_transcription:
            self._update_progress("transcription", 0, 100, "Starting transcription...")
            try:
                logger.info("Stage 1: Transcription")
                transcription = self.transcriber.transcribe_video(
                    str(video_path),
                    str(recording_dir)
                )
                transcript_text = transcription.get("text", "")
                results["transcript"] = str(recording_dir / "transcript.md")
                results["transcript_json"] = str(recording_dir / "transcript.json")
                logger.info("Transcription complete")
            except Exception as e:
                logger.error(f"Transcription failed: {e}")
                results["transcript_error"] = str(e)
        else:
            # Try to load existing transcript
            transcript_path = recording_dir / "transcript.txt"
            if transcript_path.exists():
                transcript_text = transcript_path.read_text()
        
        # Stage 2: Frame Extraction
        frames = []
        slide_analyses = []
        if not skip_frames:
            self._update_progress("frames", 0, 100, "Extracting frames...")
            try:
                logger.info("Stage 2: Frame Extraction")
                frames = self.frame_extractor.extract_frames(
                    str(video_path),
                    str(recording_dir),
                    use_hybrid=False  # Simple 30s intervals only
                )
                results["frames"] = frames
                results["frames_count"] = len(frames)
                logger.info(f"Extracted {len(frames)} frames")
                
                # Stage 2.5: Analyze slides with OCR and Vision LLM
                if not skip_slide_analysis:
                    self._update_progress("slide_analysis", 0, 100, "Analyzing slides with OCR and Vision...")
                    try:
                        logger.info("Stage 2.5: Slide Analysis")
                        slide_analyses = self.slide_analyzer.analyze_all_slides(
                            frames,
                            str(recording_dir)
                        )
                        results["slide_analyses"] = len(slide_analyses)
                        logger.info(f"Analyzed {len(slide_analyses)} slides")
                    except Exception as e:
                        logger.error(f"Slide analysis failed: {e}")
                else:
                    logger.info("Skipping slide analysis (requested)")
                    
            except Exception as e:
                logger.error(f"Frame extraction failed: {e}")
                results["frames_error"] = str(e)
        
        # Stage 3: Create enhanced transcript with slides and analysis
        if frames and (recording_dir / "transcript.json").exists():
            self._update_progress("integration", 0, 100, "Integrating slides into transcript...")
            try:
                self._create_enhanced_transcript(recording_dir, frames, slide_analyses)
                results["enhanced_transcript"] = str(recording_dir / "transcript_with_slides.md")
                logger.info("Created enhanced transcript with slides")
            except Exception as e:
                logger.error(f"Enhanced transcript creation failed: {e}")
        
        # Stage 3: Notes Generation
        if not skip_notes and transcript_text:
            self._update_progress("notes", 0, 100, "Generating notes...")
            try:
                logger.info("Stage 3: Notes Generation")
                # Include slide OCR text in notes generation
                notes_context = self._prepare_notes_context(transcript_text, frames, slide_analyses)
                notes_results = self.notes_generator.generate_all(
                    notes_context,
                    str(recording_dir),
                    title=title
                )
                results["notes"] = notes_results
                logger.info("Notes generation complete")
            except Exception as e:
                logger.error(f"Notes generation failed: {e}")
                results["notes_error"] = str(e)
        elif skip_notes:
            logger.info("Skipping notes generation")
        else:
            logger.warning("No transcript available for notes generation")
        
        # Create Obsidian index file
        self._create_index_file(recording_dir, title, results)
        
        # Create HTML lecture viewer
        if frames:
            self._create_lecture_viewer(recording_dir, title, frames, slide_analyses)
        
        # Save metadata
        metadata = {
            "title": title,
            "processed_at": datetime.now().isoformat(),
            "whisper_model": self.whisper_model,
            "ollama_model": self.ollama_model,
            "results": results
        }
        
        with open(recording_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        
        results["status"] = "complete"
        results["metadata"] = str(recording_dir / "metadata.json")
        
        logger.info(f"Processing complete: {recording_dir}")
        
        return results
    
    def _create_enhanced_transcript(self, recording_dir: Path, frames: list, slide_analyses: list = None):
        """Create a transcript with slides and analysis embedded at appropriate timestamps"""
        # Load transcript chunks
        transcript_path = recording_dir / "transcript.json"
        with open(transcript_path, "r") as f:
            transcript_data = json.load(f)
        
        chunks = transcript_data.get("chunks", [])
        
        # Build frame lookup by timestamp
        frame_lookup = {}
        for frame in frames:
            ts = frame.get("timestamp", 0)
            frame_lookup[ts] = frame
        
        # Build analysis lookup by filename
        analysis_lookup = {}
        if slide_analyses:
            for analysis in slide_analyses:
                filename = analysis.get("filename", "")
                analysis_lookup[filename] = analysis
        
        # Sort frame timestamps
        frame_timestamps = sorted(frame_lookup.keys())
        
        # Create enhanced markdown
        enhanced_path = recording_dir / "transcript_with_slides.md"
        with open(enhanced_path, "w", encoding="utf-8") as f:
            f.write("# Lecture Transcript with Slides\n\n")
            f.write("---\n\n")
            
            current_frame_idx = 0
            
            for chunk in chunks:
                start_time = chunk.get("timestamp", [0, 0])[0] or 0
                end_time = chunk.get("timestamp", [0, 0])[1] or start_time
                text = chunk.get("text", "").strip()
                
                if not text:
                    continue
                
                # Find and insert any frames that fall before this chunk
                while current_frame_idx < len(frame_timestamps):
                    frame_ts = frame_timestamps[current_frame_idx]
                    if frame_ts <= start_time:
                        frame = frame_lookup[frame_ts]
                        ts_display = frame.get("timestamp_display", self._format_ts(frame_ts))
                        filename = frame.get("filename", "")
                        
                        f.write(f"### 🖼️ Slide at {ts_display}\n\n")
                        f.write(f"![Slide at {ts_display}](slides/{filename})\n\n")
                        
                        # Add analysis if available
                        if filename in analysis_lookup:
                            analysis = analysis_lookup[filename]
                            
                            # Add OCR text
                            ocr_text = analysis.get("ocr_text", "").strip()
                            if ocr_text:
                                f.write(f"**📝 Text on slide:**\n> {ocr_text[:500]}\n\n")
                            
                            # Add vision analysis
                            vision = analysis.get("vision_analysis", "").strip()
                            if vision:
                                f.write(f"**🔍 Slide Analysis:**\n{vision}\n\n")
                        
                        f.write("---\n\n")
                        current_frame_idx += 1
                    else:
                        break
                
                # Write transcript chunk
                start_str = self._format_ts(start_time)
                end_str = self._format_ts(end_time)
                f.write(f"**[{start_str}]** ")
                f.write(f"[▶](video.mp4#t={int(start_time)}) ")
                f.write(f"{text}\n\n")
            
            # Add any remaining frames at the end
            while current_frame_idx < len(frame_timestamps):
                frame_ts = frame_timestamps[current_frame_idx]
                frame = frame_lookup[frame_ts]
                ts_display = frame.get("timestamp_display", self._format_ts(frame_ts))
                filename = frame.get("filename", "")
                
                f.write(f"### 🖼️ Slide at {ts_display}\n\n")
                f.write(f"![Slide at {ts_display}](slides/{filename})\n\n")
                
                # Add analysis for remaining frames too
                if filename in analysis_lookup:
                    analysis = analysis_lookup[filename]
                    ocr_text = analysis.get("ocr_text", "").strip()
                    if ocr_text:
                        f.write(f"**📝 Text on slide:**\n> {ocr_text[:500]}\n\n")
                    vision = analysis.get("vision_analysis", "").strip()
                    if vision:
                        f.write(f"**🔍 Slide Analysis:**\n{vision}\n\n")
                
                current_frame_idx += 1
        
        logger.info(f"Enhanced transcript saved to {enhanced_path}")
    
    def _prepare_notes_context(self, transcript_text: str, frames: list, slide_analyses: list = None) -> str:
        """
        Prepare context for notes generation with CUMULATIVE slide content.
        Each slide builds on the context from previous slides.
        """
        context_parts = []
        
        # Add slide OCR text with cumulative context
        if slide_analyses:
            context_parts.append("## EXTRACTED SLIDE CONTENT (cumulative)\n")
            cumulative_content = []  # Track content seen so far
            
            for i, analysis in enumerate(slide_analyses[:40], 1):  # Up to 40 slides
                ocr_text = analysis.get("ocr_text", "").strip()
                ts = analysis.get("timestamp_display", "")
                
                if ocr_text:
                    # Find NEW content (not in previous slides)
                    new_content = ocr_text
                    for prev in cumulative_content:
                        # Simple deduplication - skip if >70% overlap
                        if len(set(ocr_text.split()) & set(prev.split())) / max(len(ocr_text.split()), 1) > 0.7:
                            new_content = ""  # Skip duplicate
                            break
                    
                    if new_content:
                        context_parts.append(f"### Slide {i} ({ts})")
                        # Show new content + brief context from last slide
                        if cumulative_content:
                            context_parts.append(f"_Building on: {cumulative_content[-1][:100]}..._")
                        context_parts.append(new_content[:600])
                        context_parts.append("")
                        cumulative_content.append(ocr_text[:300])
            
            if len(slide_analyses) > 40:
                context_parts.append(f"\n... and {len(slide_analyses) - 40} more slides\n")
            
            context_parts.append("---\n")
        elif frames:
            context_parts.append(f"This lecture contains {len(frames)} visual slides at 30s intervals.\n")
            context_parts.append("---\n")
        
        # Add transcript
        context_parts.append("## TRANSCRIPT\n")
        context_parts.append(transcript_text)
        
        return "\n".join(context_parts)
    
    @staticmethod
    def _format_ts(seconds: float) -> str:
        """Format seconds to HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _create_index_file(self, recording_dir: Path, title: str, results: dict):
        """Create an Obsidian index file for the recording"""
        index_path = recording_dir / "index.md"
        
        content = f"""# {title}

**Processed:** {datetime.now().strftime("%Y-%m-%d %H:%M")}

---

## Media

- [▶ Watch Video](video.mp4)
- [📄 Transcript](transcript.md)

---

## Study Materials

- [📝 Lecture Notes](lecture_notes.md)
- [❓ Flashcards](qa_cards.md)
- [📋 Summary](summary.md)

---

## Slides

"""
        # Add slide gallery
        slides_dir = recording_dir / "slides"
        if slides_dir.exists():
            slides = sorted(slides_dir.glob("*.png"))
            for slide in slides[:10]:  # First 10 slides
                # Extract timestamp from filename (00_05_32.png -> 00:05:32)
                ts = slide.stem.replace("_", ":")
                content += f"![{ts}](slides/{slide.name})\n\n"
            
            if len(slides) > 10:
                content += f"\n*...and {len(slides) - 10} more slides in the slides/ folder*\n"
        
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"Created index file: {index_path}")
    
    def _create_lecture_viewer(self, recording_dir: Path, title: str, frames: list, slide_analyses: list = None):
        """Create an HTML lecture viewer with timeline, slides, and transcript"""
        viewer_path = recording_dir / "viewer.html"
        
        # Load transcript chunks if available
        transcript_chunks = []
        transcript_json = recording_dir / "transcript.json"
        if transcript_json.exists():
            with open(transcript_json, "r") as f:
                data = json.load(f)
                transcript_chunks = data.get("chunks", [])
        
        # Build slide data with OCR
        slides_data = []
        for i, frame in enumerate(frames):
            slide = {
                "timestamp": frame.get("timestamp", 0),
                "timestamp_display": frame.get("timestamp_display", ""),
                "filename": frame.get("filename", ""),
                "ocr_text": ""
            }
            if slide_analyses and i < len(slide_analyses):
                slide["ocr_text"] = slide_analyses[i].get("ocr_text", "")[:300]
            slides_data.append(slide)
        
        # Build transcript HTML with timestamps
        transcript_html = ""
        for chunk in transcript_chunks:
            start = chunk.get("timestamp", [0, 0])[0] or 0
            text = chunk.get("text", "").strip()
            if text:
                ts_display = self._format_ts(start)
                transcript_html += f'''
                <div class="transcript-chunk" data-time="{int(start)}">
                    <span class="timestamp">[{ts_display}]</span>
                    <span class="text">{text}</span>
                </div>'''
        
        # Build slides gallery HTML
        slides_html = ""
        for i, slide in enumerate(slides_data):
            slides_html += f'''
            <div class="slide-card" data-time="{int(slide['timestamp'])}">
                <img src="slides/{slide['filename']}" alt="Slide at {slide['timestamp_display']}" loading="lazy">
                <div class="slide-info">
                    <span class="slide-time">{slide['timestamp_display']}</span>
                    <span class="slide-num">#{i+1}</span>
                </div>
            </div>'''
        
        # Generate HTML
        html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Lecture Viewer</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: #1a1a1a; color: #e0e0e0; line-height: 1.6;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        header {{ padding: 20px 0; border-bottom: 1px solid #333; margin-bottom: 20px; }}
        h1 {{ font-size: 1.8rem; font-weight: 600; }}
        .subtitle {{ color: #888; font-size: 0.9rem; margin-top: 5px; }}
        
        .tabs {{ display: flex; gap: 10px; margin-bottom: 20px; }}
        .tab {{ padding: 10px 20px; background: #2a2a2a; border: none; color: #888;
                border-radius: 8px; cursor: pointer; font-size: 0.9rem; }}
        .tab.active {{ background: #3b82f6; color: white; }}
        .tab:hover {{ background: #333; }}
        .tab.active:hover {{ background: #3b82f6; }}
        
        .panel {{ display: none; }}
        .panel.active {{ display: block; }}
        
        /* Slides Grid */
        .slides-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 15px; }}
        .slide-card {{ background: #2a2a2a; border-radius: 8px; overflow: hidden; cursor: pointer; }}
        .slide-card:hover {{ transform: scale(1.02); }}
        .slide-card img {{ width: 100%; height: 160px; object-fit: cover; }}
        .slide-info {{ padding: 10px; display: flex; justify-content: space-between; }}
        .slide-time {{ color: #3b82f6; font-size: 0.85rem; }}
        .slide-num {{ color: #666; font-size: 0.8rem; }}
        
        /* Transcript */
        .transcript-chunk {{ padding: 12px 15px; border-left: 3px solid transparent; margin-bottom: 5px;
                            background: #222; border-radius: 0 8px 8px 0; }}
        .transcript-chunk:hover {{ border-left-color: #3b82f6; background: #262626; }}
        .timestamp {{ color: #3b82f6; font-size: 0.8rem; margin-right: 10px; font-family: monospace; }}
        .text {{ color: #ccc; }}
        
        /* Slide Modal */
        .modal {{ display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                 background: rgba(0,0,0,0.9); z-index: 1000; align-items: center; justify-content: center; }}
        .modal.active {{ display: flex; }}
        .modal img {{ max-width: 90%; max-height: 90%; border-radius: 8px; }}
        .modal-close {{ position: absolute; top: 20px; right: 30px; color: white; font-size: 2rem;
                       cursor: pointer; }}
        
        /* Timeline */
        .timeline {{ display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 20px; }}
        .timeline-dot {{ width: 30px; height: 8px; background: #333; border-radius: 4px; cursor: pointer; }}
        .timeline-dot:hover {{ background: #3b82f6; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📚 {title}</h1>
            <p class="subtitle">{len(frames)} slides • {len(transcript_chunks)} transcript segments</p>
        </header>
        
        <div class="tabs">
            <button class="tab active" data-panel="slides">🖼️ Slides ({len(frames)})</button>
            <button class="tab" data-panel="transcript">📝 Transcript</button>
        </div>
        
        <div class="timeline" id="timeline"></div>
        
        <div id="slides" class="panel active">
            <div class="slides-grid">{slides_html}</div>
        </div>
        
        <div id="transcript" class="panel">
            {transcript_html}
        </div>
    </div>
    
    <div class="modal" id="modal">
        <span class="modal-close">&times;</span>
        <img src="" alt="Slide preview">
    </div>
    
    <script>
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {{
            tab.addEventListener('click', () => {{
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(tab.dataset.panel).classList.add('active');
            }});
        }});
        
        // Slide modal
        const modal = document.getElementById('modal');
        document.querySelectorAll('.slide-card img').forEach(img => {{
            img.addEventListener('click', () => {{
                modal.querySelector('img').src = img.src;
                modal.classList.add('active');
            }});
        }});
        modal.addEventListener('click', () => modal.classList.remove('active'));
        
        // Build timeline
        const slides = {json.dumps([{"t": s["timestamp"], "f": s["filename"]} for s in slides_data])};
        const timeline = document.getElementById('timeline');
        slides.forEach(s => {{
            const dot = document.createElement('div');
            dot.className = 'timeline-dot';
            dot.title = new Date(s.t * 1000).toISOString().substr(11, 8);
            dot.addEventListener('click', () => {{
                const card = document.querySelector(`.slide-card[data-time="${{Math.floor(s.t)}}"]`);
                if (card) card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }});
            timeline.appendChild(dot);
        }});
    </script>
</body>
</html>'''
        
        with open(viewer_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        logger.info(f"Created lecture viewer: {viewer_path}")


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    pipeline = ProcessingPipeline(
        output_base="../output",
        whisper_model="medium",
        ollama_model="gpt-oss:20b"
    )
    
    # Test with sample video
    test_video = "../scaler_videos/full_video.mp4"
    if os.path.exists(test_video):
        results = pipeline.process(
            test_video,
            title="Test Lecture",
            skip_notes=True  # Skip LLM for quick test
        )
        print(f"Results: {json.dumps(results, indent=2)}")
    else:
        print(f"Test video not found: {test_video}")
