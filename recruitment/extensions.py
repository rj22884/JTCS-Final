"""Shared Flask extensions."""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per minute"])


@login_manager.user_loader
def load_user(user_id):
    from recruitment.models import AdminUser

    try:
        return db.session.get(AdminUser, int(user_id))
    except (TypeError, ValueError):
        return None
