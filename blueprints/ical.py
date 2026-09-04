from flask import Blueprint, Response, abort, url_for
from flask_login import login_required, current_user
from models.models import db, User, RotaAssignment, Team, Rota
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

    # Find matching Team member
    all_members = Team.query.all()
    u_name = user.username.lower()
    member = next((m for m in all_members if u_name in m.name.lower() or any(part in m.name.lower() for part in u_name.split('_'))), None)
    member_name = member.name if member else user.username

    cal = Calendar()
    cal.add('prodid', '-//Magic Rota//Hospital Shift Calendar//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', f'Shifts – {member_name.title()}')
    cal.add('x-wr-timezone', 'Africa/Nairobi')

    # Query all rotas
    rotas = Rota.query.order_by(Rota.date.asc()).all()

    for idx, r in enumerate(rotas):
        shifts_found = []
        if member_name in (r.shift_8_5 or ''):
            shifts_found.append(('Morning Shift (8 AM - 5 PM)', 8, 0, 17, 0))
        if member_name in (r.shift_5_8 or ''):
            shifts_found.append(('Evening Shift (5 PM - 8 PM)', 17, 0, 20, 0))
        if member_name in (r.shift_8_8 or ''):
            shifts_found.append(('Night Shift (8 PM - 8 AM)', 20, 0, 8, 0))
        if member_name in (r.night_off or ''):
            shifts_found.append(('Night Off 💤', 8, 0, 17, 0))

        shift_date = r.date if r.date else datetime.now().date()
        for title, sh, sm, eh, em in shifts_found:
            start_dt = datetime(shift_date.year, shift_date.month, shift_date.day, sh, sm)
            if 'Night Shift' in title:
                next_day = shift_date + timedelta(days=1)
                end_dt = datetime(next_day.year, next_day.month, next_day.day, eh, em)
            else:
                end_dt = datetime(shift_date.year, shift_date.month, shift_date.day, eh, em)

            event = Event()
            event.add('summary', f'{title} — {member_name.title()}')
            event.add('dtstart', start_dt)
            event.add('dtend', end_dt)
            event.add('description', f'Week: {r.week_range}\nDepartment: {r.department.name if r.department else "General"}')
            event.add('uid', f'rota-{r.id}-{idx}-{token[:8]}@magicrota')
            cal.add_component(event)

    # Query approved leaves for staff member
    if member:
        from models.models import Leave
        leaves = Leave.query.filter_by(member_id=member.id).all()
        for idx, l in enumerate(leaves):
            l_type = getattr(l, 'leave_type', 'Annual Leave') or 'Annual Leave'
            event = Event()
            event.add('summary', f'🏖️ On Leave ({l_type}) — {member_name.title()}')
            event.add('dtstart', l.start_date)
            event.add('dtend', l.end_date + timedelta(days=1))
            event.add('description', f'Leave Type: {l_type}\nReason: {l.reason or "N/A"}')
            event.add('uid', f'leave-{l.id}-{token[:8]}@magicrota')
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
