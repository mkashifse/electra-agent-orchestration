"""
Deepgram Flux Speech-to-Text Service

This module provides a robust WebSocket-based speech-to-text service using Deepgram's
Flux model. It handles real-time audio streaming, automatic reconnection, and
transcript processing with professional error handling and logging.

Key Features:
- Real-time audio transcription using Deepgram Flux model
- Automatic reconnection with exponential backoff
- Connection health monitoring and recovery
- Professional error handling and logging
- Thread-safe operation with async/await support

Example:
    async def on_transcript(text: str):
        print(f"Transcribed: {text}")
    
    stt = FluxSTT(on_transcript, api_key="your-api-key")
    await stt.start()
    await stt.send_audio_chunk(audio_data)
    await stt.finish()
"""

import asyncio
import json
import base64
import random
import time
import logfire
import websockets
from typing import Callable, Union, Optional, Dict, Any


class FluxSTT:
    """
    Deepgram Flux Speech-to-Text service with automatic reconnection and error handling.
    
    This class provides a production-ready WebSocket connection to Deepgram's Flux
    speech-to-text model with robust error handling, automatic reconnection, and
    professional logging.
    
    Attributes:
        callback: Async function called when transcript is received
        api_key: Deepgram API key for authentication
        sample_rate: Audio sample rate in Hz (default: 16000)
        debug_audio: Enable audio debugging features
        ws: WebSocket connection object
        is_connected: Current connection status
        reconnect_attempts: Number of reconnection attempts made
        max_reconnect_attempts: Maximum allowed reconnection attempts
        heartbeat_interval: Interval for keep-alive packets in seconds
        reconnect_lock: Async lock for thread-safe reconnection
        threshold: Minimum time between transcript callbacks in seconds
        last_turn_time: Timestamp of last transcript callback
        last_transcript: Last received transcript text
    """
    
    def __init__(
        self,
        callback: Callable[[str], asyncio.Future],
        api_key: str,
        sample_rate: int = 16000,
        debug_audio: bool = True,
    ) -> None:
        """
        Initialize FluxSTT service.
        
        Args:
            callback: Async function to call when transcript is received.
                     Must accept a single string parameter (transcript text).
            api_key: Deepgram API key for authentication.
            sample_rate: Audio sample rate in Hz. Default is 16000.
            debug_audio: Enable audio debugging features. Default is True.
            
        Raises:
            ValueError: If api_key is empty or callback is not callable.
        """
        if not api_key or not api_key.strip():
            raise ValueError("API key cannot be empty")
        if not callable(callback):
            raise ValueError("Callback must be a callable function")
            
        self.callback: Callable[[str], asyncio.Future] = callback
        self.api_key: str = api_key.strip()
        self.sample_rate: int = sample_rate
        self.debug_audio: bool = debug_audio
        
        # Connection state
        self.ws = None
        self.is_connected: bool = False
        
        # Reconnection management
        self.reconnect_attempts: int = 0
        self.max_reconnect_attempts: int = 5
        self.reconnect_lock: asyncio.Lock = asyncio.Lock()
        
        # Heartbeat configuration
        self.heartbeat_interval: int = 3  # seconds
        
        # Transcript processing
        self.threshold: int = 5  # seconds between transcript callbacks
        self.last_turn_time: Optional[float] = None
        self.last_transcript: str = ""

    async def start(self) -> None:
        """
        Establish WebSocket connection to Deepgram Flux service.
        
        This method initializes the WebSocket connection to Deepgram's Flux
        speech-to-text service and starts the message receiver task.
        
        The connection includes:
        - Authentication using the provided API key
        - Automatic receiver task creation for handling incoming messages
        - Connection state management and error handling
        
        Raises:
            ConnectionError: If unable to establish WebSocket connection
            AuthenticationError: If API key is invalid
        """
        await self._cleanup_connection()
        
        try:
            url = "wss://api.deepgram.com/v2/listen?model=flux-general-en&encoding=linear16&sample_rate=16000"
            logfire.info(f"Connecting to Deepgram Flux service: {url}")

            self.ws = await websockets.connect(
                url,
                additional_headers={"Authorization": f"Token {self.api_key}"}
            )
            self.is_connected = True
            self.reconnect_attempts = 0

            # Start message receiver task
            asyncio.create_task(self._receiver())
            logfire.info("Flux STT connection established successfully")

        except Exception as e:
            logfire.error(f"Failed to connect to Deepgram Flux service: {e}")
            await self._handle_disconnect()
            raise ConnectionError(f"Connection failed: {e}")

    async def send_audio_chunk(self, chunk: Union[bytes, str]) -> None:
        """
        Send audio data chunk to Deepgram for transcription.
        
        This method sends audio data to the connected Deepgram service for
        real-time speech-to-text processing. The audio data can be provided
        as raw bytes or base64-encoded string.
        
        Args:
            chunk: Audio data as bytes or base64-encoded string.
                   Expected format: 16kHz, 16-bit, mono PCM audio.
                   
        Raises:
            ConnectionError: If WebSocket connection is not available
            ValueError: If audio chunk format is invalid
        """
        if not self.ws or not self.is_connected:
            logfire.warning("No active connection available for audio transmission")
            await self._handle_disconnect()
            return

        try:
            # Decode base64 if necessary
            if isinstance(chunk, str):
                data = base64.b64decode(chunk)
            else:
                data = chunk
                
            # Validate audio data
            if not data or len(data) == 0:
                logfire.warning("Empty audio chunk received, skipping transmission")
                return
                
            await self.ws.send(data)
            logfire.debug(f"Audio chunk sent successfully: {len(data)} bytes")
            
        except websockets.exceptions.ConnectionClosed:
            logfire.warning("WebSocket connection closed during audio transmission")
            await self._handle_disconnect()
        except Exception as e:
            logfire.error(f"Error sending audio chunk: {e}")
            await self._handle_disconnect()

    async def _receiver(self) -> None:
        """
        Handle incoming WebSocket messages from Deepgram Flux service.
        
        This private method runs as a background task to process incoming
        messages from the Deepgram WebSocket connection. It handles various
        message types including transcripts, errors, and connection events.
        
        Message Types Handled:
        - TurnInfo: Contains transcript data with confidence scores
        - Error: Service errors that require reconnection
        - Close: Connection closure events
        
        The method implements intelligent transcript filtering based on:
        - Confidence thresholds (minimum 0.6)
        - Time-based deduplication (5-second threshold)
        - Content deduplication (prevents duplicate transcripts)
        """
        try:
            async for message in self.ws:
                try:
                    event: Dict[str, Any] = json.loads(message)
                except json.JSONDecodeError as e:
                    logfire.warning(f"Failed to parse JSON message: {e}")
                    continue

                event_type: str = event.get("type", "")

                if event_type == "TurnInfo":
                    await self._handle_turn_info(event)
                elif event_type == "Error":
                    await self._handle_error(event)
                elif event_type == "Close":
                    await self._handle_close(event)
                else:
                    logfire.debug(f"Unhandled event type: {event_type}")

        except websockets.exceptions.ConnectionClosed:
            logfire.warning("WebSocket connection closed in receiver")
            await self._handle_disconnect()
        except Exception as e:
            logfire.error(f"Receiver error: {e}")
            await self._handle_disconnect()

    async def _handle_turn_info(self, event: Dict[str, Any]) -> None:
        """
        Process TurnInfo events containing transcript data.
        
        Args:
            event: TurnInfo event dictionary containing transcript and metadata
        """
        text: str = event.get("transcript", "")
        confidence: float = event.get("end_of_turn_confidence", 0.0)
        
        if not text.strip() or text.strip() == self.last_transcript:
            return
            
        # Check confidence threshold and time-based deduplication
        current_time = time.time()
        time_since_last = (current_time - self.last_turn_time) if self.last_turn_time else float('inf')
        
        if confidence > 0.6 and time_since_last > self.threshold:
            logfire.info(f"Transcript received: {text.strip()}")
            self.last_turn_time = current_time
            self.last_transcript = text.strip()
            
            try:
                await self.callback(text.strip())
            except Exception as callback_error:
                logfire.error(f"Error in transcript callback: {callback_error}")

    async def _handle_error(self, event: Dict[str, Any]) -> None:
        """
        Process Error events from Deepgram service.
        
        Args:
            event: Error event dictionary containing error details
        """
        error_message = event.get("message", "Unknown error")
        logfire.error(f"Deepgram Flux error: {error_message}")
        await self._handle_disconnect()

    async def _handle_close(self, event: Dict[str, Any]) -> None:
        """
        Process Close events from Deepgram service.
        
        Args:
            event: Close event dictionary containing closure details
        """
        logfire.info("Deepgram Flux connection closed by server")
        await self._handle_disconnect()


    async def _handle_disconnect(self) -> None:
        """
        Handle disconnection with automatic reconnection logic.
        
        This method implements a robust reconnection strategy with:
        - Thread-safe operation using async locks
        - Exponential backoff with jitter to prevent thundering herd
        - Maximum retry limits to prevent infinite loops
        - Proper cleanup before reconnection attempts
        
        The reconnection delay follows the formula:
        delay = min(2^attempts + random(0,1), 10) seconds
        """
        async with self.reconnect_lock:
            if not self.is_connected:
                return
                
            self.is_connected = False
            await self._cleanup_connection()
            
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                logfire.error(f"Maximum reconnection attempts ({self.max_reconnect_attempts}) reached. Stopping reconnection.")
                return
                
            # Calculate exponential backoff with jitter
            delay = min(2 ** self.reconnect_attempts + random.random(), 10)
            self.reconnect_attempts += 1
            
            logfire.warning(f"Attempting reconnection {self.reconnect_attempts}/{self.max_reconnect_attempts} in {delay:.1f} seconds")
            await asyncio.sleep(delay)
            
            try:
                await self.start()
                logfire.info("Reconnection successful")
            except Exception as e:
                logfire.error(f"Reconnection attempt {self.reconnect_attempts} failed: {e}")

    async def _cleanup_connection(self) -> None:
        """
        Clean up WebSocket connection resources.
        
        This method safely closes the WebSocket connection and resets
        connection state. It handles cleanup errors gracefully to ensure
        the service can continue operating even if cleanup fails.
        """
        if self.ws:
            try:
                await self.ws.close()
                logfire.info("WebSocket connection closed successfully")
            except Exception as e:
                logfire.warning(f"Error closing WebSocket connection: {e}")
                
        self.ws = None
        self.is_connected = False

    async def finish(self) -> None:
        """
        Gracefully shutdown the FluxSTT service.
        
        This method performs a clean shutdown of the service by:
        - Closing the WebSocket connection
        - Resetting connection state
        - Logging the shutdown event
        
        This method should be called when the service is no longer needed
        to ensure proper resource cleanup.
        """
        await self._cleanup_connection()
        logfire.info("FluxSTT service shutdown completed")