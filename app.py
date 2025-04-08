from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash
import os
import re
import fitz  # PyMuPDF for PDF processing
import docx
import spacy
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or 'dev-secret-key'  # Use environment variable in production

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB file size limit

# Load NLP model
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    print("Downloading language model...")
    from spacy.cli import download
    download("en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

# User storage (replace with database in production)
users = {
    'admin': {
        'password': generate_password_hash('password123'),
        'resumes': []
    }
}

# Helper functions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
    
    # Extract name (first PERSON entity)
    name = next((ent.text for ent in doc.ents if ent.label_ == "PERSON"), "Not found")
    
    # Extract email
    email = re.findall(r"[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]+", text)
    
    # Extract phone numbers (international format support)
    phone = re.findall(r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    
    # Education detection
    education_keywords = ["B.Tech", "M.Tech", "B.Sc", "M.Sc", "BCA", "MCA", "MBA", "PhD", 
                         "Bachelor", "Master", "Ph.D", "Diploma", "Degree"]
    education = [word for word in education_keywords if word.lower() in text.lower()]
    
    # Skills detection
    skills_list = [
        "Python", "Java", "C++", "JavaScript", "HTML", "CSS", "React", "Node.js", "SQL",
        "Machine Learning", "Deep Learning", "TensorFlow", "Pandas", "Data Science",
        "Cyber Security", "Networking", "AWS", "Docker", "Kubernetes", "Statistics",
        "Data Visualization", "Scikit-learn", "Neural Networks", "Optimization",
        "Big Data", "NLP", "Reinforcement Learning", "Edge AI", "AutoML"
    ]
    skills = [skill for skill in skills_list if skill.lower() in text.lower()]
    
    return {
        'name': name,
        'email': email[0] if email else None,
        'phone': phone[0] if phone else None,
        'education': ", ".join(education) if education else None,
        'skills': skills
    }

def calculate_resume_score(details):
    """Calculate resume score based on extracted details"""
    score = 0
    score += 15 if details['name'] and details['name'] != "Not found" else 0
    score += 15 if details['email'] else 0
    score += 15 if details['phone'] else 0
    score += 20 if details['education'] else 0
    score += min(len(details['skills']) * 5, 35)
    return min(score, 100)

# Routes
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session['username'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter both username and password')
            return redirect(url_for('login'))
        
        if username not in users or not check_password_hash(users[username]['password'], password):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        
        session['username'] = username
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not username or not password:
            flash('Please enter both username and password')
            return redirect(url_for('register'))
        
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('register'))
        
        if username in users:
            flash('Username already exists')
            return redirect(url_for('register'))
        
        users[username] = {
            'password': generate_password_hash(password),
            'resumes': []
        }
        
        flash('Registration successful! Please login')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/upload', methods=['POST'])
def upload_resume():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    if 'resume' not in request.files:
        flash('No file selected')
        return redirect(url_for('index'))
    
    file = request.files['resume']
    
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))
    
    if not allowed_file(file.filename):
        flash('Only PDF and DOCX files are allowed')
        return redirect(url_for('index'))
    
    try:
        # Secure filename and save
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Process file based on extension
        if filename.endswith('.pdf'):
            text = extract_text_from_pdf(filepath)
        else:
            text = extract_text_from_docx(filepath)
        
        if not text:
            flash('Could not extract text from file')
            return redirect(url_for('index'))
        
        # Extract details and calculate score
        details = extract_details(text)
        score = calculate_resume_score(details)
        
        # Store resume info for user
        users[session['username']]['resumes'].append({
            'filename': filename,
            'details': details,
            'score': score
        })
        
        return render_template('result.html', 
                             filename=filename,
                             score=score,
                             **details)
    
    except Exception as e:
        flash(f'Error processing file: {str(e)}')
        return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/history')
def history():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    user_resumes = users.get(session['username'], {}).get('resumes', [])
    return render_template('history.html', resumes=user_resumes)

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

if __name__ == '__main__':
    app.run(debug=True)
