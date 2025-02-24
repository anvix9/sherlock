# Sherlock-lit
> Sherlock is processing research papers.

Sherlock-lit is a Python package (part of the tools used in haut platform) designed to process NLP research papers (Later, on more general papers) and generate precise descriptions of the papers in markdown (MD) card format. It streamlines understanding and documentation of research papers, making it an invaluable tool for researchers, students, and developers in NLP field to discover easily the contributions and research questions researchers tackle without being lost in papers or being doubtful after reading the abstract.

---

## Features

- **Markdown Card Generation**: Automatically generates concise and precise descriptions of NLP papers in markdown format.
- **Efficient Processing**: Really fast on CPUs and also can be further improved with GPU.
- **Small Size**: less than **70 MB**.
- **First-Time Setup**: The first run may be slower due to setup, but subsequent runs are significantly faster.
- **Simple Command-Line Interface**: Process papers by simply providing the path to a PDF file or a folder containing PDFs files.

---

## Installation

Sherlock is currently available for installation directly from GitHub. To install, run:

```bash
pip install sherlock-lit 
```

---

## Usage

Once installed, you can process a research paper by running:

```bash
sherlock_lit file_path.pdf
```

Replace `file_path.pdf` with the path to the research paper you want to process. The markdown card will be generated and saved in the output directory. 

---

## Example Workflow

1. Install sherlock-lit from PypI.
2. Run `sherlock_lit` on a PDF file:

   ```bash
   sherlock_lit example_paper.pdf
   ```

3. Retrieve the generated markdown card from the output directory (card-papers folder located in the current directory).

---

## Contributions

Contributions are welcome! I will be writing the contribution guidelines very soon.

---

## Future Plans

- Optimize processing speed further.
- Improve parsing of papers.
- Add support for more advanced GPU and multi-threaded processing.
- Expand compatibility for additional research paper formats.

---

## License

Sherlock-lit is licensed under the [MIT License](LICENSE).

---
