from flask import Blueprint, render_template, request, redirect, url_for, flash
from models import Booking, Payment
from enums import PaymentProvider, PaymentType, PaymentStatus
from extensions import db
from datetime import datetime

payments_bp = Blueprint('payments', __name__)

PAYMENT_PROVIDERS = [p.value for p in PaymentProvider]
PAYMENT_TYPES     = [p.value for p in PaymentType]


@payments_bp.route('/<int:booking_id>')
def booking_payments(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template('payments.html', booking=booking,
                           payment_providers=PAYMENT_PROVIDERS,
                           payment_types=PAYMENT_TYPES)


@payments_bp.route('/<int:booking_id>/add', methods=['POST'])
def add_payment(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    try:
        amount = float(request.form.get('amount', 0))
        if amount <= 0:
            raise ValueError
    except ValueError:
        flash('Invalid payment amount.', 'error')
        return redirect(url_for('payments.booking_payments', booking_id=booking_id))

    provider     = request.form.get('provider', PaymentProvider.CASH.value)
    payment_type = request.form.get('payment_type', PaymentType.FULL.value)
    notes_text   = request.form.get('notes', '').strip()
    txn_id       = request.form.get('transaction_id', '').strip()

    payment = Payment(
        booking_id          = booking.id,
        checkout_item_id    = booking.checkout_item_id,
        amount              = amount,
        currency            = booking.currency or 'INR',
        provider            = provider,
        payment_type        = payment_type,
        status              = PaymentStatus.CAPTURED.value,
        external_transaction_id = txn_id or None,
        raw_payload         = {'notes': notes_text} if notes_text else {},
    )
    db.session.add(payment)
    booking.amount_due = max(0, booking.amount_due - amount)
    db.session.commit()

    flash(f'Payment of ₹{amount:,.0f} recorded!', 'success')
    return redirect(url_for('payments.booking_payments', booking_id=booking_id))


@payments_bp.route('/<int:booking_id>/refund', methods=['POST'])
def process_refund(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    try:
        refund_amount = float(request.form.get('refund_amount', 0))
        if refund_amount <= 0:
            raise ValueError
    except ValueError:
        flash('Invalid refund amount.', 'error')
        return redirect(url_for('payments.booking_payments', booking_id=booking_id))

    notes_text = request.form.get('reason', '').strip()
    provider   = request.form.get('provider', PaymentProvider.CASH.value)

    payment = Payment(
        booking_id       = booking.id,
        checkout_item_id = booking.checkout_item_id,
        amount           = -refund_amount,
        currency         = booking.currency or 'INR',
        provider         = provider,
        payment_type     = PaymentType.FULL.value,
        status           = PaymentStatus.REFUNDED.value,
        raw_payload      = {'notes': notes_text} if notes_text else {},
    )
    db.session.add(payment)
    booking.amount_due = min(booking.total_amount, booking.amount_due + refund_amount)
    db.session.commit()

    flash(f'Refund of ₹{refund_amount:,.0f} processed.', 'success')
    return redirect(url_for('payments.booking_payments', booking_id=booking_id))
