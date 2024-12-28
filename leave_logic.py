from flask import flash, redirect, url_for
from datetime import date
from models.models import db, Leave, Rota, Team

def save_leave_logic(member_id, form):
    member = Team.query.get_or_404(member_id)
    try:
        start_date = date.fromisoformat(form['start_date'])
        end_date = date.fromisoformat(form['end_date'])
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", 'danger')
        return redirect(url_for('manage_members'))

    # Check if dates are valid
    if start_date > end_date:
        flash("End date must be after start date.", 'danger')
        return redirect(url_for('manage_members'))
    if start_date < date.today():
        flash("Leave cannot start in the past.", 'danger')
        return redirect(url_for('manage_members'))

    # Check if rota exists for these dates
    existing_rotas = Rota.query.filter(Rota.week_range.contains(start_date.strftime('%d/%m/%Y'))).all()
    if existing_rotas:
        for rota in existing_rotas:
            if member.name not in rota.shift_8_5:
                flash("Leave can only be applied by members in the morning shift.", 'danger')
                return redirect(url_for('manage_members'))

    # Check for overlapping leaves
    overlapping_leaves = Leave.query.filter(
        Leave.member_id == member_id,
        Leave.start_date <= end_date,
        Leave.end_date >= start_date
    ).first()
    if overlapping_leaves:
        flash(f"Leave conflicts with an existing leave from {overlapping_leaves.start_date} to {overlapping_leaves.end_date}.", 'danger')
        return redirect(url_for('manage_members'))

    # If all checks pass, save the leave
    new_leave = Leave(member_id=member_id, start_date=start_date, end_date=end_date)
    db.session.add(new_leave)
    db.session.commit()
    flash("Leave added successfully.", 'success')
    return redirect(url_for('manage_members'))

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
    return redirect(url_for('on_leave'))

def edit_leave_logic(leave_id, form):
    """Edit an existing leave entry."""
    leave = Leave.query.get_or_404(leave_id)
    try:
        start_date = date.fromisoformat(form['start_date'])
        end_date = date.fromisoformat(form['end_date'])
    except ValueError:
        flash("Invalid date format. Please use YYYY-MM-DD.", 'danger')
        return redirect(url_for('on_leave'))

    if start_date > end_date:
        flash("End date must be after start date.", 'danger')
        return redirect(url_for('on_leave'))

    leave.start_date = start_date
    leave.end_date = end_date
    db.session.commit()
    flash("Leave updated successfully.", 'success')
    return redirect(url_for('on_leave'))
def days_taken(self):
    """Calculate the number of days taken."""
    if self.start_date and self.end_date:
        days_taken = (self.end_date - self.start_date).days + 1
        print(f"[DEBUG] Days taken: {days_taken} (Start: {self.start_date}, End: {self.end_date})")
        return days_taken
    return 0

def days_remaining(self):
    """Calculate the number of days remaining from today."""
    if self.end_date:
        remaining_days = (self.end_date - date.today()).days
        print(f"[DEBUG] Days remaining: {remaining_days} (Today: {date.today()}, End: {self.end_date})")
        return max(remaining_days, 0)  # Ensure it doesn't return negative values
    return 0