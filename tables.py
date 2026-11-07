""" Lay out <table> elements for minihtml, which has no table support.

minihtml (the HTML engine used by phantoms) neither implements <table> nor any
CSS width property, so cells can't be sized. Instead, each table is drawn as a
monospace text grid: column widths are computed in characters from the
available width, cell contents are word-wrapped inside their column, and
borders are box-drawing characters. Bold, italics, links and inline code keep
their formatting, since in a monospace font they don't change the width of the
text.

Like markdown2html, this file is independent of Sublime Text.
"""

import html

import bs4

__all__ = ("layout_tables", "TABLE_CLASS")

TABLE_CLASS = "mlp-table"
NBSP = "\xa0"

# tags whose formatting is kept inside cells: name -> attributes to keep
KEPT_TAGS = {
    "a": ("href",),
    "strong": (),
    "b": (),
    "em": (),
    "i": (),
    "code": (),
    "del": (),
    "s": (),
}


def layout_tables(soup, max_chars):
    """Replace every <table> in `soup` with a monospace grid at most
    `max_chars` characters wide (when the columns can fit).

    Grids hold thousands of tags (one per character), which are slow to parse
    into the soup and to serialize again. So each table is replaced by an empty
    placeholder; pass the serialized soup to `insert_tables` with the returned
    grids to fill them in."""
    grids = []
    for table in soup.find_all("table"):
        rows = []  # [(is_header, [cell, ...])]
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"], recursive=False)
            if cells:
                is_header = all(cell.name == "th" for cell in cells)
                rows.append((is_header, [Cell(cell) for cell in cells]))
        if not rows:
            table.decompose()
            continue
        grids.append(render_grid(rows, max_chars))
        table.replace_with(placeholder(len(grids) - 1))
    return grids


def placeholder(index):
    return bs4.BeautifulSoup(
        '<div class="{}" id="mlp-table-{}"></div>'.format(TABLE_CLASS, index),
        "html.parser",
    )


def insert_tables(html_text, grids):
    """Fill the placeholders left by `layout_tables` in serialized HTML."""
    for index, grid in enumerate(grids):
        html_text = html_text.replace(
            '<div class="{}" id="mlp-table-{}"></div>'.format(TABLE_CLASS, index),
            '<div class="{}">{}</div>'.format(TABLE_CLASS, grid),
            1,
        )
    return html_text


class Cell:
    """A table cell as a list of styled characters: [(char, style), ...].

    `style` is a tuple of (tag name, attributes) pairs, outermost first."""

    def __init__(self, element):
        self.align = cell_alignment(element)
        self.header = element.name == "th"
        chars = []
        for text in element.find_all(string=True):
            if isinstance(text, bs4.Comment):
                continue
            style = text_style(text, element)
            chars.extend((char, style) for char in str(text))
        self.chars = collapse_whitespace(chars)

    def __len__(self):
        return len(self.chars)

    def words(self):
        return split_words(self.chars)


def cell_alignment(element):
    align = (element.get("align") or "").lower()
    style = (element.get("style") or "").replace(" ", "").lower()
    for value in ("right", "center", "left"):
        if align == value or "text-align:" + value in style:
            return value
    return "left"


def text_style(text, cell):
    style = []
    parent = text.parent
    while parent is not None and parent is not cell:
        if parent.name in KEPT_TAGS:
            attrs = tuple(
                (name, parent.get(name))
                for name in KEPT_TAGS[parent.name]
                if parent.get(name) is not None
            )
            style.append((parent.name, attrs))
        parent = parent.parent
    return tuple(reversed(style))


def collapse_whitespace(chars):
    out = []
    for char, style in chars:
        if char.isspace():
            if out and out[-1][0] != " ":
                out.append((" ", style))
        else:
            out.append((char, style))
    if out and out[-1][0] == " ":
        out.pop()
    return out


def split_words(chars):
    """Split styled chars on spaces: [(word_chars, space_before), ...]."""
    words = []
    word = []
    space = None
    for item in chars:
        if item[0] == " ":
            if word:
                words.append((word, space))
            word, space = [], item
        else:
            word.append(item)
    if word:
        words.append((word, space))
    return words


def wrap(cell, width):
    """Word-wrap a cell's styled chars into lines at most `width` long."""
    lines = []
    line = []
    for word, space in cell.words():
        if line and len(line) + 1 + len(word) <= width:
            line.append(space)
            line.extend(word)
            continue
        if line:
            lines.append(line)
            line = []
        while len(word) > width:  # hard-break words longer than the column
            lines.append(word[:width])
            word = word[width:]
        line = list(word)
    if line or not lines:
        lines.append(line)
    return lines


