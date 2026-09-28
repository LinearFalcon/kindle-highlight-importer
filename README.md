# Kindle Highlight Importer

Turns a Kindle `My Clippings.txt` into one clean Markdown note per book, plus an index note.
Works with English and Chinese book text, highlights, notes and bookmarks. Python 3.8+, standard library only.

## Quick start

```bash
# defaults: ~/Downloads/My Clippings.txt  ->  ~/Downloads/My Kindle Clippings/
python kindle_highlight_importer.py

# explicit paths
python kindle_highlight_importer.py "path/to/My Clippings.txt" -o "path/to/notes/kindle"

# check what would happen without writing anything
python kindle_highlight_importer.py --dry-run -v
```

Copy `My Clippings.txt` from the `documents/` folder of the Kindle (connected over USB). Re-run the script any time
with a newer copy; it regenerates every note.

| Option | Effect |
| --- | --- |
| `input` | Clippings file (default `~/Downloads/My Clippings.txt`) |
| `-o`, `--output-dir` | Output folder (default: `My Kindle Clippings` next to the input file) |
| `--no-frontmatter` | Omit the YAML properties block at the top of each note |
| `--no-index` | Do not write `_Index.md` |
| `-n`, `--dry-run` | Parse and report only |
| `-v`, `--verbose` | List every entry that could not be parsed |

## Output

Each book becomes `Title.md` (`Title (Author).md` if two different books share a title):

```markdown
---
title: "Why Nations Fail"
author: "Daron Acemoglu"
source: Kindle
highlights: 7
first_highlighted: 2025-10-08
last_highlighted: 2025-10-12
tags: [kindle]
---

# Why Nations Fail

*Daron Acemoglu* · 7 highlights · last highlighted 2025-10-12

---

> The highlighted passage goes here. A multi-paragraph highlight keeps its paragraphs.
>
> — *Page 82 · Location 1256–1257 · 2025-10-11*

**Note:** your own note on that highlight, if you wrote one.
```

`_Index.md` lists every book (most recently highlighted first) with links, highlight counts and last-highlighted date.
The YAML block is what Obsidian and similar tools read as properties; use `--no-frontmatter` if yours does not.

## What the script does with the file

- **Splits the file into entries first** (on the `==========` lines), then reads each by position: title line, metadata
  line, text. Highlighted text can therefore never be mistaken for a book title.
- **Merges revisions.** Kindle appends a new entry every time you adjust a highlight, so the file holds shorter
  earlier versions next to the final one. An entry is dropped when its location range overlaps another entry and its
  text is contained in it; the longest version is kept. The same words highlighted at two different places are both kept.
- **Attaches notes** to the highlight whose location range contains them (edited notes: the latest wins). A note on
  no highlight is printed on its own.
- **Skips, and tells you about it:** bookmarks, empty entries and the `<You have reached the clipping limit…>`
  placeholder are counted in the summary. Any entry whose metadata line cannot be read is reported as a warning
  (`-v` shows which) instead of being dropped silently.
- **Books are identified by title + author**, so two books with the same title stay separate.
- Handles the UTF-8 BOM, CRLF line endings, `Title (Author)` lines whose title contains its own brackets, full-width
  brackets `（）`, page ranges (`page 12-13`), roman-numeral pages, and entries with no page or no location (PDFs).
- Filenames are made safe for Windows/macOS/Linux and capped in bytes (a Chinese character takes three).

## Supported Kindle formats

| Metadata line | Status |
| --- | --- |
| English: `- Your Highlight on page 15 \| Location 224-228 \| Added on Saturday, March 29, 2025 6:07:12 PM` | Verified against a real export |
| English variants: no page, `at location`, UK dates (`29 March 2025 18:07:12`) | Covered by unit tests, not verified on a device |
| Chinese (Simplified): `- 您在第 15 页（位置 #224-228）的标注 \| 添加于 2025年3月29日星期六 下午6:07:12`, plus 笔记 / 书签 | Covered by unit tests, not verified on a device |
| Chinese (Traditional): 標註 / 筆記 / 書籤 wording | Best effort, untested |

Kindle's UI language decides the metadata wording; the language of the book does not. To add another language, extend the
patterns at the top of `kindle_highlight_importer.py` (`_KIND_WORDS`, `_PAGE`, `_LOCATION`, `_ADDED`, `_DATE_PATTERNS`),
and add a test for one real entry.

## Limits of `My Clippings.txt`

- It is an append-only log. Highlights you later delete or shorten on the Kindle still appear in the file, and the
  script cannot tell they are gone. Overlapping revisions are merged; deleted highlights cannot be detected.
- For books whose publisher sets a clipping limit (commonly around 10% of the book), Kindle writes a placeholder
  instead of the text once you pass it. Those highlights still exist on the device but cannot be recovered from this file.
- Only Kindle e-readers write this file; highlights made in the Kindle phone/tablet apps are not in it (use
  `read.amazon.com/notebook` for those).
- Output notes are overwritten on every run. Keep your own writing in separate notes that link to these.

## Tests

```bash
python -m unittest -v
```

The tests use small inline fixtures. When a new format breaks the parser, paste a few anonymised entries into a test,
watch it fail, then fix the patterns.
