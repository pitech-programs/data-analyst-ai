# Import required libraries
from fastapi import FastAPI, WebSocket, WebSocketDisconnect # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from fastapi.staticfiles import StaticFiles # type: ignore
import json
import asyncio
import os
import subprocess
from typing import List, Dict, Any, Optional
import openai
from weasyprint import HTML # type: ignore
from dotenv import load_dotenv # type: ignore
import logging
import uvicorn # type: ignore
import base64
from elevenlabs.client import ElevenLabs # type: ignore

# Configuration Constants
OPENAI_MODEL = "gpt-4o-mini"
ELEVENLABS_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb" 
ELEVENLABS_MODEL_ID = "eleven_turbo_v2_5"
ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"
MAX_RETRIES = 5

# Directory Configuration
TEMP_DIR = 'temp'
INPUT_DIR = 'input'
OUTPUT_DIR = 'output'
REQUIRED_DIRS = [TEMP_DIR, INPUT_DIR, OUTPUT_DIR]

# File paths
ANALYSIS_SCRIPT_PATH = os.path.join(TEMP_DIR, 'analysis_script.py')
ANALYSIS_RESULTS_PATH = os.path.join(OUTPUT_DIR, 'analysis_results.json')
REPORT_HTML_PATH = os.path.join(OUTPUT_DIR, 'report.html')
REPORT_PDF_PATH = os.path.join(OUTPUT_DIR, 'report.pdf')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize ElevenLabs
elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
if not elevenlabs_api_key:
    logger.warning("ELEVENLABS_API_KEY not found in environment variables")
elevenlabs_client = ElevenLabs(api_key=elevenlabs_api_key) if elevenlabs_api_key else None

# Create FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create required directories
for dir_path in REQUIRED_DIRS:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

# Helper Functions for OpenAI API calls
async def stream_openai_response(
    messages: List[Dict[str, Any]], 
    websocket: Optional[WebSocket] = None, 
    **kwargs
) -> str:
    """
    Stream OpenAI API response and handle code blocks.
    Returns the full response as a string.
    
    Args:
        messages: List of message dictionaries for the OpenAI chat completion
        websocket: Optional WebSocket to stream responses to
        **kwargs: Additional arguments to pass to the OpenAI API
        
    Returns:
        str: The complete response from OpenAI
    """
    logger.info("Making API call to OpenAI")
    client = openai.OpenAI()
    stream = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=messages,
        stream=True,
        **kwargs
    )
    
    logger.info("Stream object created, beginning to process chunks")
    full_response = ""
    code_section = False
    current_section = ""
    
    for chunk in stream:
        if chunk and chunk.choices and chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            full_response += content
            
            # Check if we're entering or leaving a code block
            if "```" in content:
                if any(lang in content for lang in ["```python", "```html"]):
                    code_section = True
                    current_section = content[content.find("```"):] + "\n"
                    continue
                elif code_section:
                    code_section = False
                    if current_section and websocket:
                        await websocket.send_json({
                            "content": "🔧 Generated code. Now preparing to execute...\n\n"
                        })
                    current_section = ""
                    continue
            
            if code_section:
                current_section += content
            elif websocket and content.strip():
                await websocket.send_json({"content": content})
    
    logger.info("Received complete response from OpenAI")
    return full_response

def extract_code_from_response(response: str, language: str = "python") -> str:
    """
    Extract code from a response containing markdown code blocks.
    
    Args:
        response: The full response containing markdown code blocks
        language: The programming language to extract (default: "python")
        
    Returns:
        str: The extracted code
        
    Raises:
        Exception: If no code block is found for the specified language
    """
    import re
    pattern = f"```{language}\n(.*?)```"
    code_match = re.search(pattern, response, re.DOTALL)
    if not code_match:
        raise Exception(f"No {language} code block found in the response")
    return code_match.group(1).strip()

# Connection manager for handling WebSocket connections
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
                self.disconnect(websocket)

# Instantiate the connection manager
manager = ConnectionManager()

