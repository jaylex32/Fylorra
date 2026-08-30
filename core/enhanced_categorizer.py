"""
Fylorra - Enhanced File Categorization Engine
Comprehensive file type detection + Optional AI vision for images
50+ categories for perfect office organization
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import os
import sqlite3
import time
import re

from dataclasses import dataclass as _dc

logger = logging.getLogger(__name__)


@dataclass
class CategoryConfig:
    """Configuration for a file category"""
    extensions: List[str]
    folder: str
    keywords: List[str] = None
    ai_vision: bool = False
    ai_prompts: List[str] = None


class EnhancedCategorizer:
    """
    Hybrid file categorization:
    - Tier 1: Fast rule-based (50+ categories)
    - Tier 2: AI vision for images (optional)
    - Tier 3: Semantic analysis (optional)
    """

    # Comprehensive category definitions (50+ categories)
    CATEGORIES = {
        # === CLEANUP (2 categories) ===
        "empty_files": CategoryConfig(
            extensions=[],
            folder="Cleanup/Empty Files",
            keywords=["0kb", "0 kb"],
        ),
        "empty_folders": CategoryConfig(
            extensions=[],
            folder="Cleanup/Empty Folders",
        ),
        "ignored_projects": CategoryConfig(
            extensions=[],
            folder="Ignored/Projects",
        ),

        # === OFFICE & DOCUMENTS (12 categories) ===
        "word_documents": CategoryConfig(
            extensions=[".doc", ".docx", ".dot", ".dotx", ".docm", ".dotm", ".odt", ".pages"],
            folder="Documents/Word"
        ),
        "excel_spreadsheets": CategoryConfig(
            extensions=[".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".csv", ".ods", ".numbers"],
            folder="Documents/Excel"
        ),
        "powerpoint_presentations": CategoryConfig(
            extensions=[".ppt", ".pptx", ".pptm", ".pot", ".potx", ".ppsx", ".odp", ".key"],
            folder="Documents/PowerPoint"
        ),
        "pdf_documents": CategoryConfig(
            extensions=[".pdf"],
            folder="Documents/PDF"
        ),
        "text_files": CategoryConfig(
            extensions=[".txt", ".rtf", ".md", ".markdown", ".log", ".nfo"],
            folder="Documents/Text"
        ),
        "notes": CategoryConfig(
            extensions=[".one", ".onenote", ".note"],
            folder="Documents/Notes"
        ),
        "ebooks": CategoryConfig(
            extensions=[".epub", ".mobi", ".azw", ".azw3"],
            folder="Books"
        ),
        "publisher": CategoryConfig(
            extensions=[".pub", ".indd"],
            folder="Documents/Publishing"
        ),
        "receipts_invoices": CategoryConfig(
            extensions=[".pdf", ".jpg", ".jpeg", ".png"],
            keywords=["receipt", "invoice", "bill", "statement", "order"],
            folder="Documents/Financial/Receipts"
        ),
        "bank_statements": CategoryConfig(
            extensions=[".pdf", ".csv", ".qfx", ".ofx", ".qbo"],
            keywords=["bank statement", "credit card statement", "statement period", "account summary", "ending balance"],
            folder="Documents/Financial/Statements",
        ),
        "tax_forms": CategoryConfig(
            extensions=[".pdf", ".csv", ".txt"],
            keywords=["w-2", "w2", "w-9", "w9", "1099", "irs", "tax return", "form 1040"],
            folder="Documents/Financial/Taxes",
        ),
        "legal_contracts": CategoryConfig(
            extensions=[".pdf", ".doc", ".docx", ".txt"],
            keywords=["contract", "agreement", "nda", "lease", "terms", "policy", "consent"],
            folder="Documents/Legal",
        ),
        "resumes_cv": CategoryConfig(
            extensions=[".pdf", ".doc", ".docx", ".txt"],
            keywords=["resume", "curriculum vitae", "cv", "cover letter", "experience", "education"],
            folder="Documents/Resumes",
        ),
        "manuals_guides": CategoryConfig(
            extensions=[".pdf", ".txt"],
            keywords=["manual", "guide", "instructions", "installation", "wiring", "datasheet", "specification"],
            folder="Documents/Manuals",
        ),
        "financial_documents": CategoryConfig(
            extensions=[".qfx", ".qbo", ".ofx", ".qif"],
            folder="Documents/Financial"
        ),

        # === DEVELOPMENT & CODE (15 categories) ===
        "web_frontend": CategoryConfig(
            extensions=[".html", ".htm", ".css", ".scss", ".sass", ".less"],
            folder="Code/Web/Frontend"
        ),
        "javascript": CategoryConfig(
            extensions=[".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"],
            folder="Code/JavaScript"
        ),
        "python": CategoryConfig(
            extensions=[".py", ".pyw", ".pyx", ".ipynb"],
            folder="Code/Python"
        ),
        "java": CategoryConfig(
            extensions=[".java", ".class", ".jar"],
            folder="Code/Java"
        ),
        "c_cpp": CategoryConfig(
            extensions=[".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"],
            folder="Code/C-C++"
        ),
        "csharp": CategoryConfig(
            extensions=[".cs", ".csx"],
            folder="Code/CSharp"
        ),
        "go": CategoryConfig(
            extensions=[".go"],
            folder="Code/Go"
        ),
        "rust": CategoryConfig(
            extensions=[".rs"],
            folder="Code/Rust"
        ),
        "ruby": CategoryConfig(
            extensions=[".rb", ".erb"],
            folder="Code/Ruby"
        ),
        "php": CategoryConfig(
            extensions=[".php", ".php3", ".php4", ".php5", ".phtml"],
            folder="Code/PHP"
        ),
        "shell_scripts": CategoryConfig(
            extensions=[".sh", ".bash", ".zsh", ".fish"],
            folder="Code/Scripts"
        ),
        "powershell": CategoryConfig(
            extensions=[".ps1", ".psm1", ".psd1"],
            folder="Code/PowerShell"
        ),
        "batch_scripts": CategoryConfig(
            extensions=[".bat", ".cmd"],
            folder="Code/Batch"
        ),
        "sql": CategoryConfig(
            extensions=[".sql", ".mysql", ".pgsql"],
            folder="Code/SQL"
        ),
        "config_files": CategoryConfig(
            extensions=[".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".xml"],
            folder="Config"
        ),

        # === MEDIA & DESIGN (10 categories) ===
        "photos": CategoryConfig(
            extensions=[".jpg", ".jpeg", ".png", ".heic", ".heif", ".avif", ".jfif", ".jxl", ".webp", ".bmp", ".tiff", ".tif"],
            keywords=["photo", "img", "camera", "dsc", "pic", "image"],
            folder="Photos",
            ai_vision=True,
            ai_prompts=["Does this show people, portraits, or selfies?"]
        ),
        "screenshots": CategoryConfig(
            extensions=[".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"],
            keywords=["screenshot", "screen_", "_screen", "capture", "snap", "scr_", "_scr"],
            folder="Screenshots",
            ai_vision=True,
            ai_prompts=[
                "Is this a screenshot of code or a code editor?",
                "Is this a screenshot of a user interface or application?"
            ]
        ),
        "vector_graphics": CategoryConfig(
            extensions=[".svg", ".ai", ".eps"],
            folder="Design/Vector"
        ),
        "design_files": CategoryConfig(
            extensions=[".psd", ".psb", ".xcf", ".sketch", ".fig", ".xd"],
            folder="Design/Projects"
        ),
        "diagrams": CategoryConfig(
            extensions=[".vsd", ".vsdx", ".drawio", ".dia"],
            folder="Diagrams"
        ),
        "3d_models": CategoryConfig(
            extensions=[".obj", ".fbx", ".blend", ".3ds", ".max", ".c4d", ".stl", ".gltf", ".glb"],
            folder="3D Models"
        ),
        "cad_files": CategoryConfig(
            extensions=[".dwg", ".dxf", ".step", ".iges", ".stp"],
            folder="CAD"
        ),
        "gifs_memes": CategoryConfig(
            extensions=[".gif"],
            folder="Memes"
        ),
        "icons": CategoryConfig(
            extensions=[".ico", ".icns"],
            folder="Design/Icons"
        ),

        # === AUDIO & VIDEO (8 categories) ===
        "midi_files": CategoryConfig(
            extensions=[".mid", ".midi"],
            folder="Music/MIDI"
        ),
        "audio_lossless": CategoryConfig(
            extensions=[".flac", ".alac", ".ape", ".wav", ".aiff"],
            folder="Music/Lossless"
        ),
        "audio_clips": CategoryConfig(
            extensions=[".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".flac"],
            keywords=["sfx", "sound", "clip", "voice", "recording", "memo"],
            folder="Audio/Clips"
        ),
        "audio_compressed": CategoryConfig(
            extensions=[".mp3", ".aac", ".m4a", ".ogg", ".opus", ".wma", ".mp2"],
            folder="Music"
        ),
        "audio_projects": CategoryConfig(
            extensions=[".aup", ".aup3", ".flp", ".als", ".logic", ".logicx", ".rpp", ".sesx", ".ptx", ".cpr", ".band"],
            folder="Music/Projects"
        ),
        "audio_project_assets": CategoryConfig(
            extensions=[
                ".adg", ".adv", ".alc", ".asd",
                ".fxp", ".fxb", ".vstpreset", ".aupreset",
                ".nksf", ".nksn", ".nki", ".nkx",
                ".bamp", ".fxcompstate", ".fst", ".mfp", ".asfx",
            ],
            folder="Music/Projects/Assets"
        ),
        "videos": CategoryConfig(
            extensions=[".mp4", ".mkv", ".webm", ".mov", ".avi"],
            folder="Videos"
        ),
        "videos_hd": CategoryConfig(
            extensions=[".m2ts", ".mts", ".m4v"],
            folder="Videos/HD"
        ),
        "videos_legacy": CategoryConfig(
            extensions=[".wmv", ".flv", ".3gp", ".mpg", ".mpeg"],
            folder="Videos/Legacy"
        ),
        "video_projects": CategoryConfig(
            extensions=[".prproj", ".aep", ".veg", ".fcpx"],
            folder="Videos/Projects"
        ),
        "subtitles": CategoryConfig(
            extensions=[".srt", ".sub", ".ass", ".vtt"],
            folder="Videos/Subtitles"
        ),

        # === ARCHIVES & SYSTEM (7 categories) ===
        "compressed_archives": CategoryConfig(
            extensions=[".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".lz", ".cab"],
            folder="Archives"
        ),
        "disk_images": CategoryConfig(
            extensions=[".iso", ".img", ".dmg", ".vhd", ".vmdk"],
            folder="Disk Images"
        ),
        "executables": CategoryConfig(
            extensions=[".exe", ".msi", ".app", ".deb", ".rpm", ".apk"],
            folder="Programs"
        ),
        "databases": CategoryConfig(
            extensions=[".db", ".sqlite", ".sqlite3", ".mdb", ".accdb"],
            folder="Databases"
        ),
        "shortcuts": CategoryConfig(
            extensions=[".lnk", ".url", ".webloc"],
            folder="Shortcuts"
        ),
        "fonts": CategoryConfig(
            extensions=[".ttf", ".otf", ".woff", ".woff2", ".eot"],
            folder="Fonts"
        ),
        "torrents": CategoryConfig(
            extensions=[".torrent"],
            folder="Torrents"
        ),

        # === MISCELLANEOUS (2 categories) ===
        "backups": CategoryConfig(
            extensions=[".bak", ".backup", ".old", ".tmp"],
            keywords=["backup", "bak"],
            folder="Backups"
        ),
        "other": CategoryConfig(
            extensions=[],
            folder="Other"
        ),
    }

    def __init__(self, ai_manager=None, use_ai_vision: bool = False):
        """
        Initialize enhanced categorizer

        Args:
            ai_manager: AI manager for vision analysis (optional)
            use_ai_vision: Whether to use AI vision for images
        """
        self.ai_manager = ai_manager
        self.use_ai_vision = use_ai_vision and ai_manager is not None
        self.use_ai_documents = False
        self._ai_doc_calls = 0
        self._ai_doc_calls_max = 40
        self.last_decisions: dict[str, "CategoryDecision"] = {}

        # Persistent cache for vision results (keeps repeat runs fast).
        try:
            cache_dir = Path.home() / ".fylorra"
            cache_dir.mkdir(exist_ok=True)
            self._vision_cache_db = cache_dir / "categorizer_vision_cache.db"
            with sqlite3.connect(self._vision_cache_db) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS vision_cache(
                        path TEXT PRIMARY KEY,
                        size INTEGER NOT NULL,
                        mtime REAL NOT NULL,
                        category TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.commit()
        except Exception:
            self._vision_cache_db = None

        # Build reverse lookup: extension -> category
        self._extension_map: Dict[str, str] = {}
        for category_name, config in self.CATEGORIES.items():
            for ext in config.extensions:
                # Store first match (priority order)
                if ext not in self._extension_map:
                    self._extension_map[ext] = category_name

        logger.info(f"Enhanced categorizer initialized with {len(self.CATEGORIES)} categories, AI vision: {self.use_ai_vision}")

    @_dc(frozen=True)
    class CategoryDecision:
        category: str
        confidence: float
        method: str
        reason: str

    def _record_decision(self, file_path: Path, decision: "CategoryDecision") -> None:
        try:
            self.last_decisions[str(file_path)] = decision
        except Exception:
            pass

    def categorize_file(self, file_path: Path) -> Optional[str]:
        """
        Categorize a single file

        Returns:
            Category name or None
        """
        if not file_path.exists() or not file_path.is_file():
            return None

        ext = file_path.suffix.lower()
        filename = file_path.stem.lower()
        parent_folder = file_path.parent.name.lower()

        # Get full parent path for deeper folder structure analysis
        parent_path_str = str(file_path.parent).lower()

        # Size-based heuristics (empty files, clips vs full songs, etc.)
        try:
            st = file_path.stat()
            size = int(st.st_size)
        except Exception:
            size = -1

        if size == 0:
            self._record_decision(file_path, self.CategoryDecision("empty_files", 1.0, "size", "Empty file (0 bytes)"))
            return "empty_files"

        normalized_name = self._normalize_text_for_match(file_path.stem)
        normalized_parent = self._normalize_text_for_match(str(file_path.parent))

        # Common camera / device patterns that aren't covered by keywords alone.
        if ext in {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".avif", ".bmp", ".tif", ".tiff"}:
            if re.match(r"^(img|dsc|pxl|mvimg|vid)_[0-9]{4,}", normalized_name):
                self._record_decision(file_path, self.CategoryDecision("photos", 0.85, "name_pattern", "Camera/device filename pattern"))
                return "photos"
            if "screenshot" in normalized_name or "screen" in normalized_name:
                self._record_decision(file_path, self.CategoryDecision("screenshots", 0.75, "name_pattern", "Name contains screenshot/screen"))
                return "screenshots"

        # Small audio files can be clips/voice notes/sfx, but avoid classifying whole music libraries as clips.
        if ext in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".wma", ".flac"} and size > 0:
            # Only treat as a clip if the name or folder hints at clips/sfx OR it is extremely small.
            clip_hint = any(w in normalized_parent for w in ["clip", "clips", "sfx", "fx", "sound", "sounds", "voice", "memo", "recording", "recordings", "sample", "samples"])
            clip_hint = clip_hint or any(w in normalized_name for w in ["sfx", "fx", "voice", "memo", "sample"])
            if size <= 350_000 or (clip_hint and size <= 2_000_000):
                self._record_decision(file_path, self.CategoryDecision("audio_clips", 0.7, "size_heuristic", "Small audio file / clip hint"))
                return "audio_clips"

        # Step 0: Check parent folder path for existing organization
        # This preserves user's existing folder structure
        for category_name, config in self.CATEGORIES.items():
            if config.keywords:
                for keyword in config.keywords:
                    # Check if keyword appears in parent folder path
                    if self._keyword_match(keyword, raw_text=parent_path_str, normalized_text=normalized_parent) or (keyword in parent_folder):
                        # Verify extension matches to avoid false positives
                        if not config.extensions or ext in config.extensions:
                            self._record_decision(file_path, self.CategoryDecision(category_name, 0.7, "parent_keyword", f"Matched folder keyword '{keyword}'"))
                            return category_name

        # Step 1: Check filename for keyword matches (receipts, screenshots, etc.)
        for category_name, config in self.CATEGORIES.items():
            if config.keywords:
                for keyword in config.keywords:
                    if self._keyword_match(keyword, raw_text=filename, normalized_text=normalized_name):
                        # Avoid false positives: only allow keyword match if extension is compatible when extensions are defined.
                        if config.extensions and ext not in config.extensions:
                            continue
                        self._record_decision(file_path, self.CategoryDecision(category_name, 0.6, "name_keyword", f"Matched filename keyword '{keyword}'"))
                        return category_name

        # Step 2: Extension-based lookup
        category = self._extension_map.get(ext)

        if category:
            # PDF content sniffing (helps when filenames don't contain "invoice", etc.)
            if ext == ".pdf":
                content_cat = self._pdf_content_category(file_path)
                if content_cat:
                    self._record_decision(file_path, self.CategoryDecision(content_cat, 0.9, "pdf_text", "Matched PDF content"))
                    return content_cat

                # If scanned/empty text, optionally use AI vision on the first page (high-confidence only).
                if self.use_ai_documents and self.ai_manager and getattr(self.ai_manager, "is_ready", False):
                    if self._ai_doc_calls < int(self._ai_doc_calls_max):
                        ai_cat = self._ai_pdf_vision_category(file_path)
                        if ai_cat:
                            self._ai_doc_calls += 1
                            self._record_decision(file_path, self.CategoryDecision(ai_cat, 0.9, "ai_pdf_vision", "AI classified scanned PDF"))
                            return ai_cat

            # Step 3: AI vision enhancement (if enabled and applicable)
            if self.use_ai_vision and self.CATEGORIES[category].ai_vision:
                ai_category = self._ai_vision_categorize(file_path, category)
                if ai_category:
                    self._record_decision(file_path, self.CategoryDecision(ai_category, 0.92, "ai_image_vision", "AI classified image"))
                    return ai_category

            self._record_decision(file_path, self.CategoryDecision(category, 0.85, "extension", f"Known extension '{ext}'"))
            return category

        # Fallback: attempt to sniff common formats by magic bytes (no extension or unknown extension).
        sniffed = self._sniff_magic_category(file_path)
        if sniffed:
            self._record_decision(file_path, self.CategoryDecision(sniffed, 0.8, "magic", "Matched file signature"))
        return sniffed or "other"

    def _ai_pdf_vision_category(self, pdf_path: Path) -> Optional[str]:
        """
        Use the vision model to classify a scanned/low-text PDF by rendering the first page.
        Returns a high-confidence category or None.
        """
        if not self.ai_manager or not getattr(self.ai_manager, "is_ready", False):
            return None
        try:
            if hasattr(self.ai_manager, "ensure_kind"):
                self.ai_manager.ensure_kind("vision")
        except Exception:
            pass

        # Cache hit?
        try:
            if self._vision_cache_db is not None:
                st = pdf_path.stat()
                with sqlite3.connect(self._vision_cache_db) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT category, size, mtime FROM vision_cache WHERE path = ?",
                        (str(pdf_path),),
                    ).fetchone()
                if row and int(row["size"]) == int(st.st_size) and float(row["mtime"]) == float(st.st_mtime):
                    cached = str(row["category"])
                    return cached or None
        except Exception:
            pass

        # If we already have text, don't use vision.
        if self._pdf_text_snippet(pdf_path):
            return None

        try:
            import fitz  # type: ignore
        except Exception:
            return None

        try:
            import base64
            import tempfile

            with tempfile.TemporaryDirectory(prefix="fylorra_pdfscan_") as td:
                img_path = Path(td) / "page1.png"
                doc = fitz.open(str(pdf_path))
                try:
                    if doc.page_count <= 0:
                        return None
                    page = doc.load_page(0)
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    pix.save(str(img_path))
                finally:
                    try:
                        doc.close()
                    except Exception:
                        pass

                try:
                    image_data = self.ai_manager._prepare_image(img_path)  # type: ignore[attr-defined]
                except Exception:
                    image_data = None
                if not image_data:
                    return None

                prompt = (
                    "Classify this PDF page into exactly ONE label and confidence.\n"
                    "Return ONLY JSON:\n"
                    "{\"label\":\"receipts_invoices|bank_statements|tax_forms|legal_contracts|resumes_cv|manuals_guides|unknown\",\"confidence\":0.0}\n"
                )

                resp = self.ai_manager.model.create_chat_completion(
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    temperature=0.1,
                    max_tokens=60,
                )
                out = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()

                data = None
                try:
                    out2 = out
                    if out2.startswith("```"):
                        parts = out2.split("```")
                        if len(parts) >= 2:
                            out2 = parts[1].strip()
                        if out2.lower().startswith("json"):
                            out2 = out2[4:].strip()
                    data = json.loads(out2)
                except Exception:
                    # best-effort parse first {...}
                    try:
                        start = out.find("{")
                        end = out.rfind("}")
                        if start != -1 and end != -1 and end > start:
                            data = json.loads(out[start : end + 1])
                    except Exception:
                        data = None

                if not isinstance(data, dict):
                    return None

                label = str(data.get("label") or "").strip()
                try:
                    conf = float(data.get("confidence", 0.0))
                except Exception:
                    conf = 0.0

                if label not in {"receipts_invoices", "bank_statements", "tax_forms", "legal_contracts", "resumes_cv", "manuals_guides"}:
                    return None
                if conf < 0.82:
                    return None

                # Persist cache
                try:
                    if self._vision_cache_db is not None:
                        st = pdf_path.stat()
                        with sqlite3.connect(self._vision_cache_db) as conn:
                            conn.execute(
                                """
                                INSERT INTO vision_cache(path, size, mtime, category, updated_at)
                                VALUES (?, ?, ?, ?, ?)
                                ON CONFLICT(path) DO UPDATE SET
                                    size=excluded.size,
                                    mtime=excluded.mtime,
                                    category=excluded.category,
                                    updated_at=excluded.updated_at
                                """,
                                (str(pdf_path), int(st.st_size), float(st.st_mtime), str(label), time.time()),
                            )
                            conn.commit()
                except Exception:
                    pass

                return label
        except Exception:
            return None

    @staticmethod
    def _normalize_text_for_match(s: str) -> str:
        s = (s or "").lower()
        s = s.replace("\\", " ").replace("/", " ")
        s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
        s = " ".join(s.split())
        return s

    @staticmethod
    def _keyword_match(keyword: str, *, raw_text: str, normalized_text: str) -> bool:
        """
        Safer keyword matching:
        - For keywords containing special pattern characters (_ - .), use raw substring match (keeps patterns like screen_).
        - For short keywords (<=4), require whole-word matches to avoid 'pic' matching 'pick'.
        - For longer keywords, allow phrase match on normalized text.
        """
        kw = (keyword or "").strip().lower()
        if not kw:
            return False

        raw = (raw_text or "").lower()
        norm = (normalized_text or "").lower()

        if any(ch in kw for ch in ["_", "-", "."]) or kw.endswith("_") or kw.startswith("_"):
            return kw in raw

        kw_norm = EnhancedCategorizer._normalize_text_for_match(kw)
        if not kw_norm:
            return False

        # Phrase match with word boundaries on normalized text.
        if len(kw_norm) <= 4 and " " not in kw_norm:
            return bool(re.search(rf"(^| ){re.escape(kw_norm)}( |$)", norm))

        return bool(re.search(rf"(^| ){re.escape(kw_norm)}( |$)", norm)) or (kw_norm in norm)

    def _pdf_content_category(self, pdf_path: Path) -> Optional[str]:
        text = self._pdf_text_snippet(pdf_path)
        if not text:
            return None
        t = self._normalize_text_for_match(text)[:5000]

        def has_any(words: list[str]) -> bool:
            return any(w in t for w in words)

        if has_any(["invoice", "amount due", "total due", "bill to", "payment due", "statement"]):
            return "receipts_invoices"
        if has_any(["agreement", "contract", "terms and conditions", "lease", "non disclosure", "governing law"]):
            return "legal_contracts"
        if has_any(["curriculum vitae", "resume", "experience", "education", "skills"]):
            return "resumes_cv"
        if has_any(["installation", "instructions", "wiring", "datasheet", "user manual", "specification"]):
            return "manuals_guides"
        if has_any(["form 1040", "w 2", "w 9", "1099", "internal revenue service", "irs"]):
            return "tax_forms"
        if has_any(["statement period", "ending balance", "account summary", "available credit", "minimum payment"]):
            return "bank_statements"
        return None

    @staticmethod
    def _pdf_text_snippet(pdf_path: Path, *, max_chars: int = 6000) -> Optional[str]:
        try:
            import fitz  # type: ignore

            doc = fitz.open(str(pdf_path))
            try:
                if doc.page_count <= 0:
                    return None
                page = doc.load_page(0)
                text = page.get_text("text") or ""
                return text[:max_chars].strip() or None
            finally:
                try:
                    doc.close()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            from pypdf import PdfReader  # type: ignore

            r = PdfReader(str(pdf_path))
            if not r.pages:
                return None
            text = r.pages[0].extract_text() or ""
            return text[:max_chars].strip() or None
        except Exception:
            return None

    @staticmethod
    def _sniff_magic_category(file_path: Path) -> Optional[str]:
        try:
            with file_path.open("rb") as f:
                head = f.read(32)
        except Exception:
            return None

        if head.startswith(b"%PDF-"):
            return "pdf_documents"
        if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06") or head.startswith(b"PK\x07\x08"):
            return "compressed_archives"
        if head.startswith(b"7z\xBC\xAF\x27\x1C"):
            return "compressed_archives"
        if head.startswith(b"Rar!\x1A\x07"):
            return "compressed_archives"
        if head.startswith(b"\x1F\x8B"):
            return "compressed_archives"
        if head[4:8] == b"ftyp":
            return "videos"
        if head.startswith(b"ID3") or (len(head) > 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
            return "audio_compressed"
        if head.startswith(b"OggS"):
            return "audio_compressed"
        return None

    def _ai_vision_categorize(self, file_path: Path, base_category: str) -> Optional[str]:
        """
        Use AI vision to refine categorization for images
        Only called if AI is enabled and category supports it
        """
        if not self.ai_manager or not self.ai_manager.is_ready:
            return None
        try:
            if hasattr(self.ai_manager, "ensure_kind"):
                self.ai_manager.ensure_kind("vision")
        except Exception:
            pass

        try:
            if file_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
                return None

            # Cache hit?
            try:
                if self._vision_cache_db is not None:
                    st = file_path.stat()
                    with sqlite3.connect(self._vision_cache_db) as conn:
                        conn.row_factory = sqlite3.Row
                        row = conn.execute(
                            "SELECT category, size, mtime FROM vision_cache WHERE path = ?",
                            (str(file_path),),
                        ).fetchone()
                    if row and int(row["size"]) == int(st.st_size) and float(row["mtime"]) == float(st.st_mtime):
                        cached = str(row["category"])
                        return cached or None
            except Exception:
                pass

            # Minimal, constrained classification to keep output stable and fast.
            prompt = (
                "Classify this image into exactly ONE label from:\n"
                "- screenshot\n"
                "- photo\n"
                "- receipt\n"
                "- diagram\n"
                "- meme\n"
                "- other\n\n"
                "Output ONLY the label."
            )

            # Use the same image encoding approach as other AI modules.
            try:
                image_data = self.ai_manager._prepare_image(file_path)  # type: ignore[attr-defined]
            except Exception:
                image_data = None
            if not image_data:
                return None

            resp = self.ai_manager.model.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                temperature=0.1,
                max_tokens=10,
            )
            out = (resp.get("choices", [{}])[0].get("message", {}).get("content") or "").strip().lower()
            out = out.splitlines()[0].strip().strip("`\"' ")

            label = out
            mapped = None
            if label == "screenshot":
                mapped = "screenshots"
            elif label == "photo":
                mapped = "photos"
            elif label == "receipt":
                mapped = "receipts_invoices"
            elif label == "diagram":
                mapped = "diagrams"
            elif label == "meme":
                mapped = "gifs_memes"
            else:
                mapped = None

            # Persist cache
            try:
                if mapped and self._vision_cache_db is not None:
                    st = file_path.stat()
                    with sqlite3.connect(self._vision_cache_db) as conn:
                        conn.execute(
                            """
                            INSERT INTO vision_cache(path, size, mtime, category, updated_at)
                            VALUES (?, ?, ?, ?, ?)
                            ON CONFLICT(path) DO UPDATE SET
                                size=excluded.size,
                                mtime=excluded.mtime,
                                category=excluded.category,
                                updated_at=excluded.updated_at
                            """,
                            (str(file_path), int(st.st_size), float(st.st_mtime), str(mapped), time.time()),
                        )
                        conn.commit()
            except Exception:
                pass

            return mapped

        except Exception as e:
            logger.debug(f"AI vision failed for {file_path}: {e}")
            return None

    def get_category_folder(self, category: str) -> str:
        """Get folder path for a category"""
        config = self.CATEGORIES.get(category)
        if config:
            return config.folder
        return "Other"

    def get_all_categories(self) -> List[str]:
        """Get list of all category names"""
        return list(self.CATEGORIES.keys())

    def get_category_info(self, category: str) -> Optional[Dict]:
        """Get detailed info about a category"""
        config = self.CATEGORIES.get(category)
        if config:
            return {
                "extensions": config.extensions,
                "folder": config.folder,
                "keywords": config.keywords or [],
                "ai_enabled": config.ai_vision
            }
        return None

    def categorize_folder(
        self,
        folder_path: Path,
        include_subfolders: bool = True,
        progress_callback=None,
        cancel_check=None,  # callable() -> bool
        use_ai_vision: Optional[bool] = None,
        include_empty_folders: bool = True,
        smart_scope: bool = True,
        include_other: bool = False,
        use_ai_documents: bool = False,
        max_ai_documents: int = 40,
    ) -> Dict[str, List[Path]]:
        """
        Categorize all files in a folder

        Args:
            folder_path: Path to folder
            include_subfolders: Whether to recurse into subfolders
            progress_callback: Callback(message, progress, current, total)

        Returns:
            Dict mapping category names to file lists
        """
        if use_ai_vision is not None:
            self.use_ai_vision = bool(use_ai_vision) and self.ai_manager is not None

        folder_path = Path(folder_path)

        def is_project_marker(name: str) -> bool:
            name_l = (name or "").lower()
            if name_l in {
                "pyproject.toml",
                "requirements.txt",
                "setup.py",
                "package.json",
                "pnpm-lock.yaml",
                "yarn.lock",
                "cargo.toml",
                "go.mod",
                "pom.xml",
                "build.gradle",
                "settings.gradle",
                "cmakelists.txt",
                "makefile",
                "composer.json",
            }:
                return True
            if name_l.endswith((".sln", ".csproj", ".vcxproj", ".xcodeproj")):
                return True
            if name_l.endswith((".als", ".flp", ".aup", ".aup3", ".logicx", ".band", ".rpp", ".prproj", ".aep", ".veg")):
                return True
            return False

        def looks_like_project_root(root_path: Path, filenames: list[str]) -> bool:
            """
            Detect a project root folder that should not be reorganized (code repos, DAW projects, etc).
            """
            try:
                if any(is_project_marker(n) for n in filenames):
                    return True
            except Exception:
                pass

            rn = (root_path.name or "").lower()
            if any(k in rn for k in ["project", "projects", "ableton", "fl studio", "reaper", "pro tools", "logic", "premiere", "after effects"]):
                # If the folder name hints it's a project AND it contains typical project assets, treat as project.
                exts = {Path(n).suffix.lower() for n in filenames}
                if exts.intersection({".als", ".flp", ".aup", ".aup3", ".logicx", ".band", ".rpp", ".prproj", ".aep", ".veg", ".csproj", ".sln", ".py"}):
                    return True
                if exts.intersection({".adg", ".adv", ".alc", ".asd", ".vstpreset", ".fxp", ".fxb", ".nksf", ".nksn", ".nki", ".nkx", ".bamp", ".fxcompstate", ".fst"}):
                    return True
            return False

        skipped_projects: list[Path] = []
        self.use_ai_documents = bool(use_ai_documents) and bool(self.ai_manager and getattr(self.ai_manager, "is_ready", False))
        self._ai_doc_calls = 0
        self._ai_doc_calls_max = max(0, int(max_ai_documents))
        self.last_decisions = {}

        # Scan files (os.walk is noticeably faster on Windows).
        files: list[Path] = []
        if include_subfolders:
            for root, dirs, fnames in os.walk(folder_path):
                if cancel_check and cancel_check():
                    break

                # Always skip obvious internal/cache dirs.
                exclude_names = {
                    "__pycache__",
                    ".git",
                    ".hg",
                    ".svn",
                    ".idea",
                    ".vscode",
                    ".fylorra",
                    "node_modules",
                    "venv",
                    ".venv",
                    "env",
                    ".tox",
                    ".mypy_cache",
                    ".pytest_cache",
                    ".ruff_cache",
                    "dist",
                    "build",
                    "out",
                    "target",
                    "bin",
                    "obj",
                    "Converted_Media",
                    "Converted_Images",
                    "Converted_Office",
                    "Converted_PDF",
                }
                dirs[:] = [d for d in dirs if d not in exclude_names]

                # Smart scope: if a subfolder looks like a project root (code/audio/video), don't descend into it.
                # This keeps categorization from shredding projects (samples, deps, build outputs).
                if smart_scope and Path(root) != folder_path:
                    try:
                        root_path = Path(root)
                        if looks_like_project_root(root_path, list(fnames)):
                            skipped_projects.append(root_path)
                            dirs[:] = []
                            continue
                    except Exception:
                        pass

                for name in fnames:
                    if cancel_check and cancel_check():
                        break
                    p = Path(root) / name
                    if p.is_file():
                        files.append(p)
        else:
            try:
                for entry in os.scandir(folder_path):
                    if cancel_check and cancel_check():
                        break
                    if entry.is_file():
                        files.append(Path(entry.path))
            except Exception:
                files = []

        total = len(files)

        if progress_callback:
            progress_callback(f"Found {total} files", 0.0, 0, total)

        # Categorize
        categorized: Dict[str, List[Path]] = {}

        for idx, file_path in enumerate(files):
            if cancel_check and cancel_check():
                break
            category = self.categorize_file(file_path)

            if category:
                if category == "other" and not include_other:
                    # Unknown stays in place; still record a decision for reporting.
                    if str(file_path) not in self.last_decisions:
                        self._record_decision(file_path, self.CategoryDecision("other", 0.2, "unknown", "Unknown format/insufficient signals"))
                    continue
                if category not in categorized:
                    categorized[category] = []
                categorized[category].append(file_path)
            else:
                self._record_decision(file_path, self.CategoryDecision("other", 0.0, "error", "Could not categorize"))

            # Progress update every 10 files
            if progress_callback and (idx % 10 == 0 or idx == total - 1):
                progress_callback(
                    f"Categorizing files...",
                    (idx + 1) / total,
                    idx + 1,
                    total
                )

        # Optional: detect empty folders (useful for cleanup).
        if include_empty_folders and (not cancel_check or not cancel_check()):
            empties = self._find_empty_folders(folder_path, include_subfolders=include_subfolders, cancel_check=cancel_check)
            if empties:
                categorized.setdefault("empty_folders", []).extend(empties)
                for d in empties:
                    try:
                        self.last_decisions[str(d)] = self.CategoryDecision("empty_folders", 1.0, "scan", "Leaf empty folder")
                    except Exception:
                        pass

        if skipped_projects:
            # De-dupe and keep stable ordering
            uniq: dict[str, Path] = {}
            for p in skipped_projects:
                try:
                    uniq[str(p)] = p
                except Exception:
                    pass
            skipped = list(uniq.values())
            skipped.sort(key=lambda p: str(p).lower())
            categorized.setdefault("ignored_projects", []).extend(skipped)
            for d in skipped:
                try:
                    self.last_decisions[str(d)] = self.CategoryDecision("ignored_projects", 1.0, "scope", "Skipped project root")
                except Exception:
                    pass

        return categorized

    @staticmethod
    def _find_empty_folders(folder_path: Path, *, include_subfolders: bool, cancel_check=None) -> list[Path]:
        folder_path = Path(folder_path)
        if not include_subfolders:
            try:
                entries = list(os.scandir(folder_path))
                if not any(True for e in entries if e.is_file() or e.is_dir()):
                    return [folder_path]
                return []
            except Exception:
                return []

        exclude_dir_names = {"__pycache__", ".git", ".fylorra", "Converted_Media", "Converted_Images", "Converted_Office"}
        out: list[Path] = []

        # Leaf-only empty folders (no files and no subfolders). This avoids noisy "parent contains empty child" results.
        for root, dirs, files in os.walk(folder_path, topdown=True):
            if cancel_check and cancel_check():
                break

            try:
                dirs[:] = [d for d in dirs if d not in exclude_dir_names]
                dirs[:] = [d for d in dirs if not d.startswith(".")]
            except Exception:
                pass

            if files:
                continue
            if dirs:
                continue

            try:
                out.append(Path(root))
            except Exception:
                pass

        # Keep only those under the original folder (defensive) and sort for stable output.
        out = [p for p in out if str(p).startswith(str(folder_path))]
        out.sort(key=lambda p: str(p).lower())
        return out
