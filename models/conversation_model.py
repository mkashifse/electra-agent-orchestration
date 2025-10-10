"""
Conversation model for handling the conversation flow.
"""

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

    def parse_chat_history(self):
        """Get clean chat history grouped by stage from database"""
        if not self.memory or not self.memory.chat_history:
            return {}
        
        return self.memory.chat_history

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
                chat_history=[],
                current_stage_id=str(self.current_stage_id) if self.current_stage_id else None
            )
            await self.memory.insert()
        else:
            # Update existing memory
            self.memory.messages = messages
            self.memory.current_stage_id = str(self.current_stage_id) if self.current_stage_id else None
            await self.memory.save()

    async def add_to_chat_history(self, message_type: str, content: str):
        """Add a message to the clean chat history grouped by stage"""
        if not self.memory:
            # Create new memory if it doesn't exist
            self.memory = ChatMemory(
                session_id=self.session_id,
                messages=[],
                chat_history={},
                current_stage_id=str(self.current_stage_id) if self.current_stage_id else None
            )
            await self.memory.insert()
        
        # Get current stage name
        stage_name = self.current_stage_name or "unknown"
        
        # Initialize stage array if it doesn't exist
        if stage_name not in self.memory.chat_history:
            self.memory.chat_history[stage_name] = []
        
        # Add message to the stage group (without stage field since it's the key)
        self.memory.chat_history[stage_name].append({
            "type": message_type,
            "content": content
        })
        
        # Update database
        self.memory.current_stage_id = str(self.current_stage_id) if self.current_stage_id else None
        await self.memory.save()

    async def call_back(self, message: str):
        await self.websocket_handler.send_user_transcription(message)
        # Store user transcription in chat history
        await self.add_to_chat_history("user", message)
        await self.process_user_input(message)

    async def process_message(self, message: WebSocketInput) -> None:
        """
        Process incoming WebSocket messages (audio or text).
        
        This method handles both audio chunks for speech-to-text processing
        and text prompts for direct conversation input.
        
        Args:
            message: WebSocket message containing either audio_chunk or text_prompt
        """
        if message.audio_chunk:
            # Process audio chunk for speech-to-text
            try:
                asyncio.create_task(self.SST.send_audio_chunk(message.audio_chunk))
                logfire.debug("Audio chunk queued for STT processing")
            except Exception as e:
                logfire.error(f"Error processing audio chunk: {e}")
        elif message.text_prompt:
            # Process text input directly
            try:
                # Store user text input in chat history
                await self.add_to_chat_history("user", message.text_prompt)
                asyncio.create_task(self.process_user_input(message.text_prompt))
                logfire.debug(f"Text prompt queued for processing: {message.text_prompt[:50]}...")
            except Exception as e:
                logfire.error(f"Error processing text prompt: {e}")

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

        # Store agent response in chat history
        agent_response_text = agent_response.get("response", "")
        if agent_response_text:
            await self.add_to_chat_history("agent", agent_response_text)

        if agent_response.get("next_stage", False):


            output = webSocketAgentOutput(
                response=agent_response_text,
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
                response=agent_response_text,
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
            # Store agent response in chat history
            agent_response_text = response.get("response", "")
            if agent_response_text:
                await self.add_to_chat_history("agent", agent_response_text)
            
            output = webSocketAgentOutput(
                response=agent_response_text,
                next_stage=response.get("next_stage", False),
                current_stage=self.current_stage_name,
                follow_up_count=response.get("follow_up_count", 0)
            )
            await self.websocket_handler.send_output(output, self.current_flag)
        else:
            await self.websocket_handler.send_error(response.get("error", "Unknown error"))

        await self.update_db_memory(response.get("messages", []))


    async def run(self, session_id: str) -> None:
        """
        Main conversation loop for handling WebSocket communication.
        
        This method orchestrates the entire conversation flow including:
        - STT service initialization
        - Database data retrieval
        - WebSocket message handling
        - Proper cleanup on exit
        
        Args:
            session_id: Unique identifier for the conversation session
        """
        try:
            # Initialize STT service
            await self.SST.start()
            logfire.info(f"STT service started for session: {session_id}")
            
            # Load session data
            await self.get_db_data(session_id)
            await self.websocket_handler.send_all_stages(self.stages)
            
            # Send chat history to frontend
            chat_history = self.parse_chat_history()
            await self.websocket_handler.send_chat_history(chat_history, self.current_stage_name)

            # Initialize conversation if new project
            if self.is_new_project:
                await self.first_question_of_the_stage(
                    "Greet the user, introduce yourself, and initiate the conversation by asking them the next question in the current stage."
                )

            # Start main message processing loop
            await self.websocket_handler.send_flag(self.current_flag)
            async for message in self.websocket_handler.receive_messages():
                if self.current_flag == Flag.LISTENING:
                    asyncio.create_task(self.process_message(message))
                    
        except Exception as e:
            logfire.error(f"Error in conversation loop for session {session_id}: {e}")
            raise
        finally:
            # Clean up STT service
            try:
                await self.SST.finish()
                logfire.info(f"STT service cleaned up for session: {session_id}")
            except Exception as cleanup_error:
                logfire.error(f"Error cleaning up STT service: {cleanup_error}")


    
