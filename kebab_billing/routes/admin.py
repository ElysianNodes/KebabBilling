import os
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from models import db, User, Ticket, TicketReply, Invoice, Service, Product, Setting
from datetime import datetime
from utils import send_discord_webhook, get_setting, activate_service
import json

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def staff_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') not in ('admin', 'support'):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

@admin_bp.route('/admin')
@staff_required
def dashboard():
    total_clients = User.query.filter_by(is_admin=False).count()
    total_tickets = Ticket.query.count()
    open_tickets = Ticket.query.filter_by(status='open').count()
    total_invoices = Invoice.query.count()
    unpaid_invoices = Invoice.query.filter_by(status='unpaid').count()
    total_services = Service.query.count()
    active_services = Service.query.filter_by(status='active').count()
    pending_services = Service.query.filter_by(status='pending').count()
    recent_tickets = Ticket.query.order_by(Ticket.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html', total_clients=total_clients,
                         total_tickets=total_tickets, open_tickets=open_tickets,
                         total_invoices=total_invoices, unpaid_invoices=unpaid_invoices,
                         total_services=total_services, active_services=active_services,
                         pending_services=pending_services, recent_tickets=recent_tickets)

@admin_bp.route('/admin/clients')
@staff_required
def clients():
    all_clients = User.query.filter(User.role != 'admin').all()
    return render_template('admin/clients.html', clients=all_clients)

@admin_bp.route('/admin/clients/create', methods=['GET', 'POST'])
@staff_required
def create_client():
    if request.method == 'POST':
        from werkzeug.security import generate_password_hash
        user = User(
            username=request.form['username'],
            email=request.form['email'],
            password=generate_password_hash(request.form['password']),
            company=request.form.get('company', ''),
            phone=request.form.get('phone', '')
        )
        db.session.add(user)
        db.session.commit()
        flash('Client created')
        send_discord_webhook(f':bust_in_silhouette: **New client created**: {user.username} ({user.email})')
        return redirect(url_for('admin.clients'))
    return render_template('admin/client_create.html')

@admin_bp.route('/admin/clients/<int:id>/delete', methods=['POST'])
@admin_required
def delete_client(id):
    user = User.query.get_or_404(id)
    if user.role == 'admin':
        flash('Cannot delete admin')
        return redirect(url_for('admin.clients'))
    db.session.delete(user)
    db.session.commit()
    flash('Client deleted')
    return redirect(url_for('admin.clients'))

@admin_bp.route('/admin/tickets')
@staff_required
def tickets():
    all_tickets = Ticket.query.order_by(Ticket.created_at.desc()).all()
    return render_template('admin/tickets.html', tickets=all_tickets)

@admin_bp.route('/admin/tickets/<int:id>', methods=['GET', 'POST'])
@staff_required
def view_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    if request.method == 'POST':
        reply = TicketReply(
            ticket_id=id,
            user_id=session['user_id'],
            message=request.form['message']
        )
        ticket.status = 'replied'
        ticket.updated_at = datetime.utcnow()
        db.session.add(reply)
        db.session.commit()
        flash('Reply added')
        send_discord_webhook(f':speech_balloon: **New ticket reply** on #{ticket.id} "{ticket.subject}" by admin')
        return redirect(url_for('admin.view_ticket', id=id))
    return render_template('admin/ticket_view.html', ticket=ticket)

@admin_bp.route('/admin/tickets/<int:id>/close', methods=['POST'])
@staff_required
def close_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    ticket.status = 'closed'
    ticket.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Ticket closed')
    return redirect(url_for('admin.tickets'))

@admin_bp.route('/admin/invoices')
@staff_required
def invoices():
    all_invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
    return render_template('admin/invoices.html', invoices=all_invoices)

@admin_bp.route('/admin/invoices/create', methods=['GET', 'POST'])
@admin_required
def create_invoice():
    if request.method == 'POST':
        invoice = Invoice(
            user_id=request.form['user_id'],
            number=request.form['number'],
            amount=float(request.form['amount']),
            description=request.form.get('description', ''),
            status=request.form.get('status', 'unpaid'),
            due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d') if request.form.get('due_date') else None
        )
        db.session.add(invoice)
        db.session.commit()
        flash('Invoice created')
        return redirect(url_for('admin.invoices'))
    clients = User.query.filter_by(is_admin=False).all()
    return render_template('admin/invoice_create.html', clients=clients)

