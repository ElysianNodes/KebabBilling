from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from models import db, User, Ticket, TicketReply, Invoice, Service, Product, Setting
from datetime import datetime
from utils import send_discord_webhook, activate_service, get_setting, pterodactyl_update_user_password, rate_limit
import secrets
import json

client_bp = Blueprint('client', __name__)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def check_billing(product=None):
    requirement = get_setting('billing_requirement') or 'all'
    if requirement == 'none':
        return True
    if requirement == 'paid_only' and product and product.price == 0:
        return True
    user = User.query.get(session['user_id'])
    if user.has_billing_info:
        return True
    flash('Please complete your billing information in your profile before ordering')
    return False

def billing_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not check_billing():
            return redirect(url_for('client.profile'))
        return f(*args, **kwargs)
    return decorated

@client_bp.route('/')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    pending_services = Service.query.filter_by(user_id=user.id, status='pending').count()
    active_services = Service.query.filter_by(user_id=user.id, status='active').count()
    unpaid_invoices = Invoice.query.filter_by(user_id=user.id, status='unpaid').count()
    open_tickets = Ticket.query.filter_by(user_id=user.id, status='open').count()
    recent_invoices = Invoice.query.filter_by(user_id=user.id).order_by(Invoice.created_at.desc()).limit(5).all()
    recent_tickets = Ticket.query.filter_by(user_id=user.id).order_by(Ticket.created_at.desc()).limit(5).all()
    return render_template('client/dashboard.html', user=user, active_services=active_services,
                         pending_services=pending_services, unpaid_invoices=unpaid_invoices,
                         open_tickets=open_tickets, recent_invoices=recent_invoices,
                         recent_tickets=recent_tickets)

@client_bp.route('/tickets')
@login_required
def tickets():
    user = User.query.get(session['user_id'])
    all_tickets = Ticket.query.filter_by(user_id=user.id).order_by(Ticket.created_at.desc()).all()
    return render_template('client/tickets.html', tickets=all_tickets)

@client_bp.route('/tickets/new', methods=['GET', 'POST'])
@login_required
@rate_limit(3, 600)
def new_ticket():
    user = User.query.get(session['user_id'])
    services = Service.query.filter_by(user_id=user.id).all()
    if request.method == 'POST':
        service_id = request.form.get('service_id')
        ticket = Ticket(
            user_id=session['user_id'],
            service_id=int(service_id) if service_id else None,
            subject=request.form['subject'],
            message=request.form['message'],
            priority=request.form.get('priority', 'normal')
        )
        db.session.add(ticket)
        db.session.commit()
        flash('Ticket created')
        send_discord_webhook(f':inbox_tray: **New ticket** #{ticket.id} "{ticket.subject}" by {ticket.client.username}')
        return redirect(url_for('client.tickets'))
    return render_template('client/ticket_new.html', services=services)

@client_bp.route('/tickets/<int:id>', methods=['GET', 'POST'])
@login_required
@rate_limit(5, 600)
def view_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    if ticket.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied')
        return redirect(url_for('client.tickets'))
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
        send_discord_webhook(f':speech_balloon: **New ticket reply** on #{ticket.id} "{ticket.subject}" by {ticket.client.username}')
        return redirect(url_for('client.view_ticket', id=id))
    return render_template('client/ticket_view.html', ticket=ticket)

@client_bp.route('/invoices')
@login_required
def invoices():
    user = User.query.get(session['user_id'])
    all_invoices = Invoice.query.filter_by(user_id=user.id).order_by(Invoice.created_at.desc()).all()
    return render_template('client/invoices.html', invoices=all_invoices)

@client_bp.route('/invoices/<int:id>')
@login_required
def view_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    if invoice.user_id != session['user_id'] and not session.get('is_admin'):
        flash('Access denied')
        return redirect(url_for('client.invoices'))
    return render_template('client/invoice_view.html', invoice=invoice)

@client_bp.route('/services')
@login_required
def services():
    user = User.query.get(session['user_id'])
    all_services = Service.query.filter_by(user_id=user.id).order_by(Service.created_at.desc()).all()
    return render_template('client/services.html', services=all_services)

@client_bp.route('/order')
@login_required
def order():
    products = Product.query.filter_by(is_active=True).all()
    return render_template('client/order.html', products=products)

