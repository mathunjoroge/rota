from flask import Blueprint, render_template, request
from flask_login import current_user
from datetime import date, timedelta
from logic.leave_logic import (
    save_leave_logic, get_leaves_on_date, delete_leave_logic, edit_leave_logic,
    apply_leave_logic, approve_leave_request_logic, reject_leave_request_logic,
    get_leave_balances, weekdays_between
)
from blueprints.routes import login_required 
from models.models import Leave, LeaveRequest, Department, Team
from blueprints.members import requires_level

leave_bp = Blueprint('leave', __name__)

@leave_bp.route('/save_leave/<int:member_id>', methods=['POST'])
@login_required
@requires_level(1)
def save_leave(member_id):
    return save_leave_logic(member_id, request.form)

@leave_bp.route('/apply_leave', methods=['POST'])
@login_required
def apply_leave():
    return apply_leave_logic(request.form, current_user)

@leave_bp.route('/leave_request/<int:req_id>/approve', methods=['POST'])
@login_required
@requires_level(1)
def approve_leave_request(req_id):
    return approve_leave_request_logic(req_id, current_user)

@leave_bp.route('/leave_request/<int:req_id>/reject', methods=['POST'])
@login_required
@requires_level(1)
def reject_leave_request(req_id):
    return reject_leave_request_logic(req_id, current_user, request.form)

@leave_bp.route('/on_leave')
@login_required
def on_leave():
    dept_id = request.args.get('dept_id', type=int)
    departments = Department.query.all()
    all_members = Team.query.filter_by(department_id=dept_id).all() if dept_id else Team.query.order_by(Team.name).all()

    if dept_id:
        leaves = Leave.query.join(Team).filter(Team.department_id == dept_id).all()
        pending_requests = LeaveRequest.query.join(Team).filter(Team.department_id == dept_id, LeaveRequest.status == 'pending').order_by(LeaveRequest.created_at.desc()).all()
        all_requests = LeaveRequest.query.join(Team).filter(Team.department_id == dept_id).order_by(LeaveRequest.created_at.desc()).all()
    else:
        leaves = Leave.query.all()
        pending_requests = LeaveRequest.query.filter_by(status='pending').order_by(LeaveRequest.created_at.desc()).all()
        all_requests = LeaveRequest.query.order_by(LeaveRequest.created_at.desc()).all()

    current_date = date.today()
    leaves_info = []

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
    
    leave_balances = get_leave_balances(dept_id)

    return render_template(
        'on_leave.html',
        leaves_info=leaves_info,
        pending_requests=pending_requests,
        all_requests=all_requests,
        leave_balances=leave_balances,
        all_members=all_members,
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