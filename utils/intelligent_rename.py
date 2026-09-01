"""
Fylorra - Intelligent Rename Utilities
AI-powered filename sanitization, duplicate detection, and pattern learning
"""

import re
import logging
import hashlib
import filecmp
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from slugify import slugify
from nameparser import HumanName

try:
    import Levenshtein
except Exception:
    Levenshtein = None

logger = logging.getLogger(__name__)


def _name_similarity(left: str, right: str) -> float:
    """Return a stable filename similarity score even without optional native deps."""
    if Levenshtein is not None:
        try:
            return float(Levenshtein.ratio(left, right))
        except Exception:
            logger.debug("Levenshtein similarity failed; using SequenceMatcher", exc_info=True)
    return SequenceMatcher(None, str(left or ""), str(right or "")).ratio()


@dataclass
class RenameValidation:
    """Result of filename validation"""
    is_valid: bool
    sanitized_name: str
    original_name: str
    issues_found: List[str]
    confidence: float


@dataclass
class DuplicateAnalysis:
    """Analysis of potential duplicate files"""
    is_duplicate: bool
    similarity_score: float
    recommended_suffix: str
    explanation: str


class FilenameSanitizer:
    """
    Professional filename sanitization with AI validation
    Ensures cross-platform compatibility and office standards
    """

    # Invalid characters for Windows/macOS/Linux
    INVALID_CHARS = r'[<>:"/\\|?*\x00-\x1f]'

    # Reserved Windows names
    RESERVED_NAMES = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }

    # Professional naming patterns
    MAX_LENGTH = 200  # Safe for all filesystems

    @classmethod
    def sanitize(cls, filename: str, preserve_case: bool = True) -> RenameValidation:
        """
        Sanitize filename to professional office standards

        Args:
            filename: Original filename (without extension)
            preserve_case: Keep original casing if True

        Returns:
            RenameValidation with sanitized name and issues found
        """
        original = filename
        issues = []

        # Remove leading/trailing whitespace and dots
        filename = filename.strip().strip('.')
        if filename != original:
            issues.append("Removed leading/trailing whitespace/dots")

        # Replace invalid characters with underscores
        sanitized = re.sub(cls.INVALID_CHARS, '_', filename)
        if sanitized != filename:
            issues.append("Replaced invalid characters with underscores")
            filename = sanitized

        # Replace multiple spaces/underscores with single underscore
        sanitized = re.sub(r'[\s_]+', '_', filename)
        if sanitized != filename:
            issues.append("Normalized whitespace to underscores")
            filename = sanitized

        # Handle reserved Windows names
        name_upper = filename.upper()
        if name_upper in cls.RESERVED_NAMES:
            filename = f"File_{filename}"
            issues.append(f"Avoided reserved Windows name: {name_upper}")

        # Truncate to safe length
        if len(filename) > cls.MAX_LENGTH:
            filename = filename[:cls.MAX_LENGTH].rstrip('_')
            issues.append(f"Truncated to {cls.MAX_LENGTH} characters")

        # Use python-slugify for professional formatting (optional)
        if not preserve_case:
            slugified = slugify(filename, separator='_', lowercase=False)
            if slugified != filename:
                filename = slugified
                issues.append("Applied professional slug formatting")

        # Calculate confidence based on changes made
        confidence = 1.0 - (len(issues) * 0.15)
        confidence = max(0.5, min(1.0, confidence))

        is_valid = len(issues) == 0

        return RenameValidation(
            is_valid=is_valid,
            sanitized_name=filename,
            original_name=original,
            issues_found=issues,
            confidence=confidence
        )

    @classmethod
    def validate_full_path(cls, path: Path, new_name: str) -> Tuple[bool, str]:
        """
        Validate that new filename won't cause filesystem errors

        Returns:
            (is_valid, error_message)
        """
        # Check total path length (Windows MAX_PATH = 260)
        full_path = path.parent / f"{new_name}{path.suffix}"
        if len(str(full_path)) > 250:  # Safe margin
            return False, "Full path would exceed Windows MAX_PATH limit"

        # Check for path traversal attempts
        if '..' in new_name or '/' in new_name or '\\' in new_name:
            return False, "Filename contains path traversal characters"

        return True, ""


