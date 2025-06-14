from flask import Flask, render_template, request, send_from_directory, redirect, url_for, session
import os
import re
import fitz  # PyMuPDF for PDF processing
import docx
import spacy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this for production
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Load NLP model for entity recognition
nlp = spacy.load("en_core_web_sm")

# Simple user database (replace with a real database in production)
users = {
    "admin": generate_password_hash("password123")
}

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file"""
    text = ""
    try:
        doc = fitz.open(pdf_path)
        for page in doc:
            text += page.get_text("text") + "\n"
    except Exception as e:
        print(f"Error reading PDF: {e}")
    return text

def extract_text_from_docx(docx_path):
    """Extract text from a DOCX file"""
    text = ""
    try:
        doc = docx.Document(docx_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
    except Exception as e:
        print(f"Error reading DOCX: {e}")
    return text

def extract_details(text):
    """Extract Name, Email, Phone, Education, and Skills from resume text"""
    doc = nlp(text)
    
    # Improved name extraction
    name = next((ent.text for ent in doc.ents if ent.label_ == "PERSON"), None)
    if not name:
        # Fallback to looking for name patterns
        name_match = re.search(r"(?i)(name|full name|contact)[:\s]*(.*?)(?=\n|$)", text)
        name = name_match.group(2).strip() if name_match else "Not found"
    
    # Email and phone extraction
    email = re.findall(r"[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
    phone = re.findall(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    
    # Enhanced education extraction
    education_keywords = [
        "B.Tech", "M.Tech", "B.Sc", "M.Sc", "BCA", "MCA", "MBA", "PhD", 
        "Bachelor", "Master", "Diploma", "Degree", "Engineering", "Computer Science",
        "Information Technology", "Data Science", "Artificial Intelligence"
    ]
    education = []
    for sent in doc.sents:
        if any(word in sent.text for word in education_keywords):
            education.append(sent.text.strip())
    
    # Comprehensive skill extraction
    all_skills = [
        "Python", "Java", "C++", "JavaScript", "HTML", "CSS", "React", "Node.js", "SQL",
        "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "Pandas", "NumPy",
        "Data Science", "Data Analysis", "Data Visualization", "Tableau", "Power BI",
        "Cyber Security", "Ethical Hacking", "Networking", "AWS", "Azure", "Google Cloud",
        "Docker", "Kubernetes", "CI/CD", "DevOps", "Git", "Statistics", "Probability",
        "Linear Algebra", "Calculus", "Scikit-learn", "Neural Networks", "Computer Vision",
        "NLP", "Natural Language Processing", "Reinforcement Learning", "Big Data", "Hadoop",
        "Spark", "Kafka", "Airflow", "REST API", "GraphQL", "Microservices", "System Design",
        "Algorithms", "Data Structures", "OOP", "Functional Programming", "Agile", "Scrum"
    ]
    
    skills = []
    for skill in all_skills:
        if re.search(rf"\b{re.escape(skill)}\b", text, re.IGNORECASE):
            skills.append(skill)
    
    return (
        name,
        email[0] if email else None,
        phone[0] if phone else None,
        "\n".join(education) if education else None,
        skills
    )

def calculate_resume_score(name, email, phone, education, skills):
    """Calculate comprehensive resume score"""
    score = 0
    
    # Personal info (max 20)
    score += 5 if name else 0
    score += 5 if email else 0
    score += 5 if phone else 0
    score += 5 if education else 0
    
    # Skills (max 40)
    unique_skills = len(set(skill.lower() for skill in skills))
    score += min(unique_skills * 2, 40)  # 2 points per unique skill, max 40
    
    # Education depth (max 20)
    if education:
        edu_lines = len(education.split('\n'))
        score += min(edu_lines * 5, 20)  # 5 points per education line, max 20
    
    # Experience indicators (max 20)
    experience_keywords = ["experience", "work history", "employment", "projects"]
    has_experience = any(keyword.lower() in education.lower() for keyword in experience_keywords) if education else False
    score += 20 if has_experience else 0
    
    return min(score, 100)

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html', username=session.get('username'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in users and check_password_hash(users[username], password):
            session['username'] = username
            return redirect(url_for('index'))
        else:
            return render_template('index.html', error="Invalid username or password")
    
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_resume():
    if 'username' not in session:
        return redirect(url_for('index'))
    
    if 'resume' not in request.files:
        return redirect(request.url)
    
    file = request.files['resume']
    if file.filename == '':
        return redirect(request.url)
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ['.pdf', '.docx']:
        return render_template('index.html', error="Unsupported file format. Please upload PDF or DOCX.")
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    
    try:
        resume_text = extract_text_from_pdf(file_path) if file_ext == ".pdf" else extract_text_from_docx(file_path)
        if not resume_text.strip():
            raise ValueError("Empty resume content")
            
        name, email, phone, education, skills = extract_details(resume_text)
        resume_score = calculate_resume_score(name, email, phone, education, skills)
        
        return render_template(
            "result.html",
            name=name,
            email=email,
            phone=phone,
            education=education,
            skills=skills,
            resume_score=resume_score,
            resume_filename=file.filename,
            username=session.get('username')
        )
    except Exception as e:
        print(f"Error processing resume: {e}")
        return render_template('index.html', error="Error processing your resume. Please try again.")

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
