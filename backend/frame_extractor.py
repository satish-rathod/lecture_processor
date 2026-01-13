#!/usr/bin/env python3
"""
Scaler Companion - Frame Extractor
Extracts key frames (slides) from lecture videos using FFmpeg
Uses hybrid approach: scene detection + interval-based for comprehensive coverage
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Callable, List
import json

try:
    from PIL import Image
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

logger = logging.getLogger(__name__)


class FrameExtractor:
    """Extracts key frames from video based on scene changes + intervals"""
    
    def __init__(
        self,
        scene_threshold: float = 0.15,  # Lower = more sensitive (was 0.3)
        min_interval: float = 3.0,       # Minimum 3 seconds between frames
        fixed_interval: float = 30.0,    # Also extract every 30 seconds as backup
        max_frames: int = 500,
        hash_threshold: int = 8,         # Lower = more strict duplicate removal
        skip_intro: float = 0.0,         # Skip first N seconds (video pre-trimmed)
        skip_outro: float = 0.0          # Skip last N seconds (video pre-trimmed)
    ):
        """
        Initialize the frame extractor
        
        Args:
            scene_threshold: FFmpeg scene detection threshold (0.0-1.0)
                            Lower = more sensitive (0.15 recommended for lectures)
            min_interval: Minimum seconds between scene-detected frames
            fixed_interval: Extract a frame every N seconds regardless of scene changes
            max_frames: Maximum number of frames to extract
            hash_threshold: Perceptual hash difference threshold for duplicates
            skip_intro: Skip first N seconds (branding/intro frames)
            skip_outro: Skip last N seconds (credits/outro frames)
        """
        self.scene_threshold = scene_threshold
        self.min_interval = min_interval
        self.fixed_interval = fixed_interval
        self.max_frames = max_frames
        self.hash_threshold = hash_threshold
        self.skip_intro = skip_intro
        self.skip_outro = skip_outro
        self.progress_callback: Optional[Callable] = None
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates: callback(current, total, message)"""
        self.progress_callback = callback
    
    def _update_progress(self, current: int, total: int, message: str = ""):
        """Update progress via callback if set"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds using FFprobe"""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"FFprobe error: {result.stderr}")
            return 0.0
        
        try:
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return 0.0
    
    def detect_scene_changes(self, video_path: str) -> List[float]:
        """
        Detect scene changes using FFmpeg
        
        Returns:
            List of timestamps (in seconds) where scene changes occur
        """
        logger.info(f"Detecting scene changes in {video_path} (threshold={self.scene_threshold})")
        self._update_progress(0, 100, "Detecting scene changes...")
        
        # Use FFmpeg's select filter with scene detection
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vf", f"select='gt(scene,{self.scene_threshold})',showinfo",
            "-vsync", "vfr",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Parse timestamps from stderr (showinfo outputs there)
        timestamps = [0.0]  # Always include first frame
        
        for line in result.stderr.split('\n'):
            if 'pts_time:' in line:
                try:
                    # Extract pts_time value
                    pts_part = line.split('pts_time:')[1].split()[0]
                    timestamp = float(pts_part)
                    
                    # Check minimum interval
                    if timestamps and (timestamp - timestamps[-1]) >= self.min_interval:
                        timestamps.append(timestamp)
                        
                    if len(timestamps) >= self.max_frames:
                        break
                except (IndexError, ValueError):
                    continue
        
        logger.info(f"Detected {len(timestamps)} scene changes")
        self._update_progress(100, 100, f"Found {len(timestamps)} scenes")
        
        return timestamps
    
    def generate_interval_timestamps(self, duration: float) -> List[float]:
        """
        Generate fixed-interval timestamps, respecting skip_intro and skip_outro
        
        Args:
            duration: Video duration in seconds
            
        Returns:
            List of timestamps at fixed intervals
        """
        timestamps = []
        # Start after intro
        t = self.skip_intro
        # End before outro
        end_time = max(0, duration - self.skip_outro)
        
        while t < end_time and len(timestamps) < self.max_frames:
            timestamps.append(t)
            t += self.fixed_interval
        return timestamps
    
    def merge_timestamps(self, scene_ts: List[float], interval_ts: List[float], duration: float = 0) -> List[float]:
        """
        Merge scene-detected and interval timestamps, removing duplicates
        Also filters out intro/outro frames
        
        Args:
            scene_ts: Timestamps from scene detection
            interval_ts: Timestamps from fixed intervals
            duration: Video duration for outro filtering
            
        Returns:
            Merged and sorted list of unique timestamps
        """
        # Calculate valid time range
        min_time = self.skip_intro
        max_time = duration - self.skip_outro if duration > 0 else float('inf')
        
        # Filter scene timestamps to valid range
        filtered_scene = [ts for ts in scene_ts if min_time <= ts <= max_time]
        
        # Combine both lists
        all_ts = set(filtered_scene)
        
        # Add interval timestamps, but only if not too close to existing ones
        for ts in interval_ts:
            if ts < min_time or ts > max_time:
                continue
            too_close = any(abs(ts - existing) < self.min_interval for existing in all_ts)
            if not too_close:
                all_ts.add(ts)
        
        # Sort and return
        merged = sorted(all_ts)
        logger.info(f"Merged timestamps: {len(filtered_scene)} scene + {len(interval_ts)} interval = {len(merged)} total "
                   f"(skipped intro={self.skip_intro}s, outro={self.skip_outro}s)")
        
        return merged[:self.max_frames]
    
    def extract_frames_at_timestamps(
        self,
        video_path: str,
        output_dir: str,
        timestamps: List[float]
    ) -> List[dict]:
        """
        Extract frames at specific timestamps
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save frames
            timestamps: List of timestamps to extract
            
        Returns:
            List of dicts with frame info (path, timestamp)
        """
        output_dir = Path(output_dir)
        slides_dir = output_dir / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)
        
        frames = []
        total = len(timestamps)
        
        logger.info(f"Extracting {total} frames")
        
        for i, timestamp in enumerate(timestamps):
            self._update_progress(i, total, f"Extracting frame {i+1}/{total}")
            
            # Format timestamp for filename
            ts_str = self._format_timestamp_filename(timestamp)
            frame_path = slides_dir / f"{ts_str}.png"
            
            # Extract single frame
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(timestamp),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",  # High quality
                str(frame_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and frame_path.exists():
                frames.append({
                    "path": str(frame_path),
                    "timestamp": timestamp,
                    "filename": frame_path.name,
                    "timestamp_display": self._format_timestamp_display(timestamp)
                })
            else:
                logger.warning(f"Failed to extract frame at {timestamp}s")
        
        self._update_progress(total, total, "Frame extraction complete")
        logger.info(f"Extracted {len(frames)} frames")
        
        return frames
    
    def remove_duplicate_frames(self, frames: List[dict]) -> List[dict]:
        """
        Remove duplicate/similar frames using perceptual hashing
        
        Args:
            frames: List of frame info dicts
            
        Returns:
            Filtered list with duplicates removed
        """
        if not IMAGEHASH_AVAILABLE:
            logger.warning("imagehash not available, skipping duplicate removal")
            return frames
        
        if not frames:
            return frames
        
        logger.info("Removing duplicate frames...")
        self._update_progress(0, 100, "Removing duplicates...")
        
        unique_frames = []
        seen_hashes = []
        
        for i, frame in enumerate(frames):
            try:
                img = Image.open(frame["path"])
                current_hash = imagehash.phash(img)
                
                # Check against all previous frames (not just the last one)
                is_duplicate = False
                for prev_hash in seen_hashes:
                    if (current_hash - prev_hash) <= self.hash_threshold:
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    unique_frames.append(frame)
                    seen_hashes.append(current_hash)
                else:
                    # Remove duplicate file
                    os.remove(frame["path"])
                    logger.debug(f"Removed duplicate: {frame['filename']}")
                    
            except Exception as e:
                logger.warning(f"Error processing {frame['path']}: {e}")
                unique_frames.append(frame)  # Keep on error
        
        logger.info(f"Kept {len(unique_frames)} unique frames (removed {len(frames) - len(unique_frames)})")
        self._update_progress(100, 100, "Duplicate removal complete")
        
        return unique_frames
    
    def extract_frames(
        self,
        video_path: str,
        output_dir: str,
        remove_duplicates: bool = True,
        use_hybrid: bool = True
    ) -> List[dict]:
        """
        Complete pipeline: detect scenes + intervals, extract frames, remove duplicates
        
        Args:
            video_path: Path to video file
            output_dir: Directory for outputs
            remove_duplicates: Whether to remove similar frames
            use_hybrid: Use both scene detection and fixed intervals
            
        Returns:
            List of extracted frame info dicts
        """
        # Get video duration for interval-based extraction
        duration = self.get_video_duration(video_path)
        
        # Detect scene changes
        scene_timestamps = self.detect_scene_changes(video_path)
        
        if use_hybrid and duration > 0:
            # Also generate interval-based timestamps
            interval_timestamps = self.generate_interval_timestamps(duration)
            timestamps = self.merge_timestamps(scene_timestamps, interval_timestamps, duration)
        else:
            # Filter scene timestamps for intro/outro
            min_time = self.skip_intro
            max_time = duration - self.skip_outro if duration > 0 else float('inf')
            timestamps = [ts for ts in scene_timestamps if min_time <= ts <= max_time]
        
        # Extract frames
        frames = self.extract_frames_at_timestamps(video_path, output_dir, timestamps)
        
        # Remove duplicates
        if remove_duplicates and IMAGEHASH_AVAILABLE:
            frames = self.remove_duplicate_frames(frames)
        
        # Save metadata
        self._save_metadata(frames, output_dir, duration)
        
        return frames
    
    def _save_metadata(self, frames: List[dict], output_dir: str, duration: float = 0):
        """Save frame metadata as JSON"""
        output_dir = Path(output_dir)
        metadata_path = output_dir / "slides_metadata.json"
        
        with open(metadata_path, "w") as f:
            json.dump({
                "total_frames": len(frames),
                "video_duration": duration,
                "frames": frames
            }, f, indent=2)
        
        logger.info(f"Metadata saved to {metadata_path}")
    
    @staticmethod
    def _format_timestamp_filename(seconds: float) -> str:
        """Format seconds to HH_MM_SS for filename"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}_{minutes:02d}_{secs:02d}"
    
    @staticmethod
    def _format_timestamp_display(seconds: float) -> str:
        """Format seconds to HH:MM:SS for display"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    extractor = FrameExtractor(
        scene_threshold=0.15,  # More sensitive
        min_interval=3.0,
        fixed_interval=30.0   # Every 30 seconds as backup
    )
    
    # Test with a video file
    test_video = "../scaler_videos/full_video.mp4"
    if os.path.exists(test_video):
        frames = extractor.extract_frames(
            test_video,
            output_dir="../output/test_frames",
            use_hybrid=True
        )
        print(f"Extracted {len(frames)} frames")
        for f in frames[:10]:
            print(f"  - {f['timestamp_display']}: {f['filename']}")
    else:
        print(f"Test video not found: {test_video}")
