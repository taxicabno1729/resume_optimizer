import streamlit as st
import pandas as pd
import PyPDF2
import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import io
import base64
import os

# Set up NLTK data path to use the local directory
nltk_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nltk_data")
if os.path.exists(nltk_data_dir):
    nltk.data.path.insert(0, nltk_data_dir)

# Check if NLTK_DATA environment variable is set
nltk_env_path = os.environ.get('NLTK_DATA')
if nltk_env_path and os.path.exists(nltk_env_path):
    nltk.data.path.insert(0, nltk_env_path)

# Download NLTK resources if needed
try:
    nltk.data.find('tokenizers/punkt')
    nltk.data.find('corpora/stopwords')
    try:
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        print("Downloading punkt_tab...")
        nltk.download('punkt_tab', download_dir=nltk_data_dir)
except LookupError:
    print("Downloading required NLTK resources...")
    nltk.download('punkt', download_dir=nltk_data_dir)
    nltk.download('stopwords', download_dir=nltk_data_dir)
    nltk.download('punkt_tab', download_dir=nltk_data_dir)

def extract_text_from_pdf(pdf_file):
    """Extract text from uploaded PDF file"""
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text() or ""
    return text

def analyze_resume_job_match(resume_text, job_description):
    """Analyze the match between resume and job description"""
    # Preprocessing
    stop_words = set(stopwords.words('english'))
    
    def preprocess(text):
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        tokens = word_tokenize(text)
        tokens = [word for word in tokens if word not in stop_words]
        return " ".join(tokens)
    
    resume_processed = preprocess(resume_text)
    job_processed = preprocess(job_description)
    
    # Create document-term matrix
    documents = [resume_processed, job_processed]
    vectorizer = CountVectorizer()
    doc_term_matrix = vectorizer.fit_transform(documents)
    
    # Get feature names (terms)
    terms = vectorizer.get_feature_names_out()
    
    # Calculate cosine similarity
    similarity = cosine_similarity(doc_term_matrix[0:1], doc_term_matrix[1:2])[0][0]
    
    # Identify matching and missing keywords
    resume_terms = set(term for term, count in zip(terms, doc_term_matrix[0].toarray()[0]) if count > 0)
    job_terms = set(term for term, count in zip(terms, doc_term_matrix[1].toarray()[0]) if count > 0)
    
    matching_keywords = resume_terms.intersection(job_terms)
    missing_keywords = job_terms - resume_terms
    
    # Sort by importance (frequency in job description)
    job_term_counts = {term: count for term, count in zip(terms, doc_term_matrix[1].toarray()[0]) if count > 0}
    missing_keywords = sorted(list(missing_keywords), key=lambda x: job_term_counts.get(x, 0), reverse=True)
    
    return {
        "similarity_score": similarity,
        "matching_keywords": list(matching_keywords),
        "missing_keywords": missing_keywords[:20]  # Return top 20 missing keywords
    }

def get_resume_suggestions(analysis_results, resume_text, job_description):
    """Generate suggestions to improve resume based on analysis"""
    suggestions = []
    
    # Overall match score suggestion
    score = analysis_results["similarity_score"] * 100
    if score < 40:
        suggestions.append("Your resume needs significant improvements to match this job description better.")
    elif score < 70:
        suggestions.append("Your resume has moderate alignment with the job description but could be improved.")
    else:
        suggestions.append("Your resume is well-aligned with this job description.")
    
    # Keyword suggestions
    if analysis_results["missing_keywords"]:
        suggestions.append("Consider incorporating these missing keywords from the job description (if relevant to your experience):")
        
    # ATS format suggestions
    suggestions.append("General ATS optimization tips:")
    suggestions.extend([
        "• Use a clean, simple format without tables, headers, footers, or images",
        "• Include section headers like 'Experience', 'Education', and 'Skills'",
        "• Use standard section titles that ATS systems can recognize",
        "• Focus on relevant skills and use industry-specific keywords",
        "• Use standard file formats like .docx or .pdf",
        "• Include your contact information at the top of the resume"
    ])
    
    return suggestions

