"""Story Room (/stories): chat with an AI director that keeps a structured
story document, then turn it into video (docs/STORY_ROOM.md).

models    StoryDoc and its normalizer (the stored document is always valid)
director  the chat turn (platform LLM through storyscript.llm.complete_json)
clip      director prompts for one shot or the whole piece in one take
keyframe  "Make keyframe": a shot's first frame from the approved images (edit model)
library   characters (faceless_character) and environments (story_environment)
"""
