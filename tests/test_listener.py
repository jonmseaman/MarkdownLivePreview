"""Exercise the plugin's editor logic against a fake `sublime` module.

Run with python -m unittest discover -s tests (from the repository root).
"""

import importlib
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FakeSettings(dict):
    def set(self, key, value):
        self[key] = value


class FakeView:
    _next_id = 1

    def __init__(self, window, file_name=None, content="", syntax=None):
        self._id = FakeView._next_id
        FakeView._next_id += 1
        self._window = window
        self._file_name = file_name
        self.content = content
        self._settings = FakeSettings()
        if syntax:
            self._settings["syntax"] = syntax
        self.closed = False
        self.read_only = False
        self.name_ = ""
        self.position = (0.0, 0.0)
        self.layout_height = 2000.0

    def id(self):
        return self._id

    def window(self):
        return None if self.closed else self._window

    def settings(self):
        return self._settings

    def file_name(self):
        return self._file_name

    def name(self):
        return self.name_

    def set_name(self, name):
        self.name_ = name

    def set_scratch(self, value):
        pass

    def set_read_only(self, value):
        self.read_only = value

    def buffer_id(self):
        return 0 if self.closed else self._id

    def size(self):
        return len(self.content)

    def substr(self, region):
        return self.content

    def viewport_extent(self):
        return (800, 600)

    def viewport_position(self):
        return self.position

    def set_viewport_position(self, xy, animate=True):
        self.position = xy

    def layout_extent(self):
        return (800, self.layout_height)

    def close(self):
        self.closed = True
        self._window._views.remove(self)


class FakeWindow:
    def __init__(self):
        self._views = []
        self.groups = 1
        self.group_of = {}
        self.active_group = 0

    def views(self):
        return list(self._views)

    def num_groups(self):
        return self.groups

    def set_layout(self, layout):
        self.groups = len(layout["cells"])

    def focus_group(self, group):
        self.active_group = group

    def focus_view(self, view):
        self.active_group = self.group_of.get(view.id(), 0)

    def get_view_index(self, view):
        return (self.group_of.get(view.id(), 0), 0)

    def new_file(self):
        view = FakeView(self)
        self._views.append(view)
        self.group_of[view.id()] = self.active_group
        return view

    def open(self, **kwargs):
        view = FakeView(self, **kwargs)
        self._views.append(view)
        self.group_of[view.id()] = self.active_group
        return view


class FakePhantomSet:
    def __init__(self, view):
        self.view = view
        self.phantoms = []

    def update(self, phantoms):
        self.phantoms = phantoms


def make_sublime(window, timers):
    sublime = types.ModuleType("sublime")
    sublime.Region = lambda a, b=None: (a, b)
    sublime.Phantom = lambda region, html, layout, on_navigate: html
    sublime.PhantomSet = FakePhantomSet
    sublime.LAYOUT_BLOCK = 2
    sublime.set_timeout_async = lambda fn, delay=0: timers.append(fn)
    sublime.windows = lambda: [window]
    sublime.packages_path = lambda: str(ROOT / "__no_such_dir__" / "Packages")
    class Settings(dict):
        def add_on_change(self, key, fn):
            pass

        def clear_on_change(self, key):
            pass

    settings = Settings(delay_between_updates=100)
    sublime.load_settings = lambda name: settings
    sublime.run_command = lambda *a, **k: None

    def load_resource(path):
        name = path.rsplit("/", 1)[1]
        return (ROOT / "resources" / name).read_text()

    sublime.load_resource = load_resource
    plugin = types.ModuleType("sublime_plugin")
    plugin.EventListener = object
    plugin.TextCommand = type(
        "TextCommand", (), {"__init__": lambda self, view: setattr(self, "view", view)}
    )
    return sublime, plugin


MD = "Packages/Markdown/Markdown.sublime-syntax"


class ListenerTests(unittest.TestCase):
    def setUp(self):
        self.window = FakeWindow()
        self.timers = []
        sublime, plugin = make_sublime(self.window, self.timers)
        sys.modules["sublime"] = sublime
        sys.modules["sublime_plugin"] = plugin
        sys.path.insert(0, str(ROOT.parent))
        name = ROOT.name
        for mod in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
            del sys.modules[mod]
        self.mlp = importlib.import_module(name + ".MarkdownLivePreview")
        self.mlp.MarkdownLivePreviewListener.phantom_sets.clear()
        self.mlp.MarkdownLivePreviewListener.pending.clear()
        self.mlp.synced_views.clear()
        self.mlp.last_scroll.clear()
        self.mlp.plugin_loaded()
        self.listener = self.mlp.MarkdownLivePreviewListener()

    def tearDown(self):
        sys.path.remove(str(ROOT.parent))

    def open_preview(self, view):
        self.mlp.OpenMarkdownPreviewCommand(view).run(None)

    def html_of(self, preview):
        ps = self.mlp.MarkdownLivePreviewListener.phantom_sets[preview.id()]
        return ps.phantoms[0]

    def test_preview_opens_in_other_group_of_same_window(self):
        md = self.window.open(file_name="/tmp/a.md", content="# Hi", syntax=MD)
        self.open_preview(md)
        previews = list(self.mlp.find_previews(md))
        self.assertEqual(len(previews), 1)
        preview = previews[0]
        self.assertIs(preview.window(), self.window)
        self.assertEqual(self.window.num_groups(), 2)
        self.assertEqual(self.window.group_of[preview.id()], 1)
        self.assertTrue(preview.read_only)
        self.assertEqual(preview.settings()["line_numbers"], False)
        self.assertEqual(preview.name(), "Preview: a.md")
        self.assertIn("<h1>Hi</h1>", self.html_of(preview))

    def test_command_toggles_preview(self):
        md = self.window.open(file_name="/tmp/a.md", content="x", syntax=MD)
        self.open_preview(md)
        self.open_preview(md)
        self.assertEqual(list(self.mlp.find_previews(md)), [])
        self.assertEqual(self.mlp.MarkdownLivePreviewListener.phantom_sets, {})

    def test_unsaved_buffer_can_be_previewed(self):
        md = self.window.open(file_name=None, content="*hello*", syntax=MD)
        self.open_preview(md)
        (preview,) = self.mlp.find_previews(md)
        self.assertIn("<em>hello</em>", self.html_of(preview))
        self.assertEqual(preview.name(), "Preview: untitled")

    def test_debounce_renders_final_state(self):
        md = self.window.open(file_name="/tmp/a.md", content="one", syntax=MD)
        self.open_preview(md)
        (preview,) = self.mlp.find_previews(md)
        self.timers.clear()  # drop the scroll-sync poll timer
        for text in ("t", "tw", "two"):
            md.content = text
            self.listener.on_modified_async(md)
        self.assertEqual(len(self.timers), 3)
        for timer in list(self.timers):
            timer()
        self.assertIn("<p>two</p>", self.html_of(preview))
        self.assertEqual(self.mlp.MarkdownLivePreviewListener.pending, {})

    def test_debounce_skips_stale_updates(self):
        md = self.window.open(file_name="/tmp/a.md", content="one", syntax=MD)
        self.open_preview(md)
        self.timers.clear()  # drop the scroll-sync poll timer
        calls = []
        original = self.mlp.update_preview
        self.mlp.update_preview = lambda view: calls.append(view.content)
        try:
            md.content = "a"
            self.listener.on_modified_async(md)
            md.content = "ab"
            self.listener.on_modified_async(md)
            for timer in list(self.timers):
                timer()
        finally:
            self.mlp.update_preview = original
        self.assertEqual(calls, ["ab"])

    def test_closing_markdown_closes_preview(self):
        md = self.window.open(file_name="/tmp/a.md", content="x", syntax=MD)
        self.open_preview(md)
        (preview,) = self.mlp.find_previews(md)
        self.listener.on_pre_close(md)
        self.assertTrue(preview.closed)
        self.assertEqual(self.mlp.MarkdownLivePreviewListener.phantom_sets, {})

    def test_closing_preview_drops_phantom_set(self):
        md = self.window.open(file_name="/tmp/a.md", content="x", syntax=MD)
        self.open_preview(md)
        (preview,) = self.mlp.find_previews(md)
        self.listener.on_pre_close(preview)
        self.assertEqual(self.mlp.MarkdownLivePreviewListener.phantom_sets, {})

    def test_views_without_syntax_are_ignored(self):
        widget = self.window.open(content="x")
        self.listener.on_pre_close(widget)
        self.listener.on_modified_async(widget)
        self.assertEqual(self.timers, [])

    def test_plugin_reload_closes_orphans_and_rerenders_live_previews(self):
        md = self.window.open(file_name="/tmp/a.md", content="live", syntax=MD)
        self.open_preview(md)
        orphan = self.window.new_file()
        orphan.settings().set(self.mlp.PREVIEW_VIEW_INFO, {"id": 99999})
        self.mlp.MarkdownLivePreviewListener.phantom_sets.clear()
        self.mlp.plugin_loaded()
        self.assertTrue(orphan.closed)
        (preview,) = self.mlp.find_previews(md)
        self.assertIn("<p>live</p>", self.html_of(preview))


    def scroll_setup(self):
        md = self.window.open(file_name="/tmp/a.md", content="x", syntax=MD)
        self.open_preview(md)
        (preview,) = self.mlp.find_previews(md)
        self.timers.clear()
        md.layout_height = 1600.0  # scrollable range 1000
        preview.layout_height = 3600.0  # scrollable range 3000
        return md, preview

    def test_scroll_sync_mirrors_relative_position(self):
        md, preview = self.scroll_setup()
        md.position = (0.0, 250.0)
        self.mlp.poll_scroll()
        self.assertEqual(preview.position, (0.0, 750.0))
        md.position = (0.0, 5000.0)  # scroll_past_end: clamp to the bottom
        self.mlp.poll_scroll()
        self.assertEqual(preview.position, (0.0, 3000.0))

    def test_scroll_sync_leaves_manual_preview_scrolling_alone(self):
        md, preview = self.scroll_setup()
        md.position = (0.0, 500.0)
        self.mlp.poll_scroll()
        preview.position = (0.0, 42.0)  # user scrolls the preview itself
        self.mlp.poll_scroll()  # markdown view hasn't moved
        self.assertEqual(preview.position, (0.0, 42.0))

    def test_scroll_resyncs_after_render(self):
        md, preview = self.scroll_setup()
        md.position = (0.0, 500.0)
        self.mlp.poll_scroll()
        preview.layout_height = 6600.0  # content grew
        self.mlp.update_preview(md)
        self.mlp.poll_scroll()
        self.assertEqual(preview.position, (0.0, 3000.0))

    def test_scroll_sync_can_be_disabled(self):
        md, preview = self.scroll_setup()
        self.mlp.SYNC_SCROLL = False
        md.position = (0.0, 500.0)
        self.mlp.poll_scroll()
        self.assertEqual(preview.position, (0.0, 0.0))

    def test_short_file_keeps_preview_at_top(self):
        md, preview = self.scroll_setup()
        md.layout_height = 300.0  # fits in the viewport
        self.mlp.poll_scroll()
        self.assertEqual(preview.position, (0.0, 0.0))

    def test_polling_stops_when_preview_closes(self):
        md, preview = self.scroll_setup()
        self.assertTrue(self.mlp.polling)
        self.open_preview(md)  # toggle off
        self.mlp.poll_scroll()
        self.assertFalse(self.mlp.polling)
        self.assertEqual(self.timers, [])


if __name__ == "__main__":
    unittest.main()