def create_optimized_resume(resume_text, job_description, analysis_results):
    """Generate guidelines for creating an optimized resume"""
    missing_keywords = analysis_results["missing_keywords"]
    
    suggestions = [
        "## Your ATS-Optimized Resume Guidelines",
        "\n### Contact Information",
        "• Include your full name, phone number, email, and LinkedIn profile at the top",
        
        "\n### Professional Summary",
        "• Create a concise summary highlighting your relevant experience and skills",
        "• Incorporate these job-specific keywords: " + ", ".join(missing_keywords[:5]),
        
        "\n### Work Experience",
        "• List your roles in reverse chronological order",
        "• For each position, include company name, your title, dates employed, and location",
        "• Use bullet points to describe accomplishments and responsibilities",
        "• Focus on quantifiable achievements and results",
        "• Try to incorporate these job-specific keywords: " + ", ".join(missing_keywords[5:10]),
        
        "\n### Education",
        "• List degrees, institutions, graduation dates, and relevant coursework",
        
        "\n### Skills",
        "• Create a dedicated skills section",
        "• Include these technical and soft skills from the job posting: " + ", ".join(missing_keywords[10:]),
        
        "\n### Formatting Tips",
        "• Use a clean, professional format",
        "• Avoid tables, graphics, headers, and footers",
        "• Use standard section headings",
        "• Save as a standard .docx or .pdf file",
    ]
    
    return "\n".join(suggestions)

def get_download_link(text, filename="ATS_Optimized_Resume_Guidelines.txt", link_text="Download Resume Guidelines"):
    """Generate a download link for the optimized resume guidelines"""
    b64 = base64.b64encode(text.encode()).decode()
    href = f'<a href="data:file/txt;base64,{b64}" download="{filename}" class="download-btn">{link_text}</a>'
    return href

def load_css():
    """Load custom CSS"""
    try:
        with open("style.css") as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except:
        # Fallback inline CSS if style.css is not found
        st.markdown("""
        <style>
        .stApp { color: #333333 !important; }
        .stTextInput > div > div > input { color: #333333 !important; }
        .stTextArea > div > div > textarea { color: #333333 !important; }
        div.stButton > button { color: #ffffff !important; background-color: #1976D2; }
        div[data-testid="stMetricValue"] { color: #1976D2 !important; }
        </style>
        """, unsafe_allow_html=True)

def load_sample_resume_text():
    """Load sample resume text for demo purposes"""
    try:
        with open("sample_resume.txt", "r") as f:
            return f.read()
    except:
        return ""

def load_sample_job_description():
    """Load sample job description for demo purposes"""
    try:
        with open("sample_job_description.txt", "r") as f:
            return f.read()
    except:
        return ""

