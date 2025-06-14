import os
import re
import fitz  # PyMuPDF
import docx
import spacy
from flask import Flask, render_template, request, send_from_directory, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-secret-key'  # Change for production
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB file size limit
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'docx'}

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.chmod(app.config['UPLOAD_FOLDER'], 0o777)  # Ensure write permissions

# Simple user database (replace with real DB in production)
users = {
    "admin": generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin123'))
}

# Load NLP model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Downloading language model...")
    from spacy.cli import download
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_from_pdf(pdf_path):
    """Extract text from PDF with error handling"""
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text("text") + "\n"
    except Exception as e:
        print(f"PDF extraction error: {e}")
        raise ValueError("Failed to extract PDF content")
    return text

def extract_text_from_docx(docx_path):
    """Extract text from DOCX with error handling"""
    text = ""
    try:
        doc = docx.Document(docx_path)
        text = "\n".join([para.text for para in doc.paragraphs if para.text])
    except Exception as e:
        print(f"DOCX extraction error: {e}")
        raise ValueError("Failed to extract DOCX content")
    return text

def extract_details(text):
    """Enhanced resume parsing with better error handling"""
    try:
        doc = nlp(text)
        
        # Name extraction with multiple fallbacks
        name = next((ent.text for ent in doc.ents if ent.label_ == "PERSON"), None)
        if not name:
            name_match = re.search(r"(?i)(name|full[-\s]?name|contact)[:\s]*(.*?)(?=\n|$)", text)
            name = name_match.group(2).strip() if name_match else "Not Found"

        # Contact info
        email = next(iter(re.findall(r"[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)), None)
        phone = next(iter(re.findall(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)), None)

        # Education with comprehensive matching
        education_keywords = {
            'degree': ["bachelor", "master", "phd", "doctorate", "b\.?a", "b\.?sc", "m\.?a", "m\.?sc"],
            'institution': ["university", "college", "institute", "school"],
            'field': ["computer science", "engineering", "information technology", "data science"]
        }
        
        education = []
        for sent in doc.sents:
            if any(re.search(keyword, sent.text.lower()) for keyword_list in education_keywords.values() for keyword in keyword_list):
                education.append(sent.text.strip())

        # Skills detection
        skills_list = [
            "Python", "Java", "C++", "JavaScript", "HTML", "CSS", "React", "Node.js", "SQL",
            "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "Pandas", "NumPy",
            "Data Science", "Data Analysis", "Data Visualization", "AWS", "Azure", "Docker"
        ]
        skills = [skill for skill in skills_list if re.search(rf"\b{re.escape(skill)}\b", text, re.IGNORECASE)]

        return name, email, phone, "\n".join(education) if education else None, skills

    except Exception as e:
        print(f"Error in resume parsing: {e}")
        return "Error", None, None, None, []

def calculate_resume_score(name, email, phone, education, skills):
    """Comprehensive scoring with weights"""
    score = 0
    score += 10 if name and name != "Not Found" else 0
    score += 10 if email else 0
    score += 10 if phone else 0
    score += 20 if education else 0
    score += min(len(set(skill.lower() for skill in skills)) * 3, 50)  # Max 50 for skills
    return min(score, 100)

@app.route('/')
def index():
    return render_template('index.html', username=session.get('username'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    if username in users and check_password_hash(users[username], password):
        session['username'] = username
        session.permanent = True
        return redirect(url_for('index'))
    
    flash('Invalid username or password', 'error')
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
def upload_resume():
    if 'username' not in session:
        flash('Please login to upload resumes', 'error')
        return redirect(url_for('index'))

    if 'resume' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    file = request.files['resume']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    if not allowed_file(file.filename):
        flash('Only PDF and DOCX files are allowed', 'error')
        return redirect(url_for('index'))
    
    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        # Save the file
        file.save(filepath)
        
        # Process based on file type
        if filename.lower().endswith('.pdf'):
            text = extract_text_from_pdf(filepath)
        else:
            text = extract_text_from_docx(filepath)
        
        # Extract details
        name, email, phone, education, skills = extract_details(text)
        score = calculate_resume_score(name, email, phone, education, skills)
        
        return render_template('result.html',
                            name=name,
                            email=email,
                            phone=phone,
                            education=education,
                            skills=skills,
                            resume_score=score,
                            resume_filename=filename,
                            username=session.get('username'))
    
    except Exception as e:
        print(f"Upload error: {e}")
        flash('Error processing your resume. Please try again.', 'error')
        return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    if 'username' not in session:
        return redirect(url_for('index'))
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('File size exceeds 5MB limit', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
