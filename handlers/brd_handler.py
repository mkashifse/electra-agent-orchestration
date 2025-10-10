"""
FastAPI Router for BRD Generation Endpoint

Simple endpoint for generating Business Requirements Documents (BRD) and 
system architecture diagrams from conversation sessions.
"""

from fastapi import APIRouter, HTTPException, status
import logfire

from models.brd_generator import BRDGeneratorModel
from schemas.websocket_schema import BRDResponse

# Create FastAPI router for BRD endpoints
router = APIRouter()


@router.post("/brd/{session_id}", response_model=BRDResponse)
async def generate_brd_endpoint(session_id: str) -> BRDResponse:
    """
    Generate BRD and system architecture diagram for a conversation session.
    
    Args:
        session_id: Unique identifier for the conversation session
        
    Returns:
        BRDResponse containing BRD content, mermaid diagram, and status information
    """
    if not session_id or not session_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session ID cannot be empty"
        )
    
    session_id = session_id.strip()
    logfire.info(f"BRD generation request for session: {session_id}")
    
    try:
        # Initialize BRD generator model
        brd_generator = BRDGeneratorModel(session_id)
        
        # Generate BRD and diagram
        result = await brd_generator.generate_brd_and_diagram()
        
        # Create response
        response = BRDResponse(
            success=result.get("success", False),
            brd_content=result.get("brd_content"),
            mermaid_diagram=result.get("mermaid_diagram"),
            message=result.get("message", "BRD generation completed"),
            session_id=session_id
        )
        
        logfire.info(f"BRD generation completed for session: {session_id}")
        return response
        
    except Exception as e:
        logfire.error(f"Error generating BRD for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"BRD generation failed: {str(e)}"
        )
