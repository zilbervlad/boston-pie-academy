from collections import defaultdict
from datetime import datetime, date
from io import BytesIO

from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from app.extensions import db
from app.models import User, MITProfile, MITLevelTemplate, MITLevelProgress, MITTask, MITPromotion

mit_sts_bp = Blueprint("mit_sts", __name__, url_prefix="/mit-sts")


# --------------------------------------------------
# ROLE HELPERS
# --------------------------------------------------

def is_tm():
    return current_user.is_authenticated and current_user.role == "tm"


def is_mit():
    return current_user.is_authenticated and current_user.role == "mit"


def is_coach():
    return current_user.is_authenticated and current_user.role in ["coach", "admin", "training_director"]


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def user_can_access_mit_profile(profile):
    return is_coach() or (
        current_user.is_authenticated
        and profile
        and profile.user_id == current_user.id
    )


def get_task_progress_row(task):
    if not getattr(task, "related_template_item_id", None):
        return None

    return MITLevelProgress.query.filter_by(
        mit_profile_id=task.mit_profile_id,
        template_item_id=task.related_template_item_id,
    ).first()


def redirect_for_task(task):
    if getattr(task, "related_template_item_id", None):
        template = MITLevelTemplate.query.get(task.related_template_item_id)
        if template:
            return redirect(
                url_for(
                    "mit_sts.view_level",
                    mit_id=task.mit_profile_id,
                    level_number=template.level_number,
                )
            )

    return redirect(url_for("mit_sts.view_tasks", mit_id=task.mit_profile_id))



def get_task_counts(mit_profile_id):
    tasks = MITTask.query.filter_by(mit_profile_id=mit_profile_id).all()
    today = date.today()

    open_count = 0
    overdue_count = 0
    submitted_count = 0

    for t in tasks:
        if t.status not in ["verified", "cancelled"]:
            open_count += 1

        if t.due_date and t.due_date < today and t.status not in ["verified", "cancelled", "submitted"]:
            overdue_count += 1

        if t.status == "submitted":
            submitted_count += 1

    return open_count, overdue_count, submitted_count


def calculate_level_progress(mit_profile_id, level_number):
    templates = MITLevelTemplate.query.filter_by(level_number=level_number).all()
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


def task_display_status(task):
    if task.status in ["verified", "cancelled"]:
        return task.status

    if task.due_date and task.due_date < date.today() and task.status not in ["submitted"]:
        return "overdue"

    return task.status


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


def get_target_level(current_level):
    if current_level == 1:
        return "2"
    if current_level == 2:
        return "3"
    return "gm"


def available_user_roles():
    return ["mit", "coach", "admin", "training_director"]


def should_force_mit_role(user):
    return user.role not in ["admin", "coach", "training_director"]


def get_active_task_map(profile_id, level_number=None):
    query = MITTask.query.filter(
        MITTask.mit_profile_id == profile_id,
        MITTask.related_template_item_id.isnot(None),
        MITTask.status.in_(["open", "in_progress", "submitted"]),
    )

    if level_number is not None:
        templates = MITLevelTemplate.query.filter_by(level_number=level_number).all()
        template_ids = [item.id for item in templates]
        if not template_ids:
            return {}
        query = query.filter(MITTask.related_template_item_id.in_(template_ids))

    tasks = query.order_by(MITTask.id.desc()).all()

    task_map = {}
    for task in tasks:
        if task.related_template_item_id not in task_map:
            task_map[task.related_template_item_id] = task

    return task_map


def get_all_linked_task_map(profile_id):
    tasks = MITTask.query.filter(
        MITTask.mit_profile_id == profile_id,
        MITTask.related_template_item_id.isnot(None),
    ).order_by(MITTask.id.desc()).all()

    task_map = {}
    for task in tasks:
        if task.related_template_item_id not in task_map:
            task_map[task.related_template_item_id] = task

    return task_map


def sync_progress_from_task(task, progress):
    if not progress:
        return

    if task.status == "verified":
        progress.status = "complete"
        progress.completed_date = datetime.utcnow().date()
        progress.verified_by_user_id = current_user.id
        task.completed_at = datetime.utcnow()
        return

    task.completed_at = None

    if task.status in ["open", "in_progress", "submitted"]:
        progress.status = "in_progress"
        progress.completed_date = None
        progress.verified_by_user_id = None
        return

    if task.status == "cancelled":
        if progress.status != "complete":
            progress.status = "not_started"
            progress.completed_date = None
            progress.verified_by_user_id = None


# --------------------------------------------------
# USERS
# --------------------------------------------------

@mit_sts_bp.route("/users")
@login_required
def list_users():
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    q = request.args.get("q", "").strip()
    selected_role = request.args.get("role", "").strip()
    selected_store = request.args.get("store", "").strip()

    query = User.query

    if q:
        query = query.filter(
            db.or_(
                User.name.ilike(f"%{q}%"),
                User.username.ilike(f"%{q}%")
            )
        )

    if selected_role:
        query = query.filter(User.role == selected_role)

    if selected_store:
        query = query.filter(User.store_number == selected_store)

    users = query.order_by(User.name.asc()).all()

    return render_template(
        "mit_sts/users.html",
        users=users,
        q=q,
        selected_role=selected_role,
        selected_store=selected_store,
        roles=available_user_roles(),
        user=current_user,
    )


