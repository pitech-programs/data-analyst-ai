# Import required libraries
from fastapi import FastAPI, WebSocket, WebSocketDisconnect # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from fastapi.staticfiles import StaticFiles # type: ignore
import json
import asyncio
import os
import subprocess
from typing import List
import openai
from weasyprint import HTML # type: ignore
from dotenv import load_dotenv # type: ignore
import logging
import uvicorn # type: ignore
import base64

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

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

# Define directories for temporary, input, and output files
TEMP_DIR = 'temp'
INPUT_DIR = 'input'
OUTPUT_DIR = 'output'

# Create directories if they don't exist
for dir_path in [TEMP_DIR, INPUT_DIR, OUTPUT_DIR]:
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

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
        logger.info("Making API call to OpenAI")
        client = openai.OpenAI()
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            stream=True,
        )
        
        logger.info("Stream object created, beginning to process chunks")
        full_response = ""
        code_section = False
        current_section = ""
        
        await websocket.send_json({
            "content": "💭 Planning the analysis approach:\n\n"
        })

        for chunk in stream:
            if chunk and chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                
                # Check if we're entering or leaving a code block
                if "```python" in content:
                    code_section = True
                    current_section = "```python\n"
                    continue
                elif "```" in content and code_section:
                    code_section = False
                    if current_section:
                        await websocket.send_json({
                            "content": "🔧 Generated analysis code. Now preparing to execute...\n\n"
                        })
                    current_section = ""
                    continue
                
                # If we're in a code section, accumulate the code
                if code_section:
                    current_section += content
                else:
                    # If not in code section, stream the planning/thinking process
                    if content.strip():
                        await websocket.send_json({
                            "content": content
                        })
        
        logger.info("Received response from OpenAI")
        
        # Extract only the Python code from between ```python and ``` markers
        import re
        code_match = re.search(r'```python\n(.*?)```', full_response, re.DOTALL)
        if not code_match:
            logger.error("No Python code block found in the response")
            raise Exception("No Python code block found in the response")
            
        code = code_match.group(1).strip()
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
5. Properly saves results to 'output/analysis_results.json'
"""
    }]

    try:
        logger.info("Making API call to OpenAI for script fix")
        client = openai.OpenAI()
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            stream=True,
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
                if "```python" in content:
                    code_section = True
                    current_section = "```python\n"
                    continue
                elif "```" in content and code_section:
                    code_section = False
                    current_section = ""
                    continue
                
                # If we're in a code section, accumulate the code
                if code_section:
                    current_section += content
                else:
                    # If not in code section, stream the content directly
                    if content.strip():
                        await websocket.send_json({
                            "content": content
                        })
        
        # Extract only the Python code from between ```python and ``` markers
        import re
        code_match = re.search(r'```python\n(.*?)```', full_response, re.DOTALL)
        if not code_match:
            logger.error("No Python code block found in the response")
            return current_script, False
            
        new_script = code_match.group(1).strip()
        logger.info("Generated fixed script")

        # Save and execute the new script
        script_path = os.path.join(TEMP_DIR, 'analysis_script.py')
        with open(script_path, 'w') as f:
            f.write(new_script)

        try:
            await execute_analysis_script(script_path, websocket)
            # Check if the JSON file was created
            if os.path.exists(os.path.join(OUTPUT_DIR, 'analysis_results.json')):
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

# Generate an HTML report from the analysis results using OpenAI API
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
        
        # Prepare the prompt for OpenAI
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
   
2. Core Sections:
   - Title and header
   - Key findings summary
   - Data quality overview
   - Statistical results
   - Visualizations with descriptions
   - Analysis metadata footer

3. Design Features:
   - Clean, professional layout
   - Responsive design (mobile and desktop)
   - Card-based content sections
   - Clear typography and spacing

Return only the complete HTML code with all required scripts and styles included."""
        }]

        # Make API call to OpenAI
        logger.info("Making API call to OpenAI for HTML generation")
        client = openai.OpenAI()
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            stream=True,
        )
        
        logger.info("Stream object created, beginning to process chunks")
        full_response = ""
        in_html = False
        
        for chunk in stream:
            if chunk and chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                
                # Check if we're entering or leaving an HTML block
                if "```html" in content:
                    in_html = True
                    continue
                elif "```" in content and in_html:
                    in_html = False
                    continue
                
                # Stream all non-empty content directly
                if content.strip():
                    await websocket.send_json({
                        "content": content
                    })
        
        # Extract only the HTML from between ```html and ``` markers
        import re
        html_match = re.search(r'```html\n(.*?)```', full_response, re.DOTALL)
        if not html_match:
            logger.error("No HTML code block found in the response")
            raise Exception("No HTML code block found in the response")
            
        html_content = html_match.group(1).strip()
        logger.info("Successfully extracted HTML content from response")

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

