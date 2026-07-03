from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from utils import rate_limit
auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
@rate_limit(5, 300)
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = request.form.get('remember_me')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session.clear()
            session.permanent = True if remember else False
            session['user_id'] = user.id
            session['role'] = user.role or ('admin' if user.is_admin else 'client')
            session['is_admin'] = user.role == 'admin' or user.is_admin
            if user.role in ('admin', 'support'):
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('client.dashboard'))
        flash('Invalid credentials')
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit(3, 600)
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return render_template('auth/register.html')
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return render_template('auth/register.html')
        user = User(username=username, email=email, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Registration successful, please login')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html')

@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
