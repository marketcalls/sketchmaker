# Faceless Studio and Motion Graphics: shared architecture

> **Status note:** this document was written for the multi-user SaaS version. Credits, charges, refunds and plans no longer exist: wherever it mentions them, read "estimated USD" for prices and ignore the rest. The Faceless Studio pipeline described here is deferred; its code is in the reference repo.


Two features share one render engine:

- `/faceless`: character-driven faceless video and story studio (cast library,
  series, templates, script, storyboard, H3 Max clips, Eleven v4 voices,
  ElevenLabs Music, word-synced captions, render, packaging).
- `/motion-graphics`: animated text and data videos (kinetic typography, stat
  and number reveals, quotes, lists, charts, lower thirds, logo reveals).

Product decisions (owner, 2026-10-25): current server (2 vCPU, 4 GB), one
render at a time; Shorts up to 3 min (9:16) and long-form up to 15 min (16:9),
also 1:1 and 4:5; pay per step with a quote before each paid step and automatic
refunds on failure; characters from real people only with a consent
attestation; no Remotion (ffmpeg and Python only).

## 1. Render engine: `backend/app/render/`

Renderer-agnostic, pure Python plus the ffmpeg/ffprobe binaries (already
provisioned by server/common.sh). Pillow for drawing. Fonts are bundled under
`backend/app/render/fonts/` (OFL licensed, with their license files). No
network access during a render: every source is a local file.

### Timeline (pydantic, `app/render/timeline.py`)

All times are in seconds (floats); frames are derived (`fps`, default 30).

```
Timeline
  width: int, height: int, fps: int = 30
  duration: float | None            # None: end of the last clip or audio
  background: str = "#04060A"
  clips: list[Clip]                 # the visual base track, in order
  overlays: list[Overlay]           # drawn above clips by the frame renderer
  captions: CaptionTrack | None
  audio: list[AudioTrack]
  output: OutputSpec = {loudness_lufs: -14, crf: 20, preset: "veryfast"}
  grade: Grade | None               # colour grade of the base track (see below)

Clip
  start: float, duration: float
  kind: "image" | "video" | "color" | "gradient"
  src: str | None                   # local path for image/video
  color / gradient: str | list[str]
  fit: "cover" | "contain" = "cover"
  motion: "none" | "push_in" | "pull_out" | "pan_left" | "pan_right" = "none"
  transition_in: "cut" | "crossfade" | "dip_black" = "cut"
  transition_duration: float = 0.73   # 22 frames at 30 fps
  video_audio_gain_db: float | None   # None: mute the clip's own audio

Overlay (discriminated by kind)
  common: start, duration, enter: Anim, exit: Anim, z: int,
          anchor: "top"|"center"|"bottom"|"top_left"|..., safe_area: bool = True
  Anim: {type: "none"|"fade"|"slide_up"|"slide_down"|"slide_left"|"slide_right"|
         "scale_in"|"pop"|"typewriter"|"word_pop"|"mask_reveal",
         duration: float, easing: "linear"|"ease_out"|"ease_in_out"|"bezier_out"}
         # bezier_out = cubic-bezier(0.16, 1, 0.3, 1)
  kinds: title_card, stat_card, lower_third, text, quote, list, counter,
         chart (bar|line|pie, animated build), progress, shape, image_overlay,
         logo, outro_card, scrim (gradient), vignette
  style: font, weight, size (relative to a 1080-wide baseline, scaled by
         width/1080), color, accent, stroke, shadow, align, max_width

CaptionTrack
  words: list[{text, start, end, speaker?}]
  preset: "bold_pop" | "karaoke_box" | "minimal_lower" | "serif_story" | "none"
  words_per_group: int | None       # default 3 vertical, 6 landscape
  highlight: str, position: "lower" | "middle" | "upper"
  platform_safe_zone: "shorts" | "tiktok" | "reels" | "youtube"

Grade                               # app/render/grade.py, LUTs in app/render/looks/
  look: "neutral" | "warm_film" | "teal_orange" | "cool_clean" | "soft_pastel" |
        "mono_contrast" | "golden_hour" | "documentary_muted"
  strength: float = 1.0              # 0 to 1, blended with the ungraded picture
  match: bool = False                # pull clips with a match_ref toward that plate
  match_strength: float = 0.5        # (Reinhard transfer in Lab, baked into the LUT)
  # Image and video clips only (stills by Pillow Color3DLUT on the plate, video by
  # ffmpeg lut3d in the decode filter). Colour and gradient clips, overlays,
  # captions and end cards are never graded. Clip.grade = False opts a clip out;
  # Clip.match_ref is a local image. The .cube files are built offline by
  # app/render/looks/build_looks.py and committed. Motion Graphics sets no grade.

AudioTrack
  src: str, start: float = 0, gain_db: float = 0,
  role: "voice" | "music" | "sfx", fade_in: float = 0, fade_out: float = 0,
  loop: bool = False, trim_to_timeline: bool = True
  duck_under_voice: bool = False    # music ducks under voice (sidechain)
```

### API (`app/render/__init__.py`)

