from datetime import timedelta, date
from app import app 
from sqlalchemy.exc import SQLAlchemyError
from models.models import db, Rota, ShiftHistory, Team, MemberShiftState, Leave
from tabulate import tabulate  # pip install tabulate


def get_or_create_shift_state(rota_id, member_name):
    """Fetch or create shift state for tracking balance"""
    state = db.session.query(MemberShiftState).filter_by(
        rota_id=rota_id, member_name=member_name
    ).first()
    if not state:
        state = MemberShiftState(
            rota_id=rota_id, member_name=member_name, shift_index=0
        )
        db.session.add(state)
        db.session.commit()
    return state


def get_shift_cycle(member):
    """Return the cycle for a member based on is_admin status."""
    if member.is_admin == 1:  # Admin always morning
        return ['morning']
    elif member.is_admin == 2:  # Evening exempt
        return ['morning', 'night', 'night_off', 'morning', 'morning', 'morning']
    elif member.is_admin == 3:  # Night exempt, no night_off
        return ['morning', 'morning', 'morning', 'evening', 'morning', 'morning']
    else:  # Regular member
        return ['morning', 'evening', 'night', 'night_off']


def pick_shift_for_member(member, shift_counts, rota_id):
    """Pick shift from member’s cycle and advance their index fairly"""
    cycle = get_shift_cycle(member)
    state = get_or_create_shift_state(rota_id=rota_id, member_name=member.name)

    shift_type = cycle[state.shift_index % len(cycle)]

    shift_counts[member.name][shift_type] += 1
    state.shift_index = (state.shift_index + 1) % len(cycle)
    db.session.commit()

    return shift_type


def generate_balanced_rota_with_cycles(start_date, period_weeks):
    members = db.session.query(Team).all()
    shift_counts = {m.name: {"morning": 0, "evening": 0, "night": 0, "night_off": 0} for m in members}

    for week in range(period_weeks):
        week_start = start_date + timedelta(weeks=week)
        week_end = week_start + timedelta(days=6)
        week_range = f"{week_start} → {week_end}"

        # ✅ Deterministic rota_id from date (e.g. 20250901)
        rota_id = int(week_start.strftime("%Y%m%d"))

        try:
            assignments = {"morning": [], "evening": None, "night": None, "night_off": None}

            for m in members:
                shift_type = pick_shift_for_member(m, shift_counts, rota_id)

                if shift_type == "morning":
                    assignments["morning"].append(m.name)
                elif assignments[shift_type] is None:
                    assignments[shift_type] = m.name
                else:
                    assignments["morning"].append(m.name)
                    shift_counts[m.name]["morning"] += 1

            # --- Save DB ---
            rota = Rota(
                rota_id=rota_id,
                date=week_start,
                week_range=week_range,
                shift_8_5=",".join(assignments["morning"]),
                shift_5_8=assignments["evening"],
                shift_8_8=assignments["night"],
                night_off=assignments["night_off"],
            )
            db.session.add(rota)
            db.session.commit()

            for shift_type, names in assignments.items():
                if not names:
                    continue
                if isinstance(names, list):
                    for n in names:
                        db.session.add(ShiftHistory(
                            rota_id=rota_id, member_name=n,
                            shift_type="morning", week_range=week_range
                        ))
                else:
                    db.session.add(ShiftHistory(
                        rota_id=rota_id, member_name=names,
                        shift_type=shift_type, week_range=week_range
                    ))
            db.session.commit()

            # --- Build console table ---
            week_table = []
            for n in members:
                shift = "morning" if n.name in assignments["morning"] else None
                for s in ["evening", "night", "night_off"]:
                    if assignments[s] == n.name:
                        shift = s
                week_table.append([n.name, shift])

            print(f"\n📅 Week {week+1} ({week_range}) | Rota ID: {rota_id}")
            print(tabulate(week_table, headers=["Member", "Shift"], tablefmt="grid"))

        except SQLAlchemyError as e:
            db.session.rollback()
            print(f"❌ Error generating rota for {week_range}: {e}")


if __name__ == "__main__":
    with app.app_context():
        generate_balanced_rota_with_cycles(
            start_date=date(2025, 9, 1),
            period_weeks=12
        )
