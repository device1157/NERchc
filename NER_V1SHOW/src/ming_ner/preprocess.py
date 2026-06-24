"""Text loading and cleaning for Ming Shilu source files."""

from __future__ import annotations

import html
import re
from pathlib import Path

from .schema import Document


HTML_TAG_RE = re.compile(r"</?[^>]+>")
SPACE_RE = re.compile(r"[ \t\r\f\v\u00a0\u3000]+")
BLANK_LINE_RE = re.compile(r"\n{2,}")
WENXUE_BANNER_RE = re.compile(r"更多经典著作，请登录文学100网（http://www\.wenxue100\.com）\s*")


def read_text_lossless(path: Path) -> str:
    """Read UTF-8 text, repairing common mojibake if a file was saved incorrectly."""

    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")

    # Some shells display UTF-8 as Latin-1 mojibake, but the files themselves are UTF-8.
    # This branch repairs genuinely mojibaked content if encountered in future imports.
    if "æ" in text[:1000] and "明" not in text[:1000]:
        try:
            repaired = text.encode("latin1").decode("utf-8")
            if "明" in repaired[:1000]:
                return repaired
        except UnicodeError:
            pass
    return text


def clean_text(text: str) -> str:
    """Normalize HTML residue, whitespace, and common source banners."""

    text = html.unescape(text)
    text = WENXUE_BANNER_RE.sub("", text)
    text = text.replace("\ufeff", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = HTML_TAG_RE.sub("\n", text)
    text = text.replace("△", "\n○")
    text = SPACE_RE.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = BLANK_LINE_RE.sub("\n", text)
    return text.strip()


def infer_title(path: Path, text: str) -> str:
    """Infer a readable title from file name or source header."""

    match = re.search(r"书名[:：]\s*(.+)", text)
    if match:
        return match.group(1).strip()
    return path.stem


def load_document(path: Path, sample_chars: int | None = None) -> Document:
    raw = read_text_lossless(path)
    cleaned = clean_text(raw)
    title = infer_title(path, cleaned)
    if sample_chars and sample_chars > 0:
        cleaned = cleaned[:sample_chars]
    return Document(
        doc_id=path.stem,
        title=title,
        source_path=str(path),
        text=cleaned,
    )


def load_documents(input_dir: Path, sample_chars: int | None = None) -> list[Document]:
    paths = sorted(input_dir.glob("*.txt"))
    return [load_document(path, sample_chars=sample_chars) for path in paths]


def split_entries(text: str) -> list[tuple[int, int, str]]:
    """Split a document into rough chronicle entries while preserving offsets."""

    starts = [m.start() for m in re.finditer(r"(?m)^○", text)]
    if not starts:
        return [(0, len(text), text)]
    entries: list[tuple[int, int, str]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        entries.append((start, end, text[start:end]))
    return entries
