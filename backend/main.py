from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
import pandas as pd
import openai
from typing import List
import ollama
import os
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_message(self, websocket: WebSocket, message: dict):
        if websocket in self.active_connections:
            try:
                await websocket.send_json(message)
            except RuntimeError:
                # Connection might be closed
                self.disconnect(websocket)

manager = ConnectionManager()

async def process_file(file: UploadFile) -> str:
    """Process uploaded file and return its contents as a string."""
    content = await file.read()
    if file.filename.endswith('.csv'):
        df = pd.read_csv(pd.io.common.BytesIO(content))
        return df.to_string()
    elif file.filename.endswith('.xlsx'):
        df = pd.read_excel(pd.io.common.BytesIO(content))
        return df.to_string()
    elif file.filename.endswith('.json'):
        return json.loads(content.decode())
    else:
        return content.decode()

async def stream_openai_analysis(data: str, prompt: str, websocket: WebSocket):
    """Stream analysis using OpenAI's API."""
    try:
        logger.info("Starting OpenAI analysis stream")
        await manager.send_message(websocket, {"status": "Starting OpenAI analysis..."})
        
        messages = [
            {"role": "system", "content": "You are a data analysis assistant. Analyze the provided data and give insights."},
            # {"role": "user", "content": f"Analyze this data with focus on: {prompt}\n\nData:\n{data}"}
            {"role": "user", "content": f"Write me a poem about data analysis as as AI Agent. make it about 20 sentences. Split it into three sections and have a Bold Headline for every of the three secitons.  Please add two new lines before every section"}
        ]
        logger.info(f"Sending request to OpenAI with prompt length: {len(prompt)} and data length: {len(data)}")
        client = openai.OpenAI()

        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            stream=True,
        )

        logger.info("Stream object created, beginning to process chunks")
        analysis = ""
        chunk_count = 0
        for chunk in stream:
            chunk_count += 1
            if chunk and chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                logger.info(f"Received content chunk of length: {len(content)}")
                analysis += content
                await manager.send_message(websocket, {"content": content})
        
        logger.info(f"Stream completed. Total chunks: {chunk_count}, Total analysis length: {len(analysis)}")
        return analysis
    
    except Exception as e:
        logger.error(f"Error in stream_openai_analysis: {str(e)}", exc_info=True)
        await manager.send_message(websocket, {"error": str(e)})
        return None

async def stream_local_analysis(data: str, prompt: str, websocket: WebSocket):
    """Stream analysis using local Ollama model."""
    try:
        await manager.send_message(websocket, {"status": "Starting local LLM analysis..."})
        
        system_prompt = "You are a data analysis assistant. Analyze the provided data and give insights."
        user_prompt = f"Analyze this data with focus on: {prompt}\n\nData:\n{data}"
        
        async for chunk in ollama.chat(
            model='llama2',  # You can change this to any model you have in Ollama
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            stream=True
        ):
            if chunk and 'content' in chunk:
                await manager.send_message(websocket, {"content": chunk['content']})
        
    except Exception as e:
        await manager.send_message(websocket, {"error": str(e)})

@app.websocket("/ws/analyze")
async def analyze_data(websocket: WebSocket):
    await manager.connect(websocket)
    
    try:
        while True:
            try:
                data = await websocket.receive_json()
                logger.info("Received websocket data")
                
                # Extract parameters from the received data
                files_data = data.get("files", [])
                use_local_model = data.get("useLocalModel", False)
                analysis_prompt = data.get("prompt", "")
                
                logger.info(f"Processing request - Files count: {len(files_data)}, Local model: {use_local_model}")
                
                # Process all files and combine their contents
                combined_data = ""
                for file_data in files_data:
                    combined_data += f"\n\nFile: {file_data['name']}\n{file_data['content']}"
                
                logger.info(f"Combined data length: {len(combined_data)}")
                
                if use_local_model:
                    await stream_local_analysis(combined_data, analysis_prompt, websocket)
                else:
                    result = await stream_openai_analysis(combined_data, analysis_prompt, websocket)
                    logger.info(f"Analysis completed with result length: {len(result) if result else 0}")
                
                # Send completion message
                logger.info("Sending completion message")
                await manager.send_message(websocket, {"status": "Analysis completed"})
                
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                manager.disconnect(websocket)
                break
            except Exception as e:
                logger.error(f"Error in analyze_data: {str(e)}", exc_info=True)
                await manager.send_message(websocket, {"error": str(e)})
                
    except Exception as e:
        logger.error(f"Fatal error in analyze_data: {str(e)}", exc_info=True)
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 