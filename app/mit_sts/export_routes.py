from .routes_shared import *

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
