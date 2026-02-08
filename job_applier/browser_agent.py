"""Browser automation agent using local Playwright + Claude.

Replaces Browserbase + Stagehand with a free stack:
- Playwright runs a local browser (Chromium/Firefox/WebKit)
- Claude analyzes page HTML to understand forms and generate actions
- Playwright executes the actions (click, fill, upload, submit)
"""

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from job_applier.config import Config
from job_applier.job_scraper import JobListing

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
    """Automates job applications using local Playwright + Claude for AI understanding."""

    def __init__(self, config: Config):
        self.config = config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._claude = None

    def _get_claude(self):
        """Lazy-init the Anthropic client."""
        if self._claude is None:
            import anthropic
            self._claude = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        return self._claude

    async def start_session(self) -> None:
        """Start a new local browser session."""
        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self.config.browser_type)
        self._browser = await launcher.launch(
            headless=self.config.headless,
            slow_mo=self.config.slow_mo,
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        logger.info("Local browser session started")

    async def end_session(self) -> None:
        """Close the browser session."""
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def apply_to_job(
        self,
        job: JobListing,
        applicant_data: dict,
        resume_path: Optional[str] = None,
    ) -> ApplicationResult:
        """Navigate to a job and attempt to fill out the application form."""
        if not self._page:
            await self.start_session()

        page = self._page
        logger.info(f"Applying to: {job.title} at {job.url}")

        try:
            await page.goto(
                job.url,
                timeout=self.config.application_timeout_seconds * 1000,
                wait_until="domcontentloaded",
            )
            await page.wait_for_timeout(2000)

            # Step 1: Find and click the Apply button
            clicked_apply = await self._find_and_click_apply(page)
            if clicked_apply:
                await page.wait_for_timeout(2000)

            # Step 2: Analyze the form with Claude and get fill instructions
            form_analysis = await self._analyze_form_with_claude(page, applicant_data)

            if not form_analysis:
                return ApplicationResult(
                    job=job,
                    success=False,
                    status="no_form_found",
                    message="Could not find an application form on this page",
                )

            # Step 3: Execute the fill instructions
            fields_filled = await self._execute_form_fill(
                page, form_analysis, applicant_data, resume_path
            )

            # Step 4: Submit the form
            submitted = await self._find_and_click_submit(page)

            if submitted:
                await page.wait_for_timeout(3000)
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
                    message=f"Form filled but could not find submit button. Fields: {', '.join(fields_filled)}",
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

    async def _find_and_click_apply(self, page: Page) -> bool:
        """Try to find and click an Apply/Apply Now button."""
        apply_selectors = [
            'a:has-text("Apply Now")',
            'button:has-text("Apply Now")',
            'a:has-text("Apply")',
            'button:has-text("Apply")',
            'a:has-text("Submit Application")',
            'button:has-text("Submit Application")',
            '[data-testid*="apply"]',
            '[class*="apply"]',
            '[id*="apply"]',
        ]
        for selector in apply_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=1000):
                    await el.click()
                    logger.info(f"Clicked apply button: {selector}")
                    return True
            except Exception:
                continue
        logger.info("No apply button found, looking for form directly")
        return False

    async def _analyze_form_with_claude(
        self,
        page: Page,
        applicant_data: dict,
    ) -> Optional[list[dict]]:
        """Use Claude to analyze the page and produce form-filling instructions.

        Returns a list of action dicts:
        [
          {"action": "fill", "selector": "input#email", "value": "user@example.com"},
          {"action": "select", "selector": "select#country", "value": "US"},
          {"action": "check", "selector": "input#agree"},
          {"action": "upload", "selector": "input[type=file]", "file": true},
        ]
        """
        # Get a simplified snapshot of the form elements on the page
        form_snapshot = await page.evaluate("""() => {
            const elements = [];
            const inputs = document.querySelectorAll(
                'input, textarea, select, button[type="submit"]'
            );
            for (const el of inputs) {
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 && rect.height === 0) continue;
                elements.push({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    label: (() => {
                        if (el.id) {
                            const lbl = document.querySelector(`label[for="${el.id}"]`);
                            if (lbl) return lbl.textContent.trim();
                        }
                        const parent = el.closest('label, .form-group, .field, [class*="field"]');
                        if (parent) {
                            const lbl = parent.querySelector('label, .label, [class*="label"]');
                            if (lbl) return lbl.textContent.trim();
                        }
                        return '';
                    })(),
                    required: el.required || el.getAttribute('aria-required') === 'true',
                    options: el.tagName === 'SELECT'
                        ? Array.from(el.options).map(o => ({value: o.value, text: o.text}))
                        : undefined,
                    value: el.value || '',
                    cssSelector: (() => {
                        if (el.id) return `#${CSS.escape(el.id)}`;
                        if (el.name) return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
                        return '';
                    })(),
                });
            }
            return elements;
        }""")

        if not form_snapshot:
            return None

        # Only include elements that have some identifiable selector
        form_snapshot = [e for e in form_snapshot if e.get("cssSelector")]

        if not form_snapshot:
            return None

        applicant_json = json.dumps(applicant_data, indent=2)
        form_json = json.dumps(form_snapshot, indent=2)

        prompt = (
            "You are filling out a job application form. Below are the form fields "
            "found on the page and the applicant's information.\n\n"
            f"FORM FIELDS:\n{form_json}\n\n"
            f"APPLICANT DATA:\n{applicant_json}\n\n"
            "For each field that should be filled, produce a JSON action object:\n"
            '- To type text: {"action": "fill", "selector": "<css>", "value": "<text>"}\n'
            '- To select a dropdown: {"action": "select", "selector": "<css>", "value": "<option_value>"}\n'
            '- To check a checkbox: {"action": "check", "selector": "<css>"}\n'
            '- For file upload fields: {"action": "upload", "selector": "<css>"}\n\n'
            "Return ONLY a JSON array of action objects. Skip fields that are already "
            "filled or that don't match any applicant data. Use the cssSelector from "
            "the form fields. For dropdowns, pick the best matching option value."
        )

        try:
            client = self._get_claude()
            response = client.messages.create(
                model=self.config.claude_model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()

            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"Claude form analysis failed: {e}")

        return None

    async def _execute_form_fill(
        self,
        page: Page,
        actions: list[dict],
        applicant_data: dict,
        resume_path: Optional[str] = None,
    ) -> list[str]:
        """Execute Claude's form-filling instructions via Playwright."""
        fields_filled = []

        for action in actions:
            act = action.get("action")
            selector = action.get("selector", "")
            value = action.get("value", "")

            if not selector:
                continue

            try:
                locator = page.locator(selector).first

                if act == "fill":
                    await locator.click()
                    await locator.fill(value)
                    fields_filled.append(f"fill:{selector}")
                    logger.info(f"Filled {selector}")

                elif act == "select":
                    await locator.select_option(value=value)
                    fields_filled.append(f"select:{selector}")
                    logger.info(f"Selected {selector} = {value}")

                elif act == "check":
                    if not await locator.is_checked():
                        await locator.check()
                    fields_filled.append(f"check:{selector}")
                    logger.info(f"Checked {selector}")

                elif act == "upload" and resume_path:
                    await locator.set_input_files(resume_path)
                    fields_filled.append("resume_upload")
                    logger.info(f"Uploaded resume to {selector}")

            except Exception as e:
                logger.debug(f"Could not execute {act} on {selector}: {e}")

        return fields_filled

    async def _find_and_click_submit(self, page: Page) -> bool:
        """Try to find and click the submit button."""
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Submit Application")',
            'button:has-text("Submit")',
            'button:has-text("Apply")',
            'button:has-text("Send Application")',
            'button:has-text("Send")',
            '[data-testid*="submit"]',
        ]
        for selector in submit_selectors:
            try:
                el = page.locator(selector).first
                if await el.is_visible(timeout=1000):
                    await el.click()
                    logger.info(f"Clicked submit: {selector}")
                    return True
            except Exception:
                continue

        logger.warning("Could not find submit button")
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
