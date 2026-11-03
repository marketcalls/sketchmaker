"""The core Faceless Studio shares with other features (/api/faceless).

The Faceless project pipeline is deferred. What stays is what Motion Graphics, My Assets
and Story Room use:

  catalog   voices, music moods, caption styles, visual styles, limits, consent text,
            default models
  activity  activity log (the consent audit trail) and database-backed hourly caps
  scenes    script helpers: scene timing, voice lines, word timings
  consent   real person consent gate and character briefs
  media     fal adapter (submit, status, result), downloads through url_fetch, storage,
            ffmpeg helpers, upload validation
  prompts   prompt building for stills, clips, thumbnails and character sheets
  views     response shapes for characters
"""
