"""
Stage model for managing information gathering stages.
"""

from beanie import Document
from pydantic import Field
from datetime import datetime


class Stage(Document):
    """Stage model for information gathering process."""
    
    name: str = Field(..., description="Stage name")
    description: str = Field(..., description="Stage description")
    goal: str = Field(..., description="Stage goal")
    order: int = Field(..., description="Stage order")
    is_active: bool = Field(default=True, description="Whether stage is active")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "stages"
        indexes = [
            "order",
            "is_active",
            "created_at"
        ]
    