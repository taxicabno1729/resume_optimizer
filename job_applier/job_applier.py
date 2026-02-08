"""Main Job Applier orchestrator.

Coordinates the full pipeline using free tools:
1. Scrape job boards with Playwright for job discovery
2. Use Claude to parse listings from raw HTML
3. Navigate to application pages with Playwright
4. Use Claude to analyze forms and fill them
5. Track results and generate reports
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from job_applier.applicant_profile import ApplicantProfile
from job_applier.browser_agent import ApplicationResult, BrowserAgent
from job_applier.config import Config
from job_applier.job_scraper import Company, JobListing, JobScraper

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    """How to discover jobs."""

    ALL_BOARDS = "all_boards"  # Scrape Indeed + LinkedIn + Google Jobs
    INDEED = "indeed"
    LINKEDIN = "linkedin"
    GOOGLE = "google"
    CAREERS_PAGE = "careers_page"  # Scrape a specific company careers URL
    URLS = "urls"  # Apply to specific URLs provided by the user


@dataclass
class ApplicationRun:
    """Tracks a single run of the job applier."""

    id: str = ""
    started_at: str = ""
    search_mode: str = ""
    query: str = ""
    jobs_found: list[JobListing] = field(default_factory=list)
    applications: list[ApplicationResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_applied(self) -> int:
        return sum(1 for a in self.applications if a.success)

    @property
    def total_failed(self) -> int:
        return sum(1 for a in self.applications if not a.success)

    def summary(self) -> dict:
        return {
            "search_mode": self.search_mode,
            "query": self.query,
            "jobs_found": len(self.jobs_found),
            "applications_submitted": self.total_applied,
            "applications_failed": self.total_failed,
            "errors": len(self.errors),
        }


class JobApplier:
    """Orchestrates the full job search and application pipeline."""

    def __init__(self, config: Config, profile: ApplicantProfile):
        self.config = config
        self.profile = profile
        self.scraper = JobScraper(config)
        self.browser_agent = BrowserAgent(config)
        self._current_run: Optional[ApplicationRun] = None
        self._on_status_update = None

    def set_status_callback(self, callback):
        """Set a callback function for status updates: callback(message: str)."""
        self._on_status_update = callback

    def _status(self, message: str):
        logger.info(message)
        if self._on_status_update:
            self._on_status_update(message)

    # ------------------------------------------------------------------
    # Search methods
    # ------------------------------------------------------------------

    async def search_all_boards(
        self, job_title: str, location: str = "Remote"
    ) -> list[JobListing]:
        """Search Indeed + LinkedIn + Google Jobs in parallel."""
        self._status(f"Searching all job boards: {job_title} in {location}")
        jobs = await self.scraper.search_all_boards(job_title, location)
        self._status(f"Found {len(jobs)} unique jobs across all boards")
        return jobs

    async def search_indeed(
        self, job_title: str, location: str = "Remote"
    ) -> list[JobListing]:
        """Search Indeed only."""
        self._status(f"Searching Indeed: {job_title} in {location}")
        jobs = await self.scraper.scrape_indeed(
            job_title, location, self.config.max_results_per_board
        )
        self._status(f"Indeed: found {len(jobs)} jobs")
        return jobs

    async def search_linkedin(
        self, job_title: str, location: str = "Remote"
    ) -> list[JobListing]:
        """Search LinkedIn only."""
        self._status(f"Searching LinkedIn: {job_title} in {location}")
        jobs = await self.scraper.scrape_linkedin(
            job_title, location, self.config.max_results_per_board
        )
        self._status(f"LinkedIn: found {len(jobs)} jobs")
        return jobs

    async def search_google(
        self, job_title: str, location: str = "Remote"
    ) -> list[JobListing]:
        """Search Google Jobs only."""
        self._status(f"Searching Google Jobs: {job_title} in {location}")
        jobs = await self.scraper.scrape_google_jobs(
            job_title, location, self.config.max_results_per_board
        )
        self._status(f"Google Jobs: found {len(jobs)} jobs")
        return jobs

    async def search_careers_page(
        self, careers_url: str, target_titles: Optional[list[str]] = None,
    ) -> list[JobListing]:
        """Scrape a specific company careers page."""
        titles = target_titles or self.profile.desired_titles or self.config.job_titles
        self._status(f"Scraping careers page: {careers_url}")
        jobs = await self.scraper.scrape_careers_page(careers_url, titles)
        self._status(f"Found {len(jobs)} jobs on careers page")
        return jobs

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Apply to a single job."""
        self._status(f"Applying to: {job.title} at {job.company or job.url}")
        form_data = self.profile.to_form_data(company=job.company, title=job.title)
        result = await self.browser_agent.apply_to_job(
            job=job,
            applicant_data=form_data,
            resume_path=self.profile.resume_path or None,
        )
        if result.success:
            self._status(f"Successfully applied to {job.title}!")
        else:
            self._status(f"Could not apply to {job.title}: {result.status}")
        return result

    # ------------------------------------------------------------------
    # Full pipeline methods
    # ------------------------------------------------------------------

    async def run_search(
        self,
        mode: SearchMode,
        job_title: str = "",
        location: str = "Remote",
        careers_url: str = "",
        urls: Optional[list[str]] = None,
    ) -> ApplicationRun:
        """Run a search and return the results (no auto-apply)."""
        run = ApplicationRun(
            id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now().isoformat(),
            search_mode=mode,
            query=f"{job_title} in {location}" if job_title else careers_url or "direct URLs",
        )
        self._current_run = run

        try:
            if mode == SearchMode.ALL_BOARDS:
                run.jobs_found = await self.search_all_boards(job_title, location)
            elif mode == SearchMode.INDEED:
                run.jobs_found = await self.search_indeed(job_title, location)
            elif mode == SearchMode.LINKEDIN:
                run.jobs_found = await self.search_linkedin(job_title, location)
            elif mode == SearchMode.GOOGLE:
                run.jobs_found = await self.search_google(job_title, location)
            elif mode == SearchMode.CAREERS_PAGE:
                run.jobs_found = await self.search_careers_page(careers_url)
            elif mode == SearchMode.URLS:
                run.jobs_found = [
                    JobListing(title=f"Job at {u}", url=u, source="user")
                    for u in (urls or [])
                ]
        except Exception as e:
            run.errors.append(str(e))
            self._status(f"Search error: {e}")

        self._status(f"Search complete: {len(run.jobs_found)} jobs found")
        return run

    async def run_apply(
        self, jobs: list[JobListing]
    ) -> list[ApplicationResult]:
        """Apply to a list of jobs."""
        results = []
        await self.browser_agent.start_session()
        try:
            for job in jobs:
                try:
                    result = await self.apply_to_job(job)
                    results.append(result)
                except Exception as e:
                    self._status(f"Error applying to {job.title}: {e}")
                    results.append(
                        ApplicationResult(
                            job=job, success=False, status="failed", message=str(e)
                        )
                    )
        finally:
            await self.browser_agent.end_session()
        return results

    async def cleanup(self):
        """Clean up all resources."""
        await self.browser_agent.end_session()
        await self.scraper.close()
