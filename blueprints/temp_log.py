from flask import Blueprint, render_template, request, current_app, send_file, make_response
from flask_login import login_required
from flask_apscheduler import APScheduler
from models.models import TemperatureLog, db, OrgDetails
import requests
from datetime import datetime
import os
import io
from xhtml2pdf import pisa
from collections import defaultdict

# Initialize Blueprint
temp_bp = Blueprint('temp_log', __name__)

# Load configuration from environment
API_KEY = os.getenv('OPENWEATHERMAP_API_KEY', '6d6bac6176e6352bf13dfee489537206')
LOCATION = 'kombewa'

def fetch_temperature():
    """Fetch current temperature from the weather API."""
    url = f'http://api.openweathermap.org/data/2.5/weather?lat=-0.10345&lon=34.51792&appid={API_KEY}&units=metric'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data['main']['temp']
    else:
        current_app.logger.error(f"Failed to fetch temperature: {response.json().get('message', 'Unknown error')}")
        return None

def record_temperature(app, time_period):
    """Record the fetched temperature into the database, adjusted for indoor conditions."""
    with app.app_context():
        temp = fetch_temperature()
        if temp is not None:
            # Estimate indoor temperature by subtracting 5°C from the outdoor temperature
            estimated_room_temp = temp - 5
            date_today = datetime.now().date()
            acceptable = 15.0 <= estimated_room_temp <= 29.0
            initials = 'SYS'

            # Check if there's already an entry for the same date and time period
            existing_log = TemperatureLog.query.filter_by(date=date_today, time=time_period).first()
            if existing_log:
                app.logger.warning(f"Temperature log already exists for {time_period} on {date_today}")
                return

            # Create and save temperature log
            temp_log = TemperatureLog(
                date=date_today,
                time=time_period,
                recorded_temp=temp,
                acceptable=acceptable,
                initials=initials,
                estimated_room=estimated_room_temp  # Save estimated room temperature
            )
            db.session.add(temp_log)
            db.session.commit()
            app.logger.info(f"Recorded temperature: {temp}°C at {time_period} (Estimated Room: {estimated_room_temp}°C)")

def schedule_tasks(app):
    """Schedule periodic temperature recording tasks."""
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.add_job(
        id='record_temp_am',
        func=lambda: record_temperature(app, 'AM'),
        trigger='cron',
        hour=8,  # 8:00 AM EAT
        minute=0
    )
    scheduler.add_job(
        id='record_temp_pm',
        func=lambda: record_temperature(app, 'PM'),
        trigger='cron',
        hour=14,  # 2:00 PM EAT
        minute=0  # Run at 2:00pm
    )
    scheduler.add_job(
        id='record_temp_test',
        func=lambda: record_temperature(app, 'TEST'),
        trigger='date',
        run_date=datetime.now().replace(second=0, microsecond=0)  # Run immediately for testing
    )
    scheduler.start()

@temp_bp.route('/temp_log')
@login_required
def temp_log():
    """Render temperature logs in a template, grouped by date."""
    # Query distinct temperature logs
    temperature_logs = db.session.query(
        TemperatureLog.date,
        TemperatureLog.time,
        TemperatureLog.recorded_temp,
        TemperatureLog.acceptable,
        TemperatureLog.initials,
        TemperatureLog.estimated_room
    ).distinct(
        TemperatureLog.date,
        TemperatureLog.time
    ).order_by(
        TemperatureLog.date.asc(),
        TemperatureLog.time.asc()
    ).all()

    # Group logs by date
    grouped_logs = defaultdict(lambda: {'AM': None, 'PM': None})

    for log in temperature_logs:
        grouped_logs[log.date][log.time] = log

    return render_template('temp_log.html', grouped_logs=grouped_logs)

@temp_bp.route('/export_logs', methods=['GET', 'POST'])
@login_required
def export_logs():
    """Export distinct temperature logs between specified dates to PDF."""
    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        if not start_date or not end_date:
            return "Start date and end date are required", 400

        # Convert date strings to datetime objects
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return "Invalid date format. Please use YYYY-MM-DD.", 400

        # Query distinct temperature logs within the given date range
        temperature_logs = db.session.query(
            TemperatureLog.date,
            TemperatureLog.time,
            TemperatureLog.recorded_temp,
            TemperatureLog.acceptable,
            TemperatureLog.initials,
            TemperatureLog.estimated_room
        ).distinct(
            TemperatureLog.date,
            TemperatureLog.time
        ).filter(
            TemperatureLog.date >= start_date,
            TemperatureLog.date <= end_date
        ).order_by(
            TemperatureLog.date.asc(),
            TemperatureLog.time.asc()
        ).all()

        # Group logs by date and time (AM/PM)
        grouped_logs = defaultdict(lambda: {'AM': None, 'PM': None})

        for log in temperature_logs:
            grouped_logs[log.date][log.time] = log

        # Retrieve organizational details for the header
        org_details = OrgDetails.query.all()

        # Render the HTML template for PDF generation
        rendered_html = render_template(
            'temp_log_pdf.html',
            grouped_logs=grouped_logs,
            start_date=start_date,
            end_date=end_date,
            org_details=org_details
        )

        # Generate the PDF using xhtml2pdf
        pdf = io.BytesIO()
        pisa_status = pisa.CreatePDF(io.StringIO(rendered_html), dest=pdf)

        if pisa_status.err:
            return "Error creating PDF", 500

        pdf.seek(0)
        # Return the generated PDF file as an attachment
        return send_file(
            pdf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'temp_logs_{start_date}_to_{end_date}.pdf'
        )

    # If GET request, just render the temp_log page
    return render_template('temp_log.html')

