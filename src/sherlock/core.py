import logging
import time
from pathlib import Path
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
from docling.document_converter import DocumentConverter, PdfFormatOption
import re
import os
import json
import arxiv
import requests
import subprocess
import platform
import shutil
from typing import Union

log = logging.getLogger(__name__)

# Main function handling the pipeline 
def generate(path: Union[str, Path], cleanup: bool = True) -> None:
    """
    Main function to process PDF papers and generate analysis cards.
    
    Args:
        path: Path to a single PDF file or directory containing PDF files
        cleanup: Whether to remove intermediate folders after processing
    """
    try:
        start_time = time.time()
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        
        # Convert path to Path object if string
        path = Path(path) if isinstance(path, str) else path
        
        # Validate input path
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
        
        # Step 1: Convert PDFs to Markdown
        logger.info("Converting PDFs to Markdown...")
        compresser(str(path))
        
        # Step 2: Extract relevant sections
        logger.info("Extracting relevant sections...")
        paper_compresser()
        
        # Step 3: Fetch metadata
        logger.info("Fetching paper metadata...")
        input_folder = "./paper_compressed/"
        pdf_files = [f.rsplit("_extracted")[0] for f in os.listdir(input_folder) if f.endswith('.md')]
        fetch_arxiv_data(pdf_files)
        
        # Step 4: Set up Ollama and generate analysis
        logger.info("Setting up Ollama and generating analysis...")
        if not setup_ollama():
            raise RuntimeError("Failed to setup Ollama requirements.")
        process_markdown_files("./converted_markdowns", "./paper_analysis")
        
        # Step 5: Generate final cards
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
        logger.info(f"Generated cards are available in: {cards_dir.absolute()}")
        
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        # Attempt cleanup on failure if requested
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
    try:
        # Check if Ollama is installed and running
        if not verify_ollama_installation():
            logging.error("Ollama is not installed. Please install from https://ollama.ai/download")
            return False
            
        # Check if the required model is available
        if not ensure_model_available("saish_15/tethysai_research"):
            logging.error("Required Ollama model is not available")
            return False
            
        return True
        
    except Exception as e:
        logging.error(f"Error checking requirements: {e}")
        return False
# PDF converter
def process_pdfs(input_path: Path, output_dir: Path, doc_converter: DocumentConverter) -> None:
    """
    Process a single PDF file or all PDF files in the given directory.

    Args:
        input_path: Path to a single PDF file or a directory containing PDF files
        output_dir: Output directory for markdown files
        doc_converter: Configured DocumentConverter instance
    """
    # Check if input_path is a single file
    if input_path.is_file() and input_path.suffix.lower() == ".pdf":
        pdf_files = [input_path]
    # If a directory, get all PDF files in it
    elif input_path.is_dir():
        pdf_files = list(input_path.glob("*.pdf"))
        if not pdf_files:
            log.warning(f"No PDF files found in directory: {input_path}")
            return
    else:
        log.error(f"Invalid input path: {input_path}. Must be a PDF file or a directory containing PDFs.")
        return

    for pdf_file in pdf_files:
        log.info(f"Processing file: {pdf_file}")
        start_time = time.time()

        try:
            # Convert PDF
            conv_result = doc_converter.convert(pdf_file)
            if not hasattr(conv_result, "document") or not conv_result.document:
                log.error(f"Conversion result is empty for file {pdf_file}. Skipping.")
                continue

            # Create output filename
            output_filename = f"{pdf_file.stem}.md"
            output_file = output_dir / output_filename

            # Export to Markdown
            markdown_content = conv_result.document.export_to_markdown()
            with output_file.open("w", encoding="utf-8") as fp:
                fp.write(markdown_content)

            log.info(f"Markdown exported successfully to {output_file}.")

        except Exception as e:
            log.error(f"Error processing file {pdf_file}: {e}")
        finally:
            elapsed_time = time.time() - start_time
            log.info(f"Finished processing {pdf_file} in {elapsed_time:.2f} seconds.")

