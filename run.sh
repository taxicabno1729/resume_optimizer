#!/bin/zsh

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is required but not installed. Please install Python 3 and try again."
    exit 1
fi

# Project directory (where this script is located)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# # Check if virtual environment exists, create if not
# if [ ! -d "venv" ]; then
#     echo "Creating virtual environment..."
#     python3 -m venv venv
# fi

# # Activate virtual environment
# source venv/bin/activate

# Install or update requirements
echo "Installing/updating requirements..."
pip install --upgrade pip
pip install -r requirements.txt

# Download NLTK resources using our dedicated script
echo "Setting up NLTK resources..."
python3 setup_nltk.py

# Export NLTK_DATA path to ensure resources are found
export NLTK_DATA="$SCRIPT_DIR/nltk_data"

# Run the application
echo "Starting Resume ATS Optimizer..."
streamlit run app.py

# Deactivate virtual environment on exit
deactivate 