import os
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, Response)
from models import (Booking, Pandit, PanditDocument, PanditComplaint,
                    PanditPayout, PanditAddress, PanditPhoto, PanditPujaDetail,
                    ADDRESS_TYPES, PHOTO_TYPES, PANDIT_PAYOUT_STATUS,
                    PANDIT_VERIFICATION_STATUS, ACCOUNT_STATUS)
from enums import PanditVerificationStatus, AccountStatus, PanditPayoutStatus
from extensions import db
from datetime import datetime
from werkzeug.utils import secure_filename

admin_bp = Blueprint('admin', __name__)

ALLOWED_DOC    = {'pdf', 'png', 'jpg', 'jpeg'}
ALLOWED_IMG    = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
DOC_TYPES      = ['Aadhaar Card', 'PAN Card', 'Degree / Certificate', 'Photo']
PAYOUT_METHODS = ['UPI', 'Bank Transfer', 'Cash', 'Cheque']


def _rituals():
    from models import Ritual
    return Ritual.query.order_by(Ritual.title).all()


def _ritual_titles():
    return [r.title for r in _rituals()]


def _allowed_doc(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_DOC


def _allowed_img(fn):
    return '.' in fn and fn.rsplit('.', 1)[1].lower() in ALLOWED_IMG


# ─────────────────────────────────────────────────────────────────────────────
#  ASSIGN PANDIT TO BOOKING
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/assign-pandit/<int:booking_id>', methods=['POST'])
def assign_pandit(booking_id):
    booking   = Booking.query.get_or_404(booking_id)
    pandit_id = request.form.get('pandit_id')
    if not pandit_id:
        flash('Please select a Pandit.', 'error')
        return redirect(url_for('bookings.view_booking', booking_id=booking_id))
    pandit = Pandit.query.get(pandit_id)
    if not pandit:
        flash('Pandit not found.', 'error')
        return redirect(url_for('bookings.view_booking', booking_id=booking_id))
    booking.pandit_id  = pandit.id
    booking.updated_at = datetime.utcnow()
    db.session.commit()
    flash(f'Pandit {pandit.name} assigned!', 'success')
    return redirect(url_for('bookings.view_booking', booking_id=booking_id))


# ─────────────────────────────────────────────────────────────────────────────
#  PANDIT LIST
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits')
def pandits_list():
    city      = request.args.get('city', '')
    v_status  = request.args.get('verification_status', '')
    a_status  = request.args.get('account_status', '')
    min_rating = request.args.get('min_rating', '')

    q = Pandit.query
    if city:
        q = q.join(PanditAddress, Pandit.id == PanditAddress.pandit_id, isouter=True)\
             .filter(PanditAddress.city.ilike(f'%{city}%'))
    if v_status:   q = q.filter(Pandit.verification_status == v_status)
    if a_status:   q = q.filter(Pandit.account_status == a_status)
    if min_rating:
        try: q = q.filter(Pandit.rating >= float(min_rating))
        except ValueError: pass

    pandits = q.distinct().order_by(Pandit.name).all()
    cities  = [r[0] for r in db.session.query(PanditAddress.city).distinct().all() if r[0]]

    stats = {
        'total':     Pandit.query.count(),
        'verified':  Pandit.query.filter_by(
                        verification_status=PanditVerificationStatus.VERIFIED.value).count(),
        'pending':   Pandit.query.filter_by(
                        verification_status=PanditVerificationStatus.PENDING.value).count(),
        'active':    Pandit.query.filter_by(
                        account_status=AccountStatus.ACTIVE.value).count(),
        'suspended': Pandit.query.filter_by(
                        account_status=AccountStatus.SUSPENDED.value).count(),
    }
    return render_template('pandits/list.html',
                           pandits=pandits, cities=cities, stats=stats,
                           ritual_types=_ritual_titles(),
                           filters=dict(city=city, verification_status=v_status,
                                        account_status=a_status, min_rating=min_rating,
                                        ))


# ─────────────────────────────────────────────────────────────────────────────
#  NEW PANDIT
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/new', methods=['GET', 'POST'])
def new_pandit():
    if request.method == 'POST':
        name   = request.form.get('name', '').strip()
        mobile = request.form.get('mobile', '').strip()
        if not name or not mobile:
            flash('Name and mobile are required.', 'error')
            return render_template('pandits/new_pandit.html',
                                   address_types=ADDRESS_TYPES,
                                   photo_types=PHOTO_TYPES,
                                   ritual_types=_ritual_titles())

        pandit = Pandit(
            name           = name,
            mobile         = mobile,
            email          = request.form.get('email', '').strip() or None,
            experience_yrs = int(request.form.get('experience_yrs', 1) or 1),
            languages      = request.form.get('languages', '').strip(),
        )
        db.session.add(pandit)
        db.session.flush()

        street = request.form.get('street', '').strip()
        city   = request.form.get('city', '').strip()
        if street and city:
            db.session.add(PanditAddress(
                pandit_id      = pandit.id,
                reference_name = request.form.get('reference_name', 'Home').strip(),
                street         = street,
                city           = city,
                state          = request.form.get('state', '').strip(),
                zip_code       = request.form.get('zip_code', '').strip(),
                country        = request.form.get('country', 'India').strip(),
                address_type   = request.form.get('address_type', 'CURRENT'),
            ))

        photo_file = request.files.get('profile_photo')
        if photo_file and photo_file.filename and _allowed_img(photo_file.filename):
            db.session.add(PanditPhoto(
                pandit_id  = pandit.id,
                photo      = photo_file.read(),
                mimetype   = photo_file.mimetype or 'image/jpeg',
                file_name  = photo_file.filename,
                photo_type = 'PROFILE',
            ))

        db.session.commit()
        flash('Pandit registered! Add ritual details from the profile page.', 'success')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit.id))

    return render_template('pandits/new_pandit.html',
                           address_types=ADDRESS_TYPES,
                           photo_types=PHOTO_TYPES,
                           ritual_types=_ritual_titles())


