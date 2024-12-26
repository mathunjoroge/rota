from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
import random
from io import BytesIO
from xhtml2pdf import pisa

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rota.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'  # Needed for flash messages
db = SQLAlchemy(app)

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
        return (self.end_date - self.start_date).days + 1

    def days_remaining(self):
        current_date = date.today()
        return (self.end_date - current_date).days if self.end_date >= current_date else 0

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

# Ensure that the database tables are created
with app.app_context():
    db.create_all()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/members', methods=['GET', 'POST'])
def manage_members():
    if request.method == 'POST':
        name = request.form['name']
        if name:
            member = Team(name=name)
            db.session.add(member)
            db.session.commit()
        return redirect(url_for('manage_members'))
    
    teams = Team.query.all()
    return render_template('members.html', teams=teams)

@app.route('/leave/<int:member_id>', methods=['GET', 'POST'])
def manage_leave(member_id):
    member = Team.query.get_or_404(member_id)
    if request.method == 'POST':
        start_date = date.fromisoformat(request.form['start_date'])
        end_date = date.fromisoformat(request.form['end_date'])
        
        # Ensure the rota is not yet made or the member is in the morning shift
        existing_rotas = Rota.query.filter(Rota.week_range.contains(start_date.strftime('%d/%m/%Y'))).all()
        if existing_rotas:
            for rota in existing_rotas:
                if member.name not in rota.shift_8_5:
                    return "Leave can only be applied by members in the morning shift."
                if start_date < date.today() or end_date < start_date:
                    return "Invalid leave dates."
        else:
            # First-come, first-served basis
            overlapping_leaves = Leave.query.filter(
                Leave.member_id == member_id,
                Leave.start_date <= end_date,
                Leave.end_date >= start_date
            ).first()
            if overlapping_leaves:
                return "Leave conflicts with an existing leave."

        leave = Leave(member_id=member_id, start_date=start_date, end_date=end_date)
        db.session.add(leave)
        db.session.commit()
        return redirect(url_for('manage_members'))
    return render_template('manage_leave.html', member=member)

@app.route('/delete_leave/<int:leave_id>', methods=['POST'])
def delete_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    db.session.delete(leave)
    db.session.commit()
    return redirect(url_for('manage_members'))

@app.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
def edit_member(member_id):
    member = Team.query.get_or_404(member_id)
    if request.method == 'POST':
        new_name = request.form['name']
        if new_name:
            member.name = new_name
            db.session.commit()
            if request.is_json:
                return jsonify(status='success')
            return redirect(url_for('manage_members'))
    if request.is_json:
        return jsonify(name=member.name)
    return render_template('edit_member.html', member=member)

@app.route('/delete_member/<int:member_id>', methods=['POST'])
def delete_member(member_id):
    member = Team.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
    return redirect(url_for('manage_members'))

@app.route('/on_leave', methods=['GET'])
def on_leave():
    current_date = date.today()
    leaves = Leave.query.filter(Leave.start_date <= current_date, Leave.end_date >= current_date).all()
    return render_template('on_leave.html', leaves=leaves)

@app.route('/edit_leave/<int:leave_id>', methods=['GET', 'POST'])
def edit_leave(leave_id):
    leave = Leave.query.get_or_404(leave_id)
    if request.method == 'POST':
        start_date = date.fromisoformat(request.form['start_date'])
        end_date = date.fromisoformat(request.form['end_date'])
        if start_date > end_date:
            return "End date must be after start date."

        leave.start_date = start_date
        leave.end_date = end_date
        db.session.commit()
        return redirect(url_for('on_leave'))
    return render_template('edit_leave.html', leave=leave)

@app.route('/shifts', methods=['GET', 'POST'])
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
        return redirect(url_for('shifts'))

    shifts = Shift.query.all()
    return render_template('shifts.html', shifts=shifts)

@app.route('/edit_shift/<int:shift_id>', methods=['POST'])
def edit_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    shift.name = request.form['shift_name']
    shift.start_time = datetime.strptime(request.form['start_time'], '%H:%M').time()
    shift.end_time = datetime.strptime(request.form['end_time'], '%H:%M').time()
    shift.max_members = int(request.form['max_members'])
    shift.min_members = int(request.form['min_members'])
    db.session.commit()
    flash('Shift updated successfully!', 'success')
    return redirect(url_for('shifts'))

