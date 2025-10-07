"""
Chat memory model for storing conversation history.
"""

from beanie import Document
from pydantic import Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class ChatMemory(Document):
    """Chat memory model for storing conversation history."""
    
    session_id: str = Field(..., description="Session identifier")
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="Chat messages history")
    current_stage_id: Optional[str] = Field(None, description="Current stage ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "chat_memories"
        indexes = [
            "session_id",
            "created_at",
            "updated_at"
        ]

    
