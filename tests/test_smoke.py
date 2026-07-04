import tempfile
import unittest
from pathlib import Path

from app import create_app
from app.extensions import db
from app.models import MITProfile, User


class AcademySmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "academy-test.db"
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
            "WTF_CSRF_ENABLED": False,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp_dir.cleanup()

    def create_user(self, username, password, role, name=None):
        user = User(
            name=name or username.title(),
            username=username,
            role=role,
            is_active_user=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        return user

    def login(self, username, password):
        return self.client.post(
            "/auth/login",
            data={"username": username, "password": password},
            follow_redirects=False,
        )

    def test_create_app_boots_with_temporary_sqlite_database(self):
        with self.app.app_context():
            self.assertEqual(User.query.count(), 0)

    def test_core_mit_sts_routes_require_login(self):
        routes = [
            "/mit-sts/",
            "/mit-sts/dashboard",
            "/mit-sts/list",
            "/mit-sts/templates",
            "/mit-sts/users",
            "/mit-sts/promotion-queue",
        ]

        for route in routes:
            with self.subTest(route=route):
                response = self.client.get(route, follow_redirects=False)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/auth/login", response.headers["Location"])

    def test_seeded_admin_login_reaches_dashboard(self):
        with self.app.app_context():
            self.create_user("admin", "admin123", "admin", name="Admin User")
            db.session.commit()

        response = self.login("admin", "admin123")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/mit-sts/dashboard", response.headers["Location"])

        dashboard = self.client.get("/mit-sts/dashboard")
        self.assertEqual(dashboard.status_code, 200)

    def test_mit_user_routes_to_own_profile(self):
        with self.app.app_context():
            mit_user = self.create_user("mit", "mit123", "mit", name="MIT User")
            profile = MITProfile(
                user_id=mit_user.id,
                store_number="3001",
                current_level=1,
                target_level="2",
            )
            db.session.add(profile)
            db.session.commit()
            profile_id = profile.id

        login_response = self.login("mit", "mit123")
        self.assertEqual(login_response.status_code, 302)
        self.assertIn("/mit-sts/my", login_response.headers["Location"])

        my_response = self.client.get("/mit-sts/my", follow_redirects=False)
        self.assertEqual(my_response.status_code, 302)
        self.assertIn(f"/mit-sts/{profile_id}", my_response.headers["Location"])

        profile_response = self.client.get(f"/mit-sts/{profile_id}")
        self.assertEqual(profile_response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
