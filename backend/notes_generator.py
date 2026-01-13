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
    "lecture_notes": """You are an expert technical note-taker creating study materials.

LECTURE TITLE: {title}
TRANSCRIPT:
{transcript}

---

Create **comprehensive, revision-ready notes** using this EXACT structure:

### 1. Overview
One paragraph: What this lecture covers, prerequisites, and target audience.

### 2. Core Concepts
Use a TABLE format:
| Concept | Definition | Key Points |
|---------|------------|------------|
| ... | ... | ... |

### 3. Detailed Sections
For EACH major topic discussed:

#### [Topic Name]
- **What**: Clear definition
- **Why**: Importance/use case  
- **How**: Implementation steps or process
- **Example**: Code or real-world example

### 4. Comparisons (if applicable)
Create comparison tables for related concepts:
| Aspect | Option A | Option B |
|--------|----------|----------|

### 5. Architecture/Diagrams
Describe any system architectures or flows in text with clear structure.

### 6. Key Takeaways
- Bullet list of 5-8 most important points
- Include specific values, commands, or configs mentioned

### 7. References & Tools
List any tools, libraries, frameworks, or resources mentioned.

---

RULES:
- Include ALL technical details from the transcript
- Use code blocks for commands, configs, code snippets
- Create tables for structured information
- Be SPECIFIC, not generic
- If the speaker mentions specific numbers, tools, or examples - include them""",

    "summary": """Create a DETAILED summary of this lecture with structured sections:

TRANSCRIPT:
{transcript}

Generate the summary with these EXACT sections:

## Lecture Overview
2-3 sentences on what this lecture is about and its context.

## Topics Covered
List ALL topics discussed as a numbered list:
1. [Topic Name] - brief description
2. [Topic Name] - brief description
...

## Key Concepts Explained
For each major concept:
- **[Concept]**: Explanation in 2-3 sentences

## Technical Details
- Specific tools, commands, or configurations mentioned
- Code examples or syntax discussed
- Any metrics, numbers, or benchmarks

## Practical Applications
How the concepts apply in real-world scenarios.

## Takeaways
Bullet list of 5-8 most important points to remember.

Be COMPREHENSIVE. Include ALL topics from the lecture.""",

    "announcements": """Extract ACTIONABLE ITEMS from this lecture transcript.

TRANSCRIPT:
{transcript}

Find and list:

## Assignments & Deadlines
- Any homework, projects, or assignments mentioned
- Due dates and deadlines
- Submission requirements

## Action Items
- Things students need to do
- Things to install, set up, or prepare
- Readings or resources to review

## Important Announcements
- Schedule changes (classes, exams, holidays)
- Grading policies or changes
- Administrative notices

## Resources to Check
- Links, tools, or documentation mentioned
- Books or papers referenced
- Websites or repositories

If no actionable items found in a category, write "None mentioned".
Be specific - include dates, names, and details.""",

    "qa_cards": """Create study flashcards from this lecture:

TRANSCRIPT:
{transcript}

Create 15-20 flashcards covering:
- Definitions of key terms
- Technical concepts
- Comparisons (X vs Y)
- Commands/syntax
- Best practices

Format EXACTLY as:

**Q:** [Specific question]
**A:** [Concise but complete answer]

---

Make questions specific and testable, not vague.""",

    "key_points": """Extract key points from this lecture as a comprehensive bullet list:

TRANSCRIPT:
{transcript}

List ALL important points including:
- Definitions and concepts
- Technical details (commands, configs, code)
- Best practices mentioned
- Tools and technologies discussed
- Comparisons made
- Examples given

Format: One bullet (-) per point. Be specific.""",

    # OPTIMIZED: Single prompt for all outputs (4 sections)
    "batch_all": """You are an expert technical note-taker. Create FOUR study materials from this lecture.

LECTURE TITLE: {title}
TRANSCRIPT:
{transcript}

---

Generate these FOUR sections with EXACT headers:

## LECTURE_NOTES_START

### Overview
One paragraph on what this lecture covers.

### Core Concepts Table
| Concept | Definition | Example |
|---------|------------|---------|
| ... | ... | ... |

### Detailed Sections
For each topic:
#### [Topic Name]
- **What**: Definition
- **Why**: Use case
- **How**: Steps/implementation
- Code examples in code blocks

### Comparisons (if topics were compared)
| Aspect | A | B |
|--------|---|---|

### Key Takeaways
- 5-8 bullet points of main learnings

## LECTURE_NOTES_END

## QA_CARDS_START
Create 12-15 flashcards:
**Q:** [Question]
**A:** [Answer]
---
(repeat for each card)
## QA_CARDS_END

## SUMMARY_START

### Lecture Overview
2-3 sentences on what this lecture covers.

### Topics Covered
1. [Topic] - description
2. [Topic] - description
(list ALL topics)

### Key Concepts
- **[Concept]**: Brief explanation

### Technical Details
- Tools, commands, configs mentioned

### Takeaways
- Important points to remember

## SUMMARY_END

## ANNOUNCEMENTS_START

### Assignments & Deadlines
- Any homework or projects mentioned with dates

### Action Items
- Things to do, install, or prepare

### Important Notices
- Schedule changes, grading info, admin notices

### Resources
- Links, tools, or documentation mentioned

(Write "None mentioned" if a category has nothing)

## ANNOUNCEMENTS_END

RULES: Be SPECIFIC. Include all technical details, commands, dates, and examples from the transcript.""",

    # Combine partial outputs
    "batch_all_combine": """Merge these partial lecture notes into ONE consolidated document.

PARTIAL OUTPUTS:
{transcript}

---

Combine following the EXACT structure:

## LECTURE_NOTES_START
[Merge all notes sections. Remove duplicates. Organize by topic. Keep all tables.]
## LECTURE_NOTES_END

## QA_CARDS_START
[Keep best 12-15 unique flashcards]
## QA_CARDS_END

## SUMMARY_START
[Merge into single coherent 4-5 paragraph summary]
## SUMMARY_END"""
}


