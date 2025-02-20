from enum import Enum
from pydantic import BaseModel
from typing import Optional


class WebhookType(str, Enum):
    audio_bytes = 'audio_bytes'
    audio_bytes_websocket = 'audio_bytes_websocket'
    realtime_transcript = 'realtime_transcript'
    memory_created = 'memory_created',
    day_summary = 'day_summary'


class TwitterCredentials(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: Optional[int] = None
    scope: Optional[str] = None
    token_type: Optional[str] = None
    created_at: Optional[int] = None


class User(BaseModel):
    uid: str
    twitter_credentials: Optional[TwitterCredentials] = None
