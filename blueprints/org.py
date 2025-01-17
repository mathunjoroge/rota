from flask import Blueprint, render_template, request, redirect, url_for, flash
from blueprints.routes import login_required 
from models.models import db, OrgDetails
from blueprints.forms import OrgForm
from blueprints.members import requires_level

org_bp = Blueprint('org', __name__)

@org_bp.route('/add_org', methods=['GET', 'POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def add_org():
    form = OrgForm()
    if form.validate_on_submit():
        name = form.name.data
        department = form.department.data
        new_org = OrgDetails(name=name, department=department)
        db.session.add(new_org)
        db.session.commit()
        flash('Organization added successfully!', 'primary')
        return redirect(url_for('org.org_details'))
    return redirect(url_for('org.org_details'))

@org_bp.route('/org_details')
@login_required
def org_details():
    org_details = OrgDetails.query.all()
    form = OrgForm()
    return render_template('org_details.html', org_details=org_details, form=form)

@org_bp.route('/edit_org/<int:org_id>', methods=['POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def edit_org(org_id):
    org = OrgDetails.query.get_or_404(org_id)
    org.name = request.form['name']
    org.department = request.form['department']
    db.session.commit()
    flash('Organization details updated successfully!', 'success')
    return redirect(url_for('org.org_details'))

@org_bp.route('/delete_org/<int:org_id>', methods=['POST'])
@login_required
@requires_level(1)  # Only users with level 1 (Admin) can access this route
def delete_org(org_id):
    org = OrgDetails.query.get_or_404(org_id)
    db.session.delete(org)
    db.session.commit()
    flash('Organization deleted successfully!', 'danger')
    return redirect(url_for('org.org_details'))