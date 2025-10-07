"""
WebSocket handler for real-time communication with the voice AI agent.
"""

from fastapi import WebSocket, APIRouter
from models.conversation_model import ConversationModel
import logfire

router = APIRouter()

@router.websocket("/conversation/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    Websocket endpoint for conversation.
    """
    try:
        await websocket.accept()
        logfire.info(f"Websocket accepted for session {session_id}")
        conversation_model = ConversationModel(websocket, session_id)
        await conversation_model.run(session_id)
    except Exception as e:
        logfire.error(f"Error in websocket endpoint: {e}")
        # Don't try to close the connection if it's already closed
        try:
            if websocket.client_state.name != "DISCONNECTED":
                await websocket.close(code=1011, reason="Internal Server Error")
        except Exception as close_error:
            logfire.warning(f"Could not close websocket: {close_error}")