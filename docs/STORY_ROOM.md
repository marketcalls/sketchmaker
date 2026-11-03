# Story Room (`/stories`)

> **Status note:** this document was written for the multi-user SaaS version. Credits, charges, refunds and plans no longer exist: wherever it mentions them, read "estimated USD" for prices and ignore the rest. The hand-off to Faceless Studio is removed until Faceless returns.


A ChatGPT-style room where people develop a story or an ad with an AI
director, then turn it into video. One thread is one story. The assistant
replies in chat and, on every turn, condenses the conversation into a
structured **story document**: title, format, characters, environments and a
director's shot list (shot sizes, camera moves, B-roll, transitions such as
jump cuts). The document is what video is made from:

- **Full video**: the story becomes a Faceless Studio project (narration,
  voices, music, captions, render) at `/faceless/projects/{id}`.
- **Scene clips**: any shot becomes a cinematic clip in the existing clip maker
  (the previous `/stories` page, now the "Quick clip" tab), with the shot's
  director prompt and the character and environment photos as references.

Characters are the Faceless Studio characters (`faceless_character`, one
library). Environments are a new library (`story_environment`) used by story
threads and by the Faceless handoff.

## Product decisions (from the owner)

- `/stories` is rebuilt as the Story Room; the old single-clip page stays as
  the "Quick clip" tab of the same page.
- Both video paths, the user picks.
- **Every AI reply in the chat is charged** at the `story:chat-turn` price
  (Model pricing table, group `story`), reserved before the call and refunded
  if the model fails. Editing the document by hand, saving to the library,
  the handoff and clip prompts are free.
- One shared character and environment library.
- Scenes are written like a film or ad director: shot sizes, camera moves,
  B-roll, jump cuts and other transitions, sound cues, on-screen text.
