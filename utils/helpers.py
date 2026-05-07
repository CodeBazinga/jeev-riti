import random
import string
from datetime import datetime


def generate_booking_ref():
    date_str = datetime.now().strftime('%Y%m%d')
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f'RB-{date_str}-{suffix}'
