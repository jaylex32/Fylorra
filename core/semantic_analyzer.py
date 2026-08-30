"""
Fylorra - Semantic File Analyzer
Intelligent document understanding using LLM for office workflows
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Structured semantic analysis result with confidence and explainability"""

    # Core classification
    document_type: str  # invoice, receipt, contract, resume, report, memo, etc.
    domain: str  # finance, work, personal, legal, education, entertainment

    # Extracted intelligence
    entities: List[str]  # Companies, people, locations
    key_date: Optional[str]  # YYYY-MM-DD format

    # AI reasoning
    confidence: float  # 0.0 to 1.0
    explanation: str  # Human-readable reasoning

    # Actionable suggestions
    suggested_filename: Optional[str]
    suggested_category: Optional[str]
    sensitivity: str  # low, medium, high

    # Metadata
    analyzed_at: str
    model_used: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    def should_auto_suggest(self) -> bool:
        """High confidence - show suggestion automatically"""
        return self.confidence >= 0.85

    def should_ask_user(self) -> bool:
        """Medium confidence - ask user for confirmation"""
        return 0.60 <= self.confidence < 0.85

    def should_fallback_to_rules(self) -> bool:
        """Low confidence - use rule-based logic"""
        return self.confidence < 0.60


class SemanticAnalyzer:
    """
    Semantic intelligence layer for document analysis

    Uses LLM to understand file content and provide structured intelligence
    for office workflows. Focus on documents, not batch vision processing.
    """

    # Semantic analysis prompt - enforces structured JSON output
    SEMANTIC_ANALYSIS_PROMPT = """You are a professional document analyst for office file management. Analyze the provided content and return ONLY valid JSON.

Output Schema:
{
  "document_type": "invoice|receipt|contract|resume|report|memo|email|letter|form|spreadsheet|presentation|notes|code|manual|other",
  "domain": "finance|work|personal|legal|education|entertainment|healthcare|travel|shopping|government",
  "entities": ["list", "of", "key", "entities"],
  "key_date": "YYYY-MM-DD or null",
  "confidence": 0.0-1.0,
  "explanation": "clear reasoning for classification",
  "suggested_filename": "Descriptive_Professional_Name",
  "suggested_category": "target folder category",
  "sensitivity": "low|medium|high"
}

Classification Guidelines:
- invoice: Has invoice number, vendor, total, payment terms
- receipt: Purchase confirmation, simpler than invoice
- contract: Legal agreement, terms and conditions
- resume: CV, work history, skills
- report: Business report, analysis, findings
- memo: Internal communication, brief updates
- email: Email correspondence saved as document
- letter: Formal letter or correspondence
- form: Application form, questionnaire
- spreadsheet: Data tables, calculations
- presentation: Slides, pitch deck
- notes: Meeting notes, personal notes
- code: Source code, scripts
- manual: Instructions, documentation

Domain Guidelines:
- finance: Invoices, receipts, tax documents, bank statements
- work: Business documents, reports, memos, contracts
- personal: Personal correspondence, personal records
- legal: Contracts, agreements, legal notices
- education: Coursework, assignments, certificates
- healthcare: Medical records, insurance, prescriptions
- travel: Tickets, itineraries, bookings
- shopping: Receipts, order confirmations
- government: Tax forms, official documents

Confidence Scoring:
- 0.90-1.0: Extremely clear (invoice with all fields, obvious document type)
- 0.70-0.89: Very likely (most indicators present)
- 0.50-0.69: Probable (some ambiguity, missing info)
- 0.30-0.49: Uncertain (limited information)
- 0.0-0.29: Cannot determine (too little content)

Sensitivity Guidelines:
- high: Financial data, SSN, passwords, medical records, legal contracts
- medium: Work documents, personal correspondence, contact info
- low: Public information, general documents, marketing materials

Rules:
- Be conservative with confidence - if unsure, lower the score
- Extract only entities ACTUALLY in the text (companies, people, locations)
- Suggested filename must be professional: Use_Underscores, no spaces
- Always provide clear explanation of your reasoning
- If content is unclear or too short, set confidence < 0.5
- Key date should be the most important date in the document (invoice date, contract date, etc.)
- Do not make up information - only use what you see

Return ONLY the JSON object, no other text."""

    # Document type priorities for office workflows
    OFFICE_DOCUMENT_TYPES = {
        'invoice': {'priority': 10, 'category': 'Finance'},
        'receipt': {'priority': 9, 'category': 'Finance'},
        'contract': {'priority': 10, 'category': 'Legal'},
        'resume': {'priority': 8, 'category': 'HR'},
        'report': {'priority': 9, 'category': 'Reports'},
        'memo': {'priority': 7, 'category': 'Communications'},
        'email': {'priority': 6, 'category': 'Communications'},
        'letter': {'priority': 7, 'category': 'Communications'},
        'form': {'priority': 8, 'category': 'Forms'},
        'spreadsheet': {'priority': 9, 'category': 'Data'},
        'presentation': {'priority': 8, 'category': 'Presentations'},
        'notes': {'priority': 5, 'category': 'Notes'},
        'manual': {'priority': 6, 'category': 'Documentation'}
    }

    def __init__(self, ai_manager):
        self.ai_manager = ai_manager
        self.analysis_cache: Dict[str, AnalysisResult] = {}
        logger.info("SemanticAnalyzer initialized")

    def analyze_document(self, file_path: Path, use_cache: bool = True) -> Optional[AnalysisResult]:
        """
        Perform semantic analysis on a document

        Args:
            file_path: Path to document (PDF, DOCX, TXT, etc.)
            use_cache: Use cached result if available

        Returns:
            AnalysisResult with structured intelligence, or None if analysis failed
        """
        # Check cache
        cache_key = str(file_path)
        if use_cache and cache_key in self.analysis_cache:
            logger.info(f"Using cached analysis for {file_path.name}")
            return self.analysis_cache[cache_key]

        # Check if AI is ready
        if not self.ai_manager.is_ready:
            logger.warning("AI manager not ready for semantic analysis")
            return None

        # Validate file
        if not file_path.exists() or not file_path.is_file():
            logger.error(f"File not found: {file_path}")
            return None

        try:
            # Extract text content from document
            text_content = self._extract_text(file_path)

            if not text_content or len(text_content.strip()) < 50:
                logger.warning(f"Insufficient text content in {file_path.name}")
                return self._create_fallback_result(file_path, "Insufficient text content")

            # Perform LLM analysis
            logger.info(f"Analyzing document: {file_path.name}")
            result = self._analyze_with_llm(file_path, text_content)

            # Cache successful result
            if result:
                self.analysis_cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Error analyzing document {file_path.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _extract_text(self, file_path: Path) -> Optional[str]:
        """
        Extract text content from various document formats

        Supports: PDF, DOCX, TXT, CSV
        """
        ext = file_path.suffix.lower()

        try:
            # Plain text files
            if ext in {'.txt', '.md', '.log', '.csv', '.json', '.xml'}:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read(10000)  # First 10KB

            # PDF files
            elif ext == '.pdf':
                return self._extract_pdf_text(file_path)

            # Word documents
            elif ext in {'.docx', '.doc'}:
                return self._extract_docx_text(file_path)

            else:
                logger.warning(f"Unsupported file type for text extraction: {ext}")
                return None

        except Exception as e:
            logger.error(f"Error extracting text from {file_path.name}: {e}")
            return None

    def _extract_pdf_text(self, file_path: Path) -> Optional[str]:
        """Extract text from PDF (first 2 pages only for speed)"""
        # Prefer PyMuPDF when available (best extraction), then fall back to pypdf.
        try:
            import fitz  # type: ignore

            with fitz.open(str(file_path)) as pdf:
                parts: list[str] = []
                for i in range(min(2, int(pdf.page_count))):
                    try:
                        parts.append(pdf.load_page(i).get_text("text") or "")
                    except Exception:
                        continue
                text = "\n".join([p for p in parts if p]).strip()
                return (text[:10000] if text else None)
        except Exception:
            pass

        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(file_path))
            parts = []
            for page_num in range(min(2, len(reader.pages))):
                try:
                    parts.append(reader.pages[page_num].extract_text() or "")
                except Exception:
                    continue
            text = "\n".join([p for p in parts if p]).strip()
            return (text[:10000] if text else None)
        except Exception as e:
            logger.warning(f"PDF text extraction unavailable/failed: {e}")
            return None

    def _extract_docx_text(self, file_path: Path) -> Optional[str]:
        """Extract text from DOCX"""
        try:
            import docx

            doc = docx.Document(file_path)

            # Extract paragraphs
            text_parts = [para.text for para in doc.paragraphs]
            text = '\n'.join(text_parts)

            return text[:10000]  # Limit to 10KB

        except ImportError:
            logger.warning("python-docx not installed - cannot extract DOCX text")
            return None
        except Exception as e:
            logger.error(f"Error extracting DOCX text: {e}")
            return None

    def _analyze_with_llm(self, file_path: Path, text_content: str) -> Optional[AnalysisResult]:
        """
        Use LLM to perform semantic analysis

        Returns structured AnalysisResult with confidence and reasoning
        """
        try:
            # Prepare context (limit to 2000 chars for fast inference)
            context = text_content[:2000]

            # Call LLM with structured prompt and force JSON output
            response = self.ai_manager.model.create_chat_completion(
                messages=[
                    {"role": "system", "content": self.SEMANTIC_ANALYSIS_PROMPT},
                    {"role": "user", "content": f"Analyze this document:\n\n{context}"}
                ],
                temperature=0.1,  # Low for consistency
                max_tokens=300,  # Enough for JSON response
                response_format={"type": "json_object"},  # Force valid JSON output
            )

            # Extract response
            result_text = response['choices'][0]['message']['content'].strip()

            # Try to parse JSON
            try:
                # Remove markdown code blocks if present
                if result_text.startswith('```'):
                    result_text = result_text.split('```')[1]
                    if result_text.startswith('json'):
                        result_text = result_text[4:]
                result_text = result_text.strip()

                result_data = json.loads(result_text)

                # Validate required fields
                required_fields = ['document_type', 'domain', 'confidence', 'explanation']
                for field in required_fields:
                    if field not in result_data:
                        logger.error(f"Missing required field: {field}")
                        return None

                # Create AnalysisResult
                return AnalysisResult(
                    document_type=result_data.get('document_type', 'other'),
                    domain=result_data.get('domain', 'other'),
                    entities=result_data.get('entities', []),
                    key_date=result_data.get('key_date'),
                    confidence=float(result_data.get('confidence', 0.0)),
                    explanation=result_data.get('explanation', 'No explanation provided'),
                    suggested_filename=result_data.get('suggested_filename'),
                    suggested_category=result_data.get('suggested_category'),
                    sensitivity=result_data.get('sensitivity', 'medium'),
                    analyzed_at=datetime.now().isoformat(),
                    model_used=self.ai_manager.MODEL_FILE
                )

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM JSON response: {e}")
                logger.error(f"Response was: {result_text}")
                return None

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    def _create_fallback_result(self, file_path: Path, reason: str) -> AnalysisResult:
        """Create a low-confidence fallback result"""
        return AnalysisResult(
            document_type='other',
            domain='other',
            entities=[],
            key_date=None,
            confidence=0.0,
            explanation=f"Unable to analyze: {reason}",
            suggested_filename=None,
            suggested_category=None,
            sensitivity='low',
            analyzed_at=datetime.now().isoformat(),
            model_used='fallback'
        )

    def get_analysis_summary(self, result: AnalysisResult) -> str:
        """Generate human-readable summary of analysis"""
        lines = [
            f"📄 Document Type: {result.document_type.title()}",
            f"🏢 Domain: {result.domain.title()}",
            f"📊 Confidence: {result.confidence:.0%}",
            f"💡 Reasoning: {result.explanation}",
        ]

        if result.entities:
            lines.append(f"🔍 Found: {', '.join(result.entities[:5])}")

        if result.key_date:
            lines.append(f"📅 Key Date: {result.key_date}")

        if result.suggested_filename:
            lines.append(f"✏️ Suggested Name: {result.suggested_filename}")

        lines.append(f"🔒 Sensitivity: {result.sensitivity.upper()}")

        return '\n'.join(lines)

    def clear_cache(self):
        """Clear analysis cache"""
        self.analysis_cache.clear()
        logger.info("Analysis cache cleared")
