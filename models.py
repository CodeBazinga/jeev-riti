from extensions import db
from datetime import datetime
import base64
from enums import (
    PujaMode, RitualPackageType,
    PaymentProvider, PaymentType, PaymentStatus,
    BookingSource, BookingStatus, CheckoutStatus,
    PanditAddressType, PanditPhotoType,RitualPackageType,
    PanditVerificationStatus, AccountStatus, PanditPayoutStatus
)
from sqlalchemy import CheckConstraint, Unicode, BigInteger,Boolean, Text, Date, DateTime,Double, ForeignKey,LargeBinary, String, Float, VARCHAR, Integer
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from typing import List
from sqlalchemy.types import TypeDecorator, String


# ─────────────────────────────────────────────────────────────────────────────
#  CONSTANTS derived from enums
# ─────────────────────────────────────────────────────────────────────────────
BOOKING_STATUS      = [s.value for s in BookingStatus]
CHECKOUT_STATUSES   = [s.value for s in CheckoutStatus]
PANDIT_VERIFICATION_STATUS = [v.value for v in PanditVerificationStatus]
ACCOUNT_STATUS      = [a.value for a in AccountStatus]
# VERIFICATION_STATUS = ['Pending', 'Verified', 'Rejected']
# ACCOUNT_STATUS      = ['Active', 'Inactive', 'Suspended']
PACKAGE_TYPES       = [p.value for p in RitualPackageType]
RITUAL_MODES        = [m.value for m in PujaMode]
ADDRESS_TYPES       = [a.value for a in PanditAddressType]
PHOTO_TYPES         = [p.value for p in PanditPhotoType]
BOOKING_SOURCES     = [s.value for s in BookingSource]
PAYMENT_PROVIDERS   = [p.value for p in PaymentProvider]
PAYMENT_TYPES       = [p.value for p in PaymentType]
PAYMENT_STATUSES    = [p.value for p in PaymentStatus]
PANDIT_PAYOUT_STATUS = [p.value for p in PanditPayoutStatus]





class EnumAsString(TypeDecorator):
    impl = String
    cache_ok = True  # important for SQLAlchemy 1.4+

    def __init__(self, enum_class, *args, **kwargs):
        self.enum_class = enum_class
        super().__init__(*args, **kwargs)

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if isinstance(value, self.enum_class):
            return value.value
        return value  # allow raw string (optional)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        try:
            return self.enum_class(value).value
        except ValueError:
            return value  # pass through unknown values



# ─────────────────────────────────────────────────────────────────────────────
#  RITUAL 
# ─────────────────────────────────────────────────────────────────────────────
class Ritual(db.Model):
    __tablename__ = 'ritual'

    id          = db.Column(BigInteger, primary_key=True)
    title       = db.Column(Text, nullable=False, unique=True)
    description = db.Column(Text, nullable=False)
    # search_vector = db.Column(TSVECTOR,nullable=True, default='dummy')
    created_at  = db.Column(DateTime, default=datetime.utcnow)
    updated_at  = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    details = db.relationship('RitualDetail', backref='ritual', lazy=True,
                               cascade='all, delete-orphan')
    images  = db.relationship('RitualImage', backref='ritual', lazy=True,
                               cascade='all, delete-orphan')


    def __repr__(self):
        return f'<Ritual {self.title}>'

    @property
    def min_price(self):
        if self.details and self.details.packages:
            prices = [p.price for p in self.details.packages if p.price]
            return min(prices) if prices else None
        return None

    @property
    def primary_image(self):
        return self.images[0] if self.images else None


# ─────────────────────────────────────────────────────────────────────────────
#  RITUAL DETAIL   - converted to PG
# ─────────────────────────────────────────────────────────────────────────────
class RitualDetail(db.Model):
    __tablename__ = 'ritual_detail'

    id               = db.Column(BigInteger, primary_key=True)
    ritual_id        = db.Column(BigInteger, ForeignKey('ritual.id'),
                                  nullable=False)
    puja_vidhi       = db.Column(ARRAY(String),nullable=False)
    puja_samagri     = db.Column(JSONB,nullable=False)           # list of dicts [{item, qty, unit}]
    puja_seasons     = db.Column(Text,nullable=False)
    num_pundits      = db.Column(Integer, default=1,nullable=False)
    duration         = db.Column(VARCHAR(20),nullable=False)
    mode             = db.Column(EnumAsString(PujaMode, length=40), nullable=False,
                                 default=PujaMode.OFFLINE.value)
    ritual_metadata  = db.Column(JSONB,default=dict)
    created_at       = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at       = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    packages = db.relationship('RitualPackage', backref='detail', lazy=True,
                                cascade='all, delete-orphan')

    def __repr__(self):
        return f'<RitualDetail ritual_id={self.ritual_id}>'


