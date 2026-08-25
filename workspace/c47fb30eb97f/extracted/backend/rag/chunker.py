"""
Turns parsed symbols (from analysis/code_parser.py) into semantic chunks
ready for embedding. Each chunk carries the metadata shape specified in the
project brief (file_path, language, symbol, type, line range, etc).

For files we have no parser for (non-Python, for now), we fall back to a
single whole-file chunk so nothing is silently dropped from retrieval.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from analysis.code_parser import ParsedFile

MAX_WHOLE_FILE_CHARS = 6000  # keep unparsed-file fallback chunks bounded


@dataclass
class Chunk:
    chunk_id: str
    project_id: str
    file_path: str
    language: str
    symbol: str
    type: str          # "class" | "function" | "method" | "file"
    line_start: int
    line_end: int
    text: str           # the actual content to embed (source + light context)
    dependencies: list = field(default_factory=list)


def _make_chunk_id(project_id: str, rel_path: str, symbol: str, line_start: int) -> str:
    return f"{project_id}:{rel_path}:{symbol}:{line_start}"


def chunk_parsed_file(project_id: str, parsed: ParsedFile) -> list:
    chunks = []
    if parsed.parse_error or not parsed.symbols:
        return chunks

    for sym in parsed.symbols:
        symbol_label = f"{sym.parent}.{sym.name}" if sym.parent else sym.name
        header = f"# File: {parsed.file_path}\n# {sym.type}: {symbol_label}\n\n"
        chunks.append(Chunk(
            chunk_id=_make_chunk_id(project_id, parsed.file_path, symbol_label, sym.line_start),
            project_id=project_id,
            file_path=parsed.file_path,
            language=parsed.language,
            symbol=symbol_label,
            type=sym.type,
            line_start=sym.line_start,
            line_end=sym.line_end,
            text=header + sym.source,
            dependencies=sym.calls,
        ))
    return chunks


def chunk_unparsed_file(project_id: str, file_path: Path, rel_path: str, language: str) -> list:
    try:
        text = file_path.read_text(errors="ignore")
    except Exception:
        return []
    if not text.strip():
        return []
    text = text[:MAX_WHOLE_FILE_CHARS]
    return [Chunk(
        chunk_id=_make_chunk_id(project_id, rel_path, "__file__", 1),
        project_id=project_id,
        file_path=rel_path,
        language=language,
        symbol=Path(rel_path).name,
        type="file",
        line_start=1,
        line_end=text.count("\n") + 1,
        text=f"# File: {rel_path}\n\n{text}",
    )]
