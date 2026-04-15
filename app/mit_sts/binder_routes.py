from datetime import datetime

from flask import render_template, request, redirect, flash, url_for
from flask_login import login_required, current_user
from sqlalchemy import func

from app.extensions import db
from app.models import (
    MITProfile,
    MITBinderTemplate,
    MITBinderField,
    MITBinderSubmission,
    MITBinderEntry,
)

from .routes import mit_sts_bp
from .routes_shared import user_can_access_mit_profile


def can_manage_binder_templates():
    return current_user.is_authenticated and current_user.role in ["admin", "training_director", "coach"]


@mit_sts_bp.route("/mits/<int:mit_id>/binder/<int:level>")
@login_required
def view_binder(mit_id, level):
    mit = MITProfile.query.get_or_404(mit_id)

    if not user_can_access_mit_profile(mit):
        flash("No access.", "danger")
        return redirect("/")

    templates = MITBinderTemplate.query.filter_by(
        level_number=level,
        is_active=True
    ).order_by(
        MITBinderTemplate.sort_order.asc(),
        MITBinderTemplate.id.asc()
    ).all()

    submissions = {
        s.template_id: s
        for s in MITBinderSubmission.query.filter_by(mit_profile_id=mit_id).all()
    }

    return render_template(
        "mit_sts/binder_level.html",
        mit=mit,
        templates=templates,
        submissions=submissions,
        level=level,
        user=current_user,
    )


@mit_sts_bp.route("/binder/<int:template_id>/add-row/<int:mit_id>", methods=["POST"])
@login_required
def add_binder_row(template_id, mit_id):
    mit = MITProfile.query.get_or_404(mit_id)

    if not user_can_access_mit_profile(mit):
        flash("No access.", "danger")
        return redirect("/")

    submission = MITBinderSubmission.query.filter_by(
        mit_profile_id=mit_id,
        template_id=template_id
    ).first()

    if not submission:
        submission = MITBinderSubmission(
            mit_profile_id=mit_id,
            template_id=template_id,
            status="in_progress",
            submitted_at=datetime.utcnow(),
        )
        db.session.add(submission)
        db.session.flush()

    if submission.sheet_approved_at:
        flash("This sheet has already been approved and is locked.", "warning")
        return redirect(request.referrer or "/")

    max_row = db.session.query(func.max(MITBinderEntry.row_index)).filter_by(
        submission_id=submission.id
    ).scalar()

    next_row = (max_row or 0) + 1

    for key, value in request.form.items():
        if key.startswith("field_"):
            field_id = int(key.split("_")[1])

            entry = MITBinderEntry(
                submission_id=submission.id,
                field_id=field_id,
                row_index=next_row,
                value=value
            )
            db.session.add(entry)

    db.session.commit()

    flash("Row added.", "success")
    return redirect(request.referrer or "/")


@mit_sts_bp.route("/binder/<int:submission_id>/delete-row/<int:row_index>", methods=["POST"])
@login_required
def delete_binder_row(submission_id, row_index):
    submission = MITBinderSubmission.query.get_or_404(submission_id)
    mit = MITProfile.query.get_or_404(submission.mit_profile_id)

    if not user_can_access_mit_profile(mit):
        flash("No access.", "danger")
        return redirect("/")

    if submission.sheet_approved_at:
        flash("Approved sheets are locked.", "warning")
        return redirect(request.referrer or "/")

    rows = MITBinderEntry.query.filter_by(
        submission_id=submission_id,
        row_index=row_index
    ).all()

    for row in rows:
        db.session.delete(row)

    db.session.commit()

    flash("Row deleted.", "success")
    return redirect(request.referrer or "/")


def _create_template_if_missing(level_number, title, template_type, sort_order, instructions, fields):
    existing = MITBinderTemplate.query.filter_by(
        level_number=level_number,
        title=title
    ).first()

    if existing:
        return False

    template = MITBinderTemplate(
        level_number=level_number,
        title=title,
        template_type=template_type,
        instructions=instructions,
        sort_order=sort_order,
        is_active=True
    )
    db.session.add(template)
    db.session.flush()

    for index, (label, field_type) in enumerate(fields):
        db.session.add(
            MITBinderField(
                template_id=template.id,
                label=label,
                field_type=field_type,
                sort_order=index
            )
        )

    return True


