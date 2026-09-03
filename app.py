from flask import Flask, redirect, url_for, session
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
import os
from datetime import timedelta
from models.models import db, User, init_db_departments
from blueprints.org import org_bp
from blueprints.temp_log import temp_bp, schedule_tasks
from blueprints.members import members_bp
from blueprints.shifts import shifts_bp
from blueprints.leave import leave_bp
from blueprints.rota import rota_bp
from blueprints.pdf import pdf_bp
from blueprints.department import department_bp
from blueprints import auth as auth_bp
from blueprints.audit import audit_bp
from blueprints.swap import swap_bp
from blueprints.ical import ical_bp
from blueprints.notifications import notifications_bp
from blueprints.analytics import analytics_bp
from blueprints.preferences import preferences_bp
from blueprints.float_pool import float_bp

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_PARTITIONED'] = False
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Set session timeout to 30 minutes
app.permanent_session_lifetime = timedelta(minutes=30)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.before_request
def update_session_timeout():
    if current_user.is_authenticated:
        session.permanent = True

with app.app_context():
    db.create_all()
    init_db_departments()
    schedule_tasks(app)

# Register blueprints
app.register_blueprint(org_bp)
app.register_blueprint(department_bp)
app.register_blueprint(members_bp)
app.register_blueprint(shifts_bp)
app.register_blueprint(leave_bp)
app.register_blueprint(rota_bp)
app.register_blueprint(pdf_bp)
app.register_blueprint(temp_bp)
app.register_blueprint(audit_bp)
app.register_blueprint(swap_bp)
app.register_blueprint(ical_bp)
app.register_blueprint(notifications_bp)
app.register_blueprint(analytics_bp)
app.register_blueprint(preferences_bp)
app.register_blueprint(float_bp)
app.register_blueprint(auth_bp, url_prefix='/')

@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('auth.home'))
    else:
        return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(debug=True)
