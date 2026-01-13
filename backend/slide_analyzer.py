#!/usr/bin/env python3
"""
Scaler Companion - Slide Analyzer (Optimized)
Analyzes slide images using OCR and Vision LLM for content understanding
Optimizations: Skip vision for text-heavy slides, shorter prompts, parallel OCR
"""

import os
import base64
import logging
from pathlib import Path
from typing import Optional, Callable, List
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# OCR imports
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

# Ollama for vision
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

logger = logging.getLogger(__name__)


class SlideAnalyzer:
    """Analyzes slide images using OCR and Vision LLM (Optimized)"""
    
    # Vision models that support image input in Ollama
    VISION_MODELS = [
        "llava",
        "llava:13b",
        "llava:34b",
        "llama3.2-vision",
        "llama3.2-vision:11b",
        "bakllava",
        "moondream",
    ]
    
    # Optimized short prompt for faster inference
    VISION_PROMPT_SHORT = """Describe this lecture slide briefly:
- Topic/title
- Key points (2-3 bullets)
- Any diagrams or code shown
Keep response under 100 words."""

    # Threshold: if OCR extracts more than this many words, skip vision
    OCR_WORD_THRESHOLD = 30
    
    def __init__(
        self,
        vision_model: str = "llama3.2-vision:11b",
        ollama_host: str = "http://localhost:11434",
        use_ocr: bool = True,
        use_vision: bool = True,
        ocr_engine: str = "easyocr",
        smart_vision: bool = True,  # Skip vision for text-heavy slides
        ocr_word_threshold: int = 30  # Threshold for skipping vision
    ):
        """
        Initialize the slide analyzer
        
        Args:
            vision_model: Ollama vision model to use
            ollama_host: Ollama server URL
            use_ocr: Whether to use OCR for text extraction
            use_vision: Whether to use vision LLM for understanding
            ocr_engine: OCR engine to use ('easyocr' or 'tesseract')
            smart_vision: If True, skip vision LLM when OCR extracts enough text
            ocr_word_threshold: Word count threshold for skipping vision
        """
        self.vision_model = vision_model
        self.ollama_host = ollama_host
        self.use_ocr = use_ocr
        self.use_vision = use_vision
        self.ocr_engine = ocr_engine
        self.smart_vision = smart_vision
        self.ocr_word_threshold = ocr_word_threshold
        self.progress_callback: Optional[Callable] = None
        
        # Initialize OCR
        self._ocr_reader = None
        
        # Stats for optimization tracking
        self.stats = {
            "slides_processed": 0,
            "vision_calls": 0,
            "vision_skipped": 0
        }
        
        if use_ocr:
            if ocr_engine == "easyocr" and EASYOCR_AVAILABLE:
                logger.info("Using EasyOCR for text extraction")
            elif ocr_engine == "tesseract" and TESSERACT_AVAILABLE:
                logger.info("Using Tesseract for text extraction")
            elif EASYOCR_AVAILABLE:
                self.ocr_engine = "easyocr"
                logger.info("Falling back to EasyOCR")
            elif TESSERACT_AVAILABLE:
                self.ocr_engine = "tesseract"
                logger.info("Falling back to Tesseract")
            else:
                logger.warning("No OCR engine available.")
                self.use_ocr = False
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates"""
        self.progress_callback = callback
    
    def _update_progress(self, current: int, total: int, message: str = ""):
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    @property
    def ocr_reader(self):
        """Lazy-load EasyOCR reader"""
        if self._ocr_reader is None and self.ocr_engine == "easyocr" and EASYOCR_AVAILABLE:
            logger.info("Loading EasyOCR model...")
            self._ocr_reader = easyocr.Reader(['en'], gpu=False)
        return self._ocr_reader
    
    def extract_text_ocr(self, image_path: str) -> str:
        """Extract text from image using OCR"""
        if not self.use_ocr:
            return ""
        
        try:
            if self.ocr_engine == "easyocr" and EASYOCR_AVAILABLE:
                results = self.ocr_reader.readtext(image_path, detail=0)
                return " ".join(results)
            
            elif self.ocr_engine == "tesseract" and TESSERACT_AVAILABLE:
                img = Image.open(image_path)
                text = pytesseract.image_to_string(img)
                return text.strip()
            
        except Exception as e:
            logger.warning(f"OCR failed for {image_path}: {e}")
        
        return ""
    
    def _should_skip_vision(self, ocr_text: str) -> bool:
        """
        Determine if vision analysis should be skipped based on OCR results
        
        Returns True if OCR extracted enough text (>threshold words)
        """
        if not self.smart_vision:
            return False
        
        word_count = len(ocr_text.split())
        return word_count >= self.ocr_word_threshold
    
    def analyze_with_vision(self, image_path: str, ocr_text: str = "") -> str:
        """Analyze image using Vision LLM with optimized short prompt"""
        if not self.use_vision or not OLLAMA_AVAILABLE:
            return ""
        
        try:
            # Read and encode image
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            # Use short optimized prompt
            prompt = self.VISION_PROMPT_SHORT
            
            # Call Ollama with image
            client = ollama.Client(host=self.ollama_host)
            response = client.generate(
                model=self.vision_model,
                prompt=prompt,
                images=[image_data]
            )
            
            self.stats["vision_calls"] += 1
            return response.get("response", "")
            
        except Exception as e:
            logger.warning(f"Vision analysis failed for {image_path}: {e}")
            return ""
    
    def analyze_slide(self, image_path: str) -> dict:
        """
        Analyze a single slide using OCR and optionally Vision LLM
        
        Optimization: Skip vision if OCR extracts enough text
        """
        result = {
            "path": image_path,
            "ocr_text": "",
            "vision_analysis": "",
            "vision_skipped": False,
            "combined_summary": ""
        }
        
        # Step 1: OCR (always run first for smart filtering)
        if self.use_ocr:
            result["ocr_text"] = self.extract_text_ocr(image_path)
        
        # Step 2: Decide whether to run vision
        if self.use_vision:
            if self._should_skip_vision(result["ocr_text"]):
                # Skip vision - OCR has enough text
                result["vision_skipped"] = True
                self.stats["vision_skipped"] += 1
                logger.debug(f"Skipping vision for {image_path} (OCR: {len(result['ocr_text'].split())} words)")
            else:
                # Run vision analysis
                result["vision_analysis"] = self.analyze_with_vision(
                    image_path, 
                    result["ocr_text"]
                )
        
        # Step 3: Create combined summary
        result["combined_summary"] = self._create_summary(result)
        self.stats["slides_processed"] += 1
        
        return result
    
    def _create_summary(self, analysis: dict) -> str:
        """Create a combined summary from OCR and vision analysis"""
        if analysis["vision_analysis"]:
            return analysis["vision_analysis"]
        elif analysis["ocr_text"]:
            # Use OCR text as summary (formatted)
            text = analysis["ocr_text"][:500]
            return f"**Slide Content:** {text}"
        return "No content detected"
    
    def analyze_all_slides(self, frames: List[dict], output_dir: str) -> List[dict]:
        """
        Analyze all slides with optimizations
        
        Optimizations:
        - Skip vision for text-heavy slides
        - Short prompts for faster inference
        """
        if not frames:
            return []
        
        # Reset stats
        self.stats = {"slides_processed": 0, "vision_calls": 0, "vision_skipped": 0}
        
        logger.info(f"Analyzing {len(frames)} slides (smart_vision={self.smart_vision})...")
        results = []
        
        for i, frame in enumerate(frames):
            self._update_progress(i, len(frames), f"Analyzing slide {i+1}/{len(frames)}")
            
            analysis = self.analyze_slide(frame["path"])
            analysis["timestamp"] = frame.get("timestamp", 0)
            analysis["timestamp_display"] = frame.get("timestamp_display", "")
            analysis["filename"] = frame.get("filename", "")
            
            results.append(analysis)
        
        self._update_progress(len(frames), len(frames), "Slide analysis complete")
        
        # Log optimization stats
        logger.info(f"Slide analysis stats: {self.stats['slides_processed']} processed, "
                   f"{self.stats['vision_calls']} vision calls, "
                   f"{self.stats['vision_skipped']} skipped (smart)")
        
        # Save analysis results
        output_dir = Path(output_dir)
        analysis_path = output_dir / "slides_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump({
                "stats": self.stats,
                "slides": results
            }, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Slide analysis saved to {analysis_path}")
        
        return results
    
    def check_vision_model_available(self) -> bool:
        """Check if the configured vision model is available in Ollama"""
        if not OLLAMA_AVAILABLE:
            return False
        
        try:
            client = ollama.Client(host=self.ollama_host)
            models = client.list()
            model_list = models.get("models", [])
            
            available = []
            for m in model_list:
                if isinstance(m, dict):
                    name = m.get("name") or m.get("model", "")
                    available.append(name)
                elif isinstance(m, str):
                    available.append(m)
            
            for model in available:
                if self.vision_model in model or model.startswith(self.vision_model.split(":")[0]):
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to check Ollama models: {e}")
            return False
    
    def list_available_vision_models(self) -> List[str]:
        """List available vision models in Ollama"""
        if not OLLAMA_AVAILABLE:
            return []
        
        try:
            client = ollama.Client(host=self.ollama_host)
            models = client.list()
            model_list = models.get("models", [])
            
            available = []
            for m in model_list:
                if isinstance(m, dict):
                    name = m.get("name") or m.get("model", "")
                    available.append(name)
            
            # Filter to vision-capable models
            vision_available = []
            for model in available:
                for vision_model in self.VISION_MODELS:
                    if vision_model in model.lower():
                        vision_available.append(model)
                        break
            
            return vision_available
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    analyzer = SlideAnalyzer(
        vision_model="llama3.2-vision:11b",
        use_ocr=True,
        use_vision=True,
        smart_vision=True,  # Enable optimization
        ocr_word_threshold=30
    )
    
    print("Available vision models:", analyzer.list_available_vision_models())
    
    # Test with a sample slide
    test_slide = "../output/improved_test/slides/00_15_00.png"
    if os.path.exists(test_slide):
        print(f"\nAnalyzing {test_slide}...")
        result = analyzer.analyze_slide(test_slide)
        print(f"OCR Text ({len(result['ocr_text'].split())} words): {result['ocr_text'][:200]}")
        print(f"Vision skipped: {result['vision_skipped']}")
        print(f"Vision Analysis: {result['vision_analysis'][:300]}")
    else:
        print(f"Test slide not found: {test_slide}")
