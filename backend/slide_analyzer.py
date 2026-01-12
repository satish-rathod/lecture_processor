#!/usr/bin/env python3
"""
Scaler Companion - Slide Analyzer
Analyzes slide images using OCR and Vision LLM for content understanding
"""

import os
import base64
import logging
from pathlib import Path
from typing import Optional, Callable, List
import json

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
    """Analyzes slide images using OCR and Vision LLM"""
    
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
    
    def __init__(
        self,
        vision_model: str = "llama3.2-vision:11b",
        ollama_host: str = "http://localhost:11434",
        use_ocr: bool = True,
        use_vision: bool = True,
        ocr_engine: str = "easyocr"  # 'easyocr' or 'tesseract'
    ):
        """
        Initialize the slide analyzer
        
        Args:
            vision_model: Ollama vision model to use
            ollama_host: Ollama server URL
            use_ocr: Whether to use OCR for text extraction
            use_vision: Whether to use vision LLM for understanding
            ocr_engine: OCR engine to use ('easyocr' or 'tesseract')
        """
        self.vision_model = vision_model
        self.ollama_host = ollama_host
        self.use_ocr = use_ocr
        self.use_vision = use_vision
        self.ocr_engine = ocr_engine
        self.progress_callback: Optional[Callable] = None
        
        # Initialize OCR
        self._ocr_reader = None
        
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
                logger.warning("No OCR engine available. Install easyocr or pytesseract.")
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
        """
        Extract text from image using OCR
        
        Args:
            image_path: Path to image file
            
        Returns:
            Extracted text
        """
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
    
    def analyze_with_vision(self, image_path: str, ocr_text: str = "") -> str:
        """
        Analyze image using Vision LLM
        
        Args:
            image_path: Path to image file
            ocr_text: Pre-extracted OCR text to include in prompt
            
        Returns:
            Vision model's analysis of the slide
        """
        if not self.use_vision or not OLLAMA_AVAILABLE:
            return ""
        
        try:
            # Read and encode image
            with open(image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            # Build prompt
            prompt = """Analyze this lecture slide image. Provide:
1. **Title/Topic**: What is the main topic shown?
2. **Key Points**: List the main points or concepts (bullet points)
3. **Diagrams/Charts**: Describe any visual elements (diagrams, flowcharts, code, etc.)
4. **Summary**: One sentence summarizing the slide

Be concise and focus on educational content."""

            if ocr_text:
                prompt += f"\n\nOCR extracted text (may have errors): {ocr_text[:500]}"
            
            # Call Ollama with image
            client = ollama.Client(host=self.ollama_host)
            response = client.generate(
                model=self.vision_model,
                prompt=prompt,
                images=[image_data]
            )
            
            return response.get("response", "")
            
        except Exception as e:
            logger.warning(f"Vision analysis failed for {image_path}: {e}")
            return ""
    
    def analyze_slide(self, image_path: str) -> dict:
        """
        Analyze a single slide using both OCR and Vision LLM
        
        Args:
            image_path: Path to slide image
            
        Returns:
            Dict with analysis results
        """
        result = {
            "path": image_path,
            "ocr_text": "",
            "vision_analysis": "",
            "combined_summary": ""
        }
        
        # Step 1: OCR
        if self.use_ocr:
            result["ocr_text"] = self.extract_text_ocr(image_path)
        
        # Step 2: Vision LLM
        if self.use_vision:
            result["vision_analysis"] = self.analyze_with_vision(
                image_path, 
                result["ocr_text"]
            )
        
        # Step 3: Create combined summary
        result["combined_summary"] = self._create_summary(result)
        
        return result
    
    def _create_summary(self, analysis: dict) -> str:
        """Create a combined summary from OCR and vision analysis"""
        parts = []
        
        if analysis["vision_analysis"]:
            parts.append(analysis["vision_analysis"])
        elif analysis["ocr_text"]:
            # If no vision, just use OCR text
            parts.append(f"**Text on slide:** {analysis['ocr_text'][:500]}")
        
        return "\n".join(parts) if parts else "No content detected"
    
    def analyze_all_slides(self, frames: List[dict], output_dir: str) -> List[dict]:
        """
        Analyze all slides and save results
        
        Args:
            frames: List of frame dicts with 'path' and 'timestamp'
            output_dir: Directory to save analysis results
            
        Returns:
            List of analysis results
        """
        if not frames:
            return []
        
        logger.info(f"Analyzing {len(frames)} slides...")
        results = []
        
        for i, frame in enumerate(frames):
            self._update_progress(i, len(frames), f"Analyzing slide {i+1}/{len(frames)}")
            
            analysis = self.analyze_slide(frame["path"])
            analysis["timestamp"] = frame.get("timestamp", 0)
            analysis["timestamp_display"] = frame.get("timestamp_display", "")
            analysis["filename"] = frame.get("filename", "")
            
            results.append(analysis)
            
            logger.debug(f"Analyzed slide {i+1}: {frame['filename']}")
        
        self._update_progress(len(frames), len(frames), "Slide analysis complete")
        
        # Save analysis results
        output_dir = Path(output_dir)
        analysis_path = output_dir / "slides_analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
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
            
            # Handle different response formats
            available = []
            for m in model_list:
                if isinstance(m, dict):
                    name = m.get("name") or m.get("model", "")
                    available.append(name)
                elif isinstance(m, str):
                    available.append(m)
            
            # Check if our model or any variant is available
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
            available = [m["name"] for m in models.get("models", [])]
            
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
        vision_model="llava",
        use_ocr=True,
        use_vision=True
    )
    
    # Check available vision models
    print("Available vision models:", analyzer.list_available_vision_models())
    
    # Test with a sample slide
    test_slide = "../output/improved_test/slides/00_04_43.png"
    if os.path.exists(test_slide):
        print(f"\nAnalyzing {test_slide}...")
        result = analyzer.analyze_slide(test_slide)
        print(f"\nOCR Text:\n{result['ocr_text'][:300]}...")
        print(f"\nVision Analysis:\n{result['vision_analysis'][:500]}...")
    else:
        print(f"Test slide not found: {test_slide}")
