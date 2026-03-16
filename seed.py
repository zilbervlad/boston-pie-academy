from app import create_app
from app.extensions import db
from app.models import User

app = create_app()

with app.app_context():

    admin = User.query.filter_by(username="admin").first()

    if not admin:
        admin = User(
            name="Admin User",
            username="admin",
            role="admin"
        )
        admin.set_password("admin123")

        db.session.add(admin)
        db.session.commit()

        print("Admin created: admin / admin123")

    else:
        print("Admin already exists")