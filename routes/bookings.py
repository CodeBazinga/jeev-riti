from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, jsonify)
from models import (Booking, Customer, CustomerAddress, CheckoutItem,
                    Pandit, Ritual, RitualPackage, CustomRitualRequest)
from enums import BookingSource, BookingStatus, CheckoutStatus, PaymentStatus
from extensions import db
from datetime import datetime

bookings_bp = Blueprint('bookings', __name__)


# ─────────────────────────────────────────────────────────────────────────────
#  BOOKING POLICY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

RESCHEDULE_LIMIT       = 2          # max reschedules per booking
RESCHEDULE_CUTOFF_HRS  = 48         # no reschedule within this many hours of slot
CANCEL_CUTOFF_HRS      = 48         # no cancellation within this many hours of slot


def _hours_until_slot(booking):
    """Return float hours from now until booking_slot. Negative if slot is past."""
    if not booking.booking_slot:
        return float('inf')
    # booking_slot may be timezone-aware (PostgreSQL TIMESTAMPTZ) — normalise to naive UTC
    slot = booking.booking_slot
    if hasattr(slot, 'tzinfo') and slot.tzinfo is not None:
        slot = slot.replace(tzinfo=None)
    return (slot - datetime.utcnow()).total_seconds() / 3600


def _parse_reschedule_count(booking):
    """
    Extract the reschedule count from reschedule_reason without a new DB column.
    Format stored: "[R:N] reason text"
    Prefixes [SLOT UPDATE] and [RITUAL EDIT] do NOT count as customer reschedules.
    """
    reason = booking.reschedule_reason or ''
    if reason.startswith('[R:'):
        try:
            return int(reason[3:reason.index(']')])
        except (ValueError, IndexError):
            pass
    # Legacy plain-text reschedule (no prefix) counts as 1
    if reason and not reason.startswith('[SLOT UPDATE]') and not reason.startswith('[RITUAL EDIT]'):
        return 1
    return 0


def _encode_reschedule_reason(count, reason):
    """Store count + reason together so no extra column is needed."""
    return f'[R:{count}] {reason}'


def _can_reschedule(booking):
    """
    Returns (allowed: bool, reason: str).
    Two checks:
      1. Reschedule count < RESCHEDULE_LIMIT
      2. More than RESCHEDULE_CUTOFF_HRS hours until the slot
    """
    count = _parse_reschedule_count(booking)
    if count >= RESCHEDULE_LIMIT:
        return False, f'Maximum {RESCHEDULE_LIMIT} reschedules already used for this booking.'
    hours_left = _hours_until_slot(booking)
    if hours_left < RESCHEDULE_CUTOFF_HRS:
        if hours_left < 0:
            return False, 'The ritual slot is already past — rescheduling not allowed.'
        return False, (
            f'Rescheduling is not allowed within {RESCHEDULE_CUTOFF_HRS} hours of the ritual. '
            f'Only {hours_left:.0f} hour(s) remaining.'
        )
    return True, ''


def _can_cancel(booking):
    """
    Returns (allowed: bool, reason: str).
    Cancellation is blocked within CANCEL_CUTOFF_HRS hours of the slot.
    """
    hours_left = _hours_until_slot(booking)
    if hours_left < CANCEL_CUTOFF_HRS:
        if hours_left < 0:
            return False, 'The ritual slot is already past — cancellation not allowed.'
        return False, (
            f'Cancellation is not allowed within {CANCEL_CUTOFF_HRS} hours of the ritual. '
            f'Only {hours_left:.0f} hour(s) remaining.'
        )
    return True, ''


# ─────────────────────────────────────────────────────────────────────────────
#  BOOKING ROUTE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _build_ritual_snapshot(package):
    return {
        'title':        package.ritual_title,
        'package_type': package.package_type,
        'price':        package.price,
        'token_amount': package.token_amount,
        'description':  package.description or '',
    }


def _build_custom_snapshot(crr):
    """Build a ritual_snapshot dict from a CustomRitualRequest."""
    return {
        'title':        crr.title,
        'package_type': 'CUSTOM',
        'price':        crr.quoted_price or 0.0,
        'token_amount': round((crr.quoted_price or 0.0) * 0.20, 2),
        'description':  crr.description or '',
        'custom_request_id': crr.id,
        'components': crr.ritual_components or [],
    }