@app.route('/delete_shift/<int:shift_id>', methods=['POST'])
def delete_shift(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    db.session.delete(shift)
    db.session.commit()
    flash('Shift deleted successfully!', 'success')
    return redirect(url_for('shifts'))

@app.route('/export_pdf')
def export_pdf():
    rotas = Rota.query.all()
    html = render_template('export_pdf.html', rotas=rotas)
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    
    if pisa_status.err:
        return "Error generating PDF", 500

    pdf.seek(0)
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=rota.pdf'})

@app.route('/generate_rota', methods=['GET', 'POST'])
def generate_rota():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate':
            start_date = date.fromisoformat(request.form['start_date'])
            end_date = date.fromisoformat(request.form['end_date'])

            Rota.query.delete()
            db.session.commit()

            current_date = start_date
            eligible_members = Team.query.all()

            if len(eligible_members) < 7:
                return "Not enough members to generate a rota."

            last_night_shift_member = None
            night_shift_history = set()
            evening_shift_history = set()

            while current_date <= end_date:
                if current_date.weekday() == 0:  # Monday (Start of the week)
                    last_night_shift_member = generate_weekly_rota(eligible_members, current_date, last_night_shift_member, night_shift_history, evening_shift_history)

                current_date += timedelta(days=1)

        elif action == 'delete':
            Rota.query.delete()
            db.session.commit()

        return redirect(url_for('generate_rota'))

    rotas = Rota.query.all()
    return render_template('rota.html', rotas=rotas)

def generate_weekly_rota(eligible_members, current_date, last_night_shift_member, night_shift_history, evening_shift_history):
    week_start_date = current_date
    week_end_date = current_date + timedelta(days=4)  # Friday (End of the week)
    week_range = f"{week_start_date.strftime('%d/%m/%Y')} - {week_end_date.strftime('%d/%m/%Y')}"

    eligible_members_for_this_week = [
        m for m in eligible_members if not any(
            leave.start_date <= current_date <= leave.end_date for leave in m.leaves
        )
    ]

    # Remove last night shift member if present
    if last_night_shift_member in eligible_members_for_this_week:
        eligible_members_for_this_week.remove(last_night_shift_member)

    remaining_members_evening = [m for m in eligible_members_for_this_week if m.name not in evening_shift_history]
    remaining_members_night = [m for m in eligible_members_for_this_week if m.name not in night_shift_history]

    if not remaining_members_evening:
        remaining_members_evening = eligible_members_for_this_week
    if not remaining_members_night:
        remaining_members_night = eligible_members_for_this_week

    evening_shift_member = random.choice(remaining_members_evening)
    # Only remove if the member is in the list
    if evening_shift_member in eligible_members_for_this_week:
        eligible_members_for_this_week.remove(evening_shift_member)
    evening_shift_history.add(evening_shift_member.name)

    night_shift_member = random.choice(remaining_members_night)
    # Only remove if the member is in the list
    if night_shift_member in eligible_members_for_this_week:
        eligible_members_for_this_week.remove(night_shift_member)
    night_shift_history.add(night_shift_member.name)

    # Ensure we have enough members for morning shifts
    morning_shift_members = random.sample(eligible_members_for_this_week, min(4, len(eligible_members_for_this_week)))

    if last_night_shift_member and len(morning_shift_members) < 4:
        morning_shift_members.insert(0, last_night_shift_member)

    # Ensure the morning shift has at least two members
    if len(morning_shift_members) < 2:
        return "Morning shift must have at least two members."

    night_off_value = last_night_shift_member.name if last_night_shift_member else None

    week_rota = Rota(
        week_range=week_range,
        shift_8_5=', '.join([m.name for m in morning_shift_members]),
        shift_5_8=evening_shift_member.name,
        shift_8_8=night_shift_member.name,
        night_off=night_off_value
    )
    db.session.add(week_rota)
    db.session.commit()

    return night_shift_member

if __name__ == '__main__':
    app.run(debug=True)