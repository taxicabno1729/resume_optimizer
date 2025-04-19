import fpdf

def create_sample_resume_pdf():
    pdf = fpdf.FPDF(format='letter')
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Read the sample resume text
    with open('sample_resume.txt', 'r') as f:
        resume_text = f.readlines()
    
    # Write to PDF
    line_height = 5
    for line in resume_text:
        pdf.cell(0, line_height, txt=line.strip(), ln=True)
    
    # Save the PDF
    pdf.output("sample_resume.pdf")
    print("Sample resume PDF created successfully!")

if __name__ == "__main__":
    create_sample_resume_pdf() 