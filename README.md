# Data Analyst AI

## Overview

This is a simple Streamlit app implementing an AI agent, dedicated to analyse your files.

The advantage over other tools is that it is agnostic to the type, schema and amount of the input data.

## Sample Dataset

Car Price Dataset

source: Kaggle <link>https://www.kaggle.com/datasets/asinow/car-price-dataset/data</link>

# Data Analysis Backend

This is the backend service for the Data Analysis Dashboard. It provides WebSocket-based API endpoints for analyzing data using OpenAI's GPT-4o-mini.

**Key Features:**

- **Versatile Data Analysis:** Analyzes various file types including CSV, XLSX, JSON, and TXT, adapting to different data schemas and sizes.
- **AI-Powered Code Generation:** Leverages OpenAI's `gpt-4o-mini` to dynamically generate Python scripts tailored to your data and analysis prompts.
- **Iterative Script Improvement:** Automatically debugs and refines the generated analysis scripts based on execution errors, ensuring robust analysis.
- **Comprehensive Reporting:** Generates detailed analysis reports in both HTML and PDF formats, including insightful visualizations.
- **Real-time Communication:** Uses WebSocket for real-time interaction, providing status updates and streaming analysis results directly to the dashboard.

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

Create a `.env` file in the root directory and add your OpenAI API key `OPENAI_API_KEY=your_api_key`.
Then source the `.env` file: `source .env`.

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

Future improvements:

- Add support for local LLM analysis
- Add Q&A mode for the Data sets
  - should be able to answer questions about the data sets
- Add support to interactively refine the report to your wishes
