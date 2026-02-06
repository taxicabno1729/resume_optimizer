"""Browser automation agent using Browserbase + Stagehand.

Handles the browser-level automation:
- Navigating to careers pages
- Discovering job listings on a page
- Filling out application forms
- Uploading resumes
- Submitting applications
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from stagehand import AsyncStagehand

from job_applier.config import Config
from job_applier.exa_search import JobListing

logger = logging.getLogger(__name__)


@dataclass
class ApplicationResult:
    """Result of attempting to apply to a job."""

    job: JobListing
    success: bool
    status: str  # "submitted", "failed", "requires_manual", "no_form_found"
    message: str = ""
    screenshot_path: str = ""
    fields_filled: list[str] = field(default_factory=list)


class BrowserAgent:
    """Automates job applications using Browserbase cloud browsers + Stagehand AI."""

    def __init__(self, config: Config):
        self.config = config
        self._client: Optional[AsyncStagehand] = None
        self._session = None

    async def _get_client(self) -> AsyncStagehand:
        """Get or create the Stagehand client."""
        if self._client is None:
            self._client = AsyncStagehand(
                browserbase_api_key=self.config.browserbase_api_key,
                browserbase_project_id=self.config.browserbase_project_id,
                model_api_key=self.config.model_api_key,
            )
        return self._client

    async def start_session(self) -> None:
        """Start a new browser session."""
        client = await self._get_client()
        self._session = await client.sessions.start(
            model_name=self.config.model_name,
        )
        logger.info(f"Browser session started: {self._session}")

    async def end_session(self) -> None:
        """End the current browser session."""
        if self._session:
            try:
                await self._session.end()
            except Exception as e:
                logger.warning(f"Error ending session: {e}")
            self._session = None

    async def discover_jobs_on_page(
        self,
        careers_url: str,
        target_titles: list[str],
    ) -> list[JobListing]:
        """Navigate to a careers page and extract matching job listings."""
        if not self._session:
            await self.start_session()

        logger.info(f"Discovering jobs at: {careers_url}")
        await self._session.navigate(url=careers_url)

        # Use Stagehand to extract job listings from the page
        titles_str = ", ".join(target_titles)
        extract_result = await self._session.extract(
            instruction=(
                f"Extract all job listings from this page. "
                f"Focus on positions related to: {titles_str}. "
                f"For each job, extract the title, URL/link, and location if available."
            ),
            schema={
                "type": "object",
                "properties": {
                    "jobs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "location": {"type": "string"},
                            },
                            "required": ["title"],
                        },
                    }
                },
                "required": ["jobs"],
            },
        )

        jobs = []
        if extract_result and extract_result.data:
            raw = extract_result.data
            # Handle both dict and object-style access
            job_list = raw.get("jobs", []) if isinstance(raw, dict) else getattr(raw, "jobs", [])
            for job_data in job_list:
                if isinstance(job_data, dict):
                    title = job_data.get("title", "")
                    url = job_data.get("url", careers_url)
                    location = job_data.get("location", "")
                else:
                    title = getattr(job_data, "title", "")
                    url = getattr(job_data, "url", careers_url)
                    location = getattr(job_data, "location", "")

                jobs.append(
                    JobListing(
                        title=title,
                        url=url,
                        location=location,
                        source="browser",
                    )
                )

        logger.info(f"Found {len(jobs)} jobs on {careers_url}")
        return jobs

    async def apply_to_job(
        self,
        job: JobListing,
        applicant_data: dict,
        resume_path: Optional[str] = None,
    ) -> ApplicationResult:
        """Navigate to a job listing and attempt to fill out the application.

        Args:
            job: The job listing to apply to.
            applicant_data: Dict with keys like name, email, phone,
                           linkedin, cover_letter, etc.
            resume_path: Local path to resume PDF to upload.
        """
        if not self._session:
            await self.start_session()

        logger.info(f"Applying to: {job.title} at {job.url}")

        try:
            await self._session.navigate(url=job.url)

            # Step 1: Look for and click an "Apply" button
            apply_action = await self._session.observe(
                instruction=(
                    "Find the 'Apply', 'Apply Now', 'Submit Application', "
                    "or similar button/link to start the job application."
                )
            )

            if apply_action and apply_action.data and apply_action.data.result:
                await self._session.act(input=apply_action.data.result[0])
                logger.info("Clicked apply button")
            else:
                logger.info("No explicit apply button found, looking for form directly")

            # Step 2: Fill in the application form fields
            fields_filled = []

            # Fill name
            if applicant_data.get("first_name"):
                await self._try_fill_field(
                    "first name field",
                    applicant_data["first_name"],
                    fields_filled,
                )
            if applicant_data.get("last_name"):
                await self._try_fill_field(
                    "last name field",
                    applicant_data["last_name"],
                    fields_filled,
                )
            if applicant_data.get("full_name") and not applicant_data.get("first_name"):
                await self._try_fill_field(
                    "name or full name field",
                    applicant_data["full_name"],
                    fields_filled,
                )

            # Fill email
            if applicant_data.get("email"):
                await self._try_fill_field(
                    "email address field",
                    applicant_data["email"],
                    fields_filled,
                )

            # Fill phone
            if applicant_data.get("phone"):
                await self._try_fill_field(
                    "phone number field",
                    applicant_data["phone"],
                    fields_filled,
                )

            # Fill LinkedIn
            if applicant_data.get("linkedin"):
                await self._try_fill_field(
                    "LinkedIn URL or profile field",
                    applicant_data["linkedin"],
                    fields_filled,
                )

            # Fill portfolio/website
            if applicant_data.get("website"):
                await self._try_fill_field(
                    "website, portfolio, or personal URL field",
                    applicant_data["website"],
                    fields_filled,
                )

            # Fill cover letter
            if applicant_data.get("cover_letter"):
                await self._try_fill_field(
                    "cover letter or additional information text area",
                    applicant_data["cover_letter"],
                    fields_filled,
                )

            # Step 3: Upload resume if path provided
            if resume_path:
                await self._try_upload_resume(resume_path, fields_filled)

            # Step 4: Handle any remaining required fields using autonomous mode
            await self._handle_remaining_fields(applicant_data, fields_filled)

            # Step 5: Submit the application
            submit_result = await self._try_submit(fields_filled)

            if submit_result:
                return ApplicationResult(
                    job=job,
                    success=True,
                    status="submitted",
                    message=f"Application submitted. Fields filled: {', '.join(fields_filled)}",
                    fields_filled=fields_filled,
                )
            else:
                return ApplicationResult(
                    job=job,
                    success=False,
                    status="requires_manual",
                    message=(
                        f"Form partially filled but could not submit. "
                        f"Fields filled: {', '.join(fields_filled)}"
                    ),
                    fields_filled=fields_filled,
                )

        except Exception as e:
            logger.error(f"Error applying to {job.title}: {e}")
            return ApplicationResult(
                job=job,
                success=False,
                status="failed",
                message=str(e),
            )

    async def _try_fill_field(
        self,
        field_description: str,
        value: str,
        fields_filled: list[str],
    ) -> bool:
        """Attempt to find and fill a form field."""
        try:
            observe_result = await self._session.observe(
                instruction=f"Find the {field_description} in the application form"
            )
            if observe_result and observe_result.data and observe_result.data.result:
                action = observe_result.data.result[0]
                # Modify action to include the value to type
                if isinstance(action, dict):
                    action["args"] = [value]
                await self._session.act(input=action)
                fields_filled.append(field_description)
                logger.info(f"Filled: {field_description}")
                return True
        except Exception as e:
            logger.debug(f"Could not fill {field_description}: {e}")
        return False

    async def _try_upload_resume(
        self,
        resume_path: str,
        fields_filled: list[str],
    ) -> bool:
        """Attempt to upload a resume file."""
        try:
            observe_result = await self._session.observe(
                instruction=(
                    "Find the file upload input for resume, CV, or document upload"
                )
            )
            if observe_result and observe_result.data and observe_result.data.result:
                action = observe_result.data.result[0]
                if isinstance(action, dict):
                    action["args"] = [resume_path]
                await self._session.act(input=action)
                fields_filled.append("resume_upload")
                logger.info("Uploaded resume")
                return True
        except Exception as e:
            logger.debug(f"Could not upload resume: {e}")
        return False

    async def _handle_remaining_fields(
        self,
        applicant_data: dict,
        fields_filled: list[str],
    ) -> None:
        """Use Stagehand's execute to handle any remaining required fields."""
        try:
            extra_info = json.dumps(
                {k: v for k, v in applicant_data.items() if k not in ("cover_letter",)},
                indent=2,
            )
            await self._session.execute(
                execute_options={
                    "instruction": (
                        f"Look at the application form on this page. "
                        f"Fill in any remaining REQUIRED fields that are empty "
                        f"using this applicant information: {extra_info}. "
                        f"Already filled: {', '.join(fields_filled)}. "
                        f"Do NOT submit the form yet."
                    ),
                    "max_steps": 5,
                },
                agent_config={"model": self.config.model_name},
            )
            fields_filled.append("remaining_required_fields")
        except Exception as e:
            logger.debug(f"Could not handle remaining fields: {e}")

    async def _try_submit(self, fields_filled: list[str]) -> bool:
        """Attempt to submit the application form."""
        try:
            observe_result = await self._session.observe(
                instruction=(
                    "Find the submit button for this application. "
                    "Look for 'Submit', 'Submit Application', 'Apply', 'Send', or similar."
                )
            )
            if observe_result and observe_result.data and observe_result.data.result:
                await self._session.act(input=observe_result.data.result[0])
                fields_filled.append("form_submitted")
                logger.info("Application submitted!")
                return True
        except Exception as e:
            logger.debug(f"Could not submit form: {e}")
        return False


def run_async(coro):
    """Helper to run async code from sync context."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            return loop.run_in_executor(pool, asyncio.run, coro)
    except RuntimeError:
        return asyncio.run(coro)
