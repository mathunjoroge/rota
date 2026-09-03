from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from models.models import db, Team, Rota, Leave, TemperatureLog, Department
from collections import defaultdict
from datetime import datetime, timedelta

analytics_bp = Blueprint('analytics', __name__)

@analytics_bp.route('/analytics')
@login_required
def analytics_page():
    """Render main Analytics & Fairness Dashboard."""
    departments = Department.query.all()
    selected_dept_id = request.args.get('dept_id', type=int) or (getattr(current_user, 'department_id', None) or (departments[0].id if departments else None))
    return render_template('analytics.html', departments=departments, selected_dept_id=selected_dept_id)


@analytics_bp.route('/analytics/api/shift_fairness')
@login_required
def api_shift_fairness():
    """API endpoint providing shift count distribution per staff member (Chart.js)."""
    dept_id = request.args.get('dept_id', type=int) or getattr(current_user, 'department_id', None)
    query = Rota.query
    if dept_id:
        query = query.filter_by(department_id=dept_id)
    rotas = query.all()

    members = Team.query.filter_by(department_id=dept_id).all() if dept_id else Team.query.all()
    member_names = [m.name for m in members]

    counts = defaultdict(lambda: {'morning': 0, 'evening': 0, 'night': 0, 'night_off': 0})

    for r in rotas:
        for m in member_names:
            if m in (r.shift_8_5 or ''): counts[m]['morning'] += 1
            if m in (r.shift_5_8 or ''): counts[m]['evening'] += 1
            if m in (r.shift_8_8 or ''): counts[m]['night'] += 1
            if m in (r.night_off or ''): counts[m]['night_off'] += 1

    labels = list(counts.keys())
    return jsonify({
        'labels': labels,
        'morning': [counts[m]['morning'] for m in labels],
        'evening': [counts[m]['evening'] for m in labels],
        'night': [counts[m]['night'] for m in labels],
        'night_off': [counts[m]['night_off'] for m in labels],
    })


@analytics_bp.route('/analytics/api/leave_stats')
@login_required
def api_leave_stats():
    """API endpoint providing leave utilization per staff member."""
    dept_id = request.args.get('dept_id', type=int) or getattr(current_user, 'department_id', None)
    members = Team.query.filter_by(department_id=dept_id).all() if dept_id else Team.query.all()

    labels = []
    taken = []
    remaining = []

    for m in members:
        leaves = Leave.query.filter_by(member_id=m.id).all()
        total_taken = sum(l.days_taken() for l in leaves)
        total_remaining = sum(l.days_remaining() for l in leaves)
        labels.append(m.name)
        taken.append(total_taken)
        remaining.append(total_remaining)

    return jsonify({
        'labels': labels,
        'taken': taken,
        'remaining': remaining
    })


@analytics_bp.route('/analytics/api/temp_trend')
@login_required
def api_temp_trend():
    """API endpoint providing 30-day temperature logs for trend analysis."""
    cutoff = datetime.now().date() - timedelta(days=30)
    logs = TemperatureLog.query.filter(TemperatureLog.date >= cutoff).order_by(TemperatureLog.date.asc()).all()

    dates = []
    room_temps = []
    acceptable = []

    for l in logs:
        dates.append(f"{l.date.strftime('%d-%b')} ({l.time})")
        room_temps.append(l.estimated_room)
        acceptable.append(l.acceptable)

    return jsonify({
        'dates': dates,
        'temps': room_temps,
        'acceptable': acceptable
    })
