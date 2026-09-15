# Release packaging checks

The v1.0.2 regression suite covers verified downloads, corrupt and missing
checksums, complete installation transactions and rollback filesystems, damaged
launcher recovery, exact resident process matching, real managed Python
environment repairs, and real backend process-tree cleanup during `--quit` and
SIGTERM. Releases are tested, built, and published manually.

# v1.0.2 validation — 2026-09-15

- All 44 regression tests passed with Arch's native Python 3.14, GTK 4.22, and
  PyGObject. The shutdown cases used isolated D-Bus sessions and real backend
  parent/child processes; no process-control calls were mocked.
- A disposable home and D-Bus session passed clean install, reinstall from the
  installed directory, repair after removing the importable application package,
  uninstall with desktop variables disabled, and reinstall with byte-identical
  retained configuration. It connected to the real Wayland and Hyprland endpoints,
  but its disposable Lua files were not part of the live compositor configuration.
- The candidate was installed into the live account. The keyboard-driven suite
  passed seven passage shapes, exact citations and clipboard bytes, live CSB to
  ESV configuration reload, failure recovery, Escape, focus loss, native Wayland
  window checks, repeated Alt+Space toggling with one PID, and exactly one live
  managed Alt+Space binding. Hyprland reported no configuration errors.
- The live configuration and clipboard SHA-256 values matched before and after
  the final launcher test. The test now detaches the restoring `wl-copy` owner so
  automation cleanup cannot discard the restored selection.
- The committed source archive passed the same 44-test suite after extraction.
  Its SHA256SUMS verified both the archive and download installer, contained no
  nested `dist` directory.
- The packaged download installer passed with a local release fixture: curl
  download, checksum selection and validation, extraction, installation, resident
  startup, temporary-directory cleanup, and offline uninstall all ran end to end.
A fresh login was not performed because it would terminate the active desktop
session. Login autostart remains verified from configuration and existing-session
startup, rather than a new Hyprland login.

# Bug review follow-up

22 tests pass. New coverage verifies running backend cancellation and process
termination, timeout cleanup, clipboard ordering, discarded stale responses,
unexpected clipboard errors, invalid UTF-8 configuration, rollback after Lua
validation or partial-edit failures, offline configuration removal, and
reinstalling from the installed directory.

Live checks passed for John 1:1-3 with its CSB citation, Escape terminating a
20-second test backend while preserving the clipboard, and running install.sh
from the installed application directory. Test configuration and clipboard were
restored, and the resident app restarted successfully.

# Citation formatting update

Clipboard output now consists of the backend passage (without trailing whitespace),
a blank line, and `(reference translation)`. Default and installed configuration
use `verse_numbers = false`; the existing scraper remains unchanged.

Seven unit tests pass, including range formatting and a config edit during a
request (the citation retains the translation actually queried). Live installed
launcher checks passed for John 1:1, John 1:1-3, and 1 John 4:7-12 in CSB,
plus John 1:1-3 in ESV without restarting. John 1:1 matched the requested output
exactly. Configuration and clipboard were restored after tests.

The following records the original installation checks before this formatting
change; its byte-for-byte raw-output expectations are superseded by the above.

# Verification — 2026-09-14

Tested on Omarchy 4.0.3, GTK 4.22.4, Python 3.14, native Wayland,
and the active eDP-1 monitor at 1.25 scale. No packages needed installation.

- Six unit tests passed: exact argument array/numbered books, safe option-like
  input, live config reload, unchanged stdout bytes, failure/empty output,
  timeout, invalid config, and clipboard invocation (some grouped in one test).
- Live GTK keyboard submissions passed for John 3:16, John 1:1-7,
  1 John 4:7-12, Psalm 23, and Romans 8:28-39. Wayland clipboard bytes equaled
  a direct call to the original backend, including the final newline.
- CSB → ESV TOML change took effect for John 3:16 with the same resident PID.
  Restored CSB afterward. Logs confirmed both optional flags enabled.
- Duplicate Return presses did not cause duplicate submissions.
- Invalid reference kept the launcher open and preserved the clipboard.
  Correcting the input succeeded without reopening.
- Escape cleared the entry and hid the window. Submitting the empty entry on
  the next invocation did nothing. Losing focus hid unsubmitted input.
- Eight virtual Alt+Space presses alternately showed/hid one window, retaining
  the same resident PID. The harness temporarily enabled symbol resolution for
  wtype's generated keymap and restored the original runtime setting afterward.
- Hyprland reported one Alt+Space binding and no configuration errors.
- Visual check: 650 × 90 logical pixels, centered, floating, native Wayland,
  rounded corners, no title bar, focused entry, dark GTK appearance.
- `--quit` left clipboard contents available; `--show` with no resident started
  it and displayed the window; another `--daemon` preserved that PID.
- Uninstall removed app, process and managed Lua blocks. SHA-256 checks confirmed
  the original Bible backend and TOML configuration were preserved.
- Reinstalled successfully; a second installation left both Lua files
  byte-identical, with exactly one managed block each.
- `o.launch_on_start` registration is in the user autostart module loaded by
  hyprland.lua; validated against the installed helper's `hyprland.start` event.

A fresh login was not performed because it would end the active desktop session.
Only one monitor is connected, so cross-monitor invocation is not physically
tested. Positioning uses Hyprland's center-on-map floating window rule.
