# Enhanced File Categorization System

## Current System Analysis

**Strengths:**
- Fast rule-based categorization by extension
- Handles images, documents, audio, video, code, archives
- Filename pattern detection (screenshot, photo, meme)

**Limitations:**
- Only 17 file categories
- Limited file type coverage (missing many office formats)
- No AI vision for image content analysis
- No hybrid mode (rule + AI)
- Basic filename pattern matching

---

## 🎯 Enhanced System: Hybrid Categorization

### Architecture: 3-Tier Categorization

```
┌──────────────────────────────────────────────────────────────┐
│  Tier 1: FAST Rule-Based (Extension + Filename Patterns)    │
│  - 50+ file type categories                                  │
│  - Comprehensive office formats                              │
│  - Development files (all languages)                         │
│  - Media files (all formats)                                 │
│  └─→ 99% of files categorized instantly                      │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Tier 2: AI Vision Analysis (Images Only - Optional)        │
│  - Content-based categorization                             │
│  - Screenshot detection (code vs UI vs terminal)            │
│  - Photo vs diagram vs art detection                        │
│  - Meme detection                                            │
│  └─→ Intelligent image categorization                       │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│  Tier 3: Semantic Analysis (Text Files - Optional)          │
│  - Document topic extraction                                │
│  - Code language detection (beyond extension)               │
│  - Receipt/invoice detection                                │
│  └─→ Content-aware categorization                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 📋 Expanded File Categories (50+)

### Office & Documents (12 categories)
```python
OFFICE_CATEGORIES = {
    # Microsoft Office
    "word_documents": {
        "extensions": [".doc", ".docx", ".dot", ".dotx", ".docm", ".dotm", ".odt"],
        "folder": "Documents/Word"
    },
    "excel_spreadsheets": {
        "extensions": [".xls", ".xlsx", ".xlsm", ".xlsb", ".xlt", ".xltx", ".csv", ".ods"],
        "folder": "Documents/Excel"
    },
    "powerpoint_presentations": {
        "extensions": [".ppt", ".pptx", ".pptm", ".pot", ".potx", ".ppsx", ".odp"],
        "folder": "Documents/PowerPoint"
    },
    "pdf_documents": {
        "extensions": [".pdf"],
        "folder": "Documents/PDF"
    },

    # Text & Notes
    "text_files": {
        "extensions": [".txt", ".rtf", ".md", ".markdown"],
        "folder": "Documents/Text"
    },
    "notes": {
        "extensions": [".one", ".onenote", ".note"],
        "folder": "Documents/Notes"
    },

    # Publishing
    "ebooks": {
        "extensions": [".epub", ".mobi", ".azw", ".azw3"],
        "folder": "Books"
    },
    "publisher": {
        "extensions": [".pub", ".indd"],
        "folder": "Documents/Publishing"
    },

    # Forms & Templates
    "forms": {
        "extensions": [".form", ".xsn", ".xsn"],
        "folder": "Documents/Forms"
    },

    # Financial
    "receipts_invoices": {
        "extensions": [".pdf"],  # + AI detection
        "keywords": ["receipt", "invoice", "bill", "statement"],
        "folder": "Documents/Financial/Receipts"
    },
    "financial_documents": {
        "extensions": [".qfx", ".qbo", ".ofx", ".qif"],
        "folder": "Documents/Financial"
    },
}
```

### Development & Code (15 categories)
```python
CODE_CATEGORIES = {
    # Web Development
    "web_frontend": {
        "extensions": [".html", ".htm", ".css", ".scss", ".sass", ".less"],
        "folder": "Code/Web/Frontend"
    },
    "javascript": {
        "extensions": [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"],
        "folder": "Code/JavaScript"
    },

    # Backend Languages
    "python": {
        "extensions": [".py", ".pyw", ".pyx", ".ipynb"],
        "folder": "Code/Python"
    },
    "java": {
        "extensions": [".java", ".class", ".jar"],
        "folder": "Code/Java"
    },
    "c_cpp": {
        "extensions": [".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx"],
        "folder": "Code/C-C++"
    },
    "csharp": {
        "extensions": [".cs", ".csx"],
        "folder": "Code/CSharp"
    },
    "go": {
        "extensions": [".go"],
        "folder": "Code/Go"
    },
    "rust": {
        "extensions": [".rs"],
        "folder": "Code/Rust"
    },
    "ruby": {
        "extensions": [".rb", ".erb"],
        "folder": "Code/Ruby"
    },
    "php": {
        "extensions": [".php", ".php3", ".php4", ".php5", ".phtml"],
        "folder": "Code/PHP"
    },

    # Scripts
    "shell_scripts": {
        "extensions": [".sh", ".bash", ".zsh", ".fish"],
        "folder": "Code/Scripts"
    },
    "powershell": {
        "extensions": [".ps1", ".psm1", ".psd1"],
        "folder": "Code/PowerShell"
    },
    "batch_scripts": {
        "extensions": [".bat", ".cmd"],
        "folder": "Code/Batch"
    },

    # Data & Config
    "sql": {
        "extensions": [".sql", ".mysql", ".pgsql"],
        "folder": "Code/SQL"
    },
    "config_files": {
        "extensions": [".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env"],
        "folder": "Config"
    },
}
```

### Media & Design (10 categories)
```python
MEDIA_CATEGORIES = {
    # Images - Raster
    "photos": {
        "extensions": [".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"],
        "keywords": ["photo", "img", "camera", "dsc", "pic"],
        "folder": "Photos"
    },
    "screenshots": {
        "extensions": [".png", ".jpg", ".jpeg"],
        "keywords": ["screenshot", "screen", "capture", "snap"],
        "folder": "Screenshots"
    },

    # Images - Vector & Design
    "vector_graphics": {
        "extensions": [".svg", ".ai", ".eps"],
        "folder": "Design/Vector"
    },
    "design_files": {
        "extensions": [".psd", ".psb", ".xcf", ".sketch", ".fig"],
        "folder": "Design/Projects"
    },

    # Diagrams & Charts
    "diagrams": {
        "extensions": [".vsd", ".vsdx", ".drawio", ".dia"],
        "folder": "Diagrams"
    },

    # 3D & CAD
    "3d_models": {
        "extensions": [".obj", ".fbx", ".blend", ".3ds", ".max", ".c4d", ".stl"],
        "folder": "3D Models"
    },
    "cad_files": {
        "extensions": [".dwg", ".dxf", ".step", ".iges"],
        "folder": "CAD"
    },

    # GIFs & Animations
    "gifs_memes": {
        "extensions": [".gif"],
        "folder": "Memes"
    },

    # Icons & Assets
    "icons": {
        "extensions": [".ico", ".icns"],
        "folder": "Design/Icons"
    },
}
```

### Audio & Video (8 categories)
```python
AUDIO_VIDEO_CATEGORIES = {
    # Audio - Lossless
    "audio_lossless": {
        "extensions": [".flac", ".alac", ".ape", ".wav", ".aiff"],
        "folder": "Music/Lossless"
    },

    # Audio - Compressed
    "audio_compressed": {
        "extensions": [".mp3", ".aac", ".m4a", ".ogg", ".opus", ".wma"],
        "folder": "Music"
    },

    # Audio - Projects
    "audio_projects": {
        "extensions": [".aup", ".flp", ".als", ".logic"],
        "folder": "Music/Projects"
    },

    # Video - Standard
    "videos": {
        "extensions": [".mp4", ".mkv", ".webm", ".mov", ".avi"],
        "folder": "Videos"
    },

    # Video - High Quality
    "videos_hd": {
        "extensions": [".m2ts", ".mts", ".m4v"],
        "folder": "Videos/HD"
    },

    # Video - Legacy
    "videos_legacy": {
        "extensions": [".wmv", ".flv", ".3gp", ".mpg", ".mpeg"],
        "folder": "Videos/Legacy"
    },

    # Video - Projects
    "video_projects": {
        "extensions": [".prproj", ".aep", ".veg", ".fcpx"],
        "folder": "Videos/Projects"
    },

    # Subtitles
    "subtitles": {
        "extensions": [".srt", ".sub", ".ass", ".vtt"],
        "folder": "Videos/Subtitles"
    },
}
```

### Archives & System (5 categories)
```python
SYSTEM_CATEGORIES = {
    "compressed_archives": {
        "extensions": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".lz"],
        "folder": "Archives"
    },
    "disk_images": {
        "extensions": [".iso", ".img", ".dmg", ".vhd", ".vmdk"],
        "folder": "Disk Images"
    },
    "executables": {
        "extensions": [".exe", ".msi", ".app", ".deb", ".rpm", ".apk"],
        "folder": "Programs"
    },
    "databases": {
        "extensions": [".db", ".sqlite", ".sqlite3", ".mdb", ".accdb"],
        "folder": "Databases"
    },
    "shortcuts": {
        "extensions": [".lnk", ".url", ".webloc"],
        "folder": "Shortcuts"
    },
}
```

---

## 🤖 AI Vision Enhancement (Images Only)

### When to Use AI
- **Never by default** - Too slow (20-60 sec per image)
- **User opts in** - "Use AI for better image categorization"
- **Batch mode** - Process overnight for large folders
- **Selective** - Only for uncategorized or ambiguous images

### AI Categories for Images
```python
AI_IMAGE_CATEGORIES = {
    # Screenshots
    "screenshot_code": {
        "prompt": "code editor, programming, terminal, IDE, syntax highlighting",
        "folder": "Screenshots/Code"
    },
    "screenshot_ui": {
        "prompt": "user interface, application window, settings, dialog box",
        "folder": "Screenshots/Apps"
    },
    "screenshot_web": {
        "prompt": "web browser, website, web page",
        "folder": "Screenshots/Web"
    },
    "screenshot_game": {
        "prompt": "video game, gaming interface, game screenshot",
        "folder": "Screenshots/Games"
    },

    # Content Type
    "photo_people": {
        "prompt": "people, person, portrait, selfie, group photo",
        "folder": "Photos/People"
    },
    "photo_nature": {
        "prompt": "nature, landscape, scenery, outdoor, mountains, ocean",
        "folder": "Photos/Nature"
    },
    "photo_food": {
        "prompt": "food, meal, dish, cooking, restaurant",
        "folder": "Photos/Food"
    },

    # Professional
    "diagram_flowchart": {
        "prompt": "flowchart, diagram, chart, graph, visualization",
        "folder": "Diagrams/Flowcharts"
    },
    "diagram_architecture": {
        "prompt": "architecture diagram, system design, network diagram",
        "folder": "Diagrams/Architecture"
    },

    # Creative
    "art_digital": {
        "prompt": "digital art, illustration, artwork, drawing",
        "folder": "Art/Digital"
    },
    "meme": {
        "prompt": "meme, funny image, internet meme, humor",
        "folder": "Memes"
    },
}
```

### AI Vision Workflow
```python
def categorize_with_ai_vision(file_path: Path) -> str:
    """
    Use AI vision to categorize image content
    Only called if user enables AI mode
    """
    # Prepare image
    image_data = prepare_image(file_path)

    # Simple yes/no prompts (faster than complex classification)
    prompts = [
        "Is this a screenshot of code or a code editor?",
        "Is this a screenshot of a user interface or application?",
        "Does this show people or portraits?",
        "Is this a diagram, chart, or flowchart?",
        "Is this a meme or humorous image?",
    ]

    # Quick classification
    for prompt in prompts:
        response = model.create_chat_completion(
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": image_data}
            ]}],
            max_tokens=10  # Just need yes/no
        )

        if "yes" in response.lower():
            return category_for_prompt(prompt)

    # Fallback to rule-based
    return "photos"