```
render_timeline(timeline, out_path, *, workdir, progress=None, cancel=None)
    -> RenderResult(path, duration, width, height, size_bytes)
preview_frame(timeline, t: float) -> bytes          # PNG, for storyboards
measure_media(path) -> {duration, width, height, has_audio}
```

Visual grammar ported from D:\sketch\story-telling (exact numbers): 22-frame
crossfades with overlapping ramps (no brightness dip: draw the outgoing clip
fully opaque under the incoming one), Ken Burns scale 1.02 to 1.12 with +/-14 px
drift alternating direction, bottom scrim plus vignette, title card entry 0 to
26 frames bezier_out, stat card with auto-shrink, outro card with glow.
Captions avoid each platform's UI zone (vertical: keep the bottom 260 px and
the right 120 px clear).

## 2. Script engine: `backend/app/services/storyscript/`

Pure functions over the existing LLM settings (APISettings default provider and
model through app/clients/litellm_client.py). No database writes.

```
list_templates() -> list[Template]
draft_script(db, *, template_id, idea, length_seconds, aspect, cast, series,
             facts=None, language="en", narrator_voice=None) -> Script
revise_scene(db, *, script, scene_id, instruction) -> Scene
describe_character(db, *, name, image_urls, notes=None) -> CharacterBible
originality_check(script, previous_scripts) -> OriginalityReport
compliance_check(script, cast) -> list[ComplianceFlag]
package(db, *, script, aspect) -> Packaging   # titles, description, tags,
                                               # chapters, thumbnail prompts,
                                               # disclosure advice
motion_graphics_draft(db, *, template_id, brief, data=None, length_seconds,
                      aspect) -> MotionSpec    # used by /motion-graphics
```

Script scenes carry: beat, narration (TTS-safe), dialogue lines with
character and emotion tag, shot plan (`still` | `clip` | `user_media` |
`card`), visual prompt, characters in shot, on-screen text, optional stat.

## 3. `/faceless` API (`/api/faceless`)

```
GET  /templates   GET /voices   GET /music-moods   GET /caption-styles
GET  /characters  POST /characters  GET|PUT|DELETE /characters/{id}
POST /characters/{id}/media           # upload image or video (signed, ours)
POST /characters/{id}/bible           # AI character bible (free, rate limited)
POST /characters/{id}/sheet           # reference sheet (paid, quoted)
GET  /series  POST /series  GET|PUT|DELETE /series/{id}
GET  /projects  POST /projects  GET|PUT|DELETE /projects/{id}
POST /projects/{id}/script            # draft (free, rate limited)
PUT  /projects/{id}/script            # save edits
POST /projects/{id}/scenes/{scene_id}/revise
POST /projects/{id}/scenes/{scene_id}/media   # bring your own image or video
GET  /projects/{id}/quote?step=storyboard|clips|voice|music|render|thumbnails&scene_ids=
POST /projects/{id}/steps/{step}      # body {scene_ids?, options?}: charges
GET  /projects/{id}/originality       GET /projects/{id}/compliance
POST /projects/{id}/package           # metadata free, thumbnails paid
```

Paid steps: quote, then charge on confirm, then run; anything that fails is
refunded under a row lock. Long steps run in the scheduler process (single
unit), which advances project steps every few seconds with fal submit and poll
(never blocking subscribe in a web worker) and claims renders one at a time
with `SELECT ... FOR UPDATE SKIP LOCKED`.

## 4. Prices (`app/services/credit_pricing.py`)

New keys, same engine and markup:

| Key | fal USD | Unit |
|---|---|---|
| `audio:eleven-v4:1k-chars` | 0.08 | 1,000 characters |
| `audio:elevenlabs-music:minute` | 0.60 | minute, rounded up per track |
| `render:minute` | 0.05 (compute estimate) | output minute |

Stills reuse `image:<model>:<res>` and `edit:<model>`; clips reuse
`video:h3-max:<res>` and `video:h3-max:reference-1k-tokens`.

## 5. Ownership and migrations

| Area | Files |
|---|---|
| Render engine | `backend/app/render/**` |
| Script engine | `backend/app/services/storyscript/**` |
| Faceless backend | `app/models/faceless.py`, `app/schemas/faceless.py`, `app/routers/faceless.py`, `app/services/faceless/**`, migration `d8e9f0a1b2c3` (down `c7d8e9f0a1b2`), small edits to main.py, credit_pricing.py, fal_cost_service.py, scheduler_service.py, gdpr and deletion services |
| Faceless frontend | `frontend/src/pages/user/faceless/**`, `frontend/src/components/faceless/**`, `frontend/src/api/faceless.ts`, `frontend/src/stores/facelessStore.ts`, App.tsx route, Sidebar entry |
| Presentations v2 | presentation and deck files; migration `f1a2b3c4d5e6` (down `d8e9f0a1b2c3`) |
| Motion graphics | `app/models/motion_graphics.py`, `app/routers/motion_graphics.py`, `app/services/motion_graphics/**`, migration `e9f0a1b2c3d4` (down `f1a2b3c4d5e6`), `frontend/src/pages/user/motion-graphics/**`, `frontend/src/components/motion-graphics/**` |
