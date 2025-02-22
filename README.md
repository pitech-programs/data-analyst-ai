# Data Analyst AI

## Overview

This is a simple Streamlit app implementing an AI agent, dedicated to analyse your files.

The advantage over other tools is that it is agnostic to the type, schema and amount of the input data.

## Sample Dataset

Car Price Dataset

source: Kaggle <link>https://www.kaggle.com/datasets/asinow/car-price-dataset/data</link>

# Data Analysis Backend

This is the backend service for the Data Analysis Dashboard. It provides WebSocket-based API endpoints for analyzing data using OpenAI's GPT-4o-mini.

## Prerequisites

1. Python 3.8 or higher
2. OpenAI API key

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
	"prompt": "Analyze sales trends"
}
```
