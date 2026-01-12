#!/usr/bin/env python3
"""
Scaler Companion - Notes Generator
Generates lecture notes using Ollama LLM
"""

import os
import logging
from pathlib import Path
from typing import Optional, Callable, List
import json

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

logger = logging.getLogger(__name__)


# Prompts for different note generation tasks
PROMPTS = {
    "lecture_notes": """You are an expert note-taker. Given the following lecture transcript, create comprehensive, well-structured study notes.

TRANSCRIPT:
{transcript}

Create detailed notes with:
1. **Key Concepts** - Main ideas and definitions
2. **Important Details** - Supporting information, examples
3. **Code/Commands** - Any technical content (format in code blocks)
4. **Summary** - Brief overview of the lecture

Format your response as clean Markdown. Use headers (##, ###), bullet points, and code blocks where appropriate.
Be thorough but concise. Include all important information from the lecture.""",

    "summary": """Summarize the following lecture transcript in 3-5 paragraphs, covering the main topics discussed:

TRANSCRIPT:
{transcript}

Write a clear, comprehensive summary.""",

    "qa_cards": """Based on this lecture transcript, create study flashcards in Q&A format.

TRANSCRIPT:
{transcript}

Create 10-15 flashcards covering key concepts. Format each as:

**Q:** [Question]
**A:** [Answer]

---

Focus on important definitions, concepts, and technical details.""",

    "key_points": """Extract the key points from this lecture transcript as a bullet list:

TRANSCRIPT:
{transcript}

List the most important points, one per line with a bullet (-)."""
}


