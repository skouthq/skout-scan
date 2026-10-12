"""Add prominent workflow labels to V3 without changing its existing content."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import enhance_video as video
from build_demo_v3 import rounded_path

DEMO = Path(__file__).resolve().parents[1]
ASSETS = DEMO / "assets"


def stage_ass(stages: list[dict], duration: float) -> str:
    source = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1440\nPlayResY: 1160\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Stage,Arial,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        "-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    for stage in stages:
        start, end, x, y = (stage[k] for k in ("start", "end", "x", "y"))
        if not (
            0 <= start < end <= duration
            and 2 <= end - start <= 3
            and 0 <= x <= 890
            and 0 <= y <= 918
            and stage["text"].isupper()
            and not any(c in stage["text"] for c in "{}\\\n")
        ):
            raise ValueError("Invalid stage geometry, timing or text.")
        drawings = [
            (
                0,
                rf"{{\an7\pos({x},{y})\p1\bord0\shad0\1c&H1A1715&\1a&H40&\fad(250,250)}}"
                + rounded_path(550, 82, 10)
                + r"{\p0}",
            ),
            (
                1,
                rf"{{\an7\pos({x + 1},{y + 10})\p1\bord0\shad0\1c&HC7C94B&\fad(250,250)}}"
                + "m 0 0 l 5 0 5 62 0 62"
                + r"{\p0}",
            ),
            (
                2,
                rf"{{\an5\pos({x + 278},{y + 41})\b1\fs38\1c&HFFFFFF&\fad(250,250)}}"
                + stage["text"],
            ),
        ]
        for layer, drawing in drawings:
            source += (
                f"Dialogue: {layer},{video.ass_time(start)},{video.ass_time(end)},"
                f"Stage,,0,0,0,,{drawing}\n"
            )
    return source


def main() -> None:
    ffmpeg, ffprobe = video.tool("ffmpeg"), video.tool("ffprobe")
    if " subtitles " not in video.run(ffmpeg, "-hide_banner", "-filters"):
        full = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
        if not full.is_file() or "FFMPEG" in os.environ:
            raise ValueError("Set FFMPEG to a build with libass.")
        ffmpeg = str(full)
    original = ASSETS / "skout-demo-v3.mp4"
    metadata = video.probe(ffprobe, original)
    duration = float(metadata["format"]["duration"])
    stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    if (stream["width"], stream["height"]) != (1440, 1160) or abs(duration - 90.72) > 0.01:
        raise ValueError("Expected preserved V3 master; recheck placement before rendering.")
    stages = json.loads((DEMO / "annotations/v4-stages.json").read_text())
    if [s["text"] for s in stages] != [
        "DISCOVER THE GAP",
        "REVIEW & CLASSIFY",
        "ADD THE MISSING EVAL",
        "VERIFY RESOLUTION",
    ]:
        raise ValueError("Exactly four specified workflow labels are required.")
    ass = DEMO / "annotations/v4-stages.ass"
    ass.write_text(stage_ass(stages, duration))
    output = ASSETS / "skout-demo-v4.mp4"
    with tempfile.TemporaryDirectory(prefix="skout-v4-") as directory:
        work = Path(directory)
        shutil.copy2(ass, work / "stages.ass")
        staged = work / "v4.mp4"
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(original),
            "-vf",
            "subtitles=stages.ass",
            "-map",
            "0:v:0",
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
            cwd=work,
        )
        video.validate(ffmpeg, ffprobe, staged, duration, True)
        shutil.copy2(staged, output)
    frames = ASSETS / "frames/v4"
    frames.mkdir(parents=True, exist_ok=True)
    for number, stage in enumerate(stages, 1):
        middle = (stage["start"] + stage["end"]) / 2
        for scale, suffix in ((False, "full"), (True, "half")):
            args = [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-ss",
                str(middle),
                "-i",
                str(output),
                "-frames:v",
                "1",
            ]
            if scale:
                args += ["-vf", "scale=iw/2:ih/2"]
            video.run(*args, str(frames / f"stage-{number}-{suffix}.png"))
    sheet = ASSETS / "skout-demo-v4-stages.png"
    video.run(
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-framerate",
        "1",
        "-i",
        str(frames / "stage-%d-half.png"),
        "-vf",
        "tile=2x2:padding=12:margin=12:color=0x202329",
        "-frames:v",
        "1",
        str(sheet),
    )
    print(f"Video: {output}\nContact sheet: {sheet}")
    print("Inspect all four midpoint frames before reporting visible-label success.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise SystemExit(f"V4 build failed: {detail}") from error
