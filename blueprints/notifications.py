from flask import Blueprint, render_template, current_app
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
import logging
from io import BytesIO

notifications_bp = Blueprint('notifications', __name__)


# ---------------------------------------------------------------------------
# Core send helpers
# ---------------------------------------------------------------------------

def _get_smtp_config():
    return {
        'server':   os.getenv('MAIL_SERVER'),
        'port':     int(os.getenv('MAIL_PORT', 587)),
        'user':     os.getenv('MAIL_USERNAME'),
        'password': os.getenv('MAIL_PASSWORD'),
        'sender':   os.getenv('MAIL_DEFAULT_SENDER',
                              os.getenv('MAIL_USERNAME') or 'noreply@magicrota.co.ke'),
    }


def send_email(to_email, subject, body_html):
    """
    Send a plain HTML email via SMTP configured in .env.
    Falls back gracefully to logging if SMTP settings are not configured.
    """
    cfg = _get_smtp_config()

    if not cfg['server'] or not cfg['user']:
        logging.info(f"[EMAIL MOCK] To: {to_email} | Subject: {subject} | Body: {body_html[:100]}...")
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = cfg['sender']
        msg['To']      = to_email
        msg.attach(MIMEText(body_html, 'html'))

        with smtplib.SMTP(cfg['server'], cfg['port']) as server:
            server.starttls()
            server.login(cfg['user'], cfg['password'])
            server.sendmail(cfg['sender'], [to_email], msg.as_string())
        logging.info(f"Email successfully sent to {to_email}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email to {to_email}: {str(e)}")
        return False


def send_email_with_attachment(to_email, subject, body_html, attachment_bytes,
                               attachment_filename, attachment_mime='application/pdf'):
    """
    Send an HTML email with a binary attachment (e.g. a PDF) via SMTP.
    Falls back to logging if SMTP is not configured.
    """
    cfg = _get_smtp_config()

    if not cfg['server'] or not cfg['user']:
        logging.info(
            f"[EMAIL MOCK] To: {to_email} | Subject: {subject} "
            f"| Attachment: {attachment_filename} ({len(attachment_bytes)} bytes)"
        )
        return True

    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From']    = cfg['sender']
        msg['To']      = to_email

        # HTML body
        msg.attach(MIMEText(body_html, 'html'))

        # PDF attachment
        part = MIMEApplication(attachment_bytes, Name=attachment_filename)
        part['Content-Disposition'] = f'attachment; filename="{attachment_filename}"'
        msg.attach(part)

        with smtplib.SMTP(cfg['server'], cfg['port']) as server:
            server.starttls()
            server.login(cfg['user'], cfg['password'])
            server.sendmail(cfg['sender'], [to_email], msg.as_string())
        logging.info(f"Email with attachment sent to {to_email}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email with attachment to {to_email}: {str(e)}")
        return False


# ---------------------------------------------------------------------------
# Email body builders
# ---------------------------------------------------------------------------

def _email_wrapper(inner_html, footer_note="Magic Rota Hospital Management"):
    """Wrap content in a consistent branded email shell."""
    return f"""
    <div style="font-family: Arial, sans-serif; max-width: 620px; margin: auto;
                padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px;
                background: #ffffff;">
        <div style="border-bottom: 3px solid #0d6efd; padding-bottom: 12px; margin-bottom: 20px;">
            <h2 style="color: #0d6efd; margin: 0;">🏥 Magic Rota</h2>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 13px;">
                Hospital Workforce Management
            </p>
        </div>
        {inner_html}
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin-top: 28px;">
        <p style="font-size: 11px; color: #94a3b8; text-align: center; margin-top: 10px;">
            {footer_note} &copy; {__import__('datetime').date.today().year}
        </p>
    </div>
    """


