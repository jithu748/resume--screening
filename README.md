# Resume Screening System

**Live Demo:** [https://resume-screening-14.onrender.com](https://resume-screening-14.onrender.com)

An automated resume-screening application that extracts text from PDF and DOCX resumes, compares candidates against job requirements using TF-IDF and cosine similarity, and ranks resumes using similarity scores and skill matching.

The project includes a web interface, bulk resume uploads, ZIP import, a Python command-line interface, and CSV/Excel export options.

> **Demo note:** The live application is hosted on Render's free instance, which may take around 50 seconds or longer to respond after inactivity. Use synthetic or non-sensitive sample resumes when testing a public demo. Do not upload confidential candidate information unless the deployment's privacy and data-retention practices have been verified.

---

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Run Locally](#run-locally)
- [Run the Web Application](#run-the-web-application)
- [Command-Line Usage](#command-line-usage)
- [Exports and Bulk Processing](#exports-and-bulk-processing)
- [Scoring Method](#scoring-method)
- [Security and Deployment](#security-and-deployment)
- [Limitations](#limitations)
- [Troubleshooting](#troubleshooting)
- [Future Improvements](#future-improvements)
- [Interview Explanation](#interview-explanation)

---

## Features

- **Resume text extraction:** Extract text from PDF and DOCX files.
- **Job requirement matching:** Compare resume content with job titles, descriptions, and required skills.
- **Automated ranking:** Rank resumes according to calculated matching scores.
- **Bulk uploads:** Upload multiple supported resumes.
- **ZIP import:** Upload an archive containing multiple resumes.
- **Web interface:** Interact with the screening workflow through a browser.
- **Command-line interface:** Run screening jobs from a terminal or automation script.
- **CSV export:** Export screening results for further analysis.
- **Excel export:** Generate XLSX reports when the optional Excel dependency is installed.
- **Shortlist management:** Copy selected top-ranked resumes into an output directory.
- **ZIP output:** Package shortlisted resumes for convenient transfer.
- **Modular design:** Keep extraction, preprocessing, vectorization, scoring, and output handling separate.

## Technology Stack

| Component | Technologies |
|---|---|
| Programming language | Python |
| Web framework | FastAPI |
| Frontend | HTML, CSS, JavaScript |
| Text extraction | pdfminer.six, python-docx |
| Text preprocessing | NLTK |
| Text vectorization | TF-IDF, scikit-learn |
| Similarity calculation | Cosine similarity |
| Data export | CSV, optional XLSX |
| Database and authentication | PostgreSQL and authentication components in the security-enabled branch |
| Hosting | Render |

The exact dependencies are defined in the project's requirements files.

---

## How It Works

The application follows a resume-screening pipeline:

1. **Input job requirements:** Enter a job title and relevant skills or requirements.
2. **Upload resumes:** Select individual PDF/DOCX files, multiple files, or a ZIP archive.
3. **Extract text:** Read text from supported documents.
4. **Preprocess text:** Normalize text, remove unwanted characters, and tokenize where applicable.
5. **Vectorize text:** Convert the job requirements and resume content into TF-IDF vectors.
6. **Calculate similarity:** Calculate cosine similarity between the job vector and each resume vector.
7. **Apply skill matching:** Evaluate required skills and combine skill matching with the similarity score according to the scoring implementation.
8. **Rank candidates:** Sort candidates by their calculated scores.
9. **Export results:** Download or generate supported reports and shortlist outputs.

The system is designed to assist recruiters with initial screening. Its scores should not be treated as definitive judgments about a candidate's qualifications.

---

## Project Structure

The repository contains the following major components. Exact paths may vary by branch.

```text
resume_screening/
├── main.py
├── data/
│   ├── requirements.txt
│   ├── src/
│   │   ├── main.py
│   │   ├── webapp.py
│   │   ├── extract_text.py
│   │   ├── preprocess.py
│   │   ├── vectorizer.py
│   │   ├── similarity.py
│   │   └── scorer.py
│   ├── web/
│   │   ├── static/
│   │   └── templates/
│   └── resume_uploads/
├── tests/
├── AUTHENTICATION.md
├── .env.example
├── .gitignore
└── README.md
```

### Main Components

- `main.py`: Project-level command-line launcher.
- `data/src/main.py`: Processes CLI arguments, loads resumes, runs screening, and handles outputs.
- `data/src/webapp.py`: FastAPI web application and API endpoints.
- `data/src/extract_text.py`: Extracts text from PDF and DOCX documents.
- `data/src/preprocess.py`: Cleans and normalizes text.
- `data/src/vectorizer.py`: Creates TF-IDF vectors.
- `data/src/similarity.py`: Calculates cosine similarity.
- `data/src/scorer.py`: Applies similarity and skill-matching logic.
- `data/web/`: Contains the web frontend.
- `tests/`: Contains automated tests.
- `AUTHENTICATION.md`: Documents authentication and development configuration.

---

## Run Locally

### Prerequisites

Install the following:

- Python 3.10 or a compatible version supported by the project's dependencies.
- Git.
- A terminal such as PowerShell, Command Prompt, or Bash.

### 1. Clone the repository

```bash
git clone https://github.com/jithu748/resume--screening.git
cd resume--screening
```

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux/macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

From the project root, install the dependencies specified by the repository:

```bash
python -m pip install --upgrade pip
python -m pip install -r data/requirements.txt
```

If Excel output is optional and not already included in the installed dependencies:

```bash
python -m pip install openpyxl
```

Install any additional web or database dependencies required by the selected application configuration and documented in the repository.

### 4. Download NLTK resources

If the preprocessing pipeline requires these NLTK resources, download them once:

```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('omw-1.4')"
```

### 5. Start the command-line application

```bash
python main.py
```

For the web interface, follow the next section.

---

## Run the Web Application

From the project root, activate your virtual environment and install the web dependencies if necessary:

```bash
python -m pip install fastapi uvicorn python-multipart
```

Start the FastAPI application:

```bash
python -m uvicorn data.src.webapp:app --reload
```

Open the local application:

[http://127.0.0.1:8000/](http://127.0.0.1:8000/)

The `--reload` option is intended for local development.

### Using the web interface

1. Open the application.
2. Enter the job title and required skills.
3. Select PDF/DOCX resumes or upload a supported ZIP archive.
4. Run the screening operation.
5. Review the ranking and matching scores.
6. Export the results if the relevant export option is available.

### Authentication and configuration

The security-enabled application supports production authentication and PostgreSQL configuration. Follow [`AUTHENTICATION.md`](AUTHENTICATION.md) and `.env.example` for the required settings.

Do not copy local development settings into a public production service. Production authentication, database configuration, explicit trusted CORS origins, and secure upload handling must remain enabled as required by the application.

---

## Command-Line Usage

Run the interactive CLI:

```bash
python main.py
```

Run a non-interactive screening job:

```bash
python main.py --job-title "Web Developer" --skills "python,html,css" --top 5
```

Print the top five candidates for a web-development role.

### Export results

Export CSV results:

```bash
python main.py --job-title "Data Scientist" --skills "python,pandas" --output-csv out/results.csv
```

Export full extracted text with the results:

```bash
python main.py --job-title "Data Scientist" --skills "python,pandas" --include-text --output-csv out/results_with_text.csv
```

Be careful when exporting full resume text because it may contain personal information.

### Shortlist and ZIP output

Copy the top three candidates into a shortlist directory and package the directory:

```bash
python main.py --job-title "Web Developer" --skills "python,html" --top 3 --copy-top-dir out/shortlisted --zip
```

The exact supported options depend on the CLI implementation in the selected branch. Run `python main.py --help` to inspect available arguments.

---

## Exports and Bulk Processing

Depending on the configured workflow, the application supports:

| Option | Purpose |
|---|---|
| `--output-csv PATH` | Write screening results to CSV |
| `--output-xlsx PATH` | Write screening results to Excel |
| `--include-text` | Include extracted resume text in exports |
| `--copy-top-dir PATH` | Copy the top-ranked resumes into a directory |
| `--zip` | Create an archive of the shortlisted files |
| `--output-dir DIR` | Set a base output directory where supported |

For bulk screening, use the ZIP upload feature or provide multiple supported files through the web interface.

Only upload files you are authorized to process. Check archive contents and avoid placing sensitive candidate information in publicly accessible output directories.

---

## Scoring Method

The documented baseline uses TF-IDF and cosine similarity, combined with explicit skill matching.

### TF-IDF

Term Frequency–Inverse Document Frequency represents how important a word is to a document relative to the document collection. It provides a lightweight way to represent job requirements and resume text numerically.

### Cosine Similarity

Cosine similarity compares the direction of two vectors and produces a similarity measure. In this project, it is used to compare the job-requirement vector with each resume vector.

### Skill Matching

The scoring component checks for required skills using the matching rules implemented in `data/src/scorer.py`. The final score combines similarity and skill-related signals according to that implementation.

### Important limitations of scoring

- Keyword matches do not guarantee actual proficiency.
- Different wording can cause relevant experience to be missed.
- Resume formatting and extraction quality can affect scores.
- TF-IDF is not a full semantic understanding system.
- A high score is not proof that a candidate is the best person for a job.

Use ranking as a decision-support tool. Human review should remain part of the recruitment process.

---

## Security and Deployment

The application has a security-enabled development branch with authentication, PostgreSQL integration, upload validation, and related tests.

**Live demo:** [https://resume-screening-14.onrender.com](https://resume-screening-14.onrender.com)

### Deployment notes

- The live demo is hosted on Render.
- Free instances may spin down after inactivity and take time to respond.
- The current live deployment may not contain every change from the latest feature branch.
- Production configuration must be verified before enabling new authentication or database migrations.
- A PostgreSQL backup should be verified before applying a production schema migration.
- Keep credentials in private environment configuration, never in source code or README files.
- Do not enable local demo mode in production.
- Keep upload validation, authentication, CSRF protections, origin validation, and session isolation intact.

For the security-enabled configuration, see [`AUTHENTICATION.md`](AUTHENTICATION.md).

---

## Limitations

- **Text extraction:** Scanned or image-only PDFs may require OCR before processing.
- **Formatting:** Multi-column resumes, unusual layouts, tables, and complex designs may reduce extraction quality.
- **Semantic matching:** TF-IDF can miss meaning when a resume describes skills differently from the job description.
- **Scale:** Large batches can increase processing time and memory usage.
- **Scoring:** Simple skill checks may not capture context, depth, or recency of experience.
- **Production readiness:** Database connectivity, migrations, environment configuration, storage persistence, and backup/restore behavior must be verified for the target deployment.

---

## Troubleshooting

### `ModuleNotFoundError`

Activate the correct virtual environment and install the project dependencies:

```bash
python -m pip install -r data/requirements.txt
```

### The web server does not start

Check that the virtual environment is activated and the required packages are installed. Run the Uvicorn command from the project root.

### PDF extraction fails

The PDF may be corrupted, encrypted, or image-only. Verify the file and use OCR if it contains scanned pages without extractable text.

### Results are empty or scores are unexpectedly low

- Confirm that the uploaded files are supported PDF/DOCX documents.
- Verify that text extraction returns non-empty content.
- Check that job requirements and skills are entered correctly.
- Review the preprocessing and scoring implementation.

### Excel export fails

Install the optional dependency if it is not already present:

```bash
python -m pip install openpyxl
```

### Render responds slowly

A free instance may have spun down after inactivity. Allow time for it to start before concluding that the application is unavailable.

### Authentication or database errors

Check the private environment configuration, PostgreSQL connectivity, database permissions, migration status, and application logs. Do not expose passwords, session tokens, or database URLs when reporting errors.

---

## Future Improvements

Possible improvements include:

1. Semantic embeddings for more context-aware matching.
2. Persistent vector storage for faster repeated screening.
3. Parallel text extraction for large batches.
4. Improved OCR support for scanned documents.
5. More detailed explanations of why a resume matched a role.
6. Improved monitoring, logging, and production observability.
7. More extensive PostgreSQL integration and deployment tests.
8. Additional report visualizations and analytics.

These are potential future enhancements, not claims that all are currently implemented.

---

## Interview Explanation

### Short explanation

"I built a resume-screening application that extracts text from PDF and Word resumes, preprocesses the content, represents it using TF-IDF, and ranks resumes by cosine similarity combined with explicit skill matching. The project includes a web interface, bulk uploads, command-line execution, and report-export options."

### Why TF-IDF?

"TF-IDF is a lightweight and interpretable baseline for converting text into numerical features. It is relatively inexpensive to compute and works well for initial keyword-oriented matching. However, it has limitations when relevant skills are described using different wording."

### Why cosine similarity?

"Cosine similarity provides a way to compare the job-requirement vector with resume vectors. It helps rank resumes according to how closely their text representations match the job requirements."

### How could it scale?

"I would consider persisting computed vectors, parallelizing text extraction, introducing semantic embeddings, and using a suitable vector index for larger collections. I would also strengthen monitoring, privacy controls, and production testing."

### One-minute project pitch

"I developed a resume-screening system that automates the initial stage of candidate matching. It accepts PDF and DOCX resumes, extracts and preprocesses their text, converts the text into TF-IDF vectors, and calculates cosine similarity against job requirements. The scoring component combines similarity with explicit skill matching to produce a ranked list of candidates. The application supports a browser-based workflow, bulk uploads, a command-line interface, and result exports. The system is intended to assist human recruiters rather than replace their judgment."

---

## License

Add a `LICENSE` file before distributing the source code commercially. Confirm that the project's dependencies and any included assets permit your intended distribution and licensing model.

---

## Live Application

Try the deployed application here:

**[Open Resume Screening Live Demo](https://resume-screening-14.onrender.com)**

