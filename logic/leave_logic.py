from flask import flash, redirect, url_for
from datetime import timedelta, date, datetime
import calendar
from models.models import db, Leave, LeaveRequest, Rota, Team, Notification, User
from blueprints.audit import log_audit
from blueprints.notifications import notify_leave_approved, notify_leave_rejected

def safe_flash(message, category='info'):
    try:
        flash(message, category)
    except RuntimeError:
        pass

def weekdays_between(start_date, end_date):
    """Calculate total weekdays (Mon-Fri) between two dates inclusive."""
    weekdays = 0
    for single_date in (start_date + timedelta(n) for n in range((end_date - start_date).days + 1)):
        if single_date.weekday() < 5:
            weekdays += 1
    return weekdays

def remove_member_from_overlapping_rotas(member_name, start_date, end_date):
    """Ensure that if a member is on leave, they are removed from any existing rotas during that period."""
    rotas = Rota.query.all()
    updated_count = 0
    for rota in rotas:
        rota_start = rota.date
        rota_end = rota_start + timedelta(days=6)
        if rota_start <= end_date and rota_end >= start_date:
            modified = False
            # Remove from Morning shift (comma-separated list)
            if rota.shift_8_5 and member_name in rota.shift_8_5:
                members_list = [m.strip() for m in rota.shift_8_5.split(',') if m.strip() != member_name]
                rota.shift_8_5 = ', '.join(members_list)
                modified = True
            # Remove from Evening shift
            if rota.shift_5_8 == member_name:
                rota.shift_5_8 = ''
                modified = True
            # Remove from Night shift
            if rota.shift_8_8 == member_name:
                rota.shift_8_8 = ''
                modified = True
            # Remove from Night Off
            if rota.night_off == member_name:
                rota.night_off = ''
                modified = True
            if modified:
                updated_count += 1
    if updated_count > 0:
        db.session.commit()
    return updated_count

def apply_leave_logic(form, current_user=None):
    """Process staff leave application request."""
    try:
        member_id = int(form['member_id'])
        start_date = date.fromisoformat(form['start_date'])
        end_date = date.fromisoformat(form['end_date'])
        leave_type = form.get('leave_type', 'Annual Leave')
        reason = form.get('reason', '').strip()
    except (KeyError, ValueError):
        safe_flash("Invalid input fields or date format. Use YYYY-MM-DD.", 'danger')
        return redirect(url_for('leave.on_leave'))

    member = Team.query.get_or_404(member_id)

    if start_date > end_date:
        safe_flash("End date cannot be prior to start date.", 'danger')
        return redirect(url_for('leave.on_leave'))

    # Check for overlapping active leaves or pending requests
    existing_leave = Leave.query.filter(
        Leave.member_id == member_id,
        Leave.start_date <= end_date,
        Leave.end_date >= start_date
    ).first()
    if existing_leave:
        safe_flash(f"{member.name} already has approved leave from {existing_leave.start_date} to {existing_leave.end_date}.", 'warning')
        return redirect(url_for('leave.on_leave'))

    existing_request = LeaveRequest.query.filter(
        LeaveRequest.member_id == member_id,
        LeaveRequest.status == 'pending',
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date
    ).first()
    if existing_request:
        safe_flash(f"{member.name} already has a pending leave application for overlapping dates.", 'warning')
        return redirect(url_for('leave.on_leave'))

    leave_req = LeaveRequest(
        member_id=member_id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        status='pending'
    )
    db.session.add(leave_req)
    db.session.commit()

    log_audit(
        action='create',
        entity_type='LeaveRequest',
        entity_id=leave_req.id,
        description=f"Submitted {leave_type} request for {member.name} ({start_date} to {end_date})"
    )

    days_num = weekdays_between(start_date, end_date)
    safe_flash(f"Leave application submitted for {member.name} ({days_num} working days). Awaiting manager review.", 'success')
    return redirect(url_for('leave.on_leave'))

