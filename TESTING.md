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
