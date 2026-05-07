import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'ritual-booking-secret-key-2024-xK9mP2'
    # PostgreSQL connection — set DATABASE_URL in .env or environment
    # Format: postgresql+psycopg2://user:password@host:port/dbname
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('DATABASE_URL') or
        'postgresql+psycopg2://postgres:1234@localhost:5432/jv_db1'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEBUG = True
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 16 MB upload limit
