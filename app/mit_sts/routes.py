from collections import defaultdict
from datetime import datetime, date

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import (
    User,
    MITProfile,
    MITLevelTemplate,
    MITLevelProgress,
    MITTask,
    MITPromotion,
)

mit_sts_bp = Blueprint("mit_sts", __name__, url_prefix="/mit-sts")


def is_tm():
    return current_user.is_authenticated and current_user.role == "tm"


def is_mit():
    return current_user.is_authenticated and current_user.role == "mit"


def is_coach():
    return current_user.is_authenticated and current_user.role == "coach"


def is_admin():
    return current_user.is_authenticated and current_user.role == "admin"


def is_training_director():
    return current_user.is_authenticated and current_user.role == "training_director"


def is_leadership():
    return current_user.is_authenticated and current_user.role in [
        "coach",
        "admin",
        "training_director",
    ]


def can_edit_mit():
    return is_leadership()


def can_view_mit(mit):
    if is_leadership():
        return True
    return is_mit() and mit.user_id == current_user.id


def task_display_status(task):
    if task.status in ["verified", "cancelled"]:
        return task.status

    if task.due_date and task.due_date < date.today() and task.status not in ["submitted"]:
        return "overdue"

    return task.status


def calculate_level_progress(mit_profile_id, level_number):
    templates = MITLevelTemplate.query.filter_by(
        level_number=level_number,
        is_required=True
    ).all()

    total = len(templates)
    if total == 0:
        return 0

    template_ids = [item.id for item in templates]

    completed = MITLevelProgress.query.filter(
        MITLevelProgress.mit_profile_id == mit_profile_id,
        MITLevelProgress.template_item_id.in_(template_ids),
        MITLevelProgress.status == "complete",
    ).count()

    return round((completed / total) * 100)


def calculate_overall_progress(mit_profile_id):
    templates = MITLevelTemplate.query.filter_by(is_required=True).all()

    total = len(templates)
    if total == 0:
        return 0

    template_ids = [item.id for item in templates]

    completed = MITLevelProgress.query.filter(
        MITLevelProgress.mit_profile_id == mit_profile_id,
        MITLevelProgress.template_item_id.in_(template_ids),
        MITLevelProgress.status == "complete",
    ).count()

    return round((completed / total) * 100)


def get_next_target_level(current_level):
    if current_level == 1:
        return "2"
    if current_level == 2:
        return "3"
    return "gm"


def get_next_promotion_level(current_level):
    if current_level == 1:
        return "2"
    if current_level == 2:
        return "3"
    return "gm"


def ensure_progress_rows_for_mit(mit_profile):
    templates = MITLevelTemplate.query.all()
    existing_template_ids = {
        row.template_item_id
        for row in MITLevelProgress.query.filter_by(mit_profile_id=mit_profile.id).all()
    }

    created = False
    for template in templates:
        if template.id not in existing_template_ids:
            db.session.add(
                MITLevelProgress(
                    mit_profile_id=mit_profile.id,
                    template_item_id=template.id,
                    status="not_started",
                )
            )
            created = True

    if created:
        db.session.commit()


def get_mit_task_counts(mit_profile_id):
    tasks = MITTask.query.filter_by(mit_profile_id=mit_profile_id).all()

    open_count = 0
    overdue_count = 0
    submitted_count = 0

    for task in tasks:
        display_status = task_display_status(task)

        if display_status not in ["verified", "cancelled"]:
            open_count += 1

        if display_status == "overdue":
            overdue_count += 1

        if task.status == "submitted":
            submitted_count += 1

    return {
        "open": open_count,
        "overdue": overdue_count,
        "submitted": submitted_count,
    }


def is_mit_ready_for_promotion(mit):
    current_level_progress = calculate_level_progress(mit.id, mit.current_level)
    task_counts = get_mit_task_counts(mit.id)

    if mit.sts_status == "blocked":
        return False

    if current_level_progress != 100:
        return False

    if task_counts["open"] > 0:
        return False

    if task_counts["overdue"] > 0:
        return False

    if task_counts["submitted"] > 0:
        return False

    return True


def refresh_mit_status(mit):
    if mit.sts_status == "blocked":
        return

    if is_mit_ready_for_promotion(mit):
        mit.sts_status = "ready"
    else:
        if mit.sts_status in ["ready", "promoted"]:
            mit.sts_status = "on_track"


