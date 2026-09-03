from flask_sqlalchemy import SQLAlchemy
from datetime import date
from flask_login import UserMixin

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
    is_admin = db.Column(db.Integer, default=0)  # 0=Regular, 1=Team Leader, 2=Evening Exempt, 3=Night Exempt
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    department = db.relationship('Department', backref=db.backref('members', cascade="all, delete-orphan"))

class Leave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    member = db.relationship('Team', backref=db.backref('leaves', cascade="all, delete"))

    def days_taken(self):
        """Calculate the number of days taken."""
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return 0

    def days_remaining(self):
        """Calculate the number of days remaining from today."""
        if self.end_date:
            remaining_days = (self.end_date - date.today()).days
            return max(remaining_days, 0)
        return 0

    def __repr__(self):
        return f"<Leave {self.id} - Member {self.member_id}: {self.start_date} to {self.end_date}>"

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
    shift_name = db.Column(db.String(50), nullable=False)  # 'morning', 'evening', 'night', 'night_off', 'on_leave'
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

class TemperatureLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=date.today)
    time = db.Column(db.String(5), nullable=False)  # 'AM' or 'PM'
    recorded_temp = db.Column(db.Float, nullable=False)
    acceptable = db.Column(db.Boolean, nullable=False)
    initials = db.Column(db.String(3), nullable=False)
    estimated_room = db.Column(db.Float, nullable=True)

from sqlalchemy import text

def init_db_departments():
    """Ensure at least one default department exists, perform lightweight schema migration, and link unassigned records."""
    # Ensure new tables are created
    db.create_all()

    # Lightweight auto-migration for existing SQLite database files
    tables_to_migrate = ['team', 'shift', 'rotas', 'user']
    for table_name in tables_to_migrate:
        try:
            result = db.session.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
            col_names = [row[1] for row in result]
            if col_names and 'department_id' not in col_names:
                db.session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN department_id INTEGER REFERENCES departments(id)"))
                db.session.commit()
        except Exception as e:
            db.session.rollback()

    default_dept = Department.query.filter_by(code='GEN').first()
    if not default_dept:
        default_dept = Department(name='General / Main', code='GEN', description='Default institution department')
        db.session.add(default_dept)
        db.session.commit()

    # Assign unassigned members to default department
    unassigned_members = Team.query.filter_by(department_id=None).all()
    for m in unassigned_members:
        m.department_id = default_dept.id

    # Assign unassigned shifts to default department
    unassigned_shifts = Shift.query.filter_by(department_id=None).all()
    for s in unassigned_shifts:
        s.department_id = default_dept.id

    # Assign unassigned rotas to default department
    unassigned_rotas = Rota.query.filter_by(department_id=None).all()
    for r in unassigned_rotas:
        r.department_id = default_dept.id

    db.session.commit()
    return default_dept 
