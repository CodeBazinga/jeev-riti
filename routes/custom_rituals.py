import json
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify)
from models import CustomRitualRequest, Customer, Ritual, Booking
from extensions import db
from datetime import datetime

custom_rituals_bp = Blueprint('custom_rituals', __name__)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json_field(raw, default):
    """Safely parse a JSON string from a form field."""
    if not raw or not raw.strip():
        return default
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return default


def _build_requirements(form):
    """Build the requirements JSONB dict from individual form fields."""
    num_pandits       = form.get('num_pandits', '').strip()
    samagri_included  = form.get('samagri_included') == 'true'
    preferred_date    = form.get('preferred_date', '').strip()
    preferred_time    = form.get('preferred_time', '').strip()
    location_type     = form.get('location_type', '').strip()
    has_havan_space   = form.get('has_havan_space') == 'true'
    languages_raw     = form.get('languages', '').strip()
    special_raw       = form.get('special_requests', '').strip()

    req = {}
    if num_pandits:
        try:
            req['num_pandits'] = int(num_pandits)
        except ValueError:
            pass
    req['samagri_included'] = samagri_included
    if preferred_date:
        req['preferred_date'] = preferred_date
    if preferred_time:
        req['preferred_time'] = preferred_time
    if location_type:
        req['location_type'] = location_type
    req['has_havan_space'] = has_havan_space
    if languages_raw:
        req['language'] = [l.strip() for l in languages_raw.split(',') if l.strip()]
    if special_raw:
        req['special_requests'] = [s.strip() for s in special_raw.splitlines() if s.strip()]
    return req


def _build_components(form):
    """
    Build ritual_components list from the dynamic component rows submitted.
    Each row sends:  component_ritual_id_N, component_name_N, component_sequence_N
    Falls back to raw JSON if provided.
    """
    raw_json = form.get('ritual_components_json', '').strip()
    if raw_json:
        parsed = _parse_json_field(raw_json, [])
        if isinstance(parsed, list):
            return parsed

    components = []
    idx = 1
    while True:
        name = form.get(f'component_name_{idx}', '').strip()
        if not name:
            break
        comp = {'name': name, 'sequence': idx}
        ritual_id_str = form.get(f'component_ritual_id_{idx}', '').strip()
        if ritual_id_str:
            try:
                comp['ritual_id'] = int(ritual_id_str)
            except ValueError:
                pass
        components.append(comp)
        idx += 1
    return components


def _build_breakdown(form):
    """Build quoted_breakdown dict from individual fee fields."""
    breakdown = {}
    for key in ['pandit_fee', 'samagri', 'travel', 'accommodation', 'other']:
        val = form.get(f'bd_{key}', '').strip()
        if val:
            try:
                breakdown[key] = float(val)
            except ValueError:
                pass
    return breakdown if breakdown else None


# ─────────────────────────────────────────────────────────────────────────────
#  LIST
# ─────────────────────────────────────────────────────────────────────────────