def compresser(path):
    logging.basicConfig(level=logging.INFO)

    # Input and Output Paths
    input_path = Path(f"{path}")  # Path to a single PDF file or a directory
    output_dir = Path("./converted_markdowns/")

    if not input_path.exists():
        log.error(f"Input path {input_path} does not exist. Exiting.")
        return

    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)

    # Docling Parse with EasyOCR
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

    # Process PDFs
    process_pdfs(input_path, output_dir, doc_converter)

# Section extraction
def extract_sections(input_file, sections_to_extract):
    """
    Extract sections from a Markdown file based on target section headers starting with '##'.

    Args:
        input_file: Path to the input markdown file
        sections_to_extract: List of section names to extract

    Returns:
        str: Extracted content in markdown format
    """
    with open(input_file, 'r', encoding='utf-8') as file:
        content = file.read()

    # Normalize section names for case-insensitive matching
    sections_to_extract = {section.lower() for section in sections_to_extract}
    # Regex to match sections starting with '##'
    section_pattern = re.compile(r"^##\s*(.+)$", re.MULTILINE)

    # Find all sections and their start positions
    sections = list(section_pattern.finditer(content))
    extracted_content = ""

    for i, match in enumerate(sections):
        section_name = re.sub(r'[^a-zA-Z0-9\s]', '', match.group(1).strip().lower()) 
        section_name = section_name.split(' ')[-1]
        if section_name in sections_to_extract:
            print(section_name)
            start = match.end()
            end = sections[i + 1].start() if i + 1 < len(sections) else len(content)
            section_content = content[start:end].strip()
            extracted_content += f"## {match.group(1).strip()}\n\n{section_content}\n\n"

    return extracted_content

def paper_compresser():
    # File paths
    input_dir = './converted_markdowns/'
    current_dir = os.getcwd()
    output_dir = os.path.join(current_dir, 'paper_compressed')
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    sections_to_extract = [
        "Abstract", "Introduction", "Method", "Conclusion","study", "studies", "discussion", "preliminaries","preliminary",
        "Summary", "Overview", "Background", "Future Work", "Motivation", "Problem Statement", "conclusions", "methodologies","methods",
        "approach", "approaches", "future directions", "architecture", "perspectives", "objectives", "aims", "motivations", "problem statement", "research problem", "goals",
        "Technical specifications", "Specifications", "State-of-the-art", "Problem-setup", "Pre-training", "Limitations", "Materials", "discussions", "limitations", "limitation",
        "experimental setup", "analysis", "approximate methods", "evaluations", "Broader impacts", "impact", "impacts", "procedure", "ablations", "ablation study", "Model", "Dataset",
        "objectives", "objective", "details", "evaluation tasks", "data construction", "inference", "main results", "field architecture", "implementation study", "setup",
        "experiment settings", "design recipes", "evaluations", "training principles", "method and data collection", "summary statistics", "conclusions, limitations, and discussion",
        "limitations and future works", "limitation and future work", "conclusion and discussion"
    ]
    md_files = [f for f in os.listdir(input_dir) if f.lower().endswith('.md')]

    if not md_files:
        print(f"No .MD files found in {input_dir}")
        return

    else:
        # Process each Markdown file
        for md_file in md_files:
            # Construct full input path
            input_path = os.path.join(input_dir, md_file)

            try:
                # Extract sections
                extracted_content = extract_sections(input_path, sections_to_extract)

                # Save to file
                output_path = os.path.join(output_dir, f"{Path(md_file).stem}_extracted.md")
                with open(output_path, 'w', encoding='utf-8') as file:
                    file.write(extracted_content)

                print(f"Successfully extracted sections to {output_path}")

            except Exception as e:
                print(f"Error occurred: {str(e)}")

# Get metadata of the file/s
def fetch_arxiv_data(paper_ids):
    data = []
    client = arxiv.Client()
    
    for paper_id in paper_ids:
        paper_id = paper_id.split("_")[0]

        print(f"Fetching {paper_id}...")
        try:
            # Use the official API to search
            search = arxiv.Search(id_list=[paper_id])
            paper = next(client.results(search))
            print(f"***************************************{paper.title}----{paper.entry_id}") 

            # Extract data
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
            print(f"Error processing {paper_id}: {str(e)}")
            
    # Save metadata
    with open("./paper_metadata/metadata.json", 'w') as json_file:
        json.dump(data, json_file, indent=4)
    print("Data saved to metadata.json")