class NotesGenerator:
    """Generates lecture notes using Ollama LLM"""
    
    def __init__(
        self,
        model: str = "gpt-oss:20b",
        ollama_host: str = "http://localhost:11434",
        chunk_size: int = 8000
    ):
        """
        Initialize the notes generator
        
        Args:
            model: Ollama model to use
            ollama_host: Ollama server URL
            chunk_size: Max characters per chunk for long transcripts
        """
        self.model = model
        self.ollama_host = ollama_host
        self.chunk_size = chunk_size
        self.progress_callback: Optional[Callable] = None
        
        if not OLLAMA_AVAILABLE:
            logger.warning("ollama package not installed. Run: pip install ollama")
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates: callback(current, total, message)"""
        self.progress_callback = callback
    
    def _update_progress(self, current: int, total: int, message: str = ""):
        """Update progress via callback if set"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def list_available_models(self) -> List[str]:
        """List all available Ollama models"""
        if not OLLAMA_AVAILABLE:
            return []
        
        try:
            client = ollama.Client(host=self.ollama_host)
            response = client.list()
            return [model["name"] for model in response.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            return []
    
    def check_model_available(self) -> bool:
        """Check if the configured model is available"""
        models = self.list_available_models()
        return self.model in models or any(m.startswith(self.model.split(":")[0]) for m in models)
    
    def _chunk_transcript(self, transcript: str) -> List[str]:
        """Split transcript into chunks for processing"""
        if len(transcript) <= self.chunk_size:
            return [transcript]
        
        chunks = []
        words = transcript.split()
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_len = len(word) + 1  # +1 for space
            if current_length + word_len > self.chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = [word]
                current_length = word_len
            else:
                current_chunk.append(word)
                current_length += word_len
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def generate(
        self,
        transcript: str,
        prompt_type: str = "lecture_notes",
        custom_prompt: Optional[str] = None
    ) -> str:
        """
        Generate notes from transcript
        
        Args:
            transcript: The lecture transcript text
            prompt_type: Type of notes (lecture_notes, summary, qa_cards, key_points)
            custom_prompt: Optional custom prompt (overrides prompt_type)
            
        Returns:
            Generated notes as string
        """
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("ollama package not installed")
        
        # Get prompt template
        prompt_template = custom_prompt or PROMPTS.get(prompt_type, PROMPTS["lecture_notes"])
        
        # Chunk transcript if too long
        chunks = self._chunk_transcript(transcript)
        
        logger.info(f"Generating notes using {self.model} ({len(chunks)} chunks)")
        self._update_progress(0, len(chunks), f"Generating with {self.model}...")
        
        client = ollama.Client(host=self.ollama_host)
        
        if len(chunks) == 1:
            # Single chunk - direct generation
            prompt = prompt_template.format(transcript=chunks[0])
            response = client.generate(model=self.model, prompt=prompt)
            self._update_progress(1, 1, "Generation complete")
            return response["response"]
        else:
            # Multiple chunks - generate for each, then summarize
            partial_notes = []
            
            for i, chunk in enumerate(chunks):
                self._update_progress(i, len(chunks), f"Processing chunk {i+1}/{len(chunks)}")
                
                prompt = prompt_template.format(transcript=chunk)
                response = client.generate(model=self.model, prompt=prompt)
                partial_notes.append(response["response"])
            
            # Combine partial notes
            self._update_progress(len(chunks), len(chunks) + 1, "Combining notes...")
            
            combine_prompt = f"""Combine and organize these partial lecture notes into a single, coherent document.
Remove any duplicates and organize by topic:

{chr(10).join(partial_notes)}

Create a well-structured final document in Markdown format."""
            
            final_response = client.generate(model=self.model, prompt=combine_prompt)
            
            self._update_progress(len(chunks) + 1, len(chunks) + 1, "Complete")
            return final_response["response"]
    
    def generate_all(
        self,
        transcript: str,
        output_dir: str,
        title: str = "Lecture"
    ) -> dict:
        """
        Generate all note types and save to files
        
        Args:
            transcript: The lecture transcript
            output_dir: Directory to save outputs
            title: Lecture title for headers
            
        Returns:
            Dict with paths to generated files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        # Generate main lecture notes
        logger.info("Generating lecture notes...")
        self._update_progress(0, 3, "Generating lecture notes...")
        
        try:
            notes = self.generate(transcript, "lecture_notes")
            notes_path = output_dir / "lecture_notes.md"
            
            with open(notes_path, "w", encoding="utf-8") as f:
                f.write(f"# Lecture Notes: {title}\n\n")
                f.write(notes)
            
            results["notes"] = str(notes_path)
            logger.info(f"Saved lecture notes to {notes_path}")
        except Exception as e:
            logger.error(f"Failed to generate lecture notes: {e}")
            results["notes_error"] = str(e)
        
        # Generate Q&A cards
        logger.info("Generating Q&A cards...")
        self._update_progress(1, 3, "Generating Q&A cards...")
        
        try:
            qa = self.generate(transcript, "qa_cards")
            qa_path = output_dir / "qa_cards.md"
            
            with open(qa_path, "w", encoding="utf-8") as f:
                f.write(f"# Flashcards: {title}\n\n")
                f.write(qa)
            
            results["qa_cards"] = str(qa_path)
            logger.info(f"Saved Q&A cards to {qa_path}")
        except Exception as e:
            logger.error(f"Failed to generate Q&A cards: {e}")
            results["qa_error"] = str(e)
        
        # Generate summary
        logger.info("Generating summary...")
        self._update_progress(2, 3, "Generating summary...")
        
        try:
            summary = self.generate(transcript, "summary")
            summary_path = output_dir / "summary.md"
            
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(f"# Summary: {title}\n\n")
                f.write(summary)
            
            results["summary"] = str(summary_path)
            logger.info(f"Saved summary to {summary_path}")
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            results["summary_error"] = str(e)
        
        self._update_progress(3, 3, "All notes generated")
        
        return results


# For testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    generator = NotesGenerator(model="gpt-oss:20b")
    
    # List available models
    print("Available Ollama models:")
    for model in generator.list_available_models():
        print(f"  - {model}")
    
    # Test with sample transcript
    sample = """
    Today we're going to talk about Terraform and infrastructure as code.
    Terraform is a tool that allows you to define infrastructure in code.
    You write HCL files that describe your desired state.
    Then Terraform figures out what needs to be created or modified.
    """
    
    if generator.check_model_available():
        result = generator.generate(sample, "key_points")
        print("\nKey Points:")
        print(result)
    else:
        print(f"\nModel {generator.model} not available. Install with: ollama pull gpt-oss:20b")
