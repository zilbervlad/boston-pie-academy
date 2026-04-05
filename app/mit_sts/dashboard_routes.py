from .routes_shared import *

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
