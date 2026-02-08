"""Configuration management for the Job Applier.

Free stack:
- Playwright (local, free) for browser automation
- Anthropic Claude API for AI-powered page understanding
"""

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    """Holds all configuration for the job applier pipeline."""

    # Anthropic Claude API (for AI page understanding + form analysis)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-5-20250929"

    # Playwright settings
    headless: bool = True  # Run browser without visible window
    slow_mo: int = 0  # Slow down actions by ms (useful for debugging)
    browser_type: str = "chromium"  # chromium, firefox, or webkit

    # Search defaults
    max_results_per_board: int = 15
    search_timeout_seconds: int = 30

    # Application defaults
    application_timeout_seconds: int = 120

    # Job preferences
    job_titles: list[str] = field(default_factory=lambda: ["Software Engineer"])
    locations: list[str] = field(default_factory=lambda: ["Remote"])

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929"),
            headless=os.getenv("HEADLESS", "true").lower() == "true",
        )

    def validate(self) -> list[str]:
        """Return a list of missing required configuration fields."""
        errors = []
        if not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required")
        return errors
