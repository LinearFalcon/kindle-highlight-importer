# Kindle Highlight Importer

Parses your Kindle `My Clippings.txt` file and exports each book's highlights into a clean, well-structured Markdown file.

## Features

- One `.md` file per book, sorted by location
- Captures page number, location range, and date added for each highlight
- Deduplicates highlights — when Kindle saves both a shorter and a longer version of the same passage, only the longer one is kept
- Strips the BOM character (`﻿`) that Kindle prepends to clipping files
- Sanitizes filenames so special characters don't cause issues

## Output Format

Each book gets a file like `Book Title.md`:

```markdown
# Book Title

**Author:** Author Name
**Highlights:** 42

---

**Page 15  ·  Location 224–228**

*Saturday, March 29, 2025 6:07:12 PM*

Highlight text goes here...

---
```

## Usage

1. Connect your Kindle and copy `My Clippings.txt` from the `documents/` folder to your computer.

2. Edit the paths at the top of the script:

```python
input_file = "path/to/My Clippings.txt"
output_dir = "path/to/output/folder"
```

3. Run:

```bash
python kindle_highlight_importer.py
```

The script will print a summary of all books and highlight counts when done.

## Requirements

Python 3.6+, standard library only — no dependencies to install.

## Notes

- The script handles **English-language Kindle clippings** (i.e. `My Clippings.txt` files where the metadata line reads `- Your Highlight on page X | Location Y-Z | Added on ...`). If your Kindle is set to a different language, the metadata line format will differ and the location pattern may need updating.
- Highlights from **borrowed books** (Kindle Unlimited, library loans) are often stripped from `My Clippings.txt` by Amazon. If a book you read has no highlights in the output, this is likely why.
- The deduplication logic handles partial overlaps: if highlight A is a substring of highlight B, only B is kept. If a shorter old highlight is later extended by re-highlighting, the longer version replaces it.
