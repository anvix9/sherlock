import logging
import time
from pathlib import Path
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from docling.document_converter import DocumentConverter, PdfFormatOption
from datetime import datetime
import re
import os
import json
import arxiv
import requests
import subprocess
import platform
import shutil
from typing import Union

def setup_logging():
    """Set up logging configuration with file and console handlers."""
    logs_dir = Path('./.logs')
    logs_dir.mkdir(exist_ok=True)
    
    # Create timestamped log filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = logs_dir / f'docling_process_{timestamp}.log'
    
    # Set up logging configuration
    logging.basicConfig(level=logging.INFO,
                       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                       handlers=[
                           # File handler with detailed logging
                           logging.FileHandler(log_file),
                           # Console handler with only ERROR and critical status messages
                           logging.StreamHandler()
                       ])
    
    # Set console handler to only show ERROR and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # Get root logger and replace its console handler
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
    root_logger.addHandler(console_handler)
    
    return logging.getLogger(__name__)

def generate(path: Union[str, Path], cleanup: bool = True) -> None:
    """
    Main function to process PDF papers and generate analysis cards.
    
    Args:
        path: Path to a single PDF file or directory containing PDF files
        cleanup: Whether to remove intermediate folders after processing
    """
    logger = setup_logging()
    start_time = time.time()
    
    try:
        path = Path(path) if isinstance(path, str) else path
        
        if not path.exists():
            raise FileNotFoundError(f"Input path does not exist: {path}")
        
        # Create temporary directories
        temp_dirs = {
            'converted_markdowns': Path('./converted_markdowns'),
            'paper_compressed': Path('./paper_compressed'),
            'paper_metadata': Path('./paper_metadata'),
            'paper_analysis': Path('./paper_analysis')
        }
        
        # Create output directory for cards
        cards_dir = Path('./card_papers')
        cards_dir.mkdir(exist_ok=True)
        
        # Create all temporary directories
        for dir_path in temp_dirs.values():
            dir_path.mkdir(exist_ok=True)
        
        logger.info("Starting paper processing pipeline...")
        print(f"Processing papers from: {path}")  # Console status
        
        # Processing steps
        logger.info("Converting PDFs to Markdown...")
        compresser(str(path))
        
        logger.info("Extracting relevant sections...")
        paper_compresser()
        
        logger.info("Fetching paper metadata...")
        input_folder = "./paper_compressed/"
        pdf_files = [f.rsplit("_extracted")[0] for f in os.listdir(input_folder) if f.endswith('.md')]
        fetch_arxiv_data(pdf_files)
        
        logger.info("Setting up Ollama and generating analysis...")
        if not setup_ollama():
            raise RuntimeError("Failed to setup Ollama requirements.")
        process_markdown_files("./converted_markdowns", "./paper_analysis")
        
        logger.info("Generating paper cards...")
        generate_paper_cards()
        
        # Cleanup if requested
        if cleanup:
            logger.info("Cleaning up temporary directories...")
            for dir_name, dir_path in temp_dirs.items():
                try:
                    shutil.rmtree(dir_path)
                    logger.info(f"Removed {dir_name}")
                except Exception as e:
                    logger.warning(f"Failed to remove {dir_name}: {e}")
        
        elapsed_time = time.time() - start_time
        logger.info(f"Processing completed in {elapsed_time:.2f} seconds")
        print(f"Processing completed in {elapsed_time:.2f} seconds")  # Console status
        print(f"Generated cards are available in: {cards_dir.absolute()}")  # Console status
        
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        print(f"Error during processing: {e}")  # Console error
        if cleanup:
            logger.info("Attempting cleanup after error...")
            for dir_path in temp_dirs.values():
                if dir_path.exists():
                    try:
                        shutil.rmtree(dir_path)
                    except Exception as cleanup_error:
                        logger.warning(f"Cleanup error: {cleanup_error}")
        raise

