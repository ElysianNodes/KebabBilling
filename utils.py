from urllib.request import Request, urlopen
from urllib.error import URLError
from urllib.parse import urlparse
from functools import wraps
from flask import request, flash, redirect, url_for, session
import json
import secrets
import time

_rate_limits = {}

def rate_limit(limit, per):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            ip = request.remote_addr or 'unknown'
            key = (ip, f.__name__)
            now = time.time()
            timestamps = _rate_limits.get(key, [])
            timestamps = [t for t in timestamps if now - t < per]
            if len(timestamps) >= limit:
                flash(f'Too many requests. Try again in {int(per)} seconds.')
                fallback = 'client.dashboard' if session.get('user_id') else 'auth.login'
                referrer = request.referrer or ''
                if referrer:
                    parsed = urlparse(referrer)
                    if parsed.netloc and parsed.netloc != request.host:
                        referrer = ''
                return redirect(referrer or url_for(fallback))
            timestamps.append(now)
            _rate_limits[key] = timestamps
            return f(*args, **kwargs)
        return decorated
    return decorator

def get_setting(key):
    from models import Setting
    s = Setting.query.filter_by(key=key).first()
    return s.value if s else ''

def send_discord_webhook(message):
    webhook_url = get_setting('discord_webhook_url')
    if not webhook_url:
        return
    try:
        payload = json.dumps({'content': message[:1900]}).encode()
        req = Request(webhook_url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        urlopen(req, timeout=5)
    except Exception as e:
        print(f'[Webhook] Failed: {e}')

def _api_request(endpoint, method='GET', data=None):
    panel_url = get_setting('pterodactyl_url')
    api_key = get_setting('pterodactyl_api_key')
    if not panel_url or not api_key:
        return None
    url = f'{panel_url.rstrip("/")}/api/application/{endpoint.lstrip("/")}'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Accept': 'Application/vnd.pterodactyl.v1+json',
        'Content-Type': 'application/json',
    }
    body = json.dumps(data).encode() if data else None
    try:
        req = Request(url, data=body, headers=headers, method=method)
        resp = urlopen(req, timeout=15)
        return json.loads(resp.read().decode())
    except URLError as e:
        print(f'[Pterodactyl] {method} {endpoint} failed: {e}')
        if hasattr(e, 'read'):
            try:
                print(f'[Pterodactyl] Response: {e.read().decode()}')
            except Exception:
                pass
        return None

def pterodactyl_update_user_password(pt_user_id, new_password):
    data = {
        'password': new_password,
    }
    result = _api_request(f'/users/{pt_user_id}', method='PATCH', data=data)
    if result and 'attributes' in result:
        return True
    return False

def pterodactyl_find_user_by_email(email):
    result = _api_request(f'/users?filter[email]={email}', method='GET')
    if result and result.get('data'):
        return result['data'][0]['attributes']['id']
    return None

def pterodactyl_create_user(email, username):
    existing = pterodactyl_find_user_by_email(email)
    if existing:
        return existing, None
    password = username + '@Pt' + secrets.token_hex(4)
    data = {
        'username': username,
        'email': email,
        'first_name': username,
        'last_name': 'User',
        'password': password,
        'language': 'en',
    }
    result = _api_request('/users', method='POST', data=data)
    if result and 'attributes' in result:
        return result['attributes']['id'], password
    return None, None

def pterodactyl_get_node_allocation(node_id):
    page = 1
    while True:
        result = _api_request(f'/nodes/{node_id}/allocations?per_page=100&page={page}', method='GET')
        if not result or 'data' not in result:
            return None
        for alloc in result['data']:
            attrs = alloc.get('attributes', {})
            if not attrs.get('assigned'):
                return attrs['id']
        meta = result.get('meta', {}) or {}
        pagination = meta.get('pagination', {}) or {}
        total_pages = pagination.get('total_pages') or pagination.get('last_page', 0)
        if page >= total_pages:
            break
        page += 1
    return None

