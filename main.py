"""
EVAA - Electra Voice AI Agent
Main entry point for the voice AI agent backend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from datetime import datetime
import logfire
from contextlib import asynccontextmanager
from db.connection import init_db, close_db

# ================================================
# Handlers
# ================================================
from handlers.conversation_handler import router as conversation_router
from handlers.brd_handler import router as brd_router


# ================================================
# Logfire Configuration
# ================================================
logfire.configure(token=settings.LOGFIRE_AUTH_TOKEN, inspect_arguments=True)
logfire.instrument_pydantic_ai()


# ============================================================================
# APPLICATION LIFECYCLE
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for startup and shutdown events
    """
    # Startup
    logfire.info("Starting EVAA - Electra Voice AI Agent server...")
    try:
        # Initialize database connection
        await init_db()
        logfire.info("Database connection initialized successfully")
    except Exception as e:
        logfire.error(f"Failed to initialize database: {str(e)}")
        raise

    yield

    # Shutdown
    logfire.info("Shutting down EVAA - Electra Voice AI Agent server...")
    try:
        await close_db()
        logfire.info("Database connection closed successfully")
    except Exception as e:
        logfire.error(f"Error closing database connection: {str(e)}")

# ================================================
# FastAPI Configuration
# ================================================
app = FastAPI(
    title="EVAA - Electra Voice AI Agent",
    description="Backend for voice AI agent that gathers information to create BRDs",
    version="1.0.0",
    lifespan=lifespan
)

# ================================================
# CORS Configuration
# ================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================================================
# Routers
# ================================================
app.include_router(conversation_router)
app.include_router(brd_router)

# ================================================
# Root Endpoint
# ================================================

@app.get("/")
async def root():
    return {
        "name": "EVAA - Electra Voice AI Agent", 
        "message": "Hello from EVAA - Electra Voice AI Agent backend",
        "version": "1.0.0",
        "created_at": str(datetime.now().isoformat())
        }
    
# ================================================
# Health Check Endpoint
# ================================================
@app.get("/health")
async def health_check():
    return {
        "name": "EVAA - Electra Voice AI Agent", 
        "status": "healthy",
        "version": "1.0.0",
        "created_at": str(datetime.now().isoformat())
        }

# ================================================
# Main Function
# ================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