def check_requirements() -> bool:
    """
    Check if all required external dependencies are available.
    Returns True if all requirements are met, False otherwise.
    """
    logger = logging.getLogger(__name__)
    try:
        # Check if Ollama is installed and running
        if not verify_ollama_installation():
            logger.error("Ollama is not installed")
            return False
            
        # Check if the required model is available
        if not ensure_model_available("saish_15/tethysai_research"):
            logger.error("Required Ollama model is not available")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error checking requirements: {e}")
        return False

def process_pdfs(input_path: Path, output_dir: Path, doc_converter: DocumentConverter) -> None:
    """
    Process a single PDF file or all PDF files in the given directory.
    """
    logger = logging.getLogger(__name__)
    
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        pdf_files = [input_path]
    elif input_path.is_dir():
        pdf_files = list(input_path.glob("*.pdf"))
        if not pdf_files:
            logger.warning(f"No PDF files found in directory: {input_path}")
            return
    else:
        logger.error(f"Invalid input path: {input_path}")
        return

    for pdf_file in pdf_files:
        logger.info(f"Processing file: {pdf_file}")
        start_time = time.time()

        try:
            conv_result = doc_converter.convert(pdf_file)
            if not hasattr(conv_result, "document") or not conv_result.document:
                logger.error(f"Conversion result is empty for file {pdf_file}")
                continue

            output_filename = f"{pdf_file.stem}.md"
            output_file = output_dir / output_filename

            markdown_content = conv_result.document.export_to_markdown()
            with output_file.open("w", encoding="utf-8") as fp:
                fp.write(markdown_content)

            logger.info(f"Markdown exported successfully to {output_file}")

        except Exception as e:
            logger.error(f"Error processing file {pdf_file}: {e}")
        finally:
            elapsed_time = time.time() - start_time
            logger.info(f"Finished processing {pdf_file} in {elapsed_time:.2f} seconds")

def compresser(path):
    logger = logging.getLogger(__name__)

    input_path = Path(f"{path}")
    output_dir = Path("./converted_markdowns/")

    if not input_path.exists():
        logger.error(f"Input path {input_path} does not exist")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True
    pipeline_options.table_structure_options.do_cell_matching = True
    pipeline_options.ocr_options.lang = ["en"]
    pipeline_options.accelerator_options = AcceleratorOptions(
        num_threads=4, device=AcceleratorDevice.AUTO
    )

    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    process_pdfs(input_path, output_dir, doc_converter)

def extract_sections(input_file, sections_to_extract):
    """Extract sections from a Markdown file based on target section headers starting with '##'."""
    logger = logging.getLogger(__name__)
    
    try:
        with open(input_file, 'r', encoding='utf-8') as file:
            content = file.read()
    except Exception as e:
        logger.error(f"Error reading file {input_file}: {e}")
        return ""

    sections_to_extract = {section.lower() for section in sections_to_extract}
    section_pattern = re.compile(r"^##\s*(.+)$", re.MULTILINE)
    
    sections = list(section_pattern.finditer(content))
    extracted_content = ""

    for i, match in enumerate(sections):
        section_name = re.sub(r'[^a-zA-Z0-9\s]', '', match.group(1).strip().lower())
        section_name = section_name.split(' ')[-1]
        if section_name in sections_to_extract:
            start = match.end()
            end = sections[i + 1].start() if i + 1 < len(sections) else len(content)
            section_content = content[start:end].strip()
            extracted_content += f"## {match.group(1).strip()}\n\n{section_content}\n\n"

    return extracted_content

