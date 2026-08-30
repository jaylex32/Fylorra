╔══════════════════════════════════════════════════════════════════════════════╗
║                    Fylorra - AI Features Guide                        ║
╚══════════════════════════════════════════════════════════════════════════════╝

🤖 OVERVIEW
-----------
Fylorra includes AI-powered vision features using Qwen3-VL-4B model.
All processing is 100% LOCAL - no data leaves your computer.

Model: Qwen3-VL-4B (Q4_K_M quantization, ~3.3GB)
Speed: 2-5 seconds per image on modern CPUs
Privacy: Completely offline, no internet required after download


📋 THREE AI FEATURES
---------------------

🟣 1. SMART RENAME
   What it does:
   - Analyzes images and PDFs using computer vision
   - Suggests descriptive, meaningful filenames
   - Replaces generic names like "IMG_1234.jpg" with "sunset_beach_vacation.jpg"

   How to use:
   1. Click the PURPLE button on any folder monitor
   2. AI analyzes all images in that folder (max 50 files)
   3. Review suggested names in preview dialog
   4. Check/uncheck files you want to rename
   5. Edit any suggested names before applying
   6. Click "Apply Renames" to execute

   Example:
   Before: Screenshot_20241215_142355.png
   After:  python_code_error_debugging.png


🟠 2. AUTO-CATEGORIZE
   What it does:
   - Analyzes visual content of images
   - Automatically sorts files into category folders
   - Creates organized folder structure

   Categories:
   - Screenshots/Code - Code or terminal screenshots
   - Screenshots/UI - Application UI or web pages
   - Screenshots/Other - Other screenshots
   - Photos - Real-world photographs
   - Diagrams - Flowcharts, diagrams, charts
   - Documents - Scanned documents or text
   - Receipts - Receipts or invoices
   - Memes - Memes or social media content
   - Art - Artwork or illustrations
   - Uncategorized - Everything else

   How to use:
   1. Click the ORANGE button on any folder monitor
   2. AI analyzes and categorizes all images
   3. Review the categorization preview
   4. Check "Move files to category folders" to apply
   5. Click "Apply Organization"

   Example folder structure after:
   YourFolder/
   ├── Screenshots/
   │   ├── Code/
   │   ├── UI/
   │   └── Other/
   ├── Photos/
   ├── Documents/
   └── Receipts/


🔴 3. SECURITY SCAN
   What it does:
   - Scans images for sensitive information
   - Detects potential security risks
   - Helps prevent accidental data leaks

   Detects:
   - Credit card numbers
   - Social Security Numbers
   - Passwords or API keys visible in screenshots
   - Bank account information
   - Personal identification documents
   - Private medical information

   How to use:
   1. Click the RED button on any folder monitor
   2. AI scans all images for sensitive content
   3. Review list of flagged files
   4. Take action (delete, encrypt, move to secure location)

   Example warning:
   ⚠ screenshot_payment.png
   Reason: Potential credit card information detected


⚡ PERFORMANCE & LIMITS
-----------------------
- Max file size: 10MB per file
- Max batch size: 50 files per operation
- Timeout: 30 seconds per file
- Supported formats: JPG, PNG, GIF, BMP, TIFF, WEBP, PDF
- Processing speed: ~2-5 seconds per image (CPU)
- Memory usage: ~4GB RAM when model loaded


🔒 PRIVACY & SECURITY
---------------------
✓ 100% local processing - no internet connection needed after download
✓ No data sent to external servers
✓ Model runs entirely on your computer
✓ Files never leave your machine
✓ Open source model (Apache 2.0 license)


💡 TIPS & BEST PRACTICES
-------------------------
1. First use will download ~3.3GB model (one-time only)
2. Model stays loaded in memory after first use for faster processing
3. Works best with clear, high-quality images
4. For large folders (>50 files), process in batches
5. Always review AI suggestions before applying
6. Use Security Scan before uploading files to cloud services
7. Smart Rename works great for organizing screenshot folders


🛠️ TROUBLESHOOTING
-------------------
Q: AI buttons not responding?
A: Model may not be loaded. Go to Settings → AI Features → Load AI Model

Q: Slow processing?
A: Normal on CPU. Each image takes 2-5 seconds. Consider smaller batches.

Q: Model not downloading?
A: Check internet connection. Download requires ~3.3GB space.

Q: Out of memory?
A: Close other applications. Model requires ~4GB RAM.

Q: Wrong categorization?
A: AI isn't perfect. Review and manually adjust as needed.


📊 WHERE TO FIND AI STATUS
---------------------------
- Settings → AI Features section shows model status
- Analytics Dashboard → AI Insights section (when model loaded)
- Monitor cards show AI buttons only for local folders (not FTP)


🎯 USE CASES
------------
1. Organize messy Downloads folder with Auto-Categorize
2. Rename vacation photos with Smart Rename
3. Scan screenshots before sharing with Security Scan
4. Sort work screenshots into project folders
5. Identify documents that need redaction
6. Clean up desktop clutter automatically


═══════════════════════════════════════════════════════════════════════════════
For more help: Check Settings → About or Analytics Dashboard
Model: Qwen3-VL-4B-Instruct-Q4_K_M by Qwen Team
═══════════════════════════════════════════════════════════════════════════════
