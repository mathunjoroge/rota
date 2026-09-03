from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models.models import db, Team, Department
from blueprints.audit import log_audit

float_bp = Blueprint('float_pool', __name__)

@float_bp.route('/float_pool', methods=['GET', 'POST'])
@login_required
def float_pool():
    """View float pool members and toggle float eligibility."""
    departments = Department.query.all()
    if request.method == 'POST':
        member_id = request.form.get('member_id', type=int)
        action = request.form.get('action')  # 'enable' or 'disable'
        member = Team.query.get(member_id)

        if member:
            member.can_float = (action == 'enable')
            db.session.commit()
            status_str = "added to" if member.can_float else "removed from"
            log_audit('update', 'Team', member.id, description=f"{member.name} {status_str} Cross-Department Float Pool")
            flash(f"{member.name} {status_str} Float Pool.", "success")
        return redirect(url_for('float_pool.float_pool'))

    floaters = Team.query.filter_by(can_float=True).all()
    all_members = Team.query.all()

    return render_template('float_pool.html', floaters=floaters, all_members=all_members, departments=departments)
