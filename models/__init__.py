from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    company = db.Column(db.String(200), default='')
    address = db.Column(db.Text, default='')
    city = db.Column(db.String(100), default='')
    state = db.Column(db.String(100), default='')
    zip_code = db.Column(db.String(20), default='')
    country = db.Column(db.String(100), default='')
    phone = db.Column(db.String(50), default='')
    is_admin = db.Column(db.Boolean, default=False)
    role = db.Column(db.String(20), default='client')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tickets = db.relationship('Ticket', backref='client', lazy=True)
    invoices = db.relationship('Invoice', backref='client', lazy=True)
    services = db.relationship('Service', backref='client', lazy=True)

    @property
    def has_billing_info(self):
        return bool(self.address and self.city and self.country)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='open')
    priority = db.Column(db.String(20), default='normal')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    replies = db.relationship('TicketReply', backref='ticket', lazy=True, cascade='all, delete-orphan')

class TicketReply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User')

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_id = db.Column(db.Integer, db.ForeignKey('service.id'), nullable=True)
    number = db.Column(db.String(50), unique=True, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='unpaid')
    due_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    service = db.relationship('Service', backref='invoices')

class Service(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    next_due_date = db.Column(db.DateTime)
    pterodactyl_server_id = db.Column(db.Integer, nullable=True)
    pterodactyl_user_id = db.Column(db.Integer, nullable=True)
    pterodactyl_password = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product', backref='services')

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    price = db.Column(db.Float, nullable=False)
    product_type = db.Column(db.String(50), default='other')
    plan_details = db.Column(db.Text, default='')
    pterodactyl_egg_id = db.Column(db.Integer, nullable=True)
    pterodactyl_nest_id = db.Column(db.Integer, nullable=True)
    pterodactyl_location_id = db.Column(db.Integer, nullable=True)
    pterodactyl_dedicated_ip = db.Column(db.String(20), default='0')
    pterodactyl_node_id = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    max_per_user = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default='')
