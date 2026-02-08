"""Streamlit UI for the Job Applier tool.

Free stack — only requires an Anthropic API key.
Uses local Playwright for browser automation and Claude for AI.

6-step wizard:
1. Configure API key (just ANTHROPIC_API_KEY)
2. Set up applicant profile
3. Choose search mode and scrape jobs
4. Review found jobs and select which to apply to
5. Monitor application progress
6. View results
"""

import asyncio
import json
import os
import sys
import logging

import streamlit as st

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from job_applier.config import Config
from job_applier.applicant_profile import ApplicantProfile
from job_applier.job_scraper import JobScraper, JobListing
from job_applier.browser_agent import BrowserAgent, ApplicationResult
from job_applier.job_applier import JobApplier, SearchMode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_css():
    """Load custom CSS matching the existing app theme."""
    try:
        with open("style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        pass

    st.markdown(
        """
        <style>
        .job-card {
            background: #f0f8ff;
            border-radius: 8px;
            padding: 1rem 1.2rem;
            margin-bottom: 0.75rem;
            border-left: 4px solid #1976D2;
            color: #333;
        }
        .job-card h4 { margin: 0 0 0.3rem 0; color: #1976D2; }
        .job-card p { margin: 0.2rem 0; font-size: 0.9rem; }
        .status-badge {
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .status-submitted { background: #c8e6c9; color: #2e7d32; }
        .status-failed { background: #ffcdd2; color: #c62828; }
        .status-manual { background: #fff9c4; color: #f57f17; }
        .step-header {
            font-size: 1.1rem;
            font-weight: 600;
            color: #1976D2;
            border-bottom: 2px solid #e3f2fd;
            padding-bottom: 0.4rem;
            margin-bottom: 1rem;
        }
        .free-badge {
            background: #e8f5e9;
            color: #2e7d32;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            display: inline-block;
            margin-left: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def init_session_state():
    """Initialize Streamlit session state variables."""
    defaults = {
        "config": None,
        "profile": ApplicantProfile(),
        "jobs": [],
        "selected_jobs": [],
        "applications": [],
        "status_log": [],
        "step": "config",
        "search_mode": SearchMode.ALL_BOARDS,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def status_callback(message: str):
    """Callback to capture status updates."""
    st.session_state.status_log.append(message)


# ---------------------------------------------------------------------------
# Step renderers
# ---------------------------------------------------------------------------

def render_sidebar():
    """Render the navigation sidebar."""
    with st.sidebar:
        st.markdown("### Navigation")

        steps = [
            ("config", "1. Setup"),
            ("profile", "2. Your Profile"),
            ("search", "3. Find Jobs"),
            ("review", "4. Review Jobs"),
            ("apply", "5. Apply"),
            ("results", "6. Results"),
        ]
        for step_key, label in steps:
            is_current = st.session_state.step == step_key
            prefix = ">> " if is_current else "   "
            if st.button(f"{prefix}{label}", key=f"nav_{step_key}", use_container_width=True):
                st.session_state.step = step_key
                st.rerun()

        st.markdown("---")
        st.markdown("**Stack:** Playwright + Claude")
        st.markdown(
            "[Resume Optimizer](/) | **Job Applier**",
            unsafe_allow_html=True,
        )


def render_config_step():
    """Step 1: Configure API key."""
    st.markdown('<div class="step-header">Step 1: Setup</div>', unsafe_allow_html=True)
    st.markdown(
        'Only one API key needed. <span class="free-badge">FREE TOOLS</span>',
        unsafe_allow_html=True,
    )

    st.markdown(
        "**How it works:**\n"
        "- **Playwright** (free, local) runs a browser on your machine to scrape "
        "job boards and fill out application forms\n"
        "- **Claude** (Anthropic API) understands page content, extracts job listings "
        "from HTML, and figures out how to fill application forms"
    )

    st.markdown("---")

    anthropic_key = st.text_input(
        "Anthropic API Key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Get one at console.anthropic.com",
    )

    col1, col2 = st.columns(2)
    with col1:
        claude_model = st.selectbox(
            "Claude Model",
            ["claude-sonnet-4-5-20250929", "claude-haiku-4-5-20251001", "claude-opus-4-6"],
            index=0,
            help="Sonnet is the best balance of speed and quality. Haiku is cheapest.",
        )
    with col2:
        headless = st.checkbox("Headless browser", value=True, help="Uncheck to see the browser window")

    if st.button("Save & Continue", type="primary"):
        config = Config(
            anthropic_api_key=anthropic_key,
            claude_model=claude_model,
            headless=headless,
        )
        errors = config.validate()
        if errors:
            for e in errors:
                st.warning(e)
        else:
            st.session_state.config = config
            st.session_state.step = "profile"
            st.rerun()


def render_profile_step():
    """Step 2: Applicant profile."""
    st.markdown('<div class="step-header">Step 2: Your Profile</div>', unsafe_allow_html=True)
    st.markdown("Fill in your details. These will be used to auto-fill application forms.")

    profile = st.session_state.profile

    # Try loading saved profile
    saved = ApplicantProfile.load(os.path.dirname(os.path.abspath(__file__)))
    if saved and not profile.first_name:
        profile = saved
        st.session_state.profile = profile

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Personal Information**")
        profile.first_name = st.text_input("First Name", value=profile.first_name)
        profile.last_name = st.text_input("Last Name", value=profile.last_name)
        profile.email = st.text_input("Email", value=profile.email)
        profile.phone = st.text_input("Phone", value=profile.phone)
        profile.city = st.text_input("City", value=profile.city)
        profile.state = st.text_input("State", value=profile.state)
        profile.country = st.text_input("Country", value=profile.country)

    with col2:
        st.markdown("**Professional Information**")
        profile.linkedin = st.text_input("LinkedIn URL", value=profile.linkedin)
        profile.github = st.text_input("GitHub URL", value=profile.github)
        profile.website = st.text_input("Website / Portfolio", value=profile.website)
        profile.current_title = st.text_input("Current Title", value=profile.current_title)
        profile.years_experience = st.number_input(
            "Years of Experience", min_value=0, max_value=50, value=profile.years_experience
        )
        profile.remote_preference = st.selectbox(
            "Remote Preference",
            ["remote", "hybrid", "onsite", "any"],
            index=["remote", "hybrid", "onsite", "any"].index(profile.remote_preference),
        )

    st.markdown("**Skills** (comma-separated)")
    skills_text = st.text_input("Skills", value=", ".join(profile.skills))
    profile.skills = [s.strip() for s in skills_text.split(",") if s.strip()]

    st.markdown("**Desired Job Titles** (comma-separated)")
    titles_text = st.text_input(
        "Desired Titles",
        value=", ".join(profile.desired_titles),
        placeholder="e.g. Software Engineer, Full Stack Developer",
    )
    profile.desired_titles = [t.strip() for t in titles_text.split(",") if t.strip()]

    st.markdown("**Desired Locations** (comma-separated)")
    locations_text = st.text_input(
        "Desired Locations",
        value=", ".join(profile.desired_locations) if profile.desired_locations else "Remote",
    )
    profile.desired_locations = [loc.strip() for loc in locations_text.split(",") if loc.strip()]

    st.markdown("**Resume**")
    uploaded_resume = st.file_uploader("Upload your resume (PDF)", type=["pdf"])
    if uploaded_resume:
        resume_dir = os.path.dirname(os.path.abspath(__file__))
        resume_path = os.path.join(resume_dir, "uploaded_resume.pdf")
        with open(resume_path, "wb") as f:
            f.write(uploaded_resume.getbuffer())
        profile.resume_path = resume_path
        st.success(f"Resume saved: {uploaded_resume.name}")
    elif profile.resume_path:
        st.info(f"Using previously uploaded resume: {os.path.basename(profile.resume_path)}")

    st.markdown("**Cover Letter Template**")
    st.markdown("*Use `{company}`, `{title}`, and `{name}` as placeholders.*")
    profile.cover_letter_template = st.text_area(
        "Cover Letter Template",
        value=profile.cover_letter_template,
        height=150,
        placeholder=(
            "Dear Hiring Manager,\n\n"
            "I am writing to express my interest in the {title} position at {company}. "
            "With my background in...\n\n"
            "Best regards,\n{name}"
        ),
    )

    st.markdown("**Work Authorization**")
    col_a, col_b = st.columns(2)
    with col_a:
        profile.authorized_to_work = st.checkbox(
            "Authorized to work", value=profile.authorized_to_work
        )
    with col_b:
        profile.requires_sponsorship = st.checkbox(
            "Requires sponsorship", value=profile.requires_sponsorship
        )

    col_save, col_next = st.columns([1, 1])
    with col_save:
        if st.button("Save Profile"):
            profile.save(os.path.dirname(os.path.abspath(__file__)))
            st.success("Profile saved!")

    with col_next:
        if st.button("Save & Continue to Search", type="primary"):
            errors = profile.validate()
            if errors:
                for e in errors:
                    st.warning(e)
            else:
                st.session_state.profile = profile
                profile.save(os.path.dirname(os.path.abspath(__file__)))
                st.session_state.step = "search"
                st.rerun()


def render_search_step():
    """Step 3: Search for jobs."""
    st.markdown('<div class="step-header">Step 3: Find Jobs</div>', unsafe_allow_html=True)

    if not st.session_state.config:
        st.warning("Please configure your API key first.")
        return

    mode = st.radio(
        "Search Mode",
        [
            SearchMode.ALL_BOARDS,
            SearchMode.INDEED,
            SearchMode.LINKEDIN,
            SearchMode.GOOGLE,
            SearchMode.CAREERS_PAGE,
            SearchMode.URLS,
        ],
        format_func={
            SearchMode.ALL_BOARDS: "All job boards (Indeed + LinkedIn + Google)",
            SearchMode.INDEED: "Indeed only",
            SearchMode.LINKEDIN: "LinkedIn only",
            SearchMode.GOOGLE: "Google Jobs only",
            SearchMode.CAREERS_PAGE: "Specific company careers page",
            SearchMode.URLS: "Apply to specific URLs",
        }.get,
        horizontal=False,
    )
    st.session_state.search_mode = mode

    if mode == SearchMode.URLS:
        urls_text = st.text_area(
            "Enter job URLs (one per line)",
            height=150,
            placeholder=(
                "https://company.com/careers/job-123\n"
                "https://boards.greenhouse.io/company/jobs/456"
            ),
        )
        if st.button("Add Jobs", type="primary"):
            urls = [u.strip() for u in urls_text.strip().split("\n") if u.strip()]
            st.session_state.jobs = [
                JobListing(title=f"Job at {u}", url=u, source="user") for u in urls
            ]
            st.session_state.step = "review"
            st.rerun()
        return

    if mode == SearchMode.CAREERS_PAGE:
        careers_url = st.text_input(
            "Careers page URL",
            placeholder="https://company.com/careers",
        )
        if st.button("Scrape Careers Page", type="primary"):
            if not careers_url:
                st.warning("Enter a URL.")
                return
            _run_search(mode, careers_url=careers_url)
        return

    # Job board search modes
    col1, col2 = st.columns(2)
    with col1:
        job_title = st.text_input(
            "Job Title",
            value=(
                st.session_state.profile.desired_titles[0]
                if st.session_state.profile.desired_titles
                else ""
            ),
            placeholder="e.g. Software Engineer",
        )
    with col2:
        location = st.text_input(
            "Location",
            value=(
                st.session_state.profile.desired_locations[0]
                if st.session_state.profile.desired_locations
                else "Remote"
            ),
        )

    num_results = st.slider("Max results per board", 5, 30, 15)

    if st.button("Search", type="primary"):
        if not job_title:
            st.warning("Enter a job title.")
            return
        _run_search(mode, job_title=job_title, location=location, num_results=num_results)


def _run_search(mode, job_title="", location="Remote", careers_url="", num_results=15):
    """Execute the search and store results."""
    config = st.session_state.config
    config.max_results_per_board = num_results
    profile = st.session_state.profile

    board_name = {
        SearchMode.ALL_BOARDS: "all job boards",
        SearchMode.INDEED: "Indeed",
        SearchMode.LINKEDIN: "LinkedIn",
        SearchMode.GOOGLE: "Google Jobs",
        SearchMode.CAREERS_PAGE: "careers page",
    }.get(mode, "jobs")

    with st.spinner(f"Scraping {board_name} with Playwright + Claude..."):
        try:
            applier = JobApplier(config, profile)

            async def do_search():
                try:
                    run = await applier.run_search(
                        mode=mode,
                        job_title=job_title,
                        location=location,
                        careers_url=careers_url,
                    )
                    return run.jobs_found
                finally:
                    await applier.cleanup()

            jobs = asyncio.run(do_search())
            st.session_state.jobs = jobs
            st.session_state.step = "review"
            st.rerun()

        except Exception as e:
            st.error(f"Search failed: {e}")


def render_review_step():
    """Step 4: Review found jobs and select which to apply to."""
    st.markdown(
        '<div class="step-header">Step 4: Review Found Jobs</div>',
        unsafe_allow_html=True,
    )

    jobs = st.session_state.jobs

    if not jobs:
        st.info("No jobs found yet. Go back to search to find jobs.")
        return

    st.markdown(f"**Found {len(jobs)} jobs**")

    # Select all / none
    col_all, col_none = st.columns(2)
    with col_all:
        if st.button("Select All"):
            st.session_state.selected_jobs = list(range(len(jobs)))
            st.rerun()
    with col_none:
        if st.button("Deselect All"):
            st.session_state.selected_jobs = []
            st.rerun()

    selected = st.session_state.selected_jobs

    for i, job in enumerate(jobs):
        col_check, col_info = st.columns([0.1, 0.9])
        with col_check:
            checked = st.checkbox("", value=(i in selected), key=f"job_select_{i}")
            if checked and i not in selected:
                selected.append(i)
            elif not checked and i in selected:
                selected.remove(i)
        with col_info:
            company_str = f" at **{job.company}**" if job.company else ""
            location_str = f" | {job.location}" if job.location else ""
            source_str = f" ({job.source})" if job.source else ""
            st.markdown(
                f'<div class="job-card">'
                f"<h4>{job.title}</h4>"
                f"<p>{company_str}{location_str}{source_str}</p>"
                f'<p style="font-size:0.8rem; color:#666;">{job.url}</p>'
                f"</div>",
                unsafe_allow_html=True,
            )

    st.session_state.selected_jobs = selected

    if selected:
        st.markdown(f"**{len(selected)} jobs selected**")
        if st.button("Proceed to Apply", type="primary"):
            st.session_state.step = "apply"
            st.rerun()


def render_apply_step():
    """Step 5: Apply to selected jobs."""
    st.markdown(
        '<div class="step-header">Step 5: Apply to Jobs</div>',
        unsafe_allow_html=True,
    )

    config = st.session_state.config
    profile = st.session_state.profile
    jobs = st.session_state.jobs
    selected = st.session_state.selected_jobs

    if not config:
        st.warning("Please configure your API key first.")
        return

    if not selected:
        st.warning("No jobs selected. Go back to review and select jobs.")
        return

    selected_jobs = [jobs[i] for i in selected if i < len(jobs)]

    st.markdown(f"Ready to apply to **{len(selected_jobs)}** jobs.")
    st.markdown(
        "The local Playwright browser will:\n"
        "1. Open each job page\n"
        "2. Find and click the Apply button\n"
        "3. Ask Claude to analyze the form\n"
        "4. Fill in your profile information\n"
        "5. Upload your resume\n"
        "6. Submit the application"
    )

    st.warning(
        "Review your profile details before proceeding. "
        "The agent will submit real applications on your behalf."
    )

    if st.button("Start Applying", type="primary"):
        st.session_state.applications = []
        st.session_state.status_log = []
        progress_bar = st.progress(0)
        status_area = st.empty()

        async def run_applications():
            applier = JobApplier(config, profile)
            applier.set_status_callback(status_callback)
            try:
                results = await applier.run_apply(selected_jobs)
            finally:
                await applier.cleanup()
            return results

        with st.spinner("Applying to jobs with Playwright + Claude..."):
            try:
                results = asyncio.run(run_applications())
                st.session_state.applications = results
                st.session_state.step = "results"
                st.rerun()
            except Exception as e:
                st.error(f"Application error: {e}")


def render_results_step():
    """Step 6: Show results."""
    st.markdown(
        '<div class="step-header">Step 6: Application Results</div>',
        unsafe_allow_html=True,
    )

    applications = st.session_state.applications

    if not applications:
        st.info("No application results yet. Run the applier first.")
        return

    # Summary metrics
    total = len(applications)
    submitted = sum(1 for a in applications if a.status == "submitted")
    failed = sum(1 for a in applications if a.status == "failed")
    manual = sum(1 for a in applications if a.status == "requires_manual")
    no_form = sum(1 for a in applications if a.status == "no_form_found")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(
            f'<div class="metric-container">Total<br/>'
            f'<span style="font-size:2rem; font-weight:bold;">{total}</span></div>',
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f'<div class="metric-container">Submitted<br/>'
            f'<span style="font-size:2rem; font-weight:bold; color:#2e7d32;">{submitted}</span></div>',
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            f'<div class="metric-container">Failed<br/>'
            f'<span style="font-size:2rem; font-weight:bold; color:#c62828;">{failed}</span></div>',
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f'<div class="metric-container">Needs Manual<br/>'
            f'<span style="font-size:2rem; font-weight:bold; color:#f57f17;">{manual + no_form}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Detailed results
    for app_result in applications:
        status_class = {
            "submitted": "status-submitted",
            "failed": "status-failed",
            "requires_manual": "status-manual",
            "no_form_found": "status-failed",
        }.get(app_result.status, "status-failed")

        st.markdown(
            f'<div class="job-card">'
            f"<h4>{app_result.job.title}</h4>"
            f'<p><span class="status-badge {status_class}">'
            f"{app_result.status.upper().replace('_', ' ')}</span></p>"
            f"<p>{app_result.message}</p>"
            f'<p style="font-size:0.8rem; color:#666;">{app_result.job.url}</p>'
            f"</div>",
            unsafe_allow_html=True,
        )

    # Export results
    if st.button("Export Results as JSON"):
        export_data = []
        for app_result in applications:
            export_data.append({
                "title": app_result.job.title,
                "url": app_result.job.url,
                "company": app_result.job.company,
                "status": app_result.status,
                "success": app_result.success,
                "message": app_result.message,
                "fields_filled": app_result.fields_filled,
            })
        json_str = json.dumps(export_data, indent=2)
        st.download_button(
            "Download JSON",
            data=json_str,
            file_name="application_results.json",
            mime="application/json",
        )

    # Status log
    if st.session_state.status_log:
        with st.expander("Activity Log"):
            for msg in st.session_state.status_log:
                st.text(msg)

    if st.button("Start New Search"):
        st.session_state.jobs = []
        st.session_state.selected_jobs = []
        st.session_state.applications = []
        st.session_state.status_log = []
        st.session_state.step = "search"
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Job Applier - Automated Job Applications",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    load_css()
    init_session_state()

    st.markdown(
        '<h1 class="main-header">Job Applier</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "Find and apply to jobs automatically using **Playwright** (free, local browser) "
        "and **Claude** (AI page understanding).",
    )

    render_sidebar()

    step = st.session_state.step
    if step == "config":
        render_config_step()
    elif step == "profile":
        render_profile_step()
    elif step == "search":
        render_search_step()
    elif step == "review":
        render_review_step()
    elif step == "apply":
        render_apply_step()
    elif step == "results":
        render_results_step()


if __name__ == "__main__":
    main()
