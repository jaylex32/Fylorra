# Fylorra - AI Features Reorganization Plan

## Current AI Features Analysis

### Existing AI Features (6 dialogs)
1. **Smart Rename Dialog** (`smart_rename_dialog.py`) - AI-powered file renaming
2. **AI Categorize Dialog** (`ai_categorize_dialog.py`) - Categorize files into folders
3. **Semantic Analysis Dialog** (`semantic_analysis_dialog.py`) - Analyze file content semantically
4. **AI Security Scan Dialog** (`ai_security_scan_dialog.py`) - Security analysis
5. **NL Rule Dialog** (`nl_rule_dialog.py`) - Natural language rule builder
6. **AI Loading Dialog** (`ai_loading_dialog.py`) - Model loading progress

### Current Limitations
- ✅ Smart Rename now supports bulk operations with folder mode
- ❌ No unified AI analysis interface (in progress)
- ✅ Subfolder recursion option added to Smart Rename and Categorize
- ✅ Tooltips added to all buttons
- ❌ Scattered AI features - hard to discover (planned)
- ✅ Batch progress tracking implemented in BulkAIProcessor
- ✅ Single file vs bulk mode now clearly separated

---

## 🎯 Proposed Architecture: Unified AI Hub

### 1. **AI Hub Dialog** (NEW - Central Interface)
A unified dialog that serves as the main entry point for ALL AI features:

```
┌─────────────────────────────────────────────────────────┐
│              Fylorra AI Assistant                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Select Folder: [C:/Users/Documents]  [Browse]         │
│  □ Include subfolders                                   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  AI Operations (Select one or more):            │   │
│  │                                                  │   │
│  │  Vision & Organization:                         │   │
│  │  ☑ Smart Rename (AI vision-based)              │   │
│  │  ☑ Auto-Categorize (organize into folders)     │   │
│  │  ☐ Duplicate Detection (vision similarity)     │   │
│  │                                                  │   │
│  │  Analysis & Intelligence:                       │   │
│  │  ☐ Content Analysis (semantic understanding)   │   │
│  │  ☐ Security Scan (malware/risk detection)      │   │
│  │  ☐ Quality Check (image/document quality)      │   │
│  │                                                  │   │
│  │  Automation:                                    │   │
│  │  ☐ Generate Rules (from observed patterns)     │   │
│  │  ☐ Suggest Workflows (optimization)            │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  File Filters:                                          │
│  Images: ☑  Documents: ☐  Videos: ☐  All: ☐           │
│                                                         │
│  [Start AI Analysis]  [Cancel]                         │
└─────────────────────────────────────────────────────────┘
```

**Features:**
- Select multiple AI operations to run in sequence
- Bulk processing with subfolder recursion
- File type filtering
- Progress tracking for all operations
- Unified results preview

---

### 2. **Bulk Processing Engine** (NEW - Core System)

**Features:**
- Process entire folder trees (with subfolder option)
- Smart batching (process N files at a time to avoid memory issues)
- Parallel processing where possible (non-vision tasks)
- Sequential processing for vision tasks (GPU memory management)
- Progress tracking with ETA
- Pausable/resumable operations
- Error recovery and retry logic

**Architecture:**
```python
class BulkAIProcessor:
    """Handles bulk AI operations across folder structures"""

    def __init__(self, ai_manager):
        self.ai_manager = ai_manager
        self.queue = []
        self.results = {}
        self.progress_callbacks = []

    def scan_folder(self, folder_path, include_subfolders=True, filters=None):
        """Scan folder and build file queue"""

    def process_batch(self, operation_type, batch_size=10):
        """Process files in batches"""

    def add_operation(self, operation):
        """Add AI operation to pipeline"""

    def execute_pipeline(self):
        """Execute all operations in sequence"""
```

---

### 3. **Enhanced Smart Rename** (IMPROVED)

**Current:** Processes files one-by-one with live UI updates
**New:** Batch processing with preview-then-apply workflow

**Modes:**
1. **Quick Mode (NEW)** - Process all files, show results table, bulk approve
2. **Review Mode (EXISTING)** - One-by-one review with live preview
3. **Bulk Edit Mode (NEW)** - Apply pattern-based edits to multiple files

**Workflow:**
```
Select Files → Choose Mode → Process (batch/sequential) → Preview Results → Approve/Edit → Apply
```

---

### 4. **New AI Features to Add**

#### A. **Smart Duplicate Finder** (NEW)
- Uses vision AI to find visually similar images
- Not just hash-based - understands content similarity
- Groups duplicates by similarity score
- Suggests which to keep/delete

#### B. **Content Quality Analyzer** (NEW)
- Image quality detection (blurry, overexposed, etc.)
- Document completeness check
- Suggest quality improvements or deletion

#### C. **Pattern-Based Rule Generator** (IMPROVED)
- Analyzes existing file organization
- Suggests automation rules based on patterns
- "Learn from my existing organization"

#### D. **Batch Vision Analysis** (NEW)
- Process all images in folder
- Generate tags, descriptions, metadata
- Export to CSV/JSON for further use

