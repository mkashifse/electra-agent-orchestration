"""
WebSocket Communication Handler for Voice AI Agent

This module provides a comprehensive WebSocket handler for real-time communication
between the voice AI agent backend and frontend clients. It manages message
serialization, event handling, and connection state management.

Key Features:
- Real-time bidirectional communication
- Message validation and serialization
- Event-based message routing
- Connection state management
- Error handling and recovery
- Session management support

Example:
    handler = WebSocketHandler(websocket)
    await handler.send_flag(Flag.LISTENING)
    async for message in handler.receive_messages():
        # Process incoming messages
        pass
"""

import json
from typing import AsyncGenerator, Dict, Any, List, Optional, Union
from fastapi import WebSocket, WebSocketException
import logfire

from schemas.websocket_schema import Flag, webSocketAgentOutput, WebSocketInput, WebSocketOutput


class WebSocketHandler:
    """
    WebSocket communication handler for voice AI agent conversations.
    
    This class provides a high-level interface for WebSocket communication
    between the backend and frontend, handling message serialization,
    validation, and event routing.
    
    Attributes:
        websocket: FastAPI WebSocket connection object
    """
    
    def __init__(self, websocket: WebSocket) -> None:
        """
        Initialize WebSocket handler.
        
        Args:
            websocket: FastAPI WebSocket connection object
            
        Raises:
            ValueError: If websocket is None or invalid
        """
        if websocket is None:
            raise ValueError("WebSocket connection cannot be None")
            
        self.websocket: WebSocket = websocket
        logfire.info("WebSocketHandler initialized")

    async def receive_messages(self) -> AsyncGenerator[WebSocketInput, None]:
        """
        Asynchronously receive and validate messages from WebSocket.
        
        This method continuously listens for incoming WebSocket messages,
        validates them against the WebSocketInput schema, and yields
        validated message objects.
        
        Yields:
            WebSocketInput: Validated message object containing audio_chunk or text_prompt
            
        Raises:
            WebSocketException: If message parsing fails or connection is lost
            StopAsyncIteration: When WebSocket connection is closed
            
        Example:
            async for message in handler.receive_messages():
                if message.audio_chunk:
                    # Process audio data
                elif message.text_prompt:
                    # Process text input
        """
        while True:
            try:
                # Receive raw message data
                message_data: str = await self.websocket.receive_text()
                logfire.debug(f"Received WebSocket message: {len(message_data)} characters")
                
                # Parse JSON data
                try:
                    parsed_data: Dict[str, Any] = json.loads(message_data)
                except json.JSONDecodeError as json_error:
                    logfire.error(f"Invalid JSON in WebSocket message: {json_error}")
                    await self.send_error(f"Invalid JSON format: {json_error}")
                    continue
                
                # Validate message structure
                try:
                    message: WebSocketInput = WebSocketInput(**parsed_data)
                    logfire.debug(f"Message validated successfully: {type(message).__name__}")
                    yield message
                except Exception as validation_error:
                    logfire.error(f"Message validation failed: {validation_error}")
                    await self.send_error(f"Message validation error: {validation_error}")
                    continue
                    
            except WebSocketException as ws_error:
                logfire.error(f"WebSocket error in receive_messages: {ws_error}")
                raise
            except Exception as e:
                logfire.error(f"Unexpected error in receive_messages: {e}")
                await self.send_error(f"Message processing error: {e}")
                raise WebSocketException(code=1011, reason=f"Message processing failed: {e}")


    async def send_flag(self, flag: Flag) -> None:
        """
        Send status flag to frontend client.
        
        This method sends a status flag (LISTENING, THINKING, etc.) to the
        frontend to indicate the current state of the conversation system.
        
        Args:
            flag: Status flag to send to frontend
            
        Raises:
            WebSocketException: If message cannot be sent
        """
        try:
            output = WebSocketOutput(flag=flag, data=None)
            await self.websocket.send_text(output.model_dump_json())
            logfire.debug(f"Status flag sent to frontend: {flag}")
        except Exception as e:
            logfire.error(f"Failed to send flag {flag}: {e}")
            raise WebSocketException(code=1011, reason=f"Failed to send flag: {e}")

    async def send_output(self, output: webSocketAgentOutput, flag: Flag) -> None:
        """
        Send agent output with status flag to frontend.
        
        This method sends both the agent's response data and a status flag
        to the frontend client.
        
        Args:
            output: Agent output data to send
            flag: Status flag indicating current system state
            
        Raises:
            WebSocketException: If message cannot be sent
        """
        try:
            websocket_output = WebSocketOutput(flag=flag, data=output)
            await self.websocket.send_text(websocket_output.model_dump_json())
            logfire.debug(f"Agent output sent with flag {flag}")
        except Exception as e:
            logfire.error(f"Failed to send agent output: {e}")
            raise WebSocketException(code=1011, reason=f"Failed to send output: {e}")

    async def send_next_stage(self, next_stage_data: Dict[str, Any]) -> None:
        """
        Send next stage information to frontend.
        
        This method notifies the frontend about stage transitions in the
        conversation flow.
        
        Args:
            next_stage_data: Dictionary containing next stage information
            
        Raises:
            WebSocketException: If message cannot be sent
        """
        try:
            message = {
                "event": "next_stage",
                "next_stage_data": next_stage_data
            }
            await self.websocket.send_text(json.dumps(message))
            logfire.info(f"Next stage notification sent: {next_stage_data.get('name', 'Unknown')}")
        except Exception as e:
            logfire.error(f"Failed to send next stage data: {e}")
            raise WebSocketException(code=1011, reason=f"Failed to send next stage: {e}")

    async def send_error(self, error: str) -> None:
        """
        Send error message to frontend and close connection.
        
        This method sends an error message to the frontend and then
        gracefully closes the WebSocket connection.
        
        Args:
            error: Error message to send to frontend
            
        Raises:
            WebSocketException: Always raises with the provided error message
        """
        try:
            error_message = {
                "event": "error",
                "error": error
            }
            await self.websocket.send_text(json.dumps(error_message))
            logfire.error(f"Error message sent to frontend: {error}")
        except Exception as send_error:
            logfire.warning(f"Could not send error message to frontend: {send_error}")
        
        # Close WebSocket connection
        try:
            if self.websocket.client_state.name != "DISCONNECTED":
                await self.websocket.close(code=1011, reason=error)
                logfire.info("WebSocket connection closed due to error")
        except Exception as close_error:
            logfire.warning(f"Could not close WebSocket connection: {close_error}")
        
        raise WebSocketException(code=1011, reason=error)

    async def end_session(self) -> None:
        """
        End the current session and close WebSocket connection.
        
        This method sends an end_session event to the frontend and then
        gracefully closes the WebSocket connection.
        """
        try:
            end_message = {"event": "end_session"}
            await self.websocket.send_text(json.dumps(end_message))
            logfire.info("End session message sent to frontend")
        except Exception as send_error:
            logfire.warning(f"Could not send end session message: {send_error}")
        
        try:
            if self.websocket.client_state.name != "DISCONNECTED":
                await self.websocket.close()
                logfire.info("WebSocket connection closed for session end")
        except Exception as close_error:
            logfire.warning(f"Could not close WebSocket connection: {close_error}")

    async def send_all_stages(self, stages: List[Any]) -> None:
        """
        Send all conversation stages to frontend.
        
        This method serializes stage objects and sends them to the frontend
        for display and navigation purposes.
        
        Args:
            stages: List of stage objects to send
            
        Raises:
            WebSocketException: If message cannot be sent
        """
        try:
            # Convert Stage objects to dictionaries for JSON serialization
            stages_data: List[Dict[str, Any]] = []
            for stage in stages:
                if hasattr(stage, 'model_dump_json'):
                    # If it's a Pydantic model, use model_dump_json()
                    stages_data.append(json.loads(stage.model_dump_json()))
                elif hasattr(stage, 'dict'):
                    # If it's a Beanie document, use dict()
                    stages_data.append(stage.dict())
                else:
                    # Fallback: convert to dict manually
                    stages_data.append({
                        "id": str(stage.id) if hasattr(stage, 'id') else None,
                        "name": stage.name if hasattr(stage, 'name') else "",
                        "description": stage.description if hasattr(stage, 'description') else "",
                        "goal": stage.goal if hasattr(stage, 'goal') else "",
                        "order": stage.order if hasattr(stage, 'order') else 0,
                        "is_active": stage.is_active if hasattr(stage, 'is_active') else True
                    })
            
            message = {
                "event": "all_stages",
                "stages": stages_data
            }
            await self.websocket.send_text(json.dumps(message))
            logfire.info(f"All stages sent to frontend: {len(stages_data)} stages")
            
        except Exception as e:
            logfire.error(f"Failed to send all stages: {e}")
            raise WebSocketException(code=1011, reason=f"Failed to send stages: {e}")

    async def send_user_transcription(self, transcription: str) -> None:
        """
        Send user transcription to frontend for display.
        
        This method sends the transcribed text to the frontend so users
        can see what was recognized from their speech input.
        
        Args:
            transcription: Transcribed text to send to frontend
            
        Raises:
            WebSocketException: If message cannot be sent
        """
        try:
            message = {
                "event": "user_transcription",
                "transcription": transcription
            }
            await self.websocket.send_text(json.dumps(message))
            logfire.debug(f"User transcription sent: {transcription[:50]}...")
        except Exception as e:
            logfire.error(f"Failed to send user transcription: {e}")
            raise WebSocketException(code=1011, reason=f"Failed to send transcription: {e}")

    async def send_chat_history(self, chat_history: Dict[str, List[Dict[str, str]]], current_stage: Optional[str] = None) -> None:
        """
        Send chat history to frontend when session connects.
        
        This method sends the conversation history grouped by stages to the
        frontend for display and context.
        
        Args:
            chat_history: Dictionary of chat history grouped by stage names
            current_stage: Current stage name (optional)
            
        Raises:
            WebSocketException: If message cannot be sent
        """
        try:
            message = {
                "event": "chat_history",
                "chat": chat_history,
                "current_stage": current_stage
            }
            await self.websocket.send_text(json.dumps(message))
            logfire.info(f"Chat history sent to frontend: {len(chat_history)} stages, current: {current_stage}")
        except Exception as e:
            logfire.error(f"Failed to send chat history: {e}")
            raise WebSocketException(code=1011, reason=f"Failed to send chat history: {e}")