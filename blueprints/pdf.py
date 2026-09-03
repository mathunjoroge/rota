from flask import Blueprint, render_template, Response
from datetime import date, datetime, timedelta
from io import BytesIO
from blueprints.routes import login_required
from models.models import Rota, OrgDetails, Leave
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
    start_dates, end_dates = [], []
    for rota in rotas:
        if not rota.week_range:
            continue
        parts = rota.week_range.split(' - ') if ' - ' in rota.week_range else rota.week_range.split(' → ')
        if len(parts) < 2:
            continue
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
            try:
                s_dt = datetime.strptime(parts[0].strip(), fmt)
                e_dt = datetime.strptime(parts[1].strip(), fmt)
                start_dates.append(s_dt)
                end_dates.append(e_dt)
                break
            except ValueError:
                continue
    if start_dates and end_dates:
        return min(start_dates), max(end_dates)
    return None, None

import os
from flask import current_app

def fetch_resources(uri, rel):
    if uri.startswith('/static/'):
        return os.path.join(current_app.root_path, uri.lstrip('/'))
    if 'static/' in uri:
        return os.path.join(current_app.root_path, 'static', uri.split('static/')[-1])
    return os.path.join(current_app.root_path, uri.lstrip('/'))

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
        pisa_status = pisa.CreatePDF(html, dest=pdf, link_callback=fetch_resources)
        if pisa_status.err:
            logging.error("Error generating PDF for rotas")
            return "Error generating PDF", 500
        pdf.seek(0)
        return Response(pdf.getvalue(), mimetype='application/pdf', headers={'Content-Disposition': 'attachment; filename="rota.pdf"'})
    except Exception as e:
        logging.error(f"Error in export_pdf: {e}")
        return "Error generating PDF", 500

def count_weekdays(start, end):
    """Calculates the number of weekdays between two dates."""
    if not start or not end:
        return 0
    
    current = start if isinstance(start, datetime) else datetime.combine(start, datetime.min.time())
    end_dt = end if isinstance(end, datetime) else datetime.combine(end, datetime.min.time())

    weekdays = 0
    while current <= end_dt:
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
        leaves = Leave.query.all()
        start_date, end_date = calculate_date_range(rotas)
        
        current_date = datetime.now().strftime('%B %d, %Y')
        
        html = render_template('leave_rota_pdf.html', leaves=leaves, org_details=org_details, 
                               start_date=start_date, end_date=end_date, 
                               current_date=current_date, count_weekdays=count_weekdays)
        
        pdf = BytesIO()
        pisa_status = pisa.CreatePDF(html, dest=pdf, link_callback=fetch_resources)
        
        if pisa_status.err:
            logging.error("Error generating PDF for leave rota")
            return "Error generating PDF", 500
        
        pdf.seek(0)
        return Response(pdf.getvalue(), mimetype='application/pdf', headers={'Content-Disposition': 'attachment; filename="leave_rota.pdf"'})
    except Exception as e:
        logging.error(f"Error in leave_rota_pdf: {e}")
        return "Error generating PDF", 500