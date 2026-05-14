"""
file_viewer.py — File viewer plugin for Project Iceberg.

Reads common file formats and returns their content as readable text
for the chat interface.

Supported formats:
  Excel  (.xlsx, .xls)  — openpyxl (already installed)
  CSV    (.csv)          — stdlib csv
  JSON   (.json, .jsonl) — stdlib json
  Text   (.txt, .md, .py, .js, .ts, .log, .ini, .cfg, .yaml, .toml, .xml, .html)
  Word   (.docx)         — python-docx (already installed)
  PDF    (.pdf)          — pdfplumber (already installed)

Tools:
  view_file         — Read and display a file's content
  list_file_sheets  — List sheets in an Excel workbook
  file_summary      — One-line summary of a file (size, type, row count)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Format constants
# ---------------------------------------------------------------------------

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".log",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".sh",
    ".bat",
    ".ps1",
    ".ahk",
    ".sql",
    ".env",
    ".gitignore",
}

_MAX_ROWS_DISPLAY = 200  # Cap table rows shown in chat
_MAX_TEXT_CHARS = 8000  # Cap plain text chars shown in chat
_MAX_COL_WIDTH = 30  # Max chars per cell in text table


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _ext(path: Path) -> str:
    return path.suffix.lower()


# ---------------------------------------------------------------------------
# Format readers
# ---------------------------------------------------------------------------


def _read_excel(path: Path, sheet_name: str = "") -> str:
    """Read an Excel file and return a text table."""
    try:
        import openpyxl
    except ImportError:
        return "❌ openpyxl not installed. Run: pip install openpyxl"

    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as e:
        return f"❌ Could not open '{path.name}': {e}"

    sheet_names = wb.sheetnames

    if sheet_name:
        if sheet_name not in sheet_names:
            return (
                f"Sheet '{sheet_name}' not found.\n" f"Available sheets: {', '.join(sheet_names)}"
            )
        ws = wb[sheet_name]
    else:
        ws = wb.active

    active_sheet = ws.title

    # Read rows
    rows = []
    for row in ws.iter_rows(values_only=True):
        rows.append([str(cell) if cell is not None else "" for cell in row])

    wb.close()

    if not rows:
        return f"Sheet '{active_sheet}' is empty."

    # Trim trailing all-empty rows
    while rows and all(c == "" for c in rows[-1]):
        rows.pop()

    # Find max col count
    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]  # pad short rows

    # Calculate column widths (cap at _MAX_COL_WIDTH)
    col_widths = [
        min(_MAX_COL_WIDTH, max(len(rows[i][c]) for i in range(min(len(rows), 100))))
        for c in range(max_cols)
    ]

    def _fmt_row(row: list[str]) -> str:
        return " | ".join(cell[: col_widths[i]].ljust(col_widths[i]) for i, cell in enumerate(row))

    header = _fmt_row(rows[0])
    separator = "-+-".join("-" * w for w in col_widths)
    data_rows = [_fmt_row(r) for r in rows[1 : _MAX_ROWS_DISPLAY + 1]]

    lines = [
        f"Excel: {path.name}  |  Sheet: {active_sheet}",
        f"Sheets: {', '.join(sheet_names)}  |  Rows: {len(rows)-1}  |  Cols: {max_cols}",
        "",
        header,
        separator,
    ]
    lines.extend(data_rows)

    if len(rows) - 1 > _MAX_ROWS_DISPLAY:
        lines.append(f"\n… {len(rows) - 1 - _MAX_ROWS_DISPLAY} more rows not shown")

    return "\n".join(lines)


def _read_csv(path: Path) -> str:
    """Read a CSV file and return a text table."""
    try:
        with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
            # Sniff delimiter
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel  # type: ignore

            reader = csv.reader(f, dialect)
            rows = [row for row in reader]
    except Exception as e:
        return f"❌ Could not read CSV '{path.name}': {e}"

    if not rows:
        return f"'{path.name}' is empty."

    # Trim trailing empty rows
    while rows and all(c.strip() == "" for c in rows[-1]):
        rows.pop()

    max_cols = max(len(r) for r in rows)
    rows = [r + [""] * (max_cols - len(r)) for r in rows]

    col_widths = [
        min(_MAX_COL_WIDTH, max(len(rows[i][c]) for i in range(min(len(rows), 100))))
        for c in range(max_cols)
    ]

    def _fmt_row(row: list[str]) -> str:
        return " | ".join(cell[: col_widths[i]].ljust(col_widths[i]) for i, cell in enumerate(row))

    header = _fmt_row(rows[0])
    separator = "-+-".join("-" * w for w in col_widths)
    data_rows = [_fmt_row(r) for r in rows[1 : _MAX_ROWS_DISPLAY + 1]]

    lines = [
        f"CSV: {path.name}  |  Rows: {len(rows)-1}  |  Cols: {max_cols}",
        "",
        header,
        separator,
    ]
    lines.extend(data_rows)
    if len(rows) - 1 > _MAX_ROWS_DISPLAY:
        lines.append(f"\n… {len(rows) - 1 - _MAX_ROWS_DISPLAY} more rows not shown")

    return "\n".join(lines)


def _read_json(path: Path) -> str:
    """Read a JSON or JSONL file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"❌ Could not read '{path.name}': {e}"

    # JSONL: one JSON object per line
    if path.suffix.lower() == ".jsonl":
        lines_raw = [l for l in text.splitlines() if l.strip()]
        parsed = []
        for line in lines_raw[:50]:
            try:
                parsed.append(json.dumps(json.loads(line), indent=2))
            except Exception:
                parsed.append(line)
        header = f"JSONL: {path.name}  |  {len(lines_raw)} records"
        if len(lines_raw) > 50:
            header += "  (showing first 50)"
        return header + "\n\n" + "\n---\n".join(parsed)

    # Regular JSON
    try:
        data = json.loads(text)
        formatted = json.dumps(data, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        formatted = text  # Show raw if invalid

    lines = [f"JSON: {path.name}  |  {_fmt_bytes(len(text))}"]
    if len(formatted) > _MAX_TEXT_CHARS:
        lines.append(formatted[:_MAX_TEXT_CHARS])
        lines.append(f"\n… truncated ({len(formatted) - _MAX_TEXT_CHARS} more chars)")
    else:
        lines.append(formatted)
    return "\n".join(lines)


def _read_text(path: Path) -> str:
    """Read a plain text / code file."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"❌ Could not read '{path.name}': {e}"

    line_count = text.count("\n")
    header = f"{path.suffix.upper() or 'TEXT'}: {path.name}  |  {line_count} lines  |  {_fmt_bytes(len(text))}"

    if len(text) > _MAX_TEXT_CHARS:
        return (
            header
            + "\n\n"
            + text[:_MAX_TEXT_CHARS]
            + f"\n\n… truncated ({len(text) - _MAX_TEXT_CHARS} more chars)"
        )
    return header + "\n\n" + text


def _read_docx(path: Path) -> str:
    """Read a Word .docx file."""
    try:
        from docx import Document
    except ImportError:
        return "❌ python-docx not installed. Run: pip install python-docx"

    try:
        doc = Document(path)
    except Exception as e:
        return f"❌ Could not open '{path.name}': {e}"

    sections: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name if para.style else ""
        if "Heading" in style:
            level = style.replace("Heading", "").strip()
            prefix = "#" * (int(level) if level.isdigit() else 1)
            sections.append(f"{prefix} {text}")
        else:
            sections.append(text)

    # Tables
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            sections.append(" | ".join(cells))

    content = "\n".join(sections)
    para_count = len(doc.paragraphs)

    header = f"DOCX: {path.name}  |  {para_count} paragraphs  |  {_fmt_bytes(path.stat().st_size)}"

    if len(content) > _MAX_TEXT_CHARS:
        return header + "\n\n" + content[:_MAX_TEXT_CHARS] + "\n\n… truncated"
    return header + "\n\n" + content


def _read_pdf(path: Path) -> str:
    """Read a PDF file."""
    try:
        import pdfplumber
    except ImportError:
        return "❌ pdfplumber not installed. Run: pip install pdfplumber"

    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            pages_text: list[str] = []
            total_chars = 0

            for i, page in enumerate(pdf.pages):
                if total_chars > _MAX_TEXT_CHARS:
                    pages_text.append(f"\n[… truncated at page {i+1} of {page_count}]")
                    break
                text = page.extract_text() or ""
                pages_text.append(f"--- Page {i+1} ---\n{text}")
                total_chars += len(text)

    except Exception as e:
        return f"❌ Could not read PDF '{path.name}': {e}"

    header = f"PDF: {path.name}  |  {page_count} pages  |  {_fmt_bytes(path.stat().st_size)}"
    return header + "\n\n" + "\n\n".join(pages_text)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _dispatch(path: Path, sheet: str = "") -> str:
    ext = _ext(path)
    if ext in (".xlsx", ".xls", ".xlsm", ".ods"):
        return _read_excel(path, sheet)
    elif ext == ".csv":
        return _read_csv(path)
    elif ext in (".json", ".jsonl"):
        return _read_json(path)
    elif ext in (".docx",):
        return _read_docx(path)
    elif ext == ".pdf":
        return _read_pdf(path)
    elif ext in _TEXT_EXTENSIONS or not ext:
        return _read_text(path)
    else:
        # Try as text anyway
        return _read_text(path)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def view_file(
    file_path: str,
    sheet: str = "",
    max_rows: int = 200,
) -> str:
    """
    Read and display the contents of a file.

    Supports: Excel (.xlsx/.xls), CSV, JSON, JSONL, plain text, code files,
    Word documents (.docx), and PDF files.

    Args:
        file_path: Full path to the file to view.
        sheet:     For Excel files — sheet name to view (default = first/active sheet).
        max_rows:  For tabular files — max rows to display (default 200).
    """
    path = Path(file_path)

    if not path.exists():
        # Try with common locations
        alternatives = [
            Path.home() / "Desktop" / file_path,
            Path.home() / "Documents" / file_path,
        ]
        for alt in alternatives:
            if alt.exists():
                path = alt
                break
        else:
            return f"File not found: '{file_path}'"

    if not path.is_file():
        return f"'{file_path}' is a directory, not a file. Use list_dir or scan_directory."

    size = path.stat().st_size
    if size > 50 * 1024 * 1024:  # 50 MB
        return (
            f"File is too large to display ({_fmt_bytes(size)}). "
            "Use a file path filter or open it in a dedicated app."
        )

    global _MAX_ROWS_DISPLAY
    _MAX_ROWS_DISPLAY = max(10, min(1000, max_rows))

    return _dispatch(path, sheet)


def list_file_sheets(file_path: str) -> str:
    """
    List all sheets in an Excel workbook.

    Args:
        file_path: Path to the .xlsx or .xls file.
    """
    path = Path(file_path)
    if not path.exists():
        return f"File not found: '{file_path}'"

    try:
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        sheets = wb.sheetnames
        wb.close()
    except ImportError:
        return "❌ openpyxl not installed. Run: pip install openpyxl"
    except Exception as e:
        return f"❌ Could not open workbook: {e}"

    lines = [
        f"Excel workbook: {path.name}",
        f"Sheets ({len(sheets)}):",
    ]
    for i, name in enumerate(sheets):
        lines.append(f"  [{i}] {name}")

    lines.append(f'\nUse view_file("{file_path}", sheet="<name>") to view a specific sheet.')
    return "\n".join(lines)


def file_summary(file_path: str) -> str:
    """
    Show a one-line summary of a file: type, size, and row/page count.

    Args:
        file_path: Path to the file.
    """
    path = Path(file_path)
    if not path.exists():
        return f"File not found: '{file_path}'"

    ext = _ext(path)
    size = path.stat().st_size
    info_parts = [f"{path.name}", f"  Type: {ext or 'unknown'}", f"  Size: {_fmt_bytes(size)}"]

    try:
        if ext in (".xlsx", ".xls", ".xlsm"):
            import openpyxl

            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            info_parts.append(f"  Sheets: {len(wb.sheetnames)} ({', '.join(wb.sheetnames[:5])})")
            ws = wb.active
            row_count = ws.max_row or 0
            info_parts.append(f"  Rows: ~{row_count}")
            wb.close()
        elif ext == ".csv":
            with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
                row_count = sum(1 for _ in f)
            info_parts.append(f"  Rows: {row_count}")
        elif ext in (".json", ".jsonl"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if ext == ".jsonl":
                info_parts.append(f"  Records: {text.count(chr(10))}")
            else:
                info_parts.append(f"  Chars: {len(text)}")
        elif ext == ".pdf":
            import pdfplumber

            with pdfplumber.open(path) as pdf:
                info_parts.append(f"  Pages: {len(pdf.pages)}")
        elif ext == ".docx":
            from docx import Document

            doc = Document(path)
            info_parts.append(f"  Paragraphs: {len(doc.paragraphs)}")
        else:
            line_count = path.read_text(encoding="utf-8", errors="replace").count("\n")
            info_parts.append(f"  Lines: {line_count}")
    except Exception as e:
        info_parts.append(f"  (could not read details: {e})")

    return "\n".join(info_parts)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register(registry) -> None:
    registry.register(
        "view_file",
        view_file,
        description=(
            "Read and display the contents of a file. "
            "Supports Excel (.xlsx/.xls), CSV, JSON, JSONL, plain text, code files, "
            "Word documents (.docx), and PDF. "
            "For Excel, specify sheet= to view a specific sheet."
        ),
        category="file",
        args=[
            {"name": "file_path", "required": True, "description": "Full path to the file to view"},
            {
                "name": "sheet",
                "required": False,
                "description": "Excel sheet name to view (default = first/active sheet)",
            },
            {
                "name": "max_rows",
                "required": False,
                "description": "Max rows to display for tabular files (default 200)",
            },
        ],
    )

    registry.register(
        "list_file_sheets",
        list_file_sheets,
        description="List all sheets in an Excel workbook (.xlsx/.xls).",
        category="file",
        args=[
            {"name": "file_path", "required": True, "description": "Path to the Excel workbook"},
        ],
    )

    registry.register(
        "file_summary",
        file_summary,
        description=(
            "Show a quick summary of a file: type, size, row/page/sheet count "
            "without reading the full content."
        ),
        category="file",
        args=[
            {"name": "file_path", "required": True, "description": "Path to the file to summarize"},
        ],
    )