@client_bp.route('/order/<int:product_id>', methods=['GET', 'POST'])
@login_required
@rate_limit(3, 600)
def checkout(product_id):
    product = Product.query.get_or_404(product_id)
    if not product.is_active:
        flash('This product is not available')
        return redirect(url_for('client.order'))
    if not check_billing(product):
        return redirect(url_for('client.profile'))
    if product.max_per_user:
        user_count = Service.query.filter_by(user_id=session['user_id'], product_id=product.id).count()
        if user_count >= product.max_per_user:
            flash(f'You already own {user_count} of this product (limit: {product.max_per_user})')
            return redirect(url_for('client.order'))
    if request.method == 'POST':
        is_free = product.price == 0
        service = Service(
            user_id=session['user_id'],
            product_id=product.id,
            name=product.name,
            description=product.description,
            price=product.price,
            status='active' if is_free else 'pending'
        )
        db.session.add(service)
        db.session.flush()
        invoice = Invoice(
            user_id=session['user_id'],
            service_id=service.id,
            number=f'INV-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}-{service.id}',
            amount=product.price,
            description=f'Order: {product.name}',
            status='paid' if is_free else 'unpaid'
        )
        db.session.add(invoice)
        db.session.commit()
        user = User.query.get(session['user_id'])
        send_discord_webhook(f':rocket: **New order** by {user.username}: {product.name} ($ {product.price}) - {invoice.number}')
        if is_free:
            activate_service(service)
            flash(f'Free service "{product.name}" activated!')
        else:
            flash(f'Order placed! "{product.name}" is pending admin approval.')
        return redirect(url_for('client.services'))
    user = User.query.get(session['user_id'])
    return render_template('client/checkout.html', product=product, user=user)

@client_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        user.email = request.form['email']
        user.company = request.form.get('company', '')
        user.address = request.form.get('address', '')
        user.city = request.form.get('city', '')
        user.state = request.form.get('state', '')
        user.zip_code = request.form.get('zip_code', '')
        user.country = request.form.get('country', '')
        user.phone = request.form.get('phone', '')
        db.session.commit()
        flash('Profile updated')
        return redirect(url_for('client.profile'))
    return render_template('client/profile.html', user=user)

@client_bp.route('/profile/delete', methods=['POST'])
@login_required
def delete_account():
    user = User.query.get(session['user_id'])
    if user.is_admin:
        flash('Admin accounts cannot be deleted')
        return redirect(url_for('client.profile'))
    TicketReply.query.filter_by(user_id=user.id).delete()
    Ticket.query.filter_by(user_id=user.id).delete()
    Invoice.query.filter_by(user_id=user.id).delete()
    Service.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    session.clear()
    flash('Your account has been permanently deleted.')
    return redirect(url_for('auth.login'))

@client_bp.route('/pterodactyl', methods=['GET', 'POST'])
@login_required
def pterodactyl():
    user = User.query.get(session['user_id'])
    pterodactyl_url = get_setting('pterodactyl_url')
    services = Service.query.filter(
        Service.user_id == user.id,
        Service.product.has(product_type='pterodactyl'),
        Service.pterodactyl_server_id.isnot(None),
    ).all()
    panel_password = None
    for s in services:
        if s.pterodactyl_password:
            panel_password = s.pterodactyl_password
            break
    new_password = session.pop('pterodactyl_password', None)
    return render_template('client/pterodactyl.html', services=services,
                         pterodactyl_url=pterodactyl_url, new_password=new_password,
                         panel_password=panel_password)

@client_bp.route('/pterodactyl/reset-password', methods=['POST'])
@login_required
def pterodactyl_reset_password():
    user = User.query.get(session['user_id'])
    pt_user_id = Service.query.filter(
        Service.user_id == user.id,
        Service.pterodactyl_user_id.isnot(None),
        Service.product.has(product_type='pterodactyl'),
    ).with_entities(Service.pterodactyl_user_id).first()
    if not pt_user_id or not pt_user_id[0]:
        flash('No Pterodactyl account found')
        return redirect(url_for('client.pterodactyl'))
    new_password = user.username + '@Pt' + secrets.token_hex(4)
    if pterodactyl_update_user_password(pt_user_id[0], new_password):
        session['pterodactyl_password'] = new_password
        flash('Pterodactyl panel password reset successfully!')
    else:
        flash('Failed to reset password. Check Pterodactyl configuration.')
    return redirect(url_for('client.pterodactyl'))
