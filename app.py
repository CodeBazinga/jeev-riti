import os
from flask import Flask
from config import Config
from extensions import db
from routes.main import main_bp
from routes.bookings import bookings_bp
from routes.admin import admin_bp
from routes.payments import payments_bp
from routes.customers import customers_bp
from routes.rituals import rituals_bp
from routes.custom_rituals import custom_rituals_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Guarantee secret key is always set
    app.secret_key = app.config.get('SECRET_KEY') or os.urandom(24)

    db.init_app(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(bookings_bp,  url_prefix='/bookings')
    app.register_blueprint(admin_bp,     url_prefix='/admin')
    app.register_blueprint(payments_bp,  url_prefix='/payments')
    app.register_blueprint(customers_bp, url_prefix='/customers')
    app.register_blueprint(rituals_bp,   url_prefix='/rituals')
    app.register_blueprint(custom_rituals_bp, url_prefix='/custom-rituals')

    with app.app_context():
        db.create_all()

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