# Generate questions per section 
def check_ollama_service():
    """
    Check if Ollama is running and available on the local machine.
    Returns True if Ollama is running, False otherwise.
    """
    try:
        response = requests.get("http://127.0.0.1:11434/api/version", timeout=5)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def ensure_model_available(model_name):
    """
    Check if the specified model is available in Ollama.
    Returns True if the model is available, False otherwise.
    """
    try:
        response = requests.post(
            "http://127.0.0.1:11434/api/show",
            json={"name": model_name},
            timeout=5
        )
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

def verify_ollama_installation():
    """
    Verify if Ollama is installed on the system.
    Returns True if Ollama is installed, False otherwise.
    """
    try:
        if platform.system() == "Windows":
            result = subprocess.run(["where", "ollama"], capture_output=True, text=True)
        else:
            result = subprocess.run(["which", "ollama"], capture_output=True, text=True)
        return result.returncode == 0
    except subprocess.SubProcessError:
        return False

def wait_for_ollama_startup(timeout=30):
    """
    Wait for Ollama service to start up.
    Returns True if service started within timeout, False otherwise.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_ollama_service():
            return True
        time.sleep(1)
    return False

def setup_ollama(required_model="saish_15/tethysai_research"):
    """
    Main function to check and setup Ollama requirements.
    Returns True if everything is ready, False otherwise.
    """
    # Check if Ollama is installed
    if not verify_ollama_installation():
        print("Error: Ollama is not installed on your system.")
        print("Please install Ollama first: https://ollama.ai/download")
        return False

    # Check if Ollama service is running
    if not check_ollama_service():
        print("Ollama service is not running. Attempting to start...")
        try:
            if platform.system() == "Windows":
                subprocess.Popen(["ollama", "serve"], 
                               creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(["ollama", "serve"])
            
            if not wait_for_ollama_startup():
                print("Error: Failed to start Ollama service.")
                return False
            print("Ollama service started successfully.")
        except Exception as e:
            print(f"Error starting Ollama service: {str(e)}")
            return False

    # Check if required model is available
    if not ensure_model_available(required_model):
        print(f"Required model '{required_model}' is not available. Attempting to pull...")
        try:
            subprocess.run(["ollama", "pull", required_model], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error pulling model: {str(e)}")
            return False
        
    return True
def get_topics(content):
    """Extract main topics from the paper content using LLaMA."""
    _url = "http://127.0.0.1:11434/api/generate"
    print("Extracting topics...")
    
    _custom_prompt = (
        f"Based on this paper content, identify the main key words and topics or research areas it addresses. "
        f"Return ONLY a list of 3-7 specific research key words, topics or subfields emphasizing the techniques, etc... (like 'Natural Language Processing', "
        f"'Computer Vision', 'Reinforcement Learning', 'DPO', etc.). "
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
        
        # Clean the response to ensure it's a valid Python list
        topics_str = response_data['response'].strip()
        # Remove any markdown formatting if present
        topics_str = re.sub(r'```python|```', '', topics_str).strip()
        # Convert string representation of list to actual list
        topics = eval(topics_str)
        return topics
    except Exception as e:
        print(f"Error extracting topics: {str(e)}")
        return ["Topic extraction failed"]

def get_llama_question(section, theme):
    """Generate questions based on the section content and theme using LLaMA."""
    _url = "http://127.0.0.1:11434/api/generate"
    print(f"generate questions for {theme}...")
    
    if theme == 'research':
        _custom_prompt = (
            f"Read the sections carefully and summarize the main research question the authors are addressing. "
            f"Focus on identifying the problem they aim to solve, the motivations behind the study, and any "
            f"explicit or implicit questions they raise in the introduction or abstract or in this passage. YOU MUST ANSWER the main question 'WHY'"
            f"Simply take the results contribution and convert it into a Research Problem transparently."
            f"Provide the research question in clear and concise terms with high precision. "
            f"IMPORTANT: Do not generate questions like : What is the primary problem addressed by this research paper?, Or What motivates the development of this solution, and what are the costs associated with LLM serving systems? You need to generate full question by writitng exactly the name of the techniques and not refer it as 'this, the proposed solutions, exisiting or current solution, etc...'"
            f"The questions must follow this - Q1: ....? etc, Contribution:.... : {section}"
        )
    elif theme == 'method':
        _custom_prompt = (
            f"Analyze the methodology section of the paper and summarize the key methodological approach "
            f"used by the authors. Highlight the data, techniques, models, or tools employed to address "
            f"the research question. Identify any specific hypotheses tested, experimental setups, or "
            f"computational methods, and explain how these align with the research objectives.YOU MUST ANSWER the main question 'HOW' . "
            f"The answer must follow this - Methodology:.....: {section}"
        )
    else: 
        _custom_prompt = (
            f"Examine this results section of the paper and summarize (Do not be long, just mention the main results) "
            f"the key findings reported by the authors. Highlight the outcomes of experiments, the performance "
            f"of any models or methodologies, or the validation of hypotheses. Focus on quantitative metrics, "
            f"qualitative observations, or comparative analyses provided. Explain how these results contribute "
            f"to addressing the research question and advancing the field from the paper. "
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
        return response_data['response']
    except requests.exceptions.HTTPError as err:
        print(f"HTTP error: {err}")
        return "Error in request or code."

def extract_markdown_sections(file_path, section_titles):
    """Extract specific sections from a markdown file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {str(e)}")
        return {}, ""
    
    # Separate "Abstract" from other titles
    abstract_pattern = r'##\s*Abstract'
    other_titles = [title for title in section_titles if title.lower() != 'abstract']
    
    # Create pattern for numbered sections
    numbered_pattern = r'##\s*(?:\d+\.?\s*)*({titles})'
    other_titles_pattern = '|'.join(map(re.escape, other_titles))
    
    # Combine patterns for both Abstract and numbered sections
    if 'Abstract' in section_titles:
        full_pattern = f'(?:{abstract_pattern}|{numbered_pattern.format(titles=other_titles_pattern)})(.*?)(?=##|\Z)'
    else:
        full_pattern = f'{numbered_pattern.format(titles=other_titles_pattern)}(.*?)(?=##|\Z)'
    
    # Find all matches with case-insensitive flag
    matches = re.finditer(full_pattern, content, re.DOTALL | re.IGNORECASE)
    
    # Store matches in a dictionary with section title as key
    extracted_sections = {}
    for match in matches:
        section_content = match.group(2).strip()
        header = match.group(0).split('\n')[0]
        clean_header = re.sub(r'^##\s*(?:\d+\.?\s*)*', '', header).strip()
        extracted_sections[clean_header] = section_content
    
    return extracted_sections, content

