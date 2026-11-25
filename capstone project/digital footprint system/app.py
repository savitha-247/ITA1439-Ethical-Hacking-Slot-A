import os
from flask import Flask, render_template, request, send_file, redirect, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
from reportlab.pdfgen import canvas
from io import BytesIO
import csv
from io import StringIO, BytesIO
import re
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "development-secret-key-change-before-deployment"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)

def init_db():
    conn = sqlite3.connect('footprint.db')
    cursor = conn.cursor()

    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Add Admin/User Role
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [column[1] for column in cursor.fetchall()]

    if 'role' not in user_columns:
        cursor.execute(
            "ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'"
        )

    # Assessments Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            score INTEGER,
            risk TEXT,
            date TEXT,
            user_id INTEGER
        )
    ''')

    # Add Missing Assessment Columns
    cursor.execute("PRAGMA table_info(assessments)")
    columns = [column[1] for column in cursor.fetchall()]

    if 'user_id' not in columns:
        cursor.execute("ALTER TABLE assessments ADD COLUMN user_id INTEGER")

    for column in ['social', 'personal', 'location', 'security']:
        if column not in columns:
            cursor.execute(
                f"ALTER TABLE assessments ADD COLUMN {column} INTEGER DEFAULT 0"
            )

    conn.commit()
    conn.close()

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/assessment')
def assessment():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('assessment.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    if 'user_id' not in session:
        return redirect('/login')

    try:
        social = int(request.form.get('social', 0))
        personal = int(request.form.get('personal', 0))
        location = int(request.form.get('location', 0))
        security = int(request.form.get('security', 0))
    except (ValueError, TypeError):
        return "Invalid assessment values", 400

    scores = [social, personal, location, security]

    if any(value < 0 or value > 2 for value in scores):
        return "Invalid assessment values", 400

    score = sum(scores)

    if score <= 3:
        risk = "LOW"
    elif score <= 6:
        risk = "MEDIUM"
    else:
        risk = "HIGH"

    conn = sqlite3.connect('footprint.db')
    cursor = conn.cursor()

    cursor.execute(
        '''INSERT INTO assessments
        (score, risk, date, user_id, social, personal, location, security)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            score,
            risk,
            datetime.now().strftime("%d-%m-%Y %H:%M"),
            session['user_id'],
            social,
            personal,
            location,
            security
        )
    )

    conn.commit()
    conn.close()

    return render_template(
        'result.html',
        score=score,
        risk=risk
    )
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('footprint.db')
    cursor = conn.cursor()

    user_id = session['user_id']

    # Total assessments
    cursor.execute(
        'SELECT COUNT(*) FROM assessments WHERE user_id = ?',
        (user_id,)
    )
    total = cursor.fetchone()[0]

    # Risk level counts
    cursor.execute(
        'SELECT risk, COUNT(*) FROM assessments WHERE user_id = ? GROUP BY risk',
        (user_id,)
    )
    risk_counts = dict(cursor.fetchall())

    low = risk_counts.get('LOW', 0)
    medium = risk_counts.get('MEDIUM', 0)
    high = risk_counts.get('HIGH', 0)

    # Latest assessment details
    cursor.execute('''
        SELECT score, risk, date, social, personal, location, security
        FROM assessments
        WHERE user_id = ?
        ORDER BY id DESC LIMIT 1
    ''', (user_id,))

    latest = cursor.fetchone()
    # Assessment timeline
    cursor.execute('''
        SELECT score, risk, date
        FROM assessments
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 7
    ''', (user_id,))

    timeline = list(reversed(cursor.fetchall()))
    conn.close()

    if latest:
        latest_score = latest[0]
        latest_risk = latest[1]
        latest_date = latest[2]

        categories = {
            'Social': latest[3],
            'Personal': latest[4],
            'Location': latest[5],
            'Security': latest[6]
        }
    else:
        latest_score = 0
        latest_risk = 'NOT AVAILABLE'
        latest_date = 'No assessment yet'

        categories = {
            'Social': 0,
            'Personal': 0,
            'Location': 0,
            'Security': 0
        }

    return render_template(
        'dashboard.html',
        total=total,
        low=low,
        medium=medium,
        high=high,
        latest_score=latest_score,
        latest_risk=latest_risk,
        latest_date=latest_date,
        categories=categories,
        timeline=timeline
    )
