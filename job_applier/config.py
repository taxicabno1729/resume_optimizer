"""Configuration management for the Job Applier."""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Holds all configuration for the job applier pipeline."""

    # Exa API
    exa_api_key: str = ""

    # Browserbase
    browserbase_api_key: str = ""
    browserbase_project_id: str = ""

    # LLM for Stagehand
    model_api_key: str = ""
    model_name: str = "google/gemini-2.0-flash"

    # Search defaults
    max_companies: int = 10
    max_jobs_per_company: int = 5

    # Application defaults
    max_concurrent_applications: int = 3
    application_timeout_seconds: int = 120

    # Job preferences
    job_titles: list[str] = field(default_factory=lambda: ["Software Engineer"])
    locations: list[str] = field(default_factory=lambda: ["Remote"])
    exclude_domains: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            exa_api_key=os.getenv("EXA_API_KEY", ""),
            browserbase_api_key=os.getenv("BROWSERBASE_API_KEY", ""),
            browserbase_project_id=os.getenv("BROWSERBASE_PROJECT_ID", ""),
            model_api_key=os.getenv("MODEL_API_KEY", ""),
            model_name=os.getenv("STAGEHAND_MODEL", "google/gemini-2.0-flash"),
        )

    def validate(self) -> list[str]:
        """Return a list of missing required configuration fields."""
        errors = []
        if not self.exa_api_key:
            errors.append("EXA_API_KEY is required")
        if not self.browserbase_api_key:
            errors.append("BROWSERBASE_API_KEY is required")
        if not self.browserbase_project_id:
            errors.append("BROWSERBASE_PROJECT_ID is required")
        if not self.model_api_key:
            errors.append("MODEL_API_KEY is required (for Stagehand LLM)")
        return errors
