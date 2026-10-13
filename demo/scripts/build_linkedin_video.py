"""Create a portrait promotional cut from the approved full demo, without reruns."""

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import enhance_video as video
from build_demo_v3 import rounded_path

DEMO = Path(__file__).resolve().parents[1]
ASSETS = DEMO / "assets"
EDIT = DEMO / "linkedin"


def event(start: float, end: float, text: str, layer: int = 1) -> str:
    return f"Dialogue: {layer},{video.ass_time(start)},{video.ass_time(end)},Brand,,0,0,0,,{text}\n"


def text_style(x: int, y: int, size: int, color: str, bold: bool = False) -> str:
    bgr = color[4:6] + color[2:4] + color[0:2]
    return rf"{{\an5\pos({x},{y})\fs{size}\b{int(bold)}\1c&H{bgr}&\bord0\shad0}}"


def make_ass(edit: list[dict], duration: float) -> str:
    source = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1350\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Brand,Arial,48,&H00F6F9FA,&H00F6F9FA,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    source += event(
        0, 4, text_style(540, 470, 56, "202323", True) + "Your AI agent evals are passing."
    )
    source += event(
        1.2,
        4,
        text_style(540, 700, 78, "F06445", True) + r"{\fad(160,0)}But what aren't\Nthey testing?",
    )
    source += event(0, 4, text_style(540, 210, 36, "F06445", True) + "SKOUT SCAN")
    source += event(4, 9, text_style(540, 505, 90, "FAF9F6", True) + "Meet Skout Scan.")
    source += event(
        4, 9, text_style(540, 680, 48, "E9E4F5") + r"Open-source agent\Neval coverage discovery."
    )
    source += event(4, 9, text_style(540, 910, 36, "F06445") + "Local-first · No source upload")
    cursor = 0.0
    for item in edit:
        length = item["duration"] if item["kind"] == "card" else item["end"] - item["start"]
        end = cursor + length
        if item["kind"] == "footage":
            source += event(cursor, end, text_style(174, 65, 32, "F06445", True) + "SKOUT SCAN")
            source += event(
                cursor,
                end,
                text_style(540, 162, 54, "FAF9F6", True) + item["headline"].replace("\n", r"\N"),
            )
            source += event(
                cursor, end, r"{\an7\pos(60,220)\p1\bord0\1c&H4564F0&}m 0 0 l 960 0 960 4 0 4{\p0}"
            )
        cursor = end
    source += event(35, duration, text_style(540, 365, 102, "202323", True) + "Skout Scan")
    source += event(
        35,
        duration,
        text_style(540, 540, 48, "202323") + r"Find what your AI agent\Nevals aren't testing.",
    )
    source += event(
        35, duration, r"{\an7\pos(440,660)\p1\bord0\1c&H4564F0&}m 0 0 l 200 0 200 5 0 5{\p0}"
    )
    source += event(
        35,
        duration,
        text_style(540, 790, 46, "202323", True) + r"Building AI agents?\NTry Skout on your repo.",
    )
    source += event(35, duration, text_style(540, 1000, 48, "F06445", True) + "www.skouthq.com")
    source += event(
        35, duration, text_style(540, 1090, 42, "202323", True) + "github.com/skouthq/skout-scan"
    )
    previous_end = 0.0
    blocks = re.split(r"\n\s*\n", (EDIT / "captions.srt").read_text().strip())
    for number, block in enumerate(blocks, 1):
        lines = block.splitlines()
        if lines[0] != str(number) or len(lines) not in {3, 4}:
            raise ValueError("Expected sequential captions, maximum two lines.")
        start, end = map(video.timestamp, lines[1].split(" --> "))
        if start < previous_end or not start < end <= duration:
            raise ValueError("Captions overlap or exceed the edit.")
        if any(len(line) > 42 or any(c in line for c in "{}\\") for line in lines[2:]):
            raise ValueError("Caption too wide or contains ASS formatting.")
        source += event(start, end, text_style(540, 1175, 48, "FAF9F6") + r"\N".join(lines[2:]))
        previous_end = end
    for item in json.loads((EDIT / "annotations.json").read_text()):
        x, y, w, h, r, thickness = (
            item[k] for k in ("x", "y", "width", "height", "radius", "thickness")
        )
        if not (
            4 <= thickness <= 6
            and thickness <= x < x + w <= 1080 - thickness
            and thickness <= y < y + h <= 1010 - thickness
            and 0 <= item["start"] < item["end"] <= duration
            and re.fullmatch(r"[0-9A-F]{6}", item["color"])
        ):
            raise ValueError("Invalid highlight bounds, timing or color.")
        color = item["color"][4:6] + item["color"][2:4] + item["color"][0:2]
        outline = (
            rf"{{\an7\pos({x},{y})\p1\bord{thickness}\shad0\1a&HFF&\3c&H{color}&}}"
            + rounded_path(w, h, r)
            + r"{\p0}"
        )
        source += event(item["start"], item["end"], outline, 2)
    return source


