"""
Terminology
markdown_view: the view holding the markdown being edited
preview_view: a scratch view, in another group of the same window, that renders
              markdown_view's content as a phantom
"""
import os.path
import re
from collections import OrderedDict
from functools import partial

import sublime
import sublime_plugin

from .markdown2html import markdown2html, pygments_highlight

try:
    import mdpopups
except ImportError:  # fall back to Pygments
    mdpopups = None

PREVIEW_VIEW_INFO = "preview_view_info"
DELAY = 100  # overwritten by the setting in plugin_loaded
SYNC_SCROLL = True  # overwritten by the setting in plugin_loaded
FOLLOW_ACTIVE_FILE = True  # overwritten by the setting in plugin_loaded
SCROLL_POLL_MS = 50
resources = {}

# Sublime has no scroll event, so while previews are open we poll the markdown
# views' viewport positions and mirror them onto their previews.
synced_views = {}  # {markdown_view.id(): markdown_view}
last_scroll = {}  # {markdown_view.id(): last synced viewport y}
last_width = {}  # {markdown_view.id(): previews' viewport widths at last check}
polling = False


def is_markdown(view):
    syntax = view.settings().get("syntax") or ""
    return "markdown" in syntax.lower()


def is_preview(view):
    return bool(view.settings().get(PREVIEW_VIEW_INFO))


def find_previews(view):
    """Yield the preview views attached to markdown view `view`."""
    window = view.window()
    if window is None:
        return
    view_id = view.id()
    for other in window.views():
        info = other.settings().get(PREVIEW_VIEW_INFO)
        if info and info.get("id") == view_id:
            yield other


def group_of(view):
    window = view.window()
    return window.get_view_index(view)[0] if window else -1


def preview_target(preview):
    """The markdown view `preview` shows, or None if it's detached."""
    target_id = (preview.settings().get(PREVIEW_VIEW_INFO) or {}).get("id")
    window = preview.window()
    if target_id is None or window is None:
        return None
    for view in window.views():
        if view.id() == target_id:
            return view
    return None


def preview_name(view):
    return "Preview: " + os.path.basename(
        view.file_name() or view.name() or "untitled"
    )


def attach_preview(preview, view):
    """Point `preview` at markdown view `view` and render it."""
    preview.settings().set(PREVIEW_VIEW_INFO, {"id": view.id()})
    preview.set_name(preview_name(view))
    update_preview(view)
    start_scroll_sync(view)


def follow(view):
    """Point a preview in another pane of the window at markdown view `view`.

    Picks a preview showing a file from `view`'s pane (or a detached one); if
    the window has exactly one preview, that one."""
    window = view.window()
    if window is None or any(find_previews(view)):
        return
    group = group_of(view)
    previews = [
        other
        for other in window.views()
        if is_preview(other) and window.get_view_index(other)[0] != group
    ]
    if not previews:
        return
    candidates = [
        preview
        for preview in previews
        if preview_target(preview) is None or group_of(preview_target(preview)) == group
    ]
    if not candidates and len(previews) == 1:
        candidates = previews
    if candidates:
        attach_preview(candidates[0], view)


def reattach_after_close(window, group, previews):
    """After the file previews were showing is closed: show the file now
    active in its pane, or another markdown file, or close the previews."""
    previews = [preview for preview in previews if preview.window() is not None]
    if not previews:
        return
    active = window.active_view_in_group(group)
    choices = [active] if active is not None else []
    choices += window.views_in_group(group) + window.views()
    for view in choices:
        if is_markdown(view) and not is_preview(view):
            for preview in previews:
                attach_preview(preview, view)
            return
    for preview in previews:
        MarkdownLivePreviewListener.phantom_sets.pop(preview.id(), None)
        preview.close()


def scroll_fraction(view):
    """How far down `view` is scrolled, from 0.0 (top) to 1.0 (bottom)."""
    scrollable = view.layout_extent()[1] - view.viewport_extent()[1]
    if scrollable <= 0:
        return 0.0
    return min(max(view.viewport_position()[1] / scrollable, 0.0), 1.0)


def sync_scroll(view, force=False):
    """Scroll `view`'s previews to the same relative position as `view`."""
    y = view.viewport_position()[1]
    if not force and last_scroll.get(view.id()) == y:
        return
    last_scroll[view.id()] = y
    fraction = scroll_fraction(view)
    for preview in find_previews(view):
        scrollable = preview.layout_extent()[1] - preview.viewport_extent()[1]
        x = preview.viewport_position()[0]
        preview.set_viewport_position((x, max(scrollable, 0) * fraction), False)


def start_scroll_sync(view):
    global polling
    synced_views[view.id()] = view
    last_scroll.pop(view.id(), None)
    if not polling:
        polling = True
        sublime.set_timeout_async(poll_scroll, SCROLL_POLL_MS)