class NotesGenerator:
    """Generates lecture notes using Ollama LLM"""
    
    def __init__(
        self,
        model: str = "gpt-oss:20b",
        ollama_host: str = "http://localhost:11434",
        chunk_size: int = 16000  # Increased for better context
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
        custom_prompt: Optional[str] = None,
        title: str = "Lecture"
    ) -> str:
        """
        Generate notes from transcript
        
        Args:
            transcript: The lecture transcript text
            prompt_type: Type of notes (lecture_notes, summary, qa_cards, key_points, batch_all)
            custom_prompt: Optional custom prompt (overrides prompt_type)
            title: Lecture title for context
            
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
            try:
                prompt = prompt_template.format(transcript=chunks[0], title=title)
            except KeyError:
                prompt = prompt_template.format(transcript=chunks[0])
            response = client.generate(model=self.model, prompt=prompt)
            self._update_progress(1, 1, "Generation complete")
            return response["response"]
        else:
            # Multiple chunks - generate for each, then summarize
            partial_notes = []
            
            for i, chunk in enumerate(chunks):
                self._update_progress(i, len(chunks), f"Processing chunk {i+1}/{len(chunks)}")
                
                try:
                    prompt = prompt_template.format(transcript=chunk, title=title)
                except KeyError:
                    prompt = prompt_template.format(transcript=chunk)
                response = client.generate(model=self.model, prompt=prompt)
                partial_notes.append(response["response"])
            
            # Combine partial notes
            self._update_progress(len(chunks), len(chunks) + 1, "Combining notes...")
            
            # Select appropriate combine prompt
            if prompt_type == "batch_all":
                combine_template = PROMPTS["batch_all_combine"]
            else:
                combine_template = """Combine and organize these partial outputs into a single, coherent document.
Remove any duplicates and organize by topic:

{transcript}

