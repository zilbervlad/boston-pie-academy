from .routes_shared import *

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
