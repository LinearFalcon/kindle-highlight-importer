#!/usr/bin/env python3
"""Convert a Kindle "My Clippings.txt" into one tidy Markdown note per book.

    python kindle_highlight_importer.py                      # ~/Downloads/My Clippings.txt
    python kindle_highlight_importer.py "My Clippings.txt" -o ~/notes/kindle
    python kindle_highlight_importer.py --dry-run -v         # parse and report only

Reads English and Chinese Kindle metadata lines and any book text (Chinese, English, mixed).
Highlights, notes and bookmarks are all recognised. Python 3.8+, standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, NamedTuple, Optional, Set, Tuple
from urllib.parse import quote

DEFAULT_INPUT = Path.home() / "Downloads" / "My Clippings.txt"
OUTPUT_DIRNAME = "My Kindle Clippings"  # created next to the input file unless -o is given
INDEX_STEM = "_Index"
UNKNOWN_AUTHOR = "Unknown"


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class Clip:
    """One entry of My Clippings.txt."""

    kind: str  # "highlight" | "note" | "bookmark"
    title: str
    author: str
    text: str
    page: Optional[str] = None  # kept as text: Kindle also writes "xii" and "12-13"
    loc_start: Optional[int] = None
    loc_end: Optional[int] = None
    added: Optional[datetime] = None
    added_raw: str = ""
    order: int = 0  # position in the file; the file is chronological
    notes: List["Clip"] = field(default_factory=list)  # notes attached to this highlight
    key: str = field(init=False, default="")  # whitespace-normalised text, for comparisons

    def __post_init__(self) -> None:
        self.key = " ".join(self.text.split())


@dataclass
class Book:
    title: str
    author: str
    items: List[Clip]  # highlights (notes attached) + stand-alone notes, in reading order
    duplicates_removed: int = 0

    @property
    def n_highlights(self) -> int:
        return sum(1 for c in self.items if c.kind == "highlight")

    @property
    def n_notes(self) -> int:
        return sum(len(c.notes) if c.kind == "highlight" else 1 for c in self.items)

    @property
    def first_added(self) -> Optional[datetime]:
        dates = [c.added for c in self.items if c.added]
        return min(dates) if dates else None

    @property
    def last_added(self) -> Optional[datetime]:
        dates = [c.added for c in self.items if c.added]
        return max(dates) if dates else None


@dataclass
class ParseResult:
    clips: List[Clip] = field(default_factory=list)
    entries: int = 0  # entries found in the file, parsed or not
    skipped: Counter = field(default_factory=Counter)  # e.g. {"bookmarks": 3}
    warnings: List[str] = field(default_factory=list)  # entries we could not understand


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
_SEPARATOR = re.compile(r"^={10}[ \t]*$", re.M)

# "Title (Author)". The LAST bracketed group on the line is the author, so titles with their own
# brackets ("Deep Work (2nd ed.) (Cal Newport)") still split correctly. Full-width （） are common
# in Chinese titles.
_TITLE_LINE = re.compile(r"^(?P<title>.*\S)\s*[(（](?P<author>[^()（）]*)[)）]$")

# Metadata line, for example:
#   - Your Highlight on page 15 | Location 224-228 | Added on Saturday, March 29, 2025 6:07:12 PM
#   - Your Note at location 224 | Added on Saturday, 29 March 2025 18:07:12
#   - 您在第 15 页（位置 #224-228）的标注 | 添加于 2025年3月29日星期六 下午6:07:12
# Each field is found independently, so a missing page/location or different wording does not break
# parsing. To support another Kindle language, add its words here.
_KIND_WORDS = (
    ("bookmark", re.compile(r"bookmark|书签|書籤", re.I)),
    ("note", re.compile(r"note|笔记|筆記", re.I)),
    ("highlight", re.compile(r"highlight|标注|標註|标记|標記", re.I)),
)
_PAGE = re.compile(r"\bpage\s+(?P<en>[^\s|,;]+)|第\s*(?P<zh>[^\s页頁|]+?)\s*[页頁]", re.I)
_LOCATION = re.compile(r"(?:\blocation|位置)\s*#?\s*(?P<start>\d+)(?:\s*[-–—]\s*(?P<end>\d+))?", re.I)
_ADDED = re.compile(r"(?:added on|添加于|添加於|新增於)\s*(?P<date>.+)$", re.I)

_TIME = r"(?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?"
_DATE_PATTERNS = (
    # Saturday, March 29, 2025 6:07:12 PM
    re.compile(rf"(?P<mon>[a-z]+)\.?\s+(?P<d>\d{{1,2}}),?\s+(?P<y>\d{{4}}),?\s+{_TIME}\s*(?P<ap>[ap]\.?m\.?)?", re.I),
    # Saturday, 29 March 2025 18:07:12
    re.compile(rf"(?P<d>\d{{1,2}})\s+(?P<mon>[a-z]+)\.?,?\s+(?P<y>\d{{4}}),?\s+{_TIME}\s*(?P<ap>[ap]\.?m\.?)?", re.I),
    # 2025年3月29日星期六 下午6:07:12
    re.compile(
        rf"(?P<y>\d{{4}})\s*年\s*(?P<mon>\d{{1,2}})\s*月\s*(?P<d>\d{{1,2}})\s*日\D*?"
        rf"(?P<zh>上午|下午|凌晨|早上|清晨|中午|晚上|傍晚)?\s*{_TIME}"
    ),
)
_MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
_AM_WORDS = ("上午", "凌晨", "早上", "清晨")
_PM_WORDS = ("下午", "中午", "晚上", "傍晚")


class Meta(NamedTuple):
    kind: str
    page: Optional[str]
    loc_start: Optional[int]
    loc_end: Optional[int]
    added_raw: str


def parse_added(raw: str) -> Optional[datetime]:
    """Parse the 'Added on' timestamp (US/UK English or Chinese). None if unrecognised."""
    for pattern in _DATE_PATTERNS:
        m = pattern.search(raw)
        if not m:
            continue
        g = m.groupdict()
        month = int(g["mon"]) if g["mon"].isdigit() else _MONTHS.get(g["mon"][:3].lower())
        if month is None:
            continue
        hour = int(g["h"])
        ampm = (g.get("ap") or "").lower()
        zh = g.get("zh") or ""
        if ampm.startswith("p") or zh in _PM_WORDS:
            hour = hour % 12 + 12
        elif ampm.startswith("a") or zh in _AM_WORDS:
            hour = hour % 12
        try:
            return datetime(int(g["y"]), month, int(g["d"]), hour, int(g["mi"]), int(g["s"] or 0))
        except ValueError:
            continue
    return None


def parse_meta(line: str) -> Optional[Meta]:
    """Parse the second line of an entry. Returns None if it is not a metadata line."""
    line = line.strip()
    if not line.startswith("-"):
        return None
    head = line.split("|", 1)[0]  # the kind of entry is named before the first "|"
    kind = next((name for name, rx in _KIND_WORDS if rx.search(head)), None)
    page, loc, added = _PAGE.search(line), _LOCATION.search(line), _ADDED.search(line)
    if kind is None or not (page or loc):
        return None
    start = int(loc["start"]) if loc else None
    end = int(loc["end"]) if loc and loc["end"] else start
    if start is not None and end is not None and end < start:
        end = start
    return Meta(
        kind=kind,
        page=(page["en"] or page["zh"]) if page else None,
        loc_start=start,
        loc_end=end,
        added_raw=added["date"].strip() if added else "",
    )


def split_title(line: str) -> Tuple[str, str]:
    """'Title (Author)' -> ('Title', 'Author'). Lines without an author keep the whole line as title."""
    m = _TITLE_LINE.match(line)
    if m and m["author"].strip():
        return m["title"].strip(), m["author"].strip()
    return line, UNKNOWN_AUTHOR


def parse_clippings(raw: str) -> ParseResult:
    """Parse the whole file. Entries are split on the '==========' lines, then read by position
    (title line, metadata line, text), so highlighted text can never be mistaken for a title."""
    text = raw.replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")  # BOMs, CRLF
    result = ParseResult()
    for block in _SEPARATOR.split(text):
        lines = [ln.strip() for ln in block.split("\n")]
        while lines and not lines[0]:
            lines.pop(0)
        if not lines:
            continue
        result.entries += 1
        title, author = split_title(lines[0])
        meta = parse_meta(lines[1]) if len(lines) > 1 else None
        if meta is None:
            result.warnings.append(
                f"entry {result.entries} ({title[:40]!r}): unrecognised metadata line {lines[1:2]!r}"
            )
            continue
        body = "\n".join(ln for ln in lines[2:] if ln)
        if meta.kind == "bookmark":
            result.skipped["bookmarks"] += 1
        elif not body:
            result.skipped["empty entries"] += 1
        elif "clipping limit" in body.lower():  # "<You have reached the clipping limit for this item>"
            result.skipped["clip-limit markers"] += 1
        else:
            result.clips.append(
                Clip(
                    kind=meta.kind,
                    title=title,
                    author=author,
                    text=body,
                    page=meta.page,
                    loc_start=meta.loc_start,
                    loc_end=meta.loc_end,
                    added=parse_added(meta.added_raw),
                    added_raw=meta.added_raw,
                    order=len(result.clips),
                )
            )
    return result


# --------------------------------------------------------------------------- #
# Turning clips into books
# --------------------------------------------------------------------------- #
_FAR = 10**12  # sorts "unknown" after everything else


def _overlaps(a: Clip, b: Clip) -> bool:
    if a.loc_start is not None and b.loc_start is not None:
        return a.loc_start <= (b.loc_end or b.loc_start) and b.loc_start <= (a.loc_end or a.loc_start)
    return a.page == b.page  # e.g. PDFs: no locations, only pages


def dedupe_highlights(clips: List[Clip]) -> List[Clip]:
    """Kindle appends a new entry each time a highlight is adjusted, so the file holds earlier,
    shorter revisions next to the final one. An entry is dropped when its location range overlaps
    another entry and its text is contained in that entry's text; the longest version survives.
    Identical text at *different* locations is kept (two separate highlights)."""
    kept: List[Clip] = []
    for clip in clips:  # file order == chronological
        if any(_overlaps(old, clip) and clip.key in old.key for old in kept):
            continue  # duplicate of, or a shorter revision of, something already kept
        kept = [old for old in kept if not (_overlaps(old, clip) and old.key in clip.key)]
        kept.append(clip)
    return kept


def dedupe_notes(notes: List[Clip]) -> List[Clip]:
    """Editing a note appends a new entry too. A location holds one note, so the latest wins."""
    latest: "OrderedDict[tuple, Clip]" = OrderedDict()
    for note in notes:
        ident = (note.loc_start, note.page) if note.loc_start is not None else (None, note.page, note.key)
        latest[ident] = note
    return list(latest.values())


def attach_notes(highlights: List[Clip], notes: List[Clip]) -> List[Clip]:
    """Attach each note to the highlight whose location range contains it. Returns the notes that
    belong to no highlight."""
    standalone: List[Clip] = []
    for note in notes:
        target = None
        if note.loc_start is not None:
            for h in highlights:
                if h.loc_start is not None and h.loc_start <= note.loc_start <= (h.loc_end or h.loc_start):
                    target = h
                    if h.loc_end == note.loc_start:  # Kindle puts a note at its highlight's end
                        break
        if target is not None:
            target.notes.append(note)
        else:
            standalone.append(note)
    return standalone


def _page_number(page: Optional[str]) -> int:
    m = re.match(r"\d+", page or "")
    return int(m.group()) if m else _FAR


def _reading_order(clip: Clip) -> Tuple[int, int, int]:
    loc = clip.loc_start if clip.loc_start is not None else _FAR
    return loc, _page_number(clip.page), clip.order


def _book_key(clip: Clip) -> Tuple[str, str]:
    return " ".join(clip.title.split()).casefold(), " ".join(clip.author.split()).casefold()


def build_books(clips: Iterable[Clip]) -> List[Book]:
    grouped: "OrderedDict[Tuple[str, str], List[Clip]]" = OrderedDict()
    for clip in clips:
        grouped.setdefault(_book_key(clip), []).append(clip)

    books = []
    for group in grouped.values():
        highlights = [c for c in group if c.kind == "highlight"]
        notes = [c for c in group if c.kind == "note"]
        kept = dedupe_highlights(highlights)
        standalone = attach_notes(kept, dedupe_notes(notes))
        items = sorted(kept + standalone, key=_reading_order)
        books.append(Book(group[0].title, group[0].author, items, len(highlights) - len(kept)))

    books.sort(key=lambda b: b.title)
    books.sort(key=lambda b: b.last_added or datetime.min, reverse=True)  # most recently read first
    return books


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #
def _escape(paragraph: str) -> str:
    """Stop highlighted text from turning into Markdown structure (or vanishing as HTML)."""
    paragraph = paragraph.replace("<", "\\<")
    m = re.match(r"^(\d+)([.)])(\s.*)?$", paragraph)  # "1. foo" would become a list
    if m:
        return f"{m.group(1)}\\{m.group(2)}{m.group(3) or ''}"
    if re.match(r"^[#>*+\-](\s|$)", paragraph):  # heading, quote, bullet
        return "\\" + paragraph
    return paragraph


def _yaml(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid YAML string


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _reference(clip: Clip) -> str:
    parts = []
    if clip.page:
        parts.append(f"Page {clip.page}")
    if clip.loc_start is not None:
        same = clip.loc_end in (None, clip.loc_start)
        parts.append(f"Location {clip.loc_start}" if same else f"Location {clip.loc_start}–{clip.loc_end}")
    if clip.added:
        parts.append(f"{clip.added:%Y-%m-%d}")
    elif clip.added_raw:
        parts.append(clip.added_raw)
    return " · ".join(parts)


def _render_clip(clip: Clip) -> List[str]:
    paragraphs = [_escape(p) for p in clip.text.split("\n")]
    if clip.kind == "note":  # a note that sits on no highlight
        paragraphs[0] = f"**Note:** {paragraphs[0]}"
    lines: List[str] = []
    for i, paragraph in enumerate(paragraphs):
        if i:
            lines.append(">")
        lines.append(f"> {paragraph}")
    reference = _reference(clip)
    if reference:
        lines += [">", f"> — *{reference}*"]
    lines.append("")
    for note in clip.notes:
        first, *rest = [_escape(p) for p in note.text.split("\n")]
        lines.append(f"**Note:** {first}")
        for paragraph in rest:
            lines += ["", paragraph]
        lines.append("")
    return lines


def render_book(book: Book, frontmatter: bool = True) -> str:
    first, last = book.first_added, book.last_added
    out: List[str] = []
    if frontmatter:
        out += ["---", f"title: {_yaml(book.title)}", f"author: {_yaml(book.author)}", "source: Kindle"]
        out.append(f"highlights: {book.n_highlights}")
        if book.n_notes:
            out.append(f"notes: {book.n_notes}")
        if first and last:
            out += [f"first_highlighted: {first:%Y-%m-%d}", f"last_highlighted: {last:%Y-%m-%d}"]
        out += ["tags: [kindle]", "---", ""]
    summary = [f"*{book.author}*", _plural(book.n_highlights, "highlight")]
    if book.n_notes:
        summary.append(_plural(book.n_notes, "note"))
    if last:
        summary.append(f"last highlighted {last:%Y-%m-%d}")
    out += [f"# {book.title}", "", " · ".join(summary), "", "---", ""]
    for clip in book.items:
        out += _render_clip(clip)
    return "\n".join(out).rstrip() + "\n"


def _cell(text: str) -> str:
    """Escape text for a Markdown table cell / link label."""
    return text.replace("|", "\\|").replace("[", "\\[").replace("]", "\\]")


def render_index(entries: List[Tuple[Book, str]]) -> str:
    total_h = sum(b.n_highlights for b, _ in entries)
    total_n = sum(b.n_notes for b, _ in entries)
    with_notes = total_n > 0
    summary = [_plural(len(entries), "book"), _plural(total_h, "highlight")]
    if with_notes:
        summary.append(_plural(total_n, "note"))
    header = ["Book", "Author", "Highlights"] + (["Notes"] if with_notes else []) + ["Last highlighted"]
    align = ["---", "---", "--:"] + (["--:"] if with_notes else []) + ["---"]
    out = ["# Kindle Highlights", "", " · ".join(summary), "", f"| {' | '.join(header)} |", f"|{'|'.join(align)}|"]
    for book, stem in entries:
        row = [f"[{_cell(book.title)}]({quote(stem)}.md)", _cell(book.author), str(book.n_highlights)]
        if with_notes:
            row.append(str(book.n_notes))
        row.append(f"{book.last_added:%Y-%m-%d}" if book.last_added else "")
        out.append(f"| {' | '.join(row)} |")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- #
# Writing files
# --------------------------------------------------------------------------- #
_FS_REPLACE = {":": " -", "/": "-", "\\": "-", "|": "-", '"': "'"}
_FS_DROP = re.compile(r"[<>?*\x00-\x1f]")


def safe_filename(name: str, max_bytes: int = 180) -> str:
    """Make a filename that is valid on Windows/macOS/Linux. The limit is in bytes (not
    characters) because filesystems cap bytes and each Chinese character takes three."""
    for bad, good in _FS_REPLACE.items():
        name = name.replace(bad, good)
    name = " ".join(_FS_DROP.sub("", name).split()).strip(" .")
    while len(name.encode("utf-8")) > max_bytes:
        name = name[:-1]
    return name.strip(" .") or "Untitled"


def unique_stem(book: Book, used: Set[str]) -> str:
    """Filename (without .md). Two different books with one title get the author appended."""
    stem = safe_filename(book.title)
    if stem.lower() in used:
        stem = safe_filename(f"{book.title} ({book.author})")
    base, n = stem, 2
    while stem.lower() in used:
        stem = f"{base} ({n})"
        n += 1
    used.add(stem.lower())
    return stem


def _write(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content)


def write_books(books: List[Book], out_dir: Path, frontmatter: bool = True, index: bool = True) -> List[Tuple[Book, str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    used: Set[str] = {INDEX_STEM.lower()} if index else set()
    written = []
    for book in books:
        stem = unique_stem(book, used)
        _write(out_dir / f"{stem}.md", render_book(book, frontmatter))
        written.append((book, stem))
    if index:
        _write(out_dir / f"{INDEX_STEM}.md", render_index(written))
    return written


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #
def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert Kindle 'My Clippings.txt' into one Markdown file per book.")
    p.add_argument("input", nargs="?", type=Path, default=DEFAULT_INPUT, help=f"clippings file (default: {DEFAULT_INPUT})")
    p.add_argument("-o", "--output-dir", type=Path, help=f"output folder (default: '{OUTPUT_DIRNAME}' next to the input file)")
    p.add_argument("--no-frontmatter", action="store_true", help="omit the YAML properties block at the top of each note")
    p.add_argument("--no-index", action="store_true", help=f"do not write {INDEX_STEM}.md")
    p.add_argument("-n", "--dry-run", action="store_true", help="parse and report, but write nothing")
    p.add_argument("-v", "--verbose", action="store_true", help="list every entry that could not be parsed")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    try:  # never crash on a console that cannot print Chinese titles
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if not args.input.is_file():
        print(f"error: clippings file not found: {args.input}", file=sys.stderr)
        return 1
    try:
        raw = args.input.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        print(f"error: {args.input} is not UTF-8 text", file=sys.stderr)
        return 1

    result = parse_clippings(raw)
    books = build_books(result.clips)
    out_dir = args.output_dir or args.input.parent / OUTPUT_DIRNAME

    n_highlights = sum(b.n_highlights for b in books)
    n_notes = sum(b.n_notes for b in books)
    merged = sum(b.duplicates_removed for b in books)
    print(f"Read {args.input.name}: {result.entries} entries")
    print(f"  highlights: {n_highlights} kept, {merged} earlier revisions/duplicates merged")
    print(f"  notes: {n_notes}")
    if result.skipped:
        print("  skipped: " + ", ".join(f"{what} {n}" for what, n in result.skipped.items()))
    if result.warnings:
        print(f"  WARNING: {len(result.warnings)} entries could not be parsed" + ("" if args.verbose else " (run with -v to list them)"))
        if args.verbose:
            for warning in result.warnings:
                print(f"    - {warning}")

    if args.dry_run:
        entries = [(b, "") for b in books]
    else:
        entries = write_books(books, out_dir, frontmatter=not args.no_frontmatter, index=not args.no_index)
    verb = "Would write" if args.dry_run else "Wrote"
    print(f"{verb} {_plural(len(books), 'book')} to {out_dir}")
    for book, _ in entries:
        print(f"  {book.n_highlights:>4}  {book.title} — {book.author}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
