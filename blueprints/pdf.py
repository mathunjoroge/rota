from flask import Blueprint, render_template, Response
from datetime import date, datetime, timedelta
from io import BytesIO
from blueprints.routes import login_required
from models.models import Rota, OrgDetails
from xhtml2pdf import pisa
import logging

# Setup logging
logging.basicConfig(level=logging.ERROR)

# Blueprints
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

def count_weekdays(start, end):
    """Calculates the number of weekdays between two dates."""
    if not start or not end:
        return 0
    
    # Convert dates to datetime objects if they are not already
    current = start if isinstance(start, datetime) else datetime.combine(start, datetime.min.time())
    end_dt = end if isinstance(end, datetime) else datetime.combine(end, datetime.min.time())

    weekdays = 0
    while current <= end_dt:
        # weekday() returns 0 for Monday and 6 for Sunday
        if current.weekday() < 5:
            weekdays += 1
        current += timedelta(days=1)
    return weekdays

@pdf_bp.route('/leave_rota_pdf')
@login_required
def leave_rota_pdf():
    try:
        rotas = Rota.query.all()
        org_details = OrgDetails.query.all()
        leaves = Leave.query.all()  # Fetch leaves data
        start_date, end_date = calculate_date_range(rotas)
        
        # Get current date and format it
        current_date = datetime.now().strftime('%B %d, %Y')
        
        # Render HTML with the new custom function passed to the template
        html = render_template('leave_rota_pdf.html', leaves=leaves, org_details=org_details, 
                               start_date=start_date, end_date=end_date, 
                               current_date=current_date, count_weekdays=count_weekdays)
        
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