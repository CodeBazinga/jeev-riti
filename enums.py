import enum


class UserType(enum.Enum):
    PUNDIT = "pundit"
    CUSTOMER = "customer"

    def __str__(self):
        return self.value


class PujaMode(enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"

    def __str__(self):
        return self.value


class RitualPackageType(enum.Enum):
    STANDARD = "STANDARD"
    COMPLETE = "COMPLETE"

    def __str__(self):
        return self.value


class PaymentProvider(enum.Enum):
    RAZORPAY = "RAZORPAY"
    CASH = "CASH"
    UPI = "UPI"
    BANK_TRANSFER = "BANK_TRANSFER"
    CHEQUE = "CHEQUE"
    ADJUSTMENT = "ADJUSTMENT"   # No real money, like waived, goodwill etc.

    def __str__(self):
        return self.value


class PaymentType(enum.Enum):
    FULL = "FULL"
    TOKEN = "TOKEN"
    REMAINING = "REMAINING"

    def __str__(self):
        return self.value


class PaymentStatus(enum.Enum):
    CREATED = "CREATED"
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

    def __str__(self):
        return self.value


class CartItemStatus(enum.Enum):
    ACTIVE = "ACTIVE"   # Ritual added to cart (Remain active until Booking confirmed)
    INACTIVE = "INACTIVE"   # When a ritual is unavailable/deprecated
    DELETED = "DELETED"     # Ritual removed from cart
    CONVERTED = "CONVERTED"     # Booking Confirmed

    def __str__(self):
        return self.value


class CheckoutStatus(enum.Enum):
    STARTED = "STARTED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CONVERTED = "CONVERTED"     # Booking Confirmed
    # CALCELLED = "CANCELLED"

    def __str__(self):
        return self.value


class BookingSource(enum.Enum):
    APP = "APP"  # Customer booked via your app / website
    WHATSAPP = "WHATSAPP"  # Booking came via WhatsApp
    PHONE = "PHONE"  # Call center / phone booking
    ADMIN = "ADMIN"  # Admin panel created
    PARTNER = "PARTNER"  # Partner / affiliate

    def __str__(self):
        return self.value


class BookingPaymentState(enum.Enum):
    PAID = "PAID"
    PAYMENT_DUE = "PAYMENT_DUE"

    def __str__(self):
        return self.value


class BookingStatus(enum.Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"

    def __str__(self):
        return self.value


class EmailStatus(enum.Enum):
    SENT = "SENT"
    FAILED = "FAILED"

    def __str__(self):
        return self.value


class PanditVerificationStatus(enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

    def __str__(self):
        return self.value
    
class AccountStatus(enum.Enum):
    ACTIVE = "Active"
    INACTIVE = "Inactive"
    SUSPENDED = "Suspended" 

    def __str__(self):
        return self.value   
    
class PanditPayoutStatus(enum.Enum):
    PENDING = "Pending"
    INTRANSIT = "INTRANSIT"
    COMPLETED = "Completed" 

    def __str__(self):
        return self.value       


class PanditAddressType(enum.Enum):
    CURRENT = "CURRENT"
    PERMANENT = "PERMANENT"
    OTHER = "OTHER"

    def __str__(self):
        return self.value


class PanditPhotoType(enum.Enum):
    PROFILE = "PROFILE"
    PUJA = "PUJA"

    def __str__(self):
        return self.value


class PanditVideoType(enum.Enum):
    INTRODUCTION = "INTRODUCTION"
    INTERVIEW = "INTERVIEW"
    PUJA = "PUJA"

    def __str__(self):
        return self.value
