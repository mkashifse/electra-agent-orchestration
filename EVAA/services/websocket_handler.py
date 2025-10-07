import json
from fastapi import WebSocket, WebSocketException
import logfire
from ..schemas.websocket_schema import Flag, webSocketAgentOutput, WebSocketInput, WebSocketOutput


class WebSocketHandler:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket

    async def receive_messages(self):
        """Asynchronously yields messages from WebSocket."""
        while True:
            message_data = await self.websocket.receive_text()
            message = json.loads(message_data)

            try: 
                message = WebSocketInput(**message)
                yield message
            except Exception as e:
                logfire.error(f"Error parsing message: {e}")
                await self.send_error(f"Error parsing message: {e}")


    async def send_flag(self, flag: Flag):
        output = WebSocketOutput(flag=flag, data=None)
        await self.websocket.send_text(output.model_dump_json())

    async def send_output(self, output: webSocketAgentOutput, flag: Flag):
        websocket_output = WebSocketOutput(flag=flag, data=output)
        await self.websocket.send_text(websocket_output.model_dump_json())

    async def send_next_stage(self, next_stage_data: dict):
        await self.websocket.send_text(json.dumps({
            "event": "next_stage",
            "next_stage_data": next_stage_data
        }))

    async def send_error(self, error: str):
        try:
            await self.websocket.send_text(json.dumps({
                "event": "error",
                "error": error
            }))
        except Exception as send_error:
            logfire.warning(f"Could not send error message: {send_error}")
        
        try:
            if self.websocket.client_state.name != "DISCONNECTED":
                await self.websocket.close()
        except Exception as close_error:
            logfire.warning(f"Could not close websocket: {close_error}")
        
        raise WebSocketException(code=1011, reason=error)

    async def end_session(self):
        try:
            await self.websocket.send_text(json.dumps({
                "event": "end_session",
            }))
        except Exception as send_error:
            logfire.warning(f"Could not send end session message: {send_error}")
        
        try:
            if self.websocket.client_state.name != "DISCONNECTED":
                await self.websocket.close()
        except Exception as close_error:
            logfire.warning(f"Could not close websocket: {close_error}")


    async def send_all_stages(self, stages: list):
        # Convert Stage objects to dictionaries for JSON serialization
        stages_data = []
        for stage in stages:
            if hasattr(stage, 'model_dump_json'):
                # If it's a Pydantic model, use model_dump_json()
                stages_data.append(stage.model_dump_json())
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
        
        await self.websocket.send_text(json.dumps({
            "event": "all_stages",
            "stages": stages_data
        }))


    async def send_user_transcription(self, transcription: str):
        await self.websocket.send_text(json.dumps({
            "event": "user_transcription",
            "transcription": transcription
        }))