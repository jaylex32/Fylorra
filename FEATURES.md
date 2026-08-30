# Fylorra - Complete Feature List

## ✅ **Persistence & Settings**

### Automatic Save/Load
- ✅ **All monitors automatically saved** when you close the app
- ✅ **Auto-restore on startup** - All your monitors come back exactly as they were
- ✅ **Running state preserved** - Monitors that were running will auto-start
- ✅ **FTP credentials saved** - Securely stored in local config
- ✅ **Settings location**: `C:\Users\[YourName]\.fylorra\`
  - `settings.json` - Application settings
  - `monitors.json` - All monitor configurations

## 📊 **Comprehensive Logging System**

### What Gets Logged
1. **Monitor Lifecycle Events**
   - Monitor added/removed/started/stopped
   - FTP connection attempts and results

2. **Initial Folder Scans**
   - When you start a monitor, it scans all existing files
   - Logs total file count and folder count
   - Lists individual files (up to 100, otherwise summary)
   - **Example output:**
     ```
     INITIAL SCAN: C:\Downloads | Files: 45 | Folders: 3
     EXISTING: C:\Downloads\document.pdf | Found during initial scan
     ```

3. **File System Events**
   - Every file created, modified, deleted, or moved
   - Full file paths with timestamps
   - **Example output:**
     ```
     [C:\Downloads] CREATED: newfile.pdf
     [C:\Downloads] MODIFIED: document.docx
     [C:\Downloads] DELETED: oldfile.txt
     ```

4. **Automation Actions**
   - Every rule execution logged
   - Success or failure status
   - **Example output:**
     ```
     ACTION: COPY on C:\file.pdf - SUCCESS | Rule matched: created event
     ACTION: MOVE on C:\file.doc - FAILED | Destination not accessible
     ```

5. **Errors and Issues**
   - Connection failures
   - Permission errors
   - Invalid paths

### Log Locations
- **Console**: Real-time output in command prompt
- **Log Files**: `C:\Users\[YourName]\.fylorra\logs\`
  - Daily log files: `fylorra_YYYYMMDD.log`
  - Automatically managed (old logs auto-deleted after 30 days)

### Log Export Features
Access via **"📊 Export Logs"** button:

1. **Text Format (.txt)**
   - Human-readable
   - Perfect for reviewing activity
   - Easy to email or share

2. **JSON Format (.json)**
   - Machine-readable
   - Complete data structure
   - Perfect for processing/analysis

3. **CSV Format (.csv)**
   - Spreadsheet-compatible
   - Open in Excel/Google Sheets
   - Perfect for data analysis

4. **Quick Actions**
   - **Open Log Folder** - Jump directly to logs in Explorer
   - **Clear Old Logs** - Remove logs older than 30 days

## 🔄 **Monitor Persistence Details**

### What Gets Saved
```json
{
  "type": "folder",  // or "ftp"
  "id": "unique-monitor-id",
  "path": "C:\\Users\\...\\Downloads",
  "rules": [...],  // All your automation rules
  "is_running": true,  // Whether it was running when you closed
  "stats": {
    "files_created": 45,
    "files_modified": 12,
    "files_deleted": 3,
    "actions_executed": 10
  }
}
```

### On Application Start
1. ✅ Loads all saved monitors
2. ✅ Recreates monitor cards in UI
3. ✅ Restores all automation rules
4. ✅ Auto-starts monitors that were running
5. ✅ Displays statistics from last session

### On Application Close
1. ✅ Saves all current monitors
2. ✅ Saves running state of each monitor
3. ✅ Stops all active monitoring threads
4. ✅ Flushes logs to disk
5. ✅ Saves application settings

## 🌐 **FTP/Network Support**

### Network Folders (UNC Paths)
- ✅ Full support for `\\ServerName\Share\Folder`
- ✅ Real-time monitoring (same as local folders)
- ✅ Automatic reconnection if network temporarily unavailable
- ✅ All features work: notifications, rules, logging

### FTP/FTPS Servers
- ✅ Standard FTP (port 21)
- ✅ FTPS (FTP with TLS/SSL encryption)
- ✅ Custom ports supported
- ✅ Polling-based (checks every N seconds)
- ✅ Connection testing before adding
- ✅ Credentials saved securely
- ✅ Windows notifications for FTP changes

## 🔔 **Windows Notifications**

### Notification Types
1. **File Events**
   - 📁 New File Detected
   - ✏️ File Modified
   - 🗑️ File Deleted
   - 📦 File Moved

2. **Action Events**
   - 📋 Copy Completed
   - 🚀 Move Completed
   - ✏️ Rename Completed
   - ✅ Action Completed
   - ❌ Action Failed

3. **FTP Events**
   - Same notifications for FTP file changes
   - Connection status alerts

## 📝 **Complete Activity Log Example**

```
2025-12-14 23:48:34 | INFO | ================================================================================
2025-12-14 23:48:34 | INFO | Fylorra Started
2025-12-14 23:48:34 | INFO | ================================================================================
2025-12-14 23:50:15 | INFO | MONITOR ADDED: C:\Downloads (ID: a1b2c3d4...) | Rules: 2
2025-12-14 23:50:15 | INFO | INITIAL SCAN: C:\Downloads | Files: 125 | Folders: 8
2025-12-14 23:50:15 | INFO | EXISTING: C:\Downloads\document.pdf | Found during initial scan
2025-12-14 23:50:15 | INFO | EXISTING: C:\Downloads\image.jpg | Found during initial scan
... (all existing files logged)
2025-12-14 23:50:16 | INFO | MONITOR STARTED: C:\Downloads (ID: a1b2c3d4...)
2025-12-14 23:52:30 | INFO | [C:\Downloads] CREATED: newfile.docx
2025-12-14 23:52:31 | INFO | ACTION: COPY on C:\Downloads\newfile.docx - SUCCESS | Rule matched: created event
2025-12-14 23:53:45 | INFO | [C:\Downloads] MODIFIED: report.xlsx
2025-12-14 23:55:00 | INFO | MONITOR STOPPED: C:\Downloads (ID: a1b2c3d4...)
2025-12-14 23:55:00 | INFO | MONITOR REMOVED: C:\Downloads (ID: a1b2c3d4...)
2025-12-14 23:56:00 | INFO | MONITOR SAVED: All monitors (ID: all...) | Saved 3 monitors
2025-12-14 23:56:00 | INFO | ================================================================================
2025-12-14 23:56:00 | INFO | Fylorra Stopped
2025-12-14 23:56:00 | INFO | ================================================================================
```

## 🎯 **Real-World Scenarios**

### Scenario 1: Work Backup
**Setup:**
1. Add monitor for `C:\Work\Projects`
2. Add rule: Copy all `.docx, .xlsx` files to `D:\Backups`
3. Start monitor

**What You Get:**
- Immediate scan of 200 existing files (all logged)
- Real-time notifications when files change
- Automatic backup to D:\Backups
- Complete log of all backups with timestamps
- Export weekly logs for compliance

### Scenario 2: FTP Downloads
**Setup:**
1. Add FTP monitor for `ftp://company-server.com/downloads`
2. Configure to check every 60 seconds
3. Start monitor

