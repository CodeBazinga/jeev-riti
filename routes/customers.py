from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, jsonify)
from models import Customer, CustomerAddress, Booking
from extensions import db
from datetime import datetime

customers_bp = Blueprint('customers', __name__)


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMER LIST
# ─────────────────────────────────────────────────────────────────────────────
@customers_bp.route('/')
def customer_list():
    search = request.args.get('search', '').strip()

    q = Customer.query
    if search:
        q = q.filter(db.or_(
            Customer.name.ilike(f'%{search}%'),
            Customer.email.ilike(f'%{search}%'),
            Customer.contact_number.ilike(f'%{search}%'),
        ))

    customers = q.order_by(Customer.created_at.desc()).all()
    stats = {
        'total':         Customer.query.count(),
        'with_address':  db.session.query(Customer.id).join(CustomerAddress).distinct().count(),
        'with_bookings': db.session.query(Customer.id).join(Booking).distinct().count(),
    }
    return render_template('customers/customer_list.html',
                           customers=customers, stats=stats,
                           filters=dict(search=search))


# ─────────────────────────────────────────────────────────────────────────────
#  REGISTER
# ─────────────────────────────────────────────────────────────────────────────
@customers_bp.route('/new', methods=['GET', 'POST'])
def new_customer():
    if request.method == 'POST':
        name           = request.form.get('name', '').strip()
        email          = request.form.get('email', '').strip().lower()
        contact_number = request.form.get('contact_number', '').strip() or None

        if not name or not email:
            flash('Name and Email are required.', 'error')
            return render_template('customers/new_customer.html')

        if Customer.query.filter_by(email=email).first():
            flash('A customer with this email already exists.', 'error')
            return render_template('customers/new_customer.html',
                                   prefill={'name': name, 'email': email,
                                            'contact_number': contact_number})

        customer = Customer(name=name, email=email,
                            contact_number=contact_number)
        db.session.add(customer)
        db.session.commit()
        flash(f'Customer {name} registered!', 'success')
        return redirect(url_for('customers.view_customer', customer_id=customer.id))

    return render_template('customers/new_customer.html')


# ─────────────────────────────────────────────────────────────────────────────
#  VIEW CUSTOMER
# ─────────────────────────────────────────────────────────────────────────────
@customers_bp.route('/<int:customer_id>')
def view_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    bookings = Booking.query.filter_by(customer_id=customer_id)\
                            .order_by(Booking.created_at.desc()).all()
    return render_template('customers/view_customer.html',
                           customer=customer, bookings=bookings)


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE CONTACT INFO
# ─────────────────────────────────────────────────────────────────────────────
@customers_bp.route('/<int:customer_id>/update-contact', methods=['POST'])
def update_contact(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    customer.name           = request.form.get('name', customer.name).strip()
    customer.contact_number = request.form.get('contact_number', '').strip() or None

    dob_str = request.form.get('date_of_birth', '').strip()
    if dob_str:
        try:
            customer.date_of_birth = datetime.strptime(dob_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date of birth format.', 'error')
            return redirect(url_for('customers.view_customer', customer_id=customer_id))
    else:
        customer.date_of_birth = None

    customer.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Contact information updated.', 'success')
    return redirect(url_for('customers.view_customer', customer_id=customer_id))


# ─────────────────────────────────────────────────────────────────────────────
#  ADD ADDRESS
# ─────────────────────────────────────────────────────────────────────────────
@customers_bp.route('/<int:customer_id>/add-address', methods=['POST'])
def add_address(customer_id):
    customer       = Customer.query.get_or_404(customer_id)
    reference_name = request.form.get('reference_name', '').strip()
    street         = request.form.get('street', '').strip()
    city           = request.form.get('city', '').strip()
    state          = request.form.get('state', '').strip()
    zip_code       = request.form.get('zip_code', '').strip()
    country        = request.form.get('country', 'India').strip()

    if not all([reference_name, street, city, state, zip_code]):
        flash('All address fields are required.', 'error')
        return redirect(url_for('customers.view_customer', customer_id=customer_id))

    db.session.add(CustomerAddress(
        customer_id=customer.id,
        reference_name=reference_name,
        street=street, city=city, state=state,
        zip_code=zip_code, country=country,
        is_active=True
    ))
    db.session.commit()
    flash(f'Address "{reference_name}" added!', 'success')
    return redirect(url_for('customers.view_customer', customer_id=customer_id))


# ─────────────────────────────────────────────────────────────────────────────
#  UPDATE ADDRESS
# ─────────────────────────────────────────────────────────────────────────────
@customers_bp.route('/<int:customer_id>/address/<int:address_id>/update', methods=['POST'])
def update_address(customer_id, address_id):
    addr = CustomerAddress.query.get_or_404(address_id)
    addr.reference_name = request.form.get('reference_name', addr.reference_name).strip()
    addr.street         = request.form.get('street', addr.street).strip()
    addr.city           = request.form.get('city', addr.city).strip()
    addr.state          = request.form.get('state', addr.state).strip()
    addr.zip_code       = request.form.get('zip_code', addr.zip_code).strip()
    addr.country        = request.form.get('country', addr.country).strip()
    addr.updated_at     = datetime.utcnow()
    db.session.commit()
    flash('Address updated.', 'success')
    return redirect(url_for('customers.view_customer', customer_id=customer_id))


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE ADDRESS
# ─────────────────────────────────────────────────────────────────────────────
@customers_bp.route('/<int:customer_id>/address/<int:address_id>/delete', methods=['POST'])
def delete_address(customer_id, address_id):
    addr = CustomerAddress.query.get_or_404(address_id)
    db.session.delete(addr)
    db.session.commit()
    flash('Address deleted.', 'warning')
    return redirect(url_for('customers.view_customer', customer_id=customer_id))


# ─────────────────────────────────────────────────────────────────────────────
#  API — LOOKUP by email or mobile (contact_number)
# ─────────────────────────────────────────────────────────────────────────────
@customers_bp.route('/lookup')
def lookup_customer():
    email  = request.args.get('email', '').strip().lower()
    mobile = request.args.get('mobile', '').strip()

    customer = None
    if email:
        customer = Customer.query.filter_by(email=email).first()
    elif mobile:
        # Normalise digits only, then match
        clean = ''.join(c for c in mobile if c.isdigit())
        # PostgreSQL: use regexp_replace or just ilike
        customer = Customer.query.filter(
            Customer.contact_number.ilike(f'%{clean[-10:]}%')
        ).first()

    if not customer:
        return jsonify({'found': False})
    return jsonify(_customer_payload(customer))


@customers_bp.route('/lookup-by-id')
def lookup_customer_by_id():
    cid      = request.args.get('id', '').strip()
    customer = Customer.query.get(cid)
    if not customer:
        return jsonify({'found': False})
    return jsonify(_customer_payload(customer))


def _customer_payload(customer):
    return {
        'found':     True,
        'id':        customer.id,
        'name':      customer.name,
        'email':     customer.email,
        'mobile':    customer.contact_number or '',
        'addresses': [
            {
                'id':             a.id,
                'reference_name': a.reference_name,
                'full_address':   a.full_address,
                'is_active':      a.is_active,
            }
            for a in customer.active_addresses
        ],
    }
