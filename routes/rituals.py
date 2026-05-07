import json
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify, Response)
from models import Ritual, RitualDetail, RitualImage, RitualPackage, RITUAL_MODES
from enums import RitualPackageType
from extensions import db
from datetime import datetime

rituals_bp = Blueprint('rituals', __name__)

ALLOWED_IMG       = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
REQUIRED_PACKAGES = [RitualPackageType.STANDARD.value, RitualPackageType.COMPLETE.value]


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def allowed_image(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMG


def _parse_samagri(raw):
    """
    Convert a comma-separated multiline string into a list of dictionaries.
    Example input:
    Kalash,1
    Red thread / Kalava,1 roll
    Rice (Akshata),300 gm
    """
    result = []
    for line in raw.strip().splitlines():
        line = line.strip()

        # Skip empty lines
        if not line:
            continue

        # Split only on the first comma
        parts = line.split(",", 1)

        if len(parts) != 2:
            continue

        item = parts[0].strip()
        qty = parts[1].strip()

        result.append({
            "item": item,
            "qty": qty
        })

    return result



def _parse_vidhi(raw):
    """Textarea (one step per line) → list of strings for ARRAY(String)."""
    if not raw:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _parse_included(raw):
    """Comma-separated text → list of strings for ARRAY(String)."""
    if not raw:
        return []
    return [i.strip() for i in raw.split(',') if i.strip()]


def _parse_metadata(raw):
    """Accepts JSON dict string or plain text → dict."""
    if not raw or not raw.strip():
        return {}
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, ValueError):
        pass
    return {'notes': raw}


def _ensure_packages(detail):
    """Guarantee STANDARD and COMPLETE rows exist for a given RitualDetail."""
    existing = {p.package_type for p in detail.packages}
    for ptype in REQUIRED_PACKAGES:
        if ptype not in existing:
            db.session.add(RitualPackage(
                ritual_detail_id=detail.id,
                package_type=ptype,
                price=0.0,
                included=[],
                not_included=[],
            ))


def _get_pkg_included(pkg):
    if not pkg.included:
        return []
    if isinstance(pkg.included, list):
        return pkg.included
    return [i.strip() for i in pkg.included.split(',') if i.strip()]


def _get_pkg_not_included(pkg):
    if not pkg.not_included:
        return []
    if isinstance(pkg.not_included, list):
        return pkg.not_included
    return [i.strip() for i in pkg.not_included.split(',') if i.strip()]


def _build_detail_from_form(form, ritual_id):
    """Build a RitualDetail from POST form data (not yet flushed)."""
    return RitualDetail(
        ritual_id       = ritual_id,
        puja_vidhi      = _parse_vidhi(form.get('puja_vidhi', '')),
        puja_samagri    = _parse_samagri(form.get('puja_samagri', '')),
        puja_seasons    = form.get('puja_seasons', '').strip(),
        num_pundits     = int(form.get('num_pundits', 1) or 1),
        duration        = form.get('duration', '').strip(),
        mode            = form.get('mode', 'OFFLINE'),
        ritual_metadata = _parse_metadata(form.get('ritual_metadata', '')),
    )


def _add_packages_from_form(form, detail_id):
    """Add STANDARD + COMPLETE packages from POST form data."""
    for ptype in REQUIRED_PACKAGES:
        key = ptype.lower()   # 'standard' or 'complete'
        try:
            price = float(form.get(f'{key}_price', 0) or 0)
        except ValueError:
            price = 0.0
        db.session.add(RitualPackage(
            ritual_detail_id = detail_id,
            package_type     = ptype,
            description      = form.get(f'{key}_description', '').strip(),
            included         = _parse_included(form.get(f'{key}_included', '')),
            not_included     = _parse_included(form.get(f'{key}_not_included', '')),
            price            = price,
        ))


# ─────────────────────────────────────────────────────────────────────────────
#  LIST
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/')
def ritual_list():
    search = request.args.get('search', '').strip()
    mode   = request.args.get('mode', '')

    q = Ritual.query
    if search:
        q = q.filter(Ritual.title.ilike(f'%{search}%'))
    if mode:
        q = q.join(RitualDetail).filter(RitualDetail.mode == mode)

    rituals = q.order_by(Ritual.title).all()
    stats = {
        'total':    Ritual.query.count(),
        'packages': RitualPackage.query.count(),
        'details':  RitualDetail.query.count(),
    }
    return render_template('rituals/ritual_list.html',
                           rituals=rituals, stats=stats,
                           ritual_modes=RITUAL_MODES,
                           filters=dict(search=search, mode=mode))