async def analyze_file_structure(file_name: str, file_path: str) -> tuple[str, dict]:
    """
    Analyze the structure of a file based on its type.
    Returns a tuple of (structure_description, metadata)
    """
    file_extension = file_name.lower().split('.')[-1]
    
    try:
        if file_extension in ['csv', 'txt']:
            import pandas as pd
            df = pd.read_csv(file_path)
            structure = f"\nFile: {file_name}\nColumns: {', '.join(df.columns)}\nFirst three rows:\n{df.head(3).to_string()}\n"
            metadata = {
                "type": "tabular",
                "rows": len(df),
                "columns": len(df.columns)
            }
            return structure, metadata
            
        elif file_extension == 'xlsx':
            import pandas as pd
            df = pd.read_excel(file_path)
            structure = f"\nFile: {file_name}\nColumns: {', '.join(df.columns)}\nFirst three rows:\n{df.head(3).to_string()}\n"
            metadata = {
                "type": "tabular",
                "rows": len(df),
                "columns": len(df.columns)
            }
            return structure, metadata
            
        elif file_extension == 'json':
            import json
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            def analyze_json_structure(obj, max_depth=3, current_depth=0):
                if current_depth >= max_depth:
                    return "..."
                
                if isinstance(obj, dict):
                    structure = "{\n"
                    for key, value in list(obj.items())[:5]:  # Limit to first 5 keys
                        structure += "  " * (current_depth + 1)
                        structure += f'"{key}": '
                        if isinstance(value, (dict, list)):
                            structure += analyze_json_structure(value, max_depth, current_depth + 1)
                        else:
                            structure += f"{type(value).__name__}"
                        structure += ",\n"
                    if len(obj) > 5:
                        structure += "  " * (current_depth + 1) + "...\n"
                    structure += "  " * current_depth + "}"
                    return structure
                
                elif isinstance(obj, list):
                    if not obj:
                        return "[]"
                    structure = "[\n"
                    for item in obj[:3]:  # Limit to first 3 items
                        structure += "  " * (current_depth + 1)
                        if isinstance(item, (dict, list)):
                            structure += analyze_json_structure(item, max_depth, current_depth + 1)
                        else:
                            structure += f"{type(item).__name__}"
                        structure += ",\n"
                    if len(obj) > 3:
                        structure += "  " * (current_depth + 1) + "...\n"
                    structure += "  " * current_depth + "]"
                    return structure
                
                return str(type(obj).__name__)
            
            structure = f"\nFile: {file_name}\nStructure:\n{analyze_json_structure(data)}\n"
            
            def count_items(obj):
                if isinstance(obj, dict):
                    return len(obj)
                elif isinstance(obj, list):
                    return len(obj)
                return 1
            
            metadata = {
                "type": "json",
                "top_level_items": count_items(data)
            }
            return structure, metadata
            
        else:
            structure = f"\nFile: {file_name}\nUnsupported file type: {file_extension}\n"
            metadata = {"type": "unsupported"}
            return structure, metadata
            
    except Exception as e:
        logger.warning(f"Could not read structure for {file_name}: {str(e)}")
        return f"\nFile: {file_name}\nStructure could not be read: {str(e)}\n", {"type": "error"}

