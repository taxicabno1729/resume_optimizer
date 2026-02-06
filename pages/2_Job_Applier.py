"""Streamlit multipage entry point for the Job Applier.

This file re-exports the job_applier_app so Streamlit picks it up
as a page in the sidebar navigation.
"""

import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from job_applier_app import main

main()
