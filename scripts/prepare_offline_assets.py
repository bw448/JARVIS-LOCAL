from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


WHISPER_REPOSITORY = "Systran/faster-whisper-small"
WHISPER_REVISION = "536b0662742c02347bc0e980a01041f333bce120"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare pinned offline model assets")
    parser.add_argument("--whisper-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    from huggingface_hub import snapshot_download

    destination = args.whisper_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {WHISPER_REPOSITORY}@{WHISPER_REVISION}...")
    snapshot_download(
        repo_id=WHISPER_REPOSITORY,
        revision=WHISPER_REVISION,
        local_dir=destination,
        allow_patterns=[
            ".gitattributes",
            "README.md",
            "config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.txt",
        ],
    )

    required = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
    missing = [name for name in required if not (destination / name).is_file()]
    if missing:
        raise SystemExit(f"Whisper snapshot is incomplete: {', '.join(missing)}")
    if (destination / "model.bin").stat().st_size < 400_000_000:
        raise SystemExit("Whisper model.bin is unexpectedly small")

    cache_dir = destination / ".cache"
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(
            {
                "repository": WHISPER_REPOSITORY,
                "revision": WHISPER_REVISION,
                "files": {
                    path.name: path.stat().st_size
                    for path in sorted(destination.iterdir())
                    if path.is_file()
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Whisper snapshot ready: {destination}")


if __name__ == "__main__":
    main()