def validate(ffmpeg: str, ffprobe: str, path: Path, duration: float, audio: bool) -> None:
    metadata = video.probe(ffprobe, path)
    streams = metadata["streams"]
    stream = next(s for s in streams if s["codec_type"] == "video")
    if (
        stream["width"],
        stream["height"],
        stream["codec_name"],
        stream["pix_fmt"],
        stream["r_frame_rate"],
    ) != (1080, 1350, "h264", "yuv420p", "25/1"):
        raise ValueError("Unexpected portrait export format.")
    if abs(float(metadata["format"]["duration"]) - duration) > 0.1:
        raise ValueError("Unexpected export duration.")
    audio_streams = [s for s in streams if s["codec_type"] == "audio"]
    if (audio and (len(audio_streams) != 1 or audio_streams[0]["codec_name"] != "aac")) or (
        not audio and audio_streams
    ):
        raise ValueError("Incorrect audio stream configuration.")
    video.run(ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-")
    print(
        f"{path.name}: {metadata['format']['duration']}s, 1080x1350, "
        f"{path.stat().st_size:,} bytes; audio={audio}"
    )


def main() -> None:
    original = ASSETS / "skout-demo-final.mp4"
    if not original.is_file():
        raise ValueError(f"Missing source recording: {original}. No substitute will be generated.")
    ffmpeg, ffprobe = video.tool("ffmpeg"), video.tool("ffprobe")
    if " subtitles " not in video.run(ffmpeg, "-hide_banner", "-filters"):
        full = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
        if not full.is_file() or "FFMPEG" in os.environ:
            raise ValueError("Set FFMPEG to an FFmpeg build with libass.")
        ffmpeg = str(full)
    metadata = video.probe(ffprobe, original)
    v = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    if (v["width"], v["height"]) != (1440, 1160):
        raise ValueError("Expected approved source canvas; inspect framing before editing.")
    edit = json.loads((EDIT / "edit.json").read_text())
    duration = sum(
        item["duration"] if item["kind"] == "card" else item["end"] - item["start"] for item in edit
    )
    if abs(duration - 42) > 0.001 or not 35 <= duration <= 45:
        raise ValueError("Expected verified 42-second storyboard.")
    for item in edit:
        if item["kind"] == "footage" and not 0 <= item["start"] < item["end"] <= float(
            metadata["format"]["duration"]
        ):
            raise ValueError("Source range outside recording.")
    ass = EDIT / "overlays.ass"
    ass.write_text(make_ass(edit, duration))
    silent = ASSETS / "skout-linkedin-40s-silent.mp4"
    final = ASSETS / "skout-linkedin-40s.mp4"
    with tempfile.TemporaryDirectory(prefix="skout-linkedin-") as directory:
        work = Path(directory)
        shutil.copy2(ass, work / "overlays.ass")
        clips = []
        for number, item in enumerate(edit):
            clip = work / f"clip-{number}.mp4"
            args = [ffmpeg, "-y", "-v", "error"]
            if item["kind"] == "card":
                length = item["duration"]
                args += [
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c=0x{item['background']}:s=1080x1350:r=25:d={length}",
                ]
            else:
                length = item["end"] - item["start"]
                args += [
                    "-ss",
                    str(item["start"]),
                    "-i",
                    str(original),
                    "-t",
                    str(length),
                    "-vf",
                    "crop=1440:1000:0:0,scale=1080:750:flags=lanczos,"
                    "pad=1080:1350:0:260:color=0x202323,setsar=1",
                ]
            video.run(
                *args,
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "medium",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "25",
                str(clip),
            )
            clips.append(clip)
        (work / "clips.txt").write_text("".join(f"file '{clip.name}'\n" for clip in clips))
        staged = work / "silent.mp4"
        video.run(
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "clips.txt",
            "-vf",
            "subtitles=overlays.ass",
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
        validate(ffmpeg, ffprobe, staged, duration, False)
        shutil.copy2(staged, silent)
        music = ASSETS / "music/skout-upbeat.mp3"
        if music.is_file() and (music.parent / "UPBEAT-LICENSE.md").is_file():
            if float(video.probe(ffprobe, music)["format"]["duration"]) < duration:
                raise ValueError("Existing music is too short; no looping.")
            staged_final = work / "final.mp4"
            mix = (
                f"atrim=duration={duration},asetpts=PTS-STARTPTS,volume=0.20,"
                f"afade=t=in:st=0:d=1,afade=t=out:st={duration - 3}:d=3,"
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
                mix,
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
        else:
            shutil.copy2(silent, final)
            print("Music pending: soundtrack/provenance unavailable; master is silent.")
    frames = ASSETS / "frames/linkedin"
    frames.mkdir(parents=True, exist_ok=True)
    for number, time in enumerate([2.5, 14, 24.5, 32, 38.5], 1):
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
            video.run(*args, str(frames / f"scene-{number}-{suffix}.png"))
    sheet = ASSETS / "skout-linkedin-contact-sheet.png"
    video.run(
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-framerate",
        "1",
        "-i",
        str(frames / "scene-%d-half.png"),
        "-vf",
        "tile=3x2:padding=12:margin=12:color=0x202323",
        "-frames:v",
        "1",
        str(sheet),
    )
    print(f"Master: {final}\nSilent: {silent}\nContact sheet: {sheet}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        detail = error.stderr if isinstance(error, subprocess.CalledProcessError) else str(error)
        raise SystemExit(f"LinkedIn build failed: {detail}") from error
