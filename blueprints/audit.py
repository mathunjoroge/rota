from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from models.models import db, AuditLog
from datetime import datetime
from functools import wraps

audit_bp = Blueprint('audit', __name__)


def log_audit(action, entity_type, entity_id=None, description=None, old_value=None, new_value=None):
    """
    Helper to write an immutable audit record.
    Call this from any blueprint that modifies data.
    """
    try:
        user_id = current_user.id if current_user.is_authenticated else None
        username = current_user.username if current_user.is_authenticated else 'system'
        ip = request.remote_addr if request else None
        entry = AuditLog(
            user_id=user_id,
            username=username,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,
            ip_address=ip,
            timestamp=datetime.utcnow()
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        import logging
        logging.getLogger(__name__).error(f"Failed to write audit log: {e}")


@audit_bp.route('/audit_log')
@login_required
def audit_log():
    """Paginated audit log — admin only."""
    from blueprints.members import requires_level
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    entity_filter = request.args.get('entity', '').strip()

    query = AuditLog.query.order_by(AuditLog.timestamp.desc())
    if search:
        query = query.filter(
            db.or_(
                AuditLog.username.ilike(f'%{search}%'),
                AuditLog.description.ilike(f'%{search}%'),
                AuditLog.action.ilike(f'%{search}%'),
            )
        )
    if entity_filter:
        query = query.filter(AuditLog.entity_type == entity_filter)

    logs = query.paginate(page=page, per_page=25, error_out=False)
    entity_types = db.session.query(AuditLog.entity_type).distinct().all()
    entity_types = [e[0] for e in entity_types]
    return render_template('audit_log.html', logs=logs, search=search,
                           entity_filter=entity_filter, entity_types=entity_types)