# Generate Python code for data analysis using OpenAI API
async def generate_analysis_code(file_names: List[str], analysis_prompt: str, websocket: WebSocket) -> str:
    """
    Generate Python code for data analysis using OpenAI API.
    """
    logger.info(f"Starting code generation for files: {', '.join(file_names)}")
    logger.info(f"Analysis prompt: {analysis_prompt}")

    await websocket.send_json({"content": "🔍 Analyzing your files and preparing the data analysis strategy...\n\n"})

    # Read file structures
    file_structures = []
    file_metadata = {}
    
    for file_name in file_names:
        file_path = os.path.join(INPUT_DIR, file_name)
        structure, metadata = await analyze_file_structure(file_name, file_path)
        file_structures.append(structure)
        file_metadata[file_name] = metadata
        
        if metadata["type"] == "tabular":
            await websocket.send_json({
                "content": f"📊 Analyzed {file_name}:\n- Found {metadata['columns']} columns\n- {metadata['rows']:,} rows of data\n\n"
            })
        elif metadata["type"] == "json":
            await websocket.send_json({
                "content": f"🔍 Analyzed {file_name}:\n- JSON data with {metadata['top_level_items']} top-level items\n\n"
            })
        elif metadata["type"] == "error":
            await websocket.send_json({
                "content": f"⚠️ Could not analyze {file_name}: {structure}\n\n"
            })

    await websocket.send_json({
        "content": "🤖 Now I'll write a Python script to analyze your data based on your requirements...\n\n"
    })

    messages = [{
        "role": "system",
        "content": """You are a data analysis assistant with expertise in Python, pandas, matplotlib, and JSON data processing. 
Write clean, efficient Python code that produces insightful analysis and clear visualizations."""
    }, {
        "role": "user",
        "content": f"""Write a Python script that analyzes the provided data:

1. Setup:
- Import pandas, matplotlib.pyplot, json, os, numpy
- set plt.style.use('default') at the beginning of the script

2. Data Processing:
The following files need to be processed from the 'input' directory: {', '.join(file_names)}

File types and structures:
{''.join(file_structures)}

Loading instructions by file type:
{
    ''.join([
        f"- {file_name}: Use " + (
            "pd.read_csv()" if metadata['type'] == 'tabular' and file_name.endswith('.csv') else
            "pd.read_excel()" if metadata['type'] == 'tabular' and file_name.endswith('.xlsx') else
            "pd.read_csv()" if metadata['type'] == 'tabular' and file_name.endswith('.txt') else
            "json.load()" if metadata['type'] == 'json' else
            "# Unsupported file type"
        ) + "\n"
        for file_name, metadata in file_metadata.items()
    ])
}

3. Required Analysis:
- For tabular data:
  * Calculate basic statistics (mean, median, etc.)
  * Identify patterns and trends
  * Find correlations if applicable
- For JSON data:
  * Analyze the structure and relationships
  * Extract key metrics and patterns
  * Identify common values or trends
- Create at least 3 relevant plots:
  * Save as PNG files in 'output' directory
  * Use clear labels and titles
  * Make them easy to read
  * All plots should have a similar style

4. Additional analysis requirements:
{analysis_prompt}

5. Save results to 'output/analysis_results.json':
{{
    "title": "Analysis Report Title",
    "timestamp": "YYYY-MM-DD HH:MM:SS",
    "summary": {{
        "key_findings": ["Main finding 1", "Main finding 2"],
        "data_quality": {{
            "missing_values": "Summary",
            "data_types": "Summary",
            "anomalies": "Any issues found"
        }}
    }},
    "description": "Analysis details",
    "statistics": {{
        "basic_stats": {{
            "numerical_summary": {{}},
            "categorical_summary": {{}}
        }},
        "advanced_stats": {{
            "correlations": {{}},
            "segment_analysis": {{}}
        }}
    }},
    "visualizations": {{
        "plots": ["plot1.png", "plot2.png"],
        "plot_descriptions": {{
            "plot1.png": "What this plot shows",
            "plot2.png": "What this plot shows"
        }}
    }},
    "metadata": {{
        "analysis_duration": "Time taken",
        "data_sources": {file_names},
        "file_types": {str({name: meta["type"] for name, meta in file_metadata.items()})},
        "rows_analyzed": "Count per file",
        "columns_analyzed": "List per file"
    }}
}}

Do not use any try except blocks - we will deal with errors in another way.
Do not handle errors in the code, we will deal with them in the iteration process.
"""
    }]

    try:
        full_response = await stream_openai_response(messages, websocket)
        code = extract_code_from_response(full_response)
        logger.info("Successfully extracted Python code from response")
        await websocket.send_json({
            "content": "✨ Analysis code is ready! Starting the execution phase...\n\n"
        })
        return code
    except Exception as e:
        logger.error(f"Failed to generate analysis code: {str(e)}", exc_info=True)
        raise

