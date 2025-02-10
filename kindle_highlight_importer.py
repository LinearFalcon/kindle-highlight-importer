import re
import os
from collections import defaultdict

# Define the input file path
input_file = "./My Clippings.txt"
output_dir = "./My Kindle Clippings"

# Ensure the output directory exists
os.makedirs(output_dir, exist_ok=True)

# Regular expressions to extract book title, location, and highlight
book_pattern = re.compile(r"^(.*?)\s+\((.*?)\)$")
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
    try:
        line = line.strip()
        
        # Identify book title
        if book_pattern.match(line):
            current_book = book_pattern.match(line).group(1)
        
        # Identify location
        elif location_pattern.search(line):
            match = location_pattern.search(line)
            start_loc = int(match.group(1))
            end_loc = int(match.group(2)) if match.group(2) else start_loc
            current_location = (start_loc, end_loc)
        
        # If separator is found, save the previous highlight
        elif line == highlight_separator:
            if current_book and current_location and current_highlight:
                books[current_book].append((current_location, "\n".join(current_highlight)))
            current_highlight = []
        
        # Otherwise, accumulate highlight text
        else:
            current_highlight.append(line)
    except Exception as e:
        print(f"Error processing line: {line}")
        print(e)

# Write to markdown files
for book, highlights in books.items():
    sorted_highlights = sorted(highlights, key=lambda x: x[0])  # Sort by location
    markdown_file = os.path.join(output_dir, f"{book}.md")
    
    with open(markdown_file, "w", encoding="utf-8") as md_file:
        # Repeat the book title as the header if you need
        # md_file.write(f"# {book}\n\n")
        for loc, text in sorted_highlights:
            md_file.write(f"**位置 {loc[0]}-{loc[1]}**\n\n{text}\n\n---\n\n")

print(f"Markdown files have been saved in {output_dir}.")