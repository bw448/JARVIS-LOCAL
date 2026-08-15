from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Preload a faster-whisper model")
    parser.add_argument("--model", default="small")
    args = parser.parse_args()

    from faster_whisper import WhisperModel

    WhisperModel(args.model, device="cpu", compute_type="int8")
    print(f"faster-whisper {args.model} model is ready.")


if __name__ == "__main__":
    main()
