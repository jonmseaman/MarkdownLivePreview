"""Run with python -m unittest discover -s tests (from the repository root)."""

import importlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
module = importlib.import_module(ROOT.name + ".markdown2html")
sys.path.remove(str(ROOT.parent))
markdown2html = module.markdown2html
pygments_highlight = module.pygments_highlight

RESOURCES = {
    "stylesheet": "",
    "base64_404_image": ("", (0, 0)),
    "base64_loading_image": ("", (0, 0)),
}

BASH = "```bash\ngit difftool --dir-diff a b\ngit difftool --dir-diff b c\n```\n"


def render(markdown, **kwargs):
    return markdown2html(markdown, ".", lambda: None, RESOURCES, 800, **kwargs)


def body(rendered):
    return rendered[rendered.index("</style>") :]


class CodeBlockTests(unittest.TestCase):
    def test_one_line_break_per_line(self):
        for kwargs in ({}, {"highlighter": lambda s, l: pygments_highlight(s, l, True)}):
            with self.subTest(**{k: True for k in kwargs}):
                html = body(render(BASH, **kwargs))
                self.assertEqual(html.count("<br />"), 1, html)
                self.assertNotIn("\n</code>", html)

    def test_no_pygments_stylesheet(self):
        # minihtml can't apply it, and its "line-height: 125%" spaced lines out
        rendered = render(BASH)
        self.assertNotIn("125%", rendered)
        self.assertNotIn(".codehilite", rendered)

    def test_highlighter_gets_source_and_language(self):
        calls = []

        def highlighter(source, language):
            calls.append((source, language))
            return '<div class="highlight"><pre>HL</pre></div>'

        html = body(render(BASH + "\n```\nplain <text>\n```\n", highlighter=highlighter))
        self.assertEqual(
            calls,
            [
                ("git difftool --dir-diff a b\ngit difftool --dir-diff b c", "bash"),
                ("plain <text>", None),
            ],
        )
        self.assertEqual(html.count('<div class="highlight"><pre>HL</pre></div>'), 2)

    def test_highlighter_none_means_plain(self):
        html = body(render("```python\nx  =  1\n```\n", highlighter=lambda s, l: None))
        self.assertIn("x\xa0\xa0=\xa0\xa01", html)
        self.assertNotIn("<span", html)

    def test_pygments_fallback_inlines_colors(self):
        html = pygments_highlight("def f():\n    return 1", "python", dark=True)
        self.assertIn('style="color:', html)
        self.assertNotIn("class=", html)
        self.assertEqual(html.count("<br/>"), 1)
        self.assertIn("\xa0\xa0\xa0\xa0", html)

    def test_pygments_fallback_unknown_language(self):
        self.assertIsNone(pygments_highlight("x", "no-such-language", dark=True))
        self.assertIsNone(pygments_highlight("x", None, dark=True))

    def test_pygments_dark_and_light_differ(self):
        dark = pygments_highlight("def f(): pass", "python", dark=True)
        light = pygments_highlight("def f(): pass", "python", dark=False)
        self.assertNotEqual(dark, light)

    def test_table_font_scale_and_line_height(self):
        rendered = render("| a |\n|---|\n| b |\n", font_scale=0.97)
        css = re.search(r"\.mlp-table \{(.*?)\}", rendered, re.S).group(1)
        self.assertIn("font-size: 0.9700rem;", css)
        self.assertIn("line-height: 1.17em;", css)


if __name__ == "__main__":
    unittest.main()
