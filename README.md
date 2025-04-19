# Resume ATS Optimizer

A Streamlit web application that helps job seekers optimize their resumes for Applicant Tracking Systems (ATS) by analyzing them against job descriptions.

## Features

- Upload your resume (PDF format)
- Paste a job description
- Get a match score between your resume and the job description
- See matching and missing keywords
- Receive ATS optimization suggestions
- Get downloadable guidelines for creating an ATS-optimized resume
- Demo mode with sample resume and job description

## Quick Start

### On macOS/Linux (zsh/bash)

The easiest way to run the application on macOS or Linux is using the provided shell script:

```bash
# Make the script executable (if not already)
chmod +x run.sh

# Run the script
./run.sh
```

### Using Python Directly

Alternatively, you can run the application using the Python script:

```bash
python run.py
```

This script will:
1. Create a virtual environment (if it doesn't exist)
2. Install all required dependencies
3. Start the Streamlit application

## Manual Setup

If you prefer to set up the application manually:

1. Clone this repository
```bash
git clone https://github.com/yourusername/resume-optimizer.git
cd resume-optimizer
```

2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the required packages
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

4. Run the application
```bash
streamlit run app.py
```

5. Open your browser and navigate to http://localhost:8501

## Usage

1. Upload your resume in PDF format or use the demo mode
2. Paste the complete job description for the position you're applying for
3. Click "Analyze and Optimize"
4. Review the analysis results and recommendations
5. Download the ATS-optimized resume guidelines

### Demo Mode

If you don't have a resume handy or just want to test the application, you can enable demo mode by checking the "Use sample data for demo" checkbox. This will use the included sample resume and job description.

## How It Works

The application uses natural language processing (NLP) techniques to:
- Extract text from your resume
- Compare it with the job description using cosine similarity
- Identify matching and missing keywords
- Provide tailored suggestions for improving your resume's ATS compatibility

## Requirements

- Python 3.8 or higher (Python 3.10-3.11 recommended for best compatibility)
- See requirements.txt for all dependencies

## Troubleshooting

If you encounter issues with package installation:

1. Try using a Python version between 3.8 and 3.11 for best compatibility
2. If using Python 3.13, some packages may not be fully compatible yet
3. On macOS, you might need to install additional dependencies with homebrew:
   ```bash
   brew install python@3.10
   ``` 