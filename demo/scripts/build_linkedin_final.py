"""Reframe approved promotional footage; retain its cards, captions and exact audio."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import enhance_video as video
from build_linkedin_video import validate

DEMO = Path(__file__).resolve().parents[1]
ASSETS = DEMO / "assets"


def main() -> None:
    ffmpeg, ffprobe = video.tool("ffmpeg"), video.tool("ffprobe")
    if " drawtext " not in video.run(ffmpeg, "-hide_banner", "-filters"):
        full = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
        if not full.is_file() or "FFMPEG" in os.environ:
            raise ValueError("Set FFMPEG to a build with drawtext support.")
        ffmpeg = str(full)
    original = ASSETS / "skout-linkedin-40s.mp4"
    if not original.is_file():
        raise ValueError(f"Missing approved promotional source: {original}")
    metadata = video.probe(ffprobe, original)
    duration = float(metadata["format"]["duration"])
    if abs(duration - 42) > 0.01:
        raise ValueError("Expected approved 42-second edit; recheck timing before reframing.")
    regions = json.loads((DEMO / "linkedin/mobile-framing.json").read_text())
    filters = ["[0:v]split=2[base][pixels]"]
    # Source copies provide authentic detail panes; no text is reconstructed.
    needed = sum(1 + bool(region.get("detail")) for region in regions)
    outputs = "".join(f"[p{i}]" for i in range(needed))
    filters.append(f"[pixels]split={needed}{outputs}")
    previous, branch = "base", 0
    for number, region in enumerate(regions):
        if not 9 <= region["start"] < region["end"] <= 35:
            raise ValueError("Only approved terminal intervals may be reframed.")
        when = f"gte(t,{region['start']})*lt(t,{region['end']})"
        zoom = region.get("zoom")
        if zoom:
            x, y, w, h, ow, oh = (
                zoom[k] for k in ("x", "y", "width", "height", "out_width", "out_height")
            )
        else:
            x, y, w, h, ow, oh = (
                0,
                260,
                1080,
                region["context_height"],
                1080,
                region["context_height"],
            )
        if not (0 <= x < x + w <= 1080 and 260 <= y < y + h <= 1010 and oh + 260 <= 1130):
            raise ValueError("Framing would crop out of source or cover the captions.")
        # Clear only the original terminal viewport, leaving headline/captions untouched.
        clean = f"clean{number}"
        filters.append(
            f"[{previous}]drawbox=x=0:y=260:w=1080:h=750:color=0x202323:t=fill:"
            f"enable='{when}'[{clean}]"
        )
        panel = f"panel{number}"
        filters.append(f"[p{branch}]crop={w}:{h}:{x}:{y},scale={ow}:{oh}:flags=lanczos[{panel}]")
        branch += 1
        current = f"context{number}"
        filters.append(f"[{clean}][{panel}]overlay=x=0:y=260:enable='{when}'[{current}]")
        detail = region.get("detail")
        if detail:
            dx, dy, dw, dh, dow, doh, out_x, out_y = (
                detail[k]
                for k in ("x", "y", "width", "height", "out_width", "out_height", "out_x", "out_y")
            )
            if not (
                0 <= dx < dx + dw <= 1080
                and 260 <= dy < dy + dh <= 1010
                and 0 <= out_x < out_x + dow <= 1080
                and out_y + doh <= 1010
            ):
                raise ValueError("Detail exceeds the source or viewport.")
            enlarged = f"detail{number}"
            filters.append(
                f"[p{branch}]crop={dw}:{dh}:{dx}:{dy},scale={dow}:{doh}:flags=lanczos[{enlarged}]"
            )
            branch += 1
            focused = f"focused{number}"
            filters.append(
                f"[{current}][{enlarged}]overlay=x={out_x}:y={out_y}:enable='{when}'[{focused}]"
            )
            labeled = f"label{number}"
            filters.append(
                f"[{focused}]drawtext=text='CLI DETAIL':fontsize=24:fontcolor=0xFAF9F6:"
                f"x={out_x + 10}:y={out_y - 36}:enable='{when}'[{labeled}]"
            )
            current = labeled
            if detail.get("border"):
                bordered = f"border{number}"
                filters.append(
                    f"[{current}]drawbox=x={out_x}:y={out_y}:w={dow}:h={doh}:"
                    f"color=0x{detail['border']}:t=4:enable='{when}'[{bordered}]"
                )
                current = bordered
        previous = current
    final = ASSETS / "skout-linkedin-final.mp4"
    with tempfile.TemporaryDirectory(prefix="skout-linkedin-mobile-") as directory:
        staged = Path(directory) / "final.mp4"
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(original),
            "-filter_complex",
            ";".join(filters),
            "-map",
            f"[{previous}]",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(staged),
        )
        validate(ffmpeg, ffprobe, staged, duration, True)
        shutil.copy2(staged, final)
    frames = ASSETS / "frames/linkedin-mobile"
    frames.mkdir(parents=True, exist_ok=True)
    for number, time in enumerate([11, 14, 18, 21, 25, 28, 32], 1):
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-ss",
            str(time),
            "-i",
            str(final),
            "-vf",
            "scale=360:450",
            "-frames:v",
            "1",
            str(frames / f"scene-{number}.png"),
        )
    sheet = ASSETS / "skout-linkedin-mobile-contact-sheet.png"
    video.run(
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-framerate",
        "1",
        "-i",
        str(frames / "scene-%d.png"),
        "-vf",
        "tile=4x2:padding=12:margin=12:color=0x202323",
        "-frames:v",
        "1",
        str(sheet),
    )
    print(f"Output: {final}\n360px contact sheet: {sheet}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise SystemExit(f"Mobile-readability build failed: {detail}") from error
