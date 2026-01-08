#!/usr/bin/env python3
"""
Scaler Academy Video Downloader & Converter
Downloads HLS video chunks and splits them into 2-minute clips
"""

import os
import subprocess
import requests
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class VideoDownloader:
    def __init__(self, output_dir="scaler_videos", clip_duration=120):
        """
        Initialize the downloader
        
        Args:
            output_dir: Directory to save videos
            clip_duration: Duration of each clip in seconds (default: 120 = 2 minutes)
        """
        self.output_dir = output_dir
        self.clips_dir = os.path.join(output_dir, "clips")
        self.chunks_dir = os.path.join(output_dir, "chunks")
        self.clip_duration = clip_duration
        
        # Create directories
        os.makedirs(self.chunks_dir, exist_ok=True)
        os.makedirs(self.clips_dir, exist_ok=True)
        
        logger.info(f"Output directory: {self.output_dir}")
    
    def download_chunks(self, base_url, start_chunk, end_chunk, key_pair_id=None, policy=None, signature=None):
        """
        Download video chunks from the server
        
        Args:
            base_url: Base URL of chunks (e.g., https://domain.com/data)
            start_chunk: Starting chunk number (e.g., 25)
            end_chunk: Ending chunk number (e.g., 38)
            key_pair_id: CloudFront key pair ID for authentication
            policy: CloudFront Policy
            signature: CloudFront Signature
        """
        logger.info(f"Starting download of chunks {start_chunk} to {end_chunk}")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        })
        
        total_chunks = end_chunk - start_chunk + 1
        
        for i in range(start_chunk, end_chunk + 1):
            chunk_num = f"{i:06d}"
            chunk_filename = f"data{chunk_num}.ts"
            chunk_path = os.path.join(self.chunks_dir, chunk_filename)
            
            # Skip if already downloaded
            if os.path.exists(chunk_path):
                logger.info(f"✓ Chunk {i} already exists, skipping...")
                continue
            
            # Build URL
            url = f"{base_url}data{chunk_num}.ts"
            params = []
            if key_pair_id:
                params.append(f"Key-Pair-Id={key_pair_id}")
            if policy:
                params.append(f"Policy={policy}")
            if signature:
                params.append(f"Signature={signature}")
                
            if params:
                url += "?" + "&".join(params)
            
            try:
                logger.info(f"Downloading chunk {i}/{total_chunks}...")
                response = session.get(url, timeout=30)
                response.raise_for_status()
                
                with open(chunk_path, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"✓ Downloaded: {chunk_filename} ({len(response.content) / 1024:.1f} KB)")
                
            except requests.RequestException as e:
                logger.error(f"✗ Failed to download chunk {i}: {e}")
                continue
        
        logger.info("✓ All chunks downloaded successfully!")
    
    def merge_chunks_to_video(self, output_filename="full_video.mp4"):
        """
        Merge all downloaded chunks into a single video file
        
        Args:
            output_filename: Name of output video file
        """
        output_path = os.path.join(self.output_dir, output_filename)
        
        # Get list of all chunks, sorted
        chunks = sorted([f for f in os.listdir(self.chunks_dir) if f.endswith('.ts')])
        
        if not chunks:
            logger.error("No chunks found to merge!")
            return None
        
        logger.info(f"Merging {len(chunks)} chunks into single video...")
        
        # Create concat file
        concat_file = os.path.join(self.output_dir, "concat.txt")
        with open(concat_file, 'w') as f:
            for chunk in chunks:
                chunk_path = os.path.join(self.chunks_dir, chunk)
                abs_chunk_path = os.path.abspath(chunk_path)
                f.write(f"file '{abs_chunk_path}'\n")
        
        # Merge using FFmpeg
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            '-bsf:a', 'aac_adtstoasc',
            '-y',  # Overwrite output file
            output_path
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"✓ Video merged successfully: {output_path}")
            return output_path
        except subprocess.CalledProcessError as e:
            logger.error(f"✗ FFmpeg merge failed: {e}")
            return None
    
    def split_video_into_clips(self, video_path, output_filename_prefix="clip"):
        """
        Split video into 2-minute clips
        
        Args:
            video_path: Path to the video file to split
            output_filename_prefix: Prefix for output clip files
        """
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return
        
        logger.info(f"Splitting video into {self.clip_duration}s clips...")
        
        # Get video duration
        duration_cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]
        
        try:
            result = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
            total_duration = float(result.stdout.strip())
            logger.info(f"Video duration: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get video duration: {e}")
            return
        
        # Calculate number of clips
        num_clips = int(total_duration / self.clip_duration) + 1
        logger.info(f"Creating {num_clips} clips...")
        
        # Split video
        for i in range(num_clips):
            start_time = i * self.clip_duration
            
            output_clip = os.path.join(
                self.clips_dir,
                f"{output_filename_prefix}_{i+1:03d}.mp4"
            )
            
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', str(start_time),
                '-t', str(self.clip_duration),
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-c:a', 'aac',
                '-q:v', '5',
                '-y',  # Overwrite output file
                output_clip
            ]
            
            try:
                logger.info(f"Creating clip {i+1}/{num_clips}...")
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info(f"✓ Created: {output_clip}")
            except subprocess.CalledProcessError as e:
                logger.error(f"✗ Failed to create clip {i+1}: {e}")
                continue
        
        logger.info(f"✓ All {num_clips} clips created in: {self.clips_dir}")
    
    def download_and_process(self, base_url, start_chunk, end_chunk, key_pair_id=None, policy=None, signature=None):
        """
        Complete pipeline: download chunks → merge → split into clips
        
        Args:
            base_url: Base URL of chunks
            start_chunk: Starting chunk number
            end_chunk: Ending chunk number
            key_pair_id: CloudFront key pair ID (optional)
            policy: CloudFront Policy (optional)
            signature: CloudFront Signature (optional)
        """
        logger.info("=" * 60)
        logger.info("STARTING VIDEO DOWNLOAD & PROCESSING PIPELINE")
        logger.info("=" * 60)
        
        # Step 1: Download chunks
        self.download_chunks(base_url, start_chunk, end_chunk, key_pair_id, policy, signature)
        
        # Step 2: Merge chunks
        full_video_path = self.merge_chunks_to_video()
        if not full_video_path:
            logger.error("Failed to merge chunks!")
            return
        
        # Step 3: Split into 2-minute clips
        self.split_video_into_clips(full_video_path)
        
        logger.info("=" * 60)
        logger.info("✓ PIPELINE COMPLETED SUCCESSFULLY!")
        logger.info(f"Clips saved in: {self.clips_dir}")
        logger.info("=" * 60)