# ─────────────────────────────────────────────────────────────────────────────
#  RITUAL IMAGE
# ─────────────────────────────────────────────────────────────────────────────
class RitualImage(db.Model):
    __tablename__ = 'ritual_image'

    id         = db.Column(BigInteger, primary_key=True,nullable=False)
    ritual_id  = db.Column(BigInteger, ForeignKey('ritual.id'), nullable=False)
    file_name  = db.Column(VARCHAR(255), nullable=False)
    mimetype   = db.Column(VARCHAR(50), default='image/jpeg',nullable=False)
    data       = db.Column(LargeBinary, nullable=False)   # LONGBLOB
    created_at = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    @property
    def data_uri(self):
        if self.data:
            return f'data:{self.mimetype};base64,{base64.b64encode(self.data).decode()}'
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  RITUAL PACKAGE
# ─────────────────────────────────────────────────────────────────────────────
class RitualPackage(db.Model):
    __tablename__ = 'ritual_package'

    id               = db.Column(BigInteger, primary_key=True,nullable=False)
    ritual_detail_id = db.Column(BigInteger, db.ForeignKey('ritual_detail.id'), nullable=False)
    package_type     = db.Column(EnumAsString(RitualPackageType, length=40), nullable=False,
                                  default=RitualPackageType.STANDARD.value)
    description      = db.Column(VARCHAR(50), nullable=True)    # Changed from original
    included         = db.Column(ARRAY(String), nullable=False, default=list)
    not_included     = db.Column(ARRAY(String), nullable=False, default=list)
    price            = db.Column(Double, nullable=False)
    currency         = db.Column(String(10), default="INR")
    created_at       = db.Column(db.DateTime, default=datetime.utcnow,nullable=False)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    checkout_items = db.relationship('CheckoutItem', backref='package', lazy=True)

    @property
    def included_list(self):
        """ARRAY(String) column — return as list directly."""
        if not self.included:
            return []
        if isinstance(self.included, list):
            return [i for i in self.included if i]
        return [s.strip() for s in str(self.included).split(',') if s.strip()]

    @property
    def not_included_list(self):
        """ARRAY(String) column — return as list directly."""
        if not self.not_included:
            return []
        if isinstance(self.not_included, list):
            return [i for i in self.not_included if i]
        return [s.strip() for s in str(self.not_included).split(',') if s.strip()]

    @property
    def token_amount(self):
        return round(self.price * 0.20, 2)

    @property
    def ritual_title(self):
        return self.detail.ritual.title if self.detail and self.detail.ritual else ''


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMER
# ─────────────────────────────────────────────────────────────────────────────
class Customer(db.Model):
    __tablename__ = 'customer'

    id               = db.Column(BigInteger, primary_key=True)
    name             = db.Column(db.String(150), nullable=False)
    email            = db.Column(String(250), unique=True, nullable=False)
    contact_number   = db.Column(String(14), unique=True, nullable=True)
    google_id        = db.Column(String(255), unique=True, nullable=True)
    # password_hash    = db.Column(db.String(255), nullable=True)
    password_hash    = db.Column(Unicode, nullable=True)
    date_of_birth    = db.Column(Date, nullable=True)
    aggregate_rating = db.Column(Float, nullable=True)
    created_at       = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at       = db.Column(DateTime, default=datetime.utcnow,nullable=False)

    addresses = db.relationship('CustomerAddress', backref='customer',
                                 lazy=True, cascade='all, delete-orphan')
    bookings  = db.relationship('Booking', backref='customer', lazy=True)

    def __repr__(self):
        return f'<Customer {self.name}>'

    @property
    def active_addresses(self):
        return [a for a in self.addresses if a.is_active]

    @property
    def mobile(self):
        """Backward-compat alias."""
        return self.contact_number


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMER ADDRESS
# ─────────────────────────────────────────────────────────────────────────────
class CustomerAddress(db.Model):
    __tablename__ = 'customer_address'

    id             = db.Column(BigInteger, primary_key=True,nullable=False)
    customer_id    = db.Column(BigInteger, ForeignKey('customer.id'), nullable=False)
    reference_name = db.Column(String(20), nullable=False)  # Home, Office
    street         = db.Column(String(255), nullable=False)
    city           = db.Column(String(100), nullable=False)
    state          = db.Column(String(50), nullable=False)
    zip_code       = db.Column(String(20),  nullable=False)
    country        = db.Column(String(100), default='India')
    is_active      = db.Column(Boolean, default=True,nullable=False)
    created_at     = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at     = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    checkout_items = db.relationship('CheckoutItem', backref='address', lazy=True)

    @property
    def full_address(self):
        return ', '.join(p for p in [self.street, self.city, self.state,
                                      self.zip_code, self.country] if p)


