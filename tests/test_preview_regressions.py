"""Run with python -m unittest discover -s tests (requires Pygments)."""

import ast
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "preview_markdown2", ROOT / "lib/markdown2.py"
)
markdown2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(markdown2)


class HighlightingTests(unittest.TestCase):
    def test_fenced_code_preserves_highlighting(self):
        import pygments  # Fail explicitly if the optional highlighter is missing.

        for language, source in (
            ("python", "print(123)"),
            ("bash", "echo hello"),
            ("json", '{"ok": true}'),
            ("sql", "SELECT 1;"),
        ):
            with self.subTest(language=language):
                html = markdown2.Markdown(extras=["fenced-code-blocks"]).convert(
                    "```{}\n{}\n```".format(language, source)
                )
                self.assertIn("<code>", html)
                self.assertIn("<span", html)

    def test_legacy_formatter_call_with_outfile(self):
        from unittest.mock import patch
        from pygments.lexers import PythonLexer

        def legacy_highlight(code, lexer, formatter):
            return "".join(
                text for _, text in formatter.wrap(iter([(1, "highlighted")]), None)
            )

        with patch("pygments.highlight", side_effect=legacy_highlight):
            html = markdown2.Markdown()._color_with_pygments("x", PythonLexer())
        self.assertIn("<code>highlighted</code>", html)


class ClosePreviewTests(unittest.TestCase):
    def setUp(self):
        # Load the actual listener without requiring a running Sublime host.
        tree = ast.parse((ROOT / "MarkdownLivePreview.py").read_text())
        listener = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "MarkdownLivePreviewListener"
        )
        tree.body = [listener]
        self.original_window = Mock()
        self.original_window.id.return_value = 42
        namespace = {
            "sublime_plugin": types.SimpleNamespace(EventListener=object),
            "sublime": types.SimpleNamespace(windows=lambda: [self.original_window]),
            "MARKDOWN_VIEW_INFOS": "markdown_view_infos",
        }
        exec(compile(tree, str(ROOT / "MarkdownLivePreview.py"), "exec"), namespace)
        self.listener = namespace["MarkdownLivePreviewListener"]()
        self.view = Mock()
        self.view.id.return_value = 14
        self.view.settings.return_value.get.return_value = {"original_window_id": 42}
        self.view.file_name.return_value = "/tmp/example.md"
        self.listener.on_pre_close(self.view)

    def test_close_without_phantom_set_still_restores_file(self):
        self.listener.on_close(self.view)
        self.view.window.return_value.run_command.assert_called_once_with(
            "close_window"
        )
        self.original_window.open_file.assert_called_once_with("/tmp/example.md")

    def test_close_removes_only_its_own_phantom_set(self):
        other = object()
        self.listener.phantom_sets.update({14: object(), 15: other})
        self.listener.on_close(self.view)
        self.assertEqual(self.listener.phantom_sets, {15: other})
        self.original_window.open_file.assert_called_once_with("/tmp/example.md")


if __name__ == "__main__":
    unittest.main()
