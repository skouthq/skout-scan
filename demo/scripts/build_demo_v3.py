"""Polish the preserved V2 recording with editable ASS vectors and captions."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import enhance_video as video

DEMO = Path(__file__).resolve().parents[1]
ASSETS = DEMO / "assets"


def rounded_path(width: int, height: int, radius: int) -> str:
    """Local ASS drawing coordinates; cubic curves approximate quarter circles."""
    w, h, r = width, height, radius
    k = round(r * 0.552285, 2)
    return (
        f"m {r} 0 l {w - r} 0 b {w - r + k} 0 {w} {r - k} {w} {r} "
        f"l {w} {h - r} b {w} {h - r + k} {w - r + k} {h} {w - r} {h} "
        f"l {r} {h} b {r - k} {h} 0 {h - r + k} 0 {h - r} "
        f"l 0 {r} b 0 {r - k} {r - k} 0 {r} 0"
    )


def event(start: float, end: float, text: str, layer: int = 1) -> str:
    return (
        f"Dialogue: {layer},{video.ass_time(start)},{video.ass_time(end)},Overlay,,0,0,0,,{text}\n"
    )


def overlays(duration: float) -> str:
    result = []
    for item in json.loads((DEMO / "annotations/v3.json").read_text()):
        x, y, w, h, r, thickness = (
            item[key] for key in ("x", "y", "width", "height", "radius", "thickness")
        )
        clearance = thickness
        if not (
            0 <= item["start"] < item["end"] <= duration
            and clearance <= x < x + w <= 1440 - clearance
            and clearance <= y < y + h <= 1000 - clearance
            and 0 < r < min(w, h) / 2
            and 4 <= thickness <= 6
            and re.fullmatch(r"[0-9A-F]{6}", item["color"])
        ):
            raise ValueError(f"Invalid annotation: {item['name']}")
        color = item["color"][4:6] + item["color"][2:4] + item["color"][0:2]
        # Transparent fill leaves only the external ASS outline visible.
        # Use the full requested width and reserve that clearance outside it.
        drawing = (
            rf"{{\an7\pos({x},{y})\p1\fscx100\fscy100\bord{thickness}"
            rf"\shad0\alpha&H00&\1a&HFF&\3c&H{color}&}}" + rounded_path(w, h, r) + r"{\p0}"
        )
        result.append(event(item["start"], item["end"], drawing))
    for item in json.loads((DEMO / "annotations/v3-labels.json").read_text()):
        if not 0 <= item["start"] < item["end"] <= duration:
            raise ValueError("Label timing exceeds the recording.")
        if any(c in item["text"] for c in "{}\\\n"):
            raise ValueError("Label text must not contain ASS instructions.")
        kind = item["kind"]
        if kind == "payoff":
            # Blank terminal space below the genuine evidence, never over it.
            style = r"{\an5\pos(720,550)\fs40\b1\bord2\shad0\3c&H183C2B&}"
            accent = r"{\an7\pos(360,595)\p1\bord0\shad0\1c&H8AD939&}m 0 0 l 720 0 720 4 0 4{\p0}"
            result.append(event(item["start"], item["end"], accent))
        elif kind in {"stage", "secondary"}:
            style = r"{\an5\pos(720,1026)\fs24\bord0\shad0\1c&HF0F4F6&}"
            if kind == "stage":
                accent = (
                    r"{\an7\pos(550,1048)\p1\bord0\shad0\1c&HC7C94B&}m 0 0 l 340 0 340 3 0 3{\p0}"
                )
                result.append(event(item["start"], item["end"], accent))
            else:
                style = r"{\an5\pos(720,1026)\fs22\bord0\shad0\1c&HB3BABE&}"
        else:
            raise ValueError(f"Unknown label kind: {kind}")
        result.append(event(item["start"], item["end"], style + item["text"]))
    return "".join(result)


def main() -> None:
    ffmpeg, ffprobe = video.tool("ffmpeg"), video.tool("ffprobe")
    if " subtitles " not in video.run(ffmpeg, "-hide_banner", "-filters"):
        full = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
        if not full.is_file() or "FFMPEG" in os.environ:
            raise ValueError("Set FFMPEG to a build with libass subtitles support.")
        ffmpeg = str(full)
    original = ASSETS / "skout-demo-v2-terminal.mp4"
    soundtrack = ASSETS / "skout-demo-v2.mp4"
    metadata = video.probe(ffprobe, original)
    duration = float(metadata["format"]["duration"])
    stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    if (stream["width"], stream["height"]) != (1440, 1000) or abs(duration - 90.72) > 0.01:
        raise ValueError("Expected preserved V2 recording; recheck annotation coordinates first.")
    music_metadata = video.probe(ffprobe, soundtrack)
    if abs(float(music_metadata["format"]["duration"]) - duration) > 0.01 or not any(
        s["codec_name"] == "aac" for s in music_metadata["streams"]
    ):
        raise ValueError("Expected matching V2 soundtrack; no audio substitution permitted.")
    video.SRT = DEMO / "captions/skout-demo-v3.srt"
    ass = video.SRT.with_suffix(".ass")
    subtitle_source = video.subtitles(duration)
    overlay_style = (
        "Style: Overlay,Arial,38,&H00F6F4F0,&H00F6F4F0,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1\n"
    )
    subtitle_source = subtitle_source.replace("\n[Events]", "\n" + overlay_style + "\n[Events]")
    ass.write_text(subtitle_source + overlays(duration))
    silent = ASSETS / "skout-demo-v3-silent.mp4"
    final = ASSETS / "skout-demo-v3.mp4"
    with tempfile.TemporaryDirectory(prefix="skout-v3-") as directory:
        work = Path(directory)
        shutil.copy2(ass, work / "captions.ass")
        staged = work / "silent.mp4"
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(original),
            "-vf",
            "pad=iw:ih+160:0:0:color=0x15171a,subtitles=captions.ass",
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(staged),
            cwd=work,
        )
        video.validate(ffmpeg, ffprobe, staged, duration, False)
        staged_final = work / "final.mp4"
        # Stream-copy existing AAC: exact music, gain, fades and audio character.
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(staged),
            "-i",
            str(soundtrack),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(staged_final),
        )
        video.validate(ffmpeg, ffprobe, staged_final, duration, True)
        if any(s["codec_type"] == "audio" for s in video.probe(ffprobe, staged)["streams"]):
            raise ValueError("Silent output unexpectedly contains audio.")
        shutil.copy2(staged, silent)
        shutil.copy2(staged_final, final)
    print(f"Silent: {silent}\nMaster: {final}\nAudio: original V2 AAC stream copied unchanged.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise SystemExit(f"V3 build failed: {detail}") from error