# ─────────────────────────────────────────────────────────────────────────────
#  CHECKOUT ITEM  (revised schema)
# ─────────────────────────────────────────────────────────────────────────────
class CheckoutItem(db.Model):
    __tablename__ = 'checkout_item'

    id                    = db.Column(BigInteger, primary_key=True)
    ritual_package_id     = db.Column(BigInteger, ForeignKey('ritual_package.id'), nullable=False)
    customer_id           = db.Column(BigInteger, ForeignKey('customer.id'), nullable=False)
    address_id            = db.Column(BigInteger, ForeignKey('customer_address.id'), nullable=True)

    # Snapshot fields (captured at checkout time)
    ritual_title          = db.Column(String(100), nullable=False)
    package_type          = db.Column(EnumAsString(RitualPackageType, length=40), nullable=False,
                                       default=RitualPackageType.STANDARD.value)
    price                 = db.Column(Float, nullable=False)
    currency              = db.Column(String(10), default='INR')
    other_snapshot_fields = db.Column(JSONB,default=dict)   # {included, not_included, description, …}
    contact_info          = db.Column(JSONB)   # {name, contact, email}

    status        = db.Column(EnumAsString(CheckoutStatus, length=40), nullable=False,
                               default=CheckoutStatus.STARTED.value)
    selected_slot = db.Column(DateTime(timezone=True), nullable=True)   # combined date+time

    created_at = db.Column(DateTime, default=datetime.utcnow)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    payments = db.relationship('Payment', backref='checkout_item', lazy=True,
                                foreign_keys='Payment.checkout_item_id')
    booking  = db.relationship('Booking', backref='checkout_item', lazy=True,
                                uselist=False, foreign_keys='Booking.checkout_item_id')

    def __repr__(self):
        return f'<CheckoutItem {self.ritual_title} [{self.status}]>'

    @property
    def token_amount(self):
        return round(self.price * 0.20, 2)


# ─────────────────────────────────────────────────────────────────────────────
#  PANDIT
# ─────────────────────────────────────────────────────────────────────────────
class Pandit(db.Model):
    __tablename__ = 'pandit'

    id             = db.Column(BigInteger, primary_key=True)
    name           = db.Column(String(250), nullable=False)
    mobile         = db.Column(String(14), unique=True,  nullable=False)
    email          = db.Column(String(250), unique=True,nullable=True)
    experience_yrs = db.Column(BigInteger, default=1,nullable=False)
    languages      = db.Column(String(200),nullable=False)

    is_available        = db.Column(Boolean, default=True)
    verification_status = db.Column(EnumAsString(PanditVerificationStatus,length=40), nullable=False,
                                    default=PanditVerificationStatus.PENDING.value)
    account_status      = db.Column(EnumAsString(AccountStatus,length=40), nullable=False,
                                    default=AccountStatus.ACTIVE.value)
    rejection_reason    = db.Column(Text)
    suspension_reason   = db.Column(Text)

    bank_name         = db.Column(String(100),nullable=True)
    bank_account_no   = db.Column(String(30),nullable=True)
    bank_ifsc         = db.Column(String(20),nullable=True)
    bank_account_name = db.Column(String(150),nullable=True)
    upi_id            = db.Column(String(100),nullable=True)

    rating                   = db.Column(Float,   default=0.0,nullable=True)
    total_earnings           = db.Column(Integer,   default=0.0,nullable=True)
    total_bookings_completed = db.Column(Integer, default=0,nullable=True)

    created_at = db.Column(DateTime, default=datetime.utcnow)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bookings   = db.relationship('Booking',        backref='pandit', lazy=True)
    documents  = db.relationship('PanditDocument', backref='pandit', lazy=True,
                                  cascade='all, delete-orphan')
    complaints = db.relationship('PanditComplaint', backref='pandit', lazy=True,
                                  cascade='all, delete-orphan')
    payouts    = db.relationship('PanditPayout',   backref='pandit', lazy=True,
                                  cascade='all, delete-orphan')
    addresses  = db.relationship('PanditAddress',  backref='pandit', lazy=True,
                                  cascade='all, delete-orphan')
    photos     = db.relationship('PanditPhoto',    backref='pandit', lazy=True,
                                  cascade='all, delete-orphan')
    puja_details= db.relationship('PanditPujaDetail', backref='pandit', lazy=True,
                                   cascade='all, delete-orphan')

    @property
    def expertise_list(self):
        """No specialization column — returns empty list."""
        return []

    @property
    def pending_payout(self):
        return sum(p.amount for p in self.payouts if p.status == 'Pending')

    @property
    def profile_photo(self):
        for ph in self.photos:
            if ph.photo_type == PanditPhotoType.PROFILE.value:
                return ph
        return self.photos[0] if self.photos else None

    @property
    def current_address(self):
        for a in self.addresses:
            if a.address_type == PanditAddressType.CURRENT.value:
                return a
        return self.addresses[0] if self.addresses else None

    @property
    def city(self):
        a = self.current_address
        return a.city if a else ''


