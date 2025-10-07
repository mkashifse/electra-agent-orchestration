import asyncio
import base64
import contextlib
import difflib
import random
import wave
from typing import Callable, Optional, Union

import logfire
from deepgram import (
    DeepgramClient,
    LiveTranscriptionEvents,
    LiveOptions,
    LiveResultResponse,
)
from config.settings import settings
from services.flux_stt import FluxSTT
import datetime

class AudioWriter:
    def __init__(self, filename: str = f"debug_audio_{datetime.datetime.now().hour}_{datetime.datetime.now().minute}_{datetime.datetime.now().second}.wav", sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.wav_file = wave.open(filename, "wb")
        self.wav_file.setnchannels(1)
        self.wav_file.setsampwidth(2)
        self.wav_file.setframerate(sample_rate)

    def write_chunk(self, audio_chunk: Union[bytes, str]):
        try:
            data = base64.b64decode(audio_chunk) if isinstance(audio_chunk, str) else audio_chunk
            self.wav_file.writeframes(data)
        except Exception as e:
            logfire.warning(f"Failed to write audio chunk: {e}")

    def close(self):
        with contextlib.suppress(Exception):
            self.wav_file.close()


class TranscriptHandler:
    def __init__(self, callback: Callable[[str], asyncio.Future]):
        self.callback = callback
        self.buffer = ""

    @staticmethod
    def merge_strings(old: str, new: str, threshold: float = 0.7) -> str:
        """
        Advanced string merging that handles complex overlapping patterns in speech transcripts.
        
        This function intelligently merges overlapping speech transcripts by:
        1. Finding the best overlap between old and new text
        2. Handling word-level overlaps and partial word matches
        3. Detecting and removing duplicate phrases
        4. Preserving the most complete version of the text
        
        Parameters:
        old (str): The existing transcript text
        new (str): The new transcript text to merge
        threshold (float): Similarity threshold for overlap detection (0.0 to 1.0)
        
        Returns:
        str: The merged transcript with overlaps intelligently handled
        """
        if not old:
            return new
        if not new:
            return old
            
        # Normalize text for better comparison
        old_normalized = old.lower().strip()
        new_normalized = new.lower().strip()
        
        # Split into words for word-level analysis
        old_words = old_normalized.split()
        new_words = new_normalized.split()
        
        if not old_words or not new_words:
            return old + " " + new if old and new else old or new
        
        # Find the best word-level overlap
        best_overlap = 0
        best_overlap_words = 0
        
        # Check for word-level overlaps (more reliable than character-level)
        for i in range(1, min(len(old_words), len(new_words)) + 1):
            old_suffix = old_words[-i:]
            new_prefix = new_words[:i]
            
            # Calculate similarity between word sequences
            if old_suffix == new_prefix:
                # Exact word match
                best_overlap = i
                best_overlap_words = i
            else:
                # Fuzzy word matching
                matches = sum(1 for a, b in zip(old_suffix, new_prefix) 
                            if difflib.SequenceMatcher(None, a, b).ratio() > 0.8)
                if matches >= i * 0.7:  # 70% of words should match
                    if matches > best_overlap_words:
                        best_overlap = i
                        best_overlap_words = matches
        
        # If no good word overlap found, try character-level overlap
        if best_overlap == 0:
            for i in range(1, min(len(old), len(new)) + 1):
                old_suffix = old[-i:]
                new_prefix = new[:i]
                ratio = difflib.SequenceMatcher(None, old_suffix, new_prefix).ratio()
                if ratio >= threshold:
                    best_overlap = i
                    break
        
        # Merge based on the best overlap found
        if best_overlap > 0:
            if best_overlap_words > 0:
                # Word-level merge
                old_without_overlap = " ".join(old_words[:-best_overlap])
                new_without_overlap = " ".join(new_words[best_overlap:])
                result = old_without_overlap + " " + new_without_overlap
            else:
                # Character-level merge
                old_without_overlap = old[:-best_overlap]
                new_without_overlap = new[best_overlap:]
                result = old_without_overlap + new_without_overlap
        else:
            # No overlap found, just concatenate
            result = old + " " + new
        
        # Clean up the result
        result = " ".join(result.split())  # Remove extra spaces
        return result.strip()

    async def handle(self, result: LiveResultResponse):
        try:
            if not hasattr(result, "channel") or not result.channel:
                return

            alternatives = getattr(result.channel, "alternatives", [])
            if not alternatives:
                return

            alt = alternatives[0]
            transcript_text = getattr(alt, "transcript", None) or getattr(alt, "text", None)
            if not transcript_text and hasattr(alt, "words"):
                transcript_text = " ".join(w.word for w in alt.words if hasattr(w, "word"))

            text = transcript_text.strip()
            if text:
                self.buffer = self.merge_strings(self.buffer, text)
            logfire.info(f"Transcript received: {self.buffer}")
            if result.speech_final:
                if self.buffer:
                    logfire.info(f"final result: {result}")
                    await self.callback(self.buffer)
                    self.buffer = ""
        except Exception as e:
            logfire.error(f"Error processing transcript: {e}")


class STT:
    """Stable, reconnect-safe Deepgram live transcription manager."""

    def __init__(
        self,
        callback: Callable[[str], asyncio.Future],
        model: str = "nova-3-general",
        encoding: str = "linear16",
        sample_rate: int = 16000,
        debug_audio: bool = True,
    ):
        self.client = DeepgramClient(settings.DEEPGRAM_API_KEY)
        self.model = model
        self.encoding = encoding
        self.sample_rate = sample_rate
        self.connection = None
        self.handler = TranscriptHandler(callback)
        self.audio_writer = AudioWriter() if debug_audio else None
        self.heartbeat_task: Optional[asyncio.Task] = None
        self.is_connected = False

        # reconnection management
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_lock = asyncio.Lock()
        self.heartbeat_interval = 3  # send silence every 5 seconds to prevent idle timeout

    async def start(self) -> bool:
        """Establishes a new Deepgram connection."""
        try:
            await self._cleanup_connection()

            # Recreate client to ensure a fresh connection
            self.client = DeepgramClient(settings.DEEPGRAM_API_KEY)

            logfire.info("Starting Deepgram connection...")
            self.connection = self.client.listen.asyncwebsocket.v("1")

            # Register event handlers
            self.connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript)
            self.connection.on(LiveTranscriptionEvents.Error, self._on_error)
            self.connection.on(LiveTranscriptionEvents.Close, self._on_close)

            options = LiveOptions(
                model=self.model,
                encoding=self.encoding,
                sample_rate=self.sample_rate,
                interim_results=False,
                endpointing=50
            )

            await self.connection.start(options)
            self.is_connected = True
            self.reconnect_attempts = 0

            # Restart heartbeat
            if self.heartbeat_task:
                self.heartbeat_task.cancel()
            self.heartbeat_task = asyncio.create_task(self._heartbeat())

            logfire.info("Deepgram connection started successfully.")
            return True
        except Exception as e:
            logfire.error(f"Failed to start Deepgram connection: {e}")
            self.is_connected = False
            return False


    async def send_audio_chunk(self, audio_chunk: Union[bytes, str]) -> None:
        """Send audio data to Deepgram for live transcription."""
        if self.audio_writer:
            self.audio_writer.write_chunk(audio_chunk)

        if not self.connection or not self.is_connected:
            logfire.warning("No active Deepgram connection. Attempting reconnection...")
            await self._handle_disconnect()
            return

        try:
            data = base64.b64decode(audio_chunk) if isinstance(audio_chunk, str) else audio_chunk
            await self.connection.send(data)
        except Exception as e:
            logfire.error(f"Error sending audio chunk: {e}")
            await self._handle_disconnect()

    async def _on_transcript(self, *_, **kwargs):
        result = kwargs.get("result")
        if isinstance(result, LiveResultResponse):
            await self.handler.handle(result)

    async def _on_error(self, *args, **kwargs):
        logfire.error(f"Deepgram error: {args} {kwargs}")
        await self._handle_disconnect()

    async def _on_close(self, *args, **kwargs):
        logfire.info(f"Deepgram connection closed: {args} {kwargs}")
        await self._handle_disconnect()

    async def _handle_disconnect(self):
        """Centralized reconnect handler with locking and backoff."""
        async with self.reconnect_lock:
            self.is_connected = False
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                logfire.error("Max reconnection attempts reached. Aborting.")
                return

            delay = min(2 ** self.reconnect_attempts + random.uniform(0, 1), 10)
            logfire.info(f"Attempting reconnection in {delay:.1f} seconds...")
            await asyncio.sleep(delay)

            self.reconnect_attempts += 1
            success = await self.start()
            if success:
                logfire.info("Reconnected successfully.")
            else:
                logfire.warning("Reconnection attempt failed.")

    async def _heartbeat(self):
        """Sends silence periodically to prevent Deepgram idle timeout."""
        while self.is_connected:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                if self.connection and self.is_connected:
                    silence = b"\x00" * 1024
                    await self.connection.send(silence)
                    logfire.debug("Sent heartbeat silence packet.")
            except Exception as e:
                logfire.warning(f"Heartbeat failed: {e}")
                await self._handle_disconnect()
                break

    async def _cleanup_connection(self):
        """Gracefully closes any existing connection before reconnecting."""
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.heartbeat_task
        if self.connection:
            try:
                await self.connection.finish()
                logfire.info("Cleaned up previous Deepgram connection.")
            except Exception:
                pass
        self.connection = None

    async def finish(self):
        """Terminate Deepgram session cleanly."""
        self.is_connected = False
        await self._cleanup_connection()
        if self.audio_writer:
            self.audio_writer.close()
        logfire.info("Deepgram session closed.")


class STTUsingFlux:
    def __init__(self, callback: Callable[[str], asyncio.Future]):
        self.callback = callback
        self.flux_stt = FluxSTT(self.on_transcript, settings.DEEPGRAM_API_KEY)

    async def on_transcript(self, text: str) -> None:
        return await self.callback(text)

    async def start(self) -> None:
        await self.flux_stt.start()

    async def send_audio_chunk(self, audio_chunk: Union[bytes, str]) -> None:
        await self.flux_stt.send_audio_chunk(audio_chunk)

    async def finish(self) -> None:
        await self.flux_stt.finish()