def main():
    """
    Main entry point - Configure your parameters here
    """
    
    # ============ CONFIGURATION ============
    # Replace these with your actual values from Network tab
    BASE_URL = "https://media.scaler.com/production/protected-recordings/987692/1005576/__segment:1010100110010101101010100101010101100101100112/stream_0/"
    START_CHUNK = 0
    END_CHUNK = 120
    
    KEY_PAIR_ID = "K4IMAQNEJMDV1"
    
    POLICY = "ewogICAgICAgICJTdGF0ZW1lbnQiOiBbCiAgICAgICAgICB7CiAgICAgICAgICAgICJSZXNvdXJjZSI6ICJodHRwczovL21lZGlhLnNjYWxlci5jb20vcHJvZHVjdGlvbi9wcm90ZWN0ZWQtcmVjb3JkaW5ncy85ODc2OTIvMTAwNTU3Ni9fX3NlZ21lbnQ6MTAxMDEwMDExMDAxMDEwMTEwMTAxMDEwMDEwMTAxMDEwMTEwMDEwMTEwMDExMi8qIiwKICAgICAgICAgICAgIkNvbmRpdGlvbiI6IHsKICAgICAgICAgICAgICAgIklwQWRkcmVzcyI6IHsKICAgICAgICAgICAgICAgICAgIkFXUzpTb3VyY2VJcCI6ICIwLjAuMC4wLzAiCiAgICAgICAgICAgICAgICB9LAogICAgICAgICAgICAgICAgIkRhdGVMZXNzVGhhbiI6IHsKICAgICAgICAgICAgICAgICAgIkFXUzpFcG9jaFRpbWUiOiAxNzY3ODgxMTAyCiAgICAgICAgICAgICAgICB9LAogICAgICAgICAgICAgICAiRGF0ZUdyZWF0ZXJUaGFuIjogewogICAgICAgICAgICAgICAgICAiQVdTOkVwb2NoVGltZSI6IDE3Njc4NjY3MDIKICAgICAgICAgICAgICAgIH0KICAgICAgICAgICAgfQogICAgICAgICAgfQogICAgICAgIF0KICAgICAgfQogICAg"
    
    SIGNATURE = "MmYXLSVohK4Iam7Rca8mL~axVH266mreOa~-eSKr5jC9nuk3jHqCg9Acvp97WAlpaiguxyaSWbQ2CjhmD6F2iOs7mJ345ruag3Aic5ebhGVd5Dy6SnIMig~Q351WRKbs1SPv9O9xX69vd2pQJII3GOpuDb2Sob9REwhg-VWW56Fn8b3AvsBUiiAdGX~3N~eCwpj4-SOLejP8YDBAgWEyh0AL4XyN0-tbF0z6Cdc1Fl5MZ297UVhI0X9zfCfZQUeJ96MWme~8IV-5yiFedXkBHjwwT0fZge4iLd1HiwAqfSDwUEGxFBMm8aYiImICPUU6Ks1~FIoXaTffb7Rh1aKI-g__"
    
    CLIP_DURATION = 120  # 2 minutes in seconds
    OUTPUT_DIR = "scaler_videos"  # Where to save everything
    
    # ============ VALIDATION ============
    print("\n📋 CONFIGURATION:")
    print(f"Base URL: {BASE_URL}")
    print(f"Chunks: {START_CHUNK} to {END_CHUNK}")
    print(f"Clip Duration: {CLIP_DURATION}s ({CLIP_DURATION/60:.1f} minutes)")
    print(f"Output Directory: {OUTPUT_DIR}")
    print()
    
    # Check for required tools
    for tool in ['ffmpeg', 'ffprobe']:
        try:
            subprocess.run([tool, '-version'], capture_output=True, check=True)
            print(f"✓ {tool} is installed")
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"✗ {tool} is NOT installed!")
            print(f"  Install with: brew install {tool}")
            sys.exit(1)
    
    # ============ EXECUTE ============
    downloader = VideoDownloader(output_dir=OUTPUT_DIR, clip_duration=CLIP_DURATION)
    downloader.download_and_process(BASE_URL, START_CHUNK, END_CHUNK, KEY_PAIR_ID, POLICY, SIGNATURE)


if __name__ == "__main__":
    main()