def paper_compresser():
    logger = logging.getLogger(__name__)
    
    input_dir = './converted_markdowns/'
    output_dir = os.path.join(os.getcwd(), 'paper_compressed')
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    sections_to_extract = [
        "Abstract", "Introduction", "Method", "Conclusion", "study", "studies", 
        # ... (rest of the sections list remains the same)
    ]
    
    md_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.md')]

    if not md_files:
        logger.error(f"No .MD files found in {input_dir}")
        return

    for md_file in md_files:
        input_path = os.path.join(input_dir, md_file)

        try:
            extracted_content = extract_sections(input_path, sections_to_extract)
            output_path = os.path.join(output_dir, f"{Path(md_file).stem}_extracted.md")
            
            with open(output_path, 'w', encoding='utf-8') as file:
                file.write(extracted_content)

            logger.info(f"Successfully extracted sections to {output_path}")

        except Exception as e:
            logger.error(f"Error processing {md_file}: {e}")

def fetch_arxiv_data(paper_ids):
    logger = logging.getLogger(__name__)
    data = []
    client = arxiv.Client()
    
    for paper_id in paper_ids:
        paper_id = paper_id.split("_")[0]
        logger.info(f"Fetching {paper_id}...")
        
        try:
            search = arxiv.Search(id_list=[paper_id])
            paper = next(client.results(search))
            paper_data = {
                "id": paper_id,
                "title": paper.title,
                "authors": [str(author) for author in paper.authors],
                "submission_date": paper.published.strftime("%Y-%m-%d"),
                "link": paper.entry_id,
            }
            data.append(paper_data)
            time.sleep(4)
            
        except Exception as e:
            logger.error(f"Error processing {paper_id}: {e}")
            
    with open("./paper_metadata/metadata.json", 'w') as json_file:
        json.dump(data, json_file, indent=4)
    logger.info("Data saved to metadata.json")

# Ollama-related functions remain largely unchanged, but with added logging
def check_ollama_service():
    logger = logging.getLogger(__name__)
    try:
        response = requests.get("http://127.0.0.1:11434/api/version", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        logger.error("Failed to connect to Ollama service")
        return False

def ensure_model_available(model_name):
    logger = logging.getLogger(__name__)
    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/show",
            json={"name": model_name},
            timeout=5
        )
        return response.status_code == 200
    except requests.exceptions.RequestException:
        logger.error(f"Failed to verify model {model_name}")
        return False

def verify_ollama_installation():
    logger = logging.getLogger(__name__)
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["where", "ollama"], capture_output=True, text=True)
        else:
            result = subprocess.run(["which", "ollama"], capture_output=True, text=True)
        return result.returncode == 0
    except subprocess.SubProcessError:
        logger.error("Failed to verify Ollama installation")
        return False

