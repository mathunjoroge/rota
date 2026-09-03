from flask import flash, redirect, url_for
from datetime import timedelta, date
import calendar
from models.models import db, Leave, Rota, Team

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

def save_leave_logic(member_id, form):
    member = Team.query.get_or_404(member_id)
    try:
        start_date = date.fromisoformat(form['start_date'])
        end_date = date.fromisoformat(form['end_date'])
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", 'danger')
        return redirect(url_for('members.manage_members'))

    # Check if dates are valid
    if start_date > end_date:
        flash("End date must be after start date.", 'danger')
        return redirect(url_for('members.manage_members'))

    # Check for overlapping leaves
    overlapping_leaves = Leave.query.filter(
        Leave.member_id == member_id,
        Leave.start_date <= end_date,
        Leave.end_date >= start_date
    ).first()
    if overlapping_leaves:
        flash(f"Leave conflicts with an existing leave from {overlapping_leaves.start_date} to {overlapping_leaves.end_date}.", 'danger')
        return redirect(url_for('members.manage_members'))

    # If all checks pass, save the leave
    new_leave = Leave(member_id=member_id, start_date=start_date, end_date=end_date)
    db.session.add(new_leave)
    db.session.commit()

    # Automatically remove member from any existing rotas during this leave period
    updated_rotas = remove_member_from_overlapping_rotas(member.name, start_date, end_date)
    if updated_rotas > 0:
        flash(f"Leave added successfully. Removed {member.name} from {updated_rotas} existing rota schedule(s).", 'success')
    else:
        flash("Leave added successfully.", 'success')
    return redirect(url_for('leave.on_leave'))

def get_leaves_on_date(today):
    """Retrieve all leaves ending on or after the specified date."""
    leaves = Leave.query.filter(Leave.end_date >= today).all()
    return leaves

def delete_leave_logic(leave_id):
    """Delete a leave entry based on its ID."""
    leave = Leave.query.get_or_404(leave_id)
    db.session.delete(leave)
    db.session.commit()
    flash("Leave deleted successfully.", 'success')
    return redirect(url_for('leave.on_leave'))

def edit_leave_logic(leave_id, form):
    """Edit an existing leave entry."""
    leave = Leave.query.get_or_404(leave_id)
    try:
        start_date = date.fromisoformat(form['start_date'])
        end_date = date.fromisoformat(form['end_date'])
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", 'danger')
        return redirect(url_for('leave.on_leave'))

    if start_date > end_date:
        flash("End date must be after start date.", 'danger')
        return redirect(url_for('leave.on_leave'))

    leave.start_date = start_date
    leave.end_date = end_date
    db.session.commit()

    remove_member_from_overlapping_rotas(leave.member.name, start_date, end_date)
    flash("Leave updated successfully.", 'success')
    return redirect(url_for('leave.on_leave'))