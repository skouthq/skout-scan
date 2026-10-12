"""Build captioned demo exports using FFmpeg and the Python standard library."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1]
ASSETS = DEMO / "assets"
SRT = DEMO / "captions/skout-demo.srt"
ASS = SRT.with_suffix(".ass")


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout


def tool(name: str) -> str:
    executable = os.environ.get(name.upper()) or shutil.which(name)
    if not executable:
        raise ValueError(f"Missing {name}. On macOS: brew install ffmpeg-full")
    return executable


def probe(ffprobe: str, path: Path) -> dict:
    return json.loads(
        run(ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path))
    )


def timestamp(value: str) -> float:
    hours, minutes, seconds, milliseconds = map(int, re.split("[:,]", value))
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid subtitle timestamp: {value}")
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def ass_time(value: float) -> str:
    centiseconds = round(value * 100)
    return (
        f"{centiseconds // 360000}:{centiseconds // 6000 % 60:02}:"
        f"{centiseconds // 100 % 60:02}.{centiseconds % 100:02}"
    )


def subtitles(duration: float) -> str:
    header = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1440\nPlayResY: 1160\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Caption,Arial,38,&H00F6F4F0,&H00F6F4F0,&H60000000,&H60000000,"
        "0,0,0,0,100,100,0,0,3,8,0,2,60,60,35,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    previous_end = 0.0
    events = []
    for number, block in enumerate(re.split(r"\n\s*\n", SRT.read_text().strip()), 1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0] != str(number):
            raise ValueError("SRT needs sequential cue numbers and caption text.")
        match = re.fullmatch(r"(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})", lines[1])
        if not match:
            raise ValueError(f"Invalid SRT timing at cue {number}.")
        start, end = map(timestamp, match.groups())
        if start < previous_end or end <= start or end > duration + 0.01:
            raise ValueError(f"Overlapping or out-of-range cue {number}.")
        if len(lines[2:]) > 2 or any(len(line) > 60 for line in lines[2:]):
            raise ValueError(f"Cue {number} must fit two readable lines.")
        if any(character in "".join(lines[2:]) for character in "{}\\"):
            raise ValueError("ASS formatting characters are not allowed in SRT captions.")
        text = r"\N".join(lines[2:])
        events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Caption,,0,0,0,,{text}\n")
        previous_end = end
    if not events:
        raise ValueError("No captions found.")
    return header + "".join(events)


def validate(ffmpeg: str, ffprobe: str, path: Path, duration: float, audio: bool) -> None:
    metadata = probe(ffprobe, path)
    video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
    if (video["width"], video["height"], video["codec_name"], video["pix_fmt"]) != (
        1440,
        1160,
        "h264",
        "yuv420p",
    ):
        raise ValueError("Unexpected export format.")
    if abs(float(metadata["format"]["duration"]) - duration) > 0.1:
        raise ValueError("Export duration changed unexpectedly.")
    audio_streams = [s for s in metadata["streams"] if s["codec_type"] == "audio"]
    if audio and (not audio_streams or audio_streams[0]["codec_name"] != "aac"):
        raise ValueError("Missing AAC soundtrack.")
    run(ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-")
    print(f"{path}: {metadata['format']['duration']}s, 1440x1160, {path.stat().st_size:,} bytes")


def main() -> None:
    ffmpeg, ffprobe = tool("ffmpeg"), tool("ffprobe")
    filters = run(ffmpeg, "-hide_banner", "-filters")
    if " subtitles " not in filters:
        full = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
        if full.is_file() and "FFMPEG" not in os.environ:
            ffmpeg = str(full)
        else:
            raise ValueError(
                "FFmpeg needs libass subtitles support. Install ffmpeg-full or set FFMPEG."
            )
    original = ASSETS / "skout-demo.mp4"
    if not original.is_file() or not SRT.is_file():
        raise ValueError("Missing original MP4 or SRT captions.")
    metadata = probe(ffprobe, original)
    video = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    if (video["width"], video["height"]) != (1440, 1000):
        raise ValueError("Expected original 1440x1000 recording; review caption placement first.")
    duration = float(metadata["format"]["duration"])
    has_audio = any(s["codec_type"] == "audio" for s in metadata["streams"])
    ASS.write_text(subtitles(duration))
    captioned = ASSETS / "skout-demo-captioned.mp4"
    final = ASSETS / "skout-demo-final.mp4"
    music = ASSETS / "music/background.mp3"
    # Fixed local filter filename avoids shell/filter escaping of checkout paths.
    with tempfile.TemporaryDirectory(prefix="skout-video-") as directory:
        work = Path(directory)
        shutil.copy2(ASS, work / "captions.ass")
        staged = work / "captioned.mp4"
        run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(original),
            "-vf",
            "pad=iw:ih+160:0:0:color=0x15171a,subtitles=captions.ass",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(staged),
            cwd=work,
        )
        validate(ffmpeg, ffprobe, staged, duration, has_audio)
        shutil.copy2(staged, captioned)
        print(f"Captioned output: {captioned}")
        if not music.is_file() or not (music.parent / "README.md").is_file():
            print(
                "Music version pending: supply demo/assets/music/background.mp3 "
                "with source/license notes."
            )
            if final.exists():
                print("Existing final MP4 was NOT refreshed; do not mistake it for this build.")
            return
        music_duration = float(probe(ffprobe, music)["format"]["duration"])
        if music_duration < duration:
            raise ValueError("Music is shorter than video; no automatic looping or substitution.")
        mix = (
            f"[1:a]atrim=duration={duration},asetpts=PTS-STARTPTS,volume=0.18,"
            f"afade=t=in:st=0:d=2,afade=t=out:st={duration - 5}:d=5[music]"
        )
        if has_audio:
            mix += (
                ";[0:a][music]amix=inputs=2:duration=first:normalize=0,"
                "alimiter=limit=0.95:level=0[audio]"
            )
        else:
            mix += ";[music]alimiter=limit=0.95:level=0[audio]"
        staged_final = work / "final.mp4"
        run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-i",
            str(captioned),
            "-i",
            str(music),
            "-filter_complex",
            mix,
            "-map",
            "0:v:0",
            "-map",
            "[audio]",
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
        validate(ffmpeg, ffprobe, staged_final, duration, True)
        shutil.copy2(staged_final, final)
        print(f"Final output: {final}")
        print("Audio: original music x 0.18; 2s fade-in; 5s fade-out; no looping.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise SystemExit(f"Video build failed: {detail}") from error