def stop_scroll_sync(view_id):
    synced_views.pop(view_id, None)
    last_scroll.pop(view_id, None)
    last_width.pop(view_id, None)


def poll_scroll():
    global polling
    for view_id, view in list(synced_views.items()):
        previews = list(find_previews(view)) if view.buffer_id() else []
        if not previews:
            stop_scroll_sync(view_id)
            continue
        # tables and images are sized to the preview: re-render when it resizes
        widths = tuple(preview.viewport_extent()[0] for preview in previews)
        if last_width.setdefault(view_id, widths) != widths:
            last_width[view_id] = widths
            update_preview(view)
        if SYNC_SCROLL:
            sync_scroll(view)
    if synced_views:
        sublime.set_timeout_async(poll_scroll, SCROLL_POLL_MS)
    else:
        polling = False


def get_resource(resource):
    path = "Packages/{}/resources/{}".format(__package__, resource)
    abs_path = os.path.join(sublime.packages_path(), "..", path)
    if os.path.isfile(abs_path):
        with open(abs_path, "r") as fp:
            return fp.read()
    return sublime.load_resource(path)


class MarkdownLivePreviewListener(sublime_plugin.EventListener):
    phantom_sets = {}  # {preview_view.id(): PhantomSet}
    pending = {}  # {markdown_view.id(): number of scheduled updates}

    def on_pre_close(self, view):
        """Closing a markdown file moves its previews to the next markdown file
        (with follow_active_file), or closes them."""
        if is_preview(view):
            self.phantom_sets.pop(view.id(), None)
        elif is_markdown(view):
            self.pending.pop(view.id(), None)
            stop_scroll_sync(view.id())
            previews = list(find_previews(view))
            if not previews:
                return
            window = view.window()
            if FOLLOW_ACTIVE_FILE and window is not None:
                for preview in previews:
                    preview.settings().set(PREVIEW_VIEW_INFO, {"id": None})
                # once the view is gone and Sublime has activated the next tab
                sublime.set_timeout(
                    partial(reattach_after_close, window, group_of(view), previews), 0
                )
            else:
                for preview in previews:
                    self.phantom_sets.pop(preview.id(), None)
                    preview.close()

    def on_activated_async(self, view):
        if FOLLOW_ACTIVE_FILE and is_markdown(view) and not is_preview(view):
            follow(view)

    def on_load_async(self, view):
        """A file opened while a preview follows may only become markdown (get
        its syntax) once loaded."""
        if not is_markdown(view) or is_preview(view):
            return
        if any(find_previews(view)):
            update_preview(view)
        elif FOLLOW_ACTIVE_FILE and view.window() and view.window().active_view() == view:
            follow(view)

    def on_modified_async(self, view):
        """Debounce: render DELAY ms after the last modification."""
        if not is_markdown(view) or is_preview(view):
            return
        view_id = view.id()
        self.pending[view_id] = self.pending.get(view_id, 0) + 1
        sublime.set_timeout_async(partial(self._debounced_update, view), DELAY)

    def _debounced_update(self, view):
        view_id = view.id()
        count = self.pending.get(view_id, 0) - 1
        if count > 0:
            self.pending[view_id] = count
            return  # a newer modification has its own update scheduled
        self.pending.pop(view_id, None)
        update_preview(view)


HIGHLIGHT_CACHE_SIZE = 500
highlight_cache = OrderedDict()  # {(color scheme, language, source): html}


