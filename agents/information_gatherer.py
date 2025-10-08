"""
Information gathering agent using Pydantic AI.
"""

from pydantic_ai import Agent, RunContext, ToolOutput
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_core import to_jsonable_python
from config.settings import settings
from typing import Dict, Any, List
from pydantic import BaseModel
import logfire
import json


# ----------------------------------------------
# Input/Output Schemas
# ----------------------------------------------
class AgentInput(BaseModel):
    """Input schema for information gathering agent."""
    user_input: str
    current_stage_name: str
    current_stage_description: str
    current_stage_goal: str
    follow_up_count: int = 0


class AgentResponse(BaseModel):
    """Response schema for information gathering agent."""
    response: str
    next_stage: bool = False
    follow_up_count: int = 0


# ----------------------------------------------
# System Prompt
# ----------------------------------------------
SYSTEM_PROMPT = """
You are an intelligent assistant of electra (a AI agent building platform). And your task is to guide user through their project requirements and help them to create a BRD for their project.

## Core Responsibilities

1. **Guiding User**: Guide user to shape their project and put it into a picture, and guide them through the process of creating a BRD.
1. **Information Gathering**: Ask follow-up questions to gather comprehensive information.
2. **Stage Management**: Guide users through structured stages of information gathering
3. **Progress Assessment**: Determine when you have enough information to move to the next stage
4. **Professional Communication**: Provide helpful and professional responses

## Stage Management Rules

- You can ask up to 3 follow-up questions per stage (not 3 conversations, but 3 follow-ups)
- If you feel you have enough information in fewer questions, you can move to the next stage
- If you need more information after 3 questions, you should still move to the next stage but note what information is missing
- Always be professional, helpful, and focused on gathering the specific information needed for each stage

## Response Guidelines

- Ask specific, relevant questions that help gather the required information
- Be conversational and engaging
- Provide context about why you're asking certain questions
- Acknowledge the user's responses appropriately
- Guide the conversation naturally toward the stage goal
- One question at a time, do not ask multiple questions in once response
- When moving on the next stage, do not ask follow-ups or talk about the next stage. Keep it to this stage only. And summarize the information gathered so far in this stage and previous stages.
- When we ask to greet the user and that he has come to this stage from a previous stage then do not talk about the previous stage. Just give a very short summary of this stage and ask a follow-up question. And do not return next_stage as true that time.
- When greeting the user, do not mention that you are a BRD building assistant. Instead mention that you are a assistant for a AI agent building platform called electra. And that you are here to help them shape their project.

## Output Requirements

Return a JSON response with:
- response: Your conversational response to the user
- next_stage: Boolean indicating if ready to move to next stage
- follow_up_count: Current number of follow-ups asked in this stage

Remember: You are gathering information to create a comprehensive BRD. Quality and completeness are key.
"""


# ----------------------------------------------
# Agent Setup
# ----------------------------------------------
groq_model = GroqModel(
    "openai/gpt-oss-120b", 
    provider=GroqProvider(api_key=settings.GROQ_API_KEY)
)

information_gatherer_agent = Agent(
    model=groq_model,
    system_prompt=SYSTEM_PROMPT,
    deps_type=AgentInput,
    output_type=ToolOutput(AgentResponse, name="json"),
    retries=3,
)


# ----------------------------------------------
# Dynamic System Prompt
# ----------------------------------------------
@information_gatherer_agent.system_prompt
def add_stage_context(ctx: RunContext[AgentInput]) -> str:
    """Add stage-specific context to the system prompt."""
    current_stage_name = ctx.deps.current_stage_name
    current_stage_description = ctx.deps.current_stage_description
    current_stage_goal = ctx.deps.current_stage_goal
    follow_up_count = ctx.deps.follow_up_count
    
    context_prompt = f"""
    Current Stage: {current_stage_name}
    Stage Description: {current_stage_description}
    Stage Goal: {current_stage_goal}
    Follow-up Count: {follow_up_count}/3
    """
    
    
    return context_prompt


# ----------------------------------------------
# Main Execution Function
# ----------------------------------------------
async def agent_run(
    user_input: str,
    current_stage_name: str,
    current_stage_description: str,
    current_stage_goal: str,
    conversation_history: List[Dict[str, Any]],
    follow_up_count: int = 0
) -> Dict[str, Any]:
    """
    Process user input and return agent response with memory.
    
    Args:
        user_input: The user's input text
        current_stage_name: Current stage name
        current_stage_description: Current stage description
        current_stage_goal: Current stage goal
        conversation_history: Previous conversation messages
        follow_up_count: Number of follow-ups asked in current stage
        
    Returns:
        Dict containing agent response and memory information
    """
    try:
        logfire.info(f"Processing user input for stage: {current_stage_name}")
        
        # Create dependencies
        deps = AgentInput(
            user_input=user_input,
            current_stage_name=current_stage_name,
            current_stage_description=current_stage_description,
            current_stage_goal=current_stage_goal,
            follow_up_count=follow_up_count
        )
        
        # Build user prompt
        user_prompt = f"""
        User Input: {user_input}
        
        Please respond to the user's input and determine if we should move to the next stage.
        Consider the stage goal and the information gathered so far.
        
        Return your response as a JSON object with the following structure:
        {{
            "response": "your conversational response here",
            "next_stage": true/false,
            "follow_up_count": {follow_up_count + 1}
        }}
        """
        
        # Convert conversation_history to ModelMessagesTypeAdapter format
        if isinstance(conversation_history, list):
            history = ModelMessagesTypeAdapter.validate_json(json.dumps(conversation_history))
        else:
            history = ModelMessagesTypeAdapter.validate_json(conversation_history)
        
        # Run the agent
        result: AgentRunResult[AgentResponse] = await information_gatherer_agent.run(
            user_prompt=user_prompt,
            deps=deps,
            message_history=history
        )
        
        logfire.info(f"Agent response generated for stage: {current_stage_name}")
        
        # Extract response data
        response_data = result.output
        
        # Return structured response with memory
        return {
            "success": True,
            "response": response_data.response,
            "next_stage": response_data.next_stage,
            "follow_up_count": response_data.follow_up_count,
            "messages": to_jsonable_python(result.all_messages()),
        }
        
    except Exception as e:
        logfire.error(f"Error processing user input: {str(e)}")
        return {
            "success": False,
            "response": f"I apologize, but I encountered an error processing your input: {str(e)}",
            "next_stage": False,
            "follow_up_count": follow_up_count,
            "messages": None,
            "error": str(e)
        }
