from flask import Blueprint, render_template, request, redirect, url_for
from datetime import date
from logic.leave_logic import save_leave_logic, get_leaves_on_date, delete_leave_logic, edit_leave_logic

leave_bp = Blueprint('leave', __name__)

@leave_bp.route('/save_leave/<int:member_id>', methods=['POST'])
def save_leave(member_id):
    return save_leave_logic(member_id, request.form)

@leave_bp.route('/on_leave')
def on_leave():
    today = date.today()
    leaves = get_leaves_on_date(today)
    return render_template('on_leave.html', leaves=leaves)

@leave_bp.route('/delete_leave/<int:leave_id>', methods=['POST'])
def delete_leave(leave_id):
    return delete_leave_logic(leave_id)

@leave_bp.route('/edit_leave/<int:leave_id>', methods=['GET', 'POST'])
def edit_leave(leave_id):
    if request.method == 'POST':
        return edit_leave_logic(leave_id, request.form)
    leave = Leave.query.get_or_404(leave_id)
    return render_template('on_leave.html', leave=leave)