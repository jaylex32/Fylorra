# Changelog

All notable changes to Fylorra are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v0.1.8] - 2026-09-01

### Changed

- The Windows setup installer now performs a real installation. Previously it
  copied a single self-extracting executable into the chosen folder, so nothing
  was actually installed there and the whole application had to unpack itself to
  a temporary directory on every launch. The Windows build is now a one-directory
  build, so the wizard writes the complete application - executable, Qt runtime,
  libraries, assets and bundled tools - into the directory you select.
- Windows startup is significantly faster, because launching no longer unpacks
  the full application first.
- The Windows portable download is now a folder rather than a single executable.
  Extract it and run `Fylorra.exe` inside. Linux and macOS downloads are unchanged.
- Uninstalling now removes the full installed application directory.

## [v0.1.7] - 2026-08-31

### Fixed

- Fixed widespread crashes in the packaged builds that did not occur when running
  from source. Background workers delivered their progress, status, finished and
  error callbacks on the worker thread instead of the GUI thread, so those callbacks
  updated Qt widgets from the wrong thread and the process died with a Windows
  access violation. This affected Device Transfer, Auto-Categorize, Smart Rename,
  AI Search indexing and search, Workspace, Cloud Sync, FTP browsing, media jobs,
  and the SMTP connection test.
- Progress bars, status labels and activity logs driven by background work now
  update reliably instead of taking the app down mid-operation.

## [v0.1.6] - 2026-08-31

### Changed

- Stabilized the AI runtime workflows.
- Made the smart rename similarity dependency optional, so the feature degrades
  gracefully when it is not installed.

### Added

- Added AI smoke gates to the binary builds so packaged AI failures are caught in CI.

## [v0.1.5] - 2026-08-31

### Added

- Added a branded Windows setup installer alongside the portable build.

### Fixed

- Fixed the Windows installer paths used by CI.

## [v0.1.4] - 2026-08-31

### Fixed

- Fixed crashes along the AI model load paths.

## [v0.1.3] - 2026-08-31

### Fixed

- Fixed a crash when downloading the AI model in packaged builds.

## [v0.1.2] - 2026-08-30

### Fixed

- Fixed a crash when downloading the AI model from Settings.

## [v0.1.1] - 2026-08-30

### Fixed

- Fixed the release binary name.
- Fixed AI model loading failures.

## [v0.1.0] - 2026-08-30

### Added

- Initial Fylorra release: folder monitoring and automation desktop app with a
  PySide6 interface.
- Cross-platform binary builds for Windows x64, Linux x64, macOS Apple Silicon
  and macOS Intel, with automated GitHub release publishing.
- README screenshots captured from the running app.

[v0.1.8]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.8
[v0.1.7]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.7
[v0.1.6]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.6
[v0.1.5]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.5
[v0.1.4]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.4
[v0.1.3]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.3
[v0.1.2]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.2
[v0.1.1]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.1
[v0.1.0]: https://github.com/jaylex32/Fylorra/releases/tag/v0.1.0
