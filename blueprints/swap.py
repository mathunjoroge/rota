from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models.models import db, ShiftSwapRequest, Team, Rota, Notification, User
from blueprints.audit import log_audit
from datetime import datetime

swap_bp = Blueprint('swap', __name__)


def _notify_user(user_id, message, link=None):
    """Create an in-app notification for a user."""
    try:
        notif = Notification(user_id=user_id, message=message, link=link)
        db.session.add(notif)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _find_user_for_member(member_id):
    """Find a User record linked to the same department as a Team member."""
    member = Team.query.get(member_id)
    if not member:
        return None
    # Try to find a user whose username matches member name (case-insensitive)
    user = User.query.filter(User.username.ilike(f'%{member.name.split()[0]}%')).first()
    return user


@swap_bp.route('/swaps')
@login_required
def list_swaps():
    """List all swap requests relevant to the current user."""
    # Find Team record linked to current user's department
    dept_id = getattr(current_user, 'department_id', None)

    # All swaps in this department
    all_swaps = ShiftSwapRequest.query.join(
        Team, ShiftSwapRequest.requester_id == Team.id
    ).filter(
        Team.department_id == dept_id
    ).order_by(ShiftSwapRequest.created_at.desc()).all() if dept_id else \
        ShiftSwapRequest.query.order_by(ShiftSwapRequest.created_at.desc()).all()

    # Pending swaps where current user is the proposed member (needs their response)
    # Match by department name prefix heuristic
    members_in_dept = Team.query.filter_by(department_id=dept_id).all() if dept_id else []
    member_ids = [m.id for m in members_in_dept]

    incoming = [s for s in all_swaps if s.proposed_member_id in member_ids and s.status == 'pending']
    my_requests = [s for s in all_swaps if s.requester_id in member_ids]
    user_level = getattr(current_user, 'level', 0)
    pending_admin = [s for s in all_swaps if s.status == 'peer_approved'] if user_level >= 1 else []

    return render_template('swap.html',
                           all_swaps=all_swaps,
                           incoming=incoming,
                           my_requests=my_requests,
                           pending_admin=pending_admin,
                           members=members_in_dept)


@swap_bp.route('/swaps/request', methods=['POST'])
@login_required
def request_swap():
    """Submit a new shift swap request."""
    requester_id = request.form.get('requester_id', type=int)
    proposed_member_id = request.form.get('proposed_member_id', type=int)
    rota_id = request.form.get('rota_id', type=int)
    week_range = request.form.get('week_range', '')
    requester_shift = request.form.get('requester_shift', '')
    proposed_shift = request.form.get('proposed_shift', '')
    reason = request.form.get('reason', '')

    if not all([requester_id, proposed_member_id, rota_id, week_range, requester_shift, proposed_shift]):
        flash('All fields are required to submit a swap request.', 'danger')
        return redirect(url_for('swap.list_swaps'))

    if requester_id == proposed_member_id:
        flash('You cannot swap shifts with yourself.', 'danger')
        return redirect(url_for('swap.list_swaps'))

    swap = ShiftSwapRequest(
        requester_id=requester_id,
        proposed_member_id=proposed_member_id,
        rota_id=rota_id,
        week_range=week_range,
        requester_shift=requester_shift,
        proposed_shift=proposed_shift,
        reason=reason,
        status='pending'
    )
    db.session.add(swap)
    db.session.commit()

    log_audit('create', 'ShiftSwapRequest', swap.id,
              description=f"{swap.requester.name} requested swap with {swap.proposed_member.name} for week {week_range}")

    # Notify admin users in dept
    user_dept = getattr(current_user, 'department_id', None)
    admins = User.query.filter(User.department_id == user_dept, User.level >= 1).all() if user_dept else []
    for admin in admins:
        _notify_user(admin.id,
                     f"New swap request: {swap.requester.name} ↔ {swap.proposed_member.name} ({week_range})",
                     link=url_for('swap.list_swaps'))

    flash(f'Swap request submitted for week {week_range}. Awaiting peer confirmation.', 'success')
    return redirect(url_for('swap.list_swaps'))


@swap_bp.route('/swaps/<int:swap_id>/peer_respond', methods=['POST'])
@login_required
def peer_respond(swap_id):
    """Proposed member accepts or rejects the swap."""
    swap = ShiftSwapRequest.query.get_or_404(swap_id)
    response = request.form.get('response')  # 'accept' or 'reject'

    if response == 'accept':
        swap.status = 'peer_approved'
        swap.peer_response = 'accepted'
        msg = f"{swap.proposed_member.name} accepted the swap request from {swap.requester.name} ({swap.week_range}). Awaiting admin approval."
        flash('You accepted the swap. Admin approval pending.', 'success')
    else:
        swap.status = 'rejected'
        swap.peer_response = 'rejected'
        swap.resolved_at = datetime.utcnow()
        msg = f"{swap.proposed_member.name} declined the swap request from {swap.requester.name} ({swap.week_range})."
        flash('You declined the swap request.', 'info')

    db.session.commit()
    log_audit('update', 'ShiftSwapRequest', swap.id, description=msg)

    # Notify dept admins and requester
    user_dept = getattr(current_user, 'department_id', None)
    admins = User.query.filter(User.department_id == user_dept, User.level >= 1).all() if user_dept else []
    for admin in admins:
        _notify_user(admin.id, msg, link=url_for('swap.list_swaps'))
    return redirect(url_for('swap.list_swaps'))


@swap_bp.route('/swaps/<int:swap_id>/admin_approve', methods=['POST'])
@login_required
def admin_approve(swap_id):
    """Department leader gives final approval or rejection."""
    if getattr(current_user, 'level', 0) < 1:
        flash('Not authorised.', 'danger')
        return redirect(url_for('swap.list_swaps'))

    swap = ShiftSwapRequest.query.get_or_404(swap_id)
    decision = request.form.get('decision')  # 'approve' or 'reject'

    if decision == 'approve':
        # Swap the shift values in the Rota record
        rota_rows = Rota.query.filter_by(rota_id=swap.rota_id).all()
        shift_map = {'morning': 'shift_8_5', 'evening': 'shift_5_8', 'night': 'shift_8_8'}
        for row in rota_rows:
            req_field = shift_map.get(swap.requester_shift)
            prop_field = shift_map.get(swap.proposed_shift)
            if req_field and prop_field:
                req_val = getattr(row, req_field, '')
                prop_val = getattr(row, prop_field, '')
                if swap.requester.name in req_val and swap.proposed_member.name in prop_val:
                    setattr(row, req_field, req_val.replace(swap.requester.name, swap.proposed_member.name))
                    setattr(row, prop_field, prop_val.replace(swap.proposed_member.name, swap.requester.name))

        swap.status = 'approved'
        swap.resolved_at = datetime.utcnow()
        db.session.commit()
        msg = f"Shift swap APPROVED: {swap.requester.name} ↔ {swap.proposed_member.name} ({swap.week_range})"
        flash('Swap approved and rota updated.', 'success')
    else:
        swap.status = 'rejected'
        swap.resolved_at = datetime.utcnow()
        db.session.commit()
        msg = f"Shift swap REJECTED by admin: {swap.requester.name} ↔ {swap.proposed_member.name} ({swap.week_range})"
        flash('Swap request rejected.', 'info')

    log_audit('update', 'ShiftSwapRequest', swap.id, description=msg)
    return redirect(url_for('swap.list_swaps'))