# WebSocket endpoint for data analysis
@app.websocket("/ws/analyze")
async def analyze_data(websocket: WebSocket):
    # Connect to the WebSocket
    await manager.connect(websocket)
    logger.info("New WebSocket connection established")
    
    # Dictionary to store file chunks
    file_chunks = {}
    
    try:
        while True:
            try:
                # Receive data from WebSocket
                data = await websocket.receive_json()
                message_type = data.get('type', '')
                
                if message_type == 'analysis_start':
                    # Initialize file chunks for each file
                    file_names = data.get('fileNames', [])
                    prompt = data.get('prompt', '')
                    
                    for file_name in file_names:
                        file_chunks[file_name] = {
                            'chunks': [],
                            'total_chunks': None,
                            'received_chunks': 0
                        }
                    
                    logger.info(f"Starting analysis for files: {file_names}")
                    
                elif message_type == 'file_chunk':
                    # Process file chunk
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
                    
                elif message_type == 'analysis_ready':
                    # All files received, start analysis
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
                        script_path = os.path.join(TEMP_DIR, 'analysis_script.py')
                        with open(script_path, 'w') as f:
                            f.write(analysis_code)
                        logger.info("Successfully generated and saved analysis code")
                    except Exception as e:
                        logger.error(f"Error generating analysis code: {str(e)}")
                        await websocket.send_json({"error": f"Error generating analysis code: {str(e)}"})
                        continue
                    
                    # Execute the analysis script with retries
                    max_retries = 5
                    current_retry = 0
                    current_script = analysis_code
                    success = False

                    while current_retry < max_retries and not success:
                        try:
                            await execute_analysis_script(script_path, websocket)
                            if os.path.exists(os.path.join(OUTPUT_DIR, 'analysis_results.json')):
                                success = True
                                break
                        except Exception as e:
                            error_message = str(e)
                            logger.error(f"Analysis script failed (attempt {current_retry + 1}/{max_retries}): {error_message}")
                            await websocket.send_json({"status": "Retrying analysis..."})
                            
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

                    # Generate HTML report from analysis results
                    analysis_json_path = os.path.join(OUTPUT_DIR, 'analysis_results.json')
                    if not os.path.exists(analysis_json_path):
                        logger.error("Analysis results JSON not found")
                        continue
                    
                    await websocket.send_json({"status": "Generating report..."})
                    output_html_path = os.path.join(OUTPUT_DIR, 'report.html')
                    await generate_html_report(analysis_json_path, output_html_path, websocket)
                    
                    # Convert HTML to PDF
                    output_pdf_path = os.path.join(OUTPUT_DIR, 'report.pdf')
                    generate_pdf_from_html(output_html_path, output_pdf_path, websocket)
                    
                    # Read file contents
                    with open(output_html_path, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    with open(output_pdf_path, 'rb') as f:
                        pdf_content = f.read()
                    
                    # Read image files and encode them
                    with open(analysis_json_path, 'r') as f:
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
                    
                    # Send completion message with file contents
                    await websocket.send_json({
                        "status": "completed",
                        "html_content": html_content,
                        "pdf_content": base64.b64encode(pdf_content).decode('utf-8'),
                        "image_data": image_data
                    })
                    
                    # Clear file chunks
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
