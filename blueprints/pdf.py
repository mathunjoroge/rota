from flask import Blueprint, render_template, Response
from io import BytesIO
from models.models import Rota, OrgDetails
from xhtml2pdf import pisa
from datetime import datetime

pdf_bp = Blueprint('pdf', __name__)

@pdf_bp.route('/export_pdf')
def export_pdf():
    rotas = Rota.query.all()
    org_details = OrgDetails.query.all()  # Fetch organization details

    # Find the start and end dates from the rota entries
    if rotas:
        start_date = min([datetime.strptime(rota.week_range.split(' - ')[0], '%d/%m/%Y') for rota in rotas])
        end_date = max([datetime.strptime(rota.week_range.split(' - ')[1], '%d/%m/%Y') for rota in rotas])
    else:
        start_date = end_date = None

    html = render_template('export_pdf.html', rotas=rotas, org_details=org_details, start_date=start_date, end_date=end_date)
    pdf = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=pdf)
    
    if pisa_status.err:
        return "Error generating PDF", 500

    pdf.seek(0)
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': 'attachment;filename=rota.pdf'})