# LinkedIn promotional edit — 42 seconds

Primary source: `../assets/skout-demo-final.mp4`. Source times below are from
that actual approved recording; no scanner or test is rerun for this edit.

| Output time | Source time | Visual | Viewer takeaway |
| --- | --- | --- | --- |
| 0–4s | Branded card | Passing evals hook; second question emphasized in coral | Existing evals may miss something important. |
| 4–9s | Branded card | Meet Skout Scan | Open-source agent eval coverage discovery. |
| 9–12.48s | 18–21.48s | Actual validator finding with original red outline | Potential gap identified. |
| 12.48–17s | 25–29.52s | Actual review source evidence, new coral outline | Explicit ModelRetry failure path; explanation grounded in source. |
| 17–19s | 33.5–35.5s | Real add_eval input | Engineer records intent; no test is generated. |
| 19–23s | 44.2–48.2s | Engineer activates supplied solution | Separate test change. |
| 23–27s | 49–53s | pytest.raises(ModelRetry), original amber outline | Eval verifies the expected failure outcome. |
| 27–30s | 58.5–61.5s | Actual rescan summaries | New evidence is assessed. |
| 30–35s | 74–79s | Persisted resolution helper, original green outline and payoff | Same finding ID, resolved/covered, matched test visible. |
| 35–42s | Branded CTA card | Product, invitation and website/GitHub URLs | Try Skout on a real agent repository. |

Footage is not sped up or frozen. Cuts remove waiting time. The primary source's
1440×1000 terminal viewport is preserved in full and scaled to 1080×750; only
its separate 160 px caption band is replaced. The terminal sits at y=260 inside
1080×1350. Captions live below it; headlines live above. The resolution helper
remains explicitly labelled read-only and is not presented as a built-in CLI.

Brand cards use warm ivory #FAF9F6, charcoal #202323, coral #F06445 and restrained
muted lavender #E9E4F5. Original red, amber and green outlines remain part of the
actual source footage. One new 4 px coral outline highlights source evidence,
positioned after inspecting source frames. No overlapping replacement outlines.

Editable sources: `edit.json` (cuts/cards/headlines), `captions.srt`,
`annotations.json`, and generated `overlays.ass`. Hook and CTA copy are editable
in the build script. Intro, captions and CTA are editorial copy, not CLI output.

Music: preserved Minimal Techno 01, `../assets/music/skout-upbeat.mp3`;
license/provenance in `../assets/music/UPBEAT-LICENSE.md`. Mixkit's Stock Music
Free License permits web/social promotional videos, checked again 2026-10-12:
https://mixkit.co/license/modal/musicFree/. Use 20% gain, 1-second opening fade,
3-second ending fade. No looping, voiceover, source audio cuts or new music.
If music/provenance is unavailable, both exports are silent and explicitly reported.

Build from the repository root: `sh demo/scripts/build_linkedin_video.sh`.
The build generates full/half-size review frames and a five-frame contact sheet.
Human listening and native LinkedIn/phone preview remain final publication checks.
