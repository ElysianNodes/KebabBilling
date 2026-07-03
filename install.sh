#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/kebab_billing"
APP_USER="kebab"
REPO_URL="https://github.com/ElysianNodes/KebabBilling.git"

if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root." >&2
    exit 1
fi

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS="$ID"
        OS_VERSION="$VERSION_ID"
    else
        echo "Unsupported OS." >&2
        exit 1
    fi
}

install_packages() {
    echo "Installing system packages..."
    case "$OS" in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-pip python3-venv nginx certbot python3-certbot-nginx git curl
            ;;
        centos|rhel|fedora|rocky|almalinux)
            if command -v dnf &>/dev/null; then
                dnf install -y python3 python3-pip nginx certbot python3-certbot-nginx git curl
            else
                yum install -y epel-release
                yum install -y python3 python3-pip nginx certbot python3-certbot-nginx git curl
            fi
            ;;
        *)
            echo "Unsupported OS: $OS" >&2
            exit 1
            ;;
    esac
}

create_user() {
    if ! id -u "$APP_USER" &>/dev/null; then
        useradd -r -s /bin/false -d "$APP_DIR" "$APP_USER"
    fi
}

setup_app() {
    echo "Setting up KebabBilling..."
    mkdir -p "$APP_DIR"
    if [ -d "$APP_DIR/.git" ]; then
        git -C "$APP_DIR" pull
    else
        git clone "$REPO_URL" "$APP_DIR"
    fi
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"

    echo "Creating Python virtual environment..."
    sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install gunicorn
    sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

    echo "Generating SECRET_KEY..."
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    cat > "$APP_DIR/.env" <<EOF
SECRET_KEY=$SECRET_KEY
FLASK_DEBUG=0
EOF
    chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
}

setup_systemd() {
    echo "Creating systemd service..."
    cat > /etc/systemd/system/kebab-billing.service <<EOF
[Unit]
Description=KebabBilling
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable kebab-billing
    systemctl start kebab-billing
    echo "KebabBilling service started."
}

setup_nginx() {
    local domain="$1"
    echo "Configuring nginx for $domain..."
    cat > /etc/nginx/sites-available/kebab-billing <<EOF
server {
    listen 80;
    server_name $domain;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    if [ -L /etc/nginx/sites-enabled/kebab-billing ]; then
        rm /etc/nginx/sites-enabled/kebab-billing
    fi
    ln -s /etc/nginx/sites-available/kebab-billing /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
}

setup_ssl() {
    local domain="$1"
    local email="$2"
    echo "Obtaining Let's Encrypt certificate for $domain..."
    certbot --nginx -d "$domain" --non-interactive --agree-tos -m "$email" --redirect
    echo "SSL configured."
}

configure_firewall() {
    if command -v ufw &>/dev/null; then
        ufw allow 80/tcp
        ufw allow 443/tcp
        ufw --force enable
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --permanent --add-service=http
        firewall-cmd --permanent --add-service=https
        firewall-cmd --reload
    fi
}

main() {
    detect_os
    install_packages
    create_user
    setup_app

    read -rp "Enter your domain or IP address: " SERVER_ADDRESS

    USE_SSL=false
    if [[ "$SERVER_ADDRESS" =~ [a-zA-Z] ]]; then
        read -rp "Use Let's Encrypt SSL? (y/N): " SSL_CHOICE
        if [[ "$SSL_CHOICE" =~ ^[Yy]$ ]]; then
            USE_SSL=true
            while true; do
                read -rp "Enter your email for Let's Encrypt: " SSL_EMAIL
                if [[ "$SSL_EMAIL" =~ @ ]]; then break; fi
                echo "Invalid email."
            done
        fi
    fi

    setup_systemd
    setup_nginx "$SERVER_ADDRESS"

    if $USE_SSL; then
        setup_ssl "$SERVER_ADDRESS" "$SSL_EMAIL"
    fi

    configure_firewall

    echo ""
    echo "====================  KebabBilling installed!  ===================="
    echo "  URL:      http${USE_SSL}s://$SERVER_ADDRESS"
    echo "  Setup:    http${USE_SSL}s://$SERVER_ADDRESS/setup"
    echo "  App dir:  $APP_DIR"
    echo "  Service:  systemctl status kebab-billing"
    echo "  Logs:     journalctl -u kebab-billing -f"
    echo "=================================================================="
}

main "$@"