def _build_address_snapshot(addr):
    if not addr:
        return {}
    return {
        'reference_name': addr.reference_name,
        'street':   addr.street,
        'city':     addr.city,
        'state':    addr.state,
        'zip_code': addr.zip_code,
        'country':  addr.country,
    }


def _booking_sources():
    return [s.value for s in BookingSource]


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


# ─────────────────────────────────────────────────────────────────────────────
#  API — custom ritual requests for a customer (unbooked, quoted only)
# ─────────────────────────────────────────────────────────────────────────────

@bookings_bp.route('/api/customer-custom-rituals/<int:customer_id>')
def api_customer_custom_rituals(customer_id):
    """
    Returns CustomRitualRequests for a customer that:
    - are quoted (quoted_price is not None)
    - do NOT yet have a linked booking
    """
    requests = CustomRitualRequest.query.filter_by(
        customer_id=customer_id
    ).filter(
        CustomRitualRequest.quoted_price.isnot(None),   # must have a quote
        ~CustomRitualRequest.booking.has()              # no booking yet
    ).order_by(CustomRitualRequest.created_at.desc()).all()

    return jsonify({'custom_rituals': [
        {
            'id':               crr.id,
            'title':            crr.title,
            'description':      crr.description or '',
            'quoted_price':     crr.quoted_price,
            'token_amount':     round(crr.quoted_price * 0.20, 2),
            'component_count':  crr.component_count,
            'components':       crr.ritual_components or [],
            'quoted_breakdown': crr.quoted_breakdown or {},
            'quote_notes':      crr.quote_notes or '',
            'requirements':     crr.requirements or {},
        }
        for crr in requests
    ]})


# ─────────────────────────────────────────────────────────────────────────────
#  NEW BOOKING
# ─────────────────────────────────────────────────────────────────────────────