@admin_bp.route('/admin/invoices/<int:id>/toggle', methods=['POST'])
@admin_required
def toggle_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    was_unpaid = invoice.status == 'unpaid'
    invoice.status = 'paid' if was_unpaid else 'unpaid'
    db.session.commit()
    if was_unpaid and invoice.service_id:
        service = Service.query.get(invoice.service_id)
        if service and service.status == 'pending':
            activate_service(service)
    flash(f'Invoice {invoice.number} marked as {invoice.status}')
    return redirect(url_for('admin.invoices'))

@admin_bp.route('/admin/services')
@staff_required
def services():
    all_services = Service.query.order_by(Service.created_at.desc()).all()
    return render_template('admin/services.html', services=all_services)

@admin_bp.route('/admin/services/create', methods=['GET', 'POST'])
@admin_required
def create_service():
    if request.method == 'POST':
        service = Service(
            user_id=request.form['user_id'],
            name=request.form['name'],
            description=request.form.get('description', ''),
            price=float(request.form['price']),
            status=request.form.get('status', 'active'),
            next_due_date=datetime.strptime(request.form['next_due_date'], '%Y-%m-%d') if request.form.get('next_due_date') else None
        )
        db.session.add(service)
        db.session.commit()
        flash('Service created')
        return redirect(url_for('admin.services'))
    clients = User.query.filter_by(is_admin=False).all()
    return render_template('admin/service_create.html', clients=clients)

@admin_bp.route('/admin/services/<int:id>/toggle', methods=['POST'])
@admin_required
def toggle_service(id):
    service = Service.query.get_or_404(id)
    status_map = {'active': 'suspended', 'suspended': 'active', 'terminated': 'active'}
    service.status = status_map.get(service.status, 'active')
    db.session.commit()
    return redirect(url_for('admin.services'))

@admin_bp.route('/admin/services/<int:id>/approve', methods=['POST'])
@admin_required
def approve_service(id):
    service = Service.query.get_or_404(id)
    if activate_service(service):
        flash(f'Service "{service.name}" approved and activated.')
    else:
        flash(f'Failed to activate service "{service.name}". Check Pterodactyl configuration.')
    return redirect(url_for('admin.services'))

@admin_bp.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def settings():
    if request.method == 'POST':
        for key in ['company_name', 'company_email', 'company_address', 'currency',
                     'pterodactyl_url', 'pterodactyl_api_key', 'discord_webhook_url']:
            setting = Setting.query.filter_by(key=key).first()
            if setting:
                setting.value = request.form.get(key, '')
            else:
                setting = Setting(key=key, value=request.form.get(key, ''))
                db.session.add(setting)
        logo_file = request.files.get('logo')
        if logo_file and logo_file.filename:
            filename = secure_filename(logo_file.filename)
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            logo_name = f'logo.{ext}' if ext else 'logo'
            logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], logo_name)
            logo_file.save(logo_path)
            setting = Setting.query.filter_by(key='logo_path').first()
            if setting:
                setting.value = logo_name
            else:
                db.session.add(Setting(key='logo_path', value=logo_name))

        db.session.commit()
        flash('Settings saved')
        return redirect(url_for('admin.settings'))
    settings_dict = {}
    for s in Setting.query.all():
        settings_dict[s.key] = s.value
    return render_template('admin/settings.html', settings=settings_dict)

@admin_bp.route('/admin/staff', methods=['GET', 'POST'])
@admin_required
def staff():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        user = User.query.filter_by(email=email).first()
        if not user:
            flash('No user found with that email')
        elif user.role == 'admin':
            flash('Cannot change admin role')
        elif user.role == 'support':
            user.role = 'client'
            db.session.commit()
            flash(f'{user.username} demoted to client')
        else:
            user.role = 'support'
            db.session.commit()
            flash(f'{user.username} promoted to support agent')
        return redirect(url_for('admin.staff'))
    support_staff = User.query.filter_by(role='support').all()
    return render_template('admin/staff.html', staff=support_staff)

