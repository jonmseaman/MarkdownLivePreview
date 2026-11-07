"""Run with python -m unittest discover -s tests (from the repository root)."""

import html
import importlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
markdown2html = importlib.import_module(ROOT.name + ".markdown2html").markdown2html
sys.path.remove(str(ROOT.parent))

RESOURCES = {
    "stylesheet": "",
    "base64_404_image": ("", (0, 0)),
    "base64_loading_image": ("", (0, 0)),
}


def render(markdown, chars=100):
    """Render markdown in a preview `chars` characters wide (8px per char)."""
    return markdown2html(
        markdown, ".", lambda: None, RESOURCES, chars * 8, char_width=8.0
    )


def grid_lines(rendered):
    """The table grid as plain text lines."""
    body = rendered[rendered.index('<div class="mlp-table">') :]
    body = body[: body.index("</div>")]
    text = re.sub(r"<[^>]+>", "", body.replace("<br />", "\n"))
    return html.unescape(text).replace("\xa0", " ").split("\n")


TABLE = """\
| # | PR | Step | + / − |
|--:|:--:|---|---:|
| 1 | [#5](http://x/5) | Let `OO_SEED` pin the **random** seed | +10 / −1 |
| 22 | [#6](http://x/6) | Add a test safety net: deterministic runs, GUI and component tests | +14088 / −56 |
"""


class TableTests(unittest.TestCase):
    def test_no_table_tags_remain(self):
        rendered = render(TABLE)
        for tag in ("<table", "<tr", "<td", "<th"):
            self.assertNotIn(tag, rendered)

    def test_grid_is_aligned_and_fits(self):
        lines = grid_lines(render(TABLE, chars=60))
        widths = {len(line) for line in lines}
        self.assertEqual(len(widths), 1, "\n".join(lines))
        self.assertLessEqual(widths.pop(), 60 - 3)
        # column separators line up on every line
        positions = {
            tuple(i for i, c in enumerate(line) if c in "│┼┬┴├┤┌┐└┘╞╡╪")
            for line in lines
        }
        self.assertEqual(len(positions), 1, "\n".join(lines))

    def test_natural_widths_when_table_fits(self):
        lines = grid_lines(render(TABLE, chars=200))
        self.assertEqual(len(lines), 7)  # top, header, ═, row, ─, row, bottom
        self.assertIn(
            "Add a test safety net: deterministic runs, GUI and component tests",
            lines[5],
        )

    def test_long_cells_wrap_within_their_column(self):
        lines = grid_lines(render(TABLE, chars=60))
        self.assertGreater(len(lines), 7)
        text = " ".join(line.split("│")[3].strip() for line in lines if "│" in line)
        self.assertIn("deterministic", text)
        self.assertIn("component tests", text)

    def test_alignment(self):
        lines = grid_lines(render(TABLE, chars=200))
        cells = [part for part in lines[3].split("│")[1:-1]]
        self.assertEqual(cells[0], "  1 ")  # right-aligned, padded to "22"
        self.assertEqual(cells[1].strip(), "#5")
        left = len(cells[1]) - len(cells[1].lstrip())
        right = len(cells[1]) - len(cells[1].rstrip())
        self.assertLessEqual(abs(left - right), 1)  # centered
        self.assertTrue(cells[3].endswith("+10 / −1 "))  # right-aligned

    def test_inline_formatting_is_kept(self):
        rendered = render(TABLE)
        self.assertIn('<a href="http://x/5">#5</a>', rendered)
        self.assertIn("<strong>random</strong>", rendered)
        self.assertIn('<span class="mlp-table-code">OO_SEED</span>', rendered)
        self.assertNotIn("<code>OO_SEED</code>", rendered)

    def test_header_is_bold(self):
        self.assertIn("<strong>Step</strong>", render(TABLE))

    def test_words_longer_than_column_are_broken(self):
        markdown = "| a | b |\n|---|---|\n| x | {} |\n".format("y" * 80)
        lines = grid_lines(render(markdown, chars=40))
        self.assertEqual(len({len(line) for line in lines}), 1, "\n".join(lines))
        self.assertEqual(sum(line.count("y") for line in lines), 80)

    def test_html_in_cells_is_escaped(self):
        markdown = "| a |\n|---|\n| 1 &lt; 2 &amp; 3 |\n"
        rendered = render(markdown)
        self.assertIn("1&nbsp;&lt;&nbsp;2&nbsp;&amp;&nbsp;3", rendered.replace("\xa0", "&nbsp;"))

    def test_editor_font_is_used(self):
        rendered = markdown2html(
            TABLE, ".", lambda: None, RESOURCES, 800, char_width=8.0, font_face="Fira Code"
        )
        self.assertIn('font-family: "Fira Code", "Consolas"', rendered)


if __name__ == "__main__":
    unittest.main()
