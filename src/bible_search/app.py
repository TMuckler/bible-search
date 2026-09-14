"""Resident native GTK launcher. Only errors ever reach the secondary label."""
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import sys
import threading

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gdk, Gio, GLib, Gtk

from .backend import LookupError, lookup
from .clipboard import copy_passage
from .config import xdg_path
from .process import Cancelled

APP_ID = 'io.github.bible_search.Launcher'


class BibleSearch(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.busy = False
        self.generation = 0
        self.had_focus = False
        self.cancel = threading.Event()
        self.clipboard_lock = threading.Lock()

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()
        self.make_window()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.stop)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.stop)

    def stop(self):
        self.cancel.set()
        self.generation += 1
        self.quit()
        return GLib.SOURCE_REMOVE

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if args == ['--quit']:
            self.stop()
        elif args == ['--status']:
            command_line.print_literal(f'Bible Search resident PID {os.getpid()}\n')
        elif args == ['--daemon']:
            pass
        elif not args or args == ['--show']:
            self.show_launcher()
        else:
            command_line.printerr_literal('Usage: bible-search [--daemon|--show|--quit|--status]\n')
            return 2
        return 0

    def do_activate(self):
        self.show_launcher()

    def make_window(self):
        self.window = Gtk.ApplicationWindow(application=self, title='Bible Search')
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_default_size(650, -1)
        self.window.add_css_class('bible-search')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for side in ('top', 'bottom', 'start', 'end'):
            getattr(box, f'set_margin_{side}')(18)
        self.entry = Gtk.Entry(placeholder_text='John 3:16', hexpand=True)
        self.entry.set_max_length(512)
        self.entry.connect('activate', self.submit)
        self.entry.connect('changed', lambda *_: self.error.set_visible(False))
        box.append(self.entry)
        self.error = Gtk.Label(xalign=0)
        self.error.add_css_class('error')
        self.error.set_visible(False)
        box.append(self.error)
        self.window.set_child(box)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key_pressed)
        self.window.add_controller(keys)
        self.window.connect('close-request', self.close_requested)
        self.window.connect('notify::is-active', self.focus_changed)
        css = Gtk.CssProvider()
        css.load_from_string('''
            window.bible-search { border-radius: 14px; }
            .bible-search entry { font-size: 22px; min-height: 42px;
                padding: 5px 12px; border-radius: 9px; }
            .bible-search .error { font-size: 13px; color: @error_color; padding-left: 8px; }
        ''')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def show_launcher(self):
        if self.window.get_visible():
            self.dismiss()
            return
        self.had_focus = False
        self.window.present()
        self.entry.grab_focus()

    def dismiss(self):
        # Cancel the backend and discard responses that have not begun copying.
        self.cancel.set()
        self.generation += 1
        self.busy = False
        self.entry.set_editable(True)
        self.entry.set_text('')
        self.error.set_visible(False)
        self.window.set_visible(False)
        self.had_focus = False

    def close_requested(self, *_):
        self.dismiss()
        return True

    def key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.dismiss()
            return True
        return False

    def focus_changed(self, *_):
        if self.window.is_active():
            self.had_focus = True
        elif self.had_focus and self.window.get_visible() and not self.busy:
            self.dismiss()

    def submit(self, *_):
        if self.busy:
            return
        reference = self.entry.get_text().strip()
        if not reference:
            return
        self.busy = True
        self.entry.set_editable(False)
        self.error.set_visible(False)
        self.generation += 1
        token = self.generation
        self.cancel = threading.Event()
        threading.Thread(target=self.fetch, args=(reference, token, self.cancel), daemon=True).start()

    def fetch(self, reference, token, cancel):
        try:
            passage = lookup(reference, cancel=cancel)
            GLib.idle_add(self.fetched, token, passage, None)
        except Cancelled:
            return
        except LookupError as error:
            GLib.idle_add(self.fetched, token, None, str(error))
        except Exception:
            logging.exception('Unexpected lookup failure')
            GLib.idle_add(self.fetched, token, None, 'Unable to fetch passage')

    def fetched(self, token, passage, error):
        if token != self.generation:
            return GLib.SOURCE_REMOVE
        if error:
            self.finish(token, error)
        else:
            # Clipboard subprocess runs off the GTK thread as well.
            threading.Thread(target=self.copy, args=(token, passage), daemon=True).start()
        return GLib.SOURCE_REMOVE

    def copy(self, token, passage):
        # Once a Wayland clipboard transfer has begun, it cannot be undone safely.
        # Serialize transfers so an older slow copy can never overwrite a newer one.
        with self.clipboard_lock:
            if token != self.generation:
                return
            try:
                copy_passage(passage)
                error = None
            except LookupError as exc:
                error = str(exc)
            except Exception:
                logging.exception('Unexpected clipboard failure')
                error = 'Unable to copy passage'
        GLib.idle_add(self.finish, token, error)

    def finish(self, token, error):
        if token != self.generation:
            return GLib.SOURCE_REMOVE
        self.busy = False
        self.entry.set_editable(True)
        if error:
            self.error.set_text(error)
            self.error.set_visible(True)
            self.entry.grab_focus()
        else:
            self.dismiss()
        return GLib.SOURCE_REMOVE


def main():
    if sys.argv[1:] in (['--help'], ['-h']):
        print('Usage: bible-search [--daemon|--show|--quit|--status]')
        return 0
    if sys.argv[1:] not in ([], ['--daemon'], ['--show'], ['--quit'], ['--status']):
        print('Unknown option. Use bible-search --help.', file=sys.stderr)
        return 2
    # Status and quit must not start a resident process when none exists.
    if sys.argv[1:] in (['--status'], ['--quit']):
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        owner = bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
                              'org.freedesktop.DBus', 'NameHasOwner',
                              GLib.Variant('(s)', (APP_ID,)), GLib.VariantType('(b)'),
                              Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
        if not owner:
            print('Bible Search is not running')
            return 1 if sys.argv[1:] == ['--status'] else 0
    state = xdg_path('XDG_STATE_HOME', '.local/state') / 'bible-search'
    state.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(state / 'bible-search.log', maxBytes=1024*1024, backupCount=2)
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format='%(asctime)s %(levelname)s %(message)s')
    return BibleSearch().run(sys.argv)
