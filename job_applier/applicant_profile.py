"""Applicant profile management.

Stores and manages the user's personal information, resume,
and application preferences used to fill out job applications.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional


PROFILE_FILENAME = "applicant_profile.json"


@dataclass
class ApplicantProfile:
    """All the information needed to fill out job applications."""

    # Personal info
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""

    # Online presence
    linkedin: str = ""
    github: str = ""
    website: str = ""

    # Location
    city: str = ""
    state: str = ""
    country: str = ""

    # Professional
    current_title: str = ""
    years_experience: int = 0
    skills: list[str] = field(default_factory=list)

    # Resume
    resume_path: str = ""
    resume_text: str = ""

    # Cover letter template (use {company} and {title} as placeholders)
    cover_letter_template: str = ""

    # Work authorization
    authorized_to_work: bool = True
    requires_sponsorship: bool = False

    # Preferences
    desired_titles: list[str] = field(default_factory=list)
    desired_locations: list[str] = field(default_factory=list)
    min_salary: int = 0
    remote_preference: str = "remote"  # "remote", "hybrid", "onsite", "any"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def generate_cover_letter(self, company: str, title: str) -> str:
        """Generate a cover letter from the template for a specific job."""
        if not self.cover_letter_template:
            return ""
        return (
            self.cover_letter_template
            .replace("{company}", company)
            .replace("{title}", title)
            .replace("{name}", self.full_name)
        )

    def to_form_data(self, company: str = "", title: str = "") -> dict:
        """Convert profile to a dict suitable for form filling."""
        data = {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "linkedin": self.linkedin,
            "github": self.github,
            "website": self.website,
            "city": self.city,
            "state": self.state,
            "country": self.country,
            "current_title": self.current_title,
            "years_experience": str(self.years_experience),
            "authorized_to_work": "Yes" if self.authorized_to_work else "No",
            "requires_sponsorship": "Yes" if self.requires_sponsorship else "No",
        }
        if company and title:
            data["cover_letter"] = self.generate_cover_letter(company, title)
        return data

    def save(self, directory: str = ".") -> str:
        """Save profile to a JSON file."""
        path = os.path.join(directory, PROFILE_FILENAME)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)
        return path

    @classmethod
    def load(cls, directory: str = ".") -> Optional["ApplicantProfile"]:
        """Load profile from a JSON file."""
        path = os.path.join(directory, PROFILE_FILENAME)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            data = json.load(f)
        return cls(**data)

    def validate(self) -> list[str]:
        """Return a list of missing required fields."""
        errors = []
        if not self.first_name:
            errors.append("First name is required")
        if not self.last_name:
            errors.append("Last name is required")
        if not self.email:
            errors.append("Email is required")
        return errors
