from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime
from flask_login import UserMixin
import uuid

db = SQLAlchemy()

class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Department {self.name}>"

class OrgDetails(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(255))

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    is_admin = db.Column(db.Integer, default=0)  # 0=Regular, 1=Team Leader/Admin (Morning Only), 2=Senior (Evening & Morning), 3=Night Exempt
    role_title = db.Column(db.String(80), default='Staff Member') # e.g. Consultant, Charge Nurse, Medical Officer
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    department = db.relationship('Department', backref=db.backref('members', cascade="all, delete-orphan"))
    phone = db.Column(db.String(20), nullable=True)       # For SMS alerts
    can_float = db.Column(db.Boolean, default=False)      # Float pool eligibility
    email = db.Column(db.String(120), nullable=True)      # For email shift alerts
    annual_leave_allowance = db.Column(db.Integer, default=21) # Annual leave days quota
    exempt_evening = db.Column(db.Boolean, default=False) # Exclude from evening shifts
    exempt_night = db.Column(db.Boolean, default=False)   # Exclude from night shifts
    exempt_weekend = db.Column(db.Boolean, default=False) # Exclude from weekend shifts

class Leave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    leave_type = db.Column(db.String(50), default='Annual Leave')
    reason = db.Column(db.String(255), nullable=True)
    member = db.relationship('Team', backref=db.backref('leaves', cascade="all, delete"))

    def days_taken(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    def days_remaining(self):
        if self.end_date:
            remaining_days = (self.end_date - date.today()).days
            return max(remaining_days, 0)
        return 0

    def __repr__(self):
        return f"<Leave {self.id} - Member {self.member_id}: {self.start_date} to {self.end_date}>"

class LeaveRequest(db.Model):
    """Staff leave application request workflow."""
    __tablename__ = 'leave_requests'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    member_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    leave_type = db.Column(db.String(50), default='Annual Leave', nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending/approved/rejected
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    review_notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)

    member = db.relationship('Team', backref=db.backref('leave_requests', cascade="all, delete"))
    reviewer = db.relationship('User', foreign_keys=[reviewed_by_id])

    def days_requested(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    max_members = db.Column(db.Integer, nullable=False)
    min_members = db.Column(db.Integer, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    department = db.relationship('Department', backref=db.backref('shifts', cascade="all, delete-orphan"))

    def __repr__(self):
        return f"<Shift {self.name}>"

class Rota(db.Model):
    __tablename__ = 'rotas'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rota_id = db.Column(db.Integer, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    department = db.relationship('Department', backref=db.backref('rotas', cascade="all, delete-orphan"))
    week_range = db.Column(db.String(50), nullable=False)
    shift_8_5 = db.Column(db.String(255), nullable=False)
    shift_5_8 = db.Column(db.String(255), nullable=False)
    shift_8_8 = db.Column(db.String(255), nullable=False)
    night_off = db.Column(db.String(255), nullable=True)
    date = db.Column(db.Date, default=date.today, nullable=False)

class RotaAssignment(db.Model):
    __tablename__ = 'rota_assignments'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rota_id = db.Column(db.Integer, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    member_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    shift_name = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    member = db.relationship('Team')
    department = db.relationship('Department')

class ShiftHistory(db.Model):
    __tablename__ = 'shift_history'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rota_id = db.Column(db.Integer, nullable=False)
    member_name = db.Column(db.String(255), nullable=False)
    shift_type = db.Column(db.String(50), nullable=False)
    week_range = db.Column(db.String(50), nullable=False)

class MemberShiftState(db.Model):
    __tablename__ = 'member_shift_states'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    rota_id = db.Column(db.Integer, nullable=False)
    member_name = db.Column(db.String(255), nullable=False)
    shift_index = db.Column(db.Integer, nullable=False)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    level = db.Column(db.Integer, default=0)  # 0=Staff, 1=Dept Admin, 2=Super Admin
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    department = db.relationship('Department', backref=db.backref('users'))
    ical_token = db.Column(db.String(64), unique=True, nullable=True)

    def get_or_create_ical_token(self):
        """Return existing iCal token or generate a new one."""
        if not self.ical_token:
            self.ical_token = uuid.uuid4().hex
            db.session.commit()
        return self.ical_token

class TemperatureLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    time = db.Column(db.String(5), nullable=False)  # 'AM' or 'PM'
    recorded_temp = db.Column(db.Float, nullable=False)
    acceptable = db.Column(db.Boolean, nullable=False)
    initials = db.Column(db.String(3), nullable=False)
    estimated_room = db.Column(db.Float, nullable=True)

# ── NEW MODELS ──────────────────────────────────────────────

class ShiftSwapRequest(db.Model):
    """Peer-to-peer shift swap requests with two-stage approval."""
    __tablename__ = 'shift_swap_requests'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    proposed_member_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    rota_id = db.Column(db.Integer, nullable=False)
    week_range = db.Column(db.String(50), nullable=False)
    requester_shift = db.Column(db.String(50), nullable=False)
    proposed_shift = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending/peer_approved/approved/rejected
    reason = db.Column(db.String(255), nullable=True)
    peer_response = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    requester = db.relationship('Team', foreign_keys=[requester_id])
    proposed_member = db.relationship('Team', foreign_keys=[proposed_member_id])

class AuditLog(db.Model):
    """Immutable audit trail — every data change is recorded for KMPDC/PPB compliance."""
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(50), nullable=True)
    action = db.Column(db.String(50), nullable=False)       # 'create', 'update', 'delete', 'generate'
    entity_type = db.Column(db.String(50), nullable=False)  # 'Rota', 'Team', 'Leave', etc.
    entity_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.String(512), nullable=True)
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user = db.relationship('User', foreign_keys=[user_id])

class StaffPreference(db.Model):
    """Staff-submitted preferred off days for upcoming rota generation."""
    __tablename__ = 'staff_preferences'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    member_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    preferred_off_days = db.Column(db.String(200), nullable=True)  # JSON list: '["2026-09-07","2026-09-08"]'
    notes = db.Column(db.String(255), nullable=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    member = db.relationship('Team', backref=db.backref('preferences', cascade='all, delete'))

class Notification(db.Model):
    """In-app notification centre for swap requests, alerts, rota publications."""
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.String(512), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('notifications', cascade='all, delete'))

# ── MIGRATION & INITIALISATION ───────────────────────────────

from sqlalchemy import text

def init_db_departments():
    """Ensure at least one default department exists, perform lightweight schema migration, and link unassigned records."""
    db.create_all()

    # Column auto-migration for existing SQLite databases
    migrations = {
        'team': [
            ('department_id',          'INTEGER REFERENCES departments(id)'),
            ('phone',                  'TEXT'),
            ('can_float',              'INTEGER DEFAULT 0'),
            ('email',                  'TEXT'),
            ('annual_leave_allowance', 'INTEGER DEFAULT 21'),
            ('role_title',             "TEXT DEFAULT 'Staff Member'"),
            ('exempt_evening',         'INTEGER DEFAULT 0'),
            ('exempt_night',           'INTEGER DEFAULT 0'),
            ('exempt_weekend',         'INTEGER DEFAULT 0'),
        ],
        'leave': [
            ('leave_type', "TEXT DEFAULT 'Annual Leave'"),
            ('reason',     'TEXT'),
        ],
        'shift': [('department_id', 'INTEGER REFERENCES departments(id)')],
        'rotas': [('department_id', 'INTEGER REFERENCES departments(id)')],
        'user':  [
            ('department_id', 'INTEGER REFERENCES departments(id)'),
            ('ical_token',    'TEXT'),
        ],
    }

    for table_name, new_cols in migrations.items():
        try:
            result = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            existing_cols = [row[1] for row in result]
            for col_name, col_def in new_cols:
                if existing_cols and col_name not in existing_cols:
                    db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))
                    db.session.commit()
        except Exception:
            db.session.rollback()

    default_dept = Department.query.filter_by(code='GEN').first()
    if not default_dept:
        default_dept = Department(name='General / Main', code='GEN', description='Default institution department')
        db.session.add(default_dept)
        db.session.commit()

    for m in Team.query.filter_by(department_id=None).all():
        m.department_id = default_dept.id
    for s in Shift.query.filter_by(department_id=None).all():
        s.department_id = default_dept.id
    for r in Rota.query.filter_by(department_id=None).all():
        r.department_id = default_dept.id

    db.session.commit()
    return default_dept