@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('footprint.db')
    cursor = conn.cursor()

    cursor.execute(
        'SELECT id, score, risk, date FROM assessments WHERE user_id = ? ORDER BY id DESC',
        (session['user_id'],)
    )
    records = cursor.fetchall()

    conn.close()

    return render_template('history.html', records=records)


@app.route('/download-report')
def download_report():

    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('footprint.db')
    cursor = conn.cursor()

    cursor.execute(
        'SELECT id, score, risk, date FROM assessments WHERE user_id = ? ORDER BY id DESC LIMIT 1',
        (session['user_id'],)
    )
    record = cursor.fetchone()

    conn.close()

    if record is None:
        return "No assessment report available."

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)

    pdf.setTitle("Digital Footprint Risk Report")

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(80, 780, "DIGITAL FOOTPRINT RISK REPORT")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(80, 730, f"Assessment ID: {record[0]}")
    pdf.drawString(80, 700, f"Risk Score: {record[1]} / 8")
    pdf.drawString(80, 670, f"Risk Level: {record[2]}")
    pdf.drawString(80, 640, f"Date: {record[3]}")

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(80, 590, "Security Recommendations")

    pdf.setFont("Helvetica", 11)

    recommendations = [
        "Review social media privacy settings.",
        "Avoid sharing sensitive personal information.",
        "Disable unnecessary location sharing.",
        "Enable Two-Factor Authentication."
    ]

    y = 560

    for item in recommendations:
        pdf.drawString(90, y, "- " + item)
        y -= 25

    pdf.drawString(80, 420, "Generated by Footprint AI")
    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="Digital_Risk_Report.pdf",
        mimetype="application/pdf"
    )
@app.route('/clear-history', methods=['POST'])
def clear_history():
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('footprint.db')
    cursor = conn.cursor()

    cursor.execute(
        'DELETE FROM assessments WHERE user_id = ?',
        (session['user_id'],)
    )

    conn.commit()
    conn.close()

    return redirect('/history')
@app.route('/download-history')
def download_history():

    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('footprint.db')
    cursor = conn.cursor()

    cursor.execute(
        'SELECT id, score, risk, date FROM assessments WHERE user_id = ? ORDER BY id DESC',
        (session['user_id'],)
    )

    records = cursor.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(['ID', 'Risk Score', 'Risk Level', 'Date'])
    writer.writerows(records)

    buffer = BytesIO(output.getvalue().encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name='Assessment_History.csv',
        mimetype='text/csv'
    )
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = sqlite3.connect('footprint.db')
        cursor = conn.cursor()

        try:
            cursor.execute(
                'INSERT INTO users (username, email, password) VALUES (?, ?, ?)',
                (username, email, password)
            )
            conn.commit()
            return redirect('/login')
        except sqlite3.IntegrityError:
            return "Email already registered. Please use another email."
        finally:
            conn.close()

    return render_template('register.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect('footprint.db')
        cursor = conn.cursor()

        cursor.execute(
            'SELECT id, username, email, password, role FROM users WHERE email = ?',
            (email,)
        )

        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session.clear()
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[4]

            return redirect('/')

        else:
            return "Invalid email or password. Please try again."

    return render_template('login.html')
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')
@app.route('/security-tools')
def security_tools():
    if 'user_id' not in session:
        return redirect('/login')

    return render_template('security_tools.html')


@app.route('/check-password', methods=['POST'])
def check_password_strength():
    if 'user_id' not in session:
        return redirect('/login')

    password = request.form.get('password', '')

    if len(password) > 128:
        return "Password is too long", 400

    score = 0

    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r'[A-Z]', password):
        score += 1
    if re.search(r'[a-z]', password):
        score += 1
    if re.search(r'[0-9]', password):
        score += 1
    if re.search(r'[^A-Za-z0-9]', password):
        score += 1

    strength = "Weak" if score <= 2 else "Medium" if score <= 4 else "Strong"

    return render_template('security_tools.html', password_strength=strength)


