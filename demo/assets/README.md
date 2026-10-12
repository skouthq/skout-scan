# Demo media

`skout-demo.gif` is the verified GitHub landing-page asset: **75.28 seconds**,
**1440×1000**, **1,088,654 bytes** (about 1.04 MiB). It was rendered with VHS 0.12.1
and Skout Scan 0.1.6. The real CLI sequence was checked visually across the
recording, including framework detection, initial source evidence, solution
activation, stable finding identity, and observed resolution. All GIF frames
decode successfully. No personal filesystem paths appear in the visible scenes.

A local MP4 copy is also available: 75.28 seconds, 1440×1000, 818,326 bytes.
MP4s are ignored by Git to keep outreach/intermediate videos out of commits;
the GIF is the only intentional tracked media asset.

From the repository root, with Skout and VHS on PATH:

```sh
vhs demo/skout-demo.tape
```

This regenerates the GIF using real commands in a fresh temporary workspace.
See [recording instructions](../README.md#record-with-vhs) for dependencies.
The tape also includes an optional direct MP4 output line. To reproduce the
small MP4 copy from the GIF instead:

```sh
ffmpeg -i demo/assets/skout-demo.gif -an -c:v libx264 -pix_fmt yuv420p -movflags +faststart -y demo/assets/skout-demo.mp4
```

After regeneration, measure duration, resolution and size again and inspect the
full sequence. Keep the recording within 60–90 seconds, preserve legibility,
and aim for a GIF under about 10 MB. Intermediate frames and videos stay
untracked. The root README embeds the verified GIF with a relative link.

## Enhanced exports

The caption/music build preserves both original assets and creates:

| Export | Duration | Canvas | Size |
| --- | --- | --- | --- |
| `skout-demo-captioned.mp4` | 75.28s | 1440×1160 | 1,163,913 bytes |
| `skout-demo-final.mp4` | 75.28s | 1440×1160 | 2,713,862 bytes |

Both use H.264/yuv420p at 25 fps. The final soundtrack is AAC; the captioned-only
export has no audio. The original terminal occupies the unchanged 1440×1000
area at the top, with a 160-pixel caption band below it. Video encoding is lossy;
terminal-area comparison against the original measured 58.30 dB average PSNR.
Original MP4, GIF and supplied MP3 hashes were unchanged after both builds.

Captions run at 0–7.5, 7.5–15, 15–24, 24–40, 40–52, 52–61 and 61–75.28 seconds.
The last cue starts after the displayed resolution. The original recording was
not regenerated. Editable SRT and generated ASS sources live in `demo/captions/`.

Validation: full decode passed, all 1,882 frames preserved, no inserted black
frames detected, and representative frames checked at 5/15/25/35/45/55/70s,
plus the resolution detail at 65s. Captions do not cover terminal content.
Decoded audio peak: −16.95 dBFS; RMS: −31.44 dBFS, with no clipping or invalid
samples. Measured amplitude ratios against the original music confirmed the
fade-in, steady 0.18 gain, and fade-out. A human listening review is still needed;
these objective checks are not a subjective listening assessment.

See [enhancement instructions](../README.md#captioned-video-exports) for editing,
rebuilding, music provenance, and intended distribution. The original silent
GitHub GIF and root README embed are unchanged. All MP4s/raw music remain ignored
by Git; only caption/build/licensing sources are intended for commits.

## V2 complete workflow

Generated with VHS 0.12.1 and Skout 0.1.6: **90.72 seconds**, terminal font
32 px (up from 24 px), captions in a separate band. All original assets preserved.

| Export | Canvas | Size | Audio |
| --- | --- | --- | --- |
| `skout-demo-v2.mp4` | 1440×1160 | 3,349,952 bytes | AAC 160 kb/s |
| `skout-demo-v2-silent.mp4` | 1440×1160 | 1,391,473 bytes | None |

Both exports use H.264/yuv420p, 25 fps, faststart, and pass full decode checks.
Real interactive review persists add_eval while the finding remains open.
The supplied solution then resolves the same finding on the second scan:
`finding_f232f8c4fbb9aae3723cde30`. Persisted matching evidence references
`tests/test_retry.py`, eval `eval_d80887b2affe2e0075e0a540`.

Frame-checked thin outlines: red 18–21s, amber 34–36.5s and 49–52s,
green 74–78s. Editable sources are in `../annotations/v2.json` and
`../captions/skout-demo-v2.srt` (generated ASS alongside).

New music: Minimal Techno 01; see `music/UPBEAT-LICENSE.md`. Gain 0.20,
2-second fade-in, 4-second fade-out. Decoded mono peak −10.70 dBFS and
RMS −18.86 dBFS; measured steady amplitude ratio 0.1996. Beginning/end
windows confirm the fades. These measurements do not replace a listening pass.
A human sound and phone-playback check remains before publication. The root
README GIF stays unchanged. No short promotional edit has been produced.
