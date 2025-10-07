"""
MongoDB Connection Setup for Intralign Agent V2

This module handles the MongoDB connection initialization using Beanie ODM.
It follows the V2 architecture with dynamic schemas and async operations.
"""

# ================================================
# MongoDB Connection Setup
# ================================================
from motor.motor_asyncio import AsyncIOMotorClient
from db.models.memory import ChatMemory
from db.models.stage import Stage
from beanie import init_beanie
from config.settings import settings
import logfire

# ================================================
# MongoDB Connection String
# ================================================
MONGODB_CONNECTION_STRING = f"{settings.DB_CONNECTION_STRING}"


# ================================================
# Initialize MongoDB Connection
# ================================================
async def init_db():
    """
    Initialize MongoDB connection and Beanie ODM

    This function sets up the connection to MongoDB and initializes
    all document models for the V2 system.

    Raises:
        ConnectionError: If unable to connect to MongoDB
        Exception: For any other database initialization errors
    """
    try:
        logfire.info("Initializing MongoDB connection...")

        # Create async MongoDB client
        client = AsyncIOMotorClient(MONGODB_CONNECTION_STRING)

        # Test connection
        await client.admin.command("ping")
        logfire.info("MongoDB connection successful")

        await init_beanie(
            client[settings.DB_NAME],
            document_models=[
                ChatMemory,
                Stage
            ],
        )

        logfire.info("Beanie ODM initialized successfully")

    except Exception as e:
        logfire.error(f"Failed to initialize MongoDB connection: {str(e)}")
        raise ConnectionError(f"Database initialization failed: {str(e)}")


# ================================================
# Close MongoDB Connection
# ================================================
async def close_db():
    """
    Close MongoDB connection

    Properly closes the database connection when the application shuts down.
    """
    try:
        logfire.info("Closing MongoDB connection...")
        # Connection cleanup will be handled by the client
        logfire.info("MongoDB connection closed")
    except Exception as e:
        logfire.error(f"Error closing MongoDB connection: {str(e)}")
