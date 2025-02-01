import logging
import pytz
from datetime import datetime, timedelta

from forms.org_form import EditRotaForm 
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from flask_login import login_required

from models.models import db, Rota, Team  # Make sure your models are imported
from logic.rota_logic import generate_weekly_rota
from blueprints.members import requires_level  # Assuming this is where your requires_level decorator is

# Configure logging
logging.basicConfig(level=logging.ERROR)

rota_bp = Blueprint('rota', __name__)

@rota_bp.route('/generate_rota', methods=['GET', 'POST'])
@login_required
def generate_rota():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'generate':
            try:
                start_date_str = request.form['start_date']
                end_date_str = request.form['end_date']

                # Parse dates with timezone awareness
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=pytz.utc)
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=pytz.utc)

                if end_date < start_date:
                    flash("End date must be after start date.", 'error')
                    return redirect(url_for('rota.generate_rota'))

            except (KeyError, ValueError) as e:
                flash(f"Invalid date format or missing date: {e}", 'error')
                return redirect(url_for('rota.generate_rota'))


            current_date = start_date
            eligible_members = Team.query.all()

            if len(eligible_members) < 7:
                flash("Not enough members to generate a complete rota.", 'error')
                return redirect(url_for('rota.generate_rota'))

            last_night_shift_member = None
            night_shift_history = set()
            evening_shift_history = set()

            first_night_off_member_id = session.pop('first_night_off_member_id', None)
            first_night_off_member = Team.query.get(first_night_off_member_id) if first_night_off_member_id else None

            while current_date <= end_date:
                if current_date.weekday() == 0:  # Monday
                    try:
                        last_night_shift_member = generate_weekly_rota(
                            eligible_members,
                            current_date,
                            last_night_shift_member,
                            night_shift_history,
                            evening_shift_history,
                            first_night_off_member=first_night_off_member
                        )
                        first_night_off_member = None  # Reset after first week
                    except ValueError as e:
                        flash(str(e), 'error')
                        break

                current_date += timedelta(days=1)

 

    # Fetch the last generated rota_id based on the most recent date
    last_rota = Rota.query.order_by(Rota.date.desc()).first()

    if last_rota:
        # Fetch all rotas that have the same rota_id as the latest one
        rotas = Rota.query.filter_by(rota_id=last_rota.rota_id).all()
    else:
        rotas = []

    return render_template('rota.html', rotas=rotas)

@rota_bp.route('/delete_rota', methods=['POST'])
@login_required
@requires_level(1)
def delete_rota():
    try:
        Rota.query.delete()
        db.session.commit()
        flash('Rota deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error deleting rota: {str(e)}")
        flash(f"Error deleting rota: {str(e)}", 'error')
    return redirect(url_for('rota.generate_rota'))


@rota_bp.route('/select_night_off', methods=['GET', 'POST'])
@login_required
@requires_level(1)
def select_night_off():
    if request.method == 'POST':
        member_id = request.form.get('member_id')
        member = Team.query.get(member_id)
        if member:
            session['first_night_off_member_id'] = member.id
            flash(f"Selected {member.name} for the first night off.", 'success')
        else:
            flash("Invalid member selected. Please try again.", 'error')
        return redirect(url_for('rota.generate_rota'))
    else:
        members = Team.query.all()
        return render_template('select_night_off.html', members=members)


@rota_bp.route('/rota/<int:rota_id>', methods=['GET'])
def rota_detail(rota_id):
    rotas = Rota.query.filter_by(rota_id=rota_id).all()

    if not rotas:
        abort(404)

    return render_template('rota_detail.html', rotas=rotas, rota_id=rota_id)



@rota_bp.route('/rotas')
def list_rotas():
    rota_id = request.args.get('rota_id', type=int)
    if rota_id:
        rotas = Rota.query.filter_by(rota_id=rota_id).all()
    else:
        # Get distinct rota_ids
        distinct_rota_ids = db.session.query(Rota.rota_id).distinct().all()
        # Extract the rota_ids from the result
        distinct_rota_ids = [row.rota_id for row in distinct_rota_ids]

        # Fetch rotas based on distinct rota_ids
        rotas = []
        for rota_id in distinct_rota_ids:
            # Get the first rota for each distinct ID (you can change this if you want all)
            rota = Rota.query.filter_by(rota_id=rota_id).first()
            if rota:
                rotas.append(rota)

    return render_template('rotas_list.html', rotas=rotas)
#edit rota
   
@rota_bp.route('/rota/edit/<int:rota_id>', methods=['GET', 'POST'])
@login_required
def edit_rota(rota_id):
    # Get all rota entries under the same rota_id (multiple weeks)
    rotas = Rota.query.filter_by(rota_id=rota_id).all()

    if not rotas:
        flash("No rota found for the given ID.", "danger")
        return redirect(url_for('rota.view_rota'))

    forms = [EditRotaForm(obj=rota) for rota in rotas]  # Create multiple forms

    if request.method == "POST":
        for form in forms:
            if form.validate():
                rota = Rota.query.get(form.id.data)
                if rota:
                    rota.shift_8_5 = form.shift_8_5.data
                    rota.shift_5_8 = form.shift_5_8.data
                    rota.shift_8_8 = form.shift_8_8.data
                    rota.night_off = form.night_off.data

        db.session.commit()
        flash("Rota updated successfully", "success")
        return redirect(url_for('rota.rota_detail', rota_id=rota_id))  # Redirect back to rota_detail

    return render_template('edit_rota.html', forms=forms)