class SmartDuplicateDetector:
    """
    Intelligent duplicate detection using content analysis and AI context
    Goes beyond simple name matching
    """

    @classmethod
    def analyze_duplicate(cls, existing_path: Path, new_name: str,
                         ai_context: Optional[Dict] = None) -> DuplicateAnalysis:
        """
        Analyze if files are true duplicates or just similar names

        Args:
            existing_path: Path to existing file with same/similar name
            new_name: Proposed new name (without extension)
            ai_context: Optional AI analysis context for both files

        Returns:
            DuplicateAnalysis with recommendation
        """
        # Check if it's the same file (rename in place)
        proposed_path = existing_path.parent / f"{new_name}{existing_path.suffix}"
        if proposed_path.samefile(existing_path) if proposed_path.exists() else False:
            return DuplicateAnalysis(
                is_duplicate=False,
                similarity_score=1.0,
                recommended_suffix="",
                explanation="Same file - rename in place"
            )

        # Calculate name similarity
        similarity = _name_similarity(existing_path.stem, new_name)

        # If AI context available, check content similarity
        is_content_duplicate = False
        explanation = ""

        if ai_context and 'existing_analysis' in ai_context:
            # Compare AI analysis results
            existing_type = ai_context['existing_analysis'].get('document_type', '')
            new_type = ai_context.get('new_analysis', {}).get('document_type', '')

            if existing_type == new_type and similarity > 0.8:
                # Suggest context-aware suffix
                existing_date = ai_context['existing_analysis'].get('key_date', '')
                new_date = ai_context.get('new_analysis', {}).get('key_date', '')

                if existing_date and new_date and existing_date != new_date:
                    # Date-based differentiation
                    recommended_suffix = f"_{new_date.replace('-', '_')}"
                    explanation = f"Different dates: {existing_date} vs {new_date}"
                else:
                    # Version-based differentiation
                    recommended_suffix = "_v2"
                    explanation = "Similar content, suggesting version suffix"
            else:
                # Generic number suffix
                recommended_suffix = "_1"
                explanation = f"Name similarity: {similarity:.0%}"
        else:
            # No AI context - use simple numbering
            recommended_suffix = "_1"
            explanation = f"Name similarity: {similarity:.0%}, using numeric suffix"

        return DuplicateAnalysis(
            is_duplicate=is_content_duplicate,
            similarity_score=similarity,
            recommended_suffix=recommended_suffix,
            explanation=explanation
        )

    @classmethod
    def find_unique_name(cls, base_path: Path, desired_name: str,
                        ai_context: Optional[Dict] = None) -> Tuple[str, str]:
        """
        Find unique filename by analyzing existing files intelligently

        Returns:
            (unique_name, explanation)
        """
        extension = base_path.suffix
        parent = base_path.parent

        # Check if desired name is already unique
        test_path = parent / f"{desired_name}{extension}"
        if not test_path.exists() or test_path.samefile(base_path) if test_path.exists() else False:
            return desired_name, "Name is unique"

        # Analyze the duplicate
        analysis = cls.analyze_duplicate(test_path, desired_name, ai_context)

        # Try smart suffix first
        if analysis.recommended_suffix and analysis.recommended_suffix != "_1":
            smart_name = f"{desired_name}{analysis.recommended_suffix}"
            smart_path = parent / f"{smart_name}{extension}"
            if not smart_path.exists():
                return smart_name, f"Added smart suffix: {analysis.explanation}"

        # Fall back to numeric suffixes
        counter = 1
        while True:
            candidate_name = f"{desired_name}_{counter}"
            candidate_path = parent / f"{candidate_name}{extension}"
            if not candidate_path.exists():
                return candidate_name, f"Added numeric suffix (#{counter})"
            counter += 1

            # Safety limit
            if counter > 9999:
                raise ValueError(f"Could not find unique name after 9999 attempts")


