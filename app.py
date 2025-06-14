from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session
import os
import re
import fitz  # PyMuPDF for PDF processing
import docx
import spacy
nlp = spacy.load("en_core_web_sm")


app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Secret key for session management
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Load NLP model for entity recognition
nlp = spacy.load("en_core_web_sm")

# Ensure upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Dummy user credentials (for simplicity, replace with database authentication in production)
USER_CREDENTIALS = {'admin': 'password123'}

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
    name = next((ent.text for ent in doc.ents if ent.label_ == "PERSON"), "Not found")
    email = re.findall(r"[a-zA-Z0-9+_.-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]+", text)
    phone = re.findall(r"\+?\d{10,13}", text)
    education_keywords = ["B.Tech", "M.Tech", "B.Sc", "M.Sc", "BCA", "MCA", "MBA", "PhD"]
    education = [word for word in text.split() if word in education_keywords]
    skills = [skill for skill in [
  "Python", "Java", "C++", "JavaScript", "HTML", "CSS", "React", "Node.js", "SQL",
  "Machine Learning", "Deep Learning", "TensorFlow", "Pandas", "Data Science",
  "Cyber Security", "Networking", "AWS", "Docker", "Kubernetes", "Statistics",
  "Data Visualization", "Scikit-learn", "Neural Networks", "Optimization",
  "Big Data", "NLP", "Reinforcement Learning", "Edge AI", "AutoML"
] if skill.lower() in text.lower()]
    return name, email[0] if email else None, phone[0] if phone else None, ", ".join(education) if education else None, skills

def calculate_resume_score(name, email, phone, education, skills):
    """Calculate resume score based on extracted details"""
    total_score = (15 if name else 0) + (15 if email else 0) + (15 if phone else 0) + (20 if education else 0) + min(len(skills) * 5, 35)
    return min(total_score, 100)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USER_CREDENTIALS:
            return "User already exists. Try a different username."
        USER_CREDENTIALS[username] = password
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/', methods=['GET'])
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    username = session['user']  # Retrieve the username from the session
    return render_template('index.html', username=username)  # Pass username to template

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            session['user'] = username
            return redirect(url_for('index'))
        else:
            return "Invalid credentials. Try again."
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))
@app.route('/upload', methods=['POST'])
def upload_resume():
    if 'user' not in session:
        return redirect(url_for('login'))
    if 'resume' not in request.files:
        return redirect(request.url)
    file = request.files['resume']
    if file.filename == '':
        return redirect(request.url)
    file_ext = os.path.splitext(file.filename)[1].lower()
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    resume_text = extract_text_from_pdf(file_path) if file_ext == ".pdf" else extract_text_from_docx(file_path) if file_ext == ".docx" else None
    if resume_text is None:
        return "Unsupported file format. Upload PDF or DOCX."
    name, email, phone, education, skills = extract_details(resume_text)
    resume_score = calculate_resume_score(name, email, phone, education, skills)
    return render_template("result.html", name=name, email=email, phone=phone, education=education, skills=skills, resume_score=resume_score, resume_filename=file.filename)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=False)
