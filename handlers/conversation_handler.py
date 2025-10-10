"""
FastAPI WebSocket Router for Voice AI Agent Conversations

This module provides the main WebSocket endpoint for real-time communication
with the voice AI agent. It handles WebSocket connections, session management,
and orchestrates the conversation flow through the ConversationModel.

Key Features:
- WebSocket connection management with proper error handling
- Session-based conversation routing
- Automatic cleanup and resource management
- Professional error handling and logging

Example:
    The endpoint is automatically registered with FastAPI and handles
    WebSocket connections at /conversation/{session_id}
    
    Frontend connection:
    const ws = new WebSocket('ws://localhost:8000/conversation/my-session-id');
"""

from fastapi import WebSocket, APIRouter, WebSocketException
from typing import Optional
import logfire

from models.conversation_model import ConversationModel

# Create FastAPI router for WebSocket endpoints
router = APIRouter()


@router.websocket("/conversation/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket endpoint for real-time voice AI agent conversations.
    
    This endpoint establishes a WebSocket connection for a specific session
    and manages the entire conversation lifecycle including:
    - WebSocket connection acceptance and validation
    - Conversation model initialization and execution
    - Error handling and graceful connection closure
    - Resource cleanup on connection termination
    
    Args:
        websocket: FastAPI WebSocket connection object
        session_id: Unique identifier for the conversation session
        
    Raises:
        WebSocketException: If connection cannot be established or maintained
        ValueError: If session_id is invalid or empty
        
    Example:
        Frontend JavaScript connection:
        ```javascript
        const ws = new WebSocket('ws://localhost:8000/conversation/user-123');
        ws.onopen = () => console.log('Connected to voice AI agent');
        ```
    """
    # Validate session_id
    if not session_id or not session_id.strip():
        logfire.error("Invalid session_id provided to WebSocket endpoint")
        await websocket.close(code=1008, reason="Invalid session ID")
        return
        
    session_id = session_id.strip()
    logfire.info(f"WebSocket connection request received for session: {session_id}")
    
    try:
        # Accept WebSocket connection
        await websocket.accept()
        logfire.info(f"WebSocket connection accepted for session: {session_id}")
        
        # Initialize and run conversation model
        conversation_model = ConversationModel(websocket, session_id)
        await conversation_model.run(session_id)
        
        logfire.info(f"Conversation completed for session: {session_id}")
        
    except WebSocketException as ws_error:
        logfire.error(f"WebSocket error in session {session_id}: {ws_error}")
        await _safe_close_websocket(websocket, code=ws_error.code, reason=str(ws_error))
        raise
        
    except Exception as e:
        logfire.error(f"Unexpected error in WebSocket endpoint for session {session_id}: {e}")
        await _safe_close_websocket(websocket, code=1011, reason="Internal Server Error")
        raise WebSocketException(code=1011, reason=f"Internal server error: {e}")


async def _safe_close_websocket(
    websocket: WebSocket, 
    code: int = 1011, 
    reason: str = "Internal Server Error"
) -> None:
    """
    Safely close WebSocket connection with proper error handling.
    
    This helper function ensures that WebSocket connections are closed
    gracefully without raising additional exceptions during cleanup.
    
    Args:
        websocket: WebSocket connection to close
        code: WebSocket close code (default: 1011 for internal error)
        reason: Close reason message
    """
    try:
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close(code=code, reason=reason)
            logfire.info(f"WebSocket connection closed with code {code}: {reason}")
    except Exception as close_error:
        logfire.warning(f"Error closing WebSocket connection: {close_error}")