def column_widths(rows, available):
    ncols = max(len(cells) for _, cells in rows)
    natural = [1] * ncols
    longest_word = [1] * ncols
    for _, cells in rows:
        for index, cell in enumerate(cells):
            natural[index] = max(natural[index], len(cell))
            for word, _ in cell.words():
                longest_word[index] = max(longest_word[index], len(word))

    if sum(natural) <= available:
        return natural

    # Columns narrower than their fair share keep their natural width; the rest
    # share what's left in proportion to their natural width.
    widths = [None] * ncols
    remaining = available
    flexible = list(range(ncols))
    while flexible:
        share = remaining / len(flexible)
        fitting = [index for index in flexible if natural[index] <= share]
        if not fitting:
            break
        for index in fitting:
            widths[index] = natural[index]
            remaining -= natural[index]
            flexible.remove(index)

    if flexible:
        total = sum(natural[index] for index in flexible)
        for index in flexible:
            # never squeeze a column below a short word's width (or 3 chars)
            minimum = max(3, min(longest_word[index], 12))
            widths[index] = max(minimum, int(remaining * natural[index] / total))
        # hand out the characters lost to rounding, widest columns first
        spare = available - sum(widths)
        for index in sorted(flexible, key=lambda i: -natural[i]):
            if spare <= 0:
                break
            widths[index] += 1
            spare -= 1
    return widths


def render_grid(rows, max_chars):
    ncols = max(len(cells) for _, cells in rows)
    border_chars = 3 * ncols + 1  # "│ " + " │ " * (ncols - 1) + " │"
    widths = column_widths(rows, max(max_chars - border_chars, ncols))

    def rule(left, middle, right, fill="─"):
        return border(left + middle.join(fill * (w + 2) for w in widths) + right)

    lines = [rule("┌", "┬", "┐")]
    for row_index, (is_header, cells) in enumerate(rows):
        if row_index:
            previous_header = rows[row_index - 1][0]
            if previous_header and not is_header:
                lines.append(rule("╞", "╪", "╡", "═"))
            else:
                lines.append(rule("├", "┼", "┤"))
        cells = cells + [None] * (ncols - len(cells))
        wrapped = [
            wrap(cell, widths[index]) if cell is not None else [[]]
            for index, cell in enumerate(cells)
        ]
        height = max(len(cell_lines) for cell_lines in wrapped)
        for line_index in range(height):
            parts = []
            for index, cell in enumerate(cells):
                cell_lines = wrapped[index]
                chars = cell_lines[line_index] if line_index < len(cell_lines) else []
                align = cell.align if cell is not None else "left"
                bold = cell is not None and cell.header
                parts.append(render_cell_line(chars, widths[index], align, bold))
            separator = border(NBSP + "│" + NBSP)
            lines.append(
                border("│" + NBSP) + separator.join(parts) + border(NBSP + "│")
            )
    lines.append(rule("└", "┴", "┘"))
    return "<br />".join(lines)


def glyphs(text, cls=None):
    """Put each character of `text` in its own <span>.

    minihtml positions each run of text separately and rounds its position to
    a whole pixel. If a line is split into runs at different places than the
    line above (a link here, bold text there), the rounding differs and the
    borders wobble from line to line. With one run per character, every line
    is split at exactly the same columns, so every line rounds the same way."""
    open_tag = '<span class="{}">'.format(cls) if cls else "<span>"
    return "".join(
        open_tag + html.escape(char, quote=False) + "</span>" for char in text
    )


def border(text):
    return glyphs(text, TABLE_CLASS + "-border")


def render_cell_line(chars, width, align, bold):
    padding = width - len(chars)
    if align == "right":
        left, right = padding, 0
    elif align == "center":
        left = padding // 2
        right = padding - left
    else:
        left, right = 0, padding
    content = render_styled(chars)
    if bold and content:
        content = "<strong>{}</strong>".format(content)
    return glyphs(NBSP * left) + content + glyphs(NBSP * right)


def render_styled(chars):
    """Render styled chars as HTML, grouping runs that share a style."""
    out = []
    run = []
    run_style = None
    for char, style in chars:
        if style != run_style and run:
            out.append(wrap_style("".join(run), run_style))
            run = []
        run_style = style
        run.append(char)
    if run:
        out.append(wrap_style("".join(run), run_style))
    return "".join(out)


def wrap_style(text, style):
    result = glyphs(text.replace(" ", NBSP))
    for name, attrs in reversed(style):
        if name == "code":
            # <code> has horizontal padding, which would break the alignment
            open_tag = '<span class="{}-code">'.format(TABLE_CLASS)
            close_tag = "</span>"
        else:
            attr_text = "".join(
                ' {}="{}"'.format(key, html.escape(value)) for key, value in attrs
            )
            open_tag = "<{}{}>".format(name, attr_text)
            close_tag = "</{}>".format(name)
        result = open_tag + result + close_tag
    return result