async def iterate_analysis_script(file_names: List[str], analysis_prompt: str, current_script: str, error_message: str, websocket: WebSocket) -> tuple[str, bool]:
    """
    Iteratively improve the analysis script based on execution errors.
    Returns a tuple of (new_script, success) where success indicates if execution was successful.
    """
    logger.info("Starting script iteration with error: %s", error_message)
    
    messages = [{
        "role": "system",
        "content": "You are a Python code debugging assistant. Fix the provided code based on the error message while maintaining the original analysis goals."
    }, {
        "role": "user",
        "content": f"""The following Python script failed to execute properly:

```python
{current_script}
```

The error message was:
{error_message}

The script should analyze these files from the 'input' directory: {', '.join(file_names)}
With this analysis focus: {analysis_prompt}

Please provide a fixed version of the script that:
1. Addresses the error
2. Maintains the original analysis goals
3. Ensures proper error handling
4. Validates data before processing
5. Properly saves results to '{ANALYSIS_RESULTS_PATH}'
6. if the error is ModuleNotFoundError, rewrite to only use libraries like pandas, matplotlib, json, os, numpy, etc.

Do not use any try except blocks - we will deal with errors in another way.
Do not handle errors in the code, we will deal with them in the iteration process.
"""
    }]

    try:
        full_response = await stream_openai_response(messages, websocket)
        new_script = extract_code_from_response(full_response)
        logger.info("Generated fixed script")

        # Save and execute the new script
        with open(ANALYSIS_SCRIPT_PATH, 'w') as f:
            f.write(new_script)

        try:
            await execute_analysis_script(ANALYSIS_SCRIPT_PATH, websocket)
            if os.path.exists(ANALYSIS_RESULTS_PATH):
                return new_script, True
            else:
                return new_script, False
        except Exception as e:
            return new_script, False

    except Exception as e:
        logger.error(f"Failed to generate fixed script: {str(e)}", exc_info=True)
        return current_script, False

# Execute the generated analysis script
async def execute_analysis_script(script_path: str, websocket: WebSocket):
    """
    Execute the generated analysis script.
    """
    logger.info(f"Starting execution of analysis script: {script_path}")
    try:
        logger.info("Running analysis script")
        await websocket.send_json({"status": "Executing analysis script..."})
        result = subprocess.run(['python', script_path], capture_output=True, text=True)
        if result.returncode != 0:
            error_msg = f"Script execution failed: {result.stderr}"
            logger.error(error_msg)
            await websocket.send_json({"status": "Analysis script failed, attempting to fix..."})
            raise Exception(error_msg)
        logger.info("Analysis script executed successfully")
        await websocket.send_json({"status": "Analysis script executed successfully"})
        return result.stdout
    except Exception as e:
        logger.error(f"Error executing analysis script: {str(e)}", exc_info=True)
        raise

# Constants for templates
ANALYSIS_RESULTS_TEMPLATE = """
{
    "title": "Analysis Report Title",
    "timestamp": "YYYY-MM-DD HH:MM:SS",
    "summary": {
        "key_findings": ["Main finding 1", "Main finding 2"],
        "data_quality": {
            "missing_values": "Summary",
            "data_types": "Summary",
            "anomalies": "Any issues found"
        }
    },
    "description": "Analysis details",
    "statistics": {
        "basic_stats": {
            "numerical_summary": {},
            "categorical_summary": {}
        },
        "advanced_stats": {
            "correlations": {},
            "segment_analysis": {}
        }
    },
    "visualizations": {
        "plots": ["plot1.png", "plot2.png"],
        "plot_descriptions": {
            "plot1.png": "What this plot shows",
            "plot2.png": "What this plot shows"
        }
    },
    "metadata": {
        "analysis_duration": "Time taken",
        "data_sources": [],
        "file_types": {},
        "rows_analyzed": "Count per file",
        "columns_analyzed": "List per file"
    }
}
"""

