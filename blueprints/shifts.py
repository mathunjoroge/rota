from flask import Blueprint, render_template, request, redirect, url_for, flash
from models.models import db, Shift
from blueprints.routes import login_required 
from datetime import datetime
from blueprints.members import requires_level

shifts_bp = Blueprint('shifts', __name__)

@shifts_bp.route('/shifts', methods=['GET', 'POST'])
@login_required
def shifts():
    if request.method == 'POST':
        shift_name = request.form['shift_name']
        start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
        end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()
        max_members = int(request.form['max_members'])
        min_members = int(request.form['min_members'])
        new_shift = Shift(name=shift_name, start_time=start_time, end_time=end_time, max_members=max_members, min_members=min_members)
        db.session.add(new_shift)
        db.session.commit()
        flash('Shift added successfully!', 'success')
        return redirect(url_for('shifts.shifts'))

    shifts = Shift.query.all()
    return render_template('shifts.html', shifts=shifts)

@shifts_bp.route('/edit_shift/<int:shift_id>', methods=['POST'])
@login_required
@requires_level(1)
def edit_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    shift.name = request.form['shift_name']
    shift.start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
    shift.end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()
    shift.max_members = int(request.form['max_members'])
    shift.min_members = int(request.form['min_members'])
    db.session.commit()
    flash('Shift updated successfully!', 'success')
    return redirect(url_for('shifts.shifts'))

@shifts_bp.route('/delete_shift/<int:shift_id>', methods=['POST'])
@login_required
@requires_level(1)
def delete_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    db.session.delete(shift)
    db.session.commit()
    flash('Shift deleted successfully!', 'danger')
    return redirect(url_for('shifts.shifts'))