# ─────────────────────────────────────────────────────────────────────────────
#  VIEW PANDIT
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>')
def view_pandit(pandit_id):
    pandit   = Pandit.query.get_or_404(pandit_id)
    bookings = Booking.query.filter_by(pandit_id=pandit_id)\
                            .order_by(Booking.booking_slot.desc()).all()
    all_rituals = _rituals()
    return render_template('pandits/view_pandit.html',
                           pandit=pandit, bookings=bookings,
                           rituals=all_rituals,
                           doc_types=DOC_TYPES,
                           payout_methods=PAYOUT_METHODS,
                           address_types=ADDRESS_TYPES,
                           photo_types=PHOTO_TYPES,
                           ritual_types=_ritual_titles(),
                           payout_statuses=PANDIT_PAYOUT_STATUS)


# ─────────────────────────────────────────────────────────────────────────────
#  SERVE PANDIT PHOTO
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/photo/<int:photo_id>')
def serve_photo(photo_id):
    ph = PanditPhoto.query.get_or_404(photo_id)
    return Response(ph.photo, mimetype=ph.mimetype)


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE PANDIT
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/update', methods=['POST'])
def update_pandit(pandit_id):
    p = Pandit.query.get_or_404(pandit_id)
    p.name           = request.form.get('name', p.name).strip()
    p.mobile         = request.form.get('mobile', p.mobile).strip()
    p.email          = request.form.get('email', '').strip() or None
    p.experience_yrs = int(request.form.get('experience_yrs', 1) or 1)
    p.languages      = request.form.get('languages', '').strip()
    p.is_available   = request.form.get('is_available') == '1'
    p.bank_name         = request.form.get('bank_name', '').strip() or None
    p.bank_account_no   = request.form.get('bank_account_no', '').strip() or None
    p.bank_ifsc         = request.form.get('bank_ifsc', '').strip() or None
    p.bank_account_name = request.form.get('bank_account_name', '').strip() or None
    p.upi_id            = request.form.get('upi_id', '').strip() or None
    p.updated_at        = datetime.utcnow()
    db.session.commit()
    flash('Pandit details updated!', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  PANDIT PUJA DETAIL — ADD
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/puja-detail/add', methods=['POST'])
def add_puja_detail(pandit_id):
    pandit    = Pandit.query.get_or_404(pandit_id)
    ritual_id = request.form.get('ritual_id', '').strip()
    if not ritual_id:
        flash('Please select a ritual.', 'error')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))

    try:
        total_fees = float(request.form.get('total_fees', 0) or 0)
        variant    = int(request.form.get('variant', 1) or 1)
    except ValueError:
        flash('Invalid fees or variant value.', 'error')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))

    # fees_breakup: nested dict {dakshina:{amount,currency}, chadhava:{...}, transportation:{...}}
    fees_breakup = {}
    for key in ['dakshina', 'chadhava', 'transportation']:
        raw = request.form.get(f'fb_{key}', '').strip()
        if raw:
            try:
                fees_breakup[key] = {'amount': float(raw), 'currency': 'INR'}
            except ValueError:
                pass

    # variant_detail: ritual_metadata from selected RitualDetail
    ritual_detail_id = request.form.get('ritual_detail_id', '').strip()
    variant_detail   = {}
    if ritual_detail_id:
        from models import RitualDetail
        rd = RitualDetail.query.get(int(ritual_detail_id))
        if rd and rd.ritual_metadata and isinstance(rd.ritual_metadata, dict):
            variant_detail = rd.ritual_metadata

    db.session.add(PanditPujaDetail(
        pandit_id       = pandit.id,
        ritual_id       = int(ritual_id),
        variant         = variant,
        variant_detail  = variant_detail,
        min_num_pandits = int(request.form.get('min_num_pandits', 1) or 1),
        duration        = request.form.get('duration', '').strip(),
        total_fees      = total_fees,
        fees_breakup    = fees_breakup,
    ))
    db.session.commit()
    flash('Puja detail added!', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  PANDIT PUJA DETAIL — UPDATE
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/puja-detail/<int:detail_id>/update', methods=['POST'])
def update_puja_detail(pandit_id, detail_id):
    detail = PanditPujaDetail.query.get_or_404(detail_id)
    try:
        detail.total_fees      = float(request.form.get('total_fees', detail.total_fees))
        detail.variant         = int(request.form.get('variant', detail.variant))
        detail.min_num_pandits = int(request.form.get('min_num_pandits', detail.min_num_pandits) or 1)
    except ValueError:
        flash('Invalid numeric value.', 'error')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))

    detail.duration = request.form.get('duration', '').strip()

    ritual_detail_id = request.form.get('ritual_detail_id', '').strip()
    if ritual_detail_id:
        from models import RitualDetail
        rd = RitualDetail.query.get(int(ritual_detail_id))
        if rd and rd.ritual_metadata and isinstance(rd.ritual_metadata, dict):
            detail.variant_detail = rd.ritual_metadata
        else:
            detail.variant_detail = {}

    fees_breakup = {}
    for key in ['dakshina', 'chadhava', 'transportation']:
        raw = request.form.get(f'fb_{key}', '').strip()
        if raw:
            try:
                fees_breakup[key] = {'amount': float(raw), 'currency': 'INR'}
            except ValueError:
                pass
    detail.fees_breakup = fees_breakup
    detail.updated_at   = datetime.utcnow()
    db.session.commit()
    flash('Puja detail updated!', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  PANDIT PUJA DETAIL — DELETE
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/puja-detail/<int:detail_id>/delete', methods=['POST'])
def delete_puja_detail(pandit_id, detail_id):
    detail = PanditPujaDetail.query.get_or_404(detail_id)
    db.session.delete(detail)
    db.session.commit()
    flash('Puja detail deleted.', 'warning')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  ADDRESS — ADD / UPDATE / DELETE
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/address/add', methods=['POST'])
def add_address(pandit_id):
    p      = Pandit.query.get_or_404(pandit_id)
    street = request.form.get('street', '').strip()
    city   = request.form.get('city', '').strip()
    state  = request.form.get('state', '').strip()
    zip_code = request.form.get('zip_code', '').strip()
    if not all([street, city, state, zip_code]):
        flash('Street, city, state and zip code are required.', 'error')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))
    db.session.add(PanditAddress(
        pandit_id      = p.id,
        reference_name = request.form.get('reference_name', 'Home').strip(),
        street=street, city=city, state=state, zip_code=zip_code,
        country  = request.form.get('country', 'India').strip(),
        address_type = request.form.get('address_type', 'CURRENT'),
    ))
    db.session.commit()
    flash('Address added!', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


@admin_bp.route('/pandits/<int:pandit_id>/address/<int:addr_id>/update', methods=['POST'])
def update_address(pandit_id, addr_id):
    addr = PanditAddress.query.get_or_404(addr_id)
    addr.reference_name = request.form.get('reference_name', addr.reference_name).strip()
    addr.street         = request.form.get('street', addr.street).strip()
    addr.city           = request.form.get('city', addr.city).strip()
    addr.state          = request.form.get('state', addr.state).strip()
    addr.zip_code       = request.form.get('zip_code', addr.zip_code).strip()
    addr.country        = request.form.get('country', addr.country).strip()
    addr.address_type   = request.form.get('address_type', addr.address_type)
    addr.updated_at     = datetime.utcnow()
    db.session.commit()
    flash('Address updated!', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


@admin_bp.route('/pandits/<int:pandit_id>/address/<int:addr_id>/delete', methods=['POST'])
def delete_address(pandit_id, addr_id):
    addr = PanditAddress.query.get_or_404(addr_id)
    db.session.delete(addr)
    db.session.commit()
    flash('Address deleted.', 'warning')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  PHOTO — ADD / DELETE
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/photo/add', methods=['POST'])
def add_photo(pandit_id):
    p          = Pandit.query.get_or_404(pandit_id)
    photo_type = request.form.get('photo_type', 'PROFILE')
    added      = 0
    for f in request.files.getlist('photos'):
        if f and f.filename and _allowed_img(f.filename):
            db.session.add(PanditPhoto(
                pandit_id=p.id, photo=f.read(),
                mimetype=f.mimetype or 'image/jpeg',
                file_name=f.filename, photo_type=photo_type,
            ))
            added += 1
    if added:
        db.session.commit()
        flash(f'{added} photo(s) uploaded!', 'success')
    else:
        flash('No valid image files. Allowed: PNG, JPG, WEBP.', 'error')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


@admin_bp.route('/pandits/<int:pandit_id>/photo/<int:photo_id>/delete', methods=['POST'])
def delete_photo(pandit_id, photo_id):
    ph = PanditPhoto.query.get_or_404(photo_id)
    db.session.delete(ph)
    db.session.commit()
    flash('Photo deleted.', 'warning')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  VERIFY / REJECT
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/verify', methods=['POST'])
def verify_pandit(pandit_id):
    p      = Pandit.query.get_or_404(pandit_id)
    action = request.form.get('action')
    reason = request.form.get('reason', '').strip()
    if action == 'approve':
        p.verification_status = PanditVerificationStatus.VERIFIED.value
        p.rejection_reason    = None
        flash(f'{p.name} approved!', 'success')
    elif action == 'reject':
        if not reason:
            flash('Rejection reason required.', 'error')
            return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))
        p.verification_status = PanditVerificationStatus.REJECTED.value
        p.rejection_reason    = reason
        flash(f'{p.name} rejected.', 'warning')
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  SET ACCOUNT STATUS
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/set-status', methods=['POST'])
def set_pandit_status(pandit_id):
    p      = Pandit.query.get_or_404(pandit_id)
    action = request.form.get('action')
    reason = request.form.get('reason', '').strip()
    if action == 'activate':
        p.account_status    = AccountStatus.ACTIVE.value
        p.is_available      = True
        p.suspension_reason = None
        flash(f'{p.name} activated.', 'success')
    elif action == 'deactivate':
        p.account_status = AccountStatus.INACTIVE.value
        p.is_available   = False
        flash(f'{p.name} deactivated.', 'warning')
    elif action == 'suspend':
        if not reason:
            flash('Suspension reason required.', 'error')
            return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))
        p.account_status    = AccountStatus.SUSPENDED.value
        p.is_available      = False
        p.suspension_reason = reason
        flash(f'{p.name} suspended.', 'error')
    p.updated_at = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  UPLOAD DOCUMENT
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/upload-doc', methods=['POST'])
def upload_document(pandit_id):
    p = Pandit.query.get_or_404(pandit_id)
    if 'document' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))
    file     = request.files['document']
    doc_type = request.form.get('doc_type', '').strip()
    notes    = request.form.get('doc_notes', '').strip()
    if not file.filename or not _allowed_doc(file.filename):
        flash('Invalid file. Allowed: PDF, PNG, JPG.', 'error')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'pandit_docs')
    os.makedirs(upload_folder, exist_ok=True)
    ts       = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    filename = secure_filename(f'pandit_{pandit_id}_{ts}_{file.filename}')
    file.save(os.path.join(upload_folder, filename))
    db.session.add(PanditDocument(pandit_id=p.id, doc_type=doc_type, filename=filename, notes=notes))
    db.session.commit()
    flash(f'{doc_type} uploaded!', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


@admin_bp.route('/pandits/<int:pandit_id>/docs/<int:doc_id>/toggle', methods=['POST'])
def toggle_document(pandit_id, doc_id):
    doc = PanditDocument.query.get_or_404(doc_id)
    doc.is_verified = not doc.is_verified
    db.session.commit()
    flash(f'Document {"verified" if doc.is_verified else "unverified"}.', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  COMPLAINT
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/complaint', methods=['POST'])
def add_complaint(pandit_id):
    p = Pandit.query.get_or_404(pandit_id)
    subject     = request.form.get('subject', '').strip()
    description = request.form.get('description', '').strip()
    if not subject or not description:
        flash('Subject and description required.', 'error')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))
    db.session.add(PanditComplaint(
        pandit_id=p.id, subject=subject, description=description,
        raised_by=request.form.get('raised_by', 'Admin').strip(),
        booking_id=request.form.get('booking_id') or None
    ))
    db.session.commit()
    flash('Complaint logged.', 'warning')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


