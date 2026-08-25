"""
Extracts an uploaded ZIP into an isolated project workspace.

Security notes (see spec section 24):
- Rejects entries that would escape the target dir (zip-slip / path traversal).
- Enforces a max uncompressed size and max file count BEFORE writing anything,
  to avoid zip-bomb style resource exhaustion.
- Never executes anything in the archive; this module only reads bytes and
  writes files to disk.
"""
import zipfile
from pathlib import Path

from core.config import settings


class ZipValidationError(Exception):
    pass


def _is_within_directory(directory: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False


def validate_and_extract(zip_path: Path, dest_dir: Path) -> dict:
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not zipfile.is_zipfile(zip_path):
        raise ZipValidationError("Uploaded file is not a valid ZIP archive.")

    max_bytes = settings.MAX_ZIP_SIZE_MB * 1024 * 1024
    max_file_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024

    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = zf.infolist()

        if len(infos) > settings.MAX_EXTRACTED_FILES:
            raise ZipValidationError(
                f"Archive contains too many files ({len(infos)} > {settings.MAX_EXTRACTED_FILES})."
            )

        total_uncompressed = sum(i.file_size for i in infos)
        if total_uncompressed > max_bytes:
            raise ZipValidationError(
                f"Uncompressed archive too large ({total_uncompressed / 1e6:.1f}MB > "
                f"{settings.MAX_ZIP_SIZE_MB}MB)."
            )

        extracted_files = 0
        for info in infos:
            # Skip directory entries; we recreate dirs as needed below.
            if info.is_dir():
                continue

            member_path = dest_dir / info.filename
            if not _is_within_directory(dest_dir, member_path):
                raise ZipValidationError(
                    f"Blocked path-traversal entry in archive: {info.filename!r}"
                )

            if info.file_size > max_file_bytes:
                # Skip oversized individual files rather than failing the whole upload.
                continue

            member_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, open(member_path, "wb") as dst:
                dst.write(src.read())
            extracted_files += 1

    return {"extracted_files": extracted_files, "total_uncompressed_bytes": total_uncompressed}
