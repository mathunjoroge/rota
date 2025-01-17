from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required
from models.models import db, Rota, Team
from datetime import date, timedelta
from logic.rota_logic import generate_weekly_rota
from blueprints.members import requires_level

rota_bp = Blueprint('rota', __name__)

@rota_bp.route('/generate_rota', methods=['GET', 'POST'])
@login_required
def generate_rota():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'generate':
            try:
                start_date = date.fromisoformat(request.form['start_date'])
                end_date = date.fromisoformat(request.form['end_date'])
            except (KeyError, ValueError):
                flash("Invalid date format. Please try again.", 'error')
                return redirect(url_for('rota.generate_rota'))

            # Clear existing rotas
            try:
                Rota.query.delete()
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                flash(f"Error clearing existing rotas: {str(e)}", 'error')
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
                if current_date.weekday() == 0:  # Monday (Start of the week)
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

        elif action == 'delete':
            try:
                Rota.query.delete()
                db.session.commit()
                flash("Rota deleted successfully.", 'success')
            except Exception as e:
                db.session.rollback()
                flash(f"Error deleting rota: {str(e)}", 'error')

        return redirect(url_for('rota.generate_rota'))

    rotas = Rota.query.all()
    return render_template('rota.html', rotas=rotas)

@rota_bp.route('/delete_rota', methods=['POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def delete_rota():
    try:
        Rota.query.delete()
        db.session.commit()
        flash('Rota deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting rota: {str(e)}", 'error')
    return redirect(url_for('rota.generate_rota'))

@rota_bp.route('/select_night_off', methods=['GET', 'POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
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