import asyncio
import json
import base64
import random
import time
import logfire
import websockets
from typing import Callable, Union

class FluxSTT:
    def __init__(
        self,
        callback: Callable[[str], asyncio.Future],
        api_key: str,
        sample_rate: int = 16000,
        debug_audio: bool = True,
    ):
        self.callback = callback
        self.api_key = api_key
        self.sample_rate = sample_rate
        self.ws = None
        self.is_connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.heartbeat_interval = 3
        self.reconnect_lock = asyncio.Lock()
        self.threshold = 5 # seconds
        self.last_turn_time = None
        self.last_transcript = ""

    async def start(self):
        await self._cleanup_connection()
        try:
            url = "wss://api.deepgram.com/v2/listen?model=flux-general-en&encoding=linear16&sample_rate=16000"
            logfire.info(f"Connecting to Deepgram Flux: {url}")

            self.ws = await websockets.connect(
                url,
                additional_headers={"Authorization": f"Token {self.api_key}"}
            )
            self.is_connected = True
            self.reconnect_attempts = 0

            # start receiver
            asyncio.create_task(self._receiver())

        except Exception as e:
            logfire.error(f"Failed to connect to Deepgram Flux: {e}")
            await self._handle_disconnect()

    async def send_audio_chunk(self, chunk: Union[bytes, str]):
        if not self.ws or not self.is_connected:
            await self._handle_disconnect()
            return

        try:
            data = base64.b64decode(chunk) if isinstance(chunk, str) else chunk
            await self.ws.send(data)
        except Exception as e:
            logfire.error(f"Error sending chunk: {e}")
            await self._handle_disconnect()

    async def _receiver(self):
        try:
            async for message in self.ws:
                try:
                    event = json.loads(message)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")

                if event_type == "TurnInfo":
                    text = event.get("transcript", "")
                    if text.strip() and text.strip() != self.last_transcript:
                        if (event.get("end_of_turn_confidence", 0) > 0.6) and (((time.time() - (self.last_turn_time) ) > self.threshold) if self.last_turn_time else True):
                            logfire.info(f"Sentence: {text.strip()}")
                            self.last_turn_time = time.time()
                            self.last_transcript = text.strip()
                            await self.callback(text.strip())

                elif event_type == "Error":
                    logfire.error(f"Flux error: {event}")
                    await self._handle_disconnect()

                elif event_type == "Close":
                    logfire.info("Flux closed connection.")
                    await self._handle_disconnect()

                else:
                    logfire.debug(f"Unhandled event: {event_type} -> {event}")
        except Exception as e:
            logfire.error(f"Receiver error: {e}")
            await self._handle_disconnect()


    async def _handle_disconnect(self):
        async with self.reconnect_lock:
            if not self.is_connected:
                return
            self.is_connected = False
            await self._cleanup_connection()
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                logfire.error("Max reconnect attempts reached.")
                return
            delay = min(2 ** self.reconnect_attempts + random.random(), 10)
            self.reconnect_attempts += 1
            logfire.warning(f"Reconnecting in {delay:.1f}s...")
            await asyncio.sleep(delay)
            await self.start()

    async def _cleanup_connection(self):
        if self.ws:
            try:
                await self.ws.close()
                logfire.info("Closed previous websocket connection.")
            except Exception:
                pass
        self.ws = None
        self.is_connected = False


    async def finish(self) -> None:
        await self._cleanup_connection()
        logfire.info("FluxSTT connection closed.")