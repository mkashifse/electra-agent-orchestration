"""
Speech-to-Text Service Module

This module provides a high-level interface for speech-to-text functionality
using Deepgram's Flux model. It includes audio debugging utilities and a
wrapper class for easy integration with the conversation system.

Key Components:
- AudioWriter: Utility for debugging audio data to WAV files
- STTUsingFlux: High-level wrapper for FluxSTT with simplified interface

Example:
    async def on_transcript(text: str):
        print(f"Transcribed: {text}")
    
    stt = STTUsingFlux(on_transcript)
    await stt.start()
    await stt.send_audio_chunk(audio_data)
    await stt.finish()
"""

import asyncio
import base64
import wave
import datetime
from typing import Callable, Union, Optional

import logfire

from config.settings import settings
from services.flux_stt import FluxSTT


class AudioWriter:
    """
    Audio debugging utility for writing audio chunks to WAV files.
    
    This class provides functionality to write audio data to WAV files
    for debugging and analysis purposes. It handles both raw bytes and
    base64-encoded audio data.
    
    Attributes:
        sample_rate: Audio sample rate in Hz (default: 16000)
        wav_file: Wave file object for writing audio data
    """
    
    def __init__(self, filename: Optional[str] = None, sample_rate: int = 16000) -> None:
        """
        Initialize AudioWriter with specified filename and sample rate.
        
        Args:
            filename: Output WAV filename. If None, generates timestamp-based name.
            sample_rate: Audio sample rate in Hz. Default is 16000.
            
        Raises:
            ValueError: If sample_rate is not positive
            IOError: If unable to create WAV file
        """
        if sample_rate <= 0:
            raise ValueError("Sample rate must be positive")
            
        if filename is None:
            timestamp = datetime.datetime.now()
            filename = f"debug_audio_{timestamp.hour}_{timestamp.minute}_{timestamp.second}.wav"
            
        self.sample_rate: int = sample_rate
        self.filename: str = filename
        
        try:
            self.wav_file = wave.open(filename, "wb")
            self.wav_file.setnchannels(1)  # Mono
            self.wav_file.setsampwidth(2)  # 16-bit
            self.wav_file.setframerate(sample_rate)
            logfire.info(f"AudioWriter initialized: {filename}")
        except Exception as e:
            raise IOError(f"Failed to create WAV file {filename}: {e}")

    def write_chunk(self, audio_chunk: Union[bytes, str]) -> None:
        """
        Write audio chunk to WAV file.
        
        Args:
            audio_chunk: Audio data as bytes or base64-encoded string.
                        Expected format: 16-bit, mono PCM audio.
                        
        Raises:
            ValueError: If audio_chunk is empty or invalid format
        """
        try:
            # Decode base64 if necessary
            if isinstance(audio_chunk, str):
                data = base64.b64decode(audio_chunk)
            else:
                data = audio_chunk
                
            if not data:
                logfire.warning("Empty audio chunk received, skipping write")
                return
                
            self.wav_file.writeframes(data)
            logfire.debug(f"Audio chunk written: {len(data)} bytes")
            
        except Exception as e:
            logfire.warning(f"Failed to write audio chunk: {e}")

    def close(self) -> None:
        """
        Close the WAV file and finalize audio data.
        
        This method safely closes the WAV file, ensuring all audio data
        is properly written and the file is finalized.
        """
        try:
            if hasattr(self, 'wav_file') and self.wav_file:
                self.wav_file.close()
                logfire.info(f"AudioWriter closed: {self.filename}")
        except Exception as e:
            logfire.warning(f"Error closing AudioWriter: {e}")


class STTUsingFlux:
    """
    High-level wrapper for FluxSTT with simplified interface.
    
    This class provides a simplified interface to the FluxSTT service,
    making it easier to integrate speech-to-text functionality into
    the conversation system. It handles the underlying FluxSTT instance
    and provides a clean API for audio processing.
    
    Attributes:
        callback: Function called when transcript is received
        flux_stt: Underlying FluxSTT service instance
    """
    
    def __init__(self, callback: Callable[[str], asyncio.Future]) -> None:
        """
        Initialize STTUsingFlux wrapper.
        
        Args:
            callback: Async function to call when transcript is received.
                     Must accept a single string parameter (transcript text).
                     
        Raises:
            ValueError: If callback is not callable
            ConfigurationError: If DEEPGRAM_API_KEY is not configured
        """
        if not callable(callback):
            raise ValueError("Callback must be a callable function")
            
        if not settings.DEEPGRAM_API_KEY:
            raise ValueError("DEEPGRAM_API_KEY not configured in settings")
            
        self.callback: Callable[[str], asyncio.Future] = callback
        self.flux_stt: FluxSTT = FluxSTT(
            callback=self.on_transcript,
            api_key=settings.DEEPGRAM_API_KEY
        )
        logfire.info("STTUsingFlux wrapper initialized")

    async def on_transcript(self, text: str) -> None:
        """
        Handle transcript callback from FluxSTT.
        
        This method acts as an intermediary between the FluxSTT service
        and the user-provided callback, ensuring proper error handling
        and logging.
        
        Args:
            text: Transcribed text from the speech-to-text service
            
        Raises:
            Exception: If the user callback raises an exception
        """
        try:
            await self.callback(text)
            logfire.debug(f"Transcript callback completed: {text[:50]}...")
        except Exception as e:
            logfire.error(f"Error in transcript callback: {e}")
            raise

    async def start(self) -> None:
        """
        Start the speech-to-text service.
        
        This method initializes the underlying FluxSTT service and
        establishes the WebSocket connection to Deepgram.
        
        Raises:
            ConnectionError: If unable to establish connection
            AuthenticationError: If API key is invalid
        """
        try:
            await self.flux_stt.start()
            logfire.info("STTUsingFlux service started successfully")
        except Exception as e:
            logfire.error(f"Failed to start STTUsingFlux service: {e}")
            raise

    async def send_audio_chunk(self, audio_chunk: Union[bytes, str]) -> None:
        """
        Send audio data for transcription.
        
        This method forwards audio data to the underlying FluxSTT service
        for real-time speech-to-text processing.
        
        Args:
            audio_chunk: Audio data as bytes or base64-encoded string.
                        Expected format: 16kHz, 16-bit, mono PCM audio.
                        
        Raises:
            ConnectionError: If service is not connected
            ValueError: If audio data is invalid
        """
        try:
            await self.flux_stt.send_audio_chunk(audio_chunk)
            logfire.debug(f"Audio chunk sent to STT service: {len(audio_chunk) if isinstance(audio_chunk, str) else len(audio_chunk)} bytes")
        except Exception as e:
            logfire.error(f"Error sending audio chunk to STT service: {e}")
            raise

    async def finish(self) -> None:
        """
        Gracefully shutdown the speech-to-text service.
        
        This method performs a clean shutdown of the underlying FluxSTT
        service, ensuring proper resource cleanup and connection closure.
        """
        try:
            await self.flux_stt.finish()
            logfire.info("STTUsingFlux service shutdown completed")
        except Exception as e:
            logfire.error(f"Error shutting down STTUsingFlux service: {e}")
            raise