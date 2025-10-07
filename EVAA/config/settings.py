"""
Application settings and configuration.
"""
# ================================================
# Application Settings
# ================================================
from pydantic_settings import BaseSettings
from typing import Optional


# ================================================
# Settings Class
# ================================================
class Settings(BaseSettings):
    """Application settings."""
    
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
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# ================================================
# Settings Instance
# ================================================
settings = Settings()
