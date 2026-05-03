import re
import os
from collections import defaultdict

# Define the input file path
input_file = "../../Downloads/My Clippings.txt"
output_dir = "../../Downloads/My Kindle Clippings"

# Ensure the output directory exists
os.makedirs(output_dir, exist_ok=True)

# Regular expressions
book_pattern = re.compile(r"^(.*?)\s+\((.*?)\)$")

# FIX: was r"位置 #(\d+)-?(\d+)?" (Chinese Kindle format) — updated to English format
metadata_pattern = re.compile(
    r"- Your Highlight on page (\d+) \| Location (\d+)-?(\d+)? \| Added on (.+)"
)

highlight_separator = "=========="

# Data storage
books = defaultdict(list)

with open(input_file, "r", encoding="utf-8") as file:
    lines = file.readlines()

current_book = None
current_author = None
current_page = None
current_location = None
current_date = None
current_highlight = []

for line in lines:
    line = line.strip()

    # --- Separator: save accumulated highlight ---
    if line == highlight_separator:
        if current_book and current_location and current_highlight:
            text = "\n".join(l for l in current_highlight if l)  # drop blank lines

            existing = books[current_book]
            is_contained = False

            for i, entry in enumerate(existing):
                if text.strip() in entry["text"].strip():
                    is_contained = True
                    break
                elif entry["text"].strip() in text.strip():
                    # Replace shorter existing entry with longer new one
                    existing[i] = {**entry, "text": text}
                    is_contained = True
                    break

            if not is_contained:
                books[current_book].append({
                    "page": current_page,
                    "location": current_location,
                    "date": current_date,
                    "text": text,
                    "author": current_author,
                })

        current_highlight = []
        continue

    # --- Book title line ---
    book_match = book_pattern.match(line)
    if book_match:
        # FIX: strip BOM (﻿ / U+FEFF) that Kindle prepends to the first entry of each file
        current_book = book_match.group(1).lstrip("\ufeff").strip()
        current_author = book_match.group(2).strip()
        current_page = None
        current_location = None
        current_date = None
        current_highlight = []
        continue

    # --- Metadata line (page / location / date) ---
    meta_match = metadata_pattern.search(line)
    if meta_match:
        current_page = int(meta_match.group(1))
        start_loc = int(meta_match.group(2))
        end_loc = int(meta_match.group(3)) if meta_match.group(3) else start_loc
        current_location = (start_loc, end_loc)
        current_date = meta_match.group(4).strip()
        continue

    # --- Accumulate highlight text (skip blank lines at top) ---
    if line or current_highlight:
        current_highlight.append(line)


def safe_filename(name: str) -> str:
    """Replace characters that are invalid in filenames."""
    return re.sub(r'[\\/*?:"<>|]', "_", name)


# Write to markdown files
for book, highlights in books.items():
    sorted_highlights = sorted(highlights, key=lambda x: x["location"][0])
    author = highlights[0]["author"] if highlights else "Unknown"

    markdown_file = os.path.join(output_dir, f"{safe_filename(book)}.md")

    with open(markdown_file, "w", encoding="utf-8") as md_file:
        # Book header
        md_file.write(f"# {book}\n\n")
        md_file.write(f"**Author:** {author}  \n")
        md_file.write(f"**Highlights:** {len(sorted_highlights)}\n\n")
        md_file.write("---\n\n")

        for h in sorted_highlights:
            loc = h["location"]
            loc_str = f"{loc[0]}–{loc[1]}" if loc[0] != loc[1] else str(loc[0])
            page_str = f"Page {h['page']}" if h["page"] else ""
            date_str = f"*{h['date']}*" if h["date"] else ""

            # Compact meta line: Page 15 · Location 224–228
            meta_parts = [p for p in [page_str, f"Location {loc_str}"] if p]
            md_file.write(f"**{'  ·  '.join(meta_parts)}**\n\n")
            if date_str:
                md_file.write(f"{date_str}\n\n")
            md_file.write(f"{h['text']}\n\n---\n\n")

print(f"Markdown files saved to: {output_dir}")
print(f"Books processed: {len(books)}")
for book, highlights in books.items():
    print(f"  • {book} — {len(highlights)} highlights")
