from flask import Blueprint, current_app
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging

notifications_bp = Blueprint('notifications', __name__)

def send_email(to_email, subject, body_html):
    """
    Send an email via SMTP configured in .env.
    Falls back gracefully to logging if SMTP settings are not configured.
    """
    mail_server = os.getenv('MAIL_SERVER')
    mail_port = os.getenv('MAIL_PORT', 587)
    mail_user = os.getenv('MAIL_USERNAME')
    mail_pass = os.getenv('MAIL_PASSWORD')
    sender = os.getenv('MAIL_DEFAULT_SENDER', mail_user or 'noreply@magicrota.co.ke')

    if not mail_server or not mail_user:
        logging.info(f"[EMAIL MOCK] To: {to_email} | Subject: {subject} | Body: {body_html[:100]}...")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to_email
        msg.attach(MIMEText(body_html, 'html'))

        with smtplib.SMTP(mail_server, int(mail_port)) as server:
            server.starttls()
            server.login(mail_user, mail_pass)
            server.sendmail(sender, [to_email], msg.as_string())
        logging.info(f"Email successfully sent to {to_email}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {str(e)}")
        return False

def notify_rota_published(rota_id):
    """
    Send emails to all department members with their published shifts for this rota.
    """
    from models.models import Rota, Team, User, db
    rotas = Rota.query.filter_by(rota_id=rota_id).all()
    if not rotas:
        return

    dept_id = rotas[0].department_id
    members = Team.query.filter_by(department_id=dept_id).all()

    for m in members:
        if not m.email:
            # Check matching user email if member email is not directly set
            first_name = m.name.split()[0].lower()
            user = User.query.filter(User.username.ilike(f'%{first_name}%')).first()
            email = user.email if user else None
        else:
            email = m.email

        if not email:
            continue

        # Build schedule HTML table for member
        rows_html = ""
        for r in rotas:
            shifts_assigned = []
            if m.name in (r.shift_8_5 or ''): shifts_assigned.append('Morning (8 AM - 5 PM)')
            if m.name in (r.shift_5_8 or ''): shifts_assigned.append('Evening (5 PM - 8 PM)')
            if m.name in (r.shift_8_8 or ''): shifts_assigned.append('Night (8 PM - 8 AM)')
            if m.name in (r.night_off or ''): shifts_assigned.append('Night Off 💤')

            shift_str = ", ".join(shifts_assigned) if shifts_assigned else 'Day Off / Unassigned'
            rows_html += f"<tr><td style='padding:6px;border:1px solid #ccc;'>{r.week_range}</td><td style='padding:6px;border:1px solid #ccc;'>{shift_str}</td></tr>"

        subject = f"🏥 New Duty Rota Published for {r.department.name if r.department else 'Your Department'}"
        body_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #eee; borderRadius: 8px;">
            <h2 style="color: #0d6efd;">🏥 New Duty Rota Schedule</h2>
            <p>Hello <strong>{m.name}</strong>,</p>
            <p>Your work schedule for the upcoming period has been published:</p>
            <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                <thead>
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 8px; border: 1px solid #ccc; text-align: left;">Week Range</th>
                        <th style="padding: 8px; border: 1px solid #ccc; text-align: left;">Assigned Shift</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            <p style="margin-top: 20px;">View or request shift swaps via the <a href="http://127.0.0.1:5000/swaps">Rota Management Portal</a>.</p>
            <hr style="border: none; border-top: 1px solid #eee;">
            <p style="font-size: 11px; color: #888;">Magic Rota Hospital Management &copy;</p>
        </div>
        """
        send_email(email, subject, body_html)
