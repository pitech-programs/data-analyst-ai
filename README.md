# Data Analyst AI

## Overview

This is a simple Streamlit app implementing an AI agent, dedicated to analyse your files.

The advantage over other tools, is that it is agnostic to the type, schema and amount of the input data and can be used privately with locally running LLMs.

## Sample Dataset

Car Price Dataset

source: Kaggle <link>https://www.kaggle.com/datasets/asinow/car-price-dataset/data</link>

# Data Analysis Backend

This is the backend service for the Data Analysis Dashboard. It provides WebSocket-based API endpoints for analyzing data using both local LLM (Ollama) and OpenAI's GPT-4o-mini.

## Prerequisites

1. Python 3.8 or higher
2. Ollama installed locally (for local LLM analysis)
3. OpenAI API key (for GPT-4 analysis)

## Setup

1. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Set up environment variables:

```bash
cp .env.example .env
```

Then edit `.env` and add your OpenAI API key.

4. Install and start Ollama (if not already done):

```bash
# Follow instructions at https://ollama.ai/
ollama pull llama2  # Pull the Llama 2 model
```

## Running the Server

Start the server with:

```bash
python main.py
```

The server will run on `http://localhost:8000`.

## API Endpoints

### WebSocket Endpoint: `/ws/analyze`

Accepts WebSocket connections for real-time data analysis. Send JSON data in the following format:

```json
{
	"files": [
		{
			"name": "data.csv",
			"content": "..."
		}
	],
	"useLocalModel": false,
	"prompt": "Analyze sales trends"
}
```

The server will stream back analysis results in real-time.
