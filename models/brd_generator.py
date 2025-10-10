"""
BRD Generator Model for Business Requirements Document Generation

This module provides the business logic for generating comprehensive Business
Requirements Documents (BRD) and system architecture diagrams based on
conversation history from information gathering sessions.
"""

from typing import Dict, Any, List, Optional
from db.models.memory import ChatMemory
from agents.brd_generator import generate_brd
import logfire


class BRDGeneratorModel:
    """
    Business logic model for BRD generation.
    
    This class handles the complete workflow of generating BRDs and system
    architecture diagrams from conversation history, including data retrieval,
    validation, and response formatting.
    """
    
    def __init__(self, session_id: str) -> None:
        """
        Initialize BRD generator model.
        
        Args:
            session_id: Unique identifier for the conversation session
            
        Raises:
            ValueError: If session_id is empty or invalid
        """
        if not session_id or not session_id.strip():
            raise ValueError("Session ID cannot be empty")
            
        self.session_id: str = session_id.strip()
        self.memory: Optional[ChatMemory] = None
        logfire.info(f"BRDGeneratorModel initialized for session: {self.session_id}")

    async def get_session_memory(self) -> Optional[ChatMemory]:
        """
        Retrieve conversation memory for the session.
        
        Returns:
            ChatMemory object if found, None otherwise
            
        Raises:
            Exception: If database query fails
        """
        try:
            self.memory = await ChatMemory.find_one(ChatMemory.session_id == self.session_id)
            
            if self.memory:
                logfire.info(f"Session memory found for {self.session_id}: {len(self.memory.messages)} messages")
            else:
                logfire.warning(f"No session memory found for {self.session_id}")
                
            return self.memory
            
        except Exception as e:
            logfire.error(f"Error retrieving session memory for {self.session_id}: {e}")
            raise

    def extract_conversation_history(self) -> List[Dict[str, Any]]:
        """
        Extract and format conversation history from memory.
        
        Returns:
            List of formatted conversation messages
            
        Raises:
            ValueError: If no memory is available
        """
        if not self.memory:
            raise ValueError("No session memory available")
            
        # Extract messages from memory
        messages = self.memory.messages or []
        
        # Format messages for BRD generation
        formatted_messages = []
        for message in messages:
            if isinstance(message, dict):
                formatted_messages.append({
                    "role": message.get("role", "unknown"),
                    "content": message.get("content", ""),
                    "timestamp": message.get("timestamp", None)
                })
            else:
                # Handle different message formats
                formatted_messages.append({
                    "role": "unknown",
                    "content": str(message),
                    "timestamp": None
                })
        
        logfire.info(f"Extracted {len(formatted_messages)} messages from conversation history")
        return formatted_messages

    def validate_conversation_data(self, messages: List[Dict[str, Any]]) -> bool:
        """
        Simple validation - just check if we have any messages.
        
        Args:
            messages: List of conversation messages
            
        Returns:
            True if we have messages, False otherwise
        """
        return len(messages) > 0

    async def generate_brd_and_diagram(self) -> Dict[str, Any]:
        """
        Generate BRD and system architecture diagram from conversation history.
        
        This method orchestrates the complete BRD generation process:
        1. Retrieve session memory
        2. Extract conversation history
        3. Validate data sufficiency
        4. Generate BRD and diagram using AI agent
        5. Format and return results
        
        Returns:
            Dictionary containing BRD content, mermaid diagram, and status information
            
        Raises:
            ValueError: If session_id is invalid or no memory found
            Exception: If BRD generation fails
        """
        try:
            logfire.info(f"Starting BRD generation process for session: {self.session_id}")
            
            # Step 1: Retrieve session memory
            memory = await self.get_session_memory()
            if not memory:
                return {
                    "success": False,
                    "brd_content": None,
                    "mermaid_diagram": None,
                    "message": f"No conversation history found for session: {self.session_id}",
                    "session_id": self.session_id
                }
            
            # Step 2: Extract conversation history
            conversation_history = self.extract_conversation_history()
            
            # Step 3: Simple validation
            if not self.validate_conversation_data(conversation_history):
                return {
                    "success": False,
                    "brd_content": None,
                    "mermaid_diagram": None,
                    "message": "No conversation history found for this session.",
                    "session_id": self.session_id
                }
            
            # Step 4: Generate BRD and diagram using AI agent
            logfire.info(f"Calling BRD generator agent for session: {self.session_id}")
            result = await generate_brd(conversation_history, self.session_id)
            
            # Step 5: Format and return results
            if result.get("success", False):
                logfire.info(f"BRD generation successful for session: {self.session_id}")
                return {
                    "success": True,
                    "brd_content": result.get("brd_content"),
                    "mermaid_diagram": result.get("mermaid_diagram"),
                    "message": "BRD and system architecture diagram generated successfully",
                    "session_id": self.session_id
                }
            else:
                logfire.error(f"BRD generation failed for session: {self.session_id}")
                return {
                    "success": False,
                    "brd_content": None,
                    "mermaid_diagram": None,
                    "message": result.get("message", "BRD generation failed"),
                    "session_id": self.session_id
                }
                
        except ValueError as ve:
            logfire.error(f"Validation error in BRD generation for session {self.session_id}: {ve}")
            return {
                "success": False,
                "brd_content": None,
                "mermaid_diagram": None,
                "message": f"Validation error: {str(ve)}",
                "session_id": self.session_id
            }
        except Exception as e:
            logfire.error(f"Unexpected error in BRD generation for session {self.session_id}: {e}")
            return {
                "success": False,
                "brd_content": None,
                "mermaid_diagram": None,
                "message": f"An unexpected error occurred during BRD generation: {str(e)}",
                "session_id": self.session_id
            }

    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get summary information about the session.
        
        Returns:
            Dictionary containing session summary information
        """
        if not self.memory:
            return {
                "session_id": self.session_id,
                "has_memory": False,
                "message_count": 0,
                "stages_completed": 0
            }
            
        message_count = len(self.memory.messages) if self.memory.messages else 0
        stages_completed = len(self.memory.chat_history) if self.memory.chat_history else 0
        
        return {
            "session_id": self.session_id,
            "has_memory": True,
            "message_count": message_count,
            "stages_completed": stages_completed,
            "current_stage": self.memory.current_stage_id,
            "created_at": self.memory.created_at.isoformat() if self.memory.created_at else None,
            "updated_at": self.memory.updated_at.isoformat() if self.memory.updated_at else None
        }
