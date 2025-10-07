So I am starting off a new project in which I have to develop a backend for a voice AI agent.

So my company has a frontend and they tried to build a voice AI agent but failed so they asked me to build it. Now I have to build a voice AI agent for them.

Background of the platform:

So the main platform is a agent building platform where user can come and can talk to the agent about their things and agent will guide and recommend how we can offer them an agent for their needs using n8n. 

This agent will be tasked to gather the initial information to create a BRD for the user.

In the information gathering process there will be multiple stages, on each stage there will be  a goal e.g. stage one: Gather project overview

The agent can ask up to 3 follow ups to the user on each stage and then if it feels it got the information in less than 3 follow ups or in max 3 follow ups it will move on to the next stage. 

And then that information will be user to create a summary and summary will be used to create a BRD.

Here are the features of the agent:

- It will connect through websocket with the frontend and will listen to the audio or text prompt 
- Its main goal is to ask follow ups to the user and gather information for each stage. 
- It will then use deepgram to transcribe the audio if available and if text prompt then it will directly give that to the LLM 
- It will return follow ups or next stage signal 
- And it will return text response for now (voice response later)


Tech stack:
- It will use async FASTAPI for backend 
- Deepgram for audio transcription 
- Pydantic AI to create the agent
- Groq for LLM provider to keep the latency low
- Eleven labs for voice responses (for later update)
- MongoDB with beanie for DB


Structure:
- I want to keep it orchestration type by making plug-able modules for each thing e.g. STT, agent, and etc
- I want to keep it modular and scale-able 
- I want to keep the latency as low as possible 

folder structure:

EVAA/
│── main.py
│── README.md
│── config/            # pydantic settings/env
│── handlers/          # fastapi routers
│── services/          # STT, TTS, LLM, Summarizer, etc.
│── agents/            # pydantic AI agents
|—— models/            # models to handle main logic of handlers 
│── db/
│   ├── connection.py
│   └── models/        # beanie models
│── schemas/           # pydantic schemas
│── utils/             # helpers
│── workflows/         # stage manager, orchestration logic


Meta data:

- Handlers will container fastapi routers, and handler will be used to get the request, route the request to the model, and return the response.
- Models will contain classes of functions or functions directly. They will hold the main logic of the endpoint 
- Agents will contain all the pydantic AI agents 
- Schemas will have to folders (beanie schemas and pydantic schemas) and they will hold schemas 
- DB will contain connection.py which will connect to the DB 
- Utils will contain files and function which will be utilities, e.g. pydantic settings to get env variables 

Technical details:

### Audio handling
- I will use Opus compression for the audio because it keeps the quality high, low latency, and deepgram also supports it
- We will start transcription as soon as we start to get the chunks, and wait for the deepgram to return end_of_speech flag to send the final STT to the LLM

### DB models 
- There will be two DB models for right now, chat memory and stages. Both will be tied with "sessionId" which the frontend will send when initializing the websocket, so the agent will fetch the old data if exists.

- Memory model:
-- _id
-- sessionId: beanie ID
-- Messages: json (pydantic AI LLM chat history)
-- current stageId: beanie ID
-- CreatedAt
-- UpdatedAt

- Stages:
-- _id
-- name
-- Description 
-- Goal
-- Order

### Chat memory
- We will dump the chat memory of the pydantic agent e.g. 'to_jsonable_python(result.all_messages())'

### Input Output schema for data on websocket
Input schema:
- audioChunk: str | None
- textPrompt: str | None
- sessionId: beanieId

Output schema:
- response: str 
- nextStage: bool
- nextStageData: dict | None


Now I want you to give me your thoughts on my design. And any improvement you want to add.