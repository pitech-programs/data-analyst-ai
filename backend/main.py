# Import required libraries
from fastapi import FastAPI, WebSocket, WebSocketDisconnect # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize OpenAI client
openai.api_key = os.getenv("OPENAI_API_KEY")

# Create FastAPI app
app = FastAPI()

# Add CORS middleware (update allow_origins and allow_methods in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[""],
    allow_credentials=True,
    allow_methods=[""],
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

# Generate Python code for data analysis using OpenAI API
async def generate_analysis_code(file_names: List[str], analysis_prompt: str, websocket: WebSocket) -> str:
    """
    Generate Python code for data analysis using OpenAI API.
    """
    logger.info(f"Starting code generation for files: {', '.join(file_names)}")
    logger.info(f"Analysis prompt: {analysis_prompt}")

    # Read CSV structure information
    file_structures = []
    for file_name in file_names:
        try:
            import pandas as pd
            file_path = os.path.join(INPUT_DIR, file_name)
            df = pd.read_csv(file_path)
            structure = f"\nFile: {file_name}\nColumns: {', '.join(df.columns)}\nFirst two rows:\n{df.head(2).to_string()}\n"
            file_structures.append(structure)
        except Exception as e:
            logger.warning(f"Could not read structure for {file_name}: {str(e)}")
            file_structures.append(f"\nFile: {file_name}\nStructure could not be read.")

    messages = [{
        "role": "system",
        "content": "You are a data analysis assistant with the ability to write Python code. Provide your response with explanations, but wrap the actual Python code in ```python ``` blocks."
    }, {
        "role": "user",
        "content": f"""Write a self-contained Python script that:

Imports necessary libraries (pandas, matplotlib.pyplot, json, os).
Reads the following CSV files from the 'input' directory: {', '.join(file_names)}.

Here is the structure of each file:
{''.join(file_structures)}

Analyzes the data with focus on: {analysis_prompt}.
Computes relevant statistics (e.g., mean, median, counts) based on the prompt.
Make sure to use the correct data types for the statistics. (dont calcualte correlation on String etc.)
Generates at least two plots using matplotlib (e.g., bar, scatter, histogram) and saves them as PNG files to the 'output' directory with descriptive filenames (e.g., 'output/plot1.png').
Outputs the analysis results to 'output/analysis_results.json' in this format:
{{
    "description": "Textual description of the analysis",
    "statistics": "Key statistics as a string or dictionary",
    "plots": ["path/to/plot1.png", "path/to/plot2.png"]
}}
"""
    }]

    try:
        logger.info("Making API call to OpenAI")
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
        )
        full_response = response.choices[0].message.content.strip()
        logger.info("Received response from OpenAI")
        
        # Extract only the Python code from between ```python and ``` markers
        import re
        code_match = re.search(r'```python\n(.*?)```', full_response, re.DOTALL)
        if not code_match:
            logger.error("No Python code block found in the response")
            raise Exception("No Python code block found in the response")
            
        code = code_match.group(1).strip()
        logger.info("Successfully extracted Python code from response")
        return code
    except Exception as e:
        logger.error(f"Failed to generate analysis code: {str(e)}", exc_info=True)
        raise

# Execute the generated analysis script
async def execute_analysis_script(script_path: str, websocket: WebSocket):
    """
    Execute the generated analysis script.
    """
    logger.info(f"Starting execution of analysis script: {script_path}")
    try:
        logger.info("Running analysis script")
        result = subprocess.run(['python', script_path], capture_output=True, text=True)
        if result.returncode != 0:
            error_msg = f"Script execution failed: {result.stderr}"
            logger.error(error_msg)
            raise Exception(error_msg)
        logger.info("Analysis script executed successfully")
        return result.stdout
    except Exception as e:
        logger.error(f"Error executing analysis script: {str(e)}", exc_info=True)
        raise

