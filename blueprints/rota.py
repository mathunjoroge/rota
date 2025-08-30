import logging
import pytz
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort
from flask_login import login_required
from forms.org_form import EditRotaForm
from models.models import db, Rota, Team, ShiftHistory, MemberShiftState
from logic.rota_logic import generate_period_rota
from blueprints.members import requires_level

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
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=pytz.utc).date()
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=pytz.utc).date()
                if end_date < start_date:
                    flash("End date must be after start date.", 'error')
                    return redirect(url_for('rota.generate_rota'))
                period_weeks = ((end_date - start_date).days // 7) + 1
                if period_weeks < 1:
                    flash("Period must include at least one week.", 'error')
                    return redirect(url_for('rota.generate_rota'))
                eligible_members = Team.query.all()
                if len(eligible_members) < 7:
                    flash("Not enough members to generate a complete rota.", 'error')
                    return redirect(url_for('rota.generate_rota'))
                first_night_off_member_id = session.pop('first_night_off_member_id', None)
                first_night_off_member = Team.query.get(first_night_off_member_id) if first_night_off_member_id else None
                night_shift_members, rota_id = generate_period_rota(
                    eligible_members=eligible_members,
                    start_date=start_date,
                    period_weeks=period_weeks,
                    week_duration_days=7,
                    reset_history_after_weeks=6,
                    use_db_for_history=True,
                    first_night_off_member=first_night_off_member
                )
                flash(f"Rota generated successfully with ID {rota_id} for {period_weeks} weeks.", 'success')
                return redirect(url_for('rota.rota_detail', rota_id=rota_id))
            except ValueError as e:
                flash(f"Error generating rota: {str(e)}", 'error')
                return redirect(url_for('rota.generate_rota'))
            except Exception as e:
                logging.error(f"Server error generating rota: {str(e)}")
                flash(f"Server error: {str(e)}", 'error')
                return redirect(url_for('rota.generate_rota'))
    last_rota = Rota.query.order_by(Rota.date.desc()).first()
    rotas = Rota.query.filter_by(rota_id=last_rota.rota_id).order_by(Rota.date).all() if last_rota else []
    return render_template('rota.html', rotas=rotas)

@rota_bp.route('/delete_rota', methods=['POST'])
@login_required
@requires_level(1)
def delete_rota():
    try:
        Rota.query.delete()
        ShiftHistory.query.delete()
        MemberShiftState.query.delete()
        db.session.commit()
        flash('Rota, shift history, and shift states deleted successfully!', 'success')
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
    rotas = Rota.query.filter_by(rota_id=rota_id).order_by(Rota.date).all()
    if not rotas:
        abort(404)
    return render_template('rota_detail.html', rotas=rotas, rota_id=rota_id)

@rota_bp.route('/rotas')
def list_rotas():
    rota_id = request.args.get('rota_id', type=int)
    if rota_id:
        rotas = Rota.query.filter_by(rota_id=rota_id).order_by(Rota.date).all()
    else:
        distinct_rota_ids = db.session.query(Rota.rota_id).distinct().all()
        distinct_rota_ids = [row.rota_id for row in distinct_rota_ids]
        rotas = [Rota.query.filter_by(rota_id=rota_id).first() for rota_id in distinct_rota_ids if Rota.query.filter_by(rota_id=rota_id).first()]
    return render_template('rotas_list.html', rotas=rotas)

@rota_bp.route('/rota/edit/<int:rota_id>', methods=['GET', 'POST'])
@login_required
def edit_rota(rota_id):
    rotas = Rota.query.filter_by(rota_id=rota_id).order_by(Rota.date).all()
    if not rotas:
        flash("No rota found for the given ID.", "danger")
        return redirect(url_for('rota.list_rotas'))
    forms = [EditRotaForm(obj=rota) for rota in rotas]
    if request.method == "POST":
        try:
            all_valid = True
            for form in forms:
                if not form.validate():
                    all_valid = False
                    for field, errors in form.errors.items():
                        for error in errors:
                            flash(f"Error in {field}: {error}", "error")
            if all_valid:
                for form, rota in zip(forms, rotas):
                    rota.shift_8_5 = form.shift_8_5.data
                    rota.shift_5_8 = form.shift_5_8.data
                    rota.shift_8_8 = form.shift_8_8.data
                    rota.night_off = form.night_off.data
                db.session.commit()
                flash("Rota updated successfully", "success")
                return redirect(url_for('rota.rota_detail', rota_id=rota_id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating rota: {str(e)}", "error")
    return render_template('edit_rota.html', forms=forms)