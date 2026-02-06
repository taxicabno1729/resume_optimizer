"""Main Job Applier orchestrator.

Coordinates the full pipeline:
1. Search for companies/jobs using Exa
2. Discover job listings on careers pages using Browserbase
3. Apply to matching jobs automatically
4. Track results and generate reports
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
from job_applier.exa_search import Company, ExaJobSearch, JobListing

logger = logging.getLogger(__name__)


class SearchMode(str, Enum):
    """How to discover jobs."""

    COMPANIES = "companies"  # Search for companies, then find their jobs
    DIRECT = "direct"  # Search for job listings directly
    JOB_BOARDS = "job_boards"  # Search specific job boards
    URLS = "urls"  # Apply to specific URLs provided by the user


@dataclass
class ApplicationRun:
    """Tracks a single run of the job applier."""

    id: str = ""
    started_at: str = ""
    search_mode: str = ""
    query: str = ""
    companies_found: list[Company] = field(default_factory=list)
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
            "companies_found": len(self.companies_found),
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
        self.exa_search = ExaJobSearch(config)
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

    async def search_companies(self, query: str) -> list[Company]:
        """Step 1a: Discover companies matching a query."""
        self._status(f"Searching for companies: {query}")
        companies = self.exa_search.discover_and_enrich(
            company_query=query,
            job_titles=self.profile.desired_titles or self.config.job_titles,
        )
        self._status(f"Found {len(companies)} companies")
        return companies

    async def search_jobs_direct(self, query: str) -> list[JobListing]:
        """Step 1b: Search for job listings directly."""
        self._status(f"Searching for jobs: {query}")
        jobs = self.exa_search.search_jobs(query=query)
        self._status(f"Found {len(jobs)} job listings")
        return jobs

    async def search_job_boards(
        self, job_title: str, location: str = "Remote"
    ) -> list[JobListing]:
        """Step 1c: Search job boards for positions."""
        self._status(f"Searching job boards: {job_title} in {location}")
        jobs = self.exa_search.search_job_boards(
            job_title=job_title, location=location
        )
        self._status(f"Found {len(jobs)} job board listings")
        return jobs

    async def discover_jobs_at_company(self, company: Company) -> list[JobListing]:
        """Step 2: Use browser to find jobs on a company's careers page."""
        if not company.careers_url:
            self._status(f"No careers URL for {company.name}, skipping")
            return []

        self._status(f"Browsing careers page: {company.name}")
        try:
            jobs = await self.browser_agent.discover_jobs_on_page(
                careers_url=company.careers_url,
                target_titles=self.profile.desired_titles or self.config.job_titles,
            )
            for job in jobs:
                job.company = company.name
            self._status(f"Found {len(jobs)} matching jobs at {company.name}")
            return jobs
        except Exception as e:
            self._status(f"Error browsing {company.name}: {e}")
            return []

    async def apply_to_job(self, job: JobListing) -> ApplicationResult:
        """Step 3: Apply to a single job."""
        self._status(f"Applying to: {job.title} at {job.company or job.url}")
        form_data = self.profile.to_form_data(
            company=job.company, title=job.title
        )
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

    async def run_company_search(self, query: str, auto_apply: bool = False) -> ApplicationRun:
        """Full pipeline: search companies -> find jobs -> optionally apply."""
        run = ApplicationRun(
            id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now().isoformat(),
            search_mode=SearchMode.COMPANIES,
            query=query,
        )
        self._current_run = run

        # Step 1: Find companies
        run.companies_found = await self.search_companies(query)

        # Step 2: Browse each company's careers page
        for company in run.companies_found:
            try:
                jobs = await self.discover_jobs_at_company(company)
                run.jobs_found.extend(jobs)
            except Exception as e:
                run.errors.append(f"Error at {company.name}: {e}")

        # Step 3: Apply if requested
        if auto_apply and run.jobs_found:
            await self.browser_agent.start_session()
            try:
                for job in run.jobs_found:
                    try:
                        result = await self.apply_to_job(job)
                        run.applications.append(result)
                    except Exception as e:
                        run.errors.append(f"Error applying to {job.title}: {e}")
            finally:
                await self.browser_agent.end_session()

        self._status(f"Run complete: {run.summary()}")
        return run

    async def run_direct_search(self, query: str, auto_apply: bool = False) -> ApplicationRun:
        """Full pipeline: search jobs directly -> optionally apply."""
        run = ApplicationRun(
            id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now().isoformat(),
            search_mode=SearchMode.DIRECT,
            query=query,
        )
        self._current_run = run

        run.jobs_found = await self.search_jobs_direct(query)

        if auto_apply and run.jobs_found:
            await self.browser_agent.start_session()
            try:
                for job in run.jobs_found:
                    try:
                        result = await self.apply_to_job(job)
                        run.applications.append(result)
                    except Exception as e:
                        run.errors.append(f"Error applying to {job.title}: {e}")
            finally:
                await self.browser_agent.end_session()

        self._status(f"Run complete: {run.summary()}")
        return run

    async def run_job_board_search(
        self,
        job_title: str,
        location: str = "Remote",
        auto_apply: bool = False,
    ) -> ApplicationRun:
        """Full pipeline: search job boards -> optionally apply."""
        run = ApplicationRun(
            id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now().isoformat(),
            search_mode=SearchMode.JOB_BOARDS,
            query=f"{job_title} in {location}",
        )
        self._current_run = run

        run.jobs_found = await self.search_job_boards(job_title, location)

        if auto_apply and run.jobs_found:
            await self.browser_agent.start_session()
            try:
                for job in run.jobs_found:
                    try:
                        result = await self.apply_to_job(job)
                        run.applications.append(result)
                    except Exception as e:
                        run.errors.append(f"Error applying to {job.title}: {e}")
            finally:
                await self.browser_agent.end_session()

        self._status(f"Run complete: {run.summary()}")
        return run

    async def apply_to_urls(self, urls: list[str]) -> ApplicationRun:
        """Apply to specific job URLs provided by the user."""
        run = ApplicationRun(
            id=datetime.now().strftime("%Y%m%d_%H%M%S"),
            started_at=datetime.now().isoformat(),
            search_mode=SearchMode.URLS,
            query=f"{len(urls)} direct URLs",
        )
        self._current_run = run

        run.jobs_found = [
            JobListing(title=f"Job at {url}", url=url, source="user")
            for url in urls
        ]

        await self.browser_agent.start_session()
        try:
            for job in run.jobs_found:
                try:
                    result = await self.apply_to_job(job)
                    run.applications.append(result)
                except Exception as e:
                    run.errors.append(f"Error applying to {job.url}: {e}")
        finally:
            await self.browser_agent.end_session()

        self._status(f"Run complete: {run.summary()}")
        return run

    async def cleanup(self):
        """Clean up resources."""
        await self.browser_agent.end_session()
