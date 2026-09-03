from flask import Blueprint, render_template, request, current_app, send_file, make_response, Response
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

# ============================================================
# PHARMACY TEMPERATURE COMPLIANCE SETTINGS
# Per WHO Technical Report Series No. 961 (Annex 9) and
# Kenya Pharmacy and Poisons Board (PPB) storage guidelines.
# ============================================================
LOCATION = 'kisumu'
# Kisumu, Kenya coordinates
LATITUDE = -0.0917
LONGITUDE = 34.7680

# Indoor offset: estimated room temp = outdoor temp - this value
INDOOR_OFFSET = 5.0

# WHO / PPB pharmacy room storage thresholds (°C)
PHARMACY_TEMP_MIN = 15.0   # Below this → CRITICAL: too cold
PHARMACY_TEMP_MAX = 25.0   # Above this → WARNING / CRITICAL
PHARMACY_WARN_MAX = 30.0   # Above this → CRITICAL DANGER

def classify_temperature(room_temp):
    """
    Classify a room temperature reading for pharmacy compliance.
    Returns (acceptable: bool, status: str, severity: str)
      - severity: 'ok', 'warning', 'critical'
    """
    if room_temp is None:
        return False, 'No Reading', 'critical'
    if room_temp < PHARMACY_TEMP_MIN:
        return False, f'TOO COLD ({room_temp:.1f}°C < {PHARMACY_TEMP_MIN}°C)', 'critical'
    if room_temp > PHARMACY_WARN_MAX:
        return False, f'DANGER ({room_temp:.1f}°C > {PHARMACY_WARN_MAX}°C)', 'critical'
    if room_temp > PHARMACY_TEMP_MAX:
        return False, f'ABOVE RANGE ({room_temp:.1f}°C > {PHARMACY_TEMP_MAX}°C)', 'warning'
    return True, f'OK ({room_temp:.1f}°C)', 'ok'


def fetch_temperature():
    """Fetch current outdoor temperature for Kisumu from OpenWeather API."""
    try:
        url = (
            f'http://api.openweathermap.org/data/2.5/weather'
            f'?lat={LATITUDE}&lon={LONGITUDE}'
            f'&appid={API_KEY}&units=metric'
        )
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data['main']['temp']
        else:
            if current_app:
                current_app.logger.error(f"OpenWeather API error {response.status_code} for {LOCATION}")
            return None
    except Exception as e:
        if current_app:
            current_app.logger.error(f"Exception fetching temperature: {str(e)}")
        return None


def record_temperature(app, time_period, manual_temp=None, initials='SYS'):
    """Record the fetched or manually-provided temperature into the database."""
    with app.app_context():
        temp = manual_temp if manual_temp is not None else fetch_temperature()
        if temp is not None:
            estimated_room_temp = round(temp - INDOOR_OFFSET, 2)
            date_today = datetime.now().date()
            acceptable, _, _ = classify_temperature(estimated_room_temp)

            existing_log = TemperatureLog.query.filter_by(date=date_today, time=time_period).first()
            if existing_log:
                existing_log.recorded_temp = temp
                existing_log.estimated_room = estimated_room_temp
                existing_log.acceptable = acceptable
                existing_log.initials = initials
                db.session.commit()
                app.logger.info(f"Updated temperature log for {time_period} on {date_today}: {estimated_room_temp}°C room")
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
            app.logger.info(f"Recorded temperature: {temp}°C outdoor, {estimated_room_temp}°C room at {time_period}")
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
        hour=8,   # 8:00 AM EAT
        minute=0
    )
    scheduler.add_job(
        id='record_temp_pm',
        func=lambda: record_temperature(app, 'PM'),
        trigger='cron',
        hour=14,  # 2:00 PM EAT
        minute=0
    )
    scheduler.start()


@temp_bp.route('/temp_log')
@login_required
def temp_log():
    """Render pharmacy temperature logs with compliance warnings."""
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
        TemperatureLog.date.desc(),
        TemperatureLog.time.asc()
    ).all()

    # Group logs by date
    grouped_logs = defaultdict(lambda: {'AM': None, 'PM': None})
    for log in temperature_logs:
        grouped_logs[log.date][log.time] = log

    # Count recent excursions (last 7 days)
    from datetime import timedelta
    cutoff = datetime.now().date() - timedelta(days=7)
    recent_excursions = TemperatureLog.query.filter(
        TemperatureLog.date >= cutoff,
        TemperatureLog.acceptable == False
    ).count()

    return render_template(
        'temp_log.html',
        grouped_logs=grouped_logs,
        recent_excursions=recent_excursions,
        temp_min=PHARMACY_TEMP_MIN,
        temp_max=PHARMACY_TEMP_MAX,
        warn_max=PHARMACY_WARN_MAX,
        location=LOCATION.title()
    )


@temp_bp.route('/export_logs', methods=['GET', 'POST'])
@login_required
def export_logs():
    """Export temperature logs to PDF (supports GET for instant 1-click export, or POST for date-range filter)."""
    start_date = None
    end_date = None

    if request.method == 'POST':
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
    else:
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            start_date = None
            end_date = None

    query = db.session.query(
        TemperatureLog.date,
        TemperatureLog.time,
        TemperatureLog.recorded_temp,
        TemperatureLog.acceptable,
        TemperatureLog.initials,
        TemperatureLog.estimated_room
    ).distinct(
        TemperatureLog.date,
        TemperatureLog.time
    )

    if start_date and end_date:
        query = query.filter(TemperatureLog.date >= start_date, TemperatureLog.date <= end_date)

    temperature_logs = query.order_by(
        TemperatureLog.date.asc(),
        TemperatureLog.time.asc()
    ).all()

    if not start_date or not end_date:
        dates = [log.date for log in temperature_logs if log.date]
        start_date = min(dates) if dates else datetime.now().date()
        end_date = max(dates) if dates else datetime.now().date()

    grouped_logs = defaultdict(lambda: {'AM': None, 'PM': None})
    for log in temperature_logs:
        grouped_logs[log.date][log.time] = log

    org_details = OrgDetails.query.all()

    rendered_html = render_template(
        'temp_log_pdf.html',
        grouped_logs=grouped_logs,
        start_date=start_date,
        end_date=end_date,
        org_details=org_details,
        temp_min=PHARMACY_TEMP_MIN,
        temp_max=PHARMACY_TEMP_MAX
    )

    def fetch_resources(uri, rel):
        if uri.startswith('/static/'):
            return os.path.join(current_app.root_path, uri.lstrip('/'))
        if 'static/' in uri:
            return os.path.join(current_app.root_path, 'static', uri.split('static/')[-1])
        return os.path.join(current_app.root_path, uri.lstrip('/'))

    pdf = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.StringIO(rendered_html), dest=pdf, link_callback=fetch_resources)

    if pisa_status.err:
        return "Error creating PDF", 500

    pdf.seek(0)
    filename = f"pharmacy_temp_log_{start_date}_to_{end_date}.pdf"
    return Response(
        pdf.getvalue(),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


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