# ─────────────────────────────────────────────────────────────────────────────
#  BOOKING
# ─────────────────────────────────────────────────────────────────────────────
class Booking(db.Model):
    __tablename__ = 'booking'

    id                  = db.Column(BigInteger, primary_key=True)
    checkout_item_id    = db.Column(BigInteger, ForeignKey('checkout_item.id'), nullable=True)
    ritual_package_id   = db.Column(BigInteger, ForeignKey('ritual_package.id'), nullable=True)
    custom_ritual_request_id  = db.Column(BigInteger, ForeignKey('custom_ritual_request.id'), 
                                          nullable=True)
    
    customer_id         = db.Column(BigInteger, ForeignKey('customer.id'), nullable=False)
    pandit_id           = db.Column(BigInteger, ForeignKey('pandit.id'), nullable=True)
    address_id          = db.Column(BigInteger, ForeignKey('customer_address.id'), nullable=True)

    ritual_snapshot     = db.Column(JSONB, nullable=False, default=dict)
    address_snapshot    = db.Column(JSONB, nullable=False, default=dict)
    contact_info        = db.Column(JSONB, nullable=False)

    booking_source      = db.Column(EnumAsString(BookingSource, length=40), nullable=False,
                                    default=BookingSource.ADMIN.value)
    booking_slot        = db.Column(DateTime, nullable=False)
    status              = db.Column(EnumAsString(BookingStatus, length=40), nullable=False,
                                    default=BookingStatus.CONFIRMED.value)
    notes               = db.Column(String(255),nullable=True)      # extra column
    total_amount        = db.Column(Float, default=0.0,nullable=False)
    amount_due          = db.Column(Float, default=0.0,nullable=False)
    currency            = db.Column(VARCHAR(10), nullable=False, default="INR")
    cancellation_reason = db.Column(String(255),nullable=True)    # extra column
    reschedule_reason   = db.Column(String(255),nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow,nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    payments       = db.relationship('Payment', backref='booking', lazy=True,
                                      foreign_keys='Payment.booking_id')
    ritual_address = db.relationship('CustomerAddress', foreign_keys=[address_id], lazy=True)
    ritual_package = db.relationship('RitualPackage', foreign_keys=[ritual_package_id], lazy=True)

    # This constraint throws error

    # __table_args__ = (
    #     CheckConstraint(
    #         "num_nonnulls(checkout_item_id, ritual_package_id, custom_ritual_request_id) = 1",
    #         name="ck_booking_either_existing_or_custom"
    #     ),
    # )          

    

    @property
    def booking_ref(self):
        return f'RB-{self.id:06d}'

    @property
    def ritual_type(self):
        if self.ritual_snapshot:
            return self.ritual_snapshot.get('title', '')
        return self.ritual_package.ritual_title if self.ritual_package else ''

    @property
    def ritual_price(self):
        if self.ritual_snapshot:
            return self.ritual_snapshot.get('price', self.total_amount)
        return self.total_amount

    @property
    def booking_date(self):
        return self.booking_slot.date() if self.booking_slot else None

    @property
    def booking_time(self):
        return self.booking_slot.time() if self.booking_slot else None

    @property
    def payment_status(self):
        if self.amount_due <= 0 and self.total_amount > 0:
            return 'Fully Paid'
        if self.amount_due < self.total_amount:
            return 'Token Paid'
        return 'Unpaid'

    @property
    def token_amount(self):
        return round(self.total_amount * 0.20, 2)

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments
                   if p.status == PaymentStatus.CAPTURED.value and p.amount > 0)

    @property
    def remaining_amount(self):
        return max(0, self.total_amount - self.total_paid)



# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOM RITUAL REQUEST
# ─────────────────────────────────────────────────────────────────────────────

class CustomRitualRequest(db.Model):
    __tablename__ = 'custom_ritual_request'
 
    id          = db.Column(BigInteger, primary_key=True)
    customer_id = db.Column(BigInteger, ForeignKey('customer.id'), nullable=False)
    # Optional anchor ritual for filtering/search
    ritual_id   = db.Column(BigInteger, ForeignKey('ritual.id'), nullable=True)
 
    title       = db.Column(Text, nullable=False)
    description = db.Column(Text, nullable=True)
 
    # source of truth — supports multi-ritual + fully custom requests
    # List[dict]: [{ritual_id, name, sequence}, ...]
    ritual_components = db.Column(JSONB, nullable=False, default=list)
 
    # Requirements dict — num_pandits, samagri_included, preferred_date, etc.
    requirements = db.Column(JSONB, nullable=False, default=dict)
 
    # Quote fields
    quoted_price     = db.Column(Float,  nullable=True)
    quoted_breakdown = db.Column(JSONB,  nullable=True)   # {pandit_fee, samagri, travel, …}
    quote_notes      = db.Column(Text,   nullable=True)
 
    created_at = db.Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = db.Column(DateTime(timezone=True), default=datetime.utcnow,
                            onupdate=datetime.utcnow, nullable=False)
 
    # Relationships
    customer = db.relationship('Customer', backref='custom_ritual_requests', lazy=True)
    ritual   = db.relationship('Ritual',   backref='custom_ritual_requests', lazy=True)
    booking  = db.relationship('Booking',  backref='custom_ritual_request',  uselist=False,
                                foreign_keys='Booking.custom_ritual_request_id')
 
    def __repr__(self):
        return f'<CustomRitualRequest {self.id} — {self.title}>'
 
    @property
    def is_quoted(self):
        return self.quoted_price is not None
 
    @property
    def component_count(self):
        return len(self.ritual_components) if self.ritual_components else 0




# ─────────────────────────────────────────────────────────────────────────────
#  PAYMENT
# ─────────────────────────────────────────────────────────────────────────────
class Payment(db.Model):
    __tablename__ = 'payment'

    id                  = db.Column(BigInteger, primary_key=True)
    checkout_item_id    = db.Column(BigInteger, ForeignKey('checkout_item.id'), nullable=True)
    booking_id          = db.Column(BigInteger, ForeignKey('booking.id'), nullable=True)
    
    #  Payment Classification fields
    provider            = db.Column(EnumAsString(PaymentProvider, length=40), nullable=False,
                                     default=PaymentProvider.CASH.value)
    payment_type        = db.Column(EnumAsString(PaymentType, length=40), nullable=False,
                                     default=PaymentType.FULL.value)
    status              = db.Column(EnumAsString(PaymentStatus, length=40), nullable=False,
                                     default=PaymentStatus.PENDING.value)
    # amount
    amount              = db.Column(Float, nullable=False)
    currency            = db.Column(String(10), nullable=False,default='INR')
    

    # gateway provider fields
    external_reference_id   = db.Column(String(100), nullable=True)
    external_transaction_id = db.Column(String(100), nullable=True)
    
    # old column names
    # provider_order_id   = db.Column(String(100), nullable=True,unique=True)
    # provider_payment_id = db.Column(String(100), nullable=True)

    
    # metadata
    raw_payload         = db.Column(JSONB, default=dict, nullable=False)
    
    # timestamps
    created_at          = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at          = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    @property
    def payment_method(self):
        return self.provider

    @property
    def transaction_id(self):
        return self.provider_payment_id

    @property
    def notes(self):
        return self.raw_payload.get('notes', '') if isinstance(self.raw_payload, dict) else ''



