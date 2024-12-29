from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired
from datetime import datetime, date, timedelta
from io import BytesIO
from xhtml2pdf import pisa

# Import models and rota logic
from models.models import db, OrgDetails, Team, Shift, Rota, Leave
from rota_logic import generate_weekly_rota
from leave_logic import save_leave_logic, get_leaves_on_date, delete_leave_logic, edit_leave_logic

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rota.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

db.init_app(app)

with app.app_context():
    db.create_all()

# Define the form for adding organizations
class OrgForm(FlaskForm):
    name = StringField('Organization Name', validators=[DataRequired()])
    department = StringField('Department')
    submit = SubmitField('Add Organization')

@app.route('/add_org', methods=['GET', 'POST'])
def add_org():
    form = OrgForm()
    if form.validate_on_submit():
        name = form.name.data
        department = form.department.data
        new_org = OrgDetails(name=name, department=department)
        db.session.add(new_org)
        db.session.commit()
        flash('Organization added successfully!', 'success')
        return redirect(url_for('org_details'))
    return redirect(url_for('org_details'))

@app.route('/org_details')
def org_details():
    org_details = OrgDetails.query.all()
    form = OrgForm()
    return render_template('org_details.html', org_details=org_details, form=form)

@app.route('/edit_org/<int:org_id>', methods=['POST'])
def edit_org(org_id):
    org = OrgDetails.query.get_or_404(org_id)
    org.name = request.form['name']
    org.department = request.form['department']
    db.session.commit()
    flash('Organization details updated successfully!', 'success')
    return redirect(url_for('org_details'))

@app.route('/delete_org/<int:org_id>', methods=['POST'])
def delete_org(org_id):
    org = OrgDetails.query.get_or_404(org_id)
    db.session.delete(org)
    db.session.commit()
    flash('Organization deleted successfully!', 'success')
    return redirect(url_for('org_details'))

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

@app.route('/save_leave/<int:member_id>', methods=['POST'])
def save_leave(member_id):
    return save_leave_logic(member_id, request.form)

@app.route('/on_leave')
def on_leave():
    today = date.today()
    leaves = get_leaves_on_date(today)
    return render_template('on_leave.html', leaves=leaves)

@app.route('/delete_leave/<int:leave_id>', methods=['POST'])
def delete_leave(leave_id):
    return delete_leave_logic(leave_id)

@app.route('/edit_leave/<int:leave_id>', methods=['GET', 'POST'])
def edit_leave(leave_id):
    if request.method == 'POST':
        return edit_leave_logic(leave_id, request.form)
    leave = Leave.query.get_or_404(leave_id)
    return render_template('on_leave.html', leave=leave)

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

@app.route('/delete_rota', methods=['POST'])
def delete_rota():
    Rota.query.delete()
    db.session.commit()
    flash('Rota deleted successfully!', 'success')
    return redirect(url_for('generate_rota'))

@app.route('/export_pdf')
def export_pdf():
    rotas = Rota.query.all()
    org_details = OrgDetails.query.all()  # Fetch organization details

    # Find the start and end dates from the rota entries
    if rotas:
        start_date = min([datetime.strptime(rota.week_range.split(' - ')[0], '%d/%m/%Y') for rota in rotas])
        end_date = max([datetime.strptime(rota.week_range.split(' - ')[1], '%d/%m/%Y') for rota in rotas])
    else:
        start_date = end_date = None

    html = render_template('export_pdf.html', rotas=rotas, org_details=org_details, start_date=start_date, end_date=end_date)
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

if __name__ == '__main__':
    app.run(debug=True)