def approve_leave_request_logic(req_id, current_user):
    """Approve a pending leave request, create Leave record, clear shifts, and log audit."""
    req = LeaveRequest.query.get_or_404(req_id)
    if req.status != 'pending':
        safe_flash(f"Leave request #{req.id} has already been processed.", 'info')
        return redirect(url_for('leave.on_leave'))

    req.status = 'approved'
    req.reviewed_by_id = getattr(current_user, 'id', None)
    req.resolved_at = datetime.utcnow()

    # Create active Leave record
    new_leave = Leave(
        member_id=req.member_id,
        start_date=req.start_date,
        end_date=req.end_date,
        leave_type=req.leave_type,
        reason=req.reason
    )
    db.session.add(new_leave)
    db.session.commit()

    # Remove staff from active rotas
    cleared_rotas = remove_member_from_overlapping_rotas(req.member.name, req.start_date, req.end_date)

    log_audit(
        action='update',
        entity_type='LeaveRequest',
        entity_id=req.id,
        description=f"Approved {req.leave_type} for {req.member.name} ({req.start_date} to {req.end_date}). Cleared {cleared_rotas} active rotas."
    )

    # In-app notification if user account matches email/member
    if req.member.email:
        user = User.query.filter_by(email=req.member.email).first()
        if user:
            notif = Notification(
                user_id=user.id,
                message=f"🎉 Your leave application ({req.leave_type}: {req.start_date} to {req.end_date}) was APPROVED!",
                link="/on_leave"
            )
            db.session.add(notif)
            db.session.commit()

    # Send email notification to staff member
    try:
        notify_leave_approved(req)
    except Exception as e:
        import logging
        logging.error(f"[leave_approve] Email notification failed: {e}")

    safe_flash(f"Approved leave for {req.member.name}. {cleared_rotas} active schedule(s) updated.", 'success')
    return redirect(url_for('leave.on_leave'))

def reject_leave_request_logic(req_id, current_user, form):
    """Reject a pending leave request with optional manager notes."""
    req = LeaveRequest.query.get_or_404(req_id)
    if req.status != 'pending':
        safe_flash(f"Leave request #{req.id} has already been processed.", 'info')
        return redirect(url_for('leave.on_leave'))

    req.status = 'rejected'
    req.review_notes = form.get('review_notes', '').strip()
    req.reviewed_by_id = getattr(current_user, 'id', None)
    req.resolved_at = datetime.utcnow()
    db.session.commit()

    log_audit(
        action='update',
        entity_type='LeaveRequest',
        entity_id=req.id,
        description=f"Rejected leave request for {req.member.name}. Reason: {req.review_notes}"
    )

    if req.member.email:
        user = User.query.filter_by(email=req.member.email).first()
        if user:
            notif = Notification(
                user_id=user.id,
                message=f"⚠️ Your leave application ({req.leave_type}: {req.start_date} to {req.end_date}) was rejected. Notes: {req.review_notes or 'N/A'}",
                link="/on_leave"
            )
            db.session.add(notif)
            db.session.commit()

    # Send email notification to staff member
    try:
        notify_leave_rejected(req)
    except Exception as e:
        import logging
        logging.error(f"[leave_reject] Email notification failed: {e}")

    safe_flash(f"Leave request for {req.member.name} rejected.", 'warning')
    return redirect(url_for('leave.on_leave'))

def get_leave_balances(dept_id=None):
    """Compute annual leave entitlement, days taken, and days remaining per team member."""
    if dept_id:
        members = Team.query.filter_by(department_id=dept_id).order_by(Team.name).all()
    else:
        members = Team.query.order_by(Team.name).all()

    balances = []
    current_year = date.today().year

    for m in members:
        # Sum weekdays taken for approved leaves in current year
        leaves = Leave.query.filter_by(member_id=m.id).all()
        used = 0
        for l in leaves:
            if l.start_date and l.start_date.year == current_year:
                used += weekdays_between(l.start_date, l.end_date)
        
        allowance = m.annual_leave_allowance or 21
        remaining = max(allowance - used, 0)
        pct = min(round((used / allowance) * 100), 100) if allowance > 0 else 0

        balances.append({
            'member': m,
            'allowance': allowance,
            'used': used,
            'remaining': remaining,
            'pct_used': pct
        })
    return balances

