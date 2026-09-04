from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, abort
from flask_login import current_user, login_required
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from models.models import db, Team, User, Department
from blueprints.forms import RegistrationForm

# Define the requires_level decorator
from functools import wraps
from flask import redirect, url_for, flash, request
from flask_login import current_user

def requires_level(level):
    """Decorator to restrict access to users with a specific level."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or current_user.level < level:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(request.referrer)  # Redirect to the previous page or users page if referrer is not available
            return func(*args, **kwargs)
        return wrapper
    return decorator

members_bp = Blueprint('members', __name__)

@members_bp.route('/members', methods=['GET'])
@login_required
def manage_members():
    dept_id = request.args.get('dept_id', type=int)
    departments = Department.query.all()
    if dept_id:
        teams = Team.query.filter_by(department_id=dept_id).all()
    else:
        teams = Team.query.all()
    return render_template('members.html', teams=teams, departments=departments, selected_dept_id=dept_id)

@members_bp.route('/add_member', methods=['GET', 'POST'])
@login_required
@requires_level(1)
def add_member():
    if request.method == 'POST':
        name = request.form.get('name')
        is_admin = request.form.get('is_admin', 0)
        dept_id = request.form.get('department_id', type=int)
        role_title = request.form.get('role_title', 'Staff Member').strip() or 'Staff Member'
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        can_float = 'can_float' in request.form
        exempt_evening = 'exempt_evening' in request.form
        exempt_night = 'exempt_night' in request.form
        exempt_weekend = 'exempt_weekend' in request.form

        if name:
            member = Team(
                name=name,
                is_admin=int(is_admin),
                department_id=dept_id,
                role_title=role_title,
                phone=phone,
                email=email,
                can_float=can_float,
                exempt_evening=exempt_evening,
                exempt_night=exempt_night,
                exempt_weekend=exempt_weekend
            )
            db.session.add(member)
            db.session.commit()
            flash('Member added successfully!', 'success')
        else:
            flash('Name is required to add a member.', 'danger')

        return redirect(url_for('members.manage_members', dept_id=dept_id if dept_id else None))


@members_bp.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
@requires_level(1)
def edit_member(member_id):
    member = Team.query.get_or_404(member_id)
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_is_admin = request.form.get('is_admin')
        dept_id = request.form.get('department_id', type=int)

        if new_name and new_is_admin is not None:
            member.name = new_name
            member.is_admin = int(new_is_admin)
            if dept_id:
                member.department_id = dept_id
            if 'role_title' in request.form:
                member.role_title = request.form['role_title'].strip() or 'Staff Member'
            if 'phone' in request.form:
                member.phone = request.form['phone'].strip()
            if 'email' in request.form:
                member.email = request.form['email'].strip()
            member.can_float = 'can_float' in request.form
            member.exempt_evening = 'exempt_evening' in request.form
            member.exempt_night = 'exempt_night' in request.form
            member.exempt_weekend = 'exempt_weekend' in request.form

            db.session.commit()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'status': 'success'})
            flash('Member updated successfully!', 'success')
            return redirect(url_for('members.manage_members'))
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'error', 'message': 'Missing data'}), 400
        flash('Failed to update member.', 'danger')
        return redirect(url_for('members.manage_members'))




@members_bp.route('/delete_member/<int:member_id>', methods=['POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def delete_member(member_id):
    member = Team.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
    flash('Member deleted successfully!', 'success')
    return redirect(url_for('members.manage_members'))

@members_bp.route('/users')
@login_required
def users():
    all_users = User.query.all()  # Fetch all users from the database
    form = RegistrationForm()  # Instantiate the form here
    return render_template('users.html', users=all_users, form=form)  # Pass the form to the template

@members_bp.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.username = request.form['username']
        user.email = request.form['email']
        user.level = request.form['level']
        db.session.commit()
        flash('User updated successfully!', 'success')
        return redirect(url_for('members.users'))
    return render_template('edit_user.html', user=user)

@members_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully!', 'success')
    return redirect(url_for('members.users'))

@members_bp.route('/register_user', methods=['POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def register_user():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data, method='pbkdf2:sha256')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password, level=form.level.data)
        db.session.add(user)
        db.session.commit()
        flash('User registered successfully!', 'success')
        return redirect(url_for('members.users'))
    flash('Failed to register user. Please check the form for errors.', 'danger')
    return redirect(url_for('members.users'))