@mit_sts_bp.route("/binder/setup-demo")
@login_required
def setup_binder_demo():
    if current_user.role not in ["admin", "coach", "training_director"]:
        flash("You do not have access to that page.", "error")
        return redirect("/")

    created_any = False

    # --------------------------------------------------
    # LEVEL 1
    # --------------------------------------------------
    created_any = _create_template_if_missing(
        level_number=1,
        title="Customer Satisfaction Callbacks",
        template_type="log",
        sort_order=1,
        instructions="""PURPOSE:
Customer call backs are a great way to build loyalty, thank customers for their business, and recover concerns before you lose them.

HOW TO COMPLETE:
Work with your manager to understand your store's best practices around callbacks.
Use a short, friendly script.
Tell the customer you only need a few minutes.
Mention the product they ordered and the date.
Ask if there is anything you can do to improve their experience.
Thank them for their business and their time.

COACHING FOCUS:
- Positive tone
- Ownership
- Clear documentation
- Follow-up discipline

GOAL:
Develop the habit of doing callbacks consistently and logging what happened.""",
        fields=[
            ("Date", "date"),
            ("Customer Name", "text"),
            ("Order #", "text"),
            ("Comments", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Tracker Feedback Callbacks",
        template_type="log",
        sort_order=2,
        instructions="""PURPOSE:
Callbacks are made to customers who gave 3 stars or less so the store can recover the experience and show ownership.

HOW TO COMPLETE:
Review tracker feedback for low-star orders.
Call the customer promptly.
Listen first, then respond professionally.
Document the customer name, date, and a short summary of the concern or resolution.

COACHING FOCUS:
- Recovery mindset
- Listening skills
- Professional tone
- Closing the loop

GOAL:
Show that customer concerns are taken seriously and handled quickly.""",
        fields=[
            ("Date", "date"),
            ("Customer Name", "text"),
            ("Comments", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Service Tracker (Opens)",
        template_type="log",
        sort_order=3,
        instructions="""PURPOSE:
Track opening service performance and compare results to the Level 1 goal of under 25-minute ADT.

HOW TO COMPLETE:
Record the date, sales, and ADT for the opening shift.
Use the tracker consistently so patterns can be reviewed with your coach or manager.

COACHING FOCUS:
- Service awareness
- Consistent tracking
- Understanding trends
- Ownership of opening execution

GOAL:
Build awareness around service performance and reinforce the under-25-minute expectation.""",
        fields=[
            ("Date", "date"),
            ("Sales", "number"),
            ("ADT", "number"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Service Tracker (Closes)",
        template_type="log",
        sort_order=4,
        instructions="""PURPOSE:
Track closing service performance and compare results to the Level 1 goal of under 25-minute ADT.

HOW TO COMPLETE:
Record the date, sales, and ADT for the closing shift.
Use this to identify patterns, coaching opportunities, and consistency on closes.

COACHING FOCUS:
- Service awareness
- Closing execution
- Consistency
- Accountability

GOAL:
Create a routine of measuring close performance instead of guessing.""",
        fields=[
            ("Date", "date"),
            ("Sales", "number"),
            ("ADT", "number"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Food Cost Control Worksheet",
        template_type="worksheet",
        sort_order=5,
        instructions="""PURPOSE:
This worksheet helps Level 1 MITs understand food usage, variance, and how actions affect food cost.

HOW TO COMPLETE:
Review ideal versus actual food usage with your manager.
Write down the variance and identify one or more actions to improve the result.
Use the action plan section to document what will change on future shifts.

COACHING FOCUS:
- Portion control
- Waste awareness
- Inventory accuracy
- Action planning

GOAL:
Understand that food variance is controllable and should be managed intentionally.""",
        fields=[
            ("Ideal Food %", "number"),
            ("Actual Food %", "number"),
            ("Variance", "number"),
            ("Action Plan", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Systems In Your Store",
        template_type="worksheet",
        sort_order=6,
        instructions="""PURPOSE:
Build understanding of the systems used in the store and why managers are expected to follow and teach them.

HOW TO COMPLETE:
Discuss store systems with your trainer or manager.
List the system name, how it is used, and where there may be improvement opportunities.
This should reflect real processes used in your store.

COACHING FOCUS:
- Systems thinking
- Standardization
- Process awareness
- Learning through observation

GOAL:
Understand that strong shifts depend on following systems consistently.""",
        fields=[
            ("System Name", "text"),
            ("How It's Used", "textarea"),
            ("Improvement Opportunity", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Having Tough Conversations",
        template_type="worksheet",
        sort_order=7,
        instructions="""PURPOSE:
Practice how to address behavior, image, and standards issues instead of ignoring them.

HOW TO COMPLETE:
Choose a real or sample situation.
Write how you would approach it and what outcome you are aiming for.
Focus on respectful, direct coaching language.

COACHING FOCUS:
- Confidence
- Clarity
- Respectful confrontation
- Coaching language

GOAL:
Reinforce the idea that silence is acceptance and leaders must address issues early.""",
        fields=[
            ("Situation", "textarea"),
            ("Approach", "textarea"),
            ("Outcome", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Store Performance Goals",
        template_type="worksheet",
        sort_order=8,
        instructions="""PURPOSE:
Help the MIT understand what goals matter in the store and how daily execution connects to those targets.

HOW TO COMPLETE:
Write one store goal, the target, the timeline, and the action plan.
This should come from a real conversation with the GM or trainer.

COACHING FOCUS:
- Goal awareness
- Store communication
- Role clarity
- Accountability

GOAL:
Make store goals visible and actionable rather than abstract.""",
        fields=[
            ("Goal", "text"),
            ("Target", "text"),
            ("Timeline", "text"),
            ("Action Plan", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Importance of Communication",
        template_type="worksheet",
        sort_order=9,
        instructions="""PURPOSE:
Strong communication keeps the team coordinated, efficient, and aware of what is happening in the store.

HOW TO COMPLETE:
Use this sheet to log communication examples and the impact they had.
Focus on specific phrases, callouts, or coaching moments that improved execution.

COACHING FOCUS:
- Vocal leadership
- Timing
- Clarity
- Team awareness

GOAL:
Get the MIT comfortable using communication as a tool during the shift.""",
        fields=[
            ("Example", "textarea"),
            ("Impact", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Wowing Works",
        template_type="worksheet",
        sort_order=10,
        instructions="""PURPOSE:
Teach the MIT how to recover customer concerns by apologizing, resolving the issue, and adding something extra when appropriate.

HOW TO COMPLETE:
Document a scenario, what the customer wanted, and how you would WOW them.
This should reflect store standards and realistic service recovery.

COACHING FOCUS:
- Empathy
- Resolution
- Speed
- Ownership

GOAL:
Prepare the MIT to handle upset customers in a way that builds loyalty.""",
        fields=[
            ("Scenario", "textarea"),
            ("Customer Need", "textarea"),
            ("Resolution / WOW", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Food Safety Scavenger Hunt",
        template_type="checklist",
        sort_order=11,
        instructions="""PURPOSE:
This page helps the MIT inspect the store against basic food safety expectations.

HOW TO COMPLETE:
Walk the store, check the item, and record whether it was found or completed.
Use the notes section if something is wrong or needs correction.

COACHING FOCUS:
- Observation
- Food safety awareness
- Standards discipline
- Corrective action

GOAL:
Build the habit of actively checking food safety instead of assuming it is fine.""",
        fields=[
            ("Item", "text"),
            ("Found / Completed?", "checkbox"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Grab & Weigh Best Practices",
        template_type="checklist",
        sort_order=12,
        instructions="""PURPOSE:
Reinforce proper portion habits and scale usage as part of Level 1 product execution.

HOW TO COMPLETE:
List a practice or item you worked on and mark whether it was completed.
Use this as a training support page for portion discipline.

COACHING FOCUS:
- Scale usage
- Portion accuracy
- Repetition
- Product consistency

GOAL:
Make portion awareness part of the MIT's daily routine.""",
        fields=[
            ("Practice", "text"),
            ("Completed?", "checkbox"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Quick TM Tasks for Lulls",
        template_type="checklist",
        sort_order=13,
        instructions="""PURPOSE:
Teach the MIT how to keep the team productive during slower moments instead of letting energy drop.

HOW TO COMPLETE:
Write a quick lull task and mark whether it was completed.
Think of realistic 60-second or short tasks that improve readiness.

COACHING FOCUS:
- Urgency
- Delegation
- Shift readiness
- Standards discipline

GOAL:
Build the habit of using downtime productively.""",
        fields=[
            ("Task", "text"),
            ("Completed?", "checkbox"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=1,
        title="Quick GM Tasks for Lulls",
        template_type="checklist",
        sort_order=14,
        instructions="""PURPOSE:
Help the MIT think like a shift leader by identifying manager-level tasks that can be handled during slower periods.

HOW TO COMPLETE:
Write a lull task and mark whether it was completed.
Focus on manager behaviors such as checking reports, labor, deposits, standards, or role play.

COACHING FOCUS:
- Manager awareness
- Prioritization
- Planning
- Ownership

GOAL:
Use downtime to improve shift control and preparation.""",
        fields=[
            ("Task", "text"),
            ("Completed?", "checkbox"),
        ],
    ) or created_any

    # --------------------------------------------------
    # LEVEL 2
    # --------------------------------------------------
    created_any = _create_template_if_missing(
        level_number=2,
        title="Motivation Audit Reflection",
        template_type="worksheet",
        sort_order=1,
        instructions="""PURPOSE:
Level 2 MITs should understand how motivation impacts shift culture and team results.

HOW TO COMPLETE:
Observe the team and record what drives energy, urgency, and attitude.
Identify what helped, what hurt, and what a manager should do next.

COACHING FOCUS:
- Team energy
- Positive reinforcement
- Shift leadership
- Culture awareness

GOAL:
Teach the MIT how to evaluate and influence motivation instead of just reacting to it.""",
        fields=[
            ("Observation", "textarea"),
            ("Positive Drivers", "textarea"),
            ("Opportunity", "textarea"),
            ("Action Plan", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=2,
        title="Interview Observation Guide",
        template_type="worksheet",
        sort_order=2,
        instructions="""PURPOSE:
Expose the MIT to structured interviewing and hiring decisions.

HOW TO COMPLETE:
Sit in on an interview and record what the candidate did well, what concerns came up, and what hiring recommendation you would make.

COACHING FOCUS:
- Listening
- Professional judgment
- Hiring standards
- Candidate evaluation

GOAL:
Build awareness of what good hiring looks like before the MIT leads interviews independently.""",
        fields=[
            ("Candidate Name", "text"),
            ("Strengths", "textarea"),
            ("Concerns", "textarea"),
            ("Hire Recommendation", "text"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=2,
        title="Advanced Load & Go Coaching Guide",
        template_type="worksheet",
        sort_order=3,
        instructions="""PURPOSE:
Level 2 MITs should move from basic Load & Go awareness into leading speed, communication, and execution.

HOW TO COMPLETE:
Use this sheet after a rush or coaching session.
Record what went well, what slowed the team down, and what should be coached next.

COACHING FOCUS:
- Hustle
- Communication
- Position control
- Throughput

GOAL:
Make the MIT able to coach Load & Go instead of only participating in it.""",
        fields=[
            ("Rush / Shift Date", "date"),
            ("What Worked", "textarea"),
            ("Biggest Delay", "textarea"),
            ("Coaching Focus", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=2,
        title="Food Order Accuracy Worksheet",
        template_type="worksheet",
        sort_order=4,
        instructions="""PURPOSE:
Teach the MIT how food orders impact waste, shortages, and store profitability.

HOW TO COMPLETE:
Review a food order with your coach.
Record what was ordered, what adjustments were needed, and what influenced the order.

COACHING FOCUS:
- Forecast awareness
- Inventory discipline
- Waste reduction
- Ordering logic

GOAL:
Build confidence in completing accurate food orders instead of guessing.""",
        fields=[
            ("Order Date", "date"),
            ("Adjustment Made", "textarea"),
            ("Reason", "textarea"),
            ("Lesson Learned", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=2,
        title="LSM Workbook Notes",
        template_type="worksheet",
        sort_order=5,
        instructions="""PURPOSE:
Level 2 MITs should understand how local store marketing supports order growth and community presence.

HOW TO COMPLETE:
Log the activity, the target audience, and the expected outcome.
Use this to reflect on actual store-level marketing execution.

COACHING FOCUS:
- Community awareness
- Brand presence
- Initiative
- Follow-through

GOAL:
Connect marketing activity to store traffic and customer awareness.""",
        fields=[
            ("Activity", "text"),
            ("Target Audience", "text"),
            ("Expected Result", "textarea"),
            ("Follow-Up", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=2,
        title="Pizza Making Consistency Tracker",
        template_type="log",
        sort_order=6,
        instructions="""PURPOSE:
Track product consistency as the MIT works toward stronger pizza quality and speed expectations.

HOW TO COMPLETE:
Log practice attempts, quality notes, and coaching feedback.
Use this sheet to reinforce repetition and measurable improvement.

COACHING FOCUS:
- Consistency
- Speed
- Quality control
- Repetition

GOAL:
Support improvement toward advanced product standards.""",
        fields=[
            ("Date", "date"),
            ("Product", "text"),
            ("Quality Result", "text"),
            ("Coaching Note", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=2,
        title="12D Training Execution Notes",
        template_type="worksheet",
        sort_order=7,
        instructions="""PURPOSE:
The MIT should begin learning how to train others with structure and follow-up.

HOW TO COMPLETE:
Use this sheet after a 12D training session.
Record what was taught, how the TM responded, and what follow-up is needed.

COACHING FOCUS:
- Teaching
- Patience
- Observation
- Reinforcement

GOAL:
Move the MIT from learning tasks to developing other people.""",
        fields=[
            ("Team Member", "text"),
            ("Topic Trained", "text"),
            ("What Went Well", "textarea"),
            ("Follow-Up Needed", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=2,
        title="Community Involvement Activity Review",
        template_type="worksheet",
        sort_order=8,
        instructions="""PURPOSE:
Level 2 MITs should begin understanding how the store connects with the community.

HOW TO COMPLETE:
Document the activity, who it reached, and what the store gained from it.
This can be tied to school, sports, fundraising, or other local involvement.

COACHING FOCUS:
- Community presence
- Planning
- Representation
- Follow-through

GOAL:
Show that community involvement is part of leadership, not just marketing.""",
        fields=[
            ("Activity", "text"),
            ("Audience", "text"),
            ("Store Benefit", "textarea"),
            ("Next Idea", "textarea"),
        ],
    ) or created_any

    # --------------------------------------------------
    # LEVEL 3
    # --------------------------------------------------
    created_any = _create_template_if_missing(
        level_number=3,
        title="Crew Meeting Planning Sheet",
        template_type="worksheet",
        sort_order=1,
        instructions="""PURPOSE:
Level 3 MITs should be able to organize and lead productive crew meetings.

HOW TO COMPLETE:
Outline the meeting topic, priorities, and desired outcome.
Use the notes section after the meeting to reflect on how it went.

COACHING FOCUS:
- Public communication
- Planning
- Team alignment
- Accountability

GOAL:
Prepare the MIT to lead structured meetings that actually move the store forward.""",
        fields=[
            ("Meeting Topic", "text"),
            ("Key Points", "textarea"),
            ("Desired Outcome", "textarea"),
            ("Post-Meeting Notes", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=3,
        title="Weekly Objectives Planning",
        template_type="worksheet",
        sort_order=2,
        instructions="""PURPOSE:
Level 3 MITs should be able to write and execute clear store objectives.

HOW TO COMPLETE:
Write the objective, how success will be measured, and what actions support it.
Review the result afterward.

COACHING FOCUS:
- Planning
- Measurement
- Follow-through
- Communication

GOAL:
Move the MIT into true goal-setting behavior.""",
        fields=[
            ("Objective", "text"),
            ("Success Measure", "text"),
            ("Action Steps", "textarea"),
            ("Result", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=3,
        title="Relief Management Week Reflection",
        template_type="worksheet",
        sort_order=3,
        instructions="""PURPOSE:
This guide helps the MIT reflect on a relief management week and what they learned from running the store at a higher level.

HOW TO COMPLETE:
Document the biggest win, hardest issue, decision made, and lesson learned.

COACHING FOCUS:
- Ownership
- Decision-making
- Self-awareness
- Readiness

GOAL:
Turn the relief week into a real development milestone, not just a checkbox.""",
        fields=[
            ("Biggest Win", "textarea"),
            ("Hardest Issue", "textarea"),
            ("Decision Made", "textarea"),
            ("Lesson Learned", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=3,
        title="Schedule Writing Review",
        template_type="worksheet",
        sort_order=4,
        instructions="""PURPOSE:
Level 3 MITs should understand how schedules affect labor, service, and team readiness.

HOW TO COMPLETE:
Review a written schedule and explain why shifts were staffed the way they were.
Note any changes you would make and why.

COACHING FOCUS:
- Labor awareness
- Staffing logic
- Forecasting
- Accountability

GOAL:
Teach the MIT to write schedules with intent, not guesswork.""",
        fields=[
            ("Week Of", "date"),
            ("What Worked", "textarea"),
            ("Adjustment Needed", "textarea"),
            ("Reason", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=3,
        title="P&L Review Notes",
        template_type="worksheet",
        sort_order=5,
        instructions="""PURPOSE:
Expose the MIT to profit and loss thinking at the store level.

HOW TO COMPLETE:
Review the store P&L with your coach or GM.
Write what stands out, what concerns you, and what action could improve results.

COACHING FOCUS:
- Profit awareness
- Business thinking
- Trend recognition
- Action planning

GOAL:
Help the MIT connect store execution to financial performance.""",
        fields=[
            ("What Stands Out", "textarea"),
            ("Biggest Concern", "textarea"),
            ("Improvement Opportunity", "textarea"),
            ("Action Step", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=3,
        title="Advanced Community Event Planning",
        template_type="worksheet",
        sort_order=6,
        instructions="""PURPOSE:
Level 3 MITs should be able to plan and execute more advanced community involvement events.

HOW TO COMPLETE:
Describe the event idea, target audience, resources needed, and expected store impact.

COACHING FOCUS:
- Planning
- Initiative
- Marketing awareness
- Community leadership

GOAL:
Prepare the MIT to take ownership of larger external store activities.""",
        fields=[
            ("Event Idea", "text"),
            ("Target Audience", "text"),
            ("Resources Needed", "textarea"),
            ("Expected Impact", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=3,
        title="New MIT Coaching Notes",
        template_type="worksheet",
        sort_order=7,
        instructions="""PURPOSE:
A Level 3 MIT should be able to assist in developing newer MITs.

HOW TO COMPLETE:
Record what was coached, how the MIT responded, and what follow-up is needed.

COACHING FOCUS:
- Teaching
- Observation
- Standards
- Development mindset

GOAL:
Transition the MIT from being developed to developing others.""",
        fields=[
            ("MIT Name", "text"),
            ("Topic Coached", "text"),
            ("Response", "textarea"),
            ("Follow-Up", "textarea"),
        ],
    ) or created_any

    created_any = _create_template_if_missing(
        level_number=3,
        title="Store Marketing Plan Notes",
        template_type="worksheet",
        sort_order=8,
        instructions="""PURPOSE:
This sheet helps the MIT understand the store marketing plan and how it supports order growth.

HOW TO COMPLETE:
Write down the current plan, what it is trying to achieve, and what improvement idea you would suggest.

COACHING FOCUS:
- Marketing awareness
- Strategy
- Initiative
- Store growth mindset

GOAL:
Teach the MIT to think proactively about business growth.""",
        fields=[
            ("Current Plan", "textarea"),
            ("Goal", "text"),
            ("Improvement Idea", "textarea"),
            ("Next Step", "textarea"),
        ],
    ) or created_any

    db.session.commit()

    if created_any:
        flash("Binder templates for Levels 1, 2, and 3 seeded.", "success")
    else:
        flash("Binder templates are already set up.", "info")

    return redirect("/mit-sts/dashboard")


@mit_sts_bp.route("/binder/templates")
@login_required
def binder_template_admin():
    if not can_manage_binder_templates():
        flash("You do not have access to that page.", "danger")
        return redirect("/")

    templates = MITBinderTemplate.query.order_by(
        MITBinderTemplate.level_number.asc(),
        MITBinderTemplate.sort_order.asc(),
        MITBinderTemplate.id.asc()
    ).all()

    grouped_templates = {}
    for template in templates:
        grouped_templates.setdefault(template.level_number, []).append(template)

    return render_template(
        "mit_sts/binder_template_admin.html",
        grouped_templates=grouped_templates,
        user=current_user,
    )


@mit_sts_bp.route("/binder/templates/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
def edit_binder_template(template_id):
    if not can_manage_binder_templates():
        flash("You do not have access to that page.", "danger")
        return redirect("/")

    template = MITBinderTemplate.query.get_or_404(template_id)

    if request.method == "POST":
        template.title = request.form.get("title", "").strip() or template.title
        template.template_type = request.form.get("template_type", "").strip() or template.template_type
        template.instructions = request.form.get("instructions", "").strip()
        template.sort_order = int(request.form.get("sort_order", template.sort_order) or template.sort_order)
        template.is_active = request.form.get("is_active") == "on"

        db.session.commit()
        flash("Binder template updated.", "success")
        return redirect(url_for("mit_sts.binder_template_admin"))

    fields = MITBinderField.query.filter_by(template_id=template.id).order_by(
        MITBinderField.sort_order.asc(),
        MITBinderField.id.asc()
    ).all()

    return render_template(
        "mit_sts/edit_binder_template.html",
        template=template,
        fields=fields,
        user=current_user,
    )


@mit_sts_bp.route("/binder/templates/<int:template_id>/fields/add", methods=["POST"])
@login_required
def add_binder_field(template_id):
    if not can_manage_binder_templates():
        flash("You do not have access to that page.", "danger")
        return redirect("/")

    template = MITBinderTemplate.query.get_or_404(template_id)

    label = request.form.get("label", "").strip()
    field_type = request.form.get("field_type", "text").strip()
    sort_order_raw = request.form.get("sort_order", "").strip()

    if not label:
        flash("Field label is required.", "danger")
        return redirect(url_for("mit_sts.edit_binder_template", template_id=template.id))

    if field_type not in ["text", "textarea", "number", "checkbox", "date"]:
        flash("Invalid field type.", "danger")
        return redirect(url_for("mit_sts.edit_binder_template", template_id=template.id))

    if sort_order_raw:
        sort_order = int(sort_order_raw)
    else:
        max_sort = db.session.query(func.max(MITBinderField.sort_order)).filter_by(template_id=template.id).scalar()
        sort_order = (max_sort or 0) + 1

    db.session.add(
        MITBinderField(
            template_id=template.id,
            label=label,
            field_type=field_type,
            sort_order=sort_order
        )
    )
    db.session.commit()

    flash("Field added.", "success")
    return redirect(url_for("mit_sts.edit_binder_template", template_id=template.id))


@mit_sts_bp.route("/binder/fields/<int:field_id>/update", methods=["POST"])
@login_required
def update_binder_field(field_id):
    if not can_manage_binder_templates():
        flash("You do not have access to that page.", "danger")
        return redirect("/")

    field = MITBinderField.query.get_or_404(field_id)

    label = request.form.get("label", "").strip()
    field_type = request.form.get("field_type", "text").strip()
    sort_order = int(request.form.get("sort_order", field.sort_order) or field.sort_order)

    if not label:
        flash("Field label is required.", "danger")
        return redirect(url_for("mit_sts.edit_binder_template", template_id=field.template_id))

    if field_type not in ["text", "textarea", "number", "checkbox", "date"]:
        flash("Invalid field type.", "danger")
        return redirect(url_for("mit_sts.edit_binder_template", template_id=field.template_id))

    field.label = label
    field.field_type = field_type
    field.sort_order = sort_order

    db.session.commit()

    flash("Field updated.", "success")
    return redirect(url_for("mit_sts.edit_binder_template", template_id=field.template_id))


@mit_sts_bp.route("/binder/fields/<int:field_id>/delete", methods=["POST"])
@login_required
def delete_binder_field(field_id):
    if not can_manage_binder_templates():
        flash("You do not have access to that page.", "danger")
        return redirect("/")

    field = MITBinderField.query.get_or_404(field_id)
    template_id = field.template_id

    has_entries = MITBinderEntry.query.filter_by(field_id=field.id).first() is not None
    if has_entries:
        flash("Cannot delete a field that already has saved data.", "warning")
        return redirect(url_for("mit_sts.edit_binder_template", template_id=template_id))

    db.session.delete(field)
    db.session.commit()

    flash("Field deleted.", "success")
    return redirect(url_for("mit_sts.edit_binder_template", template_id=template_id))