def pterodactyl_get_egg(nest_id, egg_id):
    result = _api_request(f'/nests/{nest_id}/eggs/{egg_id}?include=variables', method='GET')
    if result and 'attributes' in result:
        return result['attributes']
    return None

def pterodactyl_create_server(name, user_id, egg_id, nest_id, location_id=None, node_id=None, memory=1024, disk=10240, cpu=100):
    egg = pterodactyl_get_egg(nest_id, egg_id)
    if not egg:
        print(f'[Pterodactyl] Could not fetch egg {egg_id} from nest {nest_id}')
        return None

    docker_image = egg.get('docker_image', 'ghcr.io/pterodactyl/yolks:games_garrysmod')
    startup = egg.get('startup', './gmodserver')

    environment = {}
    variables = egg.get('relationships', {}).get('variables', {}).get('data', [])
    for var in variables:
        attrs = var.get('attributes', {})
        env_var = attrs.get('env_variable')
        default = attrs.get('default_value', '')
        rules = attrs.get('rules', '')
        if env_var:
            if default:
                environment[env_var] = default
            elif 'required' in rules:
                environment[env_var] = ''

    data = {
        'name': name,
        'user': user_id,
        'egg': egg_id,
        'docker_image': docker_image,
        'startup': startup,
        'environment': environment,
        'limits': {
            'memory': memory,
            'swap': 0,
            'disk': disk,
            'io': 500,
            'cpu': cpu,
        },
        'feature_limits': {
            'databases': 1,
            'backups': 1,
            'allocations': 1,
        },
        'start_on_completion': True,
        'skip_scripts': False,
    }

    if node_id:
        alloc_id = pterodactyl_get_node_allocation(node_id)
        if alloc_id is None:
            print(f'[Pterodactyl] No free allocation on node {node_id}')
            return None
        data['allocation'] = {'default': alloc_id}
    elif location_id:
        data['deploy'] = {
            'locations': [location_id],
            'dedicated_ip': False,
            'port_range': [],
        }

    result = _api_request('/servers', method='POST', data=data)
    if result and 'attributes' in result:
        return result['attributes']['id']
    return None

def activate_service(service):
    from models import db, Service
    product = service.product
    if product and product.product_type == 'pterodactyl':
        if not get_setting('pterodactyl_url') or not get_setting('pterodactyl_api_key'):
            print('[Activate] Pterodactyl not configured')
            return False
        client = service.client
        pt_user_id, pt_password = pterodactyl_create_user(email=client.email, username=client.username)
        if pt_user_id is None:
            print('[Activate] Failed to create Pterodactyl user')
            return False
        service.pterodactyl_user_id = pt_user_id
        if pt_password:
            service.pterodactyl_password = pt_password
        plan = {}
        if product.plan_details:
            try:
                plan = json.loads(product.plan_details)
            except json.JSONDecodeError:
                plan = {}
        memory = int(str(plan.get('memory', '4')).replace('GB', '').strip()) * 1024
        disk = int(str(plan.get('disk', '20')).replace('GB', '').strip()) * 1024
        cpu = int(plan.get('cpu_cores', 1)) * 100
        pt_server_id = pterodactyl_create_server(
            name=service.name, user_id=pt_user_id,
            egg_id=product.pterodactyl_egg_id, nest_id=product.pterodactyl_nest_id,
            location_id=product.pterodactyl_location_id, node_id=product.pterodactyl_node_id,
            memory=memory, disk=disk, cpu=cpu,
        )
        if pt_server_id is None:
            print('[Activate] Failed to create Pterodactyl server')
            db.session.commit()
            return False
        service.pterodactyl_server_id = pt_server_id
    service.status = 'active'
    db.session.commit()
    send_discord_webhook(f':white_check_mark: **Service activated**: {service.name} for {service.client.username}')
    return True
