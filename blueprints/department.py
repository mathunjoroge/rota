from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models.models import db, Department, Team, Shift, Rota
from blueprints.members import requires_level

department_bp = Blueprint('department', __name__)

@department_bp.route('/departments', methods=['GET'])
@login_required
def list_departments():
    departments = Department.query.all()
    return render_template('departments.html', departments=departments)

@department_bp.route('/add_department', methods=['POST'])
@login_required
@requires_level(1)
def add_department():
    name = request.form.get('name')
    code = request.form.get('code')
    description = request.form.get('description', '')

    if not name or not code:
        flash("Department name and code are required.", 'danger')
        return redirect(url_for('department.list_departments'))

    # Check for existing code or name
    if Department.query.filter_by(code=code).first():
        flash(f"Department code '{code}' already exists.", 'danger')
        return redirect(url_for('department.list_departments'))
    if Department.query.filter_by(name=name).first():
        flash(f"Department name '{name}' already exists.", 'danger')
        return redirect(url_for('department.list_departments'))

    new_dept = Department(name=name, code=code.upper(), description=description)
    db.session.add(new_dept)
    db.session.commit()
    flash(f"Department '{name}' created successfully!", 'success')
    return redirect(url_for('department.list_departments'))

@department_bp.route('/edit_department/<int:dept_id>', methods=['POST'])
@login_required
@requires_level(1)
def edit_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    name = request.form.get('name')
    code = request.form.get('code')
    description = request.form.get('description', '')

    if name:
        dept.name = name
    if code:
        dept.code = code.upper()
    dept.description = description

    db.session.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'success'})
    flash(f"Department '{dept.name}' updated successfully!", 'success')
    return redirect(url_for('department.list_departments'))

@department_bp.route('/delete_department/<int:dept_id>', methods=['POST'])
@login_required
@requires_level(1)
def delete_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    # Don't delete the default GEN department
    if dept.code == 'GEN':
        flash("Cannot delete default institution department.", 'warning')
        return redirect(url_for('department.list_departments'))

    db.session.delete(dept)
    db.session.commit()
    flash(f"Department deleted successfully!", 'success')
    return redirect(url_for('department.list_departments'))
