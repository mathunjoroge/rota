from datetime import date, timedelta
from datetime import time
from app import app
from models.models import db, Department, Team, Shift, Rota, RotaAssignment, init_db_departments
from logic.rota_pulp import generate_rota_with_pulp

def run_department_rule_tests():
    print("=== STARTING HOSPITAL DEPARTMENT RULES & SHIFT COVERAGE TESTS ===")

    with app.test_request_context('/'):
        init_db_departments()
        
        # 1. Setup Test Hospital Department
        dept = Department.query.filter_by(code='ICU_TEST').first()
        if not dept:
            dept = Department(name='Intensive Care Unit Test', code='ICU_TEST', description='Test ICU Department')
            db.session.add(dept)
            db.session.commit()

        # Clean existing test shifts and members for ICU_TEST
        Shift.query.filter_by(department_id=dept.id).delete()
        Team.query.filter_by(department_id=dept.id).delete()
        db.session.commit()

        # 2. Add Department Shifts (Night requires MIN 2 nurses for ICU coverage)
        morning_shift = Shift(name='Morning 8-5', start_time=time(8, 0), end_time=time(17, 0), min_members=2, max_members=5, department_id=dept.id)
        evening_shift = Shift(name='Evening 5-8', start_time=time(17, 0), end_time=time(20, 0), min_members=1, max_members=2, department_id=dept.id)
        night_shift   = Shift(name='Night 8-8',   start_time=time(20, 0), end_time=time(8, 0),  min_members=2, max_members=2, department_id=dept.id)

        db.session.add_all([morning_shift, evening_shift, night_shift])
        db.session.commit()
        print("1. Department Shift bounds created (Night shift requires minimum 2 staff).")

        # 3. Add Staff Roster with Staff Levels & Exemptions
        staff_members = [
            Team(name="Dr. Head Admin", is_admin=1, role_title="Consultant Head", department_id=dept.id),
            Team(name="Nurse Senior Dave", is_admin=2, role_title="Charge Nurse", exempt_night=True, department_id=dept.id),
            Team(name="Nurse Mary", is_admin=0, role_title="Staff Nurse", exempt_night=True, department_id=dept.id),
            Team(name="Nurse Alice", is_admin=0, role_title="Staff Nurse", department_id=dept.id),
            Team(name="Nurse Bob", is_admin=0, role_title="Staff Nurse", department_id=dept.id),
            Team(name="Nurse Carol", is_admin=0, role_title="Staff Nurse", department_id=dept.id),
            Team(name="Nurse Eve", is_admin=0, role_title="Staff Nurse", department_id=dept.id),
        ]
        db.session.add_all(staff_members)
        db.session.commit()
        print("2. Added 7 Staff Members with levels: L1 Head, L2 Senior, Night Exempt, Regular.")

        # 4. Generate Rota with PuLP Solver
        start_d = date.today() + timedelta(days=7)
        print("3. Generating 3-week Hospital Rota with PuLP Solver...")
        _, rota_id = generate_rota_with_pulp(staff_members, start_d, period_weeks=3, department_id=dept.id)

        assert rota_id is not None, "❌ Failed to generate optimal rota!"
        print(f"   ✓ Optimal Rota #{rota_id} generated successfully.")

        # 5. Verify Shift Assignments against Rules
        rotas = Rota.query.filter_by(rota_id=rota_id).all()
        assert len(rotas) == 3, f"❌ Expected 3 weeks of rotas, got {len(rotas)}"

        for week_idx, r in enumerate(rotas):
            night_staff = [s.strip() for s in r.shift_8_8.split(',') if s.strip()]
            morning_staff = [s.strip() for s in r.shift_8_5.split(',') if s.strip()]
            evening_staff = [s.strip() for s in r.shift_5_8.split(',') if s.strip()]

            # Rule Verification 1: Minimum Night Staff Count = 2
            assert len(night_staff) >= 2, f"❌ Week {week_idx+1} night staff count {len(night_staff)} < min_members (2)! Staff: {night_staff}"
            
            # Rule Verification 2: Dr. Head Admin (L1) works Morning only
            assert "Dr. Head Admin" in morning_staff
            assert "Dr. Head Admin" not in night_staff and "Dr. Head Admin" not in evening_staff, "❌ Head Admin assigned outside Morning!"

            # Rule Verification 3: Nurse Senior Dave (L2) and Nurse Mary (Night Exempt) never on Night shift
            assert "Nurse Senior Dave" not in night_staff, "❌ Senior Dave (L2) assigned to Night shift!"
            assert "Nurse Mary" not in night_staff, "❌ Nurse Mary (Night Exempt) assigned to Night shift!"

            print(f"   ✓ Week {week_idx+1} verified: Morning={len(morning_staff)}, Evening={len(evening_staff)}, Night={len(night_staff)} ({', '.join(night_staff)})")

        # 6. Cleanup Test Data
        Rota.query.filter_by(rota_id=rota_id).delete()
        RotaAssignment.query.filter_by(rota_id=rota_id).delete()
        Shift.query.filter_by(department_id=dept.id).delete()
        Team.query.filter_by(department_id=dept.id).delete()
        Department.query.filter_by(id=dept.id).delete()
        db.session.commit()
        print("4. Cleaned up temporary test department and records.")

    print("\n=== ALL HOSPITAL DEPARTMENT RULE TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_department_rule_tests()