def setup_ollama(required_model="saish_15/tethysai_research"):
    logger = logging.getLogger(__name__)
    
    if not verify_ollama_installation():
        logger.error("Ollama is not installed")
        print("Error: Ollama is not installed. Please install from https://ollama.ai/download")
        return False
    
    if not check_ollama_service():
        logger.info("Attempting to start Ollama service...")
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["ollama", "serve"], 
                               creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(["ollama", "serve"])
            
            if not check_ollama_service():
                logger.error("Failed to start Ollama service")
                return False
            logger.info("Ollama service started successfully")
        except Exception as e:
            logger.error(f"Error starting Ollama service: {e}")
            return False

    if not ensure_model_available(required_model):
        logger.info(f"Pulling required model: {required_model}")
        try:
            subprocess.run(["ollama", "pull", required_model], check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Error pulling model: {e}")
            return False
        
    return True

def process_markdown_files(input_folder, output_folder):
    logger = logging.getLogger(__name__)
    
    os.makedirs(output_folder, exist_ok=True)
    
    research_question_sections = [
        "Abstract", "Introduction", "Conclusion", "goals", "Motivation", "Motivations", 
        "overview", "problem statement", "research problem", "objectives", "aims", "objective",
        "main"
    ]
    
    method_questions = [
        "Method", "Methods", "architecture", "Abstract", "study", "studies", 
        "methodologies", "approach", "approaches", "preliminary", "preliminaries",
        "Technical specifications", "Specifications","Problem-setup", "Pre-training",
        "experimental setup","approximate methods","procedure", "ablations", "ablation study", "Model", "Dataset",
        "details", "evaluation tasks", "data construction", "inference","field architecture", "implementation study", "setup",
        "experiment settings", "design recipes","method and data collection", "Materials", "discussions"
    ]

    results_question_sections = [
        "conclusion", "discussion", "study", "studies", "future work", 
        "Summary", "Abstract", "future directions","Limitation", "limitations", "limitation",
        "analysis",  "evaluations", "Broader impacts", "impact", "impacts", 
        "objectives",  "main results", "evaluations", "training principles", "summary statistics", "conclusions, limitations, and discussion",
        "limitations and future works", "limitation and future work", "conclusion and discussion"
    ]
    
    themes = ['research', 'method', 'results']
    markdown_files = [f for f in os.listdir(input_folder) if f.endswith('.md')]
    total_files = len(markdown_files)
    
    for idx, md_file in enumerate(markdown_files, 1):
        logger.info(f"Processing {md_file}...")
        if idx % 5 == 0:
            print(f"Progress: {idx}/{total_files} files processed")
            
        file_path = os.path.join(input_folder, md_file)
        complete = {}
        research_content = ""
        
        sections, _ = extract_sections(file_path, research_question_sections)
        if sections:
            research_content = "\n\n".join(sections.values())
            topics = get_topics(research_content)
            complete["topics"] = topics
            logger.info(f"Extracted topics for {md_file}")
        
        for theme in themes:
            if theme == "research":
                tmp_contents = research_content
            elif theme == "method":
                sections, _ = extract_sections(file_path, method_questions)
                tmp_contents = "\n\n".join(sections.values()) if sections else ""
            elif theme == "results":
                sections, _ = extract_sections(file_path, results_question_sections)
                tmp_contents = "\n\n".join(sections.values()) if sections else ""

            if tmp_contents:
                res = get_llama_question(tmp_contents, theme)
                complete[theme] = res
                logger.info(f"Generated {theme} analysis for {md_file}")
            else:
                complete[theme] = "No relevant sections found"
                logger.warning(f"No {theme} sections found for {md_file}")
        
        output_filename = os.path.splitext(md_file)[0] + '_analysis.json'
        output_path = os.path.join(output_folder, output_filename)
        
        with open(output_path, 'w', encoding='utf-8') as outfile:
            json.dump(complete, outfile, indent=4)
        
        logger.info(f"Saved analysis for {md_file} to {output_filename}")

def get_topics(content):
    logger = logging.getLogger(__name__)
    _url = "http://127.0.0.1:11434/api/generate"
    logger.info("Extracting topics...")
    
    _custom_prompt = (
        f"Based on this paper content, identify the main key words and topics or research areas it addresses. "
        f"Return ONLY a list of 3-7 specific research key words, topics or subfields emphasizing the techniques, etc... "
        f"Format the response as a Python list of strings. Example format: ['Topic1', 'Topic2', 'Topic3']. "
        f"Content: {content}"
    )
    
    _payload = {
        "model": "saish_15/tethysai_research",
        "prompt": _custom_prompt,
        "stream": False,
        "options": {"num_ctx": 6000},
        "keep_alive": -1
    }
    
    try:
        response = requests.post(_url, data=json.dumps(_payload))
        response.raise_for_status()
        response_data = response.json()
        
        topics_str = response_data['response'].strip()
        topics_str = re.sub(r'```python|```', '', topics_str).strip()
        topics = eval(topics_str)
        logger.info("Topics extracted successfully")
        return topics
    except Exception as e:
        logger.error(f"Error extracting topics: {e}")
        return ["Topic extraction failed"]

def get_llama_question(section, theme):
    logger = logging.getLogger(__name__)
    _url = "http://127.0.0.1:11434/api/generate"
    logger.info(f"Generating questions for {theme}...")
    
    if theme == 'research':
        _custom_prompt = (
            f"Read the sections carefully and summarize the main research question the authors are addressing. "
            f"Focus on identifying the problem they aim to solve, the motivations behind the study, and any "
            f"explicit or implicit questions they raise in the introduction or abstract or in this passage. "
            f"Simply take the results contribution and convert it into a Research Problem transparently."
            f"The questions must follow this - Q1: ....? etc, Contribution:.... : {section}"
        )
    elif theme == 'method':
        _custom_prompt = (
            f"Analyze the methodology section of the paper and summarize the key methodological approach "
            f"used by the authors. The answer must follow this - Methodology:.....: {section}"
        )
    else:  # results
        _custom_prompt = (
            f"Examine this results section of the paper and summarize the key findings reported by the authors. "
            f"The answer must follow this - Results:.....: {section}"
        )

    _payload = {
        "model": "saish_15/tethysai_research",
        "prompt": _custom_prompt,
        "stream": False,
        "options": {"num_ctx": 6000},
        "keep_alive": -1
    }
    
    try:
        response = requests.post(_url, data=json.dumps(_payload))
        response.raise_for_status()
        response_data = response.json()
        logger.info(f"Successfully generated {theme} questions")
        return response_data['response']
    except requests.exceptions.HTTPError as err:
        logger.error(f"HTTP error in LLaMA request: {err}")
        return "Error in request or code."

def get_tethy_summary(content):
    logger = logging.getLogger(__name__)
    url = "http://127.0.0.1:11434/api/generate"
    
    prompt = (
        f"Summarize this paper content into a bulleted list of main results, Methods and contributions. "
        f"Be short and concise no more than 700 characters. "
        f"Focus on key findings and avoid technical details and add the key words from the topics at the end. Content: {content}"
    )
    
    payload = {
        "model": "saish_15/tethysai_research",
        "prompt": prompt,
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info("Summary generated successfully")
        return response.json()['response']
    except Exception as e:
        logger.error(f"Error getting summary: {e}")
        return None

def generate_paper_cards():
    logger = logging.getLogger(__name__)
    
    try:
        with open('paper_metadata/metadata.json', 'r') as f:
            papers = json.load(f)
    except Exception as e:
        logger.error(f"Error loading metadata: {e}")
        raise
    
    Path('card_papers').mkdir(exist_ok=True)
    
    analysis_files = list(Path('paper_analysis').glob('*_analysis.json'))
    total_files = len(analysis_files)
    
    for idx, analysis_path in enumerate(analysis_files, 1):
        paper_id = analysis_path.stem.replace('_analysis', '')
        logger.info(f"Processing paper {paper_id}")
        
        try:
            with open(analysis_path, 'r') as f:
                analysis = json.load(f)
            
            title = next((paper['title'] for paper in papers if paper['id'] == paper_id), "Unknown Title")
            
            content = f"{analysis['research']}\n{analysis['method']}\n{analysis['results']}"
            summary = get_tethy_summary(content)
            if summary:
                summary = summary.split(":")[-1]
            
            tmp_topics = ", ".join(analysis['topics'])
            
            md_content = f"""# {title}

# Research questions
{analysis['research']}

## Problem Statement, Methods and Main Results
{summary}

#### Keywords: {tmp_topics}

### [Link to paper](https://arxiv.org/abs/{paper_id})
"""
            
            output_path = f"card_papers/{paper_id}_card.md"
            with open(output_path, 'w') as f:
                f.write(md_content)
            
            if idx % 5 == 0:
                print(f"Progress: {idx}/{total_files} cards generated")
                
            logger.info(f"Generated card for {paper_id}")
            
        except Exception as e:
            logger.error(f"Error processing {paper_id}: {e}")
            continue

if __name__ == "__main__":
    try:
        logger = setup_logging()
        logger.info("Starting document processing")
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise
