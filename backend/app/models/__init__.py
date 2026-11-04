"""Database models. Importing this package registers every table on Base.metadata."""

from app.models.api import AIModel, APIProvider, APISettings
from app.models.asset import UserAsset
from app.models.content import (
    GenerationJob,
    Image,
    LipSyncJob,
    StoryGenerationJob,
    SubtitleJob,
    Video,
    VideoGenerationJob,
)
from app.models.faceless import (
    FacelessActivity,
    FacelessCharacter,
    FacelessProject,
    FacelessScriptVersion,
    FacelessSeries,
    FacelessStepRun,
)
from app.models.llm_usage import LLMUsage
from app.models.motion_graphics import MGActivity, MGBrandKit, MGJob, MGProject
from app.models.notification import Notification, NotificationType
from app.models.story_room import StoryEnvironment, StoryMessage, StoryThread
from app.models.usage_log import UsageLog
from app.models.user import User

__all__ = [
    "AIModel",
    "APIProvider",
    "APISettings",
    "FacelessActivity",
    "FacelessCharacter",
    "FacelessProject",
    "FacelessScriptVersion",
    "FacelessSeries",
    "FacelessStepRun",
    "GenerationJob",
    "Image",
    "LLMUsage",
    "LipSyncJob",
    "MGActivity",
    "MGBrandKit",
    "MGJob",
    "MGProject",
    "Notification",
    "NotificationType",
    "StoryEnvironment",
    "StoryGenerationJob",
    "StoryMessage",
    "StoryThread",
    "SubtitleJob",
    "UsageLog",
    "User",
    "UserAsset",
    "Video",
    "VideoGenerationJob",
]
