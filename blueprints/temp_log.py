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
API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
LOCATION = 'kombewa'

def fetch_temperature():
    """Fetch current temperature from the weather API with error handling."""
    try:
        url = f'http://api.openweathermap.org/data/2.5/weather?lat=-0.10345&lon=34.51792&appid={API_KEY}&units=metric'
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data['main']['temp']
        else:
            if current_app:
                current_app.logger.error(f"Failed to fetch temperature: {response.status_code}")
            return None
    except Exception as e:
        if current_app:
            current_app.logger.error(f"Exception while fetching temperature: {str(e)}")
        return None

def record_temperature(app, time_period, manual_temp=None, initials='SYS'):
    """Record the fetched or provided temperature into the database."""
    with app.app_context():
        temp = manual_temp if manual_temp is not None else fetch_temperature()
        if temp is not None:
            estimated_room_temp = temp - 5
            date_today = datetime.now().date()
            acceptable = 15.0 <= estimated_room_temp <= 29.0

            existing_log = TemperatureLog.query.filter_by(date=date_today, time=time_period).first()
            if existing_log:
                existing_log.recorded_temp = temp
                existing_log.estimated_room = estimated_room_temp
                existing_log.acceptable = acceptable
                existing_log.initials = initials
                db.session.commit()
                app.logger.info(f"Updated temperature log for {time_period} on {date_today}")
                return True

            temp_log = TemperatureLog(
                date=date_today,
                time=time_period,
                recorded_temp=temp,
                acceptable=acceptable,
                initials=initials,
                estimated_room=estimated_room_temp
            )
            db.session.add(temp_log)
            db.session.commit()
            app.logger.info(f"Recorded temperature: {temp}°C at {time_period}")
            return True
        return False

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
        hour=16,  # 2:00 PM EAT
        minute=27 # Run at 2:00pm
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

@temp_bp.route('/record_now', methods=['POST'])
@login_required
def record_now():
    from flask import flash, redirect, url_for
    time_period = request.form.get('time_period', 'AM')
    manual_temp = request.form.get('recorded_temp')
    initials = request.form.get('initials', 'USR').upper()[:3]
    temp_val = float(manual_temp) if manual_temp else None

    success = record_temperature(current_app._get_current_object(), time_period, manual_temp=temp_val, initials=initials)
    if success:
        flash(f"Temperature logged successfully for {time_period}.", "success")
    else:
        flash("Could not fetch temperature automatically. Please specify a manual value.", "danger")
    return redirect(url_for('temp_log.temp_log'))

