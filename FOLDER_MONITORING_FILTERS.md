# Folder Monitoring Filters

Folder filters run before notifications and automation rules. If a file does not pass these filters, Fylorra ignores it for that monitor.

## Basic Setup

1. Open `Folder Monitor`.
2. Choose or edit a monitored folder.
3. Open `File Filters`.
4. Leave a value blank or set it to `0` when you do not want that filter.
5. Save the monitor.

## Filters

`Minimum size`
: Only process files at least this size. Example: `1024 KB` ignores files smaller than 1 MB.

`Maximum size`
: Only process files up to this size. Example: `51200 KB` ignores files larger than 50 MB.

`Modified in last`
: Only process files changed recently. Example: `7 days` ignores older files.

`Exclude patterns`
: Ignore files or folders before rules run. Add one per line or separate them with commas.

Examples:

```text
*.tmp
node_modules/
.git/
*/cache/*
```

`Filename regex`
: Advanced filter that matches only the filename, not the folder path.

Examples:

```text
^invoice_.*\.pdf$
^client_[0-9]+\.docx$
report_\d{4}\.xlsx
```

## Global Filters vs Rule Filters

Global monitor filters decide what the monitor sees.

Rule filters decide whether one specific automation rule runs after the file passes the global filters.

Example: a monitor can ignore `node_modules/`, then one rule can move only `pdf` files and another rule can copy only `jpg` files.
