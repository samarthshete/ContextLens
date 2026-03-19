"""Document parser for PDF, TXT, and Markdown."""

from pathlib import Path

from pypdf import PdfReader


SUPPORTED_TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


def parse_document(file_path: str | Path) -> str:
    """Extract raw text from a supported document."""
    path = Path(file_path)

    if not path.exists():
        raise ValueError(f"File does not exist: {path}")

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _parse_pdf(path)
    if suffix in SUPPORTED_TEXT_SUFFIXES:
        return _parse_text(path)

    raise ValueError(f"Unsupported file type: {suffix}")


def _parse_pdf(path: Path) -> str:
    """Extract text from a PDF file."""
    try:
        reader = PdfReader(path)
    except Exception as exc:
        raise ValueError(f"Failed to open PDF: {exc}") from exc

    parts: list[str] = []

    try:
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                parts.append(text.strip())
    except Exception as exc:
        raise ValueError(f"Failed to read PDF content: {exc}") from exc

    raw_text = "\n\n".join(parts).strip()
    if not raw_text:
        raise ValueError("No extractable text found in PDF.")

    return raw_text


def _parse_text(path: Path) -> str:
    """Read plain text or markdown file."""
    try:
        raw_text = path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception as exc:
        raise ValueError(f"Failed to read text file: {exc}") from exc

    if not raw_text:
        raise ValueError("Uploaded text file is empty.")

    return raw_text