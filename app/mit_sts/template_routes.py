from .routes_shared import *

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
