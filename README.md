# Bible Search

A small native GTK4 launcher for Omarchy/Hyprland/Wayland:

**Alt+Space → type a Bible reference → Enter → paste with Ctrl+V.**

The passage goes directly to your clipboard. The window disappears and clears
its input. No results, previews, history, or success popups. The resident process
keeps GTK ready between searches; Gio/D-Bus ensures a single instance.

![Bible Search native launcher showing the John 3:16 placeholder](assets/screenshot.png)

The actual native launcher; fetched passages go directly to the clipboard.

## Install from GitHub

Designed for **Omarchy with Hyprland's Lua configuration** (tested on Omarchy
4.0.3). Run installation from your logged-in desktop session. This is a native
Python/GTK4 application, not a web app or Electron application. An internet
connection is required for passage lookups.

```bash
git clone https://github.com/TMuckler/bible-search.git
cd bible-search
./scripts/install.sh
```

The repository includes the [original Bible Python script](third_party/bible-fetch/bible)
and its [license](third_party/bible-fetch/LICENSE). No separate backend download
or manual Python setup is required.

The installer keeps an existing configured backend or discovers `bible` on PATH,
in `~/.local/bin`, or in the current directory. If none exists, it installs the
bundled script with a private virtual environment containing Beautiful Soup,
Requests, and Unidecode. This managed backend lives in
`~/.local/share/bible-search/backend/bible` (respecting `XDG_DATA_HOME`) and its
path is written into config.toml. An existing `bible` script is never overwritten.

To select a different existing backend when creating the configuration:

```bash
./scripts/install.sh --bible /absolute/path/to/bible
```

Requires Python 3.11+, `python-gobject`, `gtk4`, and `wl-clipboard`. The installer
reports missing Arch packages and invokes pacman with sudo (interactive terminal)
or pkexec (graphical authorization). Bundled backend dependencies are installed
with pip into a user-owned virtual environment, without sudo.

Installs into `$XDG_DATA_HOME/bible-search` (default `~/.local/share/bible-search`)
with an executable at `~/.local/bin/bible-search`. It backs up user Lua files before
editing, uses marked blocks to avoid duplicates, configures Alt+Space and login
autostart, reloads and validates Hyprland, checks the backend and clipboard
connection, and starts/verifies the resident process. Re-running preserves your
TOML configuration. `--bible` applies only when creating a new configuration.

## Clipboard output

For `John 1:1`, the default CSB output is:

```text
In the beginning was the Word, and the Word was with God, and the Word was God.

(John 1:1 CSB)
```

For `John 1:1-3`, all three verses are copied together, followed by a blank line
and `(John 1:1-3 CSB)`. Numbered books such as `1 John 4:7-12` and whole chapters
such as `Psalm 23` work too. The citation retains the reference you typed.

## How it works

1. Omarchy starts a resident process at login, with its window hidden.
2. Alt+Space activates that process through Gio/D-Bus and focuses its GTK input.
3. Enter reads the current TOML configuration and runs your `bible` executable
   with an argument array in a worker thread. No shell interprets the reference.
4. The existing script fetches and extracts the passage from BibleGateway.
5. Bible Search removes trailing whitespace, appends a blank line and
   `(reference translation)`, and sends the text to Wayland's `wl-copy`.
6. Once copying succeeds, the launcher clears its input and hides. `wl-copy`
   keeps the text available for pasting independently of the launcher window.

The translation used in the citation comes from the same configuration snapshot
as the query. Backend failure or empty output produces a small error beneath the
input and leaves the existing clipboard untouched. There is no passage display,
second confirmation, history, or Bible-reading interface.

## Usage

Type `John 3:16`, `John 1:1-7`, `1 John 4:7-12`, `Psalm 23`, `Genesis 1`,
or `Romans 8:28-39`, then press Enter once. Wait for the window to disappear,
then paste. The passage is followed by a blank line and its citation, for example
`(John 1:1 CSB)` or `(John 1:1-3 CSB)`. Verse numbers are omitted by default.
Paragraph breaks within the passage are preserved. Escape cancels and clears. Alt+Space again toggles closed. Unsubmitted
input is dismissed on focus loss. Duplicate Enter presses during a request are
ignored. Errors appear below the input; correct the reference and retry.

```bash
bible-search --show    # show/toggle; starts resident process if needed
bible-search --daemon  # start hidden; harmless if already running
bible-search --status  # report resident PID (exit 1 if absent)
bible-search --quit    # stop; does not start an absent daemon
```

## Configuration

Edit `~/.config/bible-search/config.toml` (or
`$XDG_CONFIG_HOME/bible-search/config.toml`):

