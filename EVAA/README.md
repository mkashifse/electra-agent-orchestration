# EVAA - Electra Voice AI Agent

A backend service for a voice AI agent that gathers information to create Business Requirements Documents (BRDs).

## Overview

This agent is designed to interact with users through voice or text, gathering information in multiple stages to create comprehensive BRDs. The agent uses advanced AI technologies to provide intelligent follow-up questions and stage management.

## Features

- **WebSocket Communication**: Real-time communication with frontend
- **Audio Processing**: Opus compression for high-quality, low-latency audio
- **Speech-to-Text**: Deepgram integration for accurate transcription
- **AI Agent**: Pydantic AI with Groq LLM for intelligent responses
- **Stage Management**: Multi-stage information gathering process
- **Memory Management**: Persistent chat history and session management

## Tech Stack

- **Backend**: FastAPI (async)
- **AI/ML**: Pydantic AI, Groq LLM
- **Speech**: Deepgram (STT), ElevenLabs (TTS - future)
- **Database**: MongoDB with Beanie ODM
- **Audio**: Opus compression

## Project Structure

```
EVAA/
├── main.py                 # FastAPI application entry point
├── README.md              # Project documentation
├── config/                # Configuration and environment settings
├── handlers/              # FastAPI routers and request handlers
├── services/              # Core services (STT, TTS, LLM, etc.)
├── agents/                # Pydantic AI agents
├── db/                    # Database configuration
│   ├── connection.py      # MongoDB connection
│   └── models/            # Beanie models
├── schemas/               # Pydantic and Beanie schemas
├── utils/                 # Utility functions and helpers
└── workflows/             # Stage management and orchestration
```

## Getting Started

1. Install dependencies
2. Set up environment variables
3. Configure database connection
4. Run the application

## API Endpoints

- `GET /` - Root endpoint
- `GET /health` - Health check
- `WebSocket /ws` - Main communication channel

## Development

This project follows a modular, pluggable architecture for scalability and maintainability.