- **Brief, treatment, images, video.** A short brief ("a 15 second ad where two
  people talk about the iPhone 18 at home") gets a complete production
  treatment in the FIRST reply, without asking questions first: the director
  makes sensible casting, setting and tone choices and lists them as
  assumptions in `open_questions`. Then the user creates and approves a
  reference image for every character and environment (generated inline with
  the same image models and prices as /generate, or uploaded / picked through
  the media window). Video is made after the images are approved.

## Data

Migration on top of `3f4a5b6c7d8e`.

```
story_thread
  id, user_id (fk user, index), title (200), format ("story" | "ad"),
  story (JSON, StoryDoc), story_version (int, default 0),
  memory (Text: rolling notes of decisions and preferences the model keeps),
  busy_until (DateTime, null: a turn is running until then),
  turns_used (int), credits_used (float),
  is_archived (bool), created_at, updated_at (index)

story_message
  id, thread_id (fk story_thread ondelete cascade, index), role ("user" | "assistant"),
  content (Text), story_version (int, null: the document version this reply produced),
  story_snapshot (JSON, null: StoryDoc after this reply, for "restore this version"),
  credits_charged (float), created_at (index)

story_environment
  id, user_id (fk user, index), name (120), description (Text),
  time_of_day (40), mood (120), style_notes (Text),
  media (JSON: list of {url, key, content_type, width, height}), is_archived,
  created_at, updated_at
```

Environment media live under the user's counted `images/{user_id}/` prefix
(storage quotas) and are removed when the environment is deleted.

## StoryDoc (pydantic, `app/services/story_room/models.py`)

```
StoryDoc
  format: "story" | "ad"
  title, logline, synopsis: str
  genre, tone, audience: str
  language: str = "en"
  aspect: "9:16" | "16:9" | "1:1" = "9:16"
  target_seconds: int (5..600) = 30
  ad: AdBrief | null          # format "ad", see AdBrief
  look: Look                  # visual_style, palette, lighting, camera_feel, music,
                              # register: "cinematic" | "ugc" | "documentary" | "animated"
                              # (default "cinematic")
  characters: list[CastEntry]
  environments: list[EnvEntry]
  products: list[Product]     # at most 4
  scenes: list[DocScene]      # at most 30
  open_questions: list[str]   # assumptions made and what the director still needs,
                              # then the plan checks (at most 16 in all)
  treatment: str              # the full production prompt, see "Treatment" below

AdBrief
  product, brand, offer, key_message, cta: str
  mandatories: list[str]      # legal lines and claims that must appear
  objective: "awareness" | "consideration" | "conversion" = "consideration"
  audience_mindset: str       # the viewer as a person with a current mindset
  proposition: str            # the single reason to buy, one sentence
  creativity: str             # "on-code", "twist" (default) or "wild"
  hook_variants: list[str]    # at most 3 alternate opening shots

Product
  key: "p1"...                # stable within the thread
  name, description: str
  must_keep: list[str]        # label text, colours, shape notes (at most 8)
  image_url: str = ""         # set only by the server: an uploaded photo (My Assets),
  image_approved: bool        # never a generated image

CastEntry
  key: "c1", "c2"...          # stable within the thread
  ref_id: int | null          # faceless_character id once saved or picked
  name, role, description, wardrobe, voice_notes: str
  image_prompt: str           # director-written prompt for the reference image:
                              # one person, full or three-quarter body, the exact
                              # wardrobe, neutral seamless background, soft light
  image_url: str | null       # set only by the server (approved image)
  image_approved: bool

EnvEntry
  key: "e1"...
  ref_id: int | null          # story_environment id
  name, description, time_of_day, mood: str
  image_prompt: str           # an empty establishing plate of the place, no people,
                              # the lighting and time of day of the story
  image_url: str | null       # set only by the server (approved image)
  image_approved: bool

DocScene
  id: "s1"...                 # stable across turns
  heading: str                # "INT. ROOFTOP CAFE - NIGHT"
  environment_key: str | null
  purpose: str                # the beat: hook, problem, reveal, CTA...
  summary: str
  shots: list[Shot]           # at most 12

Shot
  id: "s1.1"...               # stable across turns
  type: establishing | wide | medium | close_up | extreme_close_up | insert |
        over_the_shoulder | pov | two_shot | aerial | tracking | cutaway
  b_roll: bool
  camera: static | pan | tilt | dolly_in | dolly_out | tracking | handheld |
          crane | orbit | whip_pan | zoom | rack_focus
  duration_seconds: float (1..15)
  transition_in: cut | jump_cut | match_cut | smash_cut | cross_cut |
                 dissolve | whip_pan | j_cut | l_cut | fade_in | fade_out
  action: str                 # what we see, concrete and filmable
  characters: list[str]       # CastEntry keys in frame
  dialogue: list[{character_key, line, delivery}]
  voiceover: str
  on_screen_text: str
  sound: str                  # SFX or music cue
  props: list[str]            # Product keys in frame
  frame_position: str = ""    # who is where, facing which way ("Mira left facing right, Dev right")
  end_state: str = ""         # the pose or state the shot ends in; the next shot begins from it
  keyframe_url: str = ""      # set only by the server: the shot's first frame, approved,
  keyframe_approved: bool = False  # or made by "Make keyframe" and waiting for approval
```

Unknown enum values from the model are coerced to the nearest valid value
(register and objective too, with aliases such as "user generated" for ugc and
"performance" for conversion), ids are re-keyed if missing or duplicated,
props and characters that name no product or cast entry are dropped (or
matched by name), caps are enforced; the document is always valid when
stored. Documents stored before a field existed load with its default, and
`GET /threads/{id}` returns the normalized document, so the page always sees
every field.

`image_url`/`image_approved` (characters, environments, products) and
`keyframe_url`/`keyframe_approved` (shots) belong to the server:
`carry_images` copies them by key, shots by id, from the stored document onto
whatever the model or a PUT sends.

## Plan checks (`app/services/story_room/lint.py`)

`apply_lint` runs after every director turn (streamed or not) and every PUT.
It drops the previous checks from `open_questions` and appends the current
ones, each a plain sentence starting `Plan check: `, at most 6, after the
director's own questions. The director is told to fix what they point out and
leave them out of its own list. Checks:

- a shot's spoken words (dialogue plus voiceover) above about 2.5 a second;
- more than two characters in one shot;
- B-roll with lip-synced dialogue;
- an ad with no insert and no shot with a product in props;
- an ad whose last scene is not a CTA or brand beat and whose last shot does
  not carry the CTA text;
- an ad length other than 6, 15 or 30 s (60 on request), or shots that do not
  add up to it within half a second;
- an ad's spoken words above the placement's budget (6 s: 8 to 12, 15 s: 30
  to 35, 30 s: 60 to 70).

The Story tab shows them in the open questions list as warnings with "Fix".

## Treatment

`treatment` is regenerated on every turn so it always matches the shot list. It
is one cohesive production prompt a video model or a human crew can work from,
in this order (plain text with short headed sections):

1. One opening paragraph: format, length, look, who, what, where.
2. **Setting:** the place in concrete detail (furniture, light, palette, mood).
3. **Scene N (a-b seconds):** for each scene, the action and camera, then the
   dialogue as `Name (delivery): "line"`. Timecodes are consecutive and add up
   to `target_seconds`.
4. **Visual direction:** quality, aspect, camera movement, grading, lighting,
   depth of field.
5. **Audio direction:** language and accents, voices, music, ambience,
   lip sync.
6. **Important constraints:** consistent identities, wardrobe, place and
   product across shots; the exact number of characters; no distorted faces or
   hands, extra fingers, robotic dialogue; for a real brand or product, present
   it as a fictional concept advertisement, not an official one.

Example for "a 15 second ad where two people talk about the Apple iPhone 18 at
home": two professionals in their early 30s in a modern living room; Scene 1
(0-4 s) she notices the phone, slow push in, "Wait! Is that the new iPhone
18?"; Scene 2 (4-9 s) he turns it toward her, cut to a close-up of the phone;
Scene 3 (9-12 s) her reaction and a shared laugh; Scene 4 (12-15 s) product
hero shot on the coffee table with a slow orbit and the end line; then the
visual, audio and constraint sections.

## The turn (`app/services/story_room/director.py`)

Input to the model: the director system prompt (story or ad mode), the user's
library (character names, roles, likeness clauses; environment names and
descriptions), the current StoryDoc, `memory`, the last 12 messages, and the
new message. Output JSON: `{reply, story, memory, title}`. `reply` is plain
prose for the chat (short paragraphs, may list shots), `story` the full
updated document, `memory` the rolling summary (decisions, preferences,
rejected ideas; at most about 1,500 characters), which is how long threads
stay within the context window. Uses `storyscript.llm.complete_json` (the
platform LLM from APISettings).

The director prompt teaches: three-act or hook-problem-solution-CTA structure
for ads; coverage that opens each place on a master, holds one side of the
action line (written as `frame_position`), climbs the shot-size ladder and
punctuates with inserts and reactions; a pose chain (each shot's `end_state`
is where the next shot of the scene begins; exits, entrances and off-camera
changes happen at shot boundaries); at most two named characters per shot;
B-roll carries voiceover, never lip sync; cutting on action; jump cuts for
energy and time compression; match cuts and smash cuts for contrast; J and L
cuts for dialogue; shot durations that add up to `target_seconds`; every shot
concrete and filmable by an AI video model (one action, one camera move, at
most 15 seconds); on-screen text is an overlay, so its frame keeps the centre
band clear; a lasting costume change is a second character entry with its own
approved image, not a per-shot clause; continuity of wardrobe and place.

Registers (`look.register`): cinematic (default), documentary, animated, and
ugc: one creator, six spoken beats (hook, context, product moment, proof,
turn, close), phone-height framing, available light, real clutter, at most
one subtle handheld drift, no cinematic grammar, no invented claims.

Products: when the brief names one, the director adds it with `must_keep`
notes and lists it in `props` of the shots that show it. A product is never
generated: the user uploads a photo of the real thing (the image endpoint
refuses a gallery image for a product).

Ad mode (from the Scenario `scenario-video-ads` brief and storyboard
references): one objective with its grammar (awareness: brand film, codes
early, soft CTA; consideration: one provable claim demonstrated, benefit plus
CTA; conversion: hook in 3 s, product and text in frame one, plain offer,
explicit CTA); audience mindset, single-minded proposition, creativity dial;
the hero shot designed first; the last 2 to 3 s a brand beat (scene purpose
"cta": logo, tagline, CTA as on-screen text); placements of exactly 6, 15 or
30 s with their beats and voiceover word budgets; three `hook_variants`;
claims only from the user's own words.

## API (`/api/story-room`, feature switch `stories`, paid plans)

```
GET    /config                         {price_per_turn, keyframe:{price, model, resolution},
                                        limits:{max_threads, max_messages,
                                        max_message_chars, max_scenes, max_shots, max_products},
                                        enums:{shot_types, cameras, transitions, registers,
                                        objectives}}
GET    /threads?q=&archived=           [{id, title, format, updated_at, scenes, shots, busy}]
POST   /threads                        {format, title?, message?} -> Thread
GET    /threads/{id}                   Thread {id, title, format, story, story_version,
                                        busy, turns_used, credits_used, messages:[Message]}
PATCH  /threads/{id}                   {title?, is_archived?}
DELETE /threads/{id}
POST   /threads/{id}/messages          {message, expected_credits?} -> {user_message, assistant_message,
                                        story, story_version, credits_charged}
                                        402 insufficient credits, 409 busy, 503 model unavailable
POST   /threads/{id}/messages/stream   same body, checks and charge as /messages, answered as
                                        text/event-stream: user {user_message}, delta {text},
                                        status {text}, replace {text}, then done {user_message,
                                        assistant_message, story, story_version, credits_charged,
                                        title} or error {detail, status: 402 | 409 | 503};
                                        ": keep-alive" after 15 s of silence. Errors before the
                                        stream starts are ordinary JSON replies. The model writes
                                        the reply, a "===STORY_JSON===" line, then {story, memory,
                                        title}; an unusable JSON part falls back once to the
                                        non-streamed turn. The turn runs in a producer task: a
                                        disconnect only stops the stream, the reply is still saved
                                        and charged once.
PUT    /threads/{id}/story             {story, expected_version} -> {story, story_version}  (free)
POST   /threads/{id}/restore/{message_id}  -> {story, story_version}                     (free)
POST   /threads/{id}/cast/{key}/save   -> {story, character|environment}   save a proposed
                                        character (to faceless_character) or environment
                                        (to story_environment) and set its ref_id     (free)
POST   /threads/{id}/cast/{key}/link   {ref_id} -> {story}   use a library item for that key
GET    /threads/{id}/shots/{shot_id}/clip  -> {prompt, references:[{url, label}],
                                        start_frame: {url, label, kind} | null,
                                        duration_seconds, aspect}        (free)
                                        the prompt: shot and camera, action, "Frame:",
                                        "Begins: ... Ends: ..." (the previous shot's end_state
                                        in the same place, this shot's end_state), who is in
                                        frame (a short likeness for anyone whose picture is
                                        attached), products, setting, the look and a closing
                                        line in the document's register, dialogue, then the
                                        references with each image's role ("Image 1 is a
                                        character reference of Mira: use it for face, hair and
                                        outfit only; take nothing else from it..."). start_frame
                                        is the shot's approved keyframe, else the product photo
                                        of a hero product shot (no people), when the video family
                                        has image-to-video; references are empty then and Quick
                                        clip opens in First & Last Frame mode
GET    /threads/{id}/treatment/clip    -> {prompt, references, duration_seconds, aspect}
                                        the whole piece as ONE clip (pieces up to 15 s):
                                        the treatment fitted to the video model's prompt
                                        limit, approved images as references (max 4)
POST   /threads/{id}/cast/{key}/image  {image_id} | {asset_id} -> {story}
                                        approve a reference image: a gallery image the
                                        user generated (/generate, owner checked) or a My
                                        Assets image. The server resolves the URL (never
                                        accepts one), sets image_url and image_approved,
                                        and adds the image to the linked library item's
                                        media when ref_id is set                   (free)
                                        key p1 (a product): {asset_id} only, an upload of the
                                        real product; {image_id} is refused (400)
DELETE /threads/{id}/cast/{key}/image  -> {story}   clear the approval            (free)
POST   /threads/{id}/shots/{shot_id}/keyframe  {image_id} | {asset_id} | {made: true} -> {story}
                                        approve the shot's first frame (resolved as above);
                                        {made: true} approves the keyframe "Make keyframe"
                                        left on the shot                            (free)
DELETE /threads/{id}/shots/{shot_id}/keyframe  -> {story}  clear or discard it    (free)
POST   /threads/{id}/shots/{shot_id}/keyframe/generate  {expected_credits?}
                                        -> {story, story_version, asset, credits_charged}
                                        "Make keyframe" (see Keyframes below), charged at
                                        the edit model's price: 400 the shot is not ready
                                        (a sentence saying what to approve), 402 not enough
                                        credits, 403 free plan, 409 a turn is running or the
                                        price changed, 503 the provider failed (refunded)
POST   /threads/{id}/to-faceless       {template_id?} -> {project_id}    (free; unsaved
                                        characters are saved first)

GET    /environments  POST /environments  GET|PUT|DELETE /environments/{id}
POST   /environments/{id}/media        multipart image (PNG, JPEG, WebP, 25 MB, max 6)
DELETE /environments/{id}/media/{key}
```

Every error detail is a sentence written for people (see CLAUDE.md "Error text
shown to users").

## Frontend (`/stories`)

Page tabs: **Story Room** (default) and **Quick clip** (the existing clip maker).

Story Room layout (desktop): thread list on the left (New story or New ad,
search, archive), chat in the middle (messages, composer with the price per
reply on the send button, starter suggestions on an empty thread), the story
panel on the right with tabs **Story** (title, logline, format, aspect,
length, look with its register, ad brief with objective, proposition,
audience mindset, creativity and hook alternates; editable; open questions
with the plan checks as warnings; the **Treatment** shown in full with a copy
button), **Cast** (characters and environments: save to library, pick from
library; each card shows its image prompt (editable), "Generate image" which
runs the regular image generation inline (`generateApi.generateImage`, model
and price as on /generate, 2 options) and "Approve" on a result, or a picture
from the media window; approved images show a check; then **Products**: name,
description, must-keep notes and a photo through the media window, uploaded to
My Assets and approved, never generated), **Shot list** (scenes as script headings, shots as rows with type,
camera, transition, B-roll, product, keyframe and duration badges, frame position
and end state; edit inline, including products in frame and an optional keyframe:
"Make keyframe" with its price on the button, disabled with the reason while a
character or product in the shot has no approved image, a placeholder while it
is made, then Approve, Make another or Discard; or a still uploaded or picked
through the media window. A scene with two or more shots ready for one shows a
"Keyframes n" button that confirms the total first and makes them one after
another), and **Make
video** as three steps: 1. Treatment ready, 2. Images approved (n of m), 3.
Video: "One take" for pieces up to 15 s (Quick clip prefilled from
`/treatment/clip`), "Scene clips" (each shot with "Make clip", prefilled from
`/shots/{id}/clip`), and "Full video" to Faceless Studio. The video buttons
ask for confirmation while images are still unapproved. Mobile:
the three columns become tabs.

## Keyframes (`app/services/story_room/keyframe.py`)

"Make keyframe" turns one shot into a still, its first frame, made from the
images the server approved in the document (the Scenario storyboard rule:
approved panels become first frames). The clip of the shot then opens on it
(image-to-video) once the user approves it.

- **Model and price**: Nano Banana 2.1 edit (`google/nano-banana-2.1/edit`,
  up to 14 references addressed by order) at 1K, one output, priced at its
  existing `edit:google/nano-banana-2.1/edit` key (`credit_pricing.edit_credits`;
  superadmins change it in the Model pricing table). No new provider or key.
  `GET /config` reports the price; the button shows it and the request sends
  it as `expected_credits` (409 when it changed).
- **References**: only approved images, in this order: the characters in
  frame, the products in the shot's props, the scene's place. Library photos
  are never sent. Each picture gets one job and what not to take from it:
  "Image 1 is Mira: use it for Mira's face, hair and outfit only; take nothing
  else from it, not its background, pose, framing or light", "Image 3 is the
  real product, Fizz Can: keep its label, shape and colour exactly (...); take
  nothing else from it", "Image 4 is the place, Kitchen: the place only, no
  people from it; use its layout, surfaces and light".
- **Prompt**: then the shot size and angle, the camera move it opens, the
  action, the starting pose (the previous shot's end state in the same place),
  `frame_position`, the exact number of people in frame with a few words each,
  the products, the setting, the look and a closing line in the document's
  register (a phone frame for ugc), room for on-screen text when the shot has
  any, and "One single frame, not a collage, grid or split screen. No text, no
  captions, no watermark". Output at the document's aspect.
- **Refused before any charge** (400, the same sentence the button shows):
  a character in frame without an approved image, a product in the shot
  without an approved photo (a product is never generated), a shot with no
  character, product or approved place, or more pictures than the model takes.
- **Charge**: `reserve_credits` at the quote before the request, refunded when
  fal fails, times out (150 s, the request is cancelled), returns nothing or a
  safety-blanked image, or the result is not an image. One request is one
  image: nothing is ever retried automatically, and "Make another" is a new,
  paid request. The fal request runs in the threadpool, so the web worker's
  event loop is not held; the browser waits up to 200 s, and if the proxy
  gives up first the page says so and reloads the story later, since the
  server still saves the keyframe.
- **Result**: saved to My Assets (`source: "keyframe"`, the user's counted
  `images/{user_id}/` folder, deleted from there like any asset), recorded in
  usage history (`story_keyframe`), and set as the shot's `keyframe_url` with
  `keyframe_approved` false. Approve (`{made: true}`), Make another or Discard
  (DELETE). A director turn saved after the keyframe keeps it: turns copy the
  server-owned image fields from the stored document, not from the one the
  turn started on.