@admin_bp.route('/pandits/<int:pandit_id>/complaint/<int:cid>/resolve', methods=['POST'])
def resolve_complaint(pandit_id, cid):
    c = PanditComplaint.query.get_or_404(cid)
    c.status     = request.form.get('status', 'Resolved')
    c.resolution = request.form.get('resolution', '').strip()
    db.session.commit()
    flash('Complaint updated.', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))


# ─────────────────────────────────────────────────────────────────────────────
#  PAYOUT
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/payout', methods=['POST'])
def record_payout(pandit_id):
    p = Pandit.query.get_or_404(pandit_id)
    try:
        amount = float(request.form.get('amount', 0))
        if amount <= 0: raise ValueError
    except ValueError:
        flash('Invalid amount.', 'error')
        return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))

    db.session.add(PanditPayout(
        pandit_id = p.id,
        amount    = amount,
        method    = request.form.get('method', ''),
        reference = request.form.get('reference', '').strip(),
        notes     = request.form.get('notes', '').strip(),
        status    = PanditPayoutStatus.COMPLETED.value,
        paid_at   = datetime.utcnow(),
    ))
    if p.total_earnings is None:
        p.total_earnings = 0
    p.total_earnings += amount
    db.session.commit()
    flash(f'Payout of ₹{amount:,.0f} recorded.', 'success')
    return redirect(url_for('admin.view_pandit', pandit_id=pandit_id))




# ─────────────────────────────────────────────────────────────────────────────
#  TOGGLE AVAILABILITY
# ─────────────────────────────────────────────────────────────────────────────
@admin_bp.route('/pandits/<int:pandit_id>/toggle', methods=['POST'])
def toggle_pandit(pandit_id):
    p = Pandit.query.get_or_404(pandit_id)
    p.is_available = not p.is_available
    db.session.commit()
    flash(f'Pandit {"available" if p.is_available else "unavailable"}.', 'success')
    return redirect(url_for('admin.pandits_list'))