@app.route('/check-url', methods=['POST'])
def check_phishing_url():
    if 'user_id' not in session:
        return redirect('/login')

    url = request.form.get('url', '').strip()

    if not url or len(url) > 2048:
        return "Invalid URL", 400

    if '://' not in url:
        url = 'https://' + url

    parsed = urlparse(url)
    host = parsed.hostname or ''
    risk = 0
    warnings = []

    if parsed.scheme != 'https':
        risk += 1
        warnings.append("Website does not use HTTPS")

    if not host:
        risk += 2
        warnings.append("Invalid website address")
    else:
        if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', host):
            risk += 2
            warnings.append("Website uses an IP address")
        if '@' in url:
            risk += 2
            warnings.append("URL contains an @ symbol")
        if host.count('.') >= 3:
            risk += 1
            warnings.append("URL contains many subdomains")
        if '-' in host:
            risk += 1
            warnings.append("Domain contains hyphens")
        if host.startswith('xn--') or '.xn--' in host:
            risk += 1
            warnings.append("Domain uses encoded characters")

    result = "High Risk" if risk >= 3 else "Medium Risk" if risk >= 1 else "Low Risk"

    if not warnings:
        warnings.append("No basic warning indicators detected")

    return render_template(
        'security_tools.html',
        url_result=result,
        warnings=warnings
    )
@app.route('/test')
def test():
    return "Flask routes are working!"

@app.route('/recommendations')
def recommendations():
    if 'user_id' not in session:
        return redirect('/login')

    return render_template('recommendations.html')


@app.route('/action-plan')
def action_plan():
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('footprint.db')
    conn.row_factory = sqlite3.Row

    assessment = conn.execute("""
        SELECT social, personal, location, security
        FROM assessments
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (session['user_id'],)).fetchone()

    conn.close()

    action_plan = []

    if assessment:
        categories = {
            'Social Media Privacy': assessment['social'],
            'Personal Information': assessment['personal'],
            'Location Privacy': assessment['location'],
            'Account Security': assessment['security']
        }

        tips = {
            'Social Media Privacy': 'Make your social media profiles private and limit public personal information.',
            'Personal Information': 'Avoid sharing sensitive details such as phone numbers and addresses.',
            'Location Privacy': 'Disable unnecessary location permissions and avoid public live-location sharing.',
            'Account Security': 'Use strong passwords, enable two-factor authentication and update your accounts regularly.'
        }

        for category, score in categories.items():
            if score > 0:
                action_plan.append({
                    'title': category,
                    'description': tips[category],
                    'priority': 'High' if score == 2 else 'Medium'
                })

    return render_template(
        'action_plan.html',
        action_plan=action_plan
    )
@app.route('/comparison')
def comparison():
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('footprint.db')
    conn.row_factory = sqlite3.Row

    records = conn.execute("""
        SELECT score, risk, date
        FROM assessments
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 2
    """, (session['user_id'],)).fetchall()

    conn.close()

    comparison_data = None

    if len(records) == 2:
        latest = records[0]
        previous = records[1]

        difference = previous['score'] - latest['score']

        if difference > 0:
            status = "Improved"
        elif difference < 0:
            status = "Risk Increased"
        else:
            status = "No Change"

        comparison_data = {
            'latest': latest,
            'previous': previous,
            'difference': abs(difference),
            'status': status
        }

    return render_template(
        'comparison.html',
        comparison_data=comparison_data,
        records=records
    )
@app.route('/download-security-report')
def download_security_report():
    if 'user_id' not in session:
        return redirect('/login')

    conn = sqlite3.connect('footprint.db')
    conn.row_factory = sqlite3.Row

    data = conn.execute("""
        SELECT score, risk, date, social, personal, location, security
        FROM assessments
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (session['user_id'],)).fetchone()

    conn.close()

    if not data:
        return "Please complete an assessment first."

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)

    pdf.setTitle("Digital Footprint Security Report")

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(50, 790, "DIGITAL FOOTPRINT SECURITY REPORT")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 750, "Intelligent Digital Footprint Risk Awareness System")
    pdf.drawString(50, 720, "Student: " + session.get('username', 'User'))

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(50, 675, "Assessment Summary")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 645, f"Total Risk Score: {data['score']}")
    pdf.drawString(50, 620, f"Risk Level: {data['risk']}")
    pdf.drawString(50, 595, f"Assessment Date: {data['date']}")

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(50, 545, "Category-wise Scores")

    categories = [
        ("Social Media Privacy", data['social']),
        ("Personal Information", data['personal']),
        ("Location Privacy", data['location']),
        ("Account Security", data['security'])
    ]

    y = 515

    pdf.setFont("Helvetica", 12)

    for category, score in categories:
        pdf.drawString(60, y, f"{category}: {score}/2")
        y -= 25

    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(50, 390, "Security Recommendations")

    recommendations = [
        "Keep social media profiles private.",
        "Avoid sharing sensitive personal information.",
        "Disable unnecessary location permissions.",
        "Use strong passwords and enable two-factor authentication.",
        "Avoid suspicious links and websites."
    ]

    pdf.setFont("Helvetica", 11)
    y = 360

    for tip in recommendations:
        pdf.drawString(60, y, "- " + tip)
        y -= 25

    pdf.setFont("Helvetica-Oblique", 10)
    pdf.drawString(50, 100, "Generated by Digital Footprint Risk Awareness System")

    pdf.save()

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="Digital_Footprint_Security_Report.pdf",
        mimetype="application/pdf"
    )
