# KebabBilling

A lightweight billing and management panel with Pterodactyl game panel integration. Built with Flask.

## Features

| Feature | Status |
|---------|--------|
| User authentication (login/register/logout) | ✅ |
| Client dashboard with stats | ✅ |
| Product catalog & ordering | ✅ |
| Service management | ✅ |
| Invoice system (manual) | ✅ |
| Support ticket system (priorities, replies) | ✅ |
| Pterodactyl panel integration (auto-create users & servers) | ✅ |
| Pterodactyl password management (on-screen display, reset) | ✅ |
| Admin panel (dashboard, client management, settings) | ✅ |
| Support agent role (staff management) | ✅ |
| Product plan details (CPU, RAM, disk, etc.) | ✅ |
| Max per-user product limit | ✅ |
| Billing info requirement (configurable: all/paid only/none) | ✅ |
| Rate limiting on sensitive endpoints | ✅ |
| CSRF protection | ✅ |
| Setup wizard with one-time console code | ✅ |
| Discord webhook notifications | ✅ |
| Logo upload for branding | ✅ |
| Update checker | ✅ |
| **Payment gateway integration (Stripe, PayPal, etc.)** | ❌ |
| **Automated recurring billing** | ❌ |
| **Email/SMTP notifications** | ❌ |
| **Two-factor authentication** | ❌ |
| **Invoice PDF generation** | ❌ |
| **Coupon / discount codes** | ❌ |
| **Affiliate system** | ❌ |
| **API endpoints** | ❌ |
| **OAuth / social login** | ❌ |
| **Email templates** | ❌ |
| **Multi-language / i18n** | ❌ |
| **Dark mode toggle** | ❌ |
| **File uploads on tickets** | ❌ |

## Requirements

- Python 3.8+
- Flask
- Flask-SQLAlchemy
- Werkzeug

## Installation

```bash
git clone https://github.com/ElysianNodes/KebabBilling.git
cd KebabBilling
pip install -r requirements.txt
python app.py
```

The setup wizard will appear at `http://localhost:5000/setup`. A one-time setup code is printed to the console.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | Auto-generated | Flask session signing key |
| `FLASK_DEBUG` | `0` | Enable debug mode (`1`) |

## Discord

Join the community: https://discord.gg/d3FXFKqyN4