async def generate_html_report(analysis_json_path: str, output_html_path: str, websocket: WebSocket):
    """
    Generate an HTML report from the analysis results using OpenAI API.
    """
    logger.info(f"Starting HTML report generation from {analysis_json_path}")
    try:
        # Load analysis data from JSON file
        logger.info("Loading analysis results from JSON")
        
        with open(analysis_json_path, 'r') as f:
            analysis_data = json.load(f)
        
        # Remove 'output/' prefix from plot paths since HTML will be in the same directory
        if 'visualizations' in analysis_data and 'plots' in analysis_data['visualizations']:
            analysis_data['visualizations']['plots'] = [
                plot.replace('output/', '') for plot in analysis_data['visualizations']['plots']
            ]
        
        messages = [{
            "role": "system",
            "content": """You are an expert HTML/CSS developer and data analyst. Create a beautiful, modern HTML report about a data analysis using Tailwind CSS.
The HTML should be a single self-contained file with the Tailwind CDN included."""
        }, {
            "role": "user",
            "content": f"""Create a clean and professional HTML report page that presents the analysis of the following data:

ANALYSIS DATA (use all relevant fields for the report):
{json.dumps(analysis_data, indent=2)}

REQUIREMENTS:

1. Document Setup:
   - Include this script tag in the head: <script src="https://unpkg.com/@tailwindcss/browser@4"></script>
   - Use proper meta tags and viewport settings
   - Use tables to display the data where it makes sense
   - Explain each plots meaning with a short sentence and have them below one another
   
2. Core Sections:
   - Title and header
   - Key findings summary
   - Data quality overview
   - Statistical results
   - Visualizations with descriptions 
   - Analysis metadata footer

3. Design Features:
   - Clean, professional layout
   - Fill the page with the actual analysis data
   - It has to be in light mode
   - Responsive design (mobile and desktop)
   - Card-based content sections
   - Clear typography and spacing

Return only the complete HTML code with all required scripts, values and styles included."""
        }]

        full_response = await stream_openai_response(messages, websocket)
        html_content = extract_code_from_response(full_response, 'html')
        
        # Save the HTML report
        with open(output_html_path, 'w') as f:
            f.write(html_content)
        logger.info(f"HTML report saved to {output_html_path}")

    except Exception as e:
        logger.error(f"Failed to generate HTML report: {str(e)}")
        raise

# Convert HTML to PDF
def generate_pdf_from_html(html_path: str, pdf_path: str, websocket: WebSocket):
    try:
        # Read the HTML content
        with open(html_path, 'r', encoding='utf-8') as file:
            html_content = file.read()
        
        # Get the absolute path of the output directory
        abs_output_dir = os.path.abspath(OUTPUT_DIR)
        
        # Replace relative image paths with absolute file:// paths
        html_content = html_content.replace('src="', f'src="file://{abs_output_dir}/')
        
        # Generate PDF using the modified HTML content
        HTML(string=html_content).write_pdf(pdf_path)
        logger.info(f"Successfully generated PDF at {pdf_path}")
    except Exception as e:
        logger.error(f"Failed to generate PDF: {str(e)}")
        raise

async def generate_verbal_summary(analysis_data: dict, websocket: WebSocket) -> str:
    """
    Generate a verbal summary of the analysis results using OpenAI.
    """
    logger.info("Generating verbal summary of analysis")
    try:
        messages = [{
            "role": "system",
            "content": """You are an expert data analyst presenting findings to a client. 
Create a clear, concise verbal summary of the data analysis results that would sound natural when spoken.
Focus on the most important findings and insights. Use natural, conversational language."""
        }, {
            "role": "user",
            "content": f"""Create a verbal summary of this data analysis that will be converted to speech:

ANALYSIS DATA:
{json.dumps(analysis_data, indent=2)}

Requirements:
1. Start with a brief introduction
2. Focus on key findings and insights
3. Highlight important patterns or trends
4. Use natural, conversational language
5. Keep it concise (2-3 minutes when spoken)
6. End with a brief conclusion

The summary should flow naturally when spoken and avoid technical jargon unless necessary."""
        }]

        await websocket.send_json({
            "status": "Generating verbal summary of the analysis..."
        })

        full_response = await stream_openai_response(
            messages,
            websocket,
            temperature=0.7,
            max_tokens=800
        )
        
        logger.info("Successfully generated verbal summary")
        return full_response

    except Exception as e:
        logger.error(f"Failed to generate verbal summary: {str(e)}")
        raise