# ─────────────────────────────────────────────────────────────────────────────
#  NEW RITUAL  (ritual + first detail + 2 packages)
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/new', methods=['GET', 'POST'])
def new_ritual():
    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()

        if not title or not description:
            flash('Ritual title and description are required.', 'error')
            return render_template('rituals/new_ritual.html', ritual_modes=RITUAL_MODES)

        if Ritual.query.filter_by(title=title).first():
            flash(f'A ritual named "{title}" already exists.', 'error')
            return render_template('rituals/new_ritual.html', ritual_modes=RITUAL_MODES)

        ritual = Ritual(title=title, description=description)
        db.session.add(ritual)
        db.session.flush()

        detail = _build_detail_from_form(request.form, ritual.id)
        db.session.add(detail)
        db.session.flush()

        _add_packages_from_form(request.form, detail.id)

        for img_file in request.files.getlist('images'):
            if img_file and img_file.filename and allowed_image(img_file.filename):
                db.session.add(RitualImage(
                    ritual_id=ritual.id,
                    file_name=img_file.filename,
                    mimetype=img_file.mimetype or 'image/jpeg',
                    data=img_file.read(),
                ))

        db.session.commit()
        flash(f'Ritual "{ritual.title}" created!', 'success')
        return redirect(url_for('rituals.view_ritual', ritual_id=ritual.id))

    return render_template('rituals/new_ritual.html', ritual_modes=RITUAL_MODES)


# ─────────────────────────────────────────────────────────────────────────────
#  VIEW RITUAL
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>')
def view_ritual(ritual_id):
    ritual = Ritual.query.get_or_404(ritual_id)
    # Ensure every detail has both package types
    for d in ritual.details:
        _ensure_packages(d)
    if ritual.details:
        db.session.commit()
    return render_template('rituals/view_ritual.html',
                           ritual=ritual,
                           ritual_modes=RITUAL_MODES,
                           required_packages=REQUIRED_PACKAGES)


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE RITUAL (title + description only)
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>/update', methods=['POST'])
def update_ritual(ritual_id):
    ritual = Ritual.query.get_or_404(ritual_id)
    ritual.title       = request.form.get('title', ritual.title).strip()
    ritual.description = request.form.get('description', ritual.description).strip()
    ritual.updated_at  = datetime.utcnow()
    # ── CHANGE: Also update puja_vidhi/samagri (shared fields) across all details.
    # This allows the Edit Ritual modal to serve as the single place to manage
    # the ritual title, description AND shared puja information in one save action.
    raw_vidhi   = request.form.get('puja_vidhi', '').strip()
    raw_samagri = request.form.get('puja_samagri', '').strip()
    if raw_vidhi or raw_samagri:
        puja_vidhi   = _parse_vidhi(raw_vidhi)   if raw_vidhi   else None
        puja_samagri = _parse_samagri(raw_samagri) if raw_samagri else None
        for d in ritual.details:
            if puja_vidhi   is not None:
                d.puja_vidhi   = puja_vidhi
            if puja_samagri is not None:
                d.puja_samagri = puja_samagri
            d.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f'"{ritual.title}" updated!', 'success')
    return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))


# ─────────────────────────────────────────────────────────────────────────────
#  ADD RITUAL DETAIL  (adds a new detail + 2 packages)
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>/detail/add', methods=['POST'])
def add_detail(ritual_id):
    ritual = Ritual.query.get_or_404(ritual_id)
    detail = _build_detail_from_form(request.form, ritual.id)
    # ── CHANGE: puja_vidhi and puja_samagri are SHARED across all variants.
    # Copy them from the first existing detail so they auto-propagate
    # without the admin needing to re-enter them in the Add Detail modal.
    if ritual.details:
        source = ritual.details[0]
        detail.puja_vidhi   = source.puja_vidhi
        detail.puja_samagri = source.puja_samagri
    db.session.add(detail)
    db.session.flush()
    _add_packages_from_form(request.form, detail.id)
    db.session.commit()
    flash('New ritual detail added with Standard & Complete packages!', 'success')
    return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE RITUAL DETAIL  (edit one specific detail by its id)
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>/detail/<int:detail_id>/update', methods=['POST'])
def update_detail(ritual_id, detail_id):
    detail = RitualDetail.query.get_or_404(detail_id)
    detail.puja_vidhi      = _parse_vidhi(request.form.get('puja_vidhi', ''))
    detail.puja_samagri    = _parse_samagri(request.form.get('puja_samagri', ''))
    detail.puja_seasons    = request.form.get('puja_seasons', '').strip()
    detail.num_pundits     = int(request.form.get('num_pundits', detail.num_pundits) or 1)
    detail.duration        = request.form.get('duration', '').strip()
    detail.mode            = request.form.get('mode', detail.mode)
    detail.ritual_metadata = _parse_metadata(request.form.get('ritual_metadata', ''))
    detail.updated_at      = datetime.utcnow()
    db.session.commit()
    flash('Ritual detail updated!', 'success')
    return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE RITUAL DETAIL  (at least one must remain)
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>/detail/<int:detail_id>/delete', methods=['POST'])
def delete_detail(ritual_id, detail_id):
    ritual = Ritual.query.get_or_404(ritual_id)
    if len(ritual.details) <= 1:
        flash('Cannot delete the only detail — a ritual must have at least one.', 'error')
        return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))
    detail = RitualDetail.query.get_or_404(detail_id)
    db.session.delete(detail)
    db.session.commit()
    flash('Ritual detail deleted.', 'warning')
    return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE SHARED INFO (puja_vidhi + puja_samagri — synced to ALL details)
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>/update-shared-info', methods=['POST'])
def update_shared_info(ritual_id):
    ritual       = Ritual.query.get_or_404(ritual_id)
    puja_vidhi   = _parse_vidhi(request.form.get('puja_vidhi', ''))
    puja_samagri = _parse_samagri(request.form.get('puja_samagri', ''))
    for d in ritual.details:
        d.puja_vidhi   = puja_vidhi
        d.puja_samagri = puja_samagri
        d.updated_at   = datetime.utcnow()
    db.session.commit()
    flash('Shared puja information updated across all detail variants!', 'success')
    return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE RITUAL
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>/delete', methods=['POST'])
def delete_ritual(ritual_id):
    ritual = Ritual.query.get_or_404(ritual_id)
    title  = ritual.title
    db.session.delete(ritual)
    db.session.commit()
    flash(f'Ritual "{title}" deleted.', 'warning')
    return redirect(url_for('rituals.ritual_list'))


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE PACKAGE
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>/package/<int:pkg_id>/update', methods=['POST'])
def update_package(ritual_id, pkg_id):
    pkg = RitualPackage.query.get_or_404(pkg_id)
    try:
        pkg.price = float(request.form.get('price', pkg.price) or pkg.price)
    except ValueError:
        pass
    pkg.description  = request.form.get('description', '').strip()
    pkg.included     = _parse_included(request.form.get('included', ''))
    pkg.not_included = _parse_included(request.form.get('not_included', ''))
    pkg.updated_at   = datetime.utcnow()
    db.session.commit()
    flash(f'{pkg.package_type} package updated!', 'success')
    return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))