---

### 5. **Tooltip System** (NEW - User Request)

Add tooltips to ALL buttons across the application:

**Implementation:**
```python
class ToolTipHelper:
    """Centralized tooltip management"""

    @staticmethod
    def create_tooltip(widget, text, delay=500):
        """Create tooltip on hover"""

    @staticmethod
    def add_tooltips_to_buttons(button_config):
        """Batch add tooltips from config"""
```

**Tooltip Locations:**
- Main window toolbar buttons
- Monitor card action buttons
- Settings dialog buttons
- All AI dialog buttons
- Menu items (if applicable)

**Example Tooltips:**
- "Add Monitor" → "Create a new folder monitor with custom rules"
- "AI Rule Builder" → "Use natural language to create automation rules"
- "Smart Rename" → "Rename files using AI vision analysis"
- "Settings" → "Configure application settings and AI models"

---

### 6. **UI/UX Improvements**

#### A. **Progress Feedback**
- Real-time progress bars with file count
- ETA calculation
- "Processing: filename.jpg (15/150)"
- Pausable long-running operations

#### B. **Results Preview**
- Table view with before/after
- Sortable/filterable results
- Bulk select/deselect
- Export results to CSV

#### C. **Error Handling**
- Clear error messages
- Skip failed files with option to retry
- Error log export

---

## 📋 Implementation Plan

### Phase 1: Foundation ✅ COMPLETED
- [x] Fix AI Rule Builder JSON generation
- [x] Fix TclError in loading dialog
- [x] Create tooltip system (utils/tooltip.py)
- [x] Add tooltips to all existing buttons
- [x] Design BulkAIProcessor class

### Phase 2: Bulk Processing ✅ COMPLETED
- [x] Implement BulkAIProcessor core (core/bulk_ai_processor.py)
- [x] Add subfolder recursion support (Smart Rename + Categorize)
- [x] Add file filtering by extension (images/videos/documents/code)
- [x] Implement batch progress tracking with ETA
- [x] Update Smart Rename dialog with folder mode
- [x] Add bulk options UI (subfolder checkbox, filter dropdown)

### Phase 3: AI Hub ✅ COMPLETED
- [x] Design AI Hub UI mockup
- [x] Implement AI Hub dialog (gui/ai_hub_dialog.py)
- [x] Integrate existing AI features into hub (Smart Rename, Auto-Categorize, Semantic Analysis, Security Scan)
- [x] Add AI Hub button to main toolbar
- [x] Sequential operation launching (pipeline foundation)
- [ ] Unified progress tracking across operations (future enhancement)

### Phase 4: Enhanced Features (Week 4)
- [ ] Smart Duplicate Finder
- [ ] Content Quality Analyzer
- [ ] Enhanced Smart Rename (batch mode)
- [ ] Pattern-based rule generator

### Phase 5: Polish & Testing (Week 5)
- [ ] Comprehensive testing
- [ ] Performance optimization
- [ ] Documentation
- [ ] User guide for AI features

---

## 🎨 Design Principles

1. **Progressive Disclosure** - Simple by default, powerful when needed
2. **Batch First** - Optimize for bulk operations, support single files
3. **Preview Everything** - Never apply changes without user approval
4. **Clear Feedback** - Always show progress and results
5. **Graceful Degradation** - Work offline, handle model loading delays
6. **Memory Efficient** - Batch processing with cleanup between batches

---

## 🔧 Technical Specifications

### File Scanning
- Use `pathlib.Path.rglob()` for subfolder recursion
- Filter by extensions: `*.jpg`, `*.png`, etc.
- Respect `.gitignore` patterns (optional)
- Max files per operation: 10,000 (configurable)

### Batch Sizes
- Vision tasks: 10 files per batch (GPU memory)
- Text tasks: 50 files per batch
- Light tasks: 100 files per batch

### Memory Management
- Clear VRAM between batches
- Use weak references for temp data
- Garbage collect after each batch

### Threading
- UI thread: Main tkinter thread
- Worker thread: AI processing
- Background thread: File scanning

---

## 📊 Expected Benefits

1. **Performance** - 10x faster bulk operations
2. **Usability** - Clearer workflow, better discoverability
3. **Features** - New AI capabilities (duplicates, quality, patterns)
4. **UX** - Tooltips improve learnability
5. **Efficiency** - Batch operations reduce overhead

---

## 🚀 Quick Wins (Start Here)

1. ✅ **Add Tooltips** - Immediate UX improvement (~2 hours)
2. ⚡ **Bulk Rename Mode** - Quick batch processing (~1 day)
3. 📁 **Subfolder Recursion** - Essential feature (~4 hours)
4. 🎯 **AI Hub Dialog** - Central interface (~2 days)

---

## Summary

Transform Fylorra's AI features from scattered single-file tools into a **unified, powerful, batch-processing AI assistant** that can handle entire folder structures with ease.

**Key Innovation:** The AI Hub becomes the primary way users interact with AI features, making them more discoverable and powerful while maintaining simplicity for single-file operations.