async def generate_speech(text: str, websocket: WebSocket) -> bytes:
    """
    Convert text to speech using ElevenLabs API.
    """
    logger.info("Converting summary to speech")
    try:
        await websocket.send_json({
            "status": "Converting summary to speech..."
        })

        if not elevenlabs_client:
            raise Exception("ElevenLabs client not initialized - missing API key")

        audio_stream = elevenlabs_client.text_to_speech.convert(
            text=text,
            voice_id=ELEVENLABS_VOICE_ID,
            model_id=ELEVENLABS_MODEL_ID,
            output_format=ELEVENLABS_OUTPUT_FORMAT
        )
        
        audio_bytes = b''
        for chunk in audio_stream:
            if isinstance(chunk, bytes):
                audio_bytes += chunk
        
        logger.info("Successfully generated speech audio")
        return audio_bytes

    except Exception as e:
        logger.error(f"Failed to generate speech: {str(e)}")
        raise

# WebSocket message handlers
async def handle_analysis_start(data: Dict[str, Any], file_chunks: Dict[str, Dict[str, Any]], websocket: WebSocket):
    """Handle the analysis_start message type."""
    file_names = data.get('fileNames', [])
    prompt = data.get('prompt', '')
    
    for file_name in file_names:
        file_chunks[file_name] = {
            'chunks': [],
            'total_chunks': None,
            'received_chunks': 0
        }
    
    logger.info(f"Starting analysis for files: {file_names}")
    return file_names, prompt

async def handle_file_chunk(data: Dict[str, Any], file_chunks: Dict[str, Dict[str, Any]], websocket: WebSocket):
    """Handle the file_chunk message type."""
    file_name = data.get('fileName')
    chunk_index = data.get('chunkIndex')
    total_chunks = data.get('totalChunks')
    content = data.get('content')
    
    if file_name not in file_chunks:
        raise Exception(f"Received chunk for unknown file: {file_name}")
    
    file_info = file_chunks[file_name]
    if file_info['total_chunks'] is None:
        file_info['total_chunks'] = total_chunks
        file_info['chunks'] = [None] * total_chunks
    
    file_info['chunks'][chunk_index] = content
    file_info['received_chunks'] += 1
    
    # Send acknowledgment
    await websocket.send_json({
        'type': 'chunk_received',
        'fileName': file_name,
        'chunkIndex': chunk_index
    })
    
    logger.info(f"Received chunk {chunk_index + 1}/{total_chunks} for {file_name}")