# ─────────────────────────────────────────────────────────────────────────────
#  PANDIT SUPPORTING TABLES
# ─────────────────────────────────────────────────────────────────────────────
class PanditPujaDetail(db.Model):
    __tablename__ = 'pandit_puja_detail'

    id = db.Column(BigInteger, primary_key=True, nullable=False)
    pandit_id = db.Column(BigInteger, ForeignKey('pandit.id'), nullable=False)
    ritual_id = db.Column(BigInteger, ForeignKey('ritual.id'), nullable=False)
    variant = db.Column(Integer, nullable=False)
    variant_detail = db.Column(JSONB, nullable=False, default=dict)
    min_num_pandits = db.Column(Integer, nullable=False)
    duration  = db.Column(String(20), nullable=False)
    total_fees = db.Column(Float, nullable=False)
    currency  = db.Column(String(20), nullable=False, default="INR")
    fees_breakup= db.Column(JSONB, nullable=False, default=dict)
    created_at = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    ritual = db.relationship('Ritual', lazy=True)
    
    def get_id(self):
        return self.id


    def __repr__(self):
        return f'<PanditPujaDetail pandit={self.pandit_id} ritual={self.ritual_id} variant={self.variant}>'




class PanditDocument(db.Model):
    __tablename__ = 'pandit_document'

    id          = db.Column(BigInteger, primary_key=True)
    pandit_id   = db.Column(BigInteger, ForeignKey('pandit.id'), nullable=False)
    doc_type    = db.Column(String(50),  nullable=False)
    filename    = db.Column(String(200), nullable=False)
    is_verified = db.Column(Boolean, default=False)
    notes       = db.Column(Text)
    uploaded_at = db.Column(DateTime, default=datetime.utcnow)
    created_at  = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at  = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)


class PanditComplaint(db.Model):
    __tablename__ = 'pandit_complaint'

    id          = db.Column(BigInteger, primary_key=True)
    pandit_id   = db.Column(BigInteger, ForeignKey('pandit.id'),  nullable=False)
    booking_id  = db.Column(BigInteger, ForeignKey('booking.id'), nullable=True)
    raised_by   = db.Column(String(150))       # check this column again (it should be Customer_ID)
    subject     = db.Column(String(200), nullable=False)
    description = db.Column(Text, nullable=False)
    status      = db.Column(String(20), default='Open')
    resolution  = db.Column(Text)
    created_at  = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at  = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)


class PanditPayout(db.Model):
    __tablename__ = 'pandit_payout'

    id         = db.Column(BigInteger, primary_key=True)
    pandit_id  = db.Column(BigInteger, ForeignKey('pandit.id'),  nullable=False)
    booking_id = db.Column(BigInteger, ForeignKey('booking.id'), nullable=True)
    amount     = db.Column(Float, nullable=False)
    status     = db.Column(EnumAsString(PanditPayoutStatus,length=40),nullable=False,
                            default=PanditPayoutStatus.PENDING.value)
    method     = db.Column(String(50))
    reference  = db.Column(String(100))
    notes      = db.Column(Text)
    paid_at    = db.Column(DateTime)
    created_at = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at  = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)


class PanditAddress(db.Model):
    __tablename__ = 'pandit_address'

    id             = db.Column(BigInteger, primary_key=True)
    pandit_id      = db.Column(BigInteger, ForeignKey('pandit.id'), nullable=False)
    reference_name = db.Column(String(20),nullable=False)
    street         = db.Column(String(255), nullable=False)
    city           = db.Column(String(100), nullable=False)
    state          = db.Column(String(50), nullable=False)
    zip_code       = db.Column(String(20), nullable=False)
    country        = db.Column(String(100), nullable=False)
    address_type   = db.Column(EnumAsString(PanditAddressType, length=40), nullable=False,
                               default=PanditAddressType.CURRENT.value)
    created_at     = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at     = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    @property
    def full_address(self):
        return ', '.join(p for p in [self.street, self.city, self.state,
                                      self.zip_code, self.country] if p)


class PanditPhoto(db.Model):
    __tablename__ = 'pandit_photo'

    id         = db.Column(BigInteger, primary_key=True)
    pandit_id  = db.Column(BigInteger, db.ForeignKey('pandit.id'), nullable=False)
    photo      = db.Column(LargeBinary,nullable=False)
    mimetype   = db.Column(String(50), default='image/jpeg')   # extra column
    file_name  = db.Column(String(200))                        # extra column
    photo_type = db.Column(EnumAsString(PanditPhotoType, length=40), nullable=False,
                            default=PanditPhotoType.PROFILE.value)
    created_at = db.Column(DateTime, default=datetime.utcnow,nullable=False)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,nullable=False)

    @property
    def data_uri(self):
        if self.photo:
            return f'data:{self.mimetype};base64,{base64.b64encode(self.photo).decode()}'
        return None