"""Exa-powered job and company search.

Uses the Exa AI search API to:
1. Discover companies matching user criteria (industry, location, size)
2. Find careers/jobs pages for those companies
3. Search for specific job listings matching user preferences
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from exa_py import Exa

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
    source: str = ""  # "exa" or "browser"


class ExaJobSearch:
    """Search for companies and job listings using Exa's AI search."""

    def __init__(self, config: Config):
        self.config = config
        self.exa = Exa(api_key=config.exa_api_key)

    def search_companies(
        self,
        query: str,
        num_results: int = 10,
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
    ) -> list[Company]:
        """Find companies matching a natural language query.

        Examples:
            - "AI startups in San Francisco"
            - "fintech companies hiring remote engineers"
            - "healthcare tech companies in NYC"
        """
        logger.info(f"Searching companies: {query}")

        search_params = {
            "query": query,
            "num_results": min(num_results, self.config.max_companies),
            "type": "auto",
            "contents": {"text": {"max_characters": 500}},
        }
        if include_domains:
            search_params["include_domains"] = include_domains
        if exclude_domains:
            search_params["exclude_domains"] = exclude_domains

        results = self.exa.search(**search_params)

        companies = []
        for result in results.results:
            companies.append(
                Company(
                    name=result.title or _extract_domain_name(result.url),
                    url=result.url,
                    description=getattr(result, "text", "") or "",
                )
            )

        logger.info(f"Found {len(companies)} companies")
        return companies

    def find_careers_page(self, company: Company) -> Optional[str]:
        """Find the careers/jobs page for a given company."""
        logger.info(f"Finding careers page for: {company.name}")

        query = f"{company.name} careers jobs hiring page"
        try:
            results = self.exa.search(
                query=query,
                num_results=3,
                type="auto",
                include_domains=[_extract_domain(company.url)],
            )
            for result in results.results:
                url_lower = result.url.lower()
                if any(
                    kw in url_lower
                    for kw in ["career", "jobs", "hiring", "openings", "positions"]
                ):
                    return result.url
            # Fall back to the first result
            if results.results:
                return results.results[0].url
        except Exception as e:
            logger.warning(f"Could not find careers page for {company.name}: {e}")

        return None

    def search_jobs(
        self,
        query: str,
        num_results: int = 20,
        include_domains: Optional[list[str]] = None,
        start_published_date: Optional[str] = None,
    ) -> list[JobListing]:
        """Search for specific job listings across the web.

        Examples:
            - "Senior Python engineer remote positions"
            - "Machine learning engineer jobs at startups"
        """
        logger.info(f"Searching jobs: {query}")

        search_params = {
            "query": query,
            "num_results": num_results,
            "type": "auto",
            "category": "company",
            "contents": {"text": {"max_characters": 1000}},
        }
        if include_domains:
            search_params["include_domains"] = include_domains
        if start_published_date:
            search_params["start_published_date"] = start_published_date

        results = self.exa.search(**search_params)

        jobs = []
        for result in results.results:
            jobs.append(
                JobListing(
                    title=result.title or "Untitled Position",
                    url=result.url,
                    description=getattr(result, "text", "") or "",
                    source="exa",
                )
            )

        logger.info(f"Found {len(jobs)} job listings")
        return jobs

    def search_job_boards(
        self,
        job_title: str,
        location: str = "Remote",
        num_results: int = 20,
    ) -> list[JobListing]:
        """Search popular job boards for specific positions."""
        job_board_domains = [
            "linkedin.com",
            "indeed.com",
            "glassdoor.com",
            "lever.co",
            "greenhouse.io",
            "ashbyhq.com",
            "workday.com",
            "wellfound.com",
            "dice.com",
        ]
        query = f"{job_title} {location} job opening apply now"
        return self.search_jobs(
            query=query,
            num_results=num_results,
            include_domains=job_board_domains,
        )

    def discover_and_enrich(
        self,
        company_query: str,
        job_titles: Optional[list[str]] = None,
    ) -> list[Company]:
        """Full pipeline: discover companies, find their careers pages.

        Returns companies enriched with careers_url.
        """
        companies = self.search_companies(company_query)

        for company in companies:
            careers_url = self.find_careers_page(company)
            if careers_url:
                company.careers_url = careers_url

        return companies


def _extract_domain(url: str) -> str:
    """Extract the root domain from a URL."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.netloc or parsed.path.split("/")[0]


def _extract_domain_name(url: str) -> str:
    """Extract a human-readable name from a URL domain."""
    domain = _extract_domain(url)
    # Remove www. and TLD
    name = domain.replace("www.", "").split(".")[0]
    return name.title()
