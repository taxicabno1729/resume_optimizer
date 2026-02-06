"""
Job Applier - Automated job discovery and application tool.

Free stack:
- Playwright (local) for browser automation and job board scraping
- Anthropic Claude API for AI-powered page understanding and form filling
"""

from job_applier.config import Config
from job_applier.job_scraper import JobScraper
from job_applier.browser_agent import BrowserAgent
from job_applier.applicant_profile import ApplicantProfile
from job_applier.job_applier import JobApplier

__all__ = [
    "Config",
    "JobScraper",
    "BrowserAgent",
    "ApplicantProfile",
    "JobApplier",
]
