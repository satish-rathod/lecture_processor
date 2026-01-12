#!/usr/bin/env python3
"""
Scaler Companion - Whisper Transcriber
Transcribes audio from video files using OpenAI Whisper (official package)
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Callable
import json

import whisper
import torch

logger = logging.getLogger(__name__)


class WhisperTranscriber:
    """Transcribes audio using OpenAI Whisper"""
    
    # Model configurations
    MODELS = ["tiny", "base", "small", "medium", "large"]
    
    def __init__(self, model_name: str = "medium"):
        """
        Initialize the transcriber
        
        Args:
            model_name: Which Whisper model to use (tiny, base, small, medium, large)
        """
        self.model_name = model_name if model_name in self.MODELS else "medium"
        self.model = None
        self.progress_callback: Optional[Callable] = None
        
        # Determine device
        if torch.backends.mps.is_available():
            self.device = "mps"
            logger.info("Using MPS (Metal) acceleration")
        elif torch.cuda.is_available():
            self.device = "cuda"
            logger.info("Using CUDA acceleration")
        else:
            self.device = "cpu"
            logger.info("Using CPU")
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates: callback(current, total, message)"""
        self.progress_callback = callback
    
    def _update_progress(self, current: int, total: int, message: str = ""):
        """Update progress via callback if set"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def load_model(self):
        """Load the Whisper model"""
        if self.model is not None:
            logger.info("Model already loaded")
            return
        
        logger.info(f"Loading Whisper model: {self.model_name}")
        self._update_progress(0, 100, f"Loading model {self.model_name}...")
        
        # Load model - MPS has issues, use CPU for inference
        self.model = whisper.load_model(self.model_name, device="cpu")
        
        logger.info("Model loaded successfully")
        self._update_progress(100, 100, "Model loaded")
    
    def extract_audio(self, video_path: str, output_dir: str) -> str:
        """
        Extract audio from video file using FFmpeg
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save audio file
            
        Returns:
            Path to extracted audio file
        """
        video_path = Path(video_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        audio_path = output_dir / "audio.wav"
        
        logger.info(f"Extracting audio from {video_path}")
        self._update_progress(0, 100, "Extracting audio...")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # PCM 16-bit
            "-ar", "16000",  # 16kHz sample rate (Whisper expects this)
            "-ac", "1",  # Mono
            str(audio_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr}")
            raise RuntimeError(f"Failed to extract audio: {result.stderr}")
        
        logger.info(f"Audio extracted to {audio_path}")
        self._update_progress(100, 100, "Audio extracted")
        
        return str(audio_path)
    
    def transcribe(
        self,
        audio_path: str,
        language: str = "en"
    ) -> dict:
        """
        Transcribe audio file
        
        Args:
            audio_path: Path to audio file
            language: Language code
            
        Returns:
            Dict with 'text' and 'chunks' (segments)
        """
        if self.model is None:
            self.load_model()
        
        logger.info(f"Transcribing {audio_path}")
        self._update_progress(0, 100, "Transcribing audio...")
        
        # Run transcription with word_timestamps for better alignment
        result = self.model.transcribe(
            audio_path,
            language=language,
            verbose=False,
            task="transcribe",
            fp16=False  # CPU doesn't support fp16
        )
        
        # Convert segments to our format
        chunks = []
        for segment in result.get("segments", []):
            chunks.append({
                "text": segment["text"].strip(),
                "timestamp": [segment["start"], segment["end"]]
            })
        
        output = {
            "text": result["text"],
            "chunks": chunks,
            "language": result.get("language", language)
        }
        
        logger.info("Transcription complete")
        self._update_progress(100, 100, "Transcription complete")
        
        return output
    
    def transcribe_video(
        self,
        video_path: str,
        output_dir: str,
        language: str = "en"
    ) -> dict:
        """
        Complete pipeline: extract audio from video and transcribe
        
        Args:
            video_path: Path to video file
            output_dir: Directory for outputs
            language: Language code
            
        Returns:
            Transcription result with text and timestamps
        """
        output_dir = Path(output_dir)
        
        # Extract audio
        audio_path = self.extract_audio(video_path, output_dir)
        
        # Transcribe
        result = self.transcribe(audio_path, language=language)
        
        # Save transcript
        self._save_transcript(result, output_dir)
        
        return result
    
    def _save_transcript(self, result: dict, output_dir: Path):
        """Save transcript in multiple formats"""
        output_dir = Path(output_dir)
        
        # Save full text
        text_path = output_dir / "transcript.txt"
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(result["text"])
        
        # Save JSON with timestamps
        json_path = output_dir / "transcript.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        # Save Markdown with timestamps
        md_path = output_dir / "transcript.md"
        self._save_markdown_transcript(result, md_path)
        
        logger.info(f"Transcripts saved to {output_dir}")
    
    def _save_markdown_transcript(self, result: dict, output_path: Path):
        """Save transcript as Obsidian-compatible Markdown"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Transcript\n\n")
            
            if "chunks" in result and result["chunks"]:
                for chunk in result["chunks"]:
                    start_time = chunk.get("timestamp", [0, 0])[0] or 0
                    end_time = chunk.get("timestamp", [0, 0])[1] or start_time
                    text = chunk.get("text", "").strip()
                    
                    if not text:
                        continue
                    
                    # Format timestamp
                    start_str = self._format_timestamp(start_time)
                    end_str = self._format_timestamp(end_time)
                    
                    # Write chunk with video link
                    f.write(f"## {start_str} - {end_str}\n")
                    f.write(f"[▶ Play](video.mp4#t={int(start_time)})\n\n")
                    f.write(f"{text}\n\n")
            else:
                # No chunks, just write full text
                f.write(result.get("text", ""))
    
    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds to HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    transcriber = WhisperTranscriber(model_name="medium")
    
    # Test with a video file
    test_video = "../scaler_videos/full_video.mp4"
    if os.path.exists(test_video):
        result = transcriber.transcribe_video(
            test_video,
            output_dir="../output/test_transcription"
        )
        print(f"Transcribed {len(result.get('text', ''))} characters")
        print(f"First 500 chars: {result.get('text', '')[:500]}")
    else:
        print(f"Test video not found: {test_video}")