# Generate an HTML report from the analysis results using OpenAI API
def generate_html_report(analysis_json_path: str, output_html_path: str, websocket: WebSocket):
    """
    Generate an HTML report from the analysis results using OpenAI API.
    """
    logger.info(f"Starting HTML report generation from {analysis_json_path}")
    try:
        # Load analysis data from JSON file
        logger.info("Loading analysis results from JSON")
        with open(analysis_json_path, 'r') as f:
            analysis_data = json.load(f)

        description = analysis_data.get('description', 'No description provided.')
        statistics = analysis_data.get('statistics', 'No statistics provided.')
        plots = analysis_data.get('plots', [])
        
        # Remove 'output/' prefix from plot paths since HTML will be in the same directory
        plots = [plot.replace('output/', '') for plot in plots]
        logger.info(f"Loaded analysis data with {len(plots)} plots")

        # Prepare the prompt for OpenAI
        messages = [{
            "role": "system",
            "content": "You are an expert HTML/CSS developer. Create a beautiful, modern HTML report using Tailwind CSS. The HTML should be a single self-contained file with the Tailwind CDN included."
        }, {
            "role": "user",
            "content": f"""Create a complete HTML report page with the following data:

Description: {description}

Statistics: {statistics}

Plot images to include: {plots}

Requirements:
1. Use Tailwind CSS for styling (include CDN)
2. Create a modern, professional design
3. Make it responsive
4. Include proper sections for description, statistics, and plots
5. Format the statistics section nicely (if it's JSON/dict, format it properly)
6. Include a header with title and timestamp
7. Make the plots display in a grid on larger screens and stack on mobile
8. Add subtle animations for better UX
9. Ensure good readability with proper spacing and typography
10. Include a footer

Return only the complete HTML code."""
        }]

        # Make API call to OpenAI
        logger.info("Making API call to OpenAI for HTML generation")
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
        )
        
        full_response = response.choices[0].message.content.strip()
        
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


# Convert HTML to PDF using pdfkit
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

The script should analyze these files: {', '.join(file_names)}
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
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.2,
        )
        full_response = response.choices[0].message.content.strip()
        
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

# WebSocket endpoint for data analysis
@app.websocket("/ws/analyze")
async def analyze_data(websocket: WebSocket):
    # Connect to the WebSocket
    await manager.connect(websocket)
    logger.info("New WebSocket connection established")
    
    try:
        while True:
            try:
                # Receive data from WebSocket
                data = await websocket.receive_json()
                logger.info("Received WebSocket data for analysis")
                
                # Extract parameters from the received data
                files_data = data.get("files", [])
                use_local_model = data.get("useLocalModel", False)
                analysis_prompt = data.get("prompt", "")
                
                logger.info(f"Analysis request: {len(files_data)} files, useLocalModel={use_local_model}")
                
                # Check if local model is requested (not supported)
                if use_local_model:
                    logger.warning("Local model requested but not supported")
                    continue
                
                # Check if files and prompt are provided
                if not files_data or not analysis_prompt:
                    logger.warning("Missing required parameters: files or prompt")
                    continue
                
                # Save CSV files to input directory
                file_names = []
                for file_data in files_data:
                    file_name = file_data['name']
                    file_content = file_data['content']
                    file_path = os.path.join(INPUT_DIR, file_name)
                    logger.info(f"Saving input file: {file_name}")
                    with open(file_path, 'w') as f:
                        f.write(file_content)
                    file_names.append(file_name)
                
                # Generate and save analysis code
                analysis_code = await generate_analysis_code(file_names, analysis_prompt, websocket)
                script_path = os.path.join(TEMP_DIR, 'analysis_script.py')
                with open(script_path, 'w') as f:
                    f.write(analysis_code)
                
                # Execute the analysis script with retries
                max_retries = 3
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
                        await websocket.send_json({"status": f"Attempt {current_retry + 1} failed, retrying with improvements..."})
                        
                        current_script, success = await iterate_analysis_script(
                            file_names,
                            analysis_prompt,
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
                    
                output_html_path = os.path.join(OUTPUT_DIR, 'report.html')
                generate_html_report(analysis_json_path, output_html_path, websocket)
                
                # Convert HTML to PDF
                output_pdf_path = os.path.join(OUTPUT_DIR, 'report.pdf')
                generate_pdf_from_html(output_html_path, output_pdf_path, websocket)
                
                # Send completion message with PDF path
                await websocket.send_json({
                    "status": "completed",
                    "pdf_path": output_pdf_path
                })
                
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