@app.route('/learning')
def learning():
    if 'user_id' not in session:
        return redirect('/login')

    return render_template('learning.html')
@app.route('/quiz')
def quiz():
    if 'user_id' not in session:
        return redirect('/login')

    return render_template('quiz.html')
@app.route('/admin-dashboard')
def admin_dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    if session.get('role') != 'admin':
        return "Access Denied! Admin permission required.", 403

    conn = sqlite3.connect('footprint.db')
    conn.row_factory = sqlite3.Row

    # Total Users
    total_users = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]

    # Total Assessments
    total_assessments = conn.execute(
        "SELECT COUNT(*) FROM assessments"
    ).fetchone()[0]

    # High Risk Count
    high_risk = conn.execute(
        "SELECT COUNT(*) FROM assessments WHERE UPPER(risk)='HIGH'"
    ).fetchone()[0]

    # Medium Risk Count
    medium_risk = conn.execute(
        "SELECT COUNT(*) FROM assessments WHERE UPPER(risk)='MEDIUM'"
    ).fetchone()[0]
    # Low Risk Count
    low_risk = conn.execute(
        "SELECT COUNT(*) FROM assessments WHERE UPPER(risk)='LOW'"
    ).fetchone()[0]
    # Registered Users
    users = conn.execute(
        "SELECT id, username, email, role FROM users ORDER BY id DESC"
    ).fetchall()

    # Risk Filter
    risk_filter = request.args.get('risk', 'ALL').upper()

    if risk_filter not in ['ALL', 'HIGH', 'MEDIUM', 'LOW']:
        risk_filter = 'ALL'

    # Assessment Records
    if risk_filter == 'ALL':

        assessments = conn.execute("""
            SELECT assessments.id, users.username, users.email,
                   assessments.score, assessments.risk, assessments.date
            FROM assessments
            LEFT JOIN users ON assessments.user_id = users.id
            ORDER BY assessments.id DESC
        """).fetchall()

    else:

        assessments = conn.execute("""
            SELECT assessments.id, users.username, users.email,
                   assessments.score, assessments.risk, assessments.date
            FROM assessments
            LEFT JOIN users ON assessments.user_id = users.id
            WHERE UPPER(assessments.risk) = ?
            ORDER BY assessments.id DESC
        """, (risk_filter,)).fetchall()

    conn.close()

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_assessments=total_assessments,
        high_risk=high_risk,
        medium_risk=medium_risk,
        low_risk=low_risk,
        users=users,
        assessments=assessments,
        selected_risk=risk_filter
    )
@app.route('/update-user-role/<int:user_id>', methods=['POST'])
def update_user_role(user_id):

    if 'user_id' not in session:
        return redirect('/login')

    if session.get('role') != 'admin':
        return "Access Denied!", 403

    role = request.form.get('role')

    if role not in ['admin', 'user']:
        return "Invalid role!", 400

    conn = sqlite3.connect('footprint.db')
    conn.execute(
        "UPDATE users SET role = ? WHERE id = ?",
        (role, user_id)
    )
    conn.commit()
    conn.close()

    return redirect('/admin-dashboard')
@app.route('/delete-user/<int:user_id>', methods=['POST'])
def delete_user(user_id):

    if 'user_id' not in session:
        return redirect('/login')

    if session.get('role') != 'admin':
        return "Access Denied!", 403

    # Prevent admin from deleting their own account
    if user_id == session['user_id']:
        return "You cannot delete your own admin account!", 400

    conn = sqlite3.connect('footprint.db')

    # Delete the user's assessment history first
    conn.execute(
        "DELETE FROM assessments WHERE user_id = ?",
        (user_id,)
    )

    # Delete the user account
    conn.execute(
        "DELETE FROM users WHERE id = ?",
        (user_id,)
    )

    conn.commit()
    conn.close()

    return redirect('/admin-dashboard')
if __name__ == '__main__':
    init_db()
    app.run(debug=True)