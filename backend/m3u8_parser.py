#!/usr/bin/env python3
"""
Scaler Companion - M3U8 Playlist Parser
Simple parser for HLS playlists to extract segment information
"""

import re
import requests
import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, quote

logger = logging.getLogger(__name__)


@dataclass
class HLSSegment:
    """Represents a single video segment in the playlist"""
    url: str
    duration: float
    sequence: int


@dataclass
class HLSPlaylist:
    """Parsed HLS playlist data"""
    segments: list
    total_duration: float
    base_url: str
    chunk_pattern: str  # Detected pattern (e.g., "data{}.ts")
    

def parse_m3u8(url: str, auth_params: dict = None) -> Optional[HLSPlaylist]:
    """
    Parse an M3U8 playlist and extract segment information.
    
    Args:
        url: URL to the .m3u8 playlist file
        auth_params: Optional dict with CloudFront auth (Key-Pair-Id, Policy, Signature)
    
    Returns:
        HLSPlaylist object with segments, or None on error
    """
    try:
        # Build request params
        params = {}
        if auth_params:
            for key, value in auth_params.items():
                if value:
                    params[key] = value
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        }
        
        logger.info(f"Fetching M3U8 playlist: {url}")
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        content = response.text
        
        # Extract base URL for relative segment paths
        base_url = url.rsplit('/', 1)[0] + '/'
        
        segments = []
        total_duration = 0.0
        sequence = 0
        chunk_pattern = None
        
        lines = content.strip().split('\n')
        current_duration = 0.0
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Parse target duration for reference
            if line.startswith('#EXT-X-TARGETDURATION:'):
                pass  # Could use for validation
            
            # Parse segment duration
            elif line.startswith('#EXTINF:'):
                match = re.match(r'#EXTINF:([\d.]+)', line)
                if match:
                    current_duration = float(match.group(1))
            
            # This is a segment URL
            elif line and not line.startswith('#'):
                # Handle relative vs absolute URLs
                if line.startswith('http'):
                    seg_url = line
                else:
                    seg_url = urljoin(base_url, line)
                
                # Detect chunk pattern from first segment
                if chunk_pattern is None:
                    pattern_match = re.search(r'(data|chunk|segment)(\d+)', line)
                    if pattern_match:
                        prefix = pattern_match.group(1)
                        num_digits = len(pattern_match.group(2))
                        chunk_pattern = f"{prefix}{{:0{num_digits}d}}.ts" if num_digits > 1 else f"{prefix}{{}}.ts"
                        logger.info(f"Detected chunk pattern: {chunk_pattern}")
                
                segments.append(HLSSegment(
                    url=seg_url,
                    duration=current_duration,
                    sequence=sequence
                ))
                total_duration += current_duration
                sequence += 1
                current_duration = 0.0
        
        if not segments:
            logger.warning("No segments found in M3U8 playlist")
            return None
        
        logger.info(f"Parsed {len(segments)} segments, total duration: {total_duration:.1f}s")
        
        return HLSPlaylist(
            segments=segments,
            total_duration=total_duration,
            base_url=base_url,
            chunk_pattern=chunk_pattern or "data{}.ts"
        )
        
    except requests.RequestException as e:
        logger.error(f"Failed to fetch M3U8 playlist: {e}")
        return None
    except Exception as e:
        logger.error(f"Error parsing M3U8 playlist: {e}")
        return None


def get_segment_urls_with_auth(playlist: HLSPlaylist, auth_params: dict = None) -> list:
    """
    Get list of segment URLs with authentication parameters appended.
    
    Args:
        playlist: Parsed HLSPlaylist
        auth_params: CloudFront auth params
    
    Returns:
        List of full URLs ready for download
    """
    urls = []
    
    for segment in playlist.segments:
        url = segment.url
        
        # Append auth params if provided
        if auth_params:
            params = []
            if auth_params.get('Key-Pair-Id'):
                params.append(f"Key-Pair-Id={auth_params['Key-Pair-Id']}")
            if auth_params.get('Policy'):
                params.append(f"Policy={quote(auth_params['Policy'], safe='')}")
            if auth_params.get('Signature'):
                params.append(f"Signature={quote(auth_params['Signature'], safe='')}")
            
            if params:
                separator = '&' if '?' in url else '?'
                url = url + separator + '&'.join(params)
        
        urls.append(url)
    
    return urls