async def handle_analysis_ready(file_chunks: Dict[str, Dict[str, Any]], prompt: str, websocket: WebSocket):
    """Handle the analysis_ready message type."""
    logger.info("All files received, starting analysis")
    
    # Save complete files
    for file_name, file_info in file_chunks.items():
        if file_info['received_chunks'] != file_info['total_chunks']:
            raise Exception(f"Incomplete file received: {file_name}")
        
        complete_content = ''.join(file_info['chunks'])
        file_path = os.path.join(INPUT_DIR, file_name)
        
        with open(file_path, 'w') as f:
            f.write(complete_content)
    
    # Generate and save analysis code
    try:
        analysis_code = await generate_analysis_code(list(file_chunks.keys()), prompt, websocket)
        with open(ANALYSIS_SCRIPT_PATH, 'w') as f:
            f.write(analysis_code)
        logger.info("Successfully generated and saved analysis code")
    except Exception as e:
        logger.error(f"Error generating analysis code: {str(e)}")
        await websocket.send_json({"error": f"Error generating analysis code: {str(e)}"})
        return
    
    # Execute the analysis script with retries
    current_retry = 0
    current_script = analysis_code
    success = False

    while current_retry < MAX_RETRIES and not success:
        try:
            await execute_analysis_script(ANALYSIS_SCRIPT_PATH, websocket)
            if os.path.exists(ANALYSIS_RESULTS_PATH):
                success = True
                break
        except Exception as e:
            error_message = str(e)
            logger.error(f"Analysis script failed (attempt {current_retry + 1}/{MAX_RETRIES}): {error_message}")
            await websocket.send_json({"status": "Improving analysis..."})
            
            current_script, success = await iterate_analysis_script(
                list(file_chunks.keys()),
                prompt,
                current_script,
                error_message,
                websocket
            )
            if success:
                break
            current_retry += 1

    if not success:
        raise Exception("Failed to execute analysis script after maximum retries")

    # Generate reports and summaries
    if not os.path.exists(ANALYSIS_RESULTS_PATH):
        logger.error("Analysis results JSON not found")
        return
    
    await websocket.send_json({"status": "Generating report..."})
    await generate_html_report(ANALYSIS_RESULTS_PATH, REPORT_HTML_PATH, websocket)
    
    # Convert HTML to PDF
    generate_pdf_from_html(REPORT_HTML_PATH, REPORT_PDF_PATH, websocket)
    
    # Read file contents
    with open(REPORT_HTML_PATH, 'r', encoding='utf-8') as f:
        html_content = f.read()
    with open(REPORT_PDF_PATH, 'rb') as f:
        pdf_content = f.read()
    
    # Read analysis data and encode images
    with open(ANALYSIS_RESULTS_PATH, 'r') as f:
        analysis_data = json.load(f)
    
    image_data = {}
    visualizations = analysis_data.get('visualizations', {})
    for plot_path in visualizations.get('plots', []):
        full_path = os.path.join(OUTPUT_DIR, os.path.basename(plot_path))
        if os.path.exists(full_path):
            with open(full_path, 'rb') as f:
                image_content = f.read()
                image_data[os.path.basename(plot_path)] = base64.b64encode(image_content).decode('utf-8')
    
    # Modify HTML content to use base64 encoded images
    for image_name, image_content in image_data.items():
        html_content = html_content.replace(
            f'src="{image_name}"',
            f'src="data:image/png;base64,{image_content}"'
        )
    
    # Generate verbal summary and speech
    try:
        verbal_summary = await generate_verbal_summary(analysis_data, websocket)
        audio_content = await generate_speech(verbal_summary, websocket)
        audio_base64 = base64.b64encode(audio_content).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to generate speech content: {str(e)}")
        audio_base64 = None
        await websocket.send_json({
            "content": f"⚠️ Could not generate speech: {str(e)}\n\n"
        })
    
    # Send completion message with all content
    await websocket.send_json({
        "status": "completed",
        "html_content": html_content,
        "pdf_content": base64.b64encode(pdf_content).decode('utf-8'),
        "image_data": image_data,
        "audio_content": audio_base64,
        "verbal_summary": verbal_summary if audio_base64 else None
    })

# WebSocket endpoint for data analysis
@app.websocket("/ws/analyze")
async def analyze_data(websocket: WebSocket):
    """WebSocket endpoint for data analysis."""
    await manager.connect(websocket)
    logger.info("New WebSocket connection established")
    
    file_chunks = {}
    prompt = ""
    
    try:
        while True:
            try:
                data = await websocket.receive_json()
                message_type = data.get('type', '')
                
                if message_type == 'analysis_start':
                    _, prompt = await handle_analysis_start(data, file_chunks, websocket)
                elif message_type == 'file_chunk':
                    await handle_file_chunk(data, file_chunks, websocket)
                elif message_type == 'analysis_ready':
                    await handle_analysis_ready(file_chunks, prompt, websocket)
                    file_chunks.clear()
                
            except WebSocketDisconnect:
                logger.info("WebSocket disconnected")
                manager.disconnect(websocket)
                break
            except Exception as e:
                logger.error(f"Error in analyze_data: {str(e)}", exc_info=True)
                await websocket.send_json({"error": str(e)})
    except Exception as e:
        logger.error(f"Fatal error in analyze_data: {str(e)}", exc_info=True)
        manager.disconnect(websocket)

# Run the app with uvicorn if this script is executed directly
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
