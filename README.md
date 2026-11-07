# MarkdownLivePreview

A simple plugin to preview your markdown as you type right in Sublime Text.

> **This is an enhanced fork of
> [math2001/MarkdownLivePreview](https://github.com/math2001/MarkdownLivePreview)**
> updated for Sublime Text 4 (build 4213+, Python 3.14 plugin host).

## What's different in this fork

- **Works on current Sublime Text.** Declares all the libraries it needs
  (`beautifulsoup4`, `soupsieve`, `typing-extensions`, `pygments`) so Package
  Control installs them for the Python 3.14 plugin host, and opts into that host
  with `.python-version`.
- **Preview opens next to your file in the same window**, instead of moving the
  file into a new window (upstream PR #109). Running the command again closes the
  preview.
- **Code blocks render correctly, with syntax highlighting** (upstream PRs #126
  and #128).
- **Unsaved buffers can be previewed.**
- **The last keystroke is always rendered.** Upstream's throttle could skip the
  final update when typing quickly.
- The preview tab is read-only, with no gutter or line numbers, and is named
  after the file it previews.
- Leftover previews from a previous session are closed on startup.
- `MarkdownLivePreview: Open Settings` is in the command palette and in
  Preferences > Package Settings.

## How to install

Install from this fork with Package Control: run `Package Control: Add
Repository`, paste `https://github.com/jonmseaman/MarkdownLivePreview`, then run
`Package Control: Install Package` and pick `MarkdownLivePreview`.

Or clone it straight into your `Packages` folder:

```
git clone https://github.com/jonmseaman/MarkdownLivePreview "%APPDATA%\Sublime Text\Packages\MarkdownLivePreview"
```

## Setting a keybinding

To open the preview, you can search up in the command palette
(<kbd>ctrl+shift+p</kbd>) `MarkdownLivePreview: Open Preview` (run it again to
close the preview). But if you
prefer to have a shortcut, add this to your keybindings file:

```json
{
    "keys": ["alt+m"],
    "command": "open_markdown_preview"
}
```

## How to contribute

If you know what feature you want to implement, or what bug you wanna fix, then
go ahead and hack! Maybe raise an issue before hand so that we can talk about
it if it's a big feature.

But if you wanna contribute just to say thanks, and don't really know what you
could be working on, then there are a bunch of `FIXME`s all over this package.
Just pick one and fix it :-)

```
$ git clone https://github.com/math2001/MarkdownLivePreview
$ cd MarkdownLivePreview
$ grep -R FIXME
```

### Hack it!

1. Fork this repo
2. Make your own branch (the name of the branch should be the feature you are
   implementing eg. `improve-tables`, `fix-crash-on-multiple-preview`
3. All your code should be formated by black.
4. Send a PR!

### Regression tests

With Pygments installed, run `python -m unittest discover -s tests -v`.
The tests cover fenced-code highlighting without a running Sublime Text
instance. Preview appearance and editor events still need to be
checked in Sublime Text.

### Known limitations

#### Numbered lists are rendered as unordered lists

```md
1. first
2. second
3. third
```

will be previewed the exact same way as

```md
- first
- second
- third
```

The issue comes from [Sublime Text's minihtml](https://www.sublimetext.com/docs/3/minihtml.html) which [doesn't support ordered lists](https://github.com/sublimehq/sublime_text/issues/1767). If you think feel like implementing a workaround, feel free to contribute, but it's not something I'm planning on doing. It isn't a critical feature, and support should come with time...
