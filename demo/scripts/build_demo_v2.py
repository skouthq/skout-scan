"""Render v2 captions and frame-verified annotations; preserve every v1 asset."""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import enhance_video as video

DEMO = Path(__file__).resolve().parents[1]
ASSETS = DEMO / "assets"


def main() -> None:
    ffmpeg, ffprobe = video.tool("ffmpeg"), video.tool("ffprobe")
    if " subtitles " not in video.run(ffmpeg, "-hide_banner", "-filters"):
        full = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
        if not full.is_file() or "FFMPEG" in os.environ:
            raise ValueError("Set FFMPEG to an FFmpeg build with libass subtitles support.")
        ffmpeg = str(full)
    original = ASSETS / "skout-demo-v2-terminal.mp4"
    metadata = video.probe(ffprobe, original)
    duration = float(metadata["format"]["duration"])
    stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    if (stream["width"], stream["height"]) != (1440, 1000) or not 85 <= duration <= 105:
        raise ValueError("Review recording dimensions/duration and recheck annotation frames.")
    video.SRT = DEMO / "captions/skout-demo-v2.srt"
    ass = video.SRT.with_suffix(".ass")
    ass.write_text(video.subtitles(duration))
    annotations = json.loads((DEMO / "annotations/v2.json").read_text())
    filters = ["pad=iw:ih+160:0:0:color=0x15171a"]
    for item in annotations:
        start, end = item["start"], item["end"]
        x, y, width, height = (item[key] for key in ("x", "y", "width", "height"))
        if not (
            0 <= start < end <= duration
            and 0 <= x < x + width <= 1440
            and 0 <= y < y + height <= 1000
        ):
            raise ValueError(f"Invalid annotation: {item['name']}")
        filters.append(
            f"drawbox=x={x}:y={y}:w={width}:h={height}:color={item['color']}:"
            f"t=2:enable='between(t,{start},{end})'"
        )
    filters.append("subtitles=captions.ass")
    silent = ASSETS / "skout-demo-v2-silent.mp4"
    final = ASSETS / "skout-demo-v2.mp4"
    with tempfile.TemporaryDirectory(prefix="skout-v2-") as directory:
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
            ",".join(filters),
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
        shutil.copy2(staged, silent)
        music = ASSETS / "music/skout-upbeat.mp3"
        if not music.is_file():
            shutil.copy2(silent, final)
            print("Music pending: v2 master is also silent. See UPBEAT-LICENSE.md.")
            return
        if not (music.parent / "UPBEAT-LICENSE.md").is_file():
            raise ValueError("Music provenance is required.")
        if float(video.probe(ffprobe, music)["format"]["duration"]) < duration:
            raise ValueError("Music is too short; no automatic looping.")
        staged_final = work / "final.mp4"
        audio = (
            f"atrim=duration={duration},asetpts=PTS-STARTPTS,volume=0.20,"
            f"afade=t=in:st=0:d=2,afade=t=out:st={duration - 4}:d=4,"
            "alimiter=limit=0.95:level=0"
        )
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(silent),
            "-i",
            str(music),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-af",
            audio,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-t",
            str(duration),
            "-movflags",
            "+faststart",
            str(staged_final),
        )
        video.validate(ffmpeg, ffprobe, staged_final, duration, True)
        shutil.copy2(staged_final, final)
    print(f"Silent: {silent}\nMaster: {final}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise SystemExit(f"V2 build failed: {detail}") from error