@mit_sts_bp.route("/my-mit")
@login_required
def my_mit():
    mit = MITProfile.query.filter_by(user_id=current_user.id).first()

    if not mit:
        flash("No MIT profile found for your account.", "danger")
        return redirect(url_for("academy.dashboard"))

    return redirect(url_for("mit_sts.view_mit", mit_id=mit.id))


@mit_sts_bp.route("/")
@login_required
def dashboard():
    if not is_leadership():
        return redirect(url_for("mit_sts.my_mit"))

    mits = MITProfile.query.order_by(MITProfile.created_at.desc()).all()

    total_mits = len(mits)
    level_1_count = sum(1 for mit in mits if mit.current_level == 1)
    level_2_count = sum(1 for mit in mits if mit.current_level == 2)
    level_3_count = sum(1 for mit in mits if mit.current_level == 3)

    ready_count = 0
    blocked_count = 0
    overdue_tasks_count = 0
    submitted_tasks_count = 0

    recent_mits = mits[:5]

    for mit in mits:
        refresh_mit_status(mit)
        if mit.sts_status == "ready":
            ready_count += 1
        if mit.sts_status == "blocked":
            blocked_count += 1

    all_tasks = MITTask.query.all()
    for task in all_tasks:
        display_status = task_display_status(task)
        if display_status == "overdue":
            overdue_tasks_count += 1
        if task.status == "submitted":
            submitted_tasks_count += 1

    db.session.commit()

    return render_template(
        "mit_sts/dashboard.html",
        total_mits=total_mits,
        level_1_count=level_1_count,
        level_2_count=level_2_count,
        level_3_count=level_3_count,
        ready_count=ready_count,
        blocked_count=blocked_count,
        overdue_tasks_count=overdue_tasks_count,
        submitted_tasks_count=submitted_tasks_count,
        recent_mits=recent_mits,
        user=current_user,
    )


@mit_sts_bp.route("/promotion-queue")
@login_required
def promotion_queue():
    if not is_leadership():
        flash("You do not have permission to access the promotion queue.", "danger")
        return redirect(url_for("academy.dashboard"))

    mits = MITProfile.query.order_by(MITProfile.updated_at.desc()).all()
    ready_mits = []

    for mit in mits:
        refresh_mit_status(mit)
        progress = calculate_level_progress(mit.id, mit.current_level)

        if is_mit_ready_for_promotion(mit):
            ready_mits.append((mit, progress, get_next_promotion_level(mit.current_level)))

    db.session.commit()

    return render_template(
        "mit_sts/promotion_queue.html",
        ready_mits=ready_mits,
        user=current_user,
    )


@mit_sts_bp.route("/mits/<int:mit_id>/promote", methods=["POST"])
@login_required
def promote_mit(mit_id):
    if not is_leadership():
        flash("You do not have permission to promote MITs.", "danger")
        return redirect(url_for("academy.dashboard"))

    mit = MITProfile.query.get_or_404(mit_id)

    if not is_mit_ready_for_promotion(mit):
        flash("This MIT is not ready for promotion yet.", "danger")
        return redirect(url_for("mit_sts.view_mit", mit_id=mit.id))

    to_level = get_next_promotion_level(mit.current_level)

    effective_date_raw = request.form.get("effective_date", "").strip()
    note = request.form.get("note", "").strip()

    effective_date = date.today()
    if effective_date_raw:
        try:
            effective_date = datetime.strptime(effective_date_raw, "%Y-%m-%d").date()
        except ValueError:
            pass

    promotion = MITPromotion(
        mit_profile_id=mit.id,
        from_level=mit.current_level,
        to_level=to_level,
        approved_by_user_id=current_user.id,
        effective_date=effective_date,
        note=note or None,
    )
    db.session.add(promotion)

    if mit.current_level == 1:
        mit.current_level = 2
        mit.target_level = "3"
    elif mit.current_level == 2:
        mit.current_level = 3
        mit.target_level = "gm"
    else:
        mit.target_level = "gm"

    mit.sts_status = "promoted"
    mit.last_review_date = effective_date

    ensure_progress_rows_for_mit(mit)
    db.session.commit()

    flash(f"{mit.mit_user.name} promoted successfully.", "success")
    return redirect(url_for("mit_sts.view_mit", mit_id=mit.id))


