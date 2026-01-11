#!/usr/bin/env python3
"""
Scaler Companion - Video Downloader
Refactored from main.py for use as a module
"""

import os
import subprocess
import requests
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class VideoDownloader:
    """Downloads HLS video chunks and processes them"""
    
    def __init__(self, output_dir: str = "scaler_videos", clip_duration: int = 120):
        """
        Initialize the downloader
        
        Args:
            output_dir: Directory to save videos
            clip_duration: Duration of each clip in seconds (default: 120 = 2 minutes)
        """
        self.output_dir = Path(output_dir)
        self.clips_dir = self.output_dir / "clips"
        self.chunks_dir = self.output_dir / "chunks"
        self.clip_duration = clip_duration
        
        # Create directories
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        self.clips_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Output directory: {self.output_dir}")
        
        # Download progress callback
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """Set callback for progress updates: callback(current, total, message)"""
        self.progress_callback = callback
    
    def _update_progress(self, current: int, total: int, message: str = ""):
        """Update progress via callback if set"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def _build_chunk_url_from_format(
        self,
        base_url: str,
        chunk_num: int,
        format_info: dict,
        key_pair_id: str = None,
        policy: str = None,
        signature: str = None
    ) -> str:
        """Build a chunk URL using format_info dict with proper auth params"""
        from urllib.parse import quote
        
        # Ensure base URL ends with /
        base_url = base_url.rstrip('/') + '/'
        
        # Generate filename using format info
        if format_info:
            prefix = format_info["prefix"]
            padding = format_info["padding"]
            suffix = format_info["suffix"]
            if padding > 0:
                chunk_filename = f"{prefix}{chunk_num:0{padding}d}{suffix}"
            else:
                chunk_filename = f"{prefix}{chunk_num}{suffix}"
        else:
            # Fallback to default format
            chunk_filename = f"data{chunk_num}.ts"
        
        url = f"{base_url}{chunk_filename}"
        
        # Build auth params with proper URL encoding
        params = []
        if key_pair_id:
            params.append(f"Key-Pair-Id={key_pair_id}")
        if policy:
            # Policy is Base64 and may contain special chars - URL encode it
            params.append(f"Policy={quote(policy, safe='')}")
        if signature:
            # Signature is Base64 and may contain special chars - URL encode it
            params.append(f"Signature={quote(signature, safe='')}")
        
        if params:
            url += "?" + "&".join(params)
        
        return url
    
    def _try_download_chunk(
        self,
        session,
        base_url: str,
        chunk_num: int,
        key_pair_id: str = None,
        policy: str = None,
        signature: str = None
    ) -> tuple:
        """
        Try downloading a chunk with multiple naming patterns.
        Returns: (content, format_info_dict) or (None, None)
        
        format_info_dict contains:
            - prefix: e.g., "data"
            - padding: number of digits for zero-padding (0 means no padding)
            - suffix: e.g., ".ts"
        """
        from urllib.parse import quote
        
        # Patterns to try: (prefix, padding_digits)
        # We try different combinations ordered by likelihood for Scaler
        pattern_configs = [
            ("data", 6),    # data000090.ts - 6-digit padding (detected from your logs!)
            ("data", 0),    # data90.ts - no padding
            ("data", 5),    # data00090.ts - 5-digit padding  
            ("data", 4),    # data0090.ts - 4-digit padding
            ("chunk_", 0),  # chunk_90.ts
            ("segment", 0), # segment90.ts
        ]
        
        base_url = base_url.rstrip('/') + '/'
        
        for prefix, padding in pattern_configs:
            # Format the chunk number with appropriate padding
            if padding > 0:
                formatted_num = f"{chunk_num:0{padding}d}"
            else:
                formatted_num = str(chunk_num)
            
            filename = f"{prefix}{formatted_num}.ts"
            url = f"{base_url}{filename}"
            
            # Add auth params
            params = []
            if key_pair_id:
                params.append(f"Key-Pair-Id={key_pair_id}")
            if policy:
                params.append(f"Policy={quote(policy, safe='')}")
            if signature:
                params.append(f"Signature={quote(signature, safe='')}")
            
            if params:
                url += "?" + "&".join(params)
            
            try:
                response = session.get(url, timeout=15)
                if response.ok and len(response.content) > 1000:  # Valid chunk should be > 1KB
                    # Return format info instead of literal filename
                    format_info = {
                        "prefix": prefix,
                        "padding": padding,
                        "suffix": ".ts"
                    }
                    logger.info(f"Found working pattern: {prefix} with {padding}-digit padding")
                    return response.content, format_info
            except requests.RequestException:
                continue
        
        return None, None

    def download_chunks(
        self, 
        base_url: str, 
        start_chunk: int, 
        end_chunk: int, 
        key_pair_id: str = None, 
        policy: str = None, 
        signature: str = None
    ) -> bool:
        """
        Download video chunks from the server
        
        Args:
            base_url: Base URL of chunks (e.g., https://domain.com/data)
            start_chunk: Starting chunk number
            end_chunk: Ending chunk number
            key_pair_id: CloudFront key pair ID for authentication
            policy: CloudFront Policy
            signature: CloudFront Signature
            
        Returns:
            True if all chunks downloaded successfully
        """
        logger.info(f"Starting download of chunks {start_chunk} to {end_chunk}")
        logger.info(f"Base URL: {base_url}")
        
        # Normalize base URL
        base_url = base_url.rstrip('/') + '/'
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        })
        
        total_chunks = end_chunk - start_chunk + 1
        success_count = 0
        format_info = None  # Will be set after first successful download: {prefix, padding, suffix}
        consecutive_failures = 0
        max_consecutive_failures = 10  # Stop if too many failures in a row
        
        for i in range(start_chunk, end_chunk + 1):
            # Generate filename using detected format or default
            if format_info:
                prefix = format_info["prefix"]
                padding = format_info["padding"]
                suffix = format_info["suffix"]
                if padding > 0:
                    chunk_filename = f"{prefix}{i:0{padding}d}{suffix}"
                else:
                    chunk_filename = f"{prefix}{i}{suffix}"
            else:
                chunk_filename = f"data{i}.ts"
            
            chunk_path = self.chunks_dir / chunk_filename
            
            # Skip if already downloaded
            if chunk_path.exists() and chunk_path.stat().st_size > 1000:
                logger.info(f"✓ Chunk {i} already exists, skipping...")
                success_count += 1
                consecutive_failures = 0
                self._update_progress(i - start_chunk + 1, total_chunks, f"Chunk {i} (cached)")
                continue
            
            self._update_progress(i - start_chunk + 1, total_chunks, f"Downloading chunk {i}")
            
            # If we don't have a format yet, try multiple formats
            if format_info is None:
                content, detected_format = self._try_download_chunk(
                    session, base_url, i, key_pair_id, policy, signature
                )
                if content and detected_format:
                    format_info = detected_format
                    logger.info(f"✓ Detected format: prefix='{format_info['prefix']}', padding={format_info['padding']}")
                    
                    # Generate filename using detected format
                    prefix = format_info["prefix"]
                    padding = format_info["padding"]
                    suffix = format_info["suffix"]
                    if padding > 0:
                        actual_filename = f"{prefix}{i:0{padding}d}{suffix}"
                    else:
                        actual_filename = f"{prefix}{i}{suffix}"
                    
                    chunk_path = self.chunks_dir / actual_filename
                    
                    with open(chunk_path, 'wb') as f:
                        f.write(content)
                    
                    logger.info(f"✓ Downloaded: {actual_filename} ({len(content) / 1024:.1f} KB)")
                    success_count += 1
                    consecutive_failures = 0
                    continue
            
            # Use detected format for remaining chunks
            url = self._build_chunk_url_from_format(base_url, i, format_info, key_pair_id, policy, signature)
            
            try:
                response = session.get(url, timeout=30)
                response.raise_for_status()
                
                if len(response.content) < 1000:
                    logger.warning(f"Chunk {i} seems too small ({len(response.content)} bytes), may be invalid")
                
                with open(chunk_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"✓ Downloaded: {chunk_filename} ({len(response.content) / 1024:.1f} KB)")
                success_count += 1
                consecutive_failures = 0
                
            except requests.RequestException as e:
                logger.error(f"✗ Failed to download chunk {i}: {e}")
                consecutive_failures += 1
                
                # If too many consecutive failures, we might be past the end
                if consecutive_failures >= max_consecutive_failures:
                    logger.warning(f"Too many consecutive failures, stopping at chunk {i}")
                    break
                continue
        
        logger.info(f"Downloaded {success_count}/{total_chunks} chunks")
        return success_count > 0
    
    def merge_chunks_to_video(self, output_filename: str = "full_video.mp4") -> str:
        """
        Merge all downloaded chunks into a single video file
        
        Args:
            output_filename: Name of output video file
            
        Returns:
            Path to merged video file, or None if failed
        """
        output_path = self.output_dir / output_filename
        
        # Get list of all chunks, sorted
        chunks = sorted([f for f in self.chunks_dir.iterdir() if f.suffix == '.ts'])
        
        if not chunks:
            logger.error("No chunks found to merge!")
            return None
        
        logger.info(f"Merging {len(chunks)} chunks into single video...")
        
        # Create concat file
        concat_file = self.output_dir / "concat.txt"
        with open(concat_file, 'w') as f:
            for chunk in chunks:
                f.write(f"file '{chunk.absolute()}'\n")
        
        # Merge using FFmpeg
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-y',
            str(output_path)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"✓ Video merged successfully: {output_path}")
            return str(output_path)
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ FFmpeg merge failed: {e}")
            return None
    
    def split_video_into_clips(self, video_path: str, output_prefix: str = "clip") -> list:
        """
        Split video into clips of specified duration
        
        Args:
            video_path: Path to the video file to split
            output_prefix: Prefix for output clip files
            
        Returns:
            List of created clip paths
        """
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return []
        
        logger.info(f"Splitting video into {self.clip_duration}s clips...")
        
        # Get video duration
        duration_cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_path)
        ]
        
        try:
            result = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
            total_duration = float(result.stdout.strip())
            logger.info(f"Video duration: {total_duration:.1f}s ({total_duration/60:.1f}min)")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get video duration: {e}")
            return []
        
        # Calculate number of clips
        num_clips = int(total_duration / self.clip_duration) + 1
        logger.info(f"Creating {num_clips} clips...")
        
        created_clips = []
        
        for i in range(num_clips):
            start_time = i * self.clip_duration
            output_clip = self.clips_dir / f"{output_prefix}_{i+1:03d}.mp4"
            
            cmd = [
                'ffmpeg',
                '-i', str(video_path),
                '-ss', str(start_time),
                '-t', str(self.clip_duration),
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-c:a', 'aac',
                '-q:v', '5',
                '-y',
                str(output_clip)
            ]
            
            try:
                self._update_progress(i + 1, num_clips, f"Creating clip {i + 1}")
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info(f"✓ Created: {output_clip}")
                created_clips.append(str(output_clip))
            except subprocess.CalledProcessError as e:
                logger.error(f"✗ Failed to create clip {i+1}: {e}")
                continue
        
        logger.info(f"✓ Created {len(created_clips)} clips in: {self.clips_dir}")
        return created_clips
    
    def download_and_process(
        self, 
        base_url: str, 
        start_chunk: int, 
        end_chunk: int,
        key_pair_id: str = None,
        policy: str = None,
        signature: str = None
    ) -> dict:
        """
        Complete pipeline: download → merge → split
        
        Returns:
            Dict with results including paths to outputs
        """
        logger.info("=" * 60)
        logger.info("STARTING VIDEO DOWNLOAD & PROCESSING PIPELINE")
        logger.info("=" * 60)
        
        result = {
            "success": False,
            "chunks_downloaded": 0,
            "full_video_path": None,
            "clips": []
        }
        
        # Step 1: Download chunks
        if not self.download_chunks(base_url, start_chunk, end_chunk, key_pair_id, policy, signature):
            logger.error("Failed to download chunks!")
            return result
        
        result["chunks_downloaded"] = len(list(self.chunks_dir.glob("*.ts")))
        
        # Step 2: Merge chunks
        full_video_path = self.merge_chunks_to_video()
        if not full_video_path:
            logger.error("Failed to merge chunks!")
            return result
        
        result["full_video_path"] = full_video_path
        
        # Step 3: Split into clips
        clips = self.split_video_into_clips(full_video_path)
        result["clips"] = clips
        
        result["success"] = True
        
        logger.info("=" * 60)
        logger.info("✓ PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info(f"Full video: {full_video_path}")
        logger.info(f"Clips: {len(clips)}")
        logger.info("=" * 60)
        
        return result