def process_markdown_files(input_folder, output_folder):
    """Process all markdown files in the input folder and generate analysis JSON files."""
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Define section categories
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
        "details", "evaluation tasks", "data construction", "inference","field architecture", "implementation study", "setup"
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
    
    # Get all markdown files in the input folder
    markdown_files = [f for f in os.listdir(input_folder) if f.endswith('.md')]
    iter_ = 0 
    for md_file in markdown_files:
        iter_ +=1
        print(f"Processing {md_file}... | {iter_}/{len(markdown_files)}")
        file_path = os.path.join(input_folder, md_file)
        
        complete = {}
        research_content = ""  # Store research sections for topic extraction
        
        # First process research sections to get topics
        sections, _ = extract_markdown_sections(file_path, research_question_sections)
        if sections:
            research_content = "\n\n".join(sections.values())
            # Extract topics from research content
            topics = get_topics(research_content)
            complete["topics"] = topics
        
        # Then process all themes
        for theme in themes:
            if theme == "research":
                # Reuse already extracted research sections
                tmp_contents = research_content
            elif theme == "method":
                sections, _ = extract_markdown_sections(file_path, method_questions)
                tmp_contents = "\n\n".join(sections.values()) if sections else ""
            elif theme == "results":
                sections, _ = extract_markdown_sections(file_path, results_question_sections)
                tmp_contents = "\n\n".join(sections.values()) if sections else ""

            if tmp_contents:  # Only process if sections were found
                res = get_llama_question(tmp_contents, theme)
                complete[theme] = res
            else:
                complete[theme] = "No relevant sections found"
        
        # Create output filename
        output_filename = os.path.splitext(md_file)[0] + '_analysis.json'
        output_path = os.path.join(output_folder, output_filename)
        
        # Save results to JSON file
        with open(output_path, 'w', encoding='utf-8') as outfile:
            json.dump(complete, outfile, indent=4)
        
        print(f"Saved analysis for {md_file} to {output_filename}")


