#!/usr/bin/env python3
import nltk
import os
import sys

def setup_nltk():
    """Download all required NLTK resources and ensure they're in the right place"""
    print("Setting up NLTK resources...")
    
    # Create nltk_data directory in the current folder if it doesn't exist
    nltk_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nltk_data")
    os.makedirs(nltk_data_dir, exist_ok=True)
    
    # Set NLTK data path to use the local directory
    nltk.data.path.insert(0, nltk_data_dir)
    
    # Download required resources
    resources = [
        'punkt',
        'punkt_tab',
        'stopwords'
    ]
    
    for resource in resources:
        print(f"Downloading {resource}...")
        try:
            nltk.download(resource, download_dir=nltk_data_dir)
            print(f"Successfully downloaded {resource}")
        except Exception as e:
            print(f"Error downloading {resource}: {str(e)}")
    
    print("\nNLTK setup complete!")
    print(f"NLTK data directory: {nltk_data_dir}")
    print("NLTK data paths:", nltk.data.path)

if __name__ == "__main__":
    setup_nltk() 