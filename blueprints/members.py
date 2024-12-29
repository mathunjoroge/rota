from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from models.models import db, Team

members_bp = Blueprint('members', __name__)

@members_bp.route('/members', methods=['GET', 'POST'])
def manage_members():
    if request.method == 'POST':
        name = request.form['name']
        if name:
            member = Team(name=name)
            db.session.add(member)
            db.session.commit()
        return redirect(url_for('members.manage_members'))  # Updated reference
    
    teams = Team.query.all()
    return render_template('members.html', teams=teams)

@members_bp.route('/edit_member/<int:member_id>', methods=['GET', 'POST'])
def edit_member(member_id):
    member = Team.query.get_or_404(member_id)
    if request.method == 'POST':
        new_name = request.form['name']
        if new_name:
            member.name = new_name
            db.session.commit()
            if request.is_json:
                return jsonify(status='success')
            return redirect(url_for('members.manage_members'))  # Updated reference
    if request.is_json:
        return jsonify(name=member.name)
    return render_template('edit_member.html', member=member)

@members_bp.route('/delete_member/<int:member_id>', methods=['POST'])
def delete_member(member_id):
    member = Team.query.get_or_404(member_id)
    db.session.delete(member)
    db.session.commit()
    return redirect(url_for('members.manage_members'))  # Updated reference