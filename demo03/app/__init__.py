from pathlib import Path

from flask import Flask

from config import Config, DATA_DIR, INSTANCE_DIR


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    Path(INSTANCE_DIR).mkdir(parents=True, exist_ok=True)
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

    from app import db

    db.init_app(app)

    with app.app_context():
        db.init_db()
        db.ensure_default_users()

        from app.services.ingestion import ensure_demo_data

        ensure_demo_data()

    from app.auth import auth_bp
    from app.routes import page_bp
    from app.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(page_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    return app
