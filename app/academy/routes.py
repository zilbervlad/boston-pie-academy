from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    User,
    TrainingTrack,
    TrainingModule,
    Lesson,
    LessonProgress,
    TrackAssignment,
    Quiz,
    QuizQuestion,
    QuizChoice,
    QuizAttempt,
    QuizAttemptAnswer,
)

academy_bp = Blueprint("academy", __name__, url_prefix="/academy")


# --------------------------------------------------
# ROLE HELPERS
# --------------------------------------------------

def admin_required():
    return current_user.is_authenticated and current_user.role in ["admin", "training_director"]


def can_manage_users():
    return current_user.is_authenticated and current_user.role in ["coach", "admin", "training_director"]


def can_manage_tracks():
    return current_user.is_authenticated and current_user.role in ["admin", "training_director"]


def can_manage_assignments():
    return current_user.is_authenticated and current_user.role in ["admin", "training_director"]


# --------------------------------------------------
# PROGRESS HELPERS
# --------------------------------------------------

def calculate_track_progress(user_id, track):
    lessons = []
    for module in track.modules:
        for lesson in module.lessons:
            if lesson.is_active:
                lessons.append(lesson)

    if not lessons:
        return 0

    lesson_ids = [lesson.id for lesson in lessons]

    completed_count = LessonProgress.query.filter(
        LessonProgress.user_id == user_id,
        LessonProgress.lesson_id.in_(lesson_ids),
        LessonProgress.status == "completed"
    ).count()

    return round((completed_count / len(lessons)) * 100)


def get_or_create_progress(user_id, lesson_id):
    progress = LessonProgress.query.filter_by(user_id=user_id, lesson_id=lesson_id).first()
    if not progress:
        progress = LessonProgress(
            user_id=user_id,
            lesson_id=lesson_id,
            status="not_started",
        )
        db.session.add(progress)
        db.session.commit()
    return progress


def user_can_access_track(user, track_id):
    if user.role in ["coach", "admin", "training_director"]:
        return True

    if user.role == "tm":
        assignment = TrackAssignment.query.filter_by(user_id=user.id, track_id=track_id).first()
        return assignment is not None

    return False


# --------------------------------------------------
# DASHBOARD / LIBRARY / MY TRAINING
# --------------------------------------------------

@academy_bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "tm":
        return redirect(url_for("academy.my_training"))

    if current_user.role == "mit":
        return redirect(url_for("mit_sts.my_mit"))

    tracks = TrainingTrack.query.order_by(
        TrainingTrack.sort_order.asc(),
        TrainingTrack.title.asc()
    ).all()

    track_progress = {
        track.id: calculate_track_progress(current_user.id, track)
        for track in tracks
    }

    completed_lessons = LessonProgress.query.filter_by(
        user_id=current_user.id,
        status="completed"
    ).count()

    in_progress_lessons = LessonProgress.query.filter_by(
        user_id=current_user.id,
        status="in_progress"
    ).count()

    employee_count = User.query.filter(User.role.in_(["tm", "mit"])).count()
    assignment_count = TrackAssignment.query.count()

    return render_template(
        "academy/dashboard.html",
        user=current_user,
        tracks=tracks,
        track_progress=track_progress,
        completed_lessons=completed_lessons,
        in_progress_lessons=in_progress_lessons,
        employee_count=employee_count,
        assignment_count=assignment_count,
    )


@academy_bp.route("/tracks")
@login_required
def tracks_library():
    if current_user.role == "tm":
        return redirect(url_for("academy.my_training"))

    if current_user.role == "mit":
        return redirect(url_for("mit_sts.my_mit"))

    if current_user.role == "coach":
        return redirect(url_for("academy.dashboard"))

    tracks = TrainingTrack.query.order_by(
        TrainingTrack.sort_order.asc(),
        TrainingTrack.title.asc()
    ).all()

    track_progress = {
        track.id: calculate_track_progress(current_user.id, track)
        for track in tracks
    }

    return render_template(
        "academy/tracks_library.html",
        tracks=tracks,
        track_progress=track_progress,
        user=current_user
    )


