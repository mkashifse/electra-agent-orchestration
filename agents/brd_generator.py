"""
BRD Generator Agent using Pydantic AI.

This agent generates comprehensive Business Requirements Documents (BRD) and
system architecture diagrams based on conversation history from information
gathering sessions.
"""

from pydantic_ai import Agent, RunContext, ToolOutput
from pydantic_ai.models.groq import GroqModel
from pydantic_ai.providers.groq import GroqProvider
from pydantic_ai.agent import AgentRunResult
from pydantic_core import to_jsonable_python
from config.settings import settings
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import logfire
import json


# ================================================
# Input/Output Schemas
# ================================================

class BRDGeneratorInput(BaseModel):
    """Input schema for BRD generator agent."""
    conversation_history: List[Dict[str, Any]]
    session_id: str


class BRDGeneratorResponse(BaseModel):
    """Response schema for BRD generator agent."""
    brd_content: Optional[str] = None  # Markdown BRD content
    mermaid_diagram: Optional[str] = None  # Mermaid diagram code
    has_sufficient_data: bool = True  # Whether conversation has enough data
    message: str  # Status message or explanation


# ================================================
# System Prompt
# ================================================

SYSTEM_PROMPT = """
You are an expert Business Analyst and System Architect specializing in creating comprehensive Business Requirements Documents (BRD) and system architecture diagrams.

## Core Responsibilities

1. **Data Assessment**: Analyze conversation history to determine if sufficient information exists for BRD generation
2. **BRD Creation**: Generate professional, comprehensive Business Requirements Documents in Markdown format
3. **System Architecture**: Create high-level system design diagrams using Mermaid syntax
4. **Quality Assurance**: Ensure all deliverables meet professional standards

## BRD Structure Requirements

When sufficient data is available, create a BRD with the following sections:

### 1. Executive Summary
- Project overview and purpose
- Key business objectives
- High-level scope and timeline
- Expected outcomes and benefits

### 2. Business Objectives
- Primary business goals
- Success metrics and KPIs
- Business value proposition
- Strategic alignment

### 3. Functional Requirements
- Core system features and capabilities
- User stories and use cases
- Business processes and workflows
- Data requirements and relationships

### 4. Non-Functional Requirements
- Performance requirements
- Security and compliance needs
- Scalability and availability
- Integration requirements
- User experience standards

## System Architecture Diagram Requirements

Create a high-level system design diagram showing:
- Main system components and modules
- Data flow between components
- External integrations and APIs
- User interfaces and access points
- Core business logic layers

Use Mermaid syntax with appropriate diagram types (flowchart, graph, etc.).

## Data Processing

Process the conversation history to extract:
- Business objectives and goals
- Functional requirements and features
- User needs and use cases
- System scope and boundaries

## Output Requirements

Return a JSON response with:
- `brd_content`: Complete BRD in Markdown format
- `mermaid_diagram`: System architecture diagram in Mermaid syntax
- `has_sufficient_data`: Always true (we'll generate with available data)
- `message`: Status message explaining the result

## Quality Standards

- Use professional business language
- Ensure technical accuracy and completeness
- Follow standard BRD formatting conventions
- Create clear, readable diagrams
- Provide actionable and specific requirements
- Maintain consistency throughout the document

Remember: Quality over quantity. It's better to indicate insufficient data than to generate incomplete or inaccurate deliverables.
"""


# ================================================
# Agent Setup
# ================================================

groq_model = GroqModel(
    "openai/gpt-oss-120b", 
    provider=GroqProvider(api_key=settings.GROQ_API_KEY)
)

brd_generator_agent = Agent(
    model=groq_model,
    system_prompt=SYSTEM_PROMPT,
    deps_type=BRDGeneratorInput,
    output_type=ToolOutput(BRDGeneratorResponse, name="json"),
    retries=3,
)


# ================================================
# Dynamic System Prompt
# ================================================

@brd_generator_agent.system_prompt
def add_conversation_context(ctx: RunContext[BRDGeneratorInput]) -> str:
    """Add conversation context to the system prompt."""
    session_id = ctx.deps.session_id
    conversation_count = len(ctx.deps.conversation_history)
    
    context_prompt = f"""
    Session ID: {session_id}
    Conversation Messages: {conversation_count}
    
    Analyze the provided conversation history to determine if sufficient information exists
    for creating a comprehensive BRD and system architecture diagram.
    
    Focus on extracting:
    - Business objectives and goals
    - Functional requirements and features
    - User needs and use cases
    - System scope and boundaries
    - Technical requirements and constraints
    """
    
    return context_prompt


# ================================================
# Main Execution Function
# ================================================

async def generate_brd(
    conversation_history: List[Dict[str, Any]],
    session_id: str
) -> Dict[str, Any]:
    """
    Generate BRD and system architecture diagram from conversation history.
    
    Args:
        conversation_history: List of conversation messages from the session
        session_id: Unique identifier for the session
        
    Returns:
        Dict containing BRD content, mermaid diagram, and status information
    """
    try:
        logfire.info(f"Starting BRD generation for session: {session_id}")
        
        # Create dependencies
        deps = BRDGeneratorInput(
            conversation_history=conversation_history,
            session_id=session_id
        )
        
        # Build user prompt
        user_prompt = f"""
        Please analyze the following conversation history and generate a comprehensive BRD and system architecture diagram.
        
        Conversation History:
        {json.dumps(conversation_history, indent=2)}
        
        Requirements:
        1. Create a complete BRD in Markdown format based on the available information
        2. Create a high-level system architecture diagram in Mermaid syntax
        3. Use the available data to generate the best possible BRD
        
        Return your response as a JSON object with the following structure:
        {{
            "brd_content": "markdown content",
            "mermaid_diagram": "mermaid diagram code", 
            "has_sufficient_data": true,
            "message": "BRD and diagram generated successfully"
        }}
        """
        
        # Run the agent without message history for now (simplified for demo)
        result: AgentRunResult[BRDGeneratorResponse] = await brd_generator_agent.run(
            user_prompt=user_prompt,
            deps=deps
        )
        
        logfire.info(f"BRD generation completed for session: {session_id}")
        
        # Extract response data
        response_data = result.output
        
        # Return structured response
        return {
            "success": True,
            "brd_content": response_data.brd_content,
            "mermaid_diagram": response_data.mermaid_diagram,
            "has_sufficient_data": True,  # Always true for demo
            "message": response_data.message,
            "session_id": session_id
        }
        
    except Exception as e:
        logfire.error(f"Error generating BRD for session {session_id}: {str(e)}")
        return {
            "success": False,
            "brd_content": None,
            "mermaid_diagram": None,
            "has_sufficient_data": True,
            "message": f"I apologize, but I encountered an error generating the BRD: {str(e)}",
            "session_id": session_id,
            "error": str(e)
        }
