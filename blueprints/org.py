from flask import Blueprint, render_template, request, redirect, url_for, flash
from models.models import db, OrgDetails
from blueprints.forms import OrgForm

org_bp = Blueprint('org', __name__)

@org_bp.route('/add_org', methods=['GET', 'POST'])
def add_org():
    form = OrgForm()
    if form.validate_on_submit():
        name = form.name.data
        department = form.department.data
        new_org = OrgDetails(name=name, department=department)
        db.session.add(new_org)
        db.session.commit()
        flash('Organization added successfully!', 'success')
        return redirect(url_for('org.org_details'))
    return redirect(url_for('org.org_details'))

@org_bp.route('/org_details')
def org_details():
    org_details = OrgDetails.query.all()
    form = OrgForm()
    return render_template('org_details.html', org_details=org_details, form=form)

@org_bp.route('/edit_org/<int:org_id>', methods=['POST'])
def edit_org(org_id):
    org = OrgDetails.query.get_or_404(org_id)
    org.name = request.form['name']
    org.department = request.form['department']
    db.session.commit()
    flash('Organization details updated successfully!', 'success')
    return redirect(url_for('org.org_details'))

@org_bp.route('/delete_org/<int:org_id>', methods=['POST'])
def delete_org(org_id):
    org = OrgDetails.query.get_or_404(org_id)
    db.session.delete(org)
    db.session.commit()
    flash('Organization deleted successfully!', 'success')
    return redirect(url_for('org.org_details'))