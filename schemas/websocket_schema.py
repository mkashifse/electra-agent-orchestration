"""
WebSocket message schemas.
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any
from enum import Enum


class WebSocketInput(BaseModel):
    """Input schema for WebSocket messages."""
    audio_chunk: Optional[str] = None  # Base64 encoded audio
    text_prompt: Optional[str] = None  # Text input
    session_id: str  # Session identifier

class Flag(Enum):
    """Flag enum for WebSocket messages."""
    THINKING = "thinking"
    LISTENING = "listening"


class webSocketAgentOutput(BaseModel):
    """Agent output schema for WebSocket messages."""
    response: str  # Agent response text
    next_stage: bool  # Whether to move to next stage
    next_stage_data: Optional[Dict[str, Any]] = None  # Next stage information
    current_stage: Optional[str] = None  # Current stage name
    follow_up_count: Optional[int] = None  # Number of follow-ups asked

class WebSocketOutput(BaseModel):
    """Output schema for WebSocket messages."""
    flag: Flag
    data: Optional[webSocketAgentOutput] = None


class WebSocketError(BaseModel):
    """Error schema for WebSocket messages."""
    error: str
    message: str
    session_id: str
