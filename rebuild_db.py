from app import create_app
from app.extensions import db
from app.models import User, MITProfile

app = create_app()

with app.app_context():
    print("Resetting database...")

    db.drop_all()
    db.create_all()

    # -----------------------
    # Create Admin
    # -----------------------
    admin = User(
        name="Admin",
        username="admin",
        role="admin",
        store_number="0000",
        is_active_user=True,
    )
    admin.set_password("admin123")
    db.session.add(admin)

    # -----------------------
    # Create MIT User
    # -----------------------
    mit_user = User(
        name="Danny Talic",
        username="danny",
        role="mit",
        store_number="3001",
        is_active_user=True,
    )
    mit_user.set_password("danny123")
    db.session.add(mit_user)
    db.session.flush()

    # -----------------------
    # Create MIT Profile
    # -----------------------
    profile = MITProfile(
        user_id=mit_user.id,
        store_number="3001",
        current_level=1,
        target_level="2",
    )
    db.session.add(profile)

    db.session.commit()

    print("Done.")
    print("Admin login -> admin / admin123")
    print("MIT login   -> danny / danny123")
    print("MIT Profile ID:", profile.id)