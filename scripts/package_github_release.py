from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import zipfile
from pathlib import Path


CHUNK_SIZE = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive(path: Path, expected_root: str) -> None:
    with zipfile.ZipFile(path, mode="r") as archive:
        entries = archive.infolist()
        if not entries:
            raise RuntimeError("Release archive is empty")
        invalid = [
            info.filename
            for info in entries
            if Path(info.filename).is_absolute()
            or ".." in Path(info.filename).parts
            or Path(info.filename).parts[0] != expected_root
        ]
        if invalid:
            raise RuntimeError(f"Unsafe archive path: {invalid[0]}")
        damaged = archive.testzip()
        if damaged:
            raise RuntimeError(f"Damaged archive entry: {damaged}")
    print(f"Verified {len(entries)} archive entries.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create GitHub Release assets from an existing offline build"
    )
    parser.add_argument("release_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--release-notes", type=Path)
    args = parser.parse_args()

    release_directory = args.release_directory.resolve()
    output_directory = args.output_directory.resolve()
    if not release_directory.is_dir():
        raise SystemExit(f"Release directory not found: {release_directory}")

    required = (
        "JARVIS LOCAL.exe",
        "BUILD-INFO.json",
        "SELF-TEST.json",
        "README-OFFLINE.md",
        "THIRD_PARTY_NOTICES.md",
        "KOKORO-MODEL-LICENSE.txt",
        "WHISPER-MODEL-LICENSE.txt",
        "WHISPER-MODEL-MANIFEST.json",
        "PYTHON-PACKAGES.txt",
    )
    missing = [name for name in required if not (release_directory / name).is_file()]
    if missing:
        raise SystemExit(f"Release directory is incomplete: {', '.join(missing)}")

    output_directory.mkdir(parents=True, exist_ok=True)
    archive_path = output_directory / f"{release_directory.name}.zip"
    temporary_path = archive_path.with_suffix(".zip.tmp")
    checksum_path = output_directory / f"{release_directory.name}.sha256"

    if temporary_path.exists():
        temporary_path.unlink()

    files = sorted(path for path in release_directory.rglob("*") if path.is_file())
    print(f"Packing {len(files)} files into {archive_path.name}...", flush=True)
    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
            allowZip64=True,
        ) as archive:
            for index, path in enumerate(files, start=1):
                relative = path.relative_to(release_directory)
                archive_name = Path(release_directory.name) / relative
                archive.write(path, archive_name.as_posix())
                if index % 250 == 0 or index == len(files):
                    print(f"  packed {index}/{len(files)} files", flush=True)
        os.replace(temporary_path, archive_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise

    verify_archive(archive_path, release_directory.name)
    digest = sha256_file(archive_path)
    checksum_path.write_text(
        f"{digest}  {archive_path.name}\n", encoding="ascii", newline="\r\n"
    )

    if args.release_notes:
        notes_path = args.release_notes.resolve()
        if not notes_path.is_file():
            raise SystemExit(f"Release notes not found: {notes_path}")
        shutil.copy2(notes_path, output_directory / "RELEASE_NOTES.md")

    print(f"Archive: {archive_path}")
    print(f"Size: {archive_path.stat().st_size} bytes")
    print(f"SHA-256: {digest}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Packaging cancelled.", file=sys.stderr)
        raise SystemExit(130)