def _build_leave_approval_html(member_name, leave_type, start_date, end_date,
                                days_num, review_notes=None):
    notes_html = (
        f"<p style='background:#f0fdf4;border-left:4px solid #22c55e;"
        f"padding:10px 14px;border-radius:4px;'>"
        f"<strong>Manager Note:</strong> {review_notes}</p>"
    ) if review_notes else ""
    inner = f"""
        <h3 style="color: #16a34a;">✅ Leave Application Approved</h3>
        <p>Hello <strong>{member_name}</strong>,</p>
        <p>Great news! Your <strong>{leave_type}</strong> leave request has been
           <span style="color:#16a34a;font-weight:bold;">APPROVED</span>.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr style="background:#f8fafc;">
                <th style="padding:8px 12px;border:1px solid #e2e8f0;text-align:left;">Detail</th>
                <th style="padding:8px 12px;border:1px solid #e2e8f0;text-align:left;">Value</th>
            </tr>
            <tr>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">Leave Type</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{leave_type}</td>
            </tr>
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">Start Date</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{start_date.strftime('%d %B %Y')}</td>
            </tr>
            <tr>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">End Date</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{end_date.strftime('%d %B %Y')}</td>
            </tr>
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">Working Days</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;font-weight:bold;">{days_num} day(s)</td>
            </tr>
        </table>
        {notes_html}
        <p>Your shift schedule has been updated automatically. You can view your
           leave record via the
           <a href="{os.getenv('APP_BASE_URL', 'http://localhost:5000')}/on_leave"
              style="color:#0d6efd;">Rota Portal</a>.</p>
    """
    return _email_wrapper(inner)


def _build_leave_rejection_html(member_name, leave_type, start_date, end_date, review_notes):
    notes_html = (
        f"<p style='background:#fef2f2;border-left:4px solid #ef4444;"
        f"padding:10px 14px;border-radius:4px;'>"
        f"<strong>Manager Note:</strong> {review_notes or 'No additional notes provided.'}</p>"
    )
    inner = f"""
        <h3 style="color: #dc2626;">❌ Leave Application Not Approved</h3>
        <p>Hello <strong>{member_name}</strong>,</p>
        <p>Unfortunately, your <strong>{leave_type}</strong> leave request has been
           <span style="color:#dc2626;font-weight:bold;">DECLINED</span>.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr style="background:#f8fafc;">
                <th style="padding:8px 12px;border:1px solid #e2e8f0;text-align:left;">Detail</th>
                <th style="padding:8px 12px;border:1px solid #e2e8f0;text-align:left;">Value</th>
            </tr>
            <tr>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">Leave Type</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">{leave_type}</td>
            </tr>
            <tr style="background:#f8fafc;">
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">Requested Period</td>
                <td style="padding:8px 12px;border:1px solid #e2e8f0;">
                    {start_date.strftime('%d %B %Y')} – {end_date.strftime('%d %B %Y')}
                </td>
            </tr>
        </table>
        {notes_html}
        <p>If you have questions, please speak to your department manager or submit a
           revised request via the
           <a href="{os.getenv('APP_BASE_URL', 'http://localhost:5000')}/on_leave"
              style="color:#0d6efd;">Rota Portal</a>.</p>
    """
    return _email_wrapper(inner)


def _build_rota_published_html(member_name, dept_name, rows_html, rota_id):
    inner = f"""
        <h3 style="color: #0d6efd;">📋 New Duty Rota Published</h3>
        <p>Hello <strong>{member_name}</strong>,</p>
        <p>Your work schedule for <strong>{dept_name}</strong> has been published.
           Your assigned shifts are listed below. A full department rota PDF is
           attached for your records.</p>
        <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <thead>
                <tr style="background:#f0f9ff;">
                    <th style="padding:8px 12px;border:1px solid #e2e8f0;text-align:left;">Week</th>
                    <th style="padding:8px 12px;border:1px solid #e2e8f0;text-align:left;">Your Assigned Shift</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
        <p>View or request shift swaps via the
           <a href="{os.getenv('APP_BASE_URL', 'http://localhost:5000')}/swaps"
              style="color:#0d6efd;">Rota Management Portal</a>.</p>
    """
    return _email_wrapper(inner)


# ---------------------------------------------------------------------------
# High-level notification functions
# ---------------------------------------------------------------------------

