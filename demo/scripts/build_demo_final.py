"""Append a branded card to approved V4 and extend its existing licensed music."""

import hashlib
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
            raise ValueError("Set FFMPEG to a build with libass.")
        ffmpeg = str(full)
    original = ASSETS / "skout-demo-v4.mp4"
    metadata = video.probe(ffprobe, original)
    duration = float(metadata["format"]["duration"])
    stream = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    if (stream["width"], stream["height"], stream["r_frame_rate"]) != (1440, 1160, "25/1"):
        raise ValueError("Expected approved V4 dimensions and frame rate.")
    if abs(duration - 90.72) > 0.01:
        raise ValueError("Expected approved 90.72-second V4 master.")
    total = duration + 4
    music = ASSETS / "music/skout-upbeat.mp3"
    if float(video.probe(ffprobe, music)["format"]["duration"]) < total:
        raise ValueError("Existing music is too short; no looping or substitution permitted.")
    final = ASSETS / "skout-demo-final.mp4"
    with tempfile.TemporaryDirectory(prefix="skout-closing-") as directory:
        work = Path(directory)
        shutil.copy2(ASSETS / "closing-card.ass", work / "closing.ass")
        card = work / "card.mp4"
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x0D1117:s=1440x1160:r=25:d=4.4",
            "-vf",
            "subtitles=closing.ass",
            "-an",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(card),
            cwd=work,
        )
        staged = work / "final.mp4"
        filters = (
            "[0:v]settb=AVTB,setpts=PTS-STARTPTS[v0];"
            "[1:v]settb=AVTB,setpts=PTS-STARTPTS[v1];"
            f"[v0][v1]xfade=transition=fade:duration=0.4:offset={duration - 0.4},"
            "format=yuv420p[v];"
            f"[2:a]atrim=duration={total},asetpts=PTS-STARTPTS,volume=0.20,"
            f"afade=t=in:st=0:d=2,afade=t=out:st={total - 3}:d=3,"
            "alimiter=limit=0.95:level=0[a]"
        )
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(original),
            "-i",
            str(card),
            "-i",
            str(music),
            "-filter_complex",
            filters,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-r",
            "25",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-t",
            str(total),
            "-movflags",
            "+faststart",
            str(staged),
        )
        video.validate(ffmpeg, ffprobe, staged, total, True)
        # The older 75-second enhancement used this filename. Preserve it once.
        if (
            final.exists()
            and abs(float(video.probe(ffprobe, final)["format"]["duration"]) - total) > 0.01
        ):
            backup = ASSETS / "skout-demo-final-pre-closing.mp4"
            if (
                backup.exists()
                and hashlib.sha256(backup.read_bytes()).digest()
                != hashlib.sha256(final.read_bytes()).digest()
            ):
                raise ValueError("Backup collision: preserve the previous final manually.")
            if not backup.exists():
                shutil.copy2(final, backup)
            print(f"Earlier final preserved: {backup}")
        shutil.copy2(staged, final)
    frames = ASSETS / "frames/final"
    frames.mkdir(parents=True, exist_ok=True)
    for name, time in (
        ("resolution", 76),
        ("transition", duration - 0.2),
        ("closing", duration + 2),
        ("last-frame", total - 0.04),
    ):
        for half, suffix in ((False, "full"), (True, "half")):
            args = [
                ffmpeg,
                "-y",
                "-v",
                "error",
                "-ss",
                str(time),
                "-i",
                str(final),
                "-frames:v",
                "1",
            ]
            if half:
                args += ["-vf", "scale=iw/2:ih/2"]
            video.run(*args, str(frames / f"{name}-{suffix}.png"))
    print(f"Final: {final}\nCrossfade: {duration - 0.4:.2f}–{duration:.2f}s")
    print(f"Fully visible closing: {duration:.2f}–{total:.2f}s; audio fades over final 3s.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise SystemExit(f"Final video build failed: {detail}") from error
