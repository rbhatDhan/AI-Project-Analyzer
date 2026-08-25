"""
Orchestrates the full "ZIP -> searchable index" flow described in spec
section 23, Phase 2-3. This is the single place that wires ingestion,
analysis, and rag modules together, so api/projects.py stays thin.
"""
from pathlib import Path

from analysis.code_parser import parse_file
from core.workspace import extracted_dir, index_dir, update_project
from ingestion.file_filter import collect_relevant_files
from ingestion.project_detector import detect_project
from ingestion.zip_extractor import validate_and_extract
from rag.chunker import chunk_parsed_file, chunk_unparsed_file
from rag.embeddings import get_embedding_provider
from rag.vector_store import get_vector_store

EMBED_DIM = 3072  # gemini-embedding-001 output size


def run_pipeline(project_id: str, zip_path: Path) -> dict:
    root = extracted_dir(project_id)

    update_project(project_id, status="extracting")
    extract_stats = validate_and_extract(zip_path, root)

    update_project(project_id, status="analyzing")
    files = collect_relevant_files(root)

    update_project(project_id, status="chunking")
    all_chunks = []
    all_imports = []
    parse_errors = []
    for f in files:
        rel_path = str(f.relative_to(root))
        parsed = parse_file(f, rel_path)
        if parsed is not None:
            all_imports.extend(parsed.imports)
            if parsed.parse_error:
                parse_errors.append({"file": rel_path, "error": parsed.parse_error})
            chunks = chunk_parsed_file(project_id, parsed)
            if not chunks and not parsed.parse_error:
                # Parser ran but found no top-level symbols (e.g. a script) -- fall back.
                chunks = chunk_unparsed_file(project_id, f, rel_path, parsed.language)
            all_chunks.extend(chunks)
        else:
            language = f.suffix.lstrip(".") or "text"
            all_chunks.extend(chunk_unparsed_file(project_id, f, rel_path, language))

    # Run structure/framework/library detection after parsing so we can use
    # real import statements, not just manifest files (many small/ML/CV
    # projects ship no requirements.txt at all).
    analysis = detect_project(files, root, all_imports=all_imports)

    update_project(project_id, status="embedding", chunk_count=len(all_chunks))
    embedder = get_embedding_provider()
    store = get_vector_store(index_dir(project_id), dim=EMBED_DIM)

    if all_chunks:
        texts = [c.text for c in all_chunks]
        vectors = embedder.embed_documents(texts)
        ids = [c.chunk_id for c in all_chunks]
        metadatas = [{
            "file_path": c.file_path, "language": c.language, "symbol": c.symbol,
            "type": c.type, "line_start": c.line_start, "line_end": c.line_end,
            "dependencies": c.dependencies, "text": c.text,
        } for c in all_chunks]
        store.add(ids, vectors, metadatas)
        store.save()

    update_project(
        project_id,
        status="ready",
        extract_stats=extract_stats,
        analysis=analysis,
        parse_errors=parse_errors[:50],  # cap what we persist
    )
    return {
        "project_id": project_id,
        "status": "ready",
        "files_analyzed": len(files),
        "chunks_indexed": len(all_chunks),
        "analysis": analysis,
    }
