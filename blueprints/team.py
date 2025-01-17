from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash
from models.models import Team, db,User
from blueprints.routes import login_required 
team_bp = Blueprint('team', __name__, url_prefix='/team')

@team_bp.route('/', methods=['GET', 'POST'])
@login_required
def manage_members():
    if request.method == 'POST':
        name = request.form['name']
        if name:
            member = Team(name=name)
            db.session.add(member)
            db.session.commit()
    teams = Team.query.all()
    return render_template('members.html', teams=teams)

@team_bp.route('/edit/<int:member_id>', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    member = Team.query.get_or_404(member_id)
    if request.method == 'POST':
        new_name = request.form['name']
        if new_name:
            member.name = new_name
            db.session.commit()
            if request.is_json:
                return jsonify(status='success')
            return redirect(url_for('team.manage_members'))
    if request.is_json:
        return jsonify(name=member.name)
    return render_template('edit_member.html', member=member)

@team_bp.route('/delete/<int:member_id>', methods=['POST'])
@login_required
def delete_member(member_id):
    member = Team.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
    return redirect(url_for('team.manage_members'))