@bookings_bp.route('/new', methods=['GET', 'POST'])
def new_booking():
    rituals = Ritual.query.order_by(Ritual.title).all()

    if request.method == 'POST':
        customer_id      = request.form.get('customer_id', '').strip()
        address_id       = request.form.get('address_id', '').strip()
        booking_date_str = request.form.get('booking_date', '')
        booking_time_str = request.form.get('booking_time', '')
        notes            = request.form.get('notes', '').strip()
        booking_source   = request.form.get('booking_source', BookingSource.ADMIN.value)
        booking_type     = request.form.get('booking_type', 'standard')  # 'standard' or 'custom'

        # ── Validate customer ─────────────────────────────────────────────────
        if not customer_id:
            flash('Please select a registered customer.', 'error')
            return render_template('bookings/new_booking.html', rituals=rituals,
                                   booking_sources=_booking_sources())

        customer = Customer.query.get(customer_id)
        if not customer:
            flash('Customer not found.', 'error')
            return render_template('bookings/new_booking.html', rituals=rituals,
                                   booking_sources=_booking_sources())

        # ── Validate date/time ────────────────────────────────────────────────
        try:
            bdate        = datetime.strptime(booking_date_str, '%Y-%m-%d').date()
            btime        = datetime.strptime(booking_time_str, '%H:%M').time()
            booking_slot = datetime.combine(bdate, btime)
        except ValueError:
            flash('Invalid date or time.', 'error')
            return render_template('bookings/new_booking.html', rituals=rituals,
                                   booking_sources=_booking_sources())

        addr_id = int(address_id) if address_id else None
        addr    = CustomerAddress.query.get(addr_id) if addr_id else None

        # ══════════════════════════════════════════════════════════════════════
        #  PATH A — CUSTOM RITUAL REQUEST BOOKING
        # ══════════════════════════════════════════════════════════════════════
        if booking_type == 'custom':
            crr_id_raw = request.form.get('custom_ritual_request_id', '').strip()
            if not crr_id_raw:
                flash('Please select a custom ritual request.', 'error')
                return render_template('bookings/new_booking.html', rituals=rituals,
                                       booking_sources=_booking_sources())

            crr = CustomRitualRequest.query.get(int(crr_id_raw))
            if not crr or crr.customer_id != int(customer_id):
                flash('Invalid custom ritual request.', 'error')
                return render_template('bookings/new_booking.html', rituals=rituals,
                                       booking_sources=_booking_sources())

            if crr.quoted_price is None:
                flash('This custom ritual has no quote yet. Please add a quote first.', 'error')
                return render_template('bookings/new_booking.html', rituals=rituals,
                                       booking_sources=_booking_sources())

            if crr.booking:
                flash('A booking already exists for this custom ritual request.', 'error')
                return render_template('bookings/new_booking.html', rituals=rituals,
                                       booking_sources=_booking_sources())

            total = crr.quoted_price

            # CheckoutItem for custom request — no ritual_package_id
            # checkout = CheckoutItem(
            #     ritual_package_id     = None,
            #     customer_id           = customer.id,
            #     address_id            = addr_id,
            #     ritual_title          = crr.title,
            #     package_type          = 'CUSTOM',
            #     price                 = total,
            #     currency              = 'INR',
            #     other_snapshot_fields = {
            #         'description':       crr.description or '',
            #         'components':        crr.ritual_components or [],
            #         'quoted_breakdown':  crr.quoted_breakdown or {},
            #         'token_amount':      round(total * 0.20, 2),
            #     },
            #     contact_info = {
            #         'name':    customer.name,
            #         'contact': customer.contact_number or '',
            #         'email':   customer.email,
            #     },
            #     status        = CheckoutStatus.STARTED.value,
            #     selected_slot = booking_slot,
            # )
            # db.session.add(checkout)
            # db.session.flush()

            booking = Booking(
                # checkout_item_id         = checkout.id,
                ritual_package_id        = None,
                custom_ritual_request_id = crr.id,
                customer_id              = customer.id,
                address_id               = addr_id,
                ritual_snapshot          = _build_custom_snapshot(crr),
                address_snapshot         = _build_address_snapshot(addr),
                contact_info             = {
                    'name':  customer.name,
                    'phone': customer.contact_number or '',
                    'email': customer.email,
                },
                booking_source = booking_source,
                booking_slot   = booking_slot,
                status         = BookingStatus.CONFIRMED.value,
                notes          = notes,
                total_amount   = total,
                amount_due     = total,
                currency       = 'INR',
            )
            db.session.add(booking)
            # checkout.status = CheckoutStatus.CONVERTED.value
            db.session.commit()

            flash(f'Booking {booking.booking_ref} created for custom ritual "{crr.title}"!', 'success')
            return redirect(url_for('bookings.view_booking', booking_id=booking.id))

        # ══════════════════════════════════════════════════════════════════════
        #  PATH B — STANDARD RITUAL PACKAGE BOOKING
        # ══════════════════════════════════════════════════════════════════════
        ritual_package_id = request.form.get('ritual_package_id', '').strip()
        if not ritual_package_id:
            flash('Please select a ritual and package.', 'error')
            return render_template('bookings/new_booking.html', rituals=rituals,
                                   booking_sources=_booking_sources())

        package = RitualPackage.query.get(ritual_package_id)
        if not package:
            flash('Invalid ritual package.', 'error')
            return render_template('bookings/new_booking.html', rituals=rituals,
                                   booking_sources=_booking_sources())

        # checkout = CheckoutItem(
        #     ritual_package_id     = package.id,
        #     customer_id           = customer.id,
        #     address_id            = addr_id,
        #     ritual_title          = package.ritual_title,
        #     package_type          = package.package_type,
        #     price                 = package.price,
        #     currency              = 'INR',
        #     other_snapshot_fields = {
        #         'description':  package.description or '',
        #         'included':     _get_pkg_included(package),
        #         'not_included': _get_pkg_not_included(package),
        #         'token_amount': package.token_amount,
        #     },
        #     contact_info = {
        #         'name':    customer.name,
        #         'contact': customer.contact_number or '',
        #         'email':   customer.email,
        #     },
        #     status        = CheckoutStatus.STARTED.value,
        #     selected_slot = booking_slot,
        # )
        # db.session.add(checkout)
        # db.session.flush()

        booking = Booking(
            # checkout_item_id  = checkout.id,
            ritual_package_id = package.id,
            customer_id       = customer.id,
            address_id        = addr_id,
            ritual_snapshot   = _build_ritual_snapshot(package),
            address_snapshot  = _build_address_snapshot(addr),
            contact_info      = {
                'name':  customer.name,
                'phone': customer.contact_number or '',
                'email': customer.email,
            },
            booking_source = booking_source,
            booking_slot   = booking_slot,
            status         = BookingStatus.CONFIRMED.value,
            notes          = notes,
            total_amount   = package.price,
            amount_due     = package.price,
            currency       = 'INR',
        )
        db.session.add(booking)
        # checkout.status = CheckoutStatus.CONVERTED.value

        db.session.commit()
        flash(f'Booking {booking.booking_ref} created!', 'success')
        return redirect(url_for('bookings.view_booking', booking_id=booking.id))

    # ── GET — pre-fill from query param ──────────────────────────────────────
    prefill_email = None
    cid = request.args.get('customer_id', '')
    if cid:
        c = Customer.query.get(cid)
        if c:
            prefill_email = c.email

    return render_template('bookings/new_booking.html',
                           rituals=rituals,
                           prefill_email=prefill_email,
                           booking_sources=_booking_sources())