@admin_bp.route('/admin/products')
@admin_required
def products():
    all_products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/products.html', products=all_products)

@admin_bp.route('/admin/products/create', methods=['GET', 'POST'])
@admin_required
def create_product():
    if request.method == 'POST':
        plan_details = {}
        for key in request.form:
            if key.startswith('pd_'):
                plan_details[key[3:]] = request.form[key]
        product = Product(
            name=request.form['name'],
            description=request.form.get('description', ''),
            price=float(request.form['price']),
            product_type=request.form.get('product_type', 'other'),
            plan_details=json.dumps(plan_details) if plan_details else '',
            pterodactyl_egg_id=request.form.get('pterodactyl_egg_id', type=int),
            pterodactyl_nest_id=request.form.get('pterodactyl_nest_id', type=int),
            pterodactyl_location_id=request.form.get('pterodactyl_location_id', type=int),
            pterodactyl_dedicated_ip=request.form.get('pterodactyl_dedicated_ip', '0'),
            pterodactyl_node_id=request.form.get('pterodactyl_node_id', type=int),
            max_per_user=int(request.form.get('max_per_user', 0)),
        )
        db.session.add(product)
        db.session.commit()
        flash('Product created')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_create.html')

@admin_bp.route('/admin/products/<int:id>/toggle', methods=['POST'])
@admin_required
def toggle_product(id):
    product = Product.query.get_or_404(id)
    product.is_active = not product.is_active
    db.session.commit()
    return redirect(url_for('admin.products'))

@admin_bp.route('/admin/products/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_product(id):
    product = Product.query.get_or_404(id)
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form.get('description', '')
        product.price = float(request.form['price'])
        product.product_type = request.form.get('product_type', 'other')
        plan_details = {}
        for key in request.form:
            if key.startswith('pd_'):
                plan_details[key[3:]] = request.form[key]
        product.plan_details = json.dumps(plan_details) if plan_details else ''
        product.pterodactyl_egg_id = request.form.get('pterodactyl_egg_id', type=int)
        product.pterodactyl_nest_id = request.form.get('pterodactyl_nest_id', type=int)
        product.pterodactyl_location_id = request.form.get('pterodactyl_location_id', type=int)
        product.pterodactyl_dedicated_ip = request.form.get('pterodactyl_dedicated_ip', '0')
        product.pterodactyl_node_id = request.form.get('pterodactyl_node_id', type=int)
        product.max_per_user = int(request.form.get('max_per_user', 0))
        db.session.commit()
        flash('Product updated')
        return redirect(url_for('admin.products'))
    return render_template('admin/product_create.html', product=product)

@admin_bp.route('/admin/products/<int:id>/delete', methods=['POST'])
@admin_required
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted')
    return redirect(url_for('admin.products'))

from urllib.request import Request, urlopen
from urllib.error import URLError

def parse_version_file(text):
    version = ''
    changelog = []
    in_changelog = False
    for line in text.splitlines():
        if line.startswith('version ='):
            version = line.split('=', 1)[1].strip()
        elif line.startswith('changelog:'):
            in_changelog = True
        elif in_changelog and line.startswith('-'):
            changelog.append(line[1:].strip())
    return version, changelog

def compare_versions(current, remote):
    if not remote:
        return False
    cur = [int(x) for x in current.split('.')]
    rem = [int(x) for x in remote.split('.')]
    return rem > cur

@admin_bp.route('/admin/updates')
@admin_required
def updates():
    remote_version = None
    changelog = []
    error = None
    try:
        req = Request('https://ulz.pages.dev/cdn/public.txt', method='GET', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
        resp = urlopen(req, timeout=10)
        text = resp.read().decode()
        remote_version, changelog = parse_version_file(text)
    except Exception as e:
        error = 'Failed to fetch update information. Check your internet connection.'
    update_available = compare_versions(current_app.config.get('APP_VERSION', '0.0.9'), remote_version) if remote_version else False
    return render_template('admin/updates.html',
                         current_version=current_app.config.get('APP_VERSION', '0.0.9'),
                         remote_version=remote_version,
                         changelog=changelog,
                         update_available=update_available,
                         error=error)
