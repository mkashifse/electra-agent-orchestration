from fastapi import WebSocket
from db.models.memory import ChatMemory
from db.models.stage import Stage
from typing import List, Dict, Any
from services.websocket_handler import WebSocketHandler
from schemas.websocket_schema import WebSocketInput, Flag, webSocketAgentOutput
from agents.information_gatherer import agent_run
from services.stt import STTUsingFlux
import asyncio
import logfire
from bson import ObjectId

class ConversationModel:
    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self.memory = None
        self.stages = None
        self.current_stage_id = None
        self.current_stage_index = 0
        self.current_stage_name = None
        self.current_stage_description = None
        self.current_stage_goal = None
        self.current_stage_order = None
        self.current_flag = Flag.LISTENING
        self.SST = STTUsingFlux(self.call_back)
        self.websocket_handler = WebSocketHandler(websocket)
        self.is_new_project = False


    async def get_current_stage_data(self):
        return {
            "stage_name": self.current_stage_name,
            "stage_description": self.current_stage_description,
            "stage_goal": self.current_stage_goal
        }

    async def get_db_data(self, session_id: str):
        memory = await ChatMemory.find_one(ChatMemory.session_id == session_id)
        stages = await Stage.find().sort("order").to_list()
        self.memory = memory
        self.stages = stages

        if memory and memory.current_stage_id:
            # Existing session with current stage
            # Convert string ID back to ObjectId for comparison
            try:
                stage_id = ObjectId(memory.current_stage_id)
                stage = next((s for s in self.stages if s.id == stage_id), None)
            except Exception as e:
                logfire.warning(f"Invalid stage ID format: {memory.current_stage_id}, error: {e}")
                stage = None
            if stage:
                self.current_stage_id = stage.id
                self.current_stage_name = stage.name
                self.current_stage_description = stage.description
                self.current_stage_goal = stage.goal
                self.current_stage_order = stage.order
            else:
                # Stage not found, start with first stage
                self.is_new_project = True
                await self._set_first_stage()
        else:
            # New session or no current stage, start with first stage
            self.is_new_project = True
            await self._set_first_stage()

    async def _set_first_stage(self):
        """Set the first stage as current stage."""
        if self.stages and len(self.stages) > 0:
            first_stage = self.stages[0]  # First stage (lowest order)
            self.current_stage_id = first_stage.id
            self.current_stage_name = first_stage.name
            self.current_stage_description = first_stage.description
            self.current_stage_goal = first_stage.goal
            self.current_stage_order = first_stage.order
            logfire.info(f"Set first stage: {first_stage.name}")
        else:
            await self.websocket_handler.send_error("No stages found in database")


    async def update_db_memory(self, messages: List[Dict[str, Any]]):
        if not self.memory:
            # Create new memory if it doesn't exist
            self.memory = ChatMemory(
                session_id=self.session_id,
                messages=messages,
                current_stage_id=str(self.current_stage_id) if self.current_stage_id else None
            )
            await self.memory.insert()
        else:
            # Update existing memory
            self.memory.messages = messages
            self.memory.current_stage_id = str(self.current_stage_id) if self.current_stage_id else None
            await self.memory.save()

    async def call_back(self, message: str):
        await self.websocket_handler.send_user_transcription(message)
        await self.process_user_input(message)

    async def process_message(self, message: WebSocketInput):
        if message.audio_chunk:
            asyncio.create_task(self.SST.send_audio_chunk(message.audio_chunk))
        elif message.text_prompt:
            asyncio.create_task(self.process_user_input(message.text_prompt))

    async def move_to_next_stage(self):
        if self.current_stage_index + 1 < len(self.stages):
            self.current_stage_index += 1
            self.current_stage_name = self.stages[self.current_stage_index].name
            self.current_stage_description = self.stages[self.current_stage_index].description
            self.current_stage_goal = self.stages[self.current_stage_index].goal
            self.current_stage_id = self.stages[self.current_stage_index].id
            self.current_stage_order = self.stages[self.current_stage_index].order

            await self.first_question_of_the_stage("The user has come to this stage from a previous stage. Give a very short summary of this stage and ask a follow-up question.")

            return True
        else:
            await self.websocket_handler.end_session()
            return False

    async def call_agent(self, user_input: str):
        agent_response = await agent_run(
            user_input=user_input,
            current_stage_name=self.current_stage_name,
            current_stage_description=self.current_stage_description,
            current_stage_goal=self.current_stage_goal,
            conversation_history=self.memory.messages if self.memory else []
        )

        if agent_response.get("success", False):
            return agent_response
        else:
            await self.websocket_handler.send_error(agent_response.get("error", "Unknown error"))

    async def process_user_input(self, user_input: str):
        self.current_flag = Flag.THINKING
        await self.websocket_handler.send_flag(self.current_flag)
        agent_response = await self.call_agent(user_input)

        if agent_response.get("next_stage", False):


            output = webSocketAgentOutput(
                response=agent_response.get("response", ""),
                next_stage=agent_response.get("next_stage", False),
                current_stage=self.current_stage_name,
                follow_up_count=agent_response.get("follow_up_count", 0)
            )
            await self.websocket_handler.send_output(output, self.current_flag)

            next_stage = await self.move_to_next_stage()
            if not next_stage:
                return

            current_stage_data = await self.get_current_stage_data()
            await self.websocket_handler.send_next_stage(current_stage_data)
        else:
            output = webSocketAgentOutput(
                response=agent_response.get("response", ""),
                next_stage=agent_response.get("next_stage", False),
                current_stage=self.current_stage_name,
                follow_up_count=agent_response.get("follow_up_count", 0)
            )
            await self.websocket_handler.send_output(output, self.current_flag)

        self.current_flag = Flag.LISTENING
        await self.websocket_handler.send_flag(self.current_flag)

        await self.update_db_memory(agent_response.get("messages", []))


    async def first_question_of_the_stage(self, message: str):
        response = await self.call_agent(message)

        if response.get("success", False):
            output = webSocketAgentOutput(
                response=response.get("response", ""),
                next_stage=response.get("next_stage", False),
                current_stage=self.current_stage_name,
                follow_up_count=response.get("follow_up_count", 0)
            )
            await self.websocket_handler.send_output(output, self.current_flag)
        else:
            await self.websocket_handler.send_error(response.get("error", "Unknown error"))

        await self.update_db_memory(response.get("messages", []))


    async def run(self, session_id: str):
        await self.SST.start()
        await self.get_db_data(session_id)
        await self.websocket_handler.send_all_stages(self.stages)

        if self.is_new_project:
            await self.first_question_of_the_stage("Greet the user, introduce yourself, and initiate the conversation by asking them the next question in the current stage.")

        await self.websocket_handler.send_flag(self.current_flag)
        try:
            async for message in self.websocket_handler.receive_messages():
                if self.current_flag == Flag.LISTENING:
                    asyncio.create_task(self.process_message(message))
        except Exception as e:
            logfire.info(f"WebSocket connection ended for session {session_id}: {e}")


    
