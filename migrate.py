"""
migrate.py — Run once to apply all schema changes.
Usage: python migrate.py
Safe to re-run: existing columns are skipped gracefully.
"""
from app import create_app
from extensions import db

app = create_app()

PANDIT_COLUMNS = [
    "ALTER TABLE pandits ADD COLUMN email VARCHAR(150)",
    "ALTER TABLE pandits ADD COLUMN city VARCHAR(100)",
    "ALTER TABLE pandits ADD COLUMN address TEXT",
    "ALTER TABLE pandits ADD COLUMN experience_yrs INT DEFAULT 0",
    "ALTER TABLE pandits ADD COLUMN languages VARCHAR(200)",
    "ALTER TABLE pandits ADD COLUMN verification_status VARCHAR(20) DEFAULT 'Pending'",
    "ALTER TABLE pandits ADD COLUMN account_status VARCHAR(20) DEFAULT 'Active'",
    "ALTER TABLE pandits ADD COLUMN rejection_reason TEXT",
    "ALTER TABLE pandits ADD COLUMN suspension_reason TEXT",
    "ALTER TABLE pandits ADD COLUMN bank_name VARCHAR(100)",
    "ALTER TABLE pandits ADD COLUMN bank_account_no VARCHAR(30)",
    "ALTER TABLE pandits ADD COLUMN bank_ifsc VARCHAR(20)",
    "ALTER TABLE pandits ADD COLUMN bank_account_name VARCHAR(150)",
    "ALTER TABLE pandits ADD COLUMN upi_id VARCHAR(100)",
    "ALTER TABLE pandits ADD COLUMN rating FLOAT DEFAULT 0.0",
    "ALTER TABLE pandits ADD COLUMN total_earnings FLOAT DEFAULT 0.0",
    "ALTER TABLE pandits ADD COLUMN total_bookings_completed INT DEFAULT 0",
    "ALTER TABLE pandits ADD COLUMN commission_pct FLOAT DEFAULT 15.0",
    "ALTER TABLE pandits ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE pandits ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
]

CUSTOMER_COLUMNS = [
    "ALTER TABLE customers ADD COLUMN mobile VARCHAR(15)",
    "ALTER TABLE customers ADD COLUMN city VARCHAR(100)",
]

NEW_TABLES = [
    """CREATE TABLE IF NOT EXISTS customer_addresses (
        id INT AUTO_INCREMENT PRIMARY KEY,
        customer_id INT NOT NULL,
        reference_name VARCHAR(100) NOT NULL,
        street TEXT NOT NULL,
        city VARCHAR(100) NOT NULL,
        state VARCHAR(100) NOT NULL,
        zip_code VARCHAR(20) NOT NULL,
        country VARCHAR(100) DEFAULT 'India',
        is_active BOOLEAN DEFAULT TRUE,
        is_ritual_address BOOLEAN DEFAULT FALSE,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(id)
    )""",
    """CREATE TABLE IF NOT EXISTS checkout_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ritual_name VARCHAR(100) NOT NULL,
        customer_id INT NOT NULL,
        address_id INT,
        price FLOAT NOT NULL,
        status VARCHAR(30) DEFAULT 'Pending',
        contact_info VARCHAR(200),
        selected_date DATE,
        selected_time TIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (customer_id) REFERENCES customers(id),
        FOREIGN KEY (address_id) REFERENCES customer_addresses(id)
    )""",
    """CREATE TABLE IF NOT EXISTS pandit_documents (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pandit_id INT NOT NULL,
        doc_type VARCHAR(50) NOT NULL,
        filename VARCHAR(200) NOT NULL,
        is_verified BOOLEAN DEFAULT FALSE,
        notes TEXT,
        uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pandit_id) REFERENCES pandits(id)
    )""",
    """CREATE TABLE IF NOT EXISTS pandit_complaints (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pandit_id INT NOT NULL,
        booking_id INT,
        raised_by VARCHAR(150),
        subject VARCHAR(200) NOT NULL,
        description TEXT NOT NULL,
        status VARCHAR(20) DEFAULT 'Open',
        resolution TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pandit_id) REFERENCES pandits(id),
        FOREIGN KEY (booking_id) REFERENCES bookings(id)
    )""",
    """CREATE TABLE IF NOT EXISTS pandit_payouts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pandit_id INT NOT NULL,
        booking_id INT,
        amount FLOAT NOT NULL,
        status VARCHAR(20) DEFAULT 'Pending',
        method VARCHAR(50),
        reference VARCHAR(100),
        notes TEXT,
        paid_at DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (pandit_id) REFERENCES pandits(id),
        FOREIGN KEY (booking_id) REFERENCES bookings(id)
    )""",
]

BOOKING_COLUMNS = [
    "ALTER TABLE bookings ADD COLUMN checkout_item_id INT",
    "ALTER TABLE bookings ADD COLUMN address_id INT",
    "ALTER TABLE bookings ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
]

PAYMENT_COLUMNS = [
    "ALTER TABLE payments ADD COLUMN checkout_item_id INT",
    "ALTER TABLE payments ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
]