class FilenamePatternLearner:
    """
    Learn user's existing filename patterns and apply them to new files
    """

    # Common patterns to detect
    PATTERNS = {
        'date_prefix': r'^(\d{4}[-_]\d{2}[-_]\d{2})[-_]',  # 2024-12-18_
        'date_suffix': r'[-_](\d{4}[-_]\d{2}[-_]\d{2})$',  # _2024-12-18
        'company_prefix': r'^([A-Z][a-zA-Z]+)[-_]',        # Apple_
        'type_suffix': r'[-_](Invoice|Receipt|Contract|Report)$',  # _Invoice
        'version': r'[-_][vV](\d+)$',                      # _v1
    }

    @classmethod
    def analyze_folder_patterns(cls, folder_path: Path, limit: int = 50) -> Dict[str, any]:
        """
        Analyze existing files in folder to detect naming patterns

        Returns:
            Pattern statistics and recommended template
        """
        if not folder_path.is_dir():
            return {'template': None, 'confidence': 0.0}

        files = list(folder_path.glob('*.*'))[:limit]
        if len(files) < 3:  # Need at least 3 files to detect pattern
            return {'template': None, 'confidence': 0.0}

        pattern_counts = {key: 0 for key in cls.PATTERNS.keys()}
        separator_counts = {'_': 0, '-': 0, ' ': 0}

        for file_path in files:
            stem = file_path.stem

            # Detect patterns
            for pattern_name, pattern_regex in cls.PATTERNS.items():
                if re.search(pattern_regex, stem):
                    pattern_counts[pattern_name] += 1

            # Detect separators
            for sep in separator_counts.keys():
                separator_counts[sep] += stem.count(sep)

        # Find dominant patterns
        total_files = len(files)
        dominant_patterns = {
            name: count / total_files
            for name, count in pattern_counts.items()
            if count / total_files > 0.5  # More than 50% of files
        }

        # Find dominant separator
        dominant_separator = max(separator_counts, key=separator_counts.get)

        # Build template
        template_parts = []
        if 'date_prefix' in dominant_patterns:
            template_parts.append('{date}')
        if 'company_prefix' in dominant_patterns:
            template_parts.append('{company}')

        template_parts.append('{description}')

        if 'type_suffix' in dominant_patterns:
            template_parts.append('{type}')
        if 'date_suffix' in dominant_patterns:
            template_parts.append('{date}')

        template = dominant_separator.join(template_parts) if template_parts else None
        confidence = len(dominant_patterns) / len(cls.PATTERNS)

        return {
            'template': template,
            'separator': dominant_separator,
            'patterns': dominant_patterns,
            'confidence': confidence,
            'sample_size': total_files
        }

    @classmethod
    def apply_pattern(cls, template: str, ai_analysis: Dict, separator: str = '_') -> str:
        """
        Apply learned pattern to new filename using AI analysis

        Args:
            template: Template string like '{date}_{company}_{description}'
            ai_analysis: AI semantic analysis result
            separator: Separator character

        Returns:
            Formatted filename
        """
        # Extract data from AI analysis
        placeholders = {
            'date': ai_analysis.get('key_date', '').replace('-', separator),
            'company': ai_analysis.get('entities', [''])[0] if ai_analysis.get('entities') else '',
            'description': ai_analysis.get('suggested_filename', 'Document'),
            'type': ai_analysis.get('document_type', '').title(),
        }

        # Replace placeholders
        result = template
        for key, value in placeholders.items():
            if value:
                result = result.replace(f'{{{key}}}', value)
            else:
                # Remove empty placeholders and extra separators
                result = result.replace(f'{{{key}}}', '')

        # Clean up multiple separators
        result = re.sub(f'{re.escape(separator)}+', separator, result)
        result = result.strip(separator)

        return result if result else placeholders['description']


# Convenience functions for easy integration
def sanitize_ai_filename(ai_suggested_name: str, preserve_case: bool = True) -> RenameValidation:
    """Quick sanitization of AI-suggested filename"""
    return FilenameSanitizer.sanitize(ai_suggested_name, preserve_case)


def get_unique_filename(file_path: Path, desired_name: str,
                       ai_context: Optional[Dict] = None) -> Tuple[str, str]:
    """Get unique filename with smart duplicate handling"""
    return SmartDuplicateDetector.find_unique_name(file_path, desired_name, ai_context)


def learn_folder_patterns(folder_path: Path) -> Dict:
    """Learn naming patterns from existing files"""
    return FilenamePatternLearner.analyze_folder_patterns(folder_path)


def apply_learned_pattern(template: str, ai_analysis: Dict, separator: str = '_') -> str:
    """Apply learned pattern to AI analysis"""
    return FilenamePatternLearner.apply_pattern(template, ai_analysis, separator)
