# Fylorra Product Direction

## Positioning

Fylorra should be a focused file intake automation tool, not a general multi-tool launcher. The core promise is:

> When a file lands somewhere, Fylorra knows what it is, sends it where it belongs, and records what happened.

## Primary Workflow

1. Watch an intake folder such as Downloads, Scanner, Camera Import, Desktop, or a cloud sync folder.
2. Classify the incoming file using rules, metadata, and optional local AI.
3. Preview risky actions before they run.
4. Move, copy, rename, link, convert, archive, upload, or delete safely.
5. Record every action in logs and undo history where possible.

## Product Rules

- Folder monitoring is the main product surface.
- AI should assist rule creation, search, and file understanding; it should not block basic automation when models are missing.
- Destructive actions must require clear confirmation in UI and conservative defaults in core code.
- App data lives under `.fylorra`; there is no legacy migration burden before first release.
- Extra tools should be reachable as helpers for intake workflows, not presented as equal competing products.

## Next High-Value Work

- Add a run preview for every monitor rule showing exact source files and destination paths.
- Add a single "Inbox Health" dashboard: active monitors, stuck files, recent failures, duplicate collisions, and missing destinations.
- Add per-rule dry-run mode and last-run summary.
- Add undo coverage to copy/move/rename/archive actions from monitor rules.
- Add a startup safety audit that flags monitors pointed at risky roots or destinations inside watched folders.