@mit_sts_bp.route("/users/<int:user_id>")
@login_required
def view_user(user_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    user_item = User.query.get_or_404(user_id)
    mit_profile = user_item.mit_profiles[0] if user_item.mit_profiles else None

    return render_template(
        "mit_sts/user_detail.html",
        user_item=user_item,
        mit_profile=mit_profile,
        user=current_user,
    )


@mit_sts_bp.route("/users/new", methods=["GET", "POST"])
@login_required
def new_user():
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "mit").strip()
        store_number = request.form.get("store_number", "").strip()
        password = request.form.get("password", "").strip()
        is_active_user = request.form.get("is_active_user") == "1"

        if not name or not username or not password:
            flash("Name, username, and password are required.", "danger")
            return render_template(
                "mit_sts/user_form.html",
                page_title="Create User",
                submit_label="Create User",
                user_item=None,
                roles=available_user_roles(),
                user=current_user,
            )

        if role not in available_user_roles():
            role = "mit"

        existing = User.query.filter_by(username=username).first()
        if existing:
            flash("That username already exists.", "danger")
            return render_template(
                "mit_sts/user_form.html",
                page_title="Create User",
                submit_label="Create User",
                user_item=None,
                roles=available_user_roles(),
                user=current_user,
            )

        user_item = User(
            name=name,
            username=username,
            role=role,
            store_number=store_number or None,
            is_active_user=is_active_user,
        )
        user_item.set_password(password)

        db.session.add(user_item)
        db.session.commit()

        flash("User created successfully.", "success")
        return redirect(url_for("mit_sts.list_users"))

    return render_template(
        "mit_sts/user_form.html",
        page_title="Create User",
        submit_label="Create User",
        user_item=None,
        roles=available_user_roles(),
        user=current_user,
    )


@mit_sts_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    user_item = User.query.get_or_404(user_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "mit").strip()
        store_number = request.form.get("store_number", "").strip()
        password = request.form.get("password", "").strip()
        is_active_user = request.form.get("is_active_user") == "1"

        if not name or not username:
            flash("Name and username are required.", "danger")
            return render_template(
                "mit_sts/user_form.html",
                page_title="Edit User",
                submit_label="Save Changes",
                user_item=user_item,
                roles=available_user_roles(),
                user=current_user,
            )

        existing = User.query.filter(User.username == username, User.id != user_item.id).first()
        if existing:
            flash("That username already exists.", "danger")
            return render_template(
                "mit_sts/user_form.html",
                page_title="Edit User",
                submit_label="Save Changes",
                user_item=user_item,
                roles=available_user_roles(),
                user=current_user,
            )

        if role not in available_user_roles():
            role = "mit"

        user_item.name = name
        user_item.username = username
        user_item.role = role
        user_item.store_number = store_number or None
        user_item.is_active_user = is_active_user

        if password:
            user_item.set_password(password)

        linked_mit = user_item.mit_profiles[0] if user_item.mit_profiles else None
        if linked_mit and store_number:
            linked_mit.store_number = store_number

        db.session.commit()

        flash("User updated successfully.", "success")
        return redirect(url_for("mit_sts.view_user", user_id=user_item.id))

    return render_template(
        "mit_sts/user_form.html",
        page_title="Edit User",
        submit_label="Save Changes",
        user_item=user_item,
        roles=available_user_roles(),
        user=current_user,
    )


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@mit_sts_bp.route("/")
@mit_sts_bp.route("/dashboard")
@login_required
def dashboard():
    if not is_coach():
        return redirect(url_for("mit_sts.my_mit"))

    mits = (
        MITProfile.query
        .join(User, MITProfile.user_id == User.id)
        .filter(User.is_active_user == True)
        .order_by(MITProfile.created_at.desc())
        .all()
    )

    overdue_tasks_count = 0
    submitted_tasks_count = 0
    recent_progress_map = {}

    level_1_count = 0
    level_2_count = 0
    level_3_count = 0
    ready_count = 0
    blocked_count = 0

    for mit in mits:
        if getattr(mit, "current_level", None) == 1:
            level_1_count += 1
        elif getattr(mit, "current_level", None) == 2:
            level_2_count += 1
        elif getattr(mit, "current_level", None) == 3:
            level_3_count += 1

        if getattr(mit, "sts_status", None) == "ready":
            ready_count += 1
        elif getattr(mit, "sts_status", None) == "blocked":
            blocked_count += 1

        _, overdue, submitted = get_task_counts(mit.id)
        overdue_tasks_count += overdue
        submitted_tasks_count += submitted

        current_level = getattr(mit, "current_level", 1) or 1
        recent_progress_map[mit.id] = calculate_level_progress(mit.id, current_level)

    recent_mits = mits[:5]

    return render_template(
        "mit_sts/dashboard.html",
        mits=mits,
        overdue_tasks_count=overdue_tasks_count,
        submitted_tasks_count=submitted_tasks_count,
        total_mits=len(mits),
        ready_count=ready_count,
        blocked_count=blocked_count,
        level_1_count=level_1_count,
        level_2_count=level_2_count,
        level_3_count=level_3_count,
        recent_mits=recent_mits,
        recent_progress_map=recent_progress_map,
        user=current_user,
    )


# --------------------------------------------------
# TEMPLATE LIBRARY
# --------------------------------------------------

@mit_sts_bp.route("/templates")
@login_required
def template_library():
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    templates = MITLevelTemplate.query.order_by(
        MITLevelTemplate.level_number.asc(),
        MITLevelTemplate.category.asc(),
        MITLevelTemplate.sort_order.asc(),
        MITLevelTemplate.id.asc(),
    ).all()

    grouped_templates = defaultdict(list)
    for item in templates:
        grouped_templates[item.level_number].append(item)

    return render_template(
        "mit_sts/template_library.html",
        templates=templates,
        grouped_templates=dict(grouped_templates),
        user=current_user,
    )


