# KebabBilling

A lightweight billing and management panel with Pterodactyl game panel integration. Built with Flask.

---

## Quick Install (Linux)

One-liner with domain + Let's Encrypt SSL:
```bash
curl -L https://raw.githubusercontent.com/ElysianNodes/KebabBilling/main/install.sh | bash /dev/stdin yourdomain.com y your@email.com
```

Minimal (IP only, no SSL):
```bash
curl -L https://raw.githubusercontent.com/ElysianNodes/KebabBilling/main/install.sh | bash /dev/stdin 203.0.113.10
```

What it does:
- Installs Python 3, nginx, certbot, git
- Clones the repo to `/opt/kebab_billing`
- Creates a Python virtualenv and installs dependencies
- Generates a `SECRET_KEY` and writes `.env`
- Sets up a systemd service (`kebab-billing`)
- Configures nginx as a reverse proxy
- Optionally provisions Let's Encrypt SSL via certbot
- Opens firewall ports 80/443

After install, visit `/setup` to create your admin account.

---

## Manual Install

### Requirements
- Python 3.8+
- pip + virtualenv

```bash
git clone https://github.com/ElysianNodes/KebabBilling.git
cd KebabBilling
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open `http://localhost:5000/setup`.

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | Auto-generated | Flask session signing key |
| `FLASK_DEBUG` | `0` | Set to `1` for debug mode |

---

## Management

```bash
# Service
systemctl status kebab-billing     # check status
systemctl restart kebab-billing     # restart after updates
journalctl -u kebab-billing -f      # live logs

# Update
cd /opt/kebab_billing
sudo -u kebab git pull
systemctl restart kebab-billing

# Nginx
nginx -t                            # test config
systemctl reload nginx              # reload nginx

# SSL renewal (auto via certbot)
certbot renew
```

---

## Features

### Implemented
- User authentication (login / register / logout)
- Client dashboard with usage stats
- Product catalog with ordering
- Service management (activate, suspend, terminate)
- Invoice system (manual)
- Support ticket system with priorities and replies
- **Pterodactyl panel integration** — auto-create users & servers on order
- Pterodactyl password reset (on-screen display)
- Admin panel (dashboard, client management, settings)
- Support agent role (staff management page)
- Product plan details (CPU cores, RAM, disk, etc.)
- Max per-user product limit
- Configurable billing info requirement (all / paid only / none)
- Rate limiting on login, register, tickets, checkout
- CSRF protection on all POST forms
- Discord webhook notifications
- Logo upload for branding
- Update checker

### Not Yet
- Payment gateway integration (Stripe, PayPal, etc.)
- Automated recurring billing
- Email / SMTP notifications
- Two-factor authentication
- Invoice PDF generation
- Coupon / discount codes
- Affiliate system
- API endpoints
- OAuth / social login
- Email templates
- Multi-language / i18n
- Dark mode toggle
- File uploads on tickets

---

## Discord

Questions? https://discord.gg/d3FXFKqyN4
