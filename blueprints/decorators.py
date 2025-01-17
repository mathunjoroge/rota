from flask import redirect, url_for, flash
from flask_login import current_user
from functools import wraps

def requires_level(level):
    """Decorator to restrict access to users with a specific level."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated or current_user.level < level:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('auth.login'))
            return func(*args, **kwargs)
        return wrapper
    return decorator
