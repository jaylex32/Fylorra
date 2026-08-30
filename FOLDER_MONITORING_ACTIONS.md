# Folder Monitoring Actions

Folder monitoring has two layers:

1. `File Filters` decide which files the monitor sees.
2. `Automation Rules` decide what happens to matching files.

## Safest Setup

For file routing, use `Created` only. This means the rule runs when a new file appears in the monitored folder.

Fylorra forces `Move` and `Organize` rules to `Created` only because `Modified` can fire many times while a download, scanner, or sync app is still writing a file.

## Office/Home Setup

Use this setup for a clean intake folder:

1. Monitor the folder where files arrive, such as Downloads, Scanner, Camera Import, Desktop, or a shared drop folder.
2. Add the `Office Organizer` preset.
3. Pick a destination outside the monitored folder.
4. Leave duplicate handling on `rename`.
5. Save the monitor.

Result:

```text
new report.pdf      -> destination/documents/report.pdf
new photo.jpg       -> destination/images/photo.jpg
new song.flac       -> destination/audio/song.flac
new installer.exe   -> destination/others/installer.exe
new archive.zip     -> destination/archives/archive.zip
```

Existing files are not moved during startup. The initial scan only records what is already there. To process existing files, use `Run automation rules now` from the monitor card and review the preview before confirming.

## Actions

`Copy`
: Copies the matching file into a destination folder. The original stays in the monitored folder.

`Move`
: Moves the matching file into a destination folder. The original leaves the monitored folder.

`Organize`
: Moves matching files into subfolders under a destination folder.

Examples:

```text
By extension: report.pdf -> destination/pdf/report.pdf
By date: photo.jpg -> destination/2026/08/photo.jpg
By type: song.mp3 -> destination/audio/song.mp3
```

`Rename`
: Renames the file in the same folder. Useful placeholders:

```text
{name}
{ext}
{date}
{time}
{timestamp}
```

Example:

```text
Pattern: {name}_{date}
report.pdf -> report_20260830.pdf
```

`Archive`
: Adds the file to a zip archive in the selected destination folder.

`Delete`
: Deletes the file using Recycle Bin/app trash when available.

`Clean folder`
: Deletes old files from a folder on a schedule. Cleanup skips active browser/download-manager files such as `.crdownload`, `.part`, `.download`, `.opdownload`, and fresh `.tmp` files. By default, scheduled cleanup keeps recent files and only removes empty folders after files are removed.

`Execute`
: Runs a command for each matching file. Use `{path}` for the full file path.

## Before Running On Existing Files

Use `Run automation rules now` on a monitor card. Fylorra now shows a preview of matching actions before it applies them.

If the preview says no files match, check:

- monitor-level File Filters
- rule-level extensions
- rule-level name regex
- whether the rule includes the `Created` event