@mit_sts_bp.route("/templates/new", methods=["GET", "POST"])
@login_required
def new_template_item():
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    if request.method == "POST":
        level_number = request.form.get("level_number", "1")
        item_name = request.form.get("item_name", "").strip()

        if not item_name:
            flash("Item name is required.", "danger")
            return redirect(url_for("mit_sts.new_template_item"))

        item = MITLevelTemplate(
            level_number=int(level_number),
            item_name=item_name,
            category=request.form.get("category") or None,
            item_description=request.form.get("item_description") or None,
            sort_order=int(request.form.get("sort_order") or 0),
            source_ref=request.form.get("source_ref") or None,
            is_required=request.form.get("is_required") == "on",
        )
        db.session.add(item)
        db.session.commit()

        flash("Template created", "success")
        return redirect(url_for("mit_sts.template_library"))

    return render_template(
        "mit_sts/template_form.html",
        page_title="Create STS Item",
        submit_label="Create STS Item",
        item=None,
        user=current_user,
    )


@mit_sts_bp.route("/templates/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_template_item(item_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    item = MITLevelTemplate.query.get_or_404(item_id)

    if request.method == "POST":
        item_name = request.form.get("item_name", "").strip()

        if not item_name:
            flash("Item name is required.", "danger")
            return redirect(url_for("mit_sts.edit_template_item", item_id=item.id))

        item.level_number = int(request.form.get("level_number") or item.level_number)
        item.item_name = item_name
        item.category = request.form.get("category") or None
        item.item_description = request.form.get("item_description") or None
        item.sort_order = int(request.form.get("sort_order") or 0)
        item.source_ref = request.form.get("source_ref") or None
        item.is_required = request.form.get("is_required") == "on"

        db.session.commit()

        flash("Template updated", "success")
        return redirect(url_for("mit_sts.template_library"))

    return render_template(
        "mit_sts/template_form.html",
        page_title="Edit STS Item",
        submit_label="Save Changes",
        item=item,
        user=current_user,
    )


@mit_sts_bp.route("/templates/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_template_item(item_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    item = MITLevelTemplate.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()

    flash("Template deleted", "success")
    return redirect(url_for("mit_sts.template_library"))


# --------------------------------------------------
# MIT LIST
# --------------------------------------------------

@mit_sts_bp.route("/list")
@login_required
def list_mits():
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    q = request.args.get("q", "").strip()
    store = request.args.get("store", "").strip()
    level = request.args.get("level", "").strip()
    status = request.args.get("status", "").strip()
    coach = request.args.get("coach", "").strip()
    task_filter = request.args.get("task_filter", "").strip()

    query = (
        MITProfile.query
        .join(User, MITProfile.user_id == User.id)
        .filter(User.is_active_user == True)
    )

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

    mits = query.all()

    progress_map = {}
    task_counts_map = {}

    filtered_mits = []
    total_overdue = 0
    total_open = 0
    total_submitted = 0

    for mit in mits:
        current_level = getattr(mit, "current_level", 1) or 1
        progress_map[mit.id] = calculate_level_progress(mit.id, current_level)

        open_count, overdue_count, submitted_count = get_task_counts(mit.id)
        task_counts_map[mit.id] = {
            "open": open_count,
            "overdue": overdue_count,
            "submitted": submitted_count,
        }

        total_overdue += overdue_count
        total_open += open_count
        total_submitted += submitted_count

        include = True
        if task_filter == "open" and open_count == 0:
            include = False
        elif task_filter == "overdue" and overdue_count == 0:
            include = False
        elif task_filter == "submitted" and submitted_count == 0:
            include = False

        if include:
            filtered_mits.append(mit)

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

    if total_overdue > 0:
        doughy_message = f"You have {total_overdue} overdue task{'s' if total_overdue != 1 else ''}. Start there first."
    elif total_submitted > 0:
        doughy_message = f"{total_submitted} task{'s' if total_submitted != 1 else ''} waiting for review."
    elif total_open > 0:
        doughy_message = f"{total_open} open task{'s' if total_open != 1 else ''} in progress."
    else:
        doughy_message = "All MIT tasks are clean. Time to assign new work."

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
        doughy_message=doughy_message,
        user=current_user,
    )


# --------------------------------------------------
# CREATE MIT
# --------------------------------------------------

@mit_sts_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_mit():
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    users = User.query.order_by(User.name.asc()).all()
    coaches = User.query.filter(
        User.role.in_(["coach", "admin", "training_director"])
    ).order_by(User.name.asc()).all()

    if request.method == "POST":
        user_source = request.form.get("user_source", "existing").strip()
        store_number = request.form.get("store_number", "").strip()
        coach_user_id = request.form.get("coach_user_id", "").strip()
        current_level = request.form.get("current_level", "1").strip()
        start_date = request.form.get("start_date", "").strip()
        sts_status = request.form.get("sts_status", "on_track").strip()
        next_review_date = request.form.get("next_review_date", "").strip()
        notes = request.form.get("notes", "").strip()

        user = None

        if user_source == "new":
            new_name = request.form.get("new_name", "").strip()
            new_username = request.form.get("new_username", "").strip()
            new_password = request.form.get("new_password", "").strip()

            if not new_name or not new_username or not new_password:
                flash("New MIT name, username, and temporary password are required.", "danger")
                return render_template(
                    "mit_sts/mit_form.html",
                    page_title="Create MIT Profile",
                    submit_label="Create MIT Profile",
                    mit=None,
                    users=users,
                    coaches=coaches,
                    user=current_user,
                )

            existing_user = User.query.filter_by(username=new_username).first()
            if existing_user:
                flash("That username already exists.", "danger")
                return render_template(
                    "mit_sts/mit_form.html",
                    page_title="Create MIT Profile",
                    submit_label="Create MIT Profile",
                    mit=None,
                    users=users,
                    coaches=coaches,
                    user=current_user,
                )

            user = User(
                name=new_name,
                username=new_username,
                role="mit",
                store_number=store_number or None,
                is_active_user=True,
            )
            user.set_password(new_password)
            db.session.add(user)
            db.session.flush()

        else:
            user_id = request.form.get("user_id", "").strip()

            if not user_id:
                flash("MIT user is required.", "danger")
                return render_template(
                    "mit_sts/mit_form.html",
                    page_title="Create MIT Profile",
                    submit_label="Create MIT Profile",
                    mit=None,
                    users=users,
                    coaches=coaches,
                    user=current_user,
                )

            user = User.query.get(int(user_id))
            if not user:
                flash("Selected user was not found.", "danger")
                return render_template(
                    "mit_sts/mit_form.html",
                    page_title="Create MIT Profile",
                    submit_label="Create MIT Profile",
                    mit=None,
                    users=users,
                    coaches=coaches,
                    user=current_user,
                )

        existing_profile = MITProfile.query.filter_by(user_id=user.id).first()
        if existing_profile:
            flash("This user already has an MIT STS profile.", "danger")
            return render_template(
                "mit_sts/mit_form.html",
                page_title="Create MIT Profile",
                submit_label="Create MIT Profile",
                mit=None,
                users=users,
                coaches=coaches,
                user=current_user,
            )

        try:
            current_level_int = int(current_level)
        except ValueError:
            current_level_int = 1

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

        if should_force_mit_role(user):
            user.role = "mit"
        if store_number:
            user.store_number = store_number

        mit = MITProfile(
            user_id=user.id,
            store_number=store_number or None,
            coach_user_id=int(coach_user_id) if coach_user_id else None,
            current_level=current_level_int,
            target_level=get_target_level(current_level_int),
            start_date=start_date_obj,
            sts_status=sts_status or "on_track",
            next_review_date=next_review_date_obj,
            notes=notes or None,
        )

        db.session.add(mit)
        db.session.commit()

        ensure_progress_rows_for_mit(mit)

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


# --------------------------------------------------
# MY MIT
# --------------------------------------------------

@mit_sts_bp.route("/my")
@login_required
def my_mit():
    profile = MITProfile.query.filter_by(user_id=current_user.id).first()

    if profile:
        return redirect(url_for("mit_sts.view_mit", mit_id=profile.id))

    if is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    flash("No MIT profile found.", "danger")
    return redirect(url_for("auth.logout"))


# --------------------------------------------------
# VIEW MIT
# --------------------------------------------------

@mit_sts_bp.route("/<int:mit_id>")
@login_required
def view_mit(mit_id):
    profile = MITProfile.query.get_or_404(mit_id)

    if not user_can_access_mit_profile(profile):
        return redirect(url_for("mit_sts.dashboard"))

    ensure_progress_rows_for_mit(profile)

    level_1_progress = calculate_level_progress(profile.id, 1)
    level_2_progress = calculate_level_progress(profile.id, 2)
    level_3_progress = calculate_level_progress(profile.id, 3)

    overall_progress = 0
    all_templates = MITLevelTemplate.query.all()
    if all_templates:
        all_template_ids = [item.id for item in all_templates]
        completed_total = MITLevelProgress.query.filter(
            MITLevelProgress.mit_profile_id == profile.id,
            MITLevelProgress.template_item_id.in_(all_template_ids),
            MITLevelProgress.status == "complete",
        ).count()
        overall_progress = round((completed_total / len(all_templates)) * 100)

    incomplete_count = MITLevelProgress.query.join(
        MITLevelTemplate,
        MITLevelProgress.template_item_id == MITLevelTemplate.id
    ).filter(
        MITLevelProgress.mit_profile_id == profile.id,
        MITLevelTemplate.level_number == profile.current_level,
        MITLevelProgress.status != "complete"
    ).count()

    open_tasks_count, overdue_tasks_count, submitted_tasks_count = get_task_counts(profile.id)

    promotions = MITPromotion.query.filter_by(
        mit_profile_id=profile.id
    ).order_by(MITPromotion.effective_date.desc()).all()

    return render_template(
        "mit_sts/mit_detail.html",
        mit=profile,
        profile=profile,
        level_1_progress=level_1_progress,
        level_2_progress=level_2_progress,
        level_3_progress=level_3_progress,
        overall_progress=overall_progress,
        incomplete_count=incomplete_count,
        open_tasks_count=open_tasks_count,
        overdue_tasks_count=overdue_tasks_count,
        submitted_tasks_count=submitted_tasks_count,
        promotions=promotions,
        user=current_user,
        can_edit=is_coach(),
        can_manage_templates=is_coach(),
    )


# --------------------------------------------------
# VIEW LEVEL
# --------------------------------------------------

@mit_sts_bp.route("/mits/<int:mit_id>/level/<int:level_number>")
@login_required
def view_level(mit_id, level_number):
    if level_number not in [1, 2, 3]:
        flash("Invalid level.", "danger")
        return redirect(url_for("mit_sts.view_mit", mit_id=mit_id))

    profile = MITProfile.query.get_or_404(mit_id)

    if not user_can_access_mit_profile(profile):
        return redirect(url_for("mit_sts.dashboard"))

    ensure_progress_rows_for_mit(profile)

    templates = MITLevelTemplate.query.filter_by(level_number=level_number).order_by(
        MITLevelTemplate.category.asc(),
        MITLevelTemplate.sort_order.asc(),
        MITLevelTemplate.id.asc(),
    ).all()

    progress_rows = MITLevelProgress.query.filter_by(mit_profile_id=profile.id).all()
    progress_map = {row.template_item_id: row for row in progress_rows}

    grouped_items = defaultdict(list)
    for template in templates:
        grouped_items[template.category or "General"].append(template)

    active_task_map = get_active_task_map(profile.id, level_number=level_number)
    all_linked_task_map = get_all_linked_task_map(profile.id)

    level_progress = calculate_level_progress(profile.id, level_number)
    is_complete = level_progress == 100 and len(templates) > 0

    return render_template(
        "mit_sts/level_detail.html",
        mit=profile,
        level_number=level_number,
        grouped_items=dict(grouped_items),
        progress_map=progress_map,
        active_task_map=active_task_map,
        all_linked_task_map=all_linked_task_map,
        level_progress=level_progress,
        is_complete=is_complete,
        task_display_status=task_display_status,
        user=current_user,
        can_edit=is_coach(),
        can_manage_templates=is_coach(),
    )


# --------------------------------------------------
# UPDATE PROGRESS
# --------------------------------------------------

@mit_sts_bp.route("/progress/<int:progress_id>/status", methods=["POST"])
@login_required
def update_progress(progress_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    progress = MITLevelProgress.query.get_or_404(progress_id)
    new_status = request.form.get("status", "not_started").strip()

    if new_status not in ["not_started", "in_progress", "complete"]:
        flash("Invalid status.", "danger")
        template = MITLevelTemplate.query.get(progress.template_item_id)
        return redirect(
            url_for(
                "mit_sts.view_level",
                mit_id=progress.mit_profile_id,
                level_number=template.level_number if template else 1,
            )
        )

    progress.status = new_status

    notes = request.form.get("notes", "").strip()
    if notes:
        progress.notes = notes

    linked_tasks = MITTask.query.filter_by(
        mit_profile_id=progress.mit_profile_id,
        related_template_item_id=progress.template_item_id,
    ).order_by(MITTask.id.desc()).all()

    if new_status == "complete":
        progress.completed_date = datetime.utcnow().date()
        progress.verified_by_user_id = current_user.id

        for task in linked_tasks:
            if task.status != "cancelled":
                task.status = "verified"
                task.completed_at = datetime.utcnow()
    elif new_status == "in_progress":
        progress.completed_date = None
        progress.verified_by_user_id = None

        for task in linked_tasks:
            if task.status not in ["cancelled", "verified"]:
                task.status = "in_progress"
                task.completed_at = None
    else:
        progress.completed_date = None
        progress.verified_by_user_id = None

        for task in linked_tasks:
            if task.status != "cancelled":
                task.status = "open"
                task.completed_at = None

    db.session.commit()

    template = MITLevelTemplate.query.get(progress.template_item_id)
    flash("STS item updated.", "success")
    return redirect(
        url_for(
            "mit_sts.view_level",
            mit_id=progress.mit_profile_id,
            level_number=template.level_number if template else 1,
        )
    )


# --------------------------------------------------
# EDIT MIT
# --------------------------------------------------

@mit_sts_bp.route("/<int:mit_id>/edit", methods=["GET", "POST"])
@login_required
def edit_mit(mit_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    mit = MITProfile.query.get_or_404(mit_id)
    users = User.query.order_by(User.name.asc()).all()
    coaches = User.query.filter(
        User.role.in_(["coach", "admin", "training_director"])
    ).order_by(User.name.asc()).all()

    if request.method == "POST":
        user_id_raw = request.form.get("user_id", "").strip()
        if user_id_raw:
            target_user = User.query.get(int(user_id_raw))
            if target_user:
                mit.user_id = target_user.id
                if should_force_mit_role(target_user):
                    target_user.role = "mit"

        mit.store_number = request.form.get("store_number", "").strip() or None

        coach_user_id = request.form.get("coach_user_id", "").strip()
        mit.coach_user_id = int(coach_user_id) if coach_user_id else None

        try:
            mit.current_level = int(request.form.get("current_level", mit.current_level))
        except ValueError:
            pass

        mit.target_level = get_target_level(mit.current_level)
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

        if mit.mit_user and mit.store_number:
            mit.mit_user.store_number = mit.store_number

        db.session.commit()

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


# --------------------------------------------------
# NEW TASK BOARD
# --------------------------------------------------

@mit_sts_bp.route("/mits/<int:mit_id>/tasks/new", methods=["GET", "POST"])
@login_required
def new_task(mit_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    profile = MITProfile.query.get_or_404(mit_id)
    ensure_progress_rows_for_mit(profile)

    grouped_template_items = defaultdict(list)
    for item in MITLevelTemplate.query.order_by(
        MITLevelTemplate.level_number.asc(),
        MITLevelTemplate.category.asc(),
        MITLevelTemplate.sort_order.asc(),
        MITLevelTemplate.id.asc(),
    ).all():
        grouped_template_items[item.level_number].append(item)

    progress_rows = MITLevelProgress.query.filter_by(mit_profile_id=profile.id).all()
    progress_map = {row.template_item_id: row for row in progress_rows}

    active_task_map = get_active_task_map(profile.id)
    all_linked_task_map = get_all_linked_task_map(profile.id)

    open_tasks_count, overdue_tasks_count, submitted_tasks_count = get_task_counts(profile.id)

    return render_template(
        "mit_sts/mit_task_form.html",
        mit=profile,
        grouped_template_items=dict(grouped_template_items),
        progress_map=progress_map,
        active_task_map=active_task_map,
        all_linked_task_map=all_linked_task_map,
        task_display_status=task_display_status,
        page_title="Assign MIT Tasks",
        submit_label="Assign Task",
        open_tasks_count=open_tasks_count,
        overdue_tasks_count=overdue_tasks_count,
        submitted_tasks_count=submitted_tasks_count,
        user=current_user,
        can_manage_templates=is_coach(),
    )


# --------------------------------------------------
# BOARD TASK ROUTES
# --------------------------------------------------

@mit_sts_bp.route("/tasks/board/<int:progress_id>/assign", methods=["POST"])
@login_required
def assign_board_task(progress_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    progress = MITLevelProgress.query.get_or_404(progress_id)
    template = MITLevelTemplate.query.get_or_404(progress.template_item_id)
    profile = MITProfile.query.get_or_404(progress.mit_profile_id)

    title = request.form.get("title", "").strip() or template.item_name
    due_date_raw = request.form.get("due_date", "").strip()
    priority = request.form.get("priority", "medium").strip()
    notes = request.form.get("notes", "").strip()
    status = request.form.get("status", "open").strip()
    redirect_mit_id = request.args.get("mit_id", type=int) or profile.id

    existing_open_task = MITTask.query.filter(
        MITTask.mit_profile_id == progress.mit_profile_id,
        MITTask.related_template_item_id == template.id,
        MITTask.status.in_(["open", "in_progress", "submitted"])
    ).first()

    if existing_open_task:
        flash("There is already an active task linked to this STS item.", "danger")
        return redirect(url_for("mit_sts.new_task", mit_id=redirect_mit_id))

    due_date_obj = None
    if due_date_raw:
        try:
            due_date_obj = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
        except ValueError:
            pass

    if priority not in ["low", "medium", "high"]:
        priority = "medium"

    if status not in ["open", "in_progress", "submitted", "verified", "cancelled"]:
        status = "open"

    task = MITTask(
        mit_profile_id=progress.mit_profile_id,
        title=title,
        description=template.item_description or None,
        related_template_item_id=template.id,
        assigned_by_user_id=current_user.id,
        due_date=due_date_obj,
        priority=priority,
        status=status,
        notes=notes or None,
    )

    db.session.add(task)
    sync_progress_from_task(task, progress)
    db.session.commit()

    flash("Task assigned successfully.", "success")
    return redirect(url_for("mit_sts.new_task", mit_id=redirect_mit_id))


@mit_sts_bp.route("/tasks/board/<int:task_id>/manage", methods=["POST"])
@login_required
def manage_board_task(task_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    task = MITTask.query.get_or_404(task_id)
    profile = MITProfile.query.get_or_404(task.mit_profile_id)
    redirect_mit_id = request.args.get("mit_id", type=int) or profile.id

    title = request.form.get("title", "").strip()
    due_date_raw = request.form.get("due_date", "").strip()
    priority = request.form.get("priority", "medium").strip()
    notes = request.form.get("notes", "").strip()

    submit_action = request.form.get("submit_action", "").strip()
    selected_status = request.form.get("status", "").strip()

    if title:
        task.title = title

    if priority in ["low", "medium", "high"]:
        task.priority = priority

    if due_date_raw:
        try:
            task.due_date = datetime.strptime(due_date_raw, "%Y-%m-%d").date()
        except ValueError:
            pass
    else:
        task.due_date = None

    task.notes = notes or None

    progress = None
    if getattr(task, "related_template_item_id", None):
        progress = MITLevelProgress.query.filter_by(
            mit_profile_id=task.mit_profile_id,
            template_item_id=task.related_template_item_id,
        ).first()

    if submit_action == "unassign":
        db.session.delete(task)

        if progress:
            active_remaining = MITTask.query.filter(
                MITTask.mit_profile_id == progress.mit_profile_id,
                MITTask.related_template_item_id == progress.template_item_id,
                MITTask.status.in_(["open", "in_progress", "submitted"])
            ).count()

            if active_remaining <= 1 and progress.status != "complete":
                progress.status = "not_started"
                progress.completed_date = None
                progress.verified_by_user_id = None

        db.session.commit()
        flash("Task unassigned.", "success")
        return redirect(url_for("mit_sts.new_task", mit_id=redirect_mit_id))

    if submit_action == "save":
        if selected_status in ["open", "in_progress", "submitted", "verified", "cancelled"]:
            task.status = selected_status

        sync_progress_from_task(task, progress)

        db.session.commit()
        flash("Task updated.", "success")
        return redirect(url_for("mit_sts.new_task", mit_id=redirect_mit_id))

    flash("No action selected.", "danger")
    return redirect(url_for("mit_sts.new_task", mit_id=redirect_mit_id))


# --------------------------------------------------
# QUICK ADD TASK
# --------------------------------------------------

@mit_sts_bp.route("/tasks/<int:task_id>/quick-add", methods=["POST"])
@login_required
def quick_add_task(task_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

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
        priority=priority if priority in ["low", "medium", "high"] else "medium",
        status="open",
        notes=notes or None,
    )
    db.session.add(task)

    progress.status = "in_progress"
    progress.completed_date = None
    progress.verified_by_user_id = None

    db.session.commit()

    flash("Task assigned to this STS item.", "success")
    return redirect(url_for("mit_sts.view_level", mit_id=progress.mit_profile_id, level_number=template.level_number))


# --------------------------------------------------
# TASKS
# --------------------------------------------------

@mit_sts_bp.route("/tasks/<int:mit_id>")
@login_required
def view_tasks(mit_id):
    profile = MITProfile.query.get_or_404(mit_id)

    if not is_coach() and profile.user_id != current_user.id:
        return redirect(url_for("mit_sts.dashboard"))

    tasks = MITTask.query.filter_by(mit_profile_id=mit_id).all()

    open_tasks_count, overdue_tasks_count, submitted_tasks_count = get_task_counts(profile.id)

    return render_template(
        "mit_sts/mit_tasks.html",
        tasks=tasks,
        profile=profile,
        mit=profile,
        open_tasks_count=open_tasks_count,
        overdue_tasks_count=overdue_tasks_count,
        submitted_tasks_count=submitted_tasks_count,
        user=current_user,
        can_edit=is_coach(),
    )


# --------------------------------------------------
# UPDATE TASK STATUS
# --------------------------------------------------

@mit_sts_bp.route("/tasks/<int:task_id>/status", methods=["POST"])
@login_required
def update_task_status(task_id):
    task = MITTask.query.get_or_404(task_id)
    profile = MITProfile.query.get_or_404(task.mit_profile_id)

    if not user_can_access_mit_profile(profile):
        return redirect(url_for("mit_sts.dashboard"))

    requested_status = request.form.get("status", "").strip()

    coach_allowed_statuses = ["open", "in_progress", "submitted", "verified", "cancelled"]
    mit_allowed_statuses = ["in_progress", "submitted"]

    if is_coach():
        allowed_statuses = coach_allowed_statuses
    else:
        if getattr(task, "related_template_item_id", None) is None:
            flash("You cannot update that task from your MIT dashboard.", "danger")
            return redirect_for_task(task)
        allowed_statuses = mit_allowed_statuses

    if requested_status not in allowed_statuses:
        flash("Invalid task status.", "danger")
        return redirect_for_task(task)

    progress = get_task_progress_row(task)

    if not is_coach() and requested_status == "submitted":
        if task.status not in ["open", "in_progress"]:
            flash("Only active tasks can be submitted for verification.", "danger")
            return redirect_for_task(task)

    task.status = requested_status
    sync_progress_from_task(task, progress)
    db.session.commit()

    if requested_status == "submitted":
        flash("Task submitted for verification.", "success")
    elif requested_status == "verified":
        flash("Task verified successfully.", "success")
    else:
        flash("Task status updated.", "success")

    return redirect_for_task(task)


@mit_sts_bp.route("/tasks/<int:task_id>/submit", methods=["POST"])
@login_required
def submit_task_for_verification(task_id):
    task = MITTask.query.get_or_404(task_id)
    profile = MITProfile.query.get_or_404(task.mit_profile_id)

    if not user_can_access_mit_profile(profile):
        return redirect(url_for("mit_sts.dashboard"))

    if is_coach():
        # Coaches can still use this shortcut if they are reviewing as the MIT.
        pass
    elif getattr(task, "related_template_item_id", None) is None:
        flash("That task cannot be submitted from the MIT side.", "danger")
        return redirect_for_task(task)

    if task.status not in ["open", "in_progress"]:
        flash("Only active tasks can be submitted for verification.", "danger")
        return redirect_for_task(task)

    progress = get_task_progress_row(task)
    task.status = "submitted"
    sync_progress_from_task(task, progress)
    db.session.commit()

    flash("Task submitted for verification.", "success")
    return redirect_for_task(task)


@mit_sts_bp.route("/tasks/<int:task_id>/verify", methods=["POST"])
@login_required
def verify_task(task_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    task = MITTask.query.get_or_404(task_id)
    progress = get_task_progress_row(task)

    if task.status == "cancelled":
        flash("Cancelled tasks cannot be verified.", "danger")
        return redirect_for_task(task)

    task.status = "verified"
    sync_progress_from_task(task, progress)
    db.session.commit()

    flash("Task verified successfully.", "success")
    return redirect_for_task(task)


@mit_sts_bp.route("/tasks/<int:task_id>/send-back", methods=["POST"])
@login_required
def send_task_back(task_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    task = MITTask.query.get_or_404(task_id)
    progress = get_task_progress_row(task)

    if task.status == "verified":
        task.completed_at = None

    task.status = "in_progress"
    sync_progress_from_task(task, progress)
    db.session.commit()

    flash("Task sent back to MIT.", "success")
    return redirect_for_task(task)


# --------------------------------------------------
# PROMOTIONS
# --------------------------------------------------

@mit_sts_bp.route("/promotion-queue")
@login_required
def promotion_queue():
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    queue = MITPromotion.query.all()
    return render_template("mit_sts/promotion_queue.html", queue=queue)


@mit_sts_bp.route("/promote/<int:mit_id>", methods=["POST"])
@login_required
def promote_mit(mit_id):
    if not is_coach():
        return redirect(url_for("mit_sts.dashboard"))

    promotion = MITPromotion(
        mit_profile_id=mit_id,
        approved_by_user_id=current_user.id,
        effective_date=date.today(),
        from_level=1,
        to_level="2",
    )

    db.session.add(promotion)
    db.session.commit()

    return redirect(url_for("mit_sts.promotion_queue"))


# --------------------------------------------------
# EXPORT
# --------------------------------------------------

@mit_sts_bp.route("/export/<int:mit_id>")
@login_required
def export_tasks_pdf(mit_id):
    profile = MITProfile.query.get_or_404(mit_id)

    if not is_coach() and profile.user_id != current_user.id:
        return redirect(url_for("mit_sts.dashboard"))

    tasks = (
        MITTask.query
        .filter(
            MITTask.mit_profile_id == mit_id,
            MITTask.status != "cancelled",
        )
        .order_by(
            MITTask.due_date.asc().nullslast(),
            MITTask.id.asc(),
        )
        .all()
    )

    open_count = sum(1 for t in tasks if t.status == "open")
    in_progress_count = sum(1 for t in tasks if t.status == "in_progress")
    submitted_count = sum(1 for t in tasks if t.status == "submitted")
    verified_count = sum(1 for t in tasks if t.status == "verified")
    overdue_count = sum(
        1 for t in tasks
        if t.due_date and t.due_date < date.today() and t.status not in ["verified", "cancelled", "submitted"]
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = styles["Heading1"]
    title_style.fontName = "Helvetica-Bold"
    title_style.fontSize = 20
    title_style.leading = 24
    title_style.textColor = colors.HexColor("#0F172A")

    section_title_style = styles["Heading2"]
    section_title_style.fontName = "Helvetica-Bold"
    section_title_style.fontSize = 12
    section_title_style.leading = 14
    section_title_style.textColor = colors.HexColor("#334155")
    section_title_style.spaceAfter = 8

    body_style = styles["BodyText"]
    body_style.fontName = "Helvetica"
    body_style.fontSize = 9
    body_style.leading = 12
    body_style.textColor = colors.HexColor("#334155")

    small_style = ParagraphStyle(
        "SmallStyle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748B"),
    )

    label_style = ParagraphStyle(
        "LabelStyle",
        parent=styles["BodyText"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748B"),
    )

    story = []

    mit_name = profile.mit_user.name if profile.mit_user else f"MIT #{profile.id}"
    coach_name = profile.coach_user.name if profile.coach_user else "Not assigned"
    store_number = profile.store_number or "-"
    current_level = profile.current_level or "-"
    status_value = profile.sts_status.replace("_", " ").title() if profile.sts_status else "-"

    story.append(Paragraph("Boston Pie Academy", small_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Assigned Task Report", title_style))
    story.append(Spacer(1, 12))

    info_data = [
        [
            Paragraph("<b>MIT</b><br/>" + mit_name, body_style),
            Paragraph("<b>Store</b><br/>" + str(store_number), body_style),
            Paragraph("<b>Coach</b><br/>" + coach_name, body_style),
        ],
        [
            Paragraph("<b>Current Level</b><br/>" + str(current_level), body_style),
            Paragraph("<b>STS Status</b><br/>" + status_value, body_style),
            Paragraph("<b>Report Date</b><br/>" + date.today().strftime("%Y-%m-%d"), body_style),
        ],
    ]

    info_table = Table(info_data, colWidths=[170, 170, 170])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
        ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(info_table)
    story.append(Spacer(1, 16))

    story.append(Paragraph("Task Summary", section_title_style))

    summary_data = [
        [
            Paragraph("<b>Total Tasks</b><br/>" + str(len(tasks)), body_style),
            Paragraph("<b>Open</b><br/>" + str(open_count), body_style),
            Paragraph("<b>In Progress</b><br/>" + str(in_progress_count), body_style),
            Paragraph("<b>Submitted</b><br/>" + str(submitted_count), body_style),
            Paragraph("<b>Verified</b><br/>" + str(verified_count), body_style),
            Paragraph("<b>Overdue</b><br/>" + str(overdue_count), body_style),
        ]
    ]

    summary_table = Table(summary_data, colWidths=[84, 72, 82, 78, 72, 72])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
        ("INNERGRID", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(summary_table)
    story.append(Spacer(1, 18))

    story.append(Paragraph("Assigned Tasks", section_title_style))

    if tasks:
        task_rows = [[
            Paragraph("<b>Task</b>", label_style),
            Paragraph("<b>Status</b>", label_style),
            Paragraph("<b>Priority</b>", label_style),
            Paragraph("<b>Due</b>", label_style),
            Paragraph("<b>Notes</b>", label_style),
        ]]

        for task in tasks:
            due_text = task.due_date.strftime("%Y-%m-%d") if task.due_date else "-"
            notes_text = task.notes if task.notes else "-"
            status_text = task.status.replace("_", " ").title()
            priority_text = (task.priority or "-").title()

            task_rows.append([
                Paragraph(task.title or "-", body_style),
                Paragraph(status_text, body_style),
                Paragraph(priority_text, body_style),
                Paragraph(due_text, body_style),
                Paragraph(notes_text, body_style),
            ])

        task_table = Table(
            task_rows,
            colWidths=[185, 72, 62, 62, 147],
            repeatRows=1,
        )

        table_style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#CBD5E1")),
            ("GRID", (0, 1), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])

        for row_index, task in enumerate(tasks, start=1):
            if task.status == "verified":
                bg = colors.HexColor("#F0FDF4")
            elif task.status == "submitted":
                bg = colors.HexColor("#FFFBEB")
            elif task.due_date and task.due_date < date.today() and task.status not in ["verified", "cancelled", "submitted"]:
                bg = colors.HexColor("#FEF2F2")
            else:
                bg = colors.white

            table_style.add("BACKGROUND", (0, row_index), (-1, row_index), bg)

        task_table.setStyle(table_style)
        story.append(task_table)
    else:
        empty_box = Table(
            [[Paragraph("No assigned tasks found for this MIT.", body_style)]],
            colWidths=[528],
        )
        empty_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(empty_box)

    doc.build(story)

    buffer.seek(0)
    safe_name = mit_name.replace(" ", "_").replace("/", "-")
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{safe_name}_assigned_tasks.pdf",
        mimetype="application/pdf",
    )

# --- MIT TASK VERIFICATION ROUTES ---

@mit_sts_bp.route("/task/<int:task_id>/submit", methods=["POST"])
@login_required
def submit_task_for_verification(task_id):
    task = MITTask.query.get_or_404(task_id)

    if current_user.role != "mit":
        flash("Only MITs can submit tasks.", "danger")
        return redirect(request.referrer or url_for("mit_sts.dashboard"))

    task.status = "submitted"
    task.updated_at = datetime.utcnow()

    db.session.commit()
    flash("Task submitted for verification.", "success")

    return redirect(request.referrer or url_for("mit_sts.dashboard"))


@mit_sts_bp.route("/task/<int:task_id>/verify", methods=["POST"])
@login_required
def verify_task(task_id):
    task = MITTask.query.get_or_404(task_id)

    if current_user.role not in ["coach", "admin", "training_director"]:
        flash("Not authorized.", "danger")
        return redirect(request.referrer or url_for("mit_sts.dashboard"))

    task.status = "verified"
    task.updated_at = datetime.utcnow()

    progress = MITLevelProgress.query.filter_by(
        mit_id=task.mit_id,
        level_template_id=task.level_template_id
    ).first()

    if progress:
        progress.status = "complete"
        progress.completed_date = datetime.utcnow()
        progress.verified_by = current_user.id

    db.session.commit()
    flash("Task verified.", "success")

    return redirect(request.referrer or url_for("mit_sts.dashboard"))


@mit_sts_bp.route("/task/<int:task_id>/send-back", methods=["POST"])
@login_required
def send_task_back(task_id):
    task = MITTask.query.get_or_404(task_id)

    if current_user.role not in ["coach", "admin", "training_director"]:
        flash("Not authorized.", "danger")
        return redirect(request.referrer or url_for("mit_sts.dashboard"))

    task.status = "in_progress"
    task.updated_at = datetime.utcnow()

    db.session.commit()
    flash("Task sent back to MIT.", "warning")

    return redirect(request.referrer or url_for("mit_sts.dashboard"))
