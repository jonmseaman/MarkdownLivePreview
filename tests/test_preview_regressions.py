"""Run with python -m unittest discover -s tests (requires Pygments)."""

import importlib.util
from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