# ─────────────────────────────────────────────────────────────────────────────
#  ADD / DELETE IMAGE
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/<int:ritual_id>/image/add', methods=['POST'])
def add_image(ritual_id):
    ritual = Ritual.query.get_or_404(ritual_id)
    added  = 0
    for img_file in request.files.getlist('images'):
        if img_file and img_file.filename and allowed_image(img_file.filename):
            db.session.add(RitualImage(
                ritual_id=ritual.id,
                file_name=img_file.filename,
                mimetype=img_file.mimetype or 'image/jpeg',
                data=img_file.read(),
            ))
            added += 1
    db.session.commit()
    flash(f'{added} image(s) uploaded!', 'success')
    return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))


@rituals_bp.route('/<int:ritual_id>/image/<int:img_id>/delete', methods=['POST'])
def delete_image(ritual_id, img_id):
    img = RitualImage.query.get_or_404(img_id)
    db.session.delete(img)
    db.session.commit()
    flash('Image deleted.', 'warning')
    return redirect(url_for('rituals.view_ritual', ritual_id=ritual_id))


# ─────────────────────────────────────────────────────────────────────────────
#  SERVE IMAGE
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/image/<int:img_id>')
def serve_image(img_id):
    img = RitualImage.query.get_or_404(img_id)
    return Response(img.data, mimetype=img.mimetype)


# ─────────────────────────────────────────────────────────────────────────────
#  API — packages for booking form (all details, flat list)
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/api/packages/<int:ritual_id>')
def api_packages(ritual_id):
    ritual = Ritual.query.get_or_404(ritual_id)
    if not ritual.details:
        return jsonify({'packages': []})

    all_packages = []
    for detail in ritual.details:
        meta_label = ''
        if detail.ritual_metadata and isinstance(detail.ritual_metadata, dict):
            meta_label = ', '.join(f'{k}: {v}' for k, v in detail.ritual_metadata.items())

        ordered = sorted(
            detail.packages,
            key=lambda p: REQUIRED_PACKAGES.index(p.package_type)
                          if p.package_type in REQUIRED_PACKAGES else 99
        )
        for p in ordered:
            all_packages.append({
                'id':           p.id,
                'detail_id':    detail.id,
                'meta_label':   meta_label,
                'package_type': p.package_type,
                'description':  p.description or '',
                'price':        p.price,
                'token_amount': p.token_amount,
                'included':     _get_pkg_included(p),
                'not_included': _get_pkg_not_included(p),
            })

    return jsonify({'packages': all_packages})


# ─────────────────────────────────────────────────────────────────────────────
#  API — search rituals
# ─────────────────────────────────────────────────────────────────────────────

@rituals_bp.route('/api/search')
def api_search():
    q      = request.args.get('q', '').strip()
    result = Ritual.query.filter(Ritual.title.ilike(f'%{q}%')).limit(10).all()
    return jsonify([{'id': r.id, 'title': r.title, 'min_price': r.min_price}
                    for r in result])