# ─────────────────────────────────────────────────────────────────────────────
#  VIEW BOOKING
# ─────────────────────────────────────────────────────────────────────────────

@bookings_bp.route('/<int:booking_id>')
def view_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    pandits = Pandit.query.filter_by(is_available=True).filter(
        Pandit.account_status == 'Active'
    ).all()
    # Pass all rituals so the Edit Ritual modal can build the selector
    rituals = Ritual.query.order_by(Ritual.title).all()
    # ── POLICY STATE passed to template (no new DB fields) ────────────────────
    can_reschedule, reschedule_block_msg = _can_reschedule(booking)
    can_cancel,     cancel_block_msg     = _can_cancel(booking)
    reschedule_count = _parse_reschedule_count(booking)
    hours_left       = _hours_until_slot(booking)
    # ──────────────────────────────────────────────────────────────────────────
    return render_template('bookings/view_booking.html',
                           booking=booking, pandits=pandits, rituals=rituals,
                           can_reschedule=can_reschedule,
                           reschedule_block_msg=reschedule_block_msg,
                           can_cancel=can_cancel,
                           cancel_block_msg=cancel_block_msg,
                           reschedule_count=reschedule_count,
                           reschedule_limit=RESCHEDULE_LIMIT,
                           hours_left=hours_left)


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE SLOT (admin correction) - Removed the functionality 
# ─────────────────────────────────────────────────────────────────────────────

# @bookings_bp.route('/<int:booking_id>/update', methods=['POST'])
# def update_booking(booking_id):
#     booking       = Booking.query.get_or_404(booking_id)
#     date_str      = request.form.get('booking_date', '').strip()
#     time_str      = request.form.get('booking_time', '').strip()
#     update_reason = request.form.get('update_reason', '').strip()

#     if not update_reason:
#         flash('Please provide a reason for the slot update.', 'error')
#         return redirect(url_for('bookings.view_booking', booking_id=booking_id))

#     try:
#         bdate = datetime.strptime(date_str, '%Y-%m-%d').date()
#         btime = datetime.strptime(time_str, '%H:%M').time()
#     except ValueError:
#         flash('Invalid date or time.', 'error')
#         return redirect(url_for('bookings.view_booking', booking_id=booking_id))

#     booking.booking_slot      = datetime.combine(bdate, btime)
#     booking.reschedule_reason = f'[SLOT UPDATE] {update_reason}'
#     booking.updated_at        = datetime.utcnow()

#     if booking.checkout_item:
#         booking.checkout_item.selected_slot = booking.booking_slot

#     db.session.commit()
#     flash('Booking slot updated.', 'success')
#     return redirect(url_for('bookings.view_booking', booking_id=booking_id))


# ─────────────────────────────────────────────────────────────────────────────
#  RESCHEDULE
# ─────────────────────────────────────────────────────────────────────────────