#input_folder = "./converted_markdowns"
#output_folder = "./paper_analysis"
#
## Check Ollama setup before processing
#if not setup_ollama():
#    print("Failed to setup Ollama requirements. Please resolve the issues and try again.")
#    sys.exit(1)
    

# Generate card/s 
def get_tethy_summary(content):
    url = "http://127.0.0.1:11434/api/generate"
    prompt = (
        f"Summarize this paper content into a bulleted list of main results, Methods and contributions. Just give the answer without any polite texts before."
        f"Be short and concise no more than 700 characters."
        f"""This is a Template example you need to follow to generate the questions: 
        Q1: What are the primary challenges faced by researchers and developers in utilizing large language models for software development tasks?

        A: The major challenge lies in the performance gap between open-source models and closed-source models, with the former being inaccessible to many researchers and developers due to their proprietary nature.

        Q2: How do the authors address this challenge by developing the DeepSeek-Coder series of open-source code models?

        A: The authors introduce a range of open-source code models with sizes from 1.3B to 33B, trained from scratch on 2 trillion tokens sourced from 87 programming languages, ensuring a comprehensive understanding of coding languages and syntax.

        Q3: What specific enhancements and innovations does the DeepSeek-Coder series bring to the field of software development?

        A: The authors develop several innovative techniques, including the 'fill-in-the-blank' pre-training objective, the extension of the context window to 16K tokens, and the incorporation of the Fill-In-Middle (FIM) approach, which significantly bolster the models' code completion capabilities.

        Q4: What are the main contributions of the authors in this study?

        A: The authors make several key contributions, including:

        * Introducing DeepSeek-Coder-Base and DeepSeek-Coder-Instruct, advanced code-focused large language models.
        * Developing repository-level data construction during pre-training, which significantly boosts cross-file code generation capabilities.
        * Conducting extensive evaluations of the code LLMs against various benchmarks, demonstrating their superiority over existing open-source models.

        Contribution: The authors' work introduces a series of specialized Large Language Models (LLMs) for coding, including the DeepSeek-Coder series, which provides significant advancements in open-source code modeling.
        """
        f"Focus on key findings and avoid technical details and add the key words from the topics at the end. Content: {content}"
    )
    
    payload = {
        "model": "saish_15/tethysai_research",
        "prompt": prompt,
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload)
        return response.json()['response']
    except Exception as e:
        print(f"Error getting summary: {e}")
        return None

def generate_paper_cards():
    # Load paper titles
    with open('paper_metadata/metadata.json', 'r') as f:
        papers = json.load(f)
    
    # Create output directory
    Path('card_papers').mkdir(exist_ok=True)
    
    # Process each analysis file
    iter_ = 0
    analysis_files = Path('paper_analysis').glob('*_analysis.json')
    for analysis_path in analysis_files:
        paper_id = analysis_path.stem.replace('_analysis', '')

        with open(analysis_path, 'r') as f:
            analysis = json.load(f)
        
        # Get paper title
        #title = titles.get(paper_id, "Unknown Title")
        print(f"*************************papers: {papers}*********************")
        title = next((paper['title'] for paper in papers if paper['id'] == paper_id), "Unknown Title")
        
        # Combine content for summary
        content = f"{analysis['research']}\n{analysis['method']}\n{analysis['results']}"
        summary = get_tethy_summary(content)
        summary = summary.split(":")[-1]
        
        tmp_topics = ", ".join(analysis['topics'])
        # Generate markdown content
        md_content = f"""# {title}

# Research questions
{analysis['research']}

## Problem Statement, Methods and Main Results
{summary}

#### Keywords: {tmp_topics}\n

### [Link to paper](https://arxiv.org/abs/{paper_id})
        """
        
        # Save to markdown file
        output_path = f"card_papers/{paper_id}_card.md"
        with open(output_path, 'w') as f:
            f.write(md_content)
        iter_ +=1 
        print(f"Generated card for {paper_id}")