def is_dark(view):
    background = (view.style().get("background") or "#ffffff").lstrip("#")
    try:
        red, green, blue = (int(background[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return False
    return 0.299 * red + 0.587 * green + 0.114 * blue < 128


def make_highlighter(view):
    """highlighter(source, language) for markdown2html: Sublime's own syntaxes
    and the view's color scheme via mdpopups, else Pygments, else None (plain).

    Results are cached, since every keystroke re-renders every code block."""
    scheme = view.settings().get("color_scheme")
    dark = is_dark(view)

    def highlight(source, language):
        if not language:
            return None
        key = (scheme, dark, language, source)
        if key in highlight_cache:
            highlight_cache.move_to_end(key)
            return highlight_cache[key]
        html = None
        if mdpopups is not None:
            result = mdpopups.syntax_highlight(view, source, language=language)
            # on failure, mdpopups returns the source unchanged
            if result and result.startswith('<div class="highlight">'):
                # mdpopups ends every line with <br>, including the last one
                html = re.sub(r"<br>((?:</span>)*</pre></div>)\s*$", r"\1", result)
        if html is None:
            html = pygments_highlight(source, language, dark)
        highlight_cache[key] = html
        while len(highlight_cache) > HIGHLIGHT_CACHE_SIZE:
            highlight_cache.popitem(last=False)
        return html

    return highlight


def update_preview(view):
    # buffer_id() is 0 once markdown_view is closed. This is needed because this
    # function is also the callback for images loaded from the internet, which
    # can finish *after* the user closes the markdown view.
    if view.buffer_id() == 0:
        return
    previews = list(find_previews(view))
    if not previews:
        return

    file_name = view.file_name()
    basepath = os.path.dirname(file_name) if file_name else os.path.expanduser("~")
    markdown = view.substr(sublime.Region(0, view.size()))

    highlighter = make_highlighter(view)
    for preview in previews:
        # Size table text so each character is a whole number of pixels wide.
        em_width = preview.em_width() or 8.0
        char_width = max(round(em_width), 1)
        html = markdown2html(
            markdown,
            basepath,
            partial(update_preview, view),
            resources,
            preview.viewport_extent()[0],
            char_width=char_width,
            font_face=view.settings().get("font_face") or None,
            font_scale=char_width / em_width,
            highlighter=highlighter,
        )
        phantom_set = MarkdownLivePreviewListener.phantom_sets.get(preview.id())
        if phantom_set is None:
            phantom_set = sublime.PhantomSet(preview)
            MarkdownLivePreviewListener.phantom_sets[preview.id()] = phantom_set
        phantom_set.update(
            [
                sublime.Phantom(
                    sublime.Region(0),
                    html,
                    sublime.LAYOUT_BLOCK,
                    lambda href: sublime.run_command("open_url", {"url": href}),
                )
            ]
        )
    # the preview's height changed: re-sync on the next poll
    last_scroll.pop(view.id(), None)


class OpenMarkdownPreviewCommand(sublime_plugin.TextCommand):
    """Open a preview of this file in the other pane, or close it if it's open."""

    def run(self, edit):
        markdown_view = self.view
        window = markdown_view.window()

        existing = list(find_previews(markdown_view))
        if existing:
            for preview in existing:
                MarkdownLivePreviewListener.phantom_sets.pop(preview.id(), None)
                preview.close()
            stop_scroll_sync(markdown_view.id())
            window.focus_view(markdown_view)
            return

        if window.num_groups() < 2:
            window.set_layout(
                {
                    "cols": [0.0, 0.5, 1.0],
                    "rows": [0.0, 1.0],
                    "cells": [[0, 0, 1, 1], [1, 0, 2, 1]],
                }
            )
        # open the preview in the group next to the markdown view
        group = 1 if window.get_view_index(markdown_view)[0] == 0 else 0
        window.focus_group(group)
        preview = window.new_file()
        preview.set_scratch(True)
        preview.set_name(preview_name(markdown_view))
        settings = preview.settings()
        settings.set(PREVIEW_VIEW_INFO, {"id": markdown_view.id()})
        for key, value in (
            ("gutter", False),
            ("line_numbers", False),
            ("draw_indent_guides", False),
            ("highlight_line", False),
            ("scroll_past_end", False),
        ):
            settings.set(key, value)
        preview.set_read_only(True)

        window.focus_view(markdown_view)
        update_preview(markdown_view)
        start_scroll_sync(markdown_view)

    def is_enabled(self):
        return is_markdown(self.view) and not is_preview(self.view)


def parse_image_resource(text):
    width, height, base64_image = text.splitlines()
    return base64_image, (int(width), int(height))


def load_settings():
    global DELAY, SYNC_SCROLL, FOLLOW_ACTIVE_FILE
    settings = sublime.load_settings("MarkdownLivePreview.sublime-settings")
    DELAY = settings.get("delay_between_updates", 100)
    SYNC_SCROLL = settings.get("sync_scroll", True)
    FOLLOW_ACTIVE_FILE = settings.get("follow_active_file", True)


def plugin_loaded():
    settings = sublime.load_settings("MarkdownLivePreview.sublime-settings")
    settings.clear_on_change(__package__)
    settings.add_on_change(__package__, load_settings)
    load_settings()
    resources["base64_404_image"] = parse_image_resource(get_resource("404.base64"))
    resources["base64_loading_image"] = parse_image_resource(
        get_resource("loading.base64")
    )
    resources["stylesheet"] = get_resource("stylesheet.css")

    # After a plugin reload, re-render previews whose markdown view still exists.
    # Previews restored from a previous session point at view ids that no longer
    # exist: close them.
    for window in sublime.windows():
        markdown_views = {v.id(): v for v in window.views() if not is_preview(v)}
        for view in window.views():
            if not is_preview(view):
                continue
            target = markdown_views.get(view.settings().get(PREVIEW_VIEW_INFO)["id"])
            if target is not None and is_markdown(target):
                update_preview(target)
                start_scroll_sync(target)
            else:
                view.close()


def plugin_unloaded():
    MarkdownLivePreviewListener.phantom_sets.clear()
    synced_views.clear()  # stops the scroll poll loop
    last_scroll.clear()
    last_width.clear()
    sublime.load_settings("MarkdownLivePreview.sublime-settings").clear_on_change(
        __package__
    )