@academy_bp.route("/my-training")
@login_required
def my_training():
    if current_user.role == "mit":
        return redirect(url_for("mit_sts.my_mit"))

    if current_user.role != "tm":
        return redirect(url_for("academy.dashboard"))

    assignments = TrackAssignment.query.filter_by(user_id=current_user.id).all()
    assigned_track_ids = [assignment.track_id for assignment in assignments]

    tracks = TrainingTrack.query.filter(
        TrainingTrack.id.in_(assigned_track_ids)
    ).order_by(
        TrainingTrack.sort_order.asc(),
        TrainingTrack.title.asc()
    ).all() if assigned_track_ids else []

    track_progress = {
        track.id: calculate_track_progress(current_user.id, track)
        for track in tracks
    }

    return render_template(
        "academy/my_training.html",
        tracks=tracks,
        track_progress=track_progress,
        user=current_user,
    )


# --------------------------------------------------
# TRACKS
# --------------------------------------------------

@academy_bp.route("/tracks/new", methods=["GET", "POST"])
@login_required
def new_track():
    if not can_manage_tracks():
        flash("You do not have permission to manage tracks.", "danger")
        return redirect(url_for("academy.dashboard"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = request.form.get("slug", "").strip()
        description = request.form.get("description", "").strip()
        audience_role = request.form.get("audience_role", "").strip()
        level_label = request.form.get("level_label", "").strip()
        sort_order = request.form.get("sort_order", "0").strip()

        if not title or not slug:
            flash("Title and slug are required.", "danger")
            return redirect(url_for("academy.new_track"))

        existing = TrainingTrack.query.filter_by(slug=slug).first()
        if existing:
            flash("Slug already exists.", "danger")
            return redirect(url_for("academy.new_track"))

        try:
            sort_order = int(sort_order)
        except ValueError:
            sort_order = 0

        track = TrainingTrack(
            title=title,
            slug=slug,
            description=description or None,
            audience_role=audience_role or None,
            level_label=level_label or None,
            sort_order=sort_order,
        )

        db.session.add(track)
        db.session.commit()

        flash("Training track created successfully.", "success")
        return redirect(url_for("academy.tracks_library"))

    return render_template(
        "academy/track_form.html",
        page_title="Create Training Track",
        submit_label="Create Track",
        track=None,
        user=current_user,
    )


@academy_bp.route("/tracks/<int:track_id>")
@login_required
def view_track(track_id):
    track = TrainingTrack.query.get_or_404(track_id)

    if current_user.role == "tm" and not user_can_access_track(current_user, track.id):
        flash("You do not have access to that training track.", "danger")
        return redirect(url_for("academy.my_training"))

    if current_user.role == "mit":
        return redirect(url_for("mit_sts.my_mit"))

    module_progress = {}
    for module in track.modules:
        active_lessons = [lesson for lesson in module.lessons if lesson.is_active]
        if not active_lessons:
            module_progress[module.id] = 0
            continue

        lesson_ids = [lesson.id for lesson in active_lessons]
        completed_count = LessonProgress.query.filter(
            LessonProgress.user_id == current_user.id,
            LessonProgress.lesson_id.in_(lesson_ids),
            LessonProgress.status == "completed"
        ).count()

        module_progress[module.id] = round((completed_count / len(active_lessons)) * 100)

    overall_progress = calculate_track_progress(current_user.id, track)

    return render_template(
        "academy/track_detail.html",
        track=track,
        module_progress=module_progress,
        overall_progress=overall_progress,
        user=current_user,
    )


@academy_bp.route("/tracks/<int:track_id>/edit", methods=["GET", "POST"])
@login_required
def edit_track(track_id):
    if not can_manage_tracks():
        flash("You do not have permission to manage tracks.", "danger")
        return redirect(url_for("academy.dashboard"))

    track = TrainingTrack.query.get_or_404(track_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = request.form.get("slug", "").strip()
        description = request.form.get("description", "").strip()
        audience_role = request.form.get("audience_role", "").strip()
        level_label = request.form.get("level_label", "").strip()
        sort_order = request.form.get("sort_order", "0").strip()

        if not title or not slug:
            flash("Title and slug are required.", "danger")
            return redirect(url_for("academy.edit_track", track_id=track.id))

        duplicate = TrainingTrack.query.filter(
            TrainingTrack.slug == slug,
            TrainingTrack.id != track.id
        ).first()
        if duplicate:
            flash("Slug already exists.", "danger")
            return redirect(url_for("academy.edit_track", track_id=track.id))

        try:
            sort_order = int(sort_order)
        except ValueError:
            sort_order = 0

        track.title = title
        track.slug = slug
        track.description = description or None
        track.audience_role = audience_role or None
        track.level_label = level_label or None
        track.sort_order = sort_order

        db.session.commit()

        flash("Training track updated successfully.", "success")
        return redirect(url_for("academy.view_track", track_id=track.id))

    return render_template(
        "academy/track_form.html",
        page_title="Edit Training Track",
        submit_label="Save Changes",
        track=track,
        user=current_user,
    )


# --------------------------------------------------
# MODULES
# --------------------------------------------------

@academy_bp.route("/tracks/<int:track_id>/modules/new", methods=["GET", "POST"])
@login_required
def new_module(track_id):
    if not can_manage_tracks():
        flash("You do not have permission to manage modules.", "danger")
        return redirect(url_for("academy.dashboard"))

    track = TrainingTrack.query.get_or_404(track_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        sort_order = request.form.get("sort_order", "0").strip()

        if not title:
            flash("Module title is required.", "danger")
            return redirect(url_for("academy.new_module", track_id=track.id))

        try:
            sort_order = int(sort_order)
        except ValueError:
            sort_order = 0

        module = TrainingModule(
            track_id=track.id,
            title=title,
            description=description or None,
            sort_order=sort_order,
        )

        db.session.add(module)
        db.session.commit()

        flash("Module created successfully.", "success")
        return redirect(url_for("academy.view_track", track_id=track.id))

    return render_template(
        "academy/module_form.html",
        track=track,
        module=None,
        page_title="Create Module",
        submit_label="Create Module",
        user=current_user,
    )


@academy_bp.route("/modules/<int:module_id>/edit", methods=["GET", "POST"])
@login_required
def edit_module(module_id):
    if not can_manage_tracks():
        flash("You do not have permission to manage modules.", "danger")
        return redirect(url_for("academy.dashboard"))

    module = TrainingModule.query.get_or_404(module_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        sort_order = request.form.get("sort_order", "0").strip()

        if not title:
            flash("Module title is required.", "danger")
            return redirect(url_for("academy.edit_module", module_id=module.id))

        try:
            sort_order = int(sort_order)
        except ValueError:
            sort_order = 0

        module.title = title
        module.description = description or None
        module.sort_order = sort_order

        db.session.commit()

        flash("Module updated successfully.", "success")
        return redirect(url_for("academy.view_track", track_id=module.track_id))

    return render_template(
        "academy/module_form.html",
        track=module.track,
        module=module,
        page_title="Edit Module",
        submit_label="Save Changes",
        user=current_user,
    )


# --------------------------------------------------
# LESSONS
# --------------------------------------------------

@academy_bp.route("/modules/<int:module_id>/lessons/new", methods=["GET", "POST"])
@login_required
def new_lesson(module_id):
    if not can_manage_tracks():
        flash("You do not have permission to manage lessons.", "danger")
        return redirect(url_for("academy.dashboard"))

    module = TrainingModule.query.get_or_404(module_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        slug = request.form.get("slug", "").strip()
        lesson_type = request.form.get("lesson_type", "text").strip()
        summary = request.form.get("summary", "").strip()
        content = request.form.get("content", "").strip()
        video_url = request.form.get("video_url", "").strip()
        passing_score = request.form.get("passing_score", "80").strip()
        requires_quiz = request.form.get("requires_quiz") == "on"
        requires_signoff = request.form.get("requires_signoff") == "on"
        signoff_role = request.form.get("signoff_role", "").strip()
        estimated_minutes = request.form.get("estimated_minutes", "5").strip()
        status = request.form.get("status", "draft").strip()
        sort_order = request.form.get("sort_order", "0").strip()

        if not title or not slug:
            flash("Lesson title and slug are required.", "danger")
            return redirect(url_for("academy.new_lesson", module_id=module.id))

        try:
            passing_score = int(passing_score)
        except ValueError:
            passing_score = 80

        try:
            estimated_minutes = int(estimated_minutes)
        except ValueError:
            estimated_minutes = 5

        try:
            sort_order = int(sort_order)
        except ValueError:
            sort_order = 0

        lesson = Lesson(
            module_id=module.id,
            title=title,
            slug=slug,
            lesson_type=lesson_type or "text",
            summary=summary or None,
            content=content or None,
            video_url=video_url or None,
            passing_score=passing_score,
            requires_quiz=requires_quiz,
            requires_signoff=requires_signoff,
            signoff_role=signoff_role or None,
            estimated_minutes=estimated_minutes,
            status=status or "draft",
            sort_order=sort_order,
        )

        db.session.add(lesson)
        db.session.commit()

        flash("Lesson created successfully.", "success")
        return redirect(url_for("academy.view_track", track_id=module.track_id))

    return render_template(
        "academy/lesson_form.html",
        module=module,
        lesson=None,
        page_title="Create Lesson",
        submit_label="Create Lesson",
        user=current_user,
    )


@academy_bp.route("/lessons/<int:lesson_id>/edit", methods=["GET", "POST"])
@login_required
def edit_lesson(lesson_id):
    if not can_manage_tracks():
        flash("You do not have permission to manage lessons.", "danger")
        return redirect(url_for("academy.dashboard"))

    lesson = Lesson.query.get_or_404(lesson_id)

    if request.method == "POST":
        lesson.title = request.form.get("title", "").strip()
        lesson.slug = request.form.get("slug", "").strip()
        lesson.lesson_type = request.form.get("lesson_type", "text").strip()
        lesson.summary = request.form.get("summary", "").strip() or None
        lesson.content = request.form.get("content", "").strip() or None
        lesson.video_url = request.form.get("video_url", "").strip() or None
        lesson.requires_quiz = request.form.get("requires_quiz") == "on"
        lesson.requires_signoff = request.form.get("requires_signoff") == "on"
        lesson.signoff_role = request.form.get("signoff_role", "").strip() or None
        lesson.status = request.form.get("status", "draft").strip() or "draft"

        try:
            lesson.passing_score = int(request.form.get("passing_score", "80").strip())
        except ValueError:
            lesson.passing_score = 80

        try:
            lesson.estimated_minutes = int(request.form.get("estimated_minutes", "5").strip())
        except ValueError:
            lesson.estimated_minutes = 5

        try:
            lesson.sort_order = int(request.form.get("sort_order", "0").strip())
        except ValueError:
            lesson.sort_order = 0

        db.session.commit()

        flash("Lesson updated successfully.", "success")
        return redirect(url_for("academy.view_track", track_id=lesson.module.track_id))

    return render_template(
        "academy/lesson_form.html",
        module=lesson.module,
        lesson=lesson,
        page_title="Edit Lesson",
        submit_label="Save Changes",
        user=current_user,
    )


@academy_bp.route("/lessons/<int:lesson_id>")
@login_required
def view_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)
    track_id = lesson.module.track_id

    if current_user.role == "mit":
        return redirect(url_for("mit_sts.my_mit"))

    if current_user.role == "tm" and not user_can_access_track(current_user, track_id):
        flash("You do not have access to that lesson.", "danger")
        return redirect(url_for("academy.my_training"))

    progress = get_or_create_progress(current_user.id, lesson.id)

    if progress.status == "not_started":
        progress.status = "in_progress"
        progress.started_at = datetime.utcnow()
        db.session.commit()

    previous_lesson = None
    next_lesson = None

    lessons_in_module = [l for l in lesson.module.lessons if l.is_active]
    lessons_in_module.sort(key=lambda x: (x.sort_order, x.id))

    for index, item in enumerate(lessons_in_module):
        if item.id == lesson.id:
            if index > 0:
                previous_lesson = lessons_in_module[index - 1]
            if index < len(lessons_in_module) - 1:
                next_lesson = lessons_in_module[index + 1]
            break

    latest_quiz_attempt = None
    if lesson.quiz:
        latest_quiz_attempt = QuizAttempt.query.filter_by(
            quiz_id=lesson.quiz.id,
            user_id=current_user.id
        ).order_by(QuizAttempt.submitted_at.desc()).first()

    return render_template(
        "academy/lesson_detail.html",
        lesson=lesson,
        progress=progress,
        previous_lesson=previous_lesson,
        next_lesson=next_lesson,
        latest_quiz_attempt=latest_quiz_attempt,
        user=current_user,
    )


@academy_bp.route("/lessons/<int:lesson_id>/complete", methods=["POST"])
@login_required
def complete_lesson(lesson_id):
    lesson = Lesson.query.get_or_404(lesson_id)

    if current_user.role == "mit":
        return redirect(url_for("mit_sts.my_mit"))

    if current_user.role == "tm" and not user_can_access_track(current_user, lesson.module.track_id):
        flash("You do not have access to that lesson.", "danger")
        return redirect(url_for("academy.my_training"))

    progress = get_or_create_progress(current_user.id, lesson.id)

    if lesson.requires_quiz and lesson.quiz:
        latest_attempt = QuizAttempt.query.filter_by(
            quiz_id=lesson.quiz.id,
            user_id=current_user.id
        ).order_by(QuizAttempt.submitted_at.desc()).first()

        if not latest_attempt or not latest_attempt.passed:
            flash("You must pass the quiz before completing this lesson.", "danger")
            return redirect(url_for("academy.view_lesson", lesson_id=lesson.id))

    progress.status = "completed"
    progress.completed_at = datetime.utcnow()
    db.session.commit()

    flash("Lesson marked complete.", "success")
    return redirect(url_for("academy.view_lesson", lesson_id=lesson.id))


# --------------------------------------------------
# QUIZZES
# --------------------------------------------------

@academy_bp.route("/lessons/<int:lesson_id>/quiz/new", methods=["GET", "POST"])
@login_required
def new_quiz(lesson_id):
    if not can_manage_tracks():
        flash("You do not have permission to manage quizzes.", "danger")
        return redirect(url_for("academy.dashboard"))

    lesson = Lesson.query.get_or_404(lesson_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        passing_score = request.form.get("passing_score", "80").strip()

        if not title:
            flash("Quiz title is required.", "danger")
            return redirect(url_for("academy.new_quiz", lesson_id=lesson.id))

        try:
            passing_score = int(passing_score)
        except ValueError:
            passing_score = 80

        quiz = Quiz(
            lesson_id=lesson.id,
            title=title,
            passing_score=passing_score,
        )

        db.session.add(quiz)
        db.session.commit()

        flash("Quiz created successfully.", "success")
        return redirect(url_for("academy.edit_quiz", quiz_id=quiz.id))

    return render_template(
        "academy/quiz_form.html",
        lesson=lesson,
        quiz=None,
        page_title="Create Quiz",
        submit_label="Create Quiz",
        user=current_user,
    )


@academy_bp.route("/quizzes/<int:quiz_id>/edit", methods=["GET", "POST"])
@login_required
def edit_quiz(quiz_id):
    if not can_manage_tracks():
        flash("You do not have permission to manage quizzes.", "danger")
        return redirect(url_for("academy.dashboard"))

    quiz = Quiz.query.get_or_404(quiz_id)

    if request.method == "POST":
        quiz.title = request.form.get("title", "").strip()

        try:
            quiz.passing_score = int(request.form.get("passing_score", "80").strip())
        except ValueError:
            quiz.passing_score = 80

        db.session.commit()
        flash("Quiz updated successfully.", "success")
        return redirect(url_for("academy.edit_quiz", quiz_id=quiz.id))

    return render_template(
        "academy/quiz_form.html",
        lesson=quiz.lesson,
        quiz=quiz,
        page_title="Edit Quiz",
        submit_label="Save Changes",
        user=current_user,
    )


@academy_bp.route("/quizzes/<int:quiz_id>/take", methods=["GET", "POST"])
@login_required
def take_quiz(quiz_id):
    quiz = Quiz.query.get_or_404(quiz_id)

    if current_user.role == "mit":
        return redirect(url_for("mit_sts.my_mit"))

    if current_user.role == "tm" and not user_can_access_track(current_user, quiz.lesson.module.track_id):
        flash("You do not have access to that quiz.", "danger")
        return redirect(url_for("academy.my_training"))

    if request.method == "POST":
        questions = quiz.questions
        total_questions = len(questions)

        if total_questions == 0:
            flash("This quiz has no questions.", "danger")
            return redirect(url_for("academy.view_lesson", lesson_id=quiz.lesson_id))

        correct_count = 0

        attempt = QuizAttempt(
            quiz_id=quiz.id,
            user_id=current_user.id,
            score=0,
            passed=False,
        )
        db.session.add(attempt)
        db.session.flush()

        for question in questions:
            selected_choice_id = request.form.get(f"question_{question.id}")
            selected_choice = None
            is_correct = False

            if selected_choice_id:
                selected_choice = QuizChoice.query.get(int(selected_choice_id))
                if selected_choice and selected_choice.is_correct:
                    is_correct = True
                    correct_count += 1

            answer = QuizAttemptAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                selected_choice_id=int(selected_choice_id) if selected_choice_id else None,
                is_correct=is_correct,
            )
            db.session.add(answer)

        score = round((correct_count / total_questions) * 100)
        attempt.score = score
        attempt.passed = score >= quiz.passing_score

        db.session.commit()

        if attempt.passed:
            flash(f"You passed the quiz with a score of {score}%.", "success")
        else:
            flash(f"You scored {score}%. Passing score is {quiz.passing_score}%.", "danger")

        return redirect(url_for("academy.view_lesson", lesson_id=quiz.lesson_id))

    return render_template(
        "academy/take_quiz.html",
        quiz=quiz,
        user=current_user,
    )


# --------------------------------------------------
# ASSIGNMENTS
# --------------------------------------------------

@academy_bp.route("/assignments")
@login_required
def manage_assignments():
    if not can_manage_assignments():
        flash("You do not have permission to manage assignments.", "danger")
        return redirect(url_for("academy.dashboard"))

    assignments = TrackAssignment.query.order_by(TrackAssignment.assigned_at.desc()).all()
    users = User.query.filter(User.role == "tm").order_by(User.name.asc()).all()
    tracks = TrainingTrack.query.order_by(TrainingTrack.title.asc()).all()

    return render_template(
        "academy/assignments.html",
        assignments=assignments,
        users=users,
        tracks=tracks,
        user=current_user,
    )


@academy_bp.route("/assignments/new", methods=["POST"])
@login_required
def new_assignment():
    if not can_manage_assignments():
        flash("You do not have permission to manage assignments.", "danger")
        return redirect(url_for("academy.dashboard"))

    user_id = request.form.get("user_id", "").strip()
    track_id = request.form.get("track_id", "").strip()

    if not user_id or not track_id:
        flash("User and track are required.", "danger")
        return redirect(url_for("academy.manage_assignments"))

    existing = TrackAssignment.query.filter_by(
        user_id=int(user_id),
        track_id=int(track_id)
    ).first()

    if existing:
        flash("That track is already assigned to this user.", "danger")
        return redirect(url_for("academy.manage_assignments"))

    assignment = TrackAssignment(
        user_id=int(user_id),
        track_id=int(track_id),
        assigned_by_user_id=current_user.id,
    )

    db.session.add(assignment)
    db.session.commit()

    flash("Track assigned successfully.", "success")
    return redirect(url_for("academy.manage_assignments"))


# --------------------------------------------------
# USERS
# --------------------------------------------------

@academy_bp.route("/admin/users")
@login_required
def manage_users():
    if not can_manage_users():
        flash("You do not have permission to access that page.", "danger")
        return redirect(url_for("academy.dashboard"))

    q = request.args.get("q", "").strip()
    role = request.args.get("role", "").strip()
    store = request.args.get("store", "").strip()

    users_query = User.query

    if q:
        users_query = users_query.filter(User.name.ilike(f"%{q}%"))

    if role:
        users_query = users_query.filter(User.role == role)

    if store:
        users_query = users_query.filter(User.store_number == store)

    users = users_query.order_by(User.role.asc(), User.name.asc()).all()

    all_stores = [
        row[0]
        for row in db.session.query(User.store_number)
        .filter(User.store_number.isnot(None), User.store_number != "")
        .distinct()
        .order_by(User.store_number.asc())
        .all()
    ]

    return render_template(
        "academy/users.html",
        users=users,
        user=current_user,
        q=q,
        selected_role=role,
        selected_store=store,
        all_stores=all_stores,
    )


@academy_bp.route("/admin/users/new", methods=["GET", "POST"])
@login_required
def new_user():
    if not can_manage_users():
        flash("You do not have permission to access that page.", "danger")
        return redirect(url_for("academy.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "tm").strip()
        store_number = request.form.get("store_number", "").strip()

        if not name or not username or not password:
            flash("Name, username, and password are required.", "danger")
            return redirect(url_for("academy.new_user"))

        existing = User.query.filter_by(username=username).first()
        if existing:
            flash("Username already exists.", "danger")
            return redirect(url_for("academy.new_user"))

        user = User(
            name=name,
            username=username,
            role=role,
            store_number=store_number or None,
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        flash("User created successfully.", "success")
        return redirect(url_for("academy.manage_users"))

    return render_template(
        "academy/user_form.html",
        edit_user=None,
        page_title="Create User",
        submit_label="Create User"
    )


@academy_bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if not can_manage_users():
        flash("You do not have permission to access that page.", "danger")
        return redirect(url_for("academy.dashboard"))

    edit_user_obj = User.query.get_or_404(user_id)

    if request.method == "POST":
        edit_user_obj.name = request.form.get("name", "").strip()
        edit_user_obj.username = request.form.get("username", "").strip()
        edit_user_obj.role = request.form.get("role", "tm").strip()
        edit_user_obj.store_number = request.form.get("store_number", "").strip() or None
        edit_user_obj.is_active_user = request.form.get("is_active_user") == "on"

        new_password = request.form.get("password", "").strip()
        if new_password:
            edit_user_obj.set_password(new_password)

        db.session.commit()
        flash("User updated successfully.", "success")
        return redirect(url_for("academy.manage_users"))

    return render_template(
        "academy/user_form.html",
        edit_user=edit_user_obj,
        page_title="Edit User",
        submit_label="Save Changes"
    )


@academy_bp.route("/admin/users/<int:user_id>/delete")
@login_required
def delete_user(user_id):
    if not admin_required():
        flash("You do not have permission to access that page.", "danger")
        return redirect(url_for("academy.dashboard"))

    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("academy.manage_users"))

    db.session.delete(user)
    db.session.commit()

    flash("User deleted.", "info")
    return redirect(url_for("academy.manage_users"))