# Changelog

User-visible changes to Bible Search are recorded here.

## Unreleased

No changes yet.

## 1.0.2 — 2026-09-15

### Fixed

- Repair and uninstall damaged installations without invoking the possibly broken
  installed launcher. Process detection matches only the exact managed launcher,
  treats an absent resident as normal, and reports a resident that will not stop.
- Validate the managed Python interpreter, pip, and Beautiful Soup, Requests, and
  Unidecode imports. Rebuild incomplete environments through an atomic staged swap.
- Track all lookup and clipboard workers during shutdown. `--quit` and SIGTERM
  cancel current and recently replaced requests, terminate their process groups,
  reap adopted descendants, and wait for bounded cleanup without blocking GTK.
- Stage and validate complete application updates before stopping the prior
  resident. Roll back the application, launcher, configuration, and Lua integration
  after copy, integration, or daemon-start failures, and restart a prior resident.
- Preserve external backends, retained configuration, and user-created top-level
  files through repair, rollback, uninstall, and reinstall.

### Release reliability

- Exercise transaction outcomes and resulting filesystems, real temporary Python
  environments, and real subprocess trees for `--quit` and SIGTERM regressions.
- Make release reruns verify existing assets, upload only missing assets, and fail
  rather than overwrite differing files. Publishing remains dependent on tests.
- Record that the v1.0.1 tag workflow did not execute tests because GitHub blocked
  its test job for an account billing issue; that release was published separately
  and has no evidence of CI validation.

## 1.0.1 — 2026-09-14

### Added

- Publish a versioned download package and SHA-256 checksums.
- Add a short download installer that verifies the archive before running setup.
- Automatically test commits and publish tagged releases only after tests pass.

- Bundle the original `bible-fetch` Python script, its MIT-style license, and
  source provenance, crediting Erik J. Sturcke and subsequent contributors.
- Automatically set up the bundled backend in a private Python environment when
  no existing `bible` executable is found. Preserve existing backend installations.
- Include an actual launcher screenshot in the README.
- Add regression tests for cancellation, clipboard ordering, configuration
  errors, and installer recovery; the suite now contains 26 tests.
- Include this changelog in the repository and user installation.

### Fixed

- Terminate a running backend when its search is cancelled or the app quits.
- Serialize clipboard transfers so an older, slower transfer cannot overwrite
  a newer result; discard cancelled requests still waiting to copy.
- Recover from unexpected clipboard errors instead of leaving input locked.
- Allow reinstalling from the installed application directory without attempting
  to copy files onto themselves.
- Restore both user Lua files if editing or configuration validation fails.
- Validate the active Hyprland configuration before changing an installation.
- Allow configuration removal during uninstall without an active desktop session.
- Report invalid UTF-8 configuration as a configuration error.
- Preserve non-ASCII characters in executable paths written to Lua configuration.

### Clarified

- Cancellation cannot undo a clipboard transfer already handed to Wayland.

Implementation: [bundled backend and screenshot](https://github.com/TMuckler/bible-search/commit/4c3cb71),
[bug fixes](https://github.com/TMuckler/bible-search/commit/8c56d6b).

## 1.0.0 — 2026-09-14

Initial public version: [8bee5a4](https://github.com/TMuckler/bible-search/commit/8bee5a4).

### Added

- Native Python/GTK4 Bible passage launcher for Omarchy, Hyprland, and Wayland.
- Resident, single-instance operation with an Alt+Space shortcut and login autostart.
- Centered floating input with Escape, focus-loss dismissal, and toggle behavior.
- Asynchronous passage retrieval using the existing BibleGateway Python script.
- Direct Wayland clipboard output with unnumbered passage text, a blank line,
  and a citation such as `(John 1:1-3 CSB)`; no passage preview or success popup.
- Support for individual verses, ranges, numbered books, and whole chapters.
- TOML configuration for translation, backend path, verse numbers, and ASCII
  output, reloaded for every search.
- Error feedback without replacing the clipboard on failed or empty lookups.
- User installer and uninstaller, backed-up Lua integration, and diagnostic logs.
- Installation documentation, upstream author credits, and MIT licensing.
