"""Publish candidate: a single terminal camera, with no magnification panels."""

import json
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
    # Start from the approved edit, not the derivative containing duplicated panels.
    original = ASSETS / "skout-linkedin-40s.mp4"
    if not original.is_file():
        raise ValueError("The approved original promotional recording is missing.")
    duration = float(video.probe(ffprobe, original)["format"]["duration"])
    if abs(duration - 42) > 0.01:
        raise ValueError("Expected approved 42-second timeline.")
    regions = json.loads((DEMO / "linkedin/publish-framing.json").read_text())
    branches = "".join(f"[camera{i}]" for i in range(len(regions)))
    filters = [f"[0:v]split={len(regions) + 1}[base]{branches}"]
    previous, previous_end = "base", 0
    for i, region in enumerate(regions):
        start, end = region["start"], region["end"]
        x, y, w, h, ow, oh = (
            region[k] for k in ("x", "y", "width", "height", "out_width", "out_height")
        )
        if not (
            previous_end <= start < end <= 35
            and 0 <= x < x + w <= 1080
            and 260 <= y < y + h <= 1010
            and ow == 1080
            and oh + 260 <= 1130
        ):
            raise ValueError("Invalid or overlapping single-camera interval.")
        previous_end = end
        when = f"gte(t,{start})*lt(t,{end})"
        # Entire previous terminal viewport is erased before its replacement.
        # There is no inset, extra screenshot, text label or second terminal view.
        filters.append(
            f"[{previous}]drawbox=x=0:y=260:w=1080:h=750:color=0x202323:"
            f"t=fill:enable='{when}'[clean{i}]"
        )
        filters.append(f"[camera{i}]crop={w}:{h}:{x}:{y},scale={ow}:{oh}:flags=lanczos[zoom{i}]")
        filters.append(f"[clean{i}][zoom{i}]overlay=x=0:y=260:enable='{when}'[single{i}]")
        previous = f"single{i}"
    final = ASSETS / "skout-linkedin-publish.mp4"
    with tempfile.TemporaryDirectory(prefix="skout-single-camera-") as directory:
        staged = Path(directory) / "publish.mp4"
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
    frames = ASSETS / "frames/linkedin-publish"
    frames.mkdir(parents=True, exist_ok=True)
    times = [12, 22, 29, 34, 14, 18, 25]
    for i, time in enumerate(times, 1):
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
            str(frames / f"scene-{i}.png"),
        )
    sheet = ASSETS / "skout-linkedin-publish-contact-sheet.png"
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
        raise SystemExit(f"Single-view video build failed: {detail}") from error