```toml
translation = "CSB"
bible_command = "/absolute/path/to/bible"
verse_numbers = false
ascii = true
```

**Changing `translation = "CSB"` to `"ESV"` or `"NASB"` changes the translation
BibleGateway is queried with on the very next search. No restart is needed.**
The file is reread for every lookup. Change `bible_command` to move or replace
your backend; it must be an executable absolute path (`~` and environment
variables are expanded). The booleans control `--verse-numbers` and `--ascii`. Leave `verse_numbers = false`
for unnumbered text; set it to true if you want verse numbers back. The citation
uses the reference you entered and the translation used for that lookup.
A missing configuration is automatically created with CSB and a discovered backend.

The command uses an argument array, never a shell. Options are placed before
`--` and the reference is passed as one argument; the existing backend joins
its positional arguments and handles multiword/numbered book names normally.

## Omarchy integration

Managed blocks live in `~/.config/hypr/bindings.lua` and `autostart.lua` (respecting
XDG_CONFIG_HOME). They use `hl.unbind`, `o.bind`, `o.window`, and
`o.launch_on_start`. The window floats centered with no compositor decorations
or animation. Its colors and font follow GTK/system settings. See the
[Hyprland window rule documentation](https://wiki.hypr.land/Configuring/Basics/Window-Rules/).
No packaged Omarchy files are modified. Backups have `.bak.bible-search.*` suffixes.

## Troubleshooting

- Check `bible-search --status`; run `bible-search --show` if stopped.
- Logs: `~/.local/state/bible-search/bible-search.log` (rotated) and `session.log`,
  or under `$XDG_STATE_HOME`. Passages are not logged.
- Test the configured script directly:
  `bible --version CSB --verse-numbers --ascii -- 'John 3:16'`.
- “Passage not found”: inspect your reference/translation; check the backend log.
- Network failures/timeouts preserve the clipboard. Lookups time out after 30 seconds.
- “Check config.toml”: check TOML syntax, string values, and boolean types.
- Clipboard errors: confirm `wl-copy` is installed and WAYLAND_DISPLAY points to
  your active session. Clipboard content survives hiding or quitting Bible Search.
- Shortcut issues: `hyprctl configerrors`, `hyprctl binds`, and `hyprctl reload`.
  The installer overrides any existing Alt+Space binding at user level; removing
  its block restores previously defined bindings after reload.
- Auto-start is registered for the next Hyprland session start. Reloading config
  alone does not fire the login event; the installer explicitly starts this session.

## Uninstall

```bash
./scripts/uninstall.sh
# Or, after removing the source checkout:
~/.local/share/bible-search/scripts/uninstall.sh
```

Stops the resident process, removes the executable/application and only the marked
Lua blocks, then reloads Hyprland. Your original `bible` script, TOML config, logs,
and backups are retained. A backend installed by Bible Search and its private
virtual environment are removed with the application; external backends remain
untouched. Reinstalling restores the managed backend if your retained config
points to it. Remove the Bible Search config manually if desired.

## Tests

```bash
PYTHONPATH=src /usr/bin/python -m unittest discover -s tests -v
```

Live integration tests are in `scripts/test_live.py` and also require `wtype`
for keyboard injection. They temporarily change the
clipboard and translation, exercise the visible launcher in the current session,
and restore configuration and clipboard afterward. The shortcut test temporarily
enables symbol-based binding resolution for wtype’s generated keyboard map, then
restores the original runtime setting; no input configuration file is changed. Run only when you can leave
the keyboard/mouse idle during the checks.

## Credits and license

The original **`bible` Python script / bible-fetch was written by
[Erik J. Sturcke](https://github.com/esturcke)**. Thank you for the command-line
BibleGateway retrieval code that makes this launcher possible.

- Upstream project: [covode/bible-fetch](https://github.com/covode/bible-fetch).
- The upstream [license](https://github.com/covode/bible-fetch/blob/main/LICENSE)
  credits **Copyright (C) 2013 Erik J. Sturcke**.
- Thanks also to [Ben Tsai](https://github.com/bentsai) and the other
  [bible-fetch contributors](https://github.com/covode/bible-fetch/graphs/contributors)
  for subsequent improvements.

Bible Search adds the native launcher, Omarchy integration, configuration,
citation formatting, and clipboard workflow. An unmodified copy of the original
script and its copyright notice are included under [third_party/bible-fetch](third_party/bible-fetch).
The pinned source revision and provenance are documented there.

Bible Search is maintained by [TMuckler](https://github.com/TMuckler) and released
under the [MIT License](LICENSE). Bible-fetch has its own MIT-style license.
Scripture text is retrieved from [BibleGateway](https://www.biblegateway.com/);
the application license does not license the Bible translations themselves.
