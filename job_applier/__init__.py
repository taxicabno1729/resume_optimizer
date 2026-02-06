"""
Job Applier - Automated job discovery and application tool.

Uses Exa for intelligent job/company search and Browserbase + Stagehand
for browser-based application automation.
"""

from job_applier.config import Config
from job_applier.exa_search import ExaJobSearch
from job_applier.browser_agent import BrowserAgent
from job_applier.applicant_profile import ApplicantProfile
from job_applier.job_applier import JobApplier

__all__ = [
    "Config",
    "ExaJobSearch",
    "BrowserAgent",
    "ApplicantProfile",
    "JobApplier",
]
