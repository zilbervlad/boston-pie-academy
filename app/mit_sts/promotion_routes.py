from .routes_shared import *

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
