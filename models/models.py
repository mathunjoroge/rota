from flask_sqlalchemy import SQLAlchemy
from datetime import date

db = SQLAlchemy()

class OrgDetails(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(255))

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)

class Leave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    member_id = db.Column(db.Integer, db.ForeignKey('team.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    member = db.relationship('Team', backref=db.backref('leaves', cascade="all, delete"))

    def days_taken(self):
        """Calculates the number of days taken for the leave, including both start and end dates."""
        return (self.end_date - self.start_date).days + 1

    def days_remaining(self):
        """Calculates the number of days remaining for the leave. If the leave has ended, it returns 0."""
        current_date = date.today()
        return max(0, (self.end_date - current_date).days)

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    max_members = db.Column(db.Integer, nullable=False)
    min_members = db.Column(db.Integer, nullable=False)

    def __repr__(self):
        return f"<Shift {self.name}>"

class Rota(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week_range = db.Column(db.String(100), nullable=False)
    shift_8_5 = db.Column(db.String(100), nullable=False)  # 8 AM - 5 PM shift members
    shift_5_8 = db.Column(db.String(50), nullable=False)  # 5 PM - 8 PM shift member
    shift_8_8 = db.Column(db.String(50), nullable=False)  # 8 PM - 8 AM shift member
    night_off = db.Column(db.String(50), nullable=True)  # Night off member