@bookings_bp.route('/<int:booking_id>/reschedule', methods=['POST'])
def reschedule_booking(booking_id):
    booking           = Booking.query.get_or_404(booking_id)
    new_date_str      = request.form.get('new_date', '').strip()
    new_time_str      = request.form.get('new_time', '').strip()
    reschedule_reason = request.form.get('reschedule_reason', '').strip()

    # ── POLICY CHECK: 48-hour window + max 2 reschedules ──────────────────────
    allowed, policy_msg = _can_reschedule(booking)
    if not allowed:
        flash(f'Reschedule not allowed: {policy_msg}', 'error')
        return redirect(url_for('bookings.view_booking', booking_id=booking_id))
    # ──────────────────────────────────────────────────────────────────────────

    if not reschedule_reason:
        flash('Please provide a reason for rescheduling.', 'error')
        return redirect(url_for('bookings.view_booking', booking_id=booking_id))

    try:
        bdate = datetime.strptime(new_date_str, '%Y-%m-%d').date()
        btime = datetime.strptime(new_time_str, '%H:%M').time()
    except ValueError:
        flash('Invalid date or time.', 'error')
        return redirect(url_for('bookings.view_booking', booking_id=booking_id))

    # Increment counter and store encoded in reschedule_reason (no new DB column)
    new_count = _parse_reschedule_count(booking) + 1
    booking.booking_slot      = datetime.combine(bdate, btime)
    booking.reschedule_reason = _encode_reschedule_reason(new_count, reschedule_reason)
    booking.updated_at        = datetime.utcnow()

    if booking.checkout_item:
        booking.checkout_item.selected_slot = booking.booking_slot

    db.session.commit()
    remaining = RESCHEDULE_LIMIT - new_count
    flash(
        f'Booking rescheduled successfully! '
        f'({new_count}/{RESCHEDULE_LIMIT} reschedules used'
        f'{" — no further reschedules allowed" if remaining == 0 else f", {remaining} remaining"}.)',
        'success'
    )
    return redirect(url_for('bookings.view_booking', booking_id=booking_id))


# ─────────────────────────────────────────────────────────────────────────────
#  CANCEL
# ─────────────────────────────────────────────────────────────────────────────

@bookings_bp.route('/<int:booking_id>/cancel', methods=['POST'])
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    # ── POLICY CHECK: no cancellation within 48 hours of the ritual ───────────
    allowed, policy_msg = _can_cancel(booking)
    if not allowed:
        flash(f'Cancellation not allowed: {policy_msg}', 'error')
        return redirect(url_for('bookings.view_booking', booking_id=booking_id))
    # ──────────────────────────────────────────────────────────────────────────

    reason = request.form.get('cancel_reason', '').strip()
    if not reason:
        flash('Cancellation reason required.', 'error')
        return redirect(url_for('bookings.view_booking', booking_id=booking_id))
    booking.status              = BookingStatus.CANCELLED.value
    booking.cancellation_reason = reason
    booking.updated_at          = datetime.utcnow()
    if booking.checkout_item:
        booking.checkout_item.status = CheckoutStatus.STARTED.value
    db.session.commit()
    flash('Booking cancelled.', 'warning')
    return redirect(url_for('bookings.view_booking', booking_id=booking_id))


# ─────────────────────────────────────────────────────────────────────────────
#  CONFIRM
# ─────────────────────────────────────────────────────────────────────────────

@bookings_bp.route('/<int:booking_id>/confirm', methods=['POST'])
def confirm_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    booking.status     = BookingStatus.CONFIRMED.value
    booking.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Booking confirmed!', 'success')
    return redirect(url_for('bookings.view_booking', booking_id=booking_id))


# ─────────────────────────────────────────────────────────────────────────────
#  COMPLETE
# ─────────────────────────────────────────────────────────────────────────────

@bookings_bp.route('/<int:booking_id>/complete', methods=['POST'])
def complete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    booking.status     = BookingStatus.COMPLETED.value
    booking.updated_at = datetime.utcnow()
    if booking.checkout_item:
        booking.checkout_item.status = CheckoutStatus.CONVERTED.value
    if booking.pandit:
        if booking.pandit.total_bookings_completed is None:
            booking.pandit.total_bookings_completed = 0
        booking.pandit.total_bookings_completed += 1
    db.session.commit()
    flash('Booking completed!', 'success')
    return redirect(url_for('bookings.view_booking', booking_id=booking_id))