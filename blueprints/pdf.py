from flask import Blueprint, render_template, request, redirect, url_for, Response
from datetime import date, datetime
from io import BytesIO
from logic.leave_logic import save_leave_logic, get_leaves_on_date, delete_leave_logic, edit_leave_logic
from blueprints.routes import login_required
from models.models import Leave, Rota, OrgDetails
from xhtml2pdf import pisa
import logging

# Setup logging
logging.basicConfig(level=logging.ERROR)

# Blueprints
leave_bp = Blueprint('leave', __name__)
pdf_bp = Blueprint('pdf', __name__)

# Utility function to calculate start and end dates
def calculate_date_range(rotas):
    if not rotas:
        return None, None
    try:
        start_date = min(datetime.strptime(rota.week_range.split(' - ')[0], '%d/%m/%Y') for rota in rotas)
        end_date = max(datetime.strptime(rota.week_range.split(' - ')[1], '%d/%m/%Y') for rota in rotas)
        return start_date, end_date
    except Exception as e:
        logging.error(f"Error calculating date range: {e}")
        return None, None

# Leave routes
@leave_bp.route('/save_leave/<int:member_id>', methods=['POST'])
@login_required
def save_leave(member_id):
    return save_leave_logic(member_id, request.form)

@leave_bp.route('/on_leave')
@login_required
def on_leave():
    leaves = Leave.query.all()
    current_date = date.today()
    return render_template('on_leave.html', leaves=leaves, current_date=current_date)

@leave_bp.route('/delete_leave/<int:leave_id>', methods=['POST'])
@login_required
def delete_leave(leave_id):
    return delete_leave_logic(leave_id)

@leave_bp.route('/edit_leave/<int:leave_id>', methods=['GET', 'POST'])
@login_required
def edit_leave(leave_id):
    if request.method == 'POST':
        return edit_leave_logic(leave_id, request.form)
    leave = Leave.query.get_or_404(leave_id)
    return render_template('edit_leave.html', leave=leave)

# PDF generation routes
@pdf_bp.route('/export_pdf')
@login_required
def export_pdf():
    try:
        rotas = Rota.query.all()
        org_details = OrgDetails.query.all()
        start_date, end_date = calculate_date_range(rotas)
        html = render_template('export_pdf.html', rotas=rotas, org_details=org_details, start_date=start_date, end_date=end_date)
        pdf = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf)
        if pisa_status.err:
            logging.error("Error generating PDF for rotas")
            return "Error generating PDF", 500
        pdf.seek(0)
        return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=rota.pdf'})
    except Exception as e:
        logging.error(f"Error in export_pdf: {e}")
        return "Error generating PDF", 500

@pdf_bp.route('/leave_rota_pdf')
@login_required
def leave_rota_pdf():
    try:
        rotas = Rota.query.all()
        org_details = OrgDetails.query.all()
        leaves = Leave.query.all()  # Fetch leaves data
        start_date, end_date = calculate_date_range(rotas)
        
        # Get current date and format it
        current_date = datetime.now().strftime('%B %d, %Y')  # Format: Month Day, Year
        
        # Render HTML with the current date passed in the context
        html = render_template('leave_rota_pdf.html', leaves=leaves, org_details=org_details, 
                               start_date=start_date, end_date=end_date, current_date=current_date)
        
        pdf = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf)
        
        if pisa_status.err:
            logging.error("Error generating PDF for leave rota")
            return "Error generating PDF", 500
        
        pdf.seek(0)
        return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=leave_rota.pdf'})
    except Exception as e:
        logging.error(f"Error in leave_rota_pdf: {e}")
        return "Error generating PDF", 500