def main():
    st.set_page_config(
        page_title="Resume ATS Optimizer",
        page_icon="📝",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Load custom CSS
    load_css()
    
    # Add additional inline CSS to ensure text contrast
    st.markdown("""
    <style>
    /* Fix any white text on white background issues */
    .streamlit-expanderHeader, .streamlit-expanderContent { color: #333333 !important; }
    [data-testid="stForm"] { border-color: #1976D2 !important; }
    .stTextInput > label, .stTextArea > label { color: #333333 !important; }
    .stSelectbox > label { color: #333333 !important; }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<h1 class="main-header">📝 Resume ATS Optimizer</h1>', unsafe_allow_html=True)
    st.markdown("""
    <p style="color: #333333;">Upload your resume and paste the job description to get recommendations on how to optimize your resume for Applicant Tracking Systems (ATS).</p>
    """, unsafe_allow_html=True)
    
    # Demo checkbox
    use_demo = st.checkbox("Use sample data for demo", value=False)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown('<h2 class="section-header">Upload Resume</h2>', unsafe_allow_html=True)
        if not use_demo:
            uploaded_resume = st.file_uploader("Upload your resume (PDF format)", type=["pdf"])
        else:
            st.info("Using sample resume for demo")
            uploaded_resume = None  # We'll use the sample text instead
        
    with col2:
        st.markdown('<h2 class="section-header">Job Description</h2>', unsafe_allow_html=True)
        if not use_demo:
            job_description = st.text_area("Paste the job description here", height=300)
        else:
            job_description = load_sample_job_description()
            st.text_area("Sample Job Description", job_description, height=300, disabled=True)
    
    # Determine if we should proceed (either with real files or demo)
    should_proceed = (uploaded_resume is not None and job_description) or (use_demo and job_description)
    
    if should_proceed:
        if st.button("Analyze and Optimize", type="primary"):
            with st.spinner("Analyzing your resume against the job description..."):
                # Process resume
                if use_demo:
                    resume_text = load_sample_resume_text()
                else:
                    resume_text = extract_text_from_pdf(uploaded_resume)
                
                # Analyze match
                analysis_results = analyze_resume_job_match(resume_text, job_description)
                
                # Display analysis results
                st.markdown('<h2 class="section-header">Resume Analysis Results</h2>', unsafe_allow_html=True)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    match_percentage = int(analysis_results["similarity_score"] * 100)
                    st.markdown(f'<div class="metric-container">Match Score<br/><span style="font-size:2rem; font-weight:bold;">{match_percentage}%</span></div>', unsafe_allow_html=True)
                
                with col2:
                    st.markdown(f'<div class="metric-container">Matching Keywords<br/><span style="font-size:2rem; font-weight:bold;">{len(analysis_results["matching_keywords"])}</span></div>', unsafe_allow_html=True)
                
                with col3:
                    st.markdown(f'<div class="metric-container">Missing Keywords<br/><span style="font-size:2rem; font-weight:bold;">{len(analysis_results["missing_keywords"])}</span></div>', unsafe_allow_html=True)
                
                # Display keyword details
                st.markdown('<h3 class="section-header">Keyword Analysis</h3>', unsafe_allow_html=True)
                keyword_col1, keyword_col2 = st.columns(2)
                
                with keyword_col1:
                    st.markdown('<div class="keyword-section"><strong>Top Matching Keywords</strong>', unsafe_allow_html=True)
                    if analysis_results["matching_keywords"]:
                        st.markdown(", ".join(sorted(analysis_results["matching_keywords"])[:20]), unsafe_allow_html=True)
                    else:
                        st.markdown("No matching keywords found.", unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                with keyword_col2:
                    st.markdown('<div class="keyword-section"><strong>Missing Keywords (Recommended to Add)</strong>', unsafe_allow_html=True)
                    if analysis_results["missing_keywords"]:
                        st.markdown(", ".join(analysis_results["missing_keywords"]), unsafe_allow_html=True)
                    else:
                        st.markdown("No significant missing keywords found.", unsafe_allow_html=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                
                # Display suggestions
                st.markdown('<h3 class="section-header">Improvement Suggestions</h3>', unsafe_allow_html=True)
                suggestions = get_resume_suggestions(analysis_results, resume_text, job_description)
                
                st.markdown('<div class="suggestions-section">', unsafe_allow_html=True)
                for suggestion in suggestions:
                    st.markdown(suggestion, unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
                # Create optimized resume
                st.markdown('<h2 class="section-header">ATS-Optimized Resume Guidelines</h2>', unsafe_allow_html=True)
                optimized_guidelines = create_optimized_resume(resume_text, job_description, analysis_results)
                
                st.markdown(f'<div class="resume-guidelines">{optimized_guidelines}</div>', unsafe_allow_html=True)
                
                # Download link
                st.markdown(get_download_link(optimized_guidelines), unsafe_allow_html=True)
                
                # Footer
                st.markdown('<div class="footer">© 2023 Resume ATS Optimizer</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main() 