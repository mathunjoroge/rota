"""
Standalone test for the rota generation logic used by the app
(logic.rota_logic.generate_period_rota).

Validates:
  1. Generation succeeds and produces one Rota row per week.
  2. Every week has exactly one evening, one night and one night_off shift.
  3. The morning shift covers the admin plus everyone not on a special shift.
  4. Night -> night_off continuity holds week over week (when eligible).
  5. Special shifts are distributed fairly (balanced counts).
  6. Members on leave for a week are excluded from that week's rota.

Run with:  ./venv/bin/python test_rota_generation.py
"""

import os
import tempfile
from datetime import date, timedelta

from flask import Flask
from models.models import db, Team, Leave, Rota, MemberShiftState

from logic.rota_logic import generate_period_rota, split_admins


def make_app(db_path):
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app


def seed_members():
    # 1 admin + 6 non-admins -> ideal 6-step cycle
    members = [
        Team(name="Admin One", is_admin=1),
        Team(name="Alice", is_admin=0),
        Team(name="Bob", is_admin=0),
        Team(name="Carol", is_admin=0),
        Team(name="Dave", is_admin=0),
        Team(name="Eve", is_admin=0),
        Team(name="Frank", is_admin=0),
    ]
    db.session.add_all(members)
    db.session.commit()
    return members


def test_basic_generation_and_constraints():
    tmp = tempfile.mkstemp(suffix='.db')[1]
    app = make_app(tmp)
    with app.app_context():
        db.create_all()
        members = seed_members()

        period_weeks = 12
        start = date(2025, 9, 1)
        _, rota_id = generate_period_rota(
            eligible_members=members,
            start_date=start,
            period_weeks=period_weeks,
        )

        assert rota_id > 0, "rota_id should be a positive integer"

        rotas = Rota.query.filter_by(rota_id=rota_id).order_by(Rota.date).all()
        assert len(rotas) == period_weeks, f"expected {period_weeks} weeks, got {len(rotas)}"

        admins, non_admins = split_admins(members)
        admin_names = {a.name for a in admins}
        non_admin_names = {m.name for m in non_admins}

        # Per-week structural checks
        for r in rotas:
            evening, night, night_off = r.shift_5_8, r.shift_8_8, r.night_off
            morning = [n.strip() for n in r.shift_8_5.split(',') if n.strip()]

            assert evening, f"week {r.week_range} missing evening shift"
            assert night, f"week {r.week_range} missing night shift"
            assert night_off, f"week {r.week_range} missing night_off"

            # Morning must include the admin
            assert admin_names.issubset(set(morning)), \
                f"week {r.week_range} morning missing admin: {morning}"

            # Everyone appears exactly once across the four shift buckets
            assigned = set(morning) | {evening, night, night_off}
            expected = admin_names | non_admin_names
            assert assigned == expected, \
                f"week {r.week_range} assignment mismatch: {assigned} != {expected}"

        # Night -> night_off continuity (ignoring weeks where the night worker
        # is on leave the following week)
        leaves_by_member = {}
        for lv in Leave.query.all():
            leaves_by_member.setdefault(lv.member_id, []).append(lv)

        for i in range(len(rotas) - 1):
            this_week, next_week = rotas[i], rotas[i + 1]
            night_worker = this_week.shift_8_8
            next_start = next_week.date
            next_end = next_start + timedelta(days=6)
            member = Team.query.filter_by(name=night_worker).first()
            on_leave_next = any(
                lv.start_date <= next_end and lv.end_date >= next_start
                for lv in leaves_by_member.get(member.id, [])
            )
            if not on_leave_next:
                assert next_week.night_off == night_worker, \
                    f"continuity broken: {night_worker} worked night in week {i+1} " \
                    f"but {next_week.night_off} got night_off in week {i+2}"

        # Fairness: with 6 non-admins over 12 weeks each special shift is done
        # exactly twice by each non-admin.
        counts = {m.name: {'evening': 0, 'night': 0, 'night_off': 0} for m in non_admins}
        for r in rotas:
            counts[r.shift_5_8]['evening'] += 1
            counts[r.shift_8_8]['night'] += 1
            counts[r.night_off]['night_off'] += 1

        for name, c in counts.items():
            assert c['evening'] == 2 and c['night'] == 2 and c['night_off'] == 2, \
                f"unbalanced distribution for {name}: {c}"

        print(f"[PASS] basic generation: {period_weeks} weeks, rota_id={rota_id}")
        print("[PASS] structural + continuity + fairness checks passed")
        return rota_id


def test_leave_filtering():
    tmp = tempfile.mkstemp(suffix='.db')[1]
    app = make_app(tmp)
    with app.app_context():
        db.create_all()
        members = seed_members()

        # Put "Bob" on leave for the second week (2025-09-08 .. 2025-09-14)
        bob = Team.query.filter_by(name="Bob").first()
        leave_start = date(2025, 9, 8)
        leave_end = date(2025, 9, 14)
        db.session.add(Leave(member_id=bob.id, start_date=leave_start, end_date=leave_end))
        db.session.commit()

        _, rota_id = generate_period_rota(
            eligible_members=members,
            start_date=date(2025, 9, 1),
            period_weeks=12,
        )

        rotas = Rota.query.filter_by(rota_id=rota_id).order_by(Rota.date).all()
        second_week = rotas[1]
        week_assignments = (
            [n.strip() for n in second_week.shift_8_5.split(',') if n.strip()]
            + [second_week.shift_5_8, second_week.shift_8_8, second_week.night_off]
        )
        assert "Bob" not in week_assignments, \
            f"Bob was scheduled while on leave: {week_assignments}"
        bob_appearances = sum(
            1 for r in rotas
            if "Bob" in [n.strip() for n in r.shift_8_5.split(',') if n.strip()]
            or "Bob" in (r.shift_5_8, r.shift_8_8, r.night_off)
        )
        assert bob_appearances > 0, "Bob should still appear in weeks he is not on leave"

        print("[PASS] leave filtering: Bob excluded from 2025-09-08 week, present elsewhere")


def test_insufficient_members():
    tmp = tempfile.mkstemp(suffix='.db')[1]
    app = make_app(tmp)
    with app.app_context():
        db.create_all()
        # Only 2 non-admins -> below the required 3
        members = [
            Team(name="Admin", is_admin=1),
            Team(name="X", is_admin=0),
            Team(name="Y", is_admin=0),
        ]
        try:
            generate_period_rota(
                eligible_members=members,
                start_date=date(2025, 9, 1),
                period_weeks=4,
            )
            assert False, "expected ValueError for too few non-admin members"
        except ValueError:
            print("[PASS] insufficient-members guard raised ValueError as expected")


if __name__ == '__main__':
    test_basic_generation_and_constraints()
    test_leave_filtering()
    test_insufficient_members()
    print("\nALL ROTA TESTS PASSED")