Create a well-structured final document in Markdown format."""
            
            combine_prompt = combine_template.format(transcript="\n\n".join(partial_notes))
            
            final_response = client.generate(model=self.model, prompt=combine_prompt)
            
            self._update_progress(len(chunks) + 1, len(chunks) + 1, "Complete")
            return final_response["response"]
    
    def generate_all(
        self,
        transcript: str,
        output_dir: str,
        title: str = "Lecture",
        use_batch: bool = True
    ) -> dict:
        """
        Generate all note types and save to files
        
        Args:
            transcript: The lecture transcript
            output_dir: Directory to save outputs
            title: Lecture title for headers
            use_batch: Use optimized batch generation (single LLM call)
            
        Returns:
            Dict with paths to generated files
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = {}
        
        if use_batch:
            # OPTIMIZED: Single LLM call for all three outputs
            return self._generate_all_batch(transcript, output_dir, title)
        else:
            # Legacy: Three separate LLM calls
            return self._generate_all_sequential(transcript, output_dir, title)
    
    def _parse_batch_response(self, response: str) -> dict:
        """Parse the batch response into separate sections"""
        sections = {
            "notes": "",
            "qa_cards": "",
            "summary": "",
            "announcements": ""
        }
        
        # Extract lecture notes
        if "## LECTURE_NOTES_START" in response and "## LECTURE_NOTES_END" in response:
            start = response.find("## LECTURE_NOTES_START") + len("## LECTURE_NOTES_START")
            end = response.find("## LECTURE_NOTES_END")
            sections["notes"] = response[start:end].strip()
        
        # Extract Q&A cards
        if "## QA_CARDS_START" in response and "## QA_CARDS_END" in response:
            start = response.find("## QA_CARDS_START") + len("## QA_CARDS_START")
            end = response.find("## QA_CARDS_END")
            sections["qa_cards"] = response[start:end].strip()
        
        # Extract summary
        if "## SUMMARY_START" in response and "## SUMMARY_END" in response:
            start = response.find("## SUMMARY_START") + len("## SUMMARY_START")
            end = response.find("## SUMMARY_END")
            sections["summary"] = response[start:end].strip()
        
        # Extract announcements/actionables
        if "## ANNOUNCEMENTS_START" in response and "## ANNOUNCEMENTS_END" in response:
            start = response.find("## ANNOUNCEMENTS_START") + len("## ANNOUNCEMENTS_START")
            end = response.find("## ANNOUNCEMENTS_END")
            sections["announcements"] = response[start:end].strip()
        
        return sections
    
    def _generate_all_batch(
        self,
        transcript: str,
        output_dir: Path,
        title: str
    ) -> dict:
        """Optimized: Generate all three outputs in a single LLM call"""
        results = {}
        
        logger.info("Generating all notes in batch mode (optimized)...")
        self._update_progress(0, 1, "Generating all notes in single call...")
        
        try:
            # Generate all in one call
            response = self.generate(transcript, "batch_all", title=title)
            
            # Parse the response into sections
            sections = self._parse_batch_response(response)
            
            # Save lecture notes
            if sections["notes"]:
                notes_path = output_dir / "lecture_notes.md"
                with open(notes_path, "w", encoding="utf-8") as f:
                    f.write(f"# Lecture Notes: {title}\n\n")
                    f.write(sections["notes"])
                results["notes"] = str(notes_path)
                logger.info(f"Saved lecture notes to {notes_path}")
            
            # Save Q&A cards
            if sections["qa_cards"]:
                qa_path = output_dir / "qa_cards.md"
                with open(qa_path, "w", encoding="utf-8") as f:
                    f.write(f"# Flashcards: {title}\n\n")
                    f.write(sections["qa_cards"])
                results["qa_cards"] = str(qa_path)
                logger.info(f"Saved Q&A cards to {qa_path}")
            
            # Save summary
            if sections["summary"]:
                summary_path = output_dir / "summary.md"
                with open(summary_path, "w", encoding="utf-8") as f:
                    f.write(f"# Summary: {title}\n\n")
                    f.write(sections["summary"])
                results["summary"] = str(summary_path)
                logger.info(f"Saved summary to {summary_path}")
            
            # Save announcements/actionables
            if sections["announcements"]:
                announcements_path = output_dir / "announcements.md"
                with open(announcements_path, "w", encoding="utf-8") as f:
                    f.write(f"# Action Items & Announcements: {title}\n\n")
                    f.write(sections["announcements"])
                results["announcements"] = str(announcements_path)
                logger.info(f"Saved announcements to {announcements_path}")
            
            self._update_progress(1, 1, "All notes generated (batch)")
            
        except Exception as e:
            logger.error(f"Batch generation failed: {e}")
            # Fallback to sequential
            logger.info("Falling back to sequential generation...")
            return self._generate_all_sequential(transcript, output_dir, title)
        
        return results
    
    def _generate_all_sequential(
        self,
        transcript: str,
        output_dir: Path,
        title: str
    ) -> dict:
        """Legacy: Generate each output type separately"""
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
        self._update_progress(2, 4, "Generating summary...")
        
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

        # Generate announcements
        logger.info("Generating announcements...")
        self._update_progress(3, 4, "Generating announcements...")
        
        try:
            announcements = self.generate(transcript, "announcements")
            announcements_path = output_dir / "announcements.md"
            
            with open(announcements_path, "w", encoding="utf-8") as f:
                f.write(f"# Action Items & Announcements: {title}\n\n")
                f.write(announcements)
            
            results["announcements"] = str(announcements_path)
            logger.info(f"Saved announcements to {announcements_path}")
        except Exception as e:
            logger.error(f"Failed to generate announcements: {e}")
            results["announcements_error"] = str(e)
        
        self._update_progress(4, 4, "All notes generated")
        
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