def notify_rota_published(rota_id):
    """
    Send emails to all department members with their published shifts for this rota.
    Each email includes the full rota as a PDF attachment.
    """
    from models.models import Rota, Team, User, OrgDetails
    from xhtml2pdf import pisa

    rotas = Rota.query.filter_by(rota_id=rota_id).all()
    if not rotas:
        return

    dept_id   = rotas[0].department_id
    members   = Team.query.filter_by(department_id=dept_id).all()
    dept_name = rotas[0].department.name if rotas[0].department else "Your Department"

    # --- Generate the rota PDF once, attach to every member's email ---
    pdf_bytes = None
    try:
        org_details = OrgDetails.query.all()
        from datetime import datetime, timedelta

        start_dates, end_dates = [], []
        for r in rotas:
            if not r.week_range:
                continue
            parts = r.week_range.split(' - ') if ' - ' in r.week_range else r.week_range.split(' → ')
            if len(parts) < 2:
                continue
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    start_dates.append(datetime.strptime(parts[0].strip(), fmt))
                    end_dates.append(datetime.strptime(parts[1].strip(), fmt))
                    break
                except ValueError:
                    continue
        start_date = min(start_dates) if start_dates else None
        end_date   = max(end_dates)   if end_dates   else None

        html_pdf = render_template(
            'export_pdf.html',
            rotas=rotas,
            org_details=org_details,
            start_date=start_date,
            end_date=end_date
        )
        buf = BytesIO()
        status = pisa.CreatePDF(html_pdf, dest=buf)
        if not status.err:
            pdf_bytes = buf.getvalue()
        else:
            logging.error(f"[notify_rota_published] PDF generation failed for rota_id={rota_id}")
    except Exception as e:
        logging.error(f"[notify_rota_published] PDF error: {e}")

    # --- Send one email per member ---
    for m in members:
        # Resolve email
        if not m.email:
            first_name = m.name.split()[0].lower()
            user = User.query.filter(User.username.ilike(f'%{first_name}%')).first()
            email = user.email if user else None
        else:
            email = m.email

        if not email:
            continue

        # Build personal schedule rows
        rows_html = ""
        for r in rotas:
            shifts_assigned = []
            if m.name in (r.shift_8_5 or ''):   shifts_assigned.append('Morning (8 AM – 5 PM)')
            if m.name in (r.shift_5_8 or ''):   shifts_assigned.append('Evening (5 PM – 8 PM)')
            if m.name in (r.shift_8_8 or ''):   shifts_assigned.append('Night (8 PM – 8 AM)')
            if m.name in (r.night_off or ''):   shifts_assigned.append('Night Off 💤')
            shift_str = ", ".join(shifts_assigned) if shifts_assigned else 'Day Off / Unassigned'
            bg = "background:#f8fafc;" if rotas.index(r) % 2 == 0 else ""
            rows_html += (
                f"<tr style='{bg}'>"
                f"<td style='padding:8px 12px;border:1px solid #e2e8f0;'>{r.week_range}</td>"
                f"<td style='padding:8px 12px;border:1px solid #e2e8f0;'>{shift_str}</td>"
                f"</tr>"
            )

        subject   = f"📋 New Duty Rota Published — {dept_name}"
        body_html = _build_rota_published_html(m.name, dept_name, rows_html, rota_id)

        if pdf_bytes:
            send_email_with_attachment(
                email, subject, body_html,
                pdf_bytes, f"rota_{rota_id}.pdf"
            )
        else:
            send_email(email, subject, body_html)


def notify_leave_approved(req):
    """
    Send an email to the staff member whose leave has been approved.
    `req` is a LeaveRequest model instance (already committed/approved).
    """
    from logic.leave_logic import weekdays_between

    if not req.member.email:
        return
    days_num  = weekdays_between(req.start_date, req.end_date)
    subject   = f"✅ Leave Approved — {req.leave_type} ({req.start_date} to {req.end_date})"
    body_html = _build_leave_approval_html(
        req.member.name, req.leave_type,
        req.start_date, req.end_date,
        days_num, review_notes=req.review_notes
    )
    send_email(req.member.email, subject, body_html)


def notify_leave_rejected(req):
    """
    Send an email to the staff member whose leave has been rejected.
    `req` is a LeaveRequest model instance (already committed/rejected).
    """
    if not req.member.email:
        return
    subject   = f"❌ Leave Not Approved — {req.leave_type} ({req.start_date} to {req.end_date})"
    body_html = _build_leave_rejection_html(
        req.member.name, req.leave_type,
        req.start_date, req.end_date,
        req.review_notes
    )
    send_email(req.member.email, subject, body_html)
