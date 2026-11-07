"""
Terminology
markdown_view: the view holding the markdown being edited
preview_view: a scratch view, in another group of the same window, that renders
              markdown_view's content as a phantom
"""
import os.path
from functools import partial

import sublime
import sublime_plugin

from .markdown2html import markdown2html

PREVIEW_VIEW_INFO = "preview_view_info"
DELAY = 100  # overwritten by the setting in plugin_loaded
resources = {}


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
        """Closing a markdown file closes its previews."""
        if is_preview(view):
            self.phantom_sets.pop(view.id(), None)
        elif is_markdown(view):
            self.pending.pop(view.id(), None)
            for preview in list(find_previews(view)):
                self.phantom_sets.pop(preview.id(), None)
                preview.close()

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

    for preview in previews:
        html = markdown2html(
            markdown,
            basepath,
            partial(update_preview, view),
            resources,
            preview.viewport_extent()[0],
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
        preview.set_name("Preview: " + os.path.basename(
            markdown_view.file_name() or markdown_view.name() or "untitled"))
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

    def is_enabled(self):
        return is_markdown(self.view) and not is_preview(self.view)


def parse_image_resource(text):
    width, height, base64_image = text.splitlines()
    return base64_image, (int(width), int(height))


def plugin_loaded():
    global DELAY
    DELAY = sublime.load_settings("MarkdownLivePreview.sublime-settings").get(
        "delay_between_updates", 100
    )
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
            else:
                view.close()


def plugin_unloaded():
    MarkdownLivePreviewListener.phantom_sets.clear()
