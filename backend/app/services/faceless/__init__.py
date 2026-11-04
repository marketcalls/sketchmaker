"""Faceless Studio (/api/faceless), and the core other features share with it.

Motion Graphics, My Assets and Story Room use catalog, activity, scenes, consent, media and
the character views.

  catalog       voices, music moods, caption styles, visual styles, limits, consent text,
                default models
  activity      activity log (the consent audit trail) and database-backed hourly caps
  scenes        script helpers: scene timing, voice lines, word timings
  consent       real person consent gate and character briefs
  media         fal adapter (submit, status, result), downloads through url_fetch, storage,
                ffmpeg helpers, upload validation
  prompts       prompt building for stills, clips, thumbnails and character sheets
  schemas       request bodies of the pipeline
  scripts       glue to the script engine: drafts, versions, compliance, originality
  pricing       step plans: what a step will do and its estimate in USD
  orchestrator  step runs: start, advance in the scheduler, record what landed
  script_job    long-form drafts on a scheduler thread
  render_job    the render step, under the shared render slot
  grade         colour grade and plate matching of a render
  scheduler     the entry points registered in scheduler_service
  views         response shapes
"""
