import smtplib
import boto3
import requests as req
from datetime import timedelta
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__, template_folder='templates')

# ── חובה: מפתח סודי לסשן (יש להוסיף FLASK_SECRET_KEY ל-.env) ──
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-me-in-env')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)  # שומר את הכניסה בדפדפן (Chrome בנייד/טאבלט)

AIRTABLE_TOKEN   = os.getenv('AIRTABLE_SLP2_ACCESS_TOKEN', '')
AIRTABLE_BASE_ID = os.getenv('AIRTABLE_SLP2_BASE_ID', '')
NOTIFY_EMAIL     = 'office@pngroup.co.il'
S3_BUCKET        = os.getenv('AWS_S3_BUCKET', '')
SUPPORTERS_TBL   = 'Supporters'
AGENTS_TBL       = 'OSLP'
MANAGER_SAP_CODE = 46


# ══════════════════════════════════════════════
#  אימות סוכנים מול טבלת oslp ב-Airtable
# ══════════════════════════════════════════════
def verify_agent(slp_code, password):
    """מאמת קוד סוכן + סיסמה מול טבלת oslp (slp_code / name / password). מחזיר dict או None."""
    slp_code_clean = str(slp_code).strip()
    try:
        res = req.get(
            f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AGENTS_TBL}',
            headers={'Authorization': f'Bearer {AIRTABLE_TOKEN}'},
            params={
                'filterByFormula': f"{{slp_code}}='{slp_code_clean}'",
                'maxRecords'     : 1
            }
        ).json()
    except Exception as e:
        print(f'[verify_agent] Airtable error: {e}')
        return None

    records = res.get('records') or []
    if not records:
        return None

    fld      = records[0]['fields']
    row_pass = str(fld.get('password', ''))
    if row_pass == password:
        return {'slp_code': slp_code_clean, 'name': fld.get('name', '')}
    return None


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'agent_code' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper


# ══════════════════════════════════════════════
#  Login / Logout
# ══════════════════════════════════════════════
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        slp_code = request.form.get('slp_code', '').strip()
        password = request.form.get('password', '').strip()

        if not slp_code or not password:
            error = 'יש להזין קוד סוכן וסיסמה'
        else:
            try:
                agent = verify_agent(slp_code, password)
            except Exception as e:
                print(f'[login] SQL error: {e}')
                agent = None
                error = 'שגיאת מערכת בהתחברות, נסה שוב'

            if agent:
                session.permanent = True
                session['agent_code'] = agent['slp_code']
                session['agent_name'] = agent['name']
                return redirect(url_for('agent_dashboard'))
            elif not error:
                error = 'קוד סוכן או סיסמה שגויים'

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ══════════════════════════════════════════════
#  Agent Dashboard (two-pane)
# ══════════════════════════════════════════════
@app.route('/agent')
@login_required
def agent_dashboard():
    return render_template(
        'agent.html',
        airtable_token = AIRTABLE_TOKEN,
        airtable_base  = AIRTABLE_BASE_ID,
        agent_code     = session['agent_code'],
        agent_name     = session['agent_name']
    )


# ══════════════════════════════════════════════
#  קיים - לא שונה
# ══════════════════════════════════════════════
def send_email(subject, body, to_email, cc_email=''):
    from_email  = 'pngis@gmail.com'
    password    = os.getenv('SMTP_PASSWORD', '')
    smtp_server = 'smtp.gmail.com'
    smtp_port   = 587

    msg            = MIMEMultipart()
    msg['From']    = from_email
    msg['To']      = to_email
    msg['Subject'] = subject
    if cc_email:
        msg['Cc'] = cc_email
    msg.attach(MIMEText(body, 'plain'))

    recipients = [to_email] + ([cc_email] if cc_email else [])

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(from_email, password)
        server.sendmail(from_email, recipients, msg.as_string())


def get_supporter_email(name):
    """מחזיר מייל תומכת לפי שם"""
    try:
        res = req.get(
            f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{SUPPORTERS_TBL}',
            headers={'Authorization': f'Bearer {AIRTABLE_TOKEN}'},
            params={
                'filterByFormula': f"{{name}}='{name}'",
                'maxRecords'     : 1
            }
        ).json()
        if res.get('records'):
            return res['records'][0]['fields'].get('email', '')
    except Exception as e:
        print(f'[get_supporter_email] Error: {e}')
    return ''


def get_manager_email():
    """מחזיר מייל המנהל לפי sap-user-code = 46"""
    try:
        res = req.get(
            f'https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{SUPPORTERS_TBL}',
            headers={'Authorization': f'Bearer {AIRTABLE_TOKEN}'},
            params={
                'filterByFormula': f'{{sap-user-code}}={MANAGER_SAP_CODE}',
                'maxRecords'     : 1
            }
        ).json()
        if res.get('records'):
            return res['records'][0]['fields'].get('email', '')
    except Exception as e:
        print(f'[get_manager_email] Error: {e}')
    return ''


def get_s3_client():
    return boto3.client(
        's3',
        region_name         = 'eu-north-1',
        aws_access_key_id   = os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
    )


@app.route('/chat')
def chat():
    return render_template(
        'chat.html',
        airtable_token = AIRTABLE_TOKEN,
        airtable_base  = AIRTABLE_BASE_ID
    )


@app.route('/upload-file', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400

    file     = request.files['file']
    call_num = request.form.get('call_num', 'unknown')

    try:
        s3       = get_s3_client()
        file_key = f'slp-calls/call_{call_num}_{file.filename}'

        s3.put_object(
            Bucket      = S3_BUCKET,
            Key         = file_key,
            Body        = file.read(),
            ContentType = file.content_type or 'application/octet-stream'
        )

        url = f'https://{S3_BUCKET}.s3.eu-north-1.amazonaws.com/{file_key}'
        return jsonify({'url': url})

    except Exception as e:
        print(f'[upload] Error: {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/notify', methods=['POST'])
def notify():
    data      = request.get_json()
    slp_name  = data.get('slp_name',  '')
    call_num  = data.get('call_num',  '')
    supporter = data.get('supporter', '')
    slp_issue = data.get('slp_issue', '')

    # שלוף מיילים דינמית מטבלת Supporters
    to_email = get_supporter_email(supporter) or NOTIFY_EMAIL
    cc_email = get_manager_email()

    subject = f'הסוכן {slp_name} השיב לקריאה {call_num}'
    body    = (
        f'שלום {supporter},\n\n'
        f'הסוכן {slp_name} השיב לקריאה מספר {call_num}.\n'
        f'נושא הקריאה: {slp_issue}\n\n'
        f'ניתן לצפות בהודעה דרך הממשק.'
    )

    try:
        send_email(subject, body, to_email, cc_email)
        print(f'[notify] Email sent → {to_email} | CC: {cc_email} | קריאה {call_num}')
        return jsonify({'ok': True})
    except Exception as e:
        print(f'[notify] Error: {e}')
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 80))
    print(f'Chat Server → http://localhost:{port}/chat?call_num=XXX')
    print(f'Agent Login → http://localhost:{port}/login')
    app.run(host='0.0.0.0', port=port, debug=False)