```

---

## 📊 Hybrid Mode Implementation

### User Options
```
┌─────────────────────────────────────────────────┐
│  Categorization Settings                        │
├─────────────────────────────────────────────────┤
│                                                 │
│  Mode:                                          │
│  ◉ Fast (Rule-based only)                      │
│  ○ Smart (Rule + AI for images)                │
│  ○ Deep (AI for all files)                     │
│                                                 │
│  AI Vision for Images:                          │
│  ☐ Use AI to detect screenshot types           │
│  ☐ Use AI to categorize photo content          │
│  ☐ Use AI to detect diagrams and charts        │
│                                                 │
│  Options:                                       │
│  ☑ Include subfolders                          │
│  ☐ Create detailed subcategories               │
│  ☑ Preserve original folder structure          │
│                                                 │
│  [Start Categorization]  [Cancel]              │
└─────────────────────────────────────────────────┘
```

---

## 🚀 Implementation Plan

### Phase 1: Expand Rule-Based Categories
- [ ] Add 50+ file type categories
- [ ] Comprehensive office format support
- [ ] All programming languages
- [ ] All media formats
- [ ] Update category folder structure

### Phase 2: Hybrid Mode
- [ ] Add AI vision toggle
- [ ] Implement selective AI processing
- [ ] Batch AI processing for images
- [ ] Progress tracking for mixed mode

### Phase 3: Subfolder Recursion
- [ ] Add "Include subfolders" option
- [ ] Preserve or flatten folder structure
- [ ] Handle nested categorization

### Phase 4: Smart Features
- [ ] Auto-detect receipts/invoices (AI + keywords)
- [ ] Code language detection beyond extension
- [ ] Duplicate detection (vision similarity)
- [ ] Quality assessment (blurry, overexposed)

---

## 💡 Benefits for Office Use

### For Office Workers
1. **All Office Formats** - Word, Excel, PowerPoint, PDF organized
2. **Financial Documents** - Receipts, invoices auto-detected
3. **Email Attachments** - Organize downloads by type
4. **Project Files** - CAD, design files categorized

### For Developers
1. **Language-Specific Folders** - Python, JavaScript, Java separated
2. **Config Files** - JSON, YAML organized
3. **Screenshots** - Code vs UI auto-detected (AI mode)

### For Media Professionals
1. **Format-Based** - Lossless vs compressed audio
2. **Project Files** - Premiere, After Effects separated
3. **Assets** - Icons, vectors organized

---

## Summary

Transform Fylorra's categorization from **17 basic categories** to **50+ comprehensive categories** with optional AI vision enhancement for intelligent image categorization.

**Key Innovation:** Hybrid approach - 99% of files categorized instantly by rules, with optional AI vision for intelligent image categorization.
