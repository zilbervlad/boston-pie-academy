from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

from app.extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="tm")
    store_number = db.Column(db.String(20), nullable=True)
    is_active_user = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    mit_profiles = db.relationship(
        "MITProfile",
        foreign_keys="MITProfile.user_id",
        backref="mit_user",
        lazy=True
    )

    coached_mits = db.relationship(
        "MITProfile",
        foreign_keys="MITProfile.coach_user_id",
        backref="coach_user",
        lazy=True
    )

    verified_mit_items = db.relationship(
        "MITLevelProgress",
        foreign_keys="MITLevelProgress.verified_by_user_id",
        backref="verified_by_user",
        lazy=True
    )

    mit_reviews_written = db.relationship(
        "MITReview",
        foreign_keys="MITReview.reviewer_user_id",
        backref="reviewer_user",
        lazy=True
    )

    mit_promotions_approved = db.relationship(
        "MITPromotion",
        foreign_keys="MITPromotion.approved_by_user_id",
        backref="approved_by_user",
        lazy=True
    )

    mit_action_items_owned = db.relationship(
        "MITActionPlanItem",
        foreign_keys="MITActionPlanItem.owner_user_id",
        backref="owner_user",
        lazy=True
    )

    mit_tasks_assigned = db.relationship(
        "MITTask",
        foreign_keys="MITTask.assigned_by_user_id",
        backref="assigned_by_user",
        lazy=True
    )

    binder_submissions_approved = db.relationship(
        "MITBinderSubmission",
        foreign_keys="MITBinderSubmission.approved_by_user_id",
        backref="approved_by_user",
        lazy=True
    )

    binder_sheet_approvals = db.relationship(
        "MITBinderSubmission",
        foreign_keys="MITBinderSubmission.sheet_approved_by_user_id",
        backref="sheet_approved_by_user",
        lazy=True
    )

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str):
        return check_password_hash(self.password_hash, password)

    def is_tm(self):
        return self.role == "tm"

    def is_mit(self):
        return self.role == "mit"

    def is_coach(self):
        return self.role == "coach"

    def is_admin(self):
        return self.role == "admin"

    def is_training_director(self):
        return self.role == "training_director"

    @property
    def is_active(self):
        return self.is_active_user


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --------------------------------------------------
# MIT STS MODELS
# --------------------------------------------------

class MITProfile(db.Model):
    __tablename__ = "mit_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    store_number = db.Column(db.String(20), nullable=True)
    coach_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    current_level = db.Column(db.Integer, nullable=False, default=1)
    target_level = db.Column(db.String(20), nullable=False, default="2")
    start_date = db.Column(db.Date, nullable=True)
    sts_status = db.Column(db.String(20), nullable=False, default="on_track")
    last_review_date = db.Column(db.Date, nullable=True)
    next_review_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    progress_items = db.relationship(
        "MITLevelProgress",
        backref="mit_profile",
        cascade="all, delete-orphan",
        lazy=True
    )

    reviews = db.relationship(
        "MITReview",
        backref="mit_profile",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="MITReview.review_date.desc()"
    )

    action_plans = db.relationship(
        "MITActionPlan",
        backref="mit_profile",
        cascade="all, delete-orphan",
        lazy=True
    )

    promotions = db.relationship(
        "MITPromotion",
        backref="mit_profile",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="MITPromotion.effective_date.desc()"
    )

    tasks = db.relationship(
        "MITTask",
        backref="mit_profile",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="MITTask.created_at.desc()"
    )

    binder_submissions = db.relationship(
        "MITBinderSubmission",
        backref="mit_profile",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<MITProfile user={self.user_id} level={self.current_level}>"


class MITLevelTemplate(db.Model):
    __tablename__ = "mit_level_templates"

    id = db.Column(db.Integer, primary_key=True)
    level_number = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(100), nullable=True)
    item_name = db.Column(db.String(255), nullable=False)
    item_description = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_required = db.Column(db.Boolean, default=True)
    source_ref = db.Column(db.String(255), nullable=True)

    progress_records = db.relationship(
        "MITLevelProgress",
        backref="template_item",
        cascade="all, delete-orphan",
        lazy=True
    )

    action_plan_items = db.relationship(
        "MITActionPlanItem",
        backref="related_template_item",
        lazy=True
    )

    tasks = db.relationship(
        "MITTask",
        backref="task_template_item",
        lazy=True
    )

    def __repr__(self):
        return f"<MITLevelTemplate level={self.level_number} item={self.item_name}>"


