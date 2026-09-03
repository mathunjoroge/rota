from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models.models import db, StaffPreference, Team
from datetime import datetime, timedelta
import json

preferences_bp = Blueprint('preferences', __name__)

def get_next_monday(d=None):
    if d is None:
        d = datetime.now().date()
    days_ahead = 0 - d.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


@preferences_bp.route('/preferences', methods=['GET', 'POST'])
@login_required
def preferences():
    """Allow staff to submit preferred off days for upcoming weeks."""
    next_mon = get_next_monday()
    dept_id = getattr(current_user, 'department_id', None)
    members = Team.query.filter_by(department_id=dept_id).all() if dept_id else Team.query.all()

    if request.method == 'POST':
        member_id = request.form.get('member_id', type=int)
        week_start_str = request.form.get('week_start')
        off_days = request.form.getlist('off_days')
        notes = request.form.get('notes', '')

        if not member_id or not week_start_str:
            flash('Member and week start date are required.', 'danger')
            return redirect(url_for('preferences.preferences'))

        week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()

        # Update or create preference record
        existing = StaffPreference.query.filter_by(member_id=member_id, week_start=week_start).first()
        if existing:
            existing.preferred_off_days = json.dumps(off_days)
            existing.notes = notes
        else:
            pref = StaffPreference(
                member_id=member_id,
                week_start=week_start,
                preferred_off_days=json.dumps(off_days),
                notes=notes
            )
            db.session.add(pref)

        db.session.commit()
        flash('Staff preferences submitted successfully!', 'success')
        return redirect(url_for('preferences.preferences'))

    # Query submitted preferences
    pref_records = StaffPreference.query.order_by(StaffPreference.week_start.desc()).all()
    parsed_prefs = []
    for p in pref_records:
        parsed_prefs.append({
            'id': p.id,
            'member_name': p.member.name if p.member else 'Unknown',
            'week_start': p.week_start.strftime('%d-%m-%Y'),
            'off_days': json.loads(p.preferred_off_days) if p.preferred_off_days else [],
            'notes': p.notes,
            'submitted_at': p.submitted_at.strftime('%d-%b %H:%M')
        })

    # Generate dates for next 7 days from next Monday
    upcoming_days = [next_mon + timedelta(days=i) for i in range(7)]

    return render_template('preferences.html',
                           members=members,
                           next_mon=next_mon,
                           upcoming_days=upcoming_days,
                           preferences=parsed_prefs)
