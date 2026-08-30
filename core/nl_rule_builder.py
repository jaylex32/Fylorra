"""
Fylorra - Natural Language Rule Builder
Converts natural language instructions into executable automation rules
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RuleGenerationResult:
    """Result of natural language rule generation"""

    # Generated rule
    rule: Optional[Dict[str, Any]]

    # AI understanding
    interpretation: str
    confidence: float

    # Explainability
    explanation: str
    warnings: List[str]

    # Metadata
    original_input: str
    model_used: str

    def is_high_confidence(self) -> bool:
        """High confidence - suggest with minimal warning"""
        return self.confidence >= 0.80

    def is_medium_confidence(self) -> bool:
        """Medium confidence - show warnings"""
        return 0.60 <= self.confidence < 0.80

    def is_low_confidence(self) -> bool:
        """Low confidence - don't suggest"""
        return self.confidence < 0.60


class NaturalLanguageRuleBuilder:
    """
    Converts natural language into Fylorra automation rules

    Examples:
    - "Move all PDFs to Documents folder"
    - "Archive old files after 30 days"
    - "Organize invoices by company name"
    - "Copy new images to Backup drive"
    """

    RULE_GENERATION_PROMPT = """You are a file automation rule generator for Fylorra. Convert natural language instructions into structured automation rules.

Rule Schema:
{
  "event_types": ["created", "modified", "deleted", "moved"],
  "file_extensions": [".pdf", ".docx", ...] or ["*"] for all,
  "name_pattern": "regex pattern to match filename" (OPTIONAL - use for filtering by filename),
  "action_type": "copy|move|rename|delete|archive|organize|execute",
  "action_params": {...},
  "interpretation": "clear description of what this rule does",
  "confidence": 0.0-1.0,
  "explanation": "why you generated this rule",
  "warnings": ["list of potential issues"]
}

IMPORTANT: name_pattern field:
- Use this for filtering files by name (e.g., "invoice", "client", "IMG_")
- Must be a valid Python regex pattern
- Matches against the FULL filename including extension
- Examples:
  * ".*client.*" - matches files with "client" anywhere in name
  * "^IMG_.*" - matches files starting with "IMG_"
  * ".*invoice.*\\.pdf$" - matches PDFs with "invoice" in name

CRITICAL SAFETY RESTRICTIONS:
- Prefer safe actions (COPY, MOVE, ORGANIZE).
- RENAME/DELETE are allowed ONLY when the user explicitly asks for them.
- For DELETE, prefer recycle bin / safe trash and always emit warnings.
- For CLEAN_FOLDER, include min_age_seconds and skip_active_downloads=true. Never generate cleanup that deletes fresh temp/download files.
- Time-based requests MUST use a schedule block (daily time). Fylorra runs scheduled tasks while the app is open.

Allowed Action Types & Parameters:

1. COPY (SAFE - keeps original file)
{
  "action_type": "copy",
  "action_params": {
    "destination": "/absolute/path/to/folder",
    "handle_duplicates": "rename|skip|overwrite"
  }
}

2. MOVE (SAFE - relocates file, doesn't modify content)
{
  "action_type": "move",
  "action_params": {
    "destination": "/absolute/path/to/folder",
    "handle_duplicates": "rename|skip|overwrite"
  }
}

3. ORGANIZE (SAFE - moves files into organized structure)
{
  "action_type": "organize",
  "action_params": {
    "destination": "/base/folder/path",
    "organize_by": "extension|date|type"
  }
}
- extension: Creates subfolder per extension (.pdf, .docx)
- date: Creates year/month structure
- type: Groups by category (images, documents, videos, etc.)

Understanding Natural Language:

SAFE Actions:
MOVE keywords: move, send, transfer, put, relocate
COPY keywords: copy, duplicate, backup, clone
ORGANIZE keywords: organize, sort, categorize, arrange, group

FORBIDDEN Actions (respond with error):
DELETE keywords: delete, remove, trash, discard
RENAME keywords: rename, call, name
ARCHIVE keywords: archive, zip, compress, bundle
EXECUTE keywords: run, execute, open with, launch

File types mapping:
- "PDFs" → [".pdf"]
- "documents" → [".pdf", ".docx", ".doc", ".txt"]
- "images" → [".jpg", ".jpeg", ".png", ".gif", ".bmp"]
- "videos" → [".mp4", ".avi", ".mkv", ".mov"]
- "audio" → [".mp3", ".wav", ".flac"]
- "all files" → ["*"]
- "invoices", "receipts" → [".pdf"] + semantic filtering

Event types:
- "new files" → ["created"]
- "modified files" → ["modified"]
- "deleted files" → ["deleted"]
- Default if not specified: ["created"]

CRITICAL SAFETY RULE:
- ONLY use ["created"] by default for move/copy/organize actions
- NEVER include "modified", "deleted", or "moved" events for move/copy/organize actions
- Reason: Moving files triggers cascading events that cause infinite loops
- Example: Moving or organizing a file triggers "deleted" (from source) and "created" (at destination)
  which would trigger the SAME rule again, creating infinite loops and file corruption

Confidence Scoring:
- 0.90-1.0: Crystal clear intent, explicit destination, standard action
- 0.70-0.89: Clear intent, minor ambiguity (relative path, inferred type)
- 0.50-0.69: Ambiguous (unclear action, missing destination)
- 0.0-0.49: Cannot interpret reliably

Warnings to include:
- Relative paths (need absolute paths)
- Destructive actions (delete without recycle bin)
- Missing destinations
- Ambiguous file types
- Complex conditions not supported

Examples:

Input: "Move all PDFs to Documents folder"
Output:
{
  "event_types": ["created"],
  "file_extensions": [".pdf"],
  "action_type": "move",
  "action_params": {
    "destination": "{{NEEDS_USER_INPUT}}/Documents",
    "handle_duplicates": "rename"
  },
  "interpretation": "Move new PDF files to Documents folder",
  "confidence": 0.75,
  "explanation": "Clear intent to move PDFs. Needs full path for Documents folder.",
  "warnings": ["Destination path needs to be specified by user"]
}

Input: "Delete all content from temp folder C:\\Temp\\Cleanup every day at 12:00 AM"
Output:
{
  "schedule": {"type": "daily", "time": "12:00 AM"},
  "target_path": "C:\\Temp\\Cleanup",
  "event_types": [],
  "file_extensions": ["*"],
  "action_type": "clean_folder",
  "action_params": {"include_subfolders": true, "use_recycle_bin": true, "min_age_seconds": 604800, "skip_active_downloads": true},
  "interpretation": "Daily cleanup of temp files older than 7 days at 12:00 AM",
  "confidence": 0.70,
  "explanation": "This is a time-based cleanup task; it is implemented as a scheduled task while Fylorra is running.",
  "warnings": ["Destructive action: deletes old files only and uses Recycle Bin when available.", "Active browser/download temp files are skipped.", "Scheduled tasks run only while Fylorra is open."]
}

Input: "Organize images by date"
Output:
{
  "event_types": ["created"],
  "file_extensions": [".jpg", ".jpeg", ".png", ".gif", ".bmp"],
  "action_type": "organize",
  "action_params": {
    "destination": "{{CURRENT_FOLDER}}",
    "organize_by": "date"
  },
  "interpretation": "Organize new image files into date-based folder structure (year/month)",
  "confidence": 0.90,
  "explanation": "Clear intent to organize images by date. Will create YYYY/MM folder structure.",
  "warnings": []
}

Input: "Copy work PDFs to backup drive"
Output:
{
  "event_types": ["created"],
  "file_extensions": [".pdf"],
  "action_type": "copy",
  "action_params": {
    "destination": "{{NEEDS_USER_INPUT}}/WorkPDFs",
    "handle_duplicates": "rename"
  },
  "interpretation": "Copy work-related PDF files to backup location",
  "confidence": 0.70,
  "explanation": "Will copy PDFs to backup. Cannot filter by 'work-related' automatically - all PDFs will be copied.",
  "warnings": ["Cannot automatically detect 'work' PDFs - all PDFs will be copied", "Backup drive path needs to be specified"]
}

Input: "Move all music files that have mixdown in their filename to Finished Audio folder"
Output:
{
  "event_types": ["created"],
  "file_extensions": [".mp3", ".wav", ".flac", ".aac", ".m4a"],
  "name_pattern": "(?i).*mixdown.*",
  "action_type": "move",
  "action_params": {
    "destination": "{{CURRENT_FOLDER}}/Finished Audio",
    "handle_duplicates": "rename"
  },
  "interpretation": "Move music files containing 'mixdown' in the filename to the Finished Audio subfolder",
  "confidence": 0.95,
  "explanation": "Clear intent to filter music files by filename pattern. Using regex to match 'mixdown' anywhere in filename.",
  "warnings": []
}

Rules:
- Always return valid JSON
- Be honest about limitations
- Set confidence conservatively
- Provide clear warnings
- Use {{NEEDS_USER_INPUT}} or {{CURRENT_FOLDER}} for paths when unclear
- Explain what the rule ACTUALLY does, not what user wishes it would do

Return ONLY the JSON object."""

    # Supported actions (including destructive ones with warnings/confirmation in UI).
    SUPPORTED_ACTIONS = ["copy", "move", "organize", "rename", "delete", "archive", "execute", "clean_folder"]

    # Kept for backwards compatibility; currently unused (we warn instead of rejecting).
    FORBIDDEN_ACTIONS: list[str] = []

    # File type mappings for common terms
    FILE_TYPE_MAPPING = {
        "document": [".pdf", ".docx", ".doc", ".txt", ".rtf"],
        "documents": [".pdf", ".docx", ".doc", ".txt", ".rtf"],
        "pdf": [".pdf"],
        "pdfs": [".pdf"],
        "word": [".docx", ".doc"],
        "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"],
        "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"],
        "photo": [".jpg", ".jpeg", ".png"],
        "photos": [".jpg", ".jpeg", ".png"],
        "video": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
        "videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
        "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg"],
        "music": [".mp3", ".wav", ".flac", ".aac"],
        "code": [".py", ".js", ".java", ".cpp", ".c", ".html", ".css", ".go", ".rs"],
        "spreadsheet": [".xlsx", ".xls", ".csv"],
        "spreadsheets": [".xlsx", ".xls", ".csv"],
        "presentation": [".pptx", ".ppt"],
        "presentations": [".pptx", ".ppt"],
        "archive": [".zip", ".rar", ".7z", ".tar", ".gz"],
        "archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    }

    def __init__(self, ai_manager):
        self.ai_manager = ai_manager
        logger.info("NaturalLanguageRuleBuilder initialized")

    def generate_rule(self, natural_language_input: str, context: Optional[Dict] = None) -> RuleGenerationResult:
        """
        Generate automation rule from natural language

        Args:
            natural_language_input: User's natural language instruction
            context: Optional context (current folder path, etc.)

        Returns:
            RuleGenerationResult with generated rule and metadata
        """
        if not natural_language_input or len(natural_language_input.strip()) < 5:
            return self._create_error_result(natural_language_input, "Input too short")

        if not self.ai_manager or not getattr(self.ai_manager, "is_ready", False) or not getattr(self.ai_manager, "model", None):
            logger.warning("AI manager not ready for rule generation; using heuristic builder")
            return self._heuristic_rule(natural_language_input, context)

        try:
            logger.info(f"Generating rule from: {natural_language_input}")

            # Prepare context info for prompt
            context_info = ""
            if context:
                if "current_folder" in context:
                    context_info = f"\nContext: Current folder is {context['current_folder']}"

            # Call LLM - Qwen3-VL handles both text and vision excellently
            try:
                # Use chat completion with JSON response format constraint (forces valid JSON)
                response = self.ai_manager.model.create_chat_completion(
                    messages=[
                        {"role": "system", "content": self.RULE_GENERATION_PROMPT},
                        {"role": "user", "content": f"Convert to rule: {natural_language_input}{context_info}"},
                    ],
                    temperature=0.1,
                    max_tokens=600,
                    response_format={"type": "json_object"},  # Force valid JSON output
                )
                result_text = (response.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()

                result_data = self._extract_json_object(result_text)
                return self._build_result(natural_language_input, result_data)

            except Exception as e:
                # If JSON parsing failed, retry with even more explicit JSON instruction
                logger.warning(f"Primary rule generation failed: {e}")
                logger.debug(f"Raw output: {result_text[:500] if 'result_text' in locals() else 'N/A'}")

                try:
                    # Retry with simpler, more explicit prompt
                    retry_response = self.ai_manager.model.create_chat_completion(
                        messages=[
                            {"role": "system", "content": "You are a JSON generator. Always return valid JSON objects."},
                            {"role": "user", "content": (
                                f"Generate a JSON automation rule for: {natural_language_input}\n\n"
                                "Required JSON structure:\n"
                                '{"event_types": ["created"], "file_extensions": [".pdf"], "action_type": "move", '
                                '"action_params": {"destination": "path", "handle_duplicates": "rename"}, '
                                '"interpretation": "description", "confidence": 0.8, "explanation": "reason", "warnings": []}'
                            )},
                        ],
                        temperature=0.0,
                        max_tokens=400,
                        response_format={"type": "json_object"},  # Force valid JSON
                    )

                    result_text2 = (retry_response.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                    result_data2 = self._extract_json_object(result_text2)
                    return self._build_result(natural_language_input, result_data2)

                except Exception as e2:
                    logger.warning(f"Retry failed, using heuristic rule builder: {e2}")
                    logger.debug(f"Retry output: {result_text2[:500] if 'result_text2' in locals() else 'N/A'}")
                    return self._heuristic_rule(natural_language_input, context)

        except Exception as e:
            logger.error(f"Rule generation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._create_error_result(natural_language_input, str(e))

    def _extract_json_object(self, text: str) -> Dict[str, Any]:
        """
        Extract and parse the first JSON object from model output.
        Models often wrap JSON in prose or code fences; this makes parsing resilient.
        """
        candidate = (text or "").strip()

        # Remove markdown code fences if present
        if candidate.startswith("```"):
            parts = candidate.split("```")
            if len(parts) >= 2:
                candidate = parts[1]
            candidate = candidate.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()

        # Trim to the outermost JSON object
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in model output")

        candidate = candidate[start : end + 1].strip()

        # Common cleanup: remove trailing commas before } or ]
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

        return json.loads(candidate)

    def _heuristic_rule(self, natural_language_input: str, context: Optional[Dict]) -> RuleGenerationResult:
        """
        Best-effort non-AI fallback for common instructions.
        This keeps the feature usable even when the current model can't produce valid JSON.
        """
        text = (natural_language_input or "").strip()
        lowered = text.lower()

        # Time-based scheduled cleanup (common request). This runs while Fylorra is open.
        if any(k in lowered for k in ["every day", "daily", "everyday"]) and any(k in lowered for k in ["delete", "remove", "clean"]):
            # Best-effort parse: "... folder: PATH ... at HH:MM ..."
            m_path = re.search(r"(?:folder\s*[:=]?\s*)([a-zA-Z]:\\[^\n]+)", text)
            m_time = re.search(r"\b(?:at)\s+(\d{1,2}:\d{2}\s*(?:AM|PM)?)\b", text, flags=re.IGNORECASE)
            target = m_path.group(1).strip() if m_path else None
            when = m_time.group(1).strip() if m_time else "12:00 AM"
            if target:
                rule = {
                    "schedule": {"type": "daily", "time": when},
                    "target_path": target,
                    "event_types": [],
                    "file_extensions": ["*"],
                    "action_type": "clean_folder",
                    "action_params": {
                        "include_subfolders": True,
                        "use_recycle_bin": True,
                        "min_age_seconds": 604800,
                        "skip_active_downloads": True,
                    },
                }
                return RuleGenerationResult(
                    rule=rule,
                    interpretation=f"Daily cleanup of files older than 7 days at {when}",
                    confidence=0.65,
                    explanation="Time-based cleanup is implemented as a scheduled task while Fylorra is running.",
                    warnings=[
                        "Destructive action: deletes old files only and uses Recycle Bin when available.",
                        "Active browser/download temp files are skipped.",
                        "Scheduled tasks run only while Fylorra is open.",
                    ],
                    original_input=natural_language_input,
                    model_used="heuristic",
                )

        # Keep heuristic limited to common SAFE rules; destructive operations are handled by the AI path with UI confirmation.
        if any(k in lowered for k in ["delete", "remove", "trash", "rename", "execute", "run ", "launch", "archive", "zip", "compress"]):
            return self._create_error_result(
                natural_language_input,
                "This request includes destructive/advanced actions. Use the AI model to generate it (with warnings), or configure it manually.",
            )

        # Action type
        action_type = None
        if any(k in lowered for k in ["move", "send", "transfer", "relocate", "put in", "put into"]):
            action_type = "move"
        elif any(k in lowered for k in ["copy", "duplicate", "backup", "clone"]):
            action_type = "copy"
        elif any(k in lowered for k in ["organize", "sort", "categorize", "group", "arrange"]):
            action_type = "organize"
        else:
            action_type = "copy"  # safest default

        # Event types (default created only)
        event_types = ["created"]
        if "modified" in lowered or "change" in lowered:
            event_types = ["created", "modified"]

        # Extensions
        file_extensions = ["*"]
        for key, exts in self.FILE_TYPE_MAPPING.items():
            if re.search(rf"\b{re.escape(key)}\b", lowered):
                file_extensions = exts
                break

        # Name pattern: look for quoted phrases or 'contains X'
        name_pattern = None
        m = re.search(r"['\"]([^'\"]{2,50})['\"]", text)
        if m:
            phrase = re.escape(m.group(1))
            name_pattern = f"(?i).*{phrase}.*"
        else:
            m2 = re.search(r"contain(?:s|ing)?\s+([A-Za-z0-9_\-]{2,50})", text, flags=re.IGNORECASE)
            if m2:
                phrase = re.escape(m2.group(1))
                name_pattern = f"(?i).*{phrase}.*"

        current_folder = None
        if context and isinstance(context, dict):
            current_folder = context.get("current_folder")

        warnings: List[str] = []

        if action_type in ["copy", "move"]:
            destination = None
            # Very rough destination detection
            m3 = re.search(r"\bto\s+(.+)$", lowered)
            if m3:
                destination = m3.group(1).strip()

            destination_resolved = self._resolve_destination(destination, current_folder, warnings)
            action_params = {"destination": destination_resolved, "handle_duplicates": "rename"}

        else:
            # organize
            organize_by = "extension"
            if "date" in lowered:
                organize_by = "date"
            elif "type" in lowered or "category" in lowered:
                organize_by = "type"

            destination = "{{CURRENT_FOLDER}}" if current_folder else "{{NEEDS_USER_INPUT}}"
            action_params = {"destination": destination, "organize_by": organize_by}

        # Safety: avoid event cascades for file-routing actions.
        if action_type in ["copy", "move", "organize"]:
            event_types = ["created"]
            if "modified" in lowered:
                warnings.append("File routing rules are limited to created events to prevent repeated actions while files are changing")

        rule: Dict[str, Any] = {
            "event_types": event_types,
            "file_extensions": file_extensions,
            "action_type": action_type,
            "action_params": action_params,
        }
        if name_pattern:
            rule["name_pattern"] = name_pattern

        interpretation = f"{action_type.title()} files matching filters"
        confidence = 0.55
        explanation = "Used heuristic rule generation because the AI response was invalid JSON."
        if file_extensions != ["*"]:
            interpretation += f" ({', '.join(file_extensions)})"
        if name_pattern:
            interpretation += " with filename filter"

        return RuleGenerationResult(
            rule=rule,
            interpretation=interpretation,
            confidence=confidence,
            explanation=explanation,
            warnings=warnings,
            original_input=natural_language_input,
            model_used="heuristic",
        )

    def _resolve_destination(self, destination: Optional[str], current_folder: Optional[str], warnings: List[str]) -> str:
        """
        Resolve a destination string into an absolute path when possible.
        Supports common Windows folders ("Documents", "Downloads", etc.) to make
        simple rules work without requiring user edits.
        """
        if not destination:
            warnings.append("Destination path needs to be specified by user")
            return "{{NEEDS_USER_INPUT}}"

        dest = destination.strip().strip('"').strip("'")

        # Remove trailing generic nouns
        dest = re.sub(r"\b(folder|directory|dir|path|location)\b", "", dest).strip()
        dest = re.sub(r"\s+", " ", dest).strip()

        # Absolute path?
        if dest.startswith(("/", "\\")) or re.match(r"^[a-zA-Z]:[\\\\/]", dest):
            return dest

        # Known user folders (Windows)
        known = {
            "documents": "Documents",
            "document": "Documents",
            "downloads": "Downloads",
            "download": "Downloads",
            "desktop": "Desktop",
            "pictures": "Pictures",
            "photos": "Pictures",
            "videos": "Videos",
            "music": "Music",
        }

        # Support "documents/work" or "documents work" as subfolder.
        # Prefer splitting on / or \\, otherwise keep as tokens.
        parts = re.split(r"[\\/]+", dest)
        if len(parts) == 1:
            parts = dest.split(" ")

        head = (parts[0] or "").lower()
        tail = parts[1:]

        if head in known:
            base = Path.home() / known[head]
            for seg in tail:
                seg = seg.strip()
                if not seg:
                    continue
                base = base / seg
            return str(base)

        # If we have current_folder, resolve relative to it.
        if current_folder:
            return str(Path(current_folder) / dest)

        warnings.append("Destination path may be relative; consider using an absolute path")
        return "{{NEEDS_USER_INPUT}}/" + dest

    def _build_result(self, original_input: str, data: Dict) -> RuleGenerationResult:
        """Build RuleGenerationResult from LLM response"""

        # Extract fields
        data = data if isinstance(data, dict) else {}
        interpretation = str(data.get("interpretation", "") or "")
        try:
            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.0))))
        except Exception:
            confidence = 0.0
        explanation = str(data.get("explanation", "") or "")
        warnings_raw = data.get("warnings", [])
        if isinstance(warnings_raw, list):
            warnings = [str(w) for w in warnings_raw if str(w).strip()]
        elif warnings_raw:
            warnings = [str(warnings_raw)]
        else:
            warnings = []

        # Build rule structure
        rule = None
        action_type = str(data.get("action_type") or "").strip().lower()

        if action_type in self.SUPPORTED_ACTIONS:
            # CRITICAL: For file-routing actions, force only "created" events to prevent event cascades.
            event_types_raw = data.get("event_types", ["created"])
            if not isinstance(event_types_raw, list):
                event_types_raw = ["created"]
            allowed_events = {"created", "modified", "deleted", "moved"}
            event_types = [str(e).strip().lower() for e in event_types_raw if str(e).strip().lower() in allowed_events]
            if not event_types and not isinstance(data.get("schedule"), dict):
                event_types = ["created"]
            if action_type in ["move", "copy", "organize"]:
                # SAFETY: Only allow "created" for routing actions to prevent event cascade loops.
                if "modified" in event_types or "deleted" in event_types or "moved" in event_types:
                    logger.warning(f"Forcing event_types to ['created'] for {action_type} action to prevent infinite loops")
                    event_types = ["created"]

            file_exts_raw = data.get("file_extensions", ["*"])
            if isinstance(file_exts_raw, str):
                file_exts_raw = [file_exts_raw]
            if not isinstance(file_exts_raw, list):
                file_exts_raw = ["*"]
            file_extensions = []
            for ext in file_exts_raw:
                value = str(ext or "").strip().lower()
                if not value:
                    continue
                if value not in {"*", ".*"} and not value.startswith("."):
                    value = "." + value
                file_extensions.append(value)
            if not file_extensions:
                file_extensions = ["*"]

            action_params = data.get("action_params", {})
            if not isinstance(action_params, dict):
                action_params = {}

            rule = {
                "event_types": event_types,
                "file_extensions": file_extensions,
                "action_type": action_type,
                "action_params": action_params
            }
            name_pattern = str(data.get("name_pattern") or "").strip()
            if name_pattern:
                try:
                    re.compile(name_pattern)
                    rule["name_pattern"] = name_pattern
                except re.error:
                    warnings.append("Ignored invalid filename regex from AI output")
                    confidence = min(confidence, 0.6)

            # Optional schedule support (time-based tasks).
            if isinstance(data.get("schedule"), dict):
                rule["schedule"] = data.get("schedule")
            if data.get("target_path"):
                rule["target_path"] = data.get("target_path")

            # Add guardrail warnings for destructive actions.
            if action_type in ["delete", "clean_folder", "execute"]:
                if "Destructive action: requires confirmation" not in warnings:
                    warnings.append("Destructive action: requires confirmation")
                confidence = min(confidence, 0.75)

        return RuleGenerationResult(
            rule=rule,
            interpretation=interpretation,
            confidence=confidence,
            explanation=explanation,
            warnings=warnings,
            original_input=original_input,
            model_used=str(getattr(self.ai_manager, "model_file", getattr(self.ai_manager, "MODEL_FILE", "ai")))
        )

    def _create_error_result(self, original_input: str, error_msg: str) -> RuleGenerationResult:
        """Create error result"""
        return RuleGenerationResult(
            rule=None,
            interpretation="Could not generate rule",
            confidence=0.0,
            explanation=error_msg,
            warnings=[error_msg],
            original_input=original_input,
            model_used="error"
        )

    def validate_rule(self, rule: Dict) -> tuple[bool, List[str]]:
        """
        Validate generated rule

        Returns:
            (is_valid, list_of_issues)
        """
        issues = []

        # Check required fields
        if "action_type" not in rule:
            issues.append("Missing action_type")

        if not rule.get("schedule") and ("event_types" not in rule or not rule["event_types"]):
            issues.append("Missing or empty event_types")

        if "action_params" not in rule:
            issues.append("Missing action_params")

        # Check action-specific requirements
        action_type = rule.get("action_type")

        if action_type in ["copy", "move"]:
            dest = rule.get("action_params", {}).get("destination")
            if not dest:
                issues.append("Missing destination path")
            elif "{{NEEDS_USER_INPUT}}" in dest:
                issues.append("Destination path requires user input")

        if action_type == "rename":
            pattern = rule.get("action_params", {}).get("pattern")
            if not pattern:
                issues.append("Missing rename pattern")

        if action_type == "organize":
            organize_by = rule.get("action_params", {}).get("organize_by")
            if organize_by not in ["extension", "date", "type"]:
                issues.append(f"Invalid organize_by value: {organize_by}")

        return (len(issues) == 0, issues)