class MITLevelProgress(db.Model):
    __tablename__ = "mit_level_progress"

    id = db.Column(db.Integer, primary_key=True)
    mit_profile_id = db.Column(db.Integer, db.ForeignKey("mit_profiles.id"), nullable=False)
    template_item_id = db.Column(db.Integer, db.ForeignKey("mit_level_templates.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="not_started")
    completed_date = db.Column(db.Date, nullable=True)
    verified_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("mit_profile_id", "template_item_id", name="uq_mit_profile_template_item"),
    )

    def __repr__(self):
        return f"<MITLevelProgress mit={self.mit_profile_id} template={self.template_item_id} status={self.status}>"


class MITReview(db.Model):
    __tablename__ = "mit_reviews"

    id = db.Column(db.Integer, primary_key=True)
    mit_profile_id = db.Column(db.Integer, db.ForeignKey("mit_profiles.id"), nullable=False)
    reviewer_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    review_date = db.Column(db.Date, nullable=False)
    current_level = db.Column(db.Integer, nullable=False)
    completion_percent = db.Column(db.Integer, default=0)
    readiness_status = db.Column(db.String(20), nullable=False, default="not_ready")
    strengths = db.Column(db.Text, nullable=True)
    gaps = db.Column(db.Text, nullable=True)
    next_steps = db.Column(db.Text, nullable=True)
    summary_notes = db.Column(db.Text, nullable=True)
    next_followup_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    action_plans = db.relationship(
        "MITActionPlan",
        backref="created_from_review",
        lazy=True
    )

    tasks = db.relationship(
        "MITTask",
        backref="related_review",
        lazy=True
    )

    def __repr__(self):
        return f"<MITReview mit={self.mit_profile_id} date={self.review_date}>"


class MITActionPlan(db.Model):
    __tablename__ = "mit_action_plans"

    id = db.Column(db.Integer, primary_key=True)
    mit_profile_id = db.Column(db.Integer, db.ForeignKey("mit_profiles.id"), nullable=False)
    created_from_review_id = db.Column(db.Integer, db.ForeignKey("mit_reviews.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="open")
    start_date = db.Column(db.Date, nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items = db.relationship(
        "MITActionPlanItem",
        backref="action_plan",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="MITActionPlanItem.sort_order.asc(), MITActionPlanItem.id.asc()"
    )

    def __repr__(self):
        return f"<MITActionPlan mit={self.mit_profile_id} status={self.status}>"


class MITActionPlanItem(db.Model):
    __tablename__ = "mit_action_plan_items"

    id = db.Column(db.Integer, primary_key=True)
    action_plan_id = db.Column(db.Integer, db.ForeignKey("mit_action_plans.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    related_template_item_id = db.Column(db.Integer, db.ForeignKey("mit_level_templates.id"), nullable=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="open")
    note = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<MITActionPlanItem plan={self.action_plan_id} title={self.title}>"


class MITPromotion(db.Model):
    __tablename__ = "mit_promotions"

    id = db.Column(db.Integer, primary_key=True)
    mit_profile_id = db.Column(db.Integer, db.ForeignKey("mit_profiles.id"), nullable=False)
    from_level = db.Column(db.Integer, nullable=False)
    to_level = db.Column(db.String(20), nullable=False)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    effective_date = db.Column(db.Date, nullable=False)
    note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<MITPromotion mit={self.mit_profile_id} from={self.from_level} to={self.to_level}>"


class MITTask(db.Model):
    __tablename__ = "mit_tasks"

    id = db.Column(db.Integer, primary_key=True)
    mit_profile_id = db.Column(db.Integer, db.ForeignKey("mit_profiles.id"), nullable=False)
    mit_review_id = db.Column(db.Integer, db.ForeignKey("mit_reviews.id"), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    related_template_item_id = db.Column(db.Integer, db.ForeignKey("mit_level_templates.id"), nullable=True)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    due_date = db.Column(db.Date, nullable=True)
    priority = db.Column(db.String(20), nullable=False, default="medium")
    status = db.Column(db.String(20), nullable=False, default="open")
    completed_at = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<MITTask mit={self.mit_profile_id} title={self.title}>"


# --------------------------------------------------
# MIT BINDER MODELS
# --------------------------------------------------

class MITBinderTemplate(db.Model):
    __tablename__ = "mit_binder_templates"

    id = db.Column(db.Integer, primary_key=True)
    level_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    template_type = db.Column(db.String(50), nullable=False)
    instructions = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    fields = db.relationship(
        "MITBinderField",
        backref="template",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="MITBinderField.sort_order.asc(), MITBinderField.id.asc()"
    )

    submissions = db.relationship(
        "MITBinderSubmission",
        backref="template",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<MITBinderTemplate level={self.level_number} title={self.title}>"


class MITBinderField(db.Model):
    __tablename__ = "mit_binder_fields"

    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey("mit_binder_templates.id"), nullable=False)
    label = db.Column(db.String(255), nullable=False)
    field_type = db.Column(db.String(50), nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    entries = db.relationship(
        "MITBinderEntry",
        backref="field",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<MITBinderField template={self.template_id} label={self.label}>"


class MITBinderSubmission(db.Model):
    __tablename__ = "mit_binder_submissions"

    id = db.Column(db.Integer, primary_key=True)
    mit_profile_id = db.Column(db.Integer, db.ForeignKey("mit_profiles.id"), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey("mit_binder_templates.id"), nullable=False)
    status = db.Column(db.String(20), default="in_progress")
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    sheet_approved_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    sheet_approved_at = db.Column(db.DateTime, nullable=True)

    entries = db.relationship(
        "MITBinderEntry",
        backref="submission",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<MITBinderSubmission mit={self.mit_profile_id} template={self.template_id}>"


class MITBinderEntry(db.Model):
    __tablename__ = "mit_binder_entries"

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey("mit_binder_submissions.id"), nullable=False)
    field_id = db.Column(db.Integer, db.ForeignKey("mit_binder_fields.id"), nullable=False)
    row_index = db.Column(db.Integer, default=0)
    value = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"<MITBinderEntry submission={self.submission_id} field={self.field_id} row={self.row_index}>"