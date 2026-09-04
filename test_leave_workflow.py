import sys
from datetime import date, timedelta
from app import app
from models.models import db, Team, Leave, LeaveRequest, AuditLog, User, Department, init_db_departments
from logic.leave_logic import (
    apply_leave_logic, approve_leave_request_logic, reject_leave_request_logic,
    get_leave_balances, weekdays_between
)
from logic.rota_logic import filter_eligible_members

def run_leave_tests():
    print("=== STARTING ENTERPRISE LEAVE WORKFLOW TESTS ===")

    with app.test_request_context('/on_leave'):
        init_db_departments()
        dept = Department.query.first()

        # 1. Setup Test Team Member
        member = Team.query.filter_by(name="Test Leave Member").first()
        if not member:
            member = Team(
                name="Test Leave Member",
                department_id=dept.id if dept else None,
                phone="0711000999",
                email="test_leave@example.com",
                annual_leave_allowance=21
            )
            db.session.add(member)
            db.session.commit()

        # Clean old test data
        LeaveRequest.query.filter_by(member_id=member.id).delete()
        Leave.query.filter_by(member_id=member.id).delete()
        db.session.commit()

        # 2. Test Leave Application Submission
        start_d = date.today() + timedelta(days=7)
        end_d = start_d + timedelta(days=4)

        form_data = {
            'member_id': str(member.id),
            'leave_type': 'Annual Leave',
            'start_date': start_d.isoformat(),
            'end_date': end_d.isoformat(),
            'reason': 'Annual vacation getaway'
        }

        print("1. Submitting Leave Application...")
        apply_leave_logic(form_data)

        req = LeaveRequest.query.filter_by(member_id=member.id, status='pending').first()
        assert req is not None, "❌ Leave request was not saved in pending state!"
        assert req.leave_type == 'Annual Leave'
        assert req.days_requested() == 5
        print(f"   ✓ Pending LeaveRequest #{req.id} created successfully ({req.days_requested()} days).")

        # 3. Test Overlap Rejection on Pending
        print("2. Testing Overlapping Request Prevention...")
        apply_leave_logic(form_data) # Should warn and not duplicate
        pending_count = LeaveRequest.query.filter_by(member_id=member.id, status='pending').count()
        assert pending_count == 1, f"❌ Overlapping pending request was incorrectly allowed! Count: {pending_count}"
        print("   ✓ Duplicate/overlapping request successfully prevented.")

        # 4. Test Manager Approval Workflow
        admin_user = User.query.first()
        print("3. Approving Leave Application...")
        approve_leave_request_logic(req.id, admin_user)

        req_updated = LeaveRequest.query.get(req.id)
        assert req_updated.status == 'approved', f"❌ LeaveRequest status is {req_updated.status}, expected approved!"

        approved_leave = Leave.query.filter_by(member_id=member.id).first()
        assert approved_leave is not None, "❌ Active Leave record was not created upon approval!"
        print(f"   ✓ LeaveRequest #{req.id} APPROVED and active Leave record #{approved_leave.id} created.")

        # 5. Test Leave Balances Calculation
        print("4. Verifying Leave Allowances & Balances...")
        balances = get_leave_balances()
        member_bal = next((b for b in balances if b['member'].id == member.id), None)
        assert member_bal is not None, "❌ Member balance not found!"
        print(f"   ✓ {member.name}: Used = {member_bal['used']} days, Remaining = {member_bal['remaining']} / {member_bal['allowance']} days ({member_bal['pct_used']}% used).")

        # 6. Test Rota Solver Availability Filtering
        print("5. Verifying Rota Solver Availability Filter...")
        eligible = filter_eligible_members([member], start_d, end_d)
        assert member not in eligible, "❌ Staff on approved leave was NOT filtered out by Rota solver eligibility logic!"
        print("   ✓ Staff member on approved leave correctly excluded from solver availability pool.")

        # 7. Test Rejection Workflow
        start_d2 = date.today() + timedelta(days=30)
        end_d2 = start_d2 + timedelta(days=2)
        form_data2 = {
            'member_id': str(member.id),
            'leave_type': 'Study Leave',
            'start_date': start_d2.isoformat(),
            'end_date': end_d2.isoformat(),
            'reason': 'Exam revision week'
        }
        apply_leave_logic(form_data2)
        req2 = LeaveRequest.query.filter_by(member_id=member.id, status='pending').first()
        assert req2 is not None

        print("6. Rejecting Leave Application...")
        reject_leave_request_logic(req2.id, admin_user, {'review_notes': 'Insufficient coverage on department shift roster'})
        req2_updated = LeaveRequest.query.get(req2.id)
        assert req2_updated.status == 'rejected'
        assert req2_updated.review_notes == 'Insufficient coverage on department shift roster'
        print(f"   ✓ LeaveRequest #{req2.id} REJECTED with manager notes recorded.")

        # 8. Check Audit Trail Entries
        audit_logs = AuditLog.query.filter_by(entity_type='LeaveRequest').all()
        assert len(audit_logs) >= 2, "❌ Audit logs were not generated for leave requests!"
        print(f"   ✓ Audit log recorded {len(audit_logs)} compliance audit entries.")

        # Cleanup Test Member to leave exact default team intact
        LeaveRequest.query.filter_by(member_id=member.id).delete()
        Leave.query.filter_by(member_id=member.id).delete()
        Team.query.filter_by(id=member.id).delete()
        db.session.commit()
        print("   ✓ Cleaned up test member and temporary test records.")

    print("\n=== ALL LEAVE WORKFLOW TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_leave_tests()