@mit_sts_bp.route("/mits")
@login_required
def list_mits():
    if not is_leadership():
        return redirect(url_for("mit_sts.my_mit"))

    q = request.args.get("q", "").strip()
    store = request.args.get("store", "").strip()
    level = request.args.get("level", "").strip()
    status = request.args.get("status", "").strip()
    coach = request.args.get("coach", "").strip()
    task_filter = request.args.get("task_filter", "").strip()

    query = MITProfile.query.join(User, MITProfile.user_id == User.id)

    if q:
        query = query.filter(User.name.ilike(f"%{q}%"))

    if store:
        query = query.filter(MITProfile.store_number == store)

    if level:
        try:
            query = query.filter(MITProfile.current_level == int(level))
        except ValueError:
            pass

    if status:
        query = query.filter(MITProfile.sts_status == status)

    if coach:
        try:
            query = query.filter(MITProfile.coach_user_id == int(coach))
        except ValueError:
            pass

    mits = query.order_by(User.name.asc()).all()

    filtered_mits = []
    task_counts_map = {}

    for mit in mits:
        refresh_mit_status(mit)
        counts = get_mit_task_counts(mit.id)
        task_counts_map[mit.id] = counts

        include = True
        if task_filter == "open" and counts["open"] == 0:
            include = False
        elif task_filter == "overdue" and counts["overdue"] == 0:
            include = False
        elif task_filter == "submitted" and counts["submitted"] == 0:
            include = False

        if include:
            filtered_mits.append(mit)

    db.session.commit()
    mits = filtered_mits

    stores = [
        row[0]
        for row in db.session.query(MITProfile.store_number)
        .filter(MITProfile.store_number.isnot(None), MITProfile.store_number != "")
        .distinct()
        .order_by(MITProfile.store_number.asc())
        .all()
    ]

    coaches = User.query.filter(
        User.role.in_(["coach", "admin", "training_director"])
    ).order_by(User.name.asc()).all()

    progress_map = {
        mit.id: calculate_level_progress(mit.id, mit.current_level)
        for mit in mits
    }

    return render_template(
        "mit_sts/mit_list.html",
        mits=mits,
        progress_map=progress_map,
        task_counts_map=task_counts_map,
        stores=stores,
        coaches=coaches,
        q=q,
        selected_store=store,
        selected_level=level,
        selected_status=status,
        selected_coach=coach,
        selected_task_filter=task_filter,
        user=current_user,
    )


