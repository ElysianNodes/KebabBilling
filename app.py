import os
import secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from config import Config
from models import db, User, Setting
from routes.auth import auth_bp
from routes.client import client_bp
from routes.admin import admin_bp
from utils import send_discord_webhook, get_setting
import json

app = Flask(__name__)
app.config.from_object(Config)
app.config['APP_VERSION'] = '0.0.9'
app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

def csrf_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.method == 'POST':
            token = session.get('_csrf_token')
            form_token = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token', '')
            if not token or not secrets.compare_digest(token, form_token):
                abort(400, 'Invalid CSRF token')
        return f(*args, **kwargs)
    return decorated

@app.before_request
def check_csrf():
    if request.method in ('POST', 'PUT', 'DELETE'):
        exempt = ('setup', 'skip_setup', 'static')
        if request.endpoint and request.endpoint in exempt:
            return
        token = session.get('_csrf_token')
        form_token = request.form.get('_csrf_token') or request.headers.get('X-CSRF-Token', '')
        if not token or not secrets.compare_digest(token, form_token):
            abort(400, 'Invalid CSRF token')

@app.context_processor
def inject_globals():
    token = session.get('_csrf_token') or secrets.token_hex(32)
    if '_csrf_token' not in session:
        session['_csrf_token'] = token
    return {
        'get_setting': get_setting,
        'app_version': app.config.get('APP_VERSION', '0.0.0'),
        'csrf_token': token,
    }

db.init_app(app)

app.register_blueprint(auth_bp)
app.register_blueprint(client_bp)
app.register_blueprint(admin_bp)

def is_installed():
    setting = Setting.query.filter_by(key='installed').first()
    return setting is not None and setting.value == 'true'

@app.before_request
def check_setup():
    if request.endpoint in ('static', 'setup', 'auth.login', 'auth.register', 'auth.logout'):
        return
    if not is_installed() and not request.path.startswith('/setup'):
        return redirect(url_for('setup'))

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if is_installed():
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        expected = session.get('setup_code')
        if not expected or request.form.get('code', '').strip() != expected:
            flash('Invalid setup code. Check the console output.')
            return render_template('setup_wizard.html', setup_code=expected or session.get('setup_code'))
        from werkzeug.security import generate_password_hash
        admin = User(
            username=request.form['username'],
            email=request.form['email'],
            password=generate_password_hash(request.form['password']),
            company=request.form.get('company', ''),
            is_admin=True,
            role='admin'
        )
        db.session.add(admin)
        db.session.add(Setting(key='company_name', value=request.form.get('company_name', 'My Company')))
        db.session.add(Setting(key='company_email', value=request.form.get('company_email', '')))
        db.session.add(Setting(key='company_address', value=request.form.get('company_address', '')))
        db.session.add(Setting(key='currency', value=request.form.get('currency', 'USD')))
        db.session.add(Setting(key='installed', value='true'))
        db.session.commit()
        session['user_id'] = admin.id
        session['is_admin'] = True
        session['role'] = 'admin'
        send_discord_webhook(':white_check_mark: **KebabBilling** installed successfully')
        return redirect(url_for('admin.dashboard'))
    code = session.get('setup_code')
    if not code:
        code = secrets.token_hex(4)
        session['setup_code'] = code
    try:
        with open(os.path.join(app.instance_path, 'setup_code.txt'), 'w') as f:
            f.write(code)
    except OSError:
        pass
    border = '=' * 52
    print()
    print(border)
    print(f'  Setup code: {code}')
    print(f'  Enter this code in the web setup form to continue.')
    print(border)
    print()
    return render_template('setup_wizard.html', setup_code=code)

@app.route('/setup/skip', methods=['POST'])
def skip_setup():
    db.session.add(Setting(key='installed', value='true'))
    db.session.commit()
    return redirect(url_for('auth.login'))

os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance'), exist_ok=True)

with app.app_context():
    db.create_all()
    result = db.session.execute(db.text('PRAGMA table_info(service)'))
    cols = [row[1] for row in result.fetchall()]
    if 'pterodactyl_password' not in cols:
        db.session.execute(db.text('ALTER TABLE service ADD COLUMN pterodactyl_password VARCHAR(256)'))
        db.session.commit()
    result = db.session.execute(db.text('PRAGMA table_info(user)'))
    cols = [row[1] for row in result.fetchall()]
    if 'role' not in cols:
        db.session.execute(db.text("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'client'"))
        db.session.execute(db.text("UPDATE user SET role = 'admin' WHERE is_admin = 1"))
        db.session.execute(db.text("UPDATE user SET role = 'client' WHERE is_admin = 0 OR is_admin IS NULL"))
        db.session.commit()
    result = db.session.execute(db.text('PRAGMA table_info(product)'))
    cols = [row[1] for row in result.fetchall()]
    if 'max_per_user' not in cols:
        db.session.execute(db.text('ALTER TABLE product ADD COLUMN max_per_user INTEGER DEFAULT 0'))
        db.session.commit()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug, host='0.0.0.0', port=5000)
