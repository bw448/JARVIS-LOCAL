from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the original JARVIS LOCAL icon")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--source",
        type=Path,
        help="Optional square PNG rendering used for the Windows icon",
    )
    parser.add_argument(
        "--png-output",
        type=Path,
        help="Also save the transparent high-resolution icon as PNG",
    )
    args = parser.parse_args()

    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    icon_sizes = [
        (16, 16),
        (24, 24),
        (32, 32),
        (48, 48),
        (64, 64),
        (128, 128),
        (256, 256),
    ]

    if args.source:
        if not args.source.is_file():
            raise SystemExit(f"Icon source not found: {args.source}")
        source = Image.open(args.source).convert("RGBA")
        image = ImageOps.fit(
            source,
            (1024, 1024),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        source_alpha = image.getchannel("A")
        if source_alpha.getextrema()[0] == 255:
            # Opaque concept renders need a shaped icon mask. Genuine RGBA
            # artwork keeps its existing alpha exactly as authored.
            alpha = Image.new("L", image.size, 0)
            ImageDraw.Draw(alpha).rounded_rectangle(
                (12, 12, 1012, 1012), radius=184, fill=255
            )
            image.putalpha(alpha.filter(ImageFilter.GaussianBlur(1.2)))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.output, format="ICO", sizes=icon_sizes)
        if args.png_output:
            args.png_output.parent.mkdir(parents=True, exist_ok=True)
            image.save(args.png_output, format="PNG")
        print(f"Icon ready from {args.source}: {args.output}")
        return

    size = 1024
    scale = size / 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    points = [
        (round(x * scale), round(y * scale))
        for x, y in [(13, 32), (20, 32), (24, 23), (31, 43), (37, 26), (41, 32), (51, 32)]
    ]

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    ring_box = tuple(round(value * scale) for value in (6, 6, 58, 58))
    glow_draw.ellipse(
        ring_box,
        outline=(38, 143, 105, 78),
        width=round(4.2 * scale),
    )
    glow_draw.line(
        points,
        fill=(38, 143, 105, 95),
        width=round(5.2 * scale),
        joint="curve",
    )
    glow = glow.filter(ImageFilter.GaussianBlur(round(0.9 * scale)))
    image = Image.alpha_composite(image, glow)
    draw = ImageDraw.Draw(image)

    draw.ellipse(
        ring_box,
        outline=(5, 43, 33, 145),
        width=round(5.4 * scale),
    )
    draw.ellipse(
        ring_box,
        outline=(31, 132, 98, 185),
        width=round(3.4 * scale),
    )
    draw.arc(
        ring_box,
        start=208,
        end=316,
        fill=(139, 219, 190, 95),
        width=max(1, round(0.55 * scale)),
    )
    draw.arc(
        ring_box,
        start=14,
        end=122,
        fill=(139, 219, 190, 95),
        width=max(1, round(0.55 * scale)),
    )
    draw.line(
        points,
        fill=(5, 42, 32, 145),
        width=round(6 * scale),
        joint="curve",
    )
    draw.line(
        points,
        fill=(32, 137, 101, 225),
        width=round(4.2 * scale),
        joint="curve",
    )
    draw.line(
        points,
        fill=(126, 215, 181, 100),
        width=max(1, round(0.65 * scale)),
        joint="curve",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        args.output,
        format="ICO",
        sizes=icon_sizes,
    )
    if args.png_output:
        args.png_output.parent.mkdir(parents=True, exist_ok=True)
        image.save(args.png_output, format="PNG")
    print(f"Icon ready: {args.output}")


if __name__ == "__main__":
    main()
