from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, abort
from flask_login import current_user, login_required
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from models.models import db, Team, User
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

@members_bp.route('/members', methods=['GET', 'POST'])
@login_required

def manage_members():
    teams = Team.query.all()
    return render_template('members.html', teams=teams)

@members_bp.route('/add_member', methods=['GET', 'POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def add_member():
    if request.method == 'POST':
        # Handle form submission
        name = request.form.get('name')  # Use get() to avoid KeyError
        is_admin = request.form.get('is_admin', 0)  # Default to 0 if not provided

        if name:
            # Create and save the new member
            member = Team(name=name, is_admin=int(is_admin))
            db.session.add(member)
            db.session.commit()
            flash('Member added successfully!', 'success')
        else:
            flash('Name is required to add a member.', 'danger')

        return redirect(url_for('members.manage_members'))


@members_bp.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def edit_member(member_id):
    member = Team.query.get_or_404(member_id)
    if request.method == 'POST':
        new_name = request.form.get('name')
        new_is_admin = request.form.get('is_admin')  # Get is_admin value from the form

        if new_name:
            member.name = new_name
            member.is_admin = int(new_is_admin)  # Convert is_admin to integer
            db.session.commit()
            flash('Member updated successfully!', 'success')
            return redirect(url_for('members.manage_members'))  # Redirect to the members page




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