import re
import os
from collections import defaultdict

# Define the input file path
input_file = "../../Downloads/My Clippings.txt"
output_dir = "../../Downloads/My Kindle Clippings"

# Ensure the output directory exists
os.makedirs(output_dir, exist_ok=True)

# Regular expressions to extract book title, location, and highlight
book_pattern = re.compile(r"^(.*?)\s+\((.*?)\)$")  # Keep full title including parentheses
location_pattern = re.compile(r"位置 #(\d+)-?(\d+)?")
highlight_separator = "=========="

# Data storage
books = defaultdict(list)

with open(input_file, "r", encoding="utf-8") as file:
    lines = file.readlines()

current_book = None
current_location = None
current_highlight = []

for line in lines:
    line = line.strip()
    
    # Identify book title (keeping full content including parentheses)
    match = book_pattern.match(line)
    if match:
        current_book = match.group(1)
    
    # Identify location
    elif location_pattern.search(line):
        match = location_pattern.search(line)
        start_loc = int(match.group(1))
        end_loc = int(match.group(2)) if match.group(2) else start_loc
        current_location = (start_loc, end_loc)
    
    # If separator is found, save the previous highlight
    elif line == highlight_separator:
        if current_book and current_location and current_highlight:
            text = "\n".join(current_highlight)
            
            # Remove exact and partial duplicates
            existing_highlights = books[current_book]
            is_contained = False
            
            # Check if the new text is a subset of any existing text
            for i, (loc, existing_text) in enumerate(existing_highlights):
                # Debug partially duplicated highlights
                # if '杨朱的两个基本观念' in text and '朱的两个基本观念' in existing_text:
                #     breakpoint()
                if text.strip() in existing_text.strip():
                    is_contained = True
                    break
                elif existing_text.strip() in text.strip():
                    existing_highlights[i] = (loc, text)
                    is_contained = True
                    break
            
            if not is_contained:
                books[current_book].append((current_location, text))
        
        current_highlight = []
    
    # Otherwise, accumulate highlight text
    else:
        current_highlight.append(line)

# Write to markdown files
for book, highlights in books.items():
    sorted_highlights = sorted(highlights, key=lambda x: x[0])  # Sort by location
    markdown_file = os.path.join(output_dir, f"{book}.md")
    
    with open(markdown_file, "w", encoding="utf-8") as md_file:
        for loc, text in sorted_highlights:
            md_file.write(f"**位置 {loc[0]}-{loc[1]}**\n\n{text}\n\n---\n\n")

print(f"Markdown files have been saved in {output_dir}.")