def run_sql(conn, statements, section):
    print(f"\n── {section} ──────────────────────────────────────")
    for sql in statements:
        # Extract a label for display
        label = sql.strip().split('\n')[0][:80]
        try:
            conn.execute(db.text(sql))
            conn.commit()
            print(f"  ✅ {label}")
        except Exception as e:
            err = str(e)
            if any(k in err for k in ['Duplicate column', '1060', 'already exists', '1050']):
                print(f"  ⏭  Already exists: {label}")
            else:
                print(f"  ❌ Error: {err[:120]}")


def run():
    with app.app_context():
        conn = db.engine.connect()
        run_sql(conn, PANDIT_COLUMNS,   "Alter pandits table")
        run_sql(conn, CUSTOMER_COLUMNS, "Alter customers table")
        run_sql(conn, BOOKING_COLUMNS,  "Alter bookings table")
        run_sql(conn, PAYMENT_COLUMNS,  "Alter payments table")
        run_sql(conn, NEW_TABLES,       "Create new tables")
        conn.close()
        print("\n✅ Migration complete! Restart Flask.\n")


if __name__ == '__main__':
    run()

# Run this at bottom of existing migrate.py — or call run() directly
RITUAL_TABLES = [
    """CREATE TABLE IF NOT EXISTS rituals (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        title       VARCHAR(200) NOT NULL UNIQUE,
        description TEXT,
        is_active   BOOLEAN DEFAULT TRUE,
        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS ritual_details (
        id               INT AUTO_INCREMENT PRIMARY KEY,
        ritual_id        INT NOT NULL UNIQUE,
        puja_vidhi       TEXT,
        puja_samagri     TEXT,
        puja_seasons     VARCHAR(300),
        num_pundits      INT DEFAULT 1,
        duration         VARCHAR(100),
        mode             VARCHAR(30) DEFAULT 'In-Person',
        ritual_metadata  TEXT,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (ritual_id) REFERENCES rituals(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS ritual_images (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        ritual_id  INT NOT NULL,
        file_name  VARCHAR(200) NOT NULL,
        mimetype   VARCHAR(50) DEFAULT 'image/jpeg',
        data       LONGBLOB,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (ritual_id) REFERENCES rituals(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS ritual_packages (
        id               INT AUTO_INCREMENT PRIMARY KEY,
        ritual_detail_id INT NOT NULL,
        package_type     VARCHAR(50) NOT NULL,
        description      TEXT,
        included         TEXT,
        not_included     TEXT,
        price            FLOAT NOT NULL,
        created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at       DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (ritual_detail_id) REFERENCES ritual_details(id) ON DELETE CASCADE
    )""",
]

BOOKING_RITUAL_COLS = [
    "ALTER TABLE bookings ADD COLUMN ritual_package_id INT",
    "ALTER TABLE checkout_items ADD COLUMN ritual_package_id INT",
]

if __name__ == '__main__':
    # Extend run() to also add ritual tables
    with app.app_context():
        conn = db.engine.connect()
        run_sql(conn, RITUAL_TABLES,       "Create Ritual tables")
        run_sql(conn, BOOKING_RITUAL_COLS, "Add ritual_package_id columns")
        conn.close()
        print("\n✅ Ritual migration complete!\n")

# ── Fix ritual_images.data column (BLOB → LONGBLOB) ──────────────────────────
FIX_IMAGE_BLOB = [
    "ALTER TABLE ritual_images MODIFY COLUMN data LONGBLOB",
]

if __name__ == '__main__':
    with app.app_context():
        conn = db.engine.connect()
        run_sql(conn, FIX_IMAGE_BLOB, "Fix ritual_images.data → LONGBLOB")
        conn.close()
        print("Done.\n")

# ── PanditAddress + PanditPhoto new tables ────────────────────────────────────
PANDIT_NEW_TABLES = [
    """CREATE TABLE IF NOT EXISTS pandit_addresses (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        pandit_id      INT NOT NULL,
        reference_name VARCHAR(100),
        street         TEXT NOT NULL,
        city           VARCHAR(100) NOT NULL,
        state          VARCHAR(100),
        zip_code       VARCHAR(20),
        country        VARCHAR(100) DEFAULT 'India',
        address_type   VARCHAR(20)  DEFAULT 'CURRENT',
        created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at     DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (pandit_id) REFERENCES pandits(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS pandit_photos (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        pandit_id  INT NOT NULL,
        photo      LONGBLOB NOT NULL,
        mimetype   VARCHAR(50) DEFAULT 'image/jpeg',
        file_name  VARCHAR(200),
        photo_type VARCHAR(20) DEFAULT 'PROFILE',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        FOREIGN KEY (pandit_id) REFERENCES pandits(id) ON DELETE CASCADE
    )""",
]

if __name__ == '__main__':
    with app.app_context():
        conn = db.engine.connect()
        run_sql(conn, PANDIT_NEW_TABLES, "Create pandit_addresses + pandit_photos")
        conn.close()
        print("Done.\n")