def save_leave_logic(member_id, form):
    member = Team.query.get_or_404(member_id)
    try:
        start_date = date.fromisoformat(form['start_date'])
        end_date = date.fromisoformat(form['end_date'])
        leave_type = form.get('leave_type', 'Annual Leave')
        reason = form.get('reason', '').strip()
    except (ValueError, KeyError):
        safe_flash("Invalid date format. Please use YYYY-MM-DD.", 'danger')
        return redirect(url_for('members.manage_members'))

    # Check if dates are valid
    if start_date > end_date:
        safe_flash("End date must be after start date.", 'danger')
        return redirect(url_for('members.manage_members'))

    # Check for overlapping leaves
    overlapping_leaves = Leave.query.filter(
        Leave.member_id == member_id,
        Leave.start_date <= end_date,
        Leave.end_date >= start_date
    ).first()
    if overlapping_leaves:
        safe_flash(f"Leave conflicts with an existing leave from {overlapping_leaves.start_date} to {overlapping_leaves.end_date}.", 'danger')
        return redirect(url_for('members.manage_members'))

    # If all checks pass, save the leave directly
    new_leave = Leave(member_id=member_id, start_date=start_date, end_date=end_date, leave_type=leave_type, reason=reason)
    db.session.add(new_leave)
    db.session.commit()

    log_audit(
        action='create',
        entity_type='Leave',
        entity_id=new_leave.id,
        description=f"Direct leave record created for {member.name} ({start_date} to {end_date})"
    )

    # Automatically remove member from any existing rotas during this leave period
    updated_rotas = remove_member_from_overlapping_rotas(member.name, start_date, end_date)
    if updated_rotas > 0:
        safe_flash(f"Leave added successfully. Removed {member.name} from {updated_rotas} existing rota schedule(s).", 'success')
    else:
        safe_flash("Leave added successfully.", 'success')
    return redirect(url_for('leave.on_leave'))

def get_leaves_on_date(today):
    """Retrieve all leaves ending on or after the specified date."""
    leaves = Leave.query.filter(Leave.end_date >= today).all()
    return leaves

def delete_leave_logic(leave_id):
    """Delete a leave entry based on its ID."""
    leave = Leave.query.get_or_404(leave_id)
    log_audit(
        action='delete',
        entity_type='Leave',
        entity_id=leave.id,
        description=f"Deleted leave for {leave.member.name} ({leave.start_date} to {leave.end_date})"
    )
    db.session.delete(leave)
    db.session.commit()
    safe_flash("Leave deleted successfully.", 'success')
    return redirect(url_for('leave.on_leave'))

def edit_leave_logic(leave_id, form):
    """Edit an existing leave entry."""
    leave = Leave.query.get_or_404(leave_id)
    try:
        start_date = date.fromisoformat(form['start_date'])
        end_date = date.fromisoformat(form['end_date'])
    except (ValueError, KeyError):
        safe_flash("Invalid date format. Please use YYYY-MM-DD.", 'danger')
        return redirect(url_for('leave.on_leave'))

    if start_date > end_date:
        safe_flash("End date must be after start date.", 'danger')
        return redirect(url_for('leave.on_leave'))

    leave.start_date = start_date
    leave.end_date = end_date
    if 'leave_type' in form:
        leave.leave_type = form['leave_type']
    if 'reason' in form:
        leave.reason = form['reason']
    db.session.commit()

    remove_member_from_overlapping_rotas(leave.member.name, start_date, end_date)
    log_audit(
        action='update',
        entity_type='Leave',
        entity_id=leave.id,
        description=f"Updated leave for {leave.member.name} ({start_date} to {end_date})"
    )
    safe_flash("Leave updated successfully.", 'success')
    return redirect(url_for('leave.on_leave'))