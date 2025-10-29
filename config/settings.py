"""
Application settings and configuration.
"""
# ================================================
# Application Settings
# ================================================
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


# ================================================
# Settings Class
# ================================================
class Settings(BaseSettings):
    """Application settings."""
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore extra fields not defined in the model
    )
    
    # Database
    DB_CONNECTION_STRING: str = "mongodb://localhost:27017"
    DB_NAME: str = "evaa-dev"
    
    # Deepgram
    DEEPGRAM_API_KEY: str
    
    # Groq
    GROQ_API_KEY: str

    # Logfire
    LOGFIRE_AUTH_TOKEN: str
    
    # ElevenLabs (for future TTS)
    ELEVENLABS_API_KEY: Optional[str] = None
    
    # CORS
    ALLOWED_ORIGINS: list[str] = ["*"]

# ================================================
# Settings Instance
# ================================================
settings = Settings()
