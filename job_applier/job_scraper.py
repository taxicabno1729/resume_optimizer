"""Job scraper using Playwright + Claude.

Replaces the paid Exa API with free direct scraping:
- Scrapes Indeed, LinkedIn, Glassdoor, Google Jobs via Playwright
- Uses Claude to parse and extract structured job data from raw HTML
- Finds careers pages for specific companies
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote_plus, urljoin

from playwright.async_api import async_playwright, Page, Browser

from job_applier.config import Config

logger = logging.getLogger(__name__)


@dataclass
class Company:
    """A discovered company."""

    name: str
    url: str
    description: str = ""
    careers_url: str = ""


@dataclass
class JobListing:
    """A discovered job listing."""

    title: str
    url: str
    company: str = ""
    location: str = ""
    description: str = ""
    source: str = ""  # "indeed", "linkedin", "google", "direct", "user"


class JobScraper:
    """Scrapes job boards directly using local Playwright + Claude for parsing."""

    def __init__(self, config: Config):
        self.config = config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._claude = None

    async def _ensure_browser(self) -> Browser:
        """Launch Playwright browser if not already running."""
        if self._browser is None:
            self._playwright = await async_playwright().start()
            launcher = getattr(self._playwright, self.config.browser_type)
            self._browser = await launcher.launch(
                headless=self.config.headless,
                slow_mo=self.config.slow_mo,
            )
        return self._browser

    def _get_claude(self):
        """Lazy-init the Anthropic client."""
        if self._claude is None:
            import anthropic
            self._claude = anthropic.Anthropic(api_key=self.config.anthropic_api_key)
        return self._claude

    async def close(self):
        """Close browser and playwright."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    # ------------------------------------------------------------------
    # Indeed scraper
    # ------------------------------------------------------------------

    async def scrape_indeed(
        self,
        job_title: str,
        location: str = "Remote",
        num_results: int = 15,
    ) -> list[JobListing]:
        """Scrape Indeed for job listings."""
        logger.info(f"Scraping Indeed: {job_title} in {location}")
        browser = await self._ensure_browser()
        page = await browser.new_page()

        jobs = []
        try:
            q = quote_plus(job_title)
            l = quote_plus(location)
            url = f"https://www.indeed.com/jobs?q={q}&l={l}"
            await page.goto(url, timeout=self.config.search_timeout_seconds * 1000)
            await page.wait_for_timeout(2000)

            # Extract job cards using Claude to handle Indeed's dynamic structure
            html = await page.content()
            jobs = await self._parse_job_listings_with_claude(
                html=html,
                source="indeed",
                base_url="https://www.indeed.com",
                max_results=num_results,
            )
        except Exception as e:
            logger.warning(f"Indeed scraping failed: {e}")
        finally:
            await page.close()

        logger.info(f"Indeed: found {len(jobs)} jobs")
        return jobs

    # ------------------------------------------------------------------
    # LinkedIn scraper (public guest view)
    # ------------------------------------------------------------------

    async def scrape_linkedin(
        self,
        job_title: str,
        location: str = "Remote",
        num_results: int = 15,
    ) -> list[JobListing]:
        """Scrape LinkedIn Jobs guest view."""
        logger.info(f"Scraping LinkedIn: {job_title} in {location}")
        browser = await self._ensure_browser()
        page = await browser.new_page()

        jobs = []
        try:
            keywords = quote_plus(job_title)
            loc = quote_plus(location)
            url = f"https://www.linkedin.com/jobs/search/?keywords={keywords}&location={loc}"
            await page.goto(url, timeout=self.config.search_timeout_seconds * 1000)
            await page.wait_for_timeout(3000)

            # Scroll to load more results
            for _ in range(3):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(1000)

            html = await page.content()
            jobs = await self._parse_job_listings_with_claude(
                html=html,
                source="linkedin",
                base_url="https://www.linkedin.com",
                max_results=num_results,
            )
        except Exception as e:
            logger.warning(f"LinkedIn scraping failed: {e}")
        finally:
            await page.close()

        logger.info(f"LinkedIn: found {len(jobs)} jobs")
        return jobs

    # ------------------------------------------------------------------
    # Google Jobs scraper
    # ------------------------------------------------------------------

    async def scrape_google_jobs(
        self,
        job_title: str,
        location: str = "Remote",
        num_results: int = 15,
    ) -> list[JobListing]:
        """Scrape Google search results for job listings."""
        logger.info(f"Scraping Google Jobs: {job_title} in {location}")
        browser = await self._ensure_browser()
        page = await browser.new_page()

        jobs = []
        try:
            query = quote_plus(f"{job_title} {location} jobs apply")
            url = f"https://www.google.com/search?q={query}&ibp=htl;jobs"
            await page.goto(url, timeout=self.config.search_timeout_seconds * 1000)
            await page.wait_for_timeout(3000)

            html = await page.content()
            jobs = await self._parse_job_listings_with_claude(
                html=html,
                source="google",
                base_url="https://www.google.com",
                max_results=num_results,
            )
        except Exception as e:
            logger.warning(f"Google Jobs scraping failed: {e}")
        finally:
            await page.close()

        logger.info(f"Google Jobs: found {len(jobs)} jobs")
        return jobs

    # ------------------------------------------------------------------
    # Generic careers page scraper
    # ------------------------------------------------------------------

    async def scrape_careers_page(
        self,
        careers_url: str,
        target_titles: list[str],
    ) -> list[JobListing]:
        """Navigate to a company careers page and extract job listings."""
        logger.info(f"Scraping careers page: {careers_url}")
        browser = await self._ensure_browser()
        page = await browser.new_page()

        jobs = []
        try:
            await page.goto(careers_url, timeout=self.config.search_timeout_seconds * 1000)
            await page.wait_for_timeout(2000)

            html = await page.content()
            titles_str = ", ".join(target_titles)
            jobs = await self._parse_job_listings_with_claude(
                html=html,
                source="direct",
                base_url=careers_url,
                max_results=30,
                extra_instruction=(
                    f"Focus on positions matching these titles: {titles_str}. "
                    f"Only include jobs that are relevant to these roles."
                ),
            )
        except Exception as e:
            logger.warning(f"Careers page scraping failed for {careers_url}: {e}")
        finally:
            await page.close()

        return jobs

    # ------------------------------------------------------------------
    # Company careers page finder
    # ------------------------------------------------------------------

    async def find_careers_page(self, company_name: str) -> Optional[str]:
        """Use Google to find a company's careers page."""
        logger.info(f"Finding careers page for: {company_name}")
        browser = await self._ensure_browser()
        page = await browser.new_page()

        try:
            query = quote_plus(f"{company_name} careers jobs page")
            url = f"https://www.google.com/search?q={query}"
            await page.goto(url, timeout=self.config.search_timeout_seconds * 1000)
            await page.wait_for_timeout(2000)

            # Extract links from search results
            links = await page.eval_on_selector_all(
                "a[href]",
                """elements => elements
                    .map(el => ({href: el.href, text: el.textContent}))
                    .filter(l => l.href.startsWith('http'))
                    .filter(l => !l.href.includes('google.com'))
                    .slice(0, 20)
                """,
            )

            # Find the most likely careers page
            careers_keywords = ["career", "jobs", "hiring", "openings", "positions", "work-with-us", "join"]
            for link in links:
                href = link.get("href", "").lower()
                text = link.get("text", "").lower()
                if any(kw in href or kw in text for kw in careers_keywords):
                    return link["href"]

            # Fall back to the first non-Google result
            if links:
                return links[0]["href"]

        except Exception as e:
            logger.warning(f"Could not find careers page for {company_name}: {e}")
        finally:
            await page.close()

        return None

    # ------------------------------------------------------------------
    # Multi-board search
    # ------------------------------------------------------------------

    async def search_all_boards(
        self,
        job_title: str,
        location: str = "Remote",
        num_results: int = 15,
    ) -> list[JobListing]:
        """Search multiple job boards in parallel and merge results."""
        tasks = [
            self.scrape_indeed(job_title, location, num_results),
            self.scrape_linkedin(job_title, location, num_results),
            self.scrape_google_jobs(job_title, location, num_results),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_jobs = []
        for result in results:
            if isinstance(result, list):
                all_jobs.extend(result)
            elif isinstance(result, Exception):
                logger.warning(f"Board scraping error: {result}")

        # Deduplicate by URL
        seen_urls = set()
        unique_jobs = []
        for job in all_jobs:
            if job.url not in seen_urls:
                seen_urls.add(job.url)
                unique_jobs.append(job)

        return unique_jobs

    # ------------------------------------------------------------------
    # Claude-powered HTML parsing
    # ------------------------------------------------------------------

    async def _parse_job_listings_with_claude(
        self,
        html: str,
        source: str,
        base_url: str,
        max_results: int = 15,
        extra_instruction: str = "",
    ) -> list[JobListing]:
        """Use Claude to extract structured job listings from raw HTML."""
        # Truncate HTML to fit in context window (keep first ~60k chars)
        truncated_html = html[:60000]

        prompt = (
            f"Extract job listings from this HTML page. For each job, extract:\n"
            f"- title: the job title\n"
            f"- url: the application URL (make absolute using base: {base_url})\n"
            f"- company: the company name\n"
            f"- location: the job location\n\n"
            f"Return ONLY a JSON array of objects. Maximum {max_results} results.\n"
            f"If no jobs are found, return an empty array [].\n"
        )
        if extra_instruction:
            prompt += f"\n{extra_instruction}\n"

        prompt += f"\nHTML:\n{truncated_html}"

        try:
            client = self._get_claude()
            response = client.messages.create(
                model=self.config.claude_model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()

            # Extract JSON from response (handle markdown code blocks)
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if not json_match:
                return []

            raw_jobs = json.loads(json_match.group())
            jobs = []
            for item in raw_jobs[:max_results]:
                url = item.get("url", "")
                if url and not url.startswith("http"):
                    url = urljoin(base_url, url)
                jobs.append(
                    JobListing(
                        title=item.get("title", "Untitled"),
                        url=url,
                        company=item.get("company", ""),
                        location=item.get("location", ""),
                        source=source,
                    )
                )
            return jobs

        except Exception as e:
            logger.warning(f"Claude parsing failed: {e}")
            return []
