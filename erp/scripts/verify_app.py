"""Verify JTCS ERP without binding a port (uses Flask test client + DB)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app
from app.services.auth_service import AuthService
from app.services.menu_service import MenuService


def main() -> None:
    app = create_app()
    client = app.test_client()

    health = client.get("/health")
    print("health", health.status_code, health.is_json)

    login_page = client.get("/login")
    print("login GET", login_page.status_code, b"Remember Me" in login_page.data)

    register_page = client.get("/register")
    print("register GET", register_page.status_code, b"Register New User" not in register_page.data)

    with app.app_context():
        auth = AuthService()
        print("administrator_exists", auth.administrator_exists())
        if auth.administrator_exists():
            dashboard = client.get("/dashboard")
            print("dashboard redirect when logged out", dashboard.status_code)
        nav = MenuService().get_navigation("Administrator")
        print("nav count", len(nav))


if __name__ == "__main__":
    main()