@custom_rituals_bp.route('/')
def list_requests():
    search    = request.args.get('search', '').strip()
    status_f  = request.args.get('status', '')   # 'quoted' | 'pending'
    ritual_f  = request.args.get('ritual_id', '')

    q = CustomRitualRequest.query.join(Customer)
    if search:
        q = q.filter(
            db.or_(
                CustomRitualRequest.title.ilike(f'%{search}%'),
                Customer.name.ilike(f'%{search}%'),
                Customer.email.ilike(f'%{search}%'),
            )
        )
    if status_f == 'quoted':
        q = q.filter(CustomRitualRequest.quoted_price.isnot(None))
    elif status_f == 'pending':
        q = q.filter(CustomRitualRequest.quoted_price.is_(None))
    if ritual_f:
        try:
            q = q.filter(CustomRitualRequest.ritual_id == int(ritual_f))
        except ValueError:
            pass

    requests_list = q.order_by(CustomRitualRequest.created_at.desc()).all()
    rituals       = Ritual.query.order_by(Ritual.title).all()

    stats = {
        'total':   CustomRitualRequest.query.count(),
        'quoted':  CustomRitualRequest.query.filter(
                       CustomRitualRequest.quoted_price.isnot(None)).count(),
        'pending': CustomRitualRequest.query.filter(
                       CustomRitualRequest.quoted_price.is_(None)).count(),
        'booked':  CustomRitualRequest.query.join(
                       Booking,
                       Booking.custom_ritual_request_id == CustomRitualRequest.id
                   ).count(),
    }
    return render_template(
        'custom_rituals/list.html',
        requests=requests_list,
        rituals=rituals,
        stats=stats,
        filters=dict(search=search, status=status_f, ritual_id=ritual_f),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  NEW REQUEST
# ─────────────────────────────────────────────────────────────────────────────

@custom_rituals_bp.route('/new', methods=['GET', 'POST'])
def new_request():
    rituals   = Ritual.query.order_by(Ritual.title).all()
    customers = Customer.query.order_by(Customer.name).all()

    if request.method == 'POST':
        customer_id = request.form.get('customer_id', '').strip()
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip() or None

        if not customer_id or not title:
            flash('Customer and title are required.', 'error')
            return render_template('custom_rituals/new.html',
                                   rituals=rituals, customers=customers)

        ritual_id_raw = request.form.get('ritual_id', '').strip()
        ritual_id     = int(ritual_id_raw) if ritual_id_raw else None

        components   = _build_components(request.form)
        requirements = _build_requirements(request.form)

        crr = CustomRitualRequest(
            customer_id       = int(customer_id),
            ritual_id         = ritual_id,
            title             = title,
            description       = description,
            ritual_components = components,
            requirements      = requirements,
        )
        db.session.add(crr)
        db.session.commit()
        flash(f'Custom ritual request "{title}" created!', 'success')
        return redirect(url_for('custom_rituals.view_request', request_id=crr.id))

    return render_template('custom_rituals/new.html',
                           rituals=rituals, customers=customers)


# ─────────────────────────────────────────────────────────────────────────────
#  VIEW REQUEST
# ─────────────────────────────────────────────────────────────────────────────

@custom_rituals_bp.route('/<int:request_id>')
def view_request(request_id):
    crr       = CustomRitualRequest.query.get_or_404(request_id)
    rituals   = Ritual.query.order_by(Ritual.title).all()
    customers = Customer.query.order_by(Customer.name).all()
    return render_template('custom_rituals/view.html',
                           crr=crr, rituals=rituals, customers=customers)


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE REQUEST
# ─────────────────────────────────────────────────────────────────────────────

@custom_rituals_bp.route('/<int:request_id>/update', methods=['POST'])
def update_request(request_id):
    crr   = CustomRitualRequest.query.get_or_404(request_id)
    title = request.form.get('title', crr.title).strip()

    if not title:
        flash('Title is required.', 'error')
        return redirect(url_for('custom_rituals.view_request', request_id=request_id))

    ritual_id_raw = request.form.get('ritual_id', '').strip()
    crr.ritual_id         = int(ritual_id_raw) if ritual_id_raw else None
    crr.title             = title
    crr.description       = request.form.get('description', '').strip() or None
    crr.ritual_components = _build_components(request.form)
    crr.requirements      = _build_requirements(request.form)
    crr.updated_at        = datetime.utcnow()
    db.session.commit()
    flash('Custom ritual request updated!', 'success')
    return redirect(url_for('custom_rituals.view_request', request_id=request_id))


# ─────────────────────────────────────────────────────────────────────────────
#  ADD / UPDATE QUOTE
# ─────────────────────────────────────────────────────────────────────────────

@custom_rituals_bp.route('/<int:request_id>/quote', methods=['POST'])
def add_quote(request_id):
    crr = CustomRitualRequest.query.get_or_404(request_id)

    price_raw = request.form.get('quoted_price', '').strip()
    if not price_raw:
        flash('Quoted price is required.', 'error')
        return redirect(url_for('custom_rituals.view_request', request_id=request_id))
    try:
        crr.quoted_price = float(price_raw)
    except ValueError:
        flash('Invalid price value.', 'error')
        return redirect(url_for('custom_rituals.view_request', request_id=request_id))

    crr.quoted_breakdown = _build_breakdown(request.form)
    crr.quote_notes      = request.form.get('quote_notes', '').strip() or None
    crr.updated_at       = datetime.utcnow()
    db.session.commit()
    flash('Quote saved successfully!', 'success')
    return redirect(url_for('custom_rituals.view_request', request_id=request_id))


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE REQUEST
# ─────────────────────────────────────────────────────────────────────────────

@custom_rituals_bp.route('/<int:request_id>/delete', methods=['POST'])
def delete_request(request_id):
    crr = CustomRitualRequest.query.get_or_404(request_id)

    # Guard: do not delete if a booking is linked
    if crr.booking:
        flash('Cannot delete — a booking is linked to this request.', 'error')
        return redirect(url_for('custom_rituals.view_request', request_id=request_id))

    title = crr.title
    db.session.delete(crr)
    db.session.commit()
    flash(f'Custom ritual request "{title}" deleted.', 'warning')
    return redirect(url_for('custom_rituals.list_requests'))


# ─────────────────────────────────────────────────────────────────────────────
#  API — customer lookup (for the form)
# ─────────────────────────────────────────────────────────────────────────────

@custom_rituals_bp.route('/api/customer-search')
def api_customer_search():
    q = request.args.get('q', '').strip()
    customers = Customer.query.filter(
        db.or_(
            Customer.name.ilike(f'%{q}%'),
            Customer.email.ilike(f'%{q}%'),
        )
    ).limit(10).all()
    return jsonify([{
        'id':    c.id,
        'name':  c.name,
        'email': c.email,
        'mobile': c.contact_number or '',
    } for c in customers])