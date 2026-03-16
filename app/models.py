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

    progress_records = db.relationship(
        "LessonProgress",
        backref="user",
        cascade="all, delete-orphan",
        lazy=True
    )

    assignments = db.relationship(
        "TrackAssignment",
        foreign_keys="TrackAssignment.user_id",
        backref="user",
        cascade="all, delete-orphan",
        lazy=True
    )

    assigned_tracks_created = db.relationship(
        "TrackAssignment",
        foreign_keys="TrackAssignment.assigned_by_user_id",
        backref="assigned_by_user",
        lazy=True
    )

    quiz_attempts = db.relationship(
        "QuizAttempt",
        backref="user",
        cascade="all, delete-orphan",
        lazy=True
    )

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


class TrainingTrack(db.Model):
    __tablename__ = "training_tracks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    audience_role = db.Column(db.String(50), nullable=True)
    level_label = db.Column(db.String(100), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    modules = db.relationship(
        "TrainingModule",
        backref="track",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="TrainingModule.sort_order.asc(), TrainingModule.id.asc()",
    )

    assignments = db.relationship(
        "TrackAssignment",
        backref="track",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<TrainingTrack {self.title}>"


class TrainingModule(db.Model):
    __tablename__ = "training_modules"

    id = db.Column(db.Integer, primary_key=True)
    track_id = db.Column(db.Integer, db.ForeignKey("training_tracks.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lessons = db.relationship(
        "Lesson",
        backref="module",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="Lesson.sort_order.asc(), Lesson.id.asc()",
    )

    def __repr__(self):
        return f"<TrainingModule {self.title}>"


class Lesson(db.Model):
    __tablename__ = "lessons"

    id = db.Column(db.Integer, primary_key=True)
    module_id = db.Column(db.Integer, db.ForeignKey("training_modules.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), nullable=False)
    lesson_type = db.Column(db.String(50), default="text")
    summary = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=True)
    video_url = db.Column(db.String(500), nullable=True)
    passing_score = db.Column(db.Integer, default=80)
    requires_quiz = db.Column(db.Boolean, default=False)
    requires_signoff = db.Column(db.Boolean, default=False)
    signoff_role = db.Column(db.String(50), nullable=True)
    estimated_minutes = db.Column(db.Integer, default=5)
    status = db.Column(db.String(20), default="draft")
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    progress_records = db.relationship(
        "LessonProgress",
        backref="lesson",
        cascade="all, delete-orphan",
        lazy=True
    )

    quiz = db.relationship(
        "Quiz",
        backref="lesson",
        uselist=False,
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<Lesson {self.title}>"


class LessonProgress(db.Model):
    __tablename__ = "lesson_progress"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="not_started")
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("user_id", "lesson_id", name="uq_user_lesson_progress"),
    )

    def __repr__(self):
        return f"<LessonProgress user={self.user_id} lesson={self.lesson_id} status={self.status}>"


class TrackAssignment(db.Model):
    __tablename__ = "track_assignments"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    track_id = db.Column(db.Integer, db.ForeignKey("training_tracks.id"), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint("user_id", "track_id", name="uq_user_track_assignment"),
    )

    def __repr__(self):
        return f"<TrackAssignment user={self.user_id} track={self.track_id}>"


class Quiz(db.Model):
    __tablename__ = "quizzes"

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id"), nullable=False, unique=True)
    title = db.Column(db.String(200), nullable=False)
    passing_score = db.Column(db.Integer, default=80)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship(
        "QuizQuestion",
        backref="quiz",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="QuizQuestion.sort_order.asc(), QuizQuestion.id.asc()",
    )

    attempts = db.relationship(
        "QuizAttempt",
        backref="quiz",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<Quiz {self.title}>"


class QuizQuestion(db.Model):
    __tablename__ = "quiz_questions"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    choices = db.relationship(
        "QuizChoice",
        backref="question",
        cascade="all, delete-orphan",
        lazy=True,
        order_by="QuizChoice.sort_order.asc(), QuizChoice.id.asc()",
    )

    def __repr__(self):
        return f"<QuizQuestion {self.id}>"


class QuizChoice(db.Model):
    __tablename__ = "quiz_choices"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("quiz_questions.id"), nullable=False)
    choice_text = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)

    def __repr__(self):
        return f"<QuizChoice {self.id}>"


class QuizAttempt(db.Model):
    __tablename__ = "quiz_attempts"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    score = db.Column(db.Integer, default=0)
    passed = db.Column(db.Boolean, default=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    answers = db.relationship(
        "QuizAttemptAnswer",
        backref="attempt",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<QuizAttempt quiz={self.quiz_id} user={self.user_id} score={self.score}>"


class QuizAttemptAnswer(db.Model):
    __tablename__ = "quiz_attempt_answers"

    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("quiz_attempts.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("quiz_questions.id"), nullable=False)
    selected_choice_id = db.Column(db.Integer, db.ForeignKey("quiz_choices.id"), nullable=True)
    is_correct = db.Column(db.Boolean, default=False)

    question = db.relationship("QuizQuestion", foreign_keys=[question_id])
    selected_choice = db.relationship("QuizChoice", foreign_keys=[selected_choice_id])

    def __repr__(self):
        return f"<QuizAttemptAnswer attempt={self.attempt_id} question={self.question_id}>"


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