@mit_sts_bp.route("/mits/new", methods=["GET", "POST"])
@login_required
def new_mit():
    if not is_leadership():
        flash("You do not have permission to create MIT profiles.", "danger")
        return redirect(url_for("academy.dashboard"))

    users = User.query.order_by(User.name.asc()).all()
    coaches = User.query.filter(
        User.role.in_(["coach", "admin", "training_director"])
    ).order_by(User.name.asc()).all()

    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        store_number = request.form.get("store_number", "").strip()
        coach_user_id = request.form.get("coach_user_id", "").strip()
        current_level = request.form.get("current_level", "1").strip()
        start_date = request.form.get("start_date", "").strip()
        sts_status = request.form.get("sts_status", "on_track").strip()
        next_review_date = request.form.get("next_review_date", "").strip()
        notes = request.form.get("notes", "").strip()

        if not user_id:
            flash("MIT user is required.", "danger")
            return redirect(url_for("mit_sts.new_mit"))

        existing = MITProfile.query.filter_by(user_id=int(user_id)).first()
        if existing:
            flash("This user already has an MIT STS profile.", "danger")
            return redirect(url_for("mit_sts.new_mit"))

        try:
            current_level = int(current_level)
        except ValueError:
            current_level = 1

        start_date_obj = None
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        next_review_date_obj = None
        if next_review_date:
            try:
                next_review_date_obj = datetime.strptime(next_review_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        mit = MITProfile(
            user_id=int(user_id),
            store_number=store_number or None,
            coach_user_id=int(coach_user_id) if coach_user_id else None,
            current_level=current_level,
            target_level=get_next_target_level(current_level),
            start_date=start_date_obj,
            sts_status=sts_status or "on_track",
            next_review_date=next_review_date_obj,
            notes=notes or None,
        )

        db.session.add(mit)
        db.session.commit()

        ensure_progress_rows_for_mit(mit)
        refresh_mit_status(mit)
        db.session.commit()

        flash("MIT profile created successfully.", "success")
        return redirect(url_for("mit_sts.view_mit", mit_id=mit.id))

    return render_template(
        "mit_sts/mit_form.html",
        page_title="Create MIT Profile",
        submit_label="Create MIT Profile",
        mit=None,
        users=users,
        coaches=coaches,
        user=current_user,
    )


@mit_sts_bp.route("/mits/<int:mit_id>/edit", methods=["GET", "POST"])
@login_required
def edit_mit(mit_id):
    if not is_leadership():
        flash("You do not have permission to edit MIT profiles.", "danger")
        return redirect(url_for("academy.dashboard"))

    mit = MITProfile.query.get_or_404(mit_id)
    users = User.query.order_by(User.name.asc()).all()
    coaches = User.query.filter(
        User.role.in_(["coach", "admin", "training_director"])
    ).order_by(User.name.asc()).all()

    if request.method == "POST":
        mit.user_id = int(request.form.get("user_id", mit.user_id))
        mit.store_number = request.form.get("store_number", "").strip() or None

        coach_user_id = request.form.get("coach_user_id", "").strip()
        mit.coach_user_id = int(coach_user_id) if coach_user_id else None

        try:
            mit.current_level = int(request.form.get("current_level", mit.current_level))
        except ValueError:
            pass

        mit.target_level = get_next_target_level(mit.current_level)
        mit.sts_status = request.form.get("sts_status", mit.sts_status).strip() or mit.sts_status
        mit.notes = request.form.get("notes", "").strip() or None

        start_date = request.form.get("start_date", "").strip()
        if start_date:
            try:
                mit.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            mit.start_date = None

        next_review_date = request.form.get("next_review_date", "").strip()
        if next_review_date:
            try:
                mit.next_review_date = datetime.strptime(next_review_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            mit.next_review_date = None

        refresh_mit_status(mit)
        db.session.commit()
        ensure_progress_rows_for_mit(mit)

        flash("MIT profile updated successfully.", "success")
        return redirect(url_for("mit_sts.view_mit", mit_id=mit.id))

    return render_template(
        "mit_sts/mit_form.html",
        page_title="Edit MIT Profile",
        submit_label="Save Changes",
        mit=mit,
        users=users,
        coaches=coaches,
        user=current_user,
    )


@mit_sts_bp.route("/mits/<int:mit_id>")
@login_required
def view_mit(mit_id):
    mit = MITProfile.query.get_or_404(mit_id)

    if not can_view_mit(mit):
        flash("You do not have permission to view that MIT profile.", "danger")
        return redirect(url_for("academy.dashboard"))

    ensure_progress_rows_for_mit(mit)
    refresh_mit_status(mit)
    db.session.commit()

    level_1_progress = calculate_level_progress(mit.id, 1)
    level_2_progress = calculate_level_progress(mit.id, 2)
    level_3_progress = calculate_level_progress(mit.id, 3)
    overall_progress = calculate_overall_progress(mit.id)

    incomplete_count = MITLevelProgress.query.join(
        MITLevelTemplate,
        MITLevelProgress.template_item_id == MITLevelTemplate.id
    ).filter(
        MITLevelProgress.mit_profile_id == mit.id,
        MITLevelTemplate.level_number == mit.current_level,
        MITLevelProgress.status != "complete"
    ).count()

    task_counts = get_mit_task_counts(mit.id)
    promotions = MITPromotion.query.filter_by(mit_profile_id=mit.id).order_by(
        MITPromotion.effective_date.desc()
    ).all()

    return render_template(
        "mit_sts/mit_detail.html",
        mit=mit,
        level_1_progress=level_1_progress,
        level_2_progress=level_2_progress,
        level_3_progress=level_3_progress,
        overall_progress=overall_progress,
        incomplete_count=incomplete_count,
        open_tasks_count=task_counts["open"],
        overdue_tasks_count=task_counts["overdue"],
        submitted_tasks_count=task_counts["submitted"],
        promotions=promotions,
        user=current_user,
        can_edit=can_edit_mit(),
    )


@mit_sts_bp.route("/mits/<int:mit_id>/level/<int:level_number>")
@login_required
def view_level(mit_id, level_number):
    if level_number not in [1, 2, 3]:
        flash("Invalid level.", "danger")
        return redirect(url_for("academy.dashboard"))

    mit = MITProfile.query.get_or_404(mit_id)

    if not can_view_mit(mit):
        flash("You do not have permission to view that MIT level.", "danger")
        return redirect(url_for("academy.dashboard"))

    ensure_progress_rows_for_mit(mit)
    refresh_mit_status(mit)
    db.session.commit()

    templates = MITLevelTemplate.query.filter_by(level_number=level_number).order_by(
        MITLevelTemplate.category.asc(),
        MITLevelTemplate.sort_order.asc(),
        MITLevelTemplate.id.asc()
    ).all()

    progress_rows = MITLevelProgress.query.filter_by(mit_profile_id=mit.id).all()
    progress_map = {row.template_item_id: row for row in progress_rows}

    grouped_items = defaultdict(list)
    for template in templates:
        grouped_items[template.category or "General"].append(template)

    active_task_map = {}
    for task in MITTask.query.filter(
        MITTask.mit_profile_id == mit.id,
        MITTask.related_template_item_id.isnot(None),
        MITTask.status.in_(["open", "in_progress", "submitted"])
    ).order_by(MITTask.created_at.desc()).all():
        if task.related_template_item_id not in active_task_map:
            active_task_map[task.related_template_item_id] = task

    level_progress = calculate_level_progress(mit.id, level_number)
    is_complete = level_progress == 100 and len(templates) > 0

    return render_template(
        "mit_sts/level_detail.html",
        mit=mit,
        level_number=level_number,
        grouped_items=dict(grouped_items),
        progress_map=progress_map,
        active_task_map=active_task_map,
        level_progress=level_progress,
        is_complete=is_complete,
        task_display_status=task_display_status,
        user=current_user,
        can_edit=can_edit_mit(),
    )


@mit_sts_bp.route("/progress/<int:progress_id>/status", methods=["POST"])
@login_required
def update_progress(progress_id):
    if not is_leadership():
        flash("You do not have permission to update STS items.", "danger")
        return redirect(url_for("academy.dashboard"))

    progress = MITLevelProgress.query.get_or_404(progress_id)
    new_status = request.form.get("status", "not_started").strip()

    if new_status not in ["not_started", "in_progress", "complete"]:
        flash("Invalid status.", "danger")
        return redirect(url_for("mit_sts.view_mit", mit_id=progress.mit_profile_id))

    progress.status = new_status
    progress.notes = request.form.get("notes", "").strip() or progress.notes

    if new_status == "complete":
        progress.completed_date = datetime.utcnow().date()
        progress.verified_by_user_id = current_user.id
    else:
        progress.completed_date = None
        if new_status == "not_started":
            progress.verified_by_user_id = None

    mit = MITProfile.query.get(progress.mit_profile_id)
    refresh_mit_status(mit)
    db.session.commit()

    template = MITLevelTemplate.query.get(progress.template_item_id)
    flash("STS item updated.", "success")
    return redirect(
        url_for(
            "mit_sts.view_level",
            mit_id=progress.mit_profile_id,
            level_number=template.level_number,
        )
    )


@mit_sts_bp.route("/mits/<int:mit_id>/tasks")
@login_required
def view_tasks(mit_id):
    mit = MITProfile.query.get_or_404(mit_id)

    if not can_view_mit(mit):
        flash("You do not have permission to view those tasks.", "danger")
        return redirect(url_for("academy.dashboard"))

    tasks = MITTask.query.filter_by(mit_profile_id=mit.id).order_by(
        MITTask.due_date.asc(),
        MITTask.created_at.desc()
    ).all()

    active_tasks = []
    completed_tasks = []

    for task in tasks:
        display_status = task_display_status(task)
        if display_status in ["verified", "cancelled"]:
            completed_tasks.append((task, display_status))
        else:
            active_tasks.append((task, display_status))

    return render_template(
        "mit_sts/mit_tasks.html",
        mit=mit,
        active_tasks=active_tasks,
        completed_tasks=completed_tasks,
        today=date.today(),
        user=current_user,
        can_edit=can_edit_mit(),
    )


@mit_sts_bp.route("/mits/<int:mit_id>/tasks/new", methods=["GET", "POST"])
@login_required
def new_task(mit_id):
    if not is_leadership():
        flash("You do not have permission to assign tasks.", "danger")
        return redirect(url_for("academy.dashboard"))

    mit = MITProfile.query.get_or_404(mit_id)

    all_template_items = MITLevelTemplate.query.order_by(
        MITLevelTemplate.level_number.asc(),
        MITLevelTemplate.category.asc(),
        MITLevelTemplate.sort_order.asc(),
        MITLevelTemplate.id.asc()
    ).all()

    grouped_template_items = defaultdict(list)
    for item in all_template_items:
        grouped_template_items[item.level_number].append(item)

    if request.method == "POST":
        due_date = request.form.get("due_date", "").strip()
        priority = request.form.get("priority", "medium").strip()
        notes = request.form.get("notes", "").strip()

        selected_template_item_ids = request.form.getlist("selected_template_item_ids")
        custom_task_titles = request.form.getlist("custom_task_titles")

        due_date_obj = None
        if due_date:
            try:
                due_date_obj = datetime.strptime(due_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        created_count = 0
        skipped_count = 0

        for raw_id in selected_template_item_ids:
            try:
                template_item_id = int(raw_id)
            except ValueError:
                continue

            template_item = MITLevelTemplate.query.get(template_item_id)
            if not template_item:
                continue

            existing_open_task = MITTask.query.filter(
                MITTask.mit_profile_id == mit.id,
                MITTask.related_template_item_id == template_item_id,
                MITTask.status.in_(["open", "in_progress", "submitted"])
            ).first()

            if existing_open_task:
                skipped_count += 1
                continue

            task = MITTask(
                mit_profile_id=mit.id,
                title=template_item.item_name,
                description=template_item.item_description or None,
                related_template_item_id=template_item.id,
                assigned_by_user_id=current_user.id,
                due_date=due_date_obj,
                priority=priority or "medium",
                status="open",
                notes=notes or None,
            )
            db.session.add(task)
            created_count += 1

        for raw_title in custom_task_titles:
            title = (raw_title or "").strip()
            if not title:
                continue

            task = MITTask(
                mit_profile_id=mit.id,
                title=title,
                description=None,
                related_template_item_id=None,
                assigned_by_user_id=current_user.id,
                due_date=due_date_obj,
                priority=priority or "medium",
                status="open",
                notes=notes or None,
            )
            db.session.add(task)
            created_count += 1

        if created_count == 0 and skipped_count == 0:
            flash("Select at least one STS task or add a custom task.", "danger")
            return redirect(url_for("mit_sts.new_task", mit_id=mit.id))

        db.session.commit()

        if skipped_count > 0:
            flash(f"Assigned {created_count} task(s). Skipped {skipped_count} duplicate open STS task(s).", "success")
        else:
            flash(f"Assigned {created_count} task(s) successfully.", "success")

        return redirect(url_for("mit_sts.view_tasks", mit_id=mit.id))

    return render_template(
        "mit_sts/mit_task_form.html",
        mit=mit,
        grouped_template_items=dict(grouped_template_items),
        page_title="Assign MIT Tasks",
        submit_label="Assign Selected Tasks",
        user=current_user,
    )


@mit_sts_bp.route("/tasks/<int:task_id>/quick-add", methods=["POST"])
@login_required
def quick_add_task(task_id):
    if not is_leadership():
        flash("You do not have permission to assign tasks.", "danger")
        return redirect(url_for("academy.dashboard"))

    progress = MITLevelProgress.query.get_or_404(task_id)
    template = MITLevelTemplate.query.get_or_404(progress.template_item_id)

    due_date = request.form.get("due_date", "").strip()
    priority = request.form.get("priority", "medium").strip()
    notes = request.form.get("notes", "").strip()
    title = request.form.get("title", "").strip() or template.item_name

    existing_open_task = MITTask.query.filter(
        MITTask.mit_profile_id == progress.mit_profile_id,
        MITTask.related_template_item_id == template.id,
        MITTask.status.in_(["open", "in_progress", "submitted"])
    ).first()

    if existing_open_task:
        flash("There is already an open task linked to this STS item.", "danger")
        return redirect(url_for("mit_sts.view_level", mit_id=progress.mit_profile_id, level_number=template.level_number))

    due_date_obj = None
    if due_date:
        try:
            due_date_obj = datetime.strptime(due_date, "%Y-%m-%d").date()
        except ValueError:
            pass

    task = MITTask(
        mit_profile_id=progress.mit_profile_id,
        title=title,
        description=template.item_description or None,
        related_template_item_id=template.id,
        assigned_by_user_id=current_user.id,
        due_date=due_date_obj,
        priority=priority or "medium",
        status="open",
        notes=notes or None,
    )
    db.session.add(task)
    db.session.commit()

    flash("Task assigned to this STS item.", "success")
    return redirect(url_for("mit_sts.view_level", mit_id=progress.mit_profile_id, level_number=template.level_number))


@mit_sts_bp.route("/tasks/<int:task_id>/submit", methods=["POST"])
@login_required
def submit_task_for_review(task_id):
    task = MITTask.query.get_or_404(task_id)

    mit = MITProfile.query.get_or_404(task.mit_profile_id)
    if not can_view_mit(mit) or current_user.id != mit.user_id:
        flash("You do not have permission to submit that task.", "danger")
        return redirect(url_for("academy.dashboard"))

    if task.status not in ["open", "in_progress", "overdue"]:
        flash("That task cannot be submitted right now.", "danger")
        return redirect(url_for("mit_sts.view_tasks", mit_id=mit.id))

    mit_note = request.form.get("mit_completion_note", "").strip()

    task.status = "submitted"
    if mit_note:
        existing_notes = task.notes or ""
        if existing_notes:
            task.notes = existing_notes + f"\n\nMIT submission note: {mit_note}"
        else:
            task.notes = f"MIT submission note: {mit_note}"

    db.session.commit()

    flash("Task submitted for leadership review.", "success")
    return redirect(url_for("mit_sts.view_tasks", mit_id=mit.id))


@mit_sts_bp.route("/tasks/<int:task_id>/status", methods=["POST"])
@login_required
def update_task_status(task_id):
    if not is_leadership():
        flash("You do not have permission to update task status.", "danger")
        return redirect(url_for("academy.dashboard"))

    task = MITTask.query.get_or_404(task_id)
    new_status = request.form.get("status", "open").strip()

    if new_status not in ["open", "in_progress", "submitted", "verified", "cancelled"]:
        flash("Invalid task status.", "danger")
        return redirect(url_for("mit_sts.view_tasks", mit_id=task.mit_profile_id))

    task.status = new_status

    if new_status == "verified":
        task.completed_at = datetime.utcnow()

        if task.related_template_item_id:
            progress = MITLevelProgress.query.filter_by(
                mit_profile_id=task.mit_profile_id,
                template_item_id=task.related_template_item_id,
            ).first()

            if progress:
                progress.status = "complete"
                progress.completed_date = datetime.utcnow().date()
                progress.verified_by_user_id = current_user.id
    else:
        task.completed_at = None

        if task.related_template_item_id and new_status in ["open", "in_progress", "submitted"]:
            progress = MITLevelProgress.query.filter_by(
                mit_profile_id=task.mit_profile_id,
                template_item_id=task.related_template_item_id,
            ).first()

            if progress and progress.status == "complete":
                progress.status = "in_progress"
                progress.completed_date = None
                progress.verified_by_user_id = None

    mit = MITProfile.query.get(task.mit_profile_id)
    if mit:
        refresh_mit_status(mit)

    db.session.commit()

    flash("Task updated.", "success")

    level_number = None
    if task.related_template_item_id:
        template = MITLevelTemplate.query.get(task.related_template_item_id)
        if template:
            level_number = template.level_number

    if level_number:
        return redirect(url_for("mit_sts.view_level", mit_id=task.mit_profile_id, level_number=level_number))

    return redirect(url_for("mit_sts.view_tasks", mit_id=task.mit_profile_id))