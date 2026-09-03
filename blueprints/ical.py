from flask import Blueprint, Response, abort, url_for
from flask_login import login_required, current_user
from models.models import db, User, RotaAssignment, Team
from datetime import datetime, timedelta
import uuid

ical_bp = Blueprint('ical', __name__)

try:
    from icalendar import Calendar, Event
    ICAL_AVAILABLE = True
except ImportError:
    ICAL_AVAILABLE = False

SHIFT_LABELS = {
    'morning':   ('Morning Shift',   8,  0,  17, 0),
    'evening':   ('Evening Shift',   17, 0,  20, 0),
    'night':     ('Night Shift',     20, 0,  8,  0),  # next day
    'night_off': ('Night Off',       8,  0,  8,  0),
    'on_leave':  ('On Leave',        8,  0,  17, 0),
}


from flask import Blueprint, Response, abort, url_for, render_template, redirect, flash

@ical_bp.route('/ical/my')
@login_required
def my_ical_link():
    """Show the current user's private iCal subscribe URL."""
    if not hasattr(current_user, 'get_or_create_ical_token'):
        user = User.query.first()
        token = user.get_or_create_ical_token() if user else 'demo_token'
    else:
        token = current_user.get_or_create_ical_token()
    feed_url = url_for('ical.ical_feed', token=token, _external=True)
    return render_template('ical_my.html', feed_url=feed_url)


@ical_bp.route('/ical/<token>')
def ical_feed(token):
    """Return a .ics calendar file for the staff member matching this token."""
    if not ICAL_AVAILABLE:
        return "iCalendar library not installed. Run: pip install icalendar", 503

    user = User.query.filter_by(ical_token=token).first()
    if not user:
        abort(404)

    # Find Team member matching this user (by name prefix or department)
    members = Team.query.filter_by(department_id=user.department_id).all()
    # Match by first name of username
    first_name = user.username.split('_')[0].lower()
    member = next((m for m in members if first_name in m.name.lower()), None)

    cal = Calendar()
    cal.add('prodid', '-//Magic Rota//Hospital Shift Calendar//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', f'Shifts – {user.username.title()}')
    cal.add('x-wr-timezone', 'Africa/Nairobi')

    if member:
        assignments = RotaAssignment.query.filter_by(member_id=member.id).order_by(RotaAssignment.date).all()
    else:
        assignments = []

    for a in assignments:
        label, sh, sm, eh, em = SHIFT_LABELS.get(a.shift_name, ('Shift', 8, 0, 17, 0))
        start_dt = datetime(a.date.year, a.date.month, a.date.day, sh, sm)
        if a.shift_name == 'night':
            next_day = a.date + timedelta(days=1)
            end_dt = datetime(next_day.year, next_day.month, next_day.day, eh, em)
        else:
            end_dt = datetime(a.date.year, a.date.month, a.date.day, eh, em)

        event = Event()
        event.add('summary', f'{label} — {member.name if member else user.username}')
        event.add('dtstart', start_dt)
        event.add('dtend', end_dt)
        event.add('description', f'Shift type: {a.shift_name}\nDepartment: {user.department.name if user.department else ""}')
        event.add('uid', f'{a.id}-{token[:8]}@magicrota')
        cal.add_component(event)

    return Response(
        cal.to_ical(),
        mimetype='text/calendar',
        headers={'Content-Disposition': f'attachment; filename="shifts_{user.username}.ics"'}
    )


@ical_bp.route('/ical/reset', methods=['POST'])
@login_required
def reset_ical_token():
    """Invalidate and regenerate the iCal token."""
    current_user.ical_token = uuid.uuid4().hex
    db.session.commit()
    flash('Your private calendar feed token has been reset.', 'success')
    return redirect(url_for('ical.my_ical_link'))
