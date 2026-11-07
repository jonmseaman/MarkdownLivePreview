# MarkdownLivePreview

Preview your markdown as you type, right inside Sublime Text: no browser, no
external tools. The preview opens next to your file, follows the file you're
working on, scrolls along with it, and highlights code like your editor does.

> This is the maintained continuation of
> [math2001/MarkdownLivePreview](https://github.com/math2001/MarkdownLivePreview),
> which has had no releases since 2019 and no longer works on current Sublime
> Text. Thanks to math2001 for the original plugin.

Requires Sublime Text 4. (Sublime Text 3 users get the last original release,
3.0.1, from Package Control.)

## Install

Run `Package Control: Install Package` and pick `MarkdownLivePreview`.

## Usage

Open a markdown file and run `MarkdownLivePreview: Open Preview` from the command
palette (<kbd>ctrl+shift+p</kbd>). Run it again to close the preview.

- **The preview opens next to your file in the same window.**
- **It follows the file you're looking at.** Switch to another markdown tab and
  the preview shows that file; close the previewed file and it moves on to the
  next markdown file (and closes when none are left). Tabs that aren't markdown,
  and files opened in the preview's own pane, leave it alone.
- **It scrolls along with your markdown file.** You can still scroll the
  preview on its own; it catches up the next time the markdown scrolls.
- **Code blocks are highlighted like your editor.** Fenced code blocks with a
  language (```` ```bash ````, ```` ```python ````, ...) are highlighted with
  Sublime's own syntax definitions and your color scheme, through
  [mdpopups](https://github.com/facelessuser/sublime-markdown-popups). Without
  mdpopups, Pygments is used with a dark or light style to match your
  background.
- **Tables render as tables.** Sublime's preview HTML can't lay out tables, so
  they're drawn as a grid in your editor font: columns fit the preview's width,
  long cells wrap inside their column, column alignment (`:--`, `:-:`, `--:`) is
  respected, and links, bold and `code` keep their formatting. Tables reflow
  when you resize the preview.
- **Unsaved files can be previewed.**
- Images (local and remote) are shown, scaled to fit the preview.

### Settings

`MarkdownLivePreview: Open Settings` (command palette, or Preferences > Package
Settings):

```js
{
    // minimum number of milliseconds to wait before updating the preview again
    "delay_between_updates": 100,

    // scroll the preview along with the markdown file
    "sync_scroll": true,

    // when you switch to another markdown file, show it in the preview; when you
    // close the previewed file, show the next markdown file instead
    "follow_active_file": true
}
```

### Key binding

There's no key binding by default. To add one, run `Preferences: Key Bindings`
and add:

```json
{
    "keys": ["alt+m"],
    "command": "open_markdown_preview"
}
```

## Known limitations

- **Numbered lists are rendered as bulleted lists.** Sublime Text's minihtml
  [doesn't support ordered lists](https://github.com/sublimehq/sublime_text/issues/1767).
- **Text in the preview can't be selected or copied.** Sublime Text doesn't
  allow selecting text in HTML it renders.

## Contributing

Issues and pull requests are welcome at
https://github.com/jonmseaman/MarkdownLivePreview.

The tests run outside Sublime Text (against a fake `sublime` module). With
`beautifulsoup4` and `pygments` installed:

```
python -m unittest discover -s tests -v
```

Preview appearance and editor events still need checking in Sublime Text itself.
