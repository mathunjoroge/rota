from flask import Blueprint, render_template, request
from datetime import date, timedelta
from logic.leave_logic import save_leave_logic, get_leaves_on_date, delete_leave_logic, edit_leave_logic
from blueprints.routes import login_required 
from models.models import Leave, Department, Team
from blueprints.members import requires_level

leave_bp = Blueprint('leave', __name__)

@leave_bp.route('/save_leave/<int:member_id>', methods=['POST'])
@login_required
@requires_level(1)
def save_leave(member_id):
    return save_leave_logic(member_id, request.form)

@leave_bp.route('/on_leave')
@login_required
def on_leave():
    dept_id = request.args.get('dept_id', type=int)
    departments = Department.query.all()
    if dept_id:
        leaves = Leave.query.join(Team).filter(Team.department_id == dept_id).all()
    else:
        leaves = Leave.query.all()

    current_date = date.today()
    leaves_info = []

    def weekdays_between(start_date, end_date):
        weekdays = 0
        for single_date in (start_date + timedelta(n) for n in range((end_date - start_date).days + 1)):
            if single_date.weekday() < 5:
                weekdays += 1
        return weekdays

    for leave in leaves:
        days_taken = weekdays_between(leave.start_date, leave.end_date)
        if leave.start_date > current_date:
            days_remaining = days_taken
        else:
            days_remaining = weekdays_between(current_date, leave.end_date)
            if days_remaining < 0:
                days_remaining = 0

        leaves_info.append({
            'leave': leave,
            'days_taken': days_taken,
            'days_remaining': days_remaining
        })
    
    return render_template(
        'on_leave.html',
        leaves_info=leaves_info,
        current_date=current_date,
        leaves_on_date=get_leaves_on_date(current_date),
        departments=departments,
        selected_dept_id=dept_id
    )

@leave_bp.route('/delete_leave/<int:leave_id>', methods=['POST'])
@login_required
@requires_level(1)
def delete_leave(leave_id):
    return delete_leave_logic(leave_id)

@leave_bp.route('/edit_leave/<int:leave_id>', methods=['GET', 'POST'])
@login_required
@requires_level(1)
def edit_leave(leave_id):
    if request.method == 'POST':
        return edit_leave_logic(leave_id, request.form)
    leave = Leave.query.get_or_404(leave_id)
    return render_template('on_leave.html', leave=leave)