**What You Get:**
- Notifications when new files appear on FTP
- Full activity log of all FTP events
- Monitor persists across restarts
- Credentials saved securely

### Scenario 3: Network Share Monitoring
**Setup:**
1. Add monitor for `\\FileServer\SharedDocs`
2. Add organize rule: Sort by file type
3. Start monitor

**What You Get:**
- Real-time monitoring of network folder
- Initial scan logs all 500+ existing files
- Auto-organization on file creation
- All activity logged for audit trail

## 🛠️ **Settings Persistence**

All these settings are automatically saved:
- ✅ Theme (dark/light/system)
- ✅ Color scheme
- ✅ Window size and position
- ✅ Notification preferences
- ✅ Minimize to tray behavior
- ✅ Auto-start monitors on launch

## 📈 **Statistics Tracking**

Per-monitor statistics (saved and restored):
- Files created count
- Files modified count
- Files deleted count
- Files moved count
- Automation actions executed

## 🔒 **Data Security**

- ✅ All data stored locally only
- ✅ No cloud sync or external connections
- ✅ FTP passwords stored in local JSON (consider encrypting in production)
- ✅ Logs contain full file paths (keep secure)
- ✅ Easy to backup: Just copy `.fylorra` folder

---

## 📊 **Quick Reference**

### Files & Folders
- **Config**: `%USERPROFILE%\.fylorra\settings.json`
- **Monitors**: `%USERPROFILE%\.fylorra\monitors.json`
- **Logs**: `%USERPROFILE%\.fylorra\logs\fylorra_YYYYMMDD.log`

### Key Features
- ✅ Automatic save on close
- ✅ Automatic restore on start
- ✅ Complete activity logging
- ✅ Export logs (JSON/CSV/Text)
- ✅ Initial folder scans
- ✅ Real-time console output
- ✅ FTP/Network support
- ✅ Windows notifications

### UI Buttons
- **+ Folder Monitor** - Add local/network folder
- **+ FTP Monitor** - Add FTP server
- **📊 Export Logs** - Export activity logs
- **⚙️ Settings** - Application settings

---

**Everything is automatically saved. Just use the app - your data is safe!** 🎉
