from flask import Blueprint, render_template, request, redirect, url_for, flash
from models.models import db, Rota, Team
from datetime import date, timedelta
from logic.rota_logic import generate_weekly_rota

rota_bp = Blueprint('rota', __name__)

@rota_bp.route('/generate_rota', methods=['GET', 'POST'])
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

        return redirect(url_for('rota.generate_rota'))

    rotas = Rota.query.all()
    return render_template('rota.html', rotas=rotas)

@rota_bp.route('/delete_rota', methods=['POST'])
def delete_rota():
    Rota.query.delete()
    db.session.commit()
    flash('Rota deleted successfully!', 'success')
    return redirect(url_for('rota.generate_rota'))