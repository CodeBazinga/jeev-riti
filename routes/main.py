from flask import Blueprint, render_template, request
from models import Booking, Customer, CustomerAddress, Pandit, Payment, Ritual
from enums import BookingStatus, PaymentStatus
from extensions import db
from sqlalchemy import asc, desc, func
from datetime import date, timedelta, datetime
import json

main_bp = Blueprint('main', __name__)

# Currency symbol for display (stored as INR in DB)
CURRENCY_SYMBOL = '₹'


@main_bp.route('/')
def index():
    rituals = Ritual.query.order_by(Ritual.title).all()
    return render_template('index.html', rituals=rituals)


@main_bp.route('/bookings-list')
def bookings_list():
    sort_date   = request.args.get('sort_date', 'desc')
    city        = request.args.get('city', '')
    status      = request.args.get('status', '')
    ritual_type = request.args.get('ritual_type', '')
    email       = request.args.get('email', '')

    query = Booking.query.join(Customer)

    if city:
        query = query.join(CustomerAddress,
                           Booking.address_id == CustomerAddress.id, isouter=True)\
                     .filter(CustomerAddress.city.ilike(f'%{city}%'))

    if status:      query = query.filter(Booking.status == status)
    if email:       query = query.filter(Customer.email.ilike(f'%{email}%'))

    bookings_raw = query.order_by(
        asc(Booking.booking_slot) if sort_date == 'asc' else desc(Booking.booking_slot)
    ).all()

    if ritual_type:
        bookings = [b for b in bookings_raw
                    if ritual_type.lower() in (b.ritual_type or '').lower()]
    else:
        bookings = bookings_raw

    cities = [r[0] for r in db.session.query(CustomerAddress.city).distinct().all() if r[0]]
    today  = date.today()

    total_revenue = db.session.query(func.sum(Payment.amount))\
        .filter(Payment.status == PaymentStatus.CAPTURED.value,
                Payment.amount > 0).scalar() or 0

    active_pandits = Pandit.query.filter_by(is_available=True, account_status='Active').count()

    future_no_pandit = Booking.query.filter(
        Booking.booking_slot >= datetime.combine(today, datetime.min.time()),
        Booking.status == BookingStatus.CONFIRMED.value,
        Booking.pandit_id.is_(None)
    ).count()

    thirty_days_ago = today - timedelta(days=29)
    revenue_rows = db.session.query(
        func.date(Payment.created_at).label('pay_date'),
        func.sum(Payment.amount).label('total')
    ).filter(
        Payment.status == PaymentStatus.CAPTURED.value,
        Payment.amount > 0,
        func.date(Payment.created_at) >= thirty_days_ago
    ).group_by(func.date(Payment.created_at)).all()

    revenue_by_date = {str(r.pay_date): float(r.total) for r in revenue_rows}
    trend_labels, trend_values = [], []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        trend_labels.append(d.strftime('%d %b'))
        trend_values.append(revenue_by_date.get(str(d), 0))

    ritual_counts = {}
    for b in Booking.query.all():
        t = b.ritual_type
        if t:
            ritual_counts[t] = ritual_counts.get(t, 0) + 1
    ritual_labels = list(ritual_counts.keys())
    ritual_values = list(ritual_counts.values())
    ritual_titles = ritual_labels[:]

    return render_template(
        'bookings_list.html',
        bookings=bookings,
        cities=cities, today_date=today,
        ritual_titles=ritual_titles,
        booking_statuses=[s.value for s in BookingStatus],
        filters=dict(sort_date=sort_date, city=city, status=status,
                     ritual_type=ritual_type, email=email),
        total_revenue=total_revenue,
        active_pandits=active_pandits,
        future_no_pandit=future_no_pandit,
        trend_labels=json.dumps(trend_labels),
        trend_values=json.dumps(trend_values),
        ritual_labels=json.dumps(ritual_labels),
        ritual_values=json.dumps(ritual_values),
        currency_symbol=CURRENCY_SYMBOL,
    )
