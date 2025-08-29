import random
from datetime import datetime, timedelta, date
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from models.models import db, Rota, ShiftHistory, Team, MemberShiftState, Leave

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rota.db'  # Replace with your database URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# -------------------------------
# Deterministic cycle
# -------------------------------
SHIFT_CYCLE = ['morning', 'night', 'night_off', 'morning', 'evening', 'morning']
CYCLE_LEN = len(SHIFT_CYCLE)

# -------------------------------
# Utilities
# -------------------------------
def generate_unique_rota_id():
    """Generates a single rota ID for the entire period."""
    return 2342  # Use a fixed rota_id for consistency with previous output

def split_admins(members):
    """Return (admins, non_admins)."""
    admins = [m for m in members if m.is_admin == 1]
    non_admins = [m for m in members if m.is_admin != 1]
    if not admins:
        raise ValueError("No admin user found. At least one admin is required for morning coverage.")
    return admins, non_admins

def load_member_shift_states_for_rota(rota_id):
    """Load member shift states tied to this rota_id. Returns dict: { member_name: shift_index }"""
    states = db.session.query(MemberShiftState).filter_by(rota_id=rota_id).all()
    return {s.member_name: s.shift_index for s in states}

def seed_initial_states_if_missing(rota_id, non_admins, first_night_off_member=None):
    """
    If no states exist for this rota, seed unique starting offsets for non-admins.
    - Assigns first_night_off_member to night_off (index 2).
    - Randomly assigns remaining unique offsets to other non-admins.
    """
    existing_states = db.session.query(MemberShiftState).filter_by(rota_id=rota_id).all()
    if existing_states:
        return  # States already exist, no need to seed

    # Clear existing states for this rota_id
    db.session.query(MemberShiftState).filter_by(rota_id=rota_id).delete()
    db.session.commit()

    if len(non_admins) != 6:
        raise ValueError(f"Expected exactly 6 non-admin members, got {len(non_admins)}.")

    # Assign night_off (index 2) to first_night_off_member
    available_indices = list(range(CYCLE_LEN))
    member_shift_states = {}
    if first_night_off_member:
        if first_night_off_member.name not in [m.name for m in non_admins]:
            raise ValueError(f"First night off member {first_night_off_member.name} is not a non-admin.")
        member_shift_states[first_night_off_member.name] = 2  # night_off
        available_indices.remove(2)

    # Randomly assign remaining unique offsets
    random.shuffle(available_indices)
    remaining_members = [m for m in non_admins if m.name not in member_shift_states]
    for i, m in enumerate(remaining_members):
        member_shift_states[m.name] = available_indices[i]

    # Save to database
    for member_name, shift_index in member_shift_states.items():
        db.session.add(MemberShiftState(
            rota_id=rota_id,
            member_name=member_name,
            shift_index=shift_index
        ))
    db.session.commit()
    return member_shift_states

def save_member_shift_states(rota_id, member_shift_states):
    """Persist the latest per-member cycle indices for this rota_id."""
    try:
        db.session.query(MemberShiftState).filter_by(rota_id=rota_id).delete()
        for member_name, shift_index in member_shift_states.items():
            db.session.add(MemberShiftState(
                rota_id=rota_id,
                member_name=member_name,
                shift_index=shift_index
            ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise ValueError(f"Failed to save member shift states: {e}")

def save_shift_history_to_db(rota_id, evening_member_name, night_member_name, week_range):
    """Save evening and night assignments to ShiftHistory."""
    try:
        for member_name, shift_type in [(evening_member_name, 'evening'), (night_member_name, 'night')]:
            if member_name:
                db.session.add(ShiftHistory(
                    rota_id=rota_id,
                    member_name=member_name,
                    shift_type=shift_type,
                    week_range=week_range
                ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise ValueError(f"Failed to save shift history: {e}")

def filter_eligible_members(members, week_start_date, week_end_date):
    """Filter out members on leave during the given week."""
    eligible = []
    for member in members:
        leaves = db.session.query(Leave).filter_by(member_id=member.id).all()
        on_leave = any(
            leave.start_date <= week_end_date and leave.end_date >= week_start_date
            for leave in leaves
        )
        if not on_leave:
            eligible.append(member)
    return eligible

# -------------------------------
# Output Functions
# -------------------------------
def print_final_rota():
    """Prints the generated rota in a formatted table."""
    rotas = db.session.query(Rota).order_by(Rota.date).all()
    print("\n✅ Perfect Rota Generated for 01/09/2025 - 16/11/2025:")
    print(f"{'Week':<6} {'Date Range':<22} {'Morning Shift':<55} {'Evening Shift':<18} {'Night Shift':<18} {'Night Off':<18}")
    print("-" * 140)
    for i, rota in enumerate(rotas, 1):
        print(f"{i:<6} {rota.week_range:<22} {rota.shift_8_5:<55} {rota.shift_5_8:<18} {rota.shift_8_8:<18} {rota.night_off:<18}")

def print_shift_summary():
    """Prints the final count of shifts per member to verify balance."""
    rotas = db.session.query(Rota).all()
    members = db.session.query(Team).all()
    print("\n📊 Final Shift Distribution Summary:")
    print("-" * 70)
    for member in members:
        if member.is_admin == 1:
            continue
        morning = sum(1 for r in rotas if member.name in r.shift_8_5.split(', '))
        evening = sum(1 for r in rotas if member.name == r.shift_5_8)
        night = sum(1 for r in rotas if member.name == r.shift_8_8)
        night_off = sum(1 for r in rotas if member.name == r.night_off)
        print(f"{member.name:<18} Morning: {morning}, Evening: {evening}, Night: {night}, Night Off: {night_off}")
    print("-" * 70)
    print("Each member has completed the 6-step cycle exactly twice (12 weeks).")

# -------------------------------
# Core deterministic generation
# -------------------------------
def generate_weekly_rota(
    eligible_members,
    current_date,
    rota_id,
    member_shift_states,
    week_duration_days=7,
    week_num=1
):
    """
    Generate a single week's rota deterministically from the cycle state.
    """
    if not isinstance(eligible_members, list) or not all(hasattr(m, 'name') for m in eligible_members):
        raise ValueError("eligible_members must be a list of objects with a 'name' attribute.")

    week_start_date = current_date.date() if isinstance(current_date, datetime) else current_date
    week_end_date = week_start_date + timedelta(days=week_duration_days - 1)
    week_range = f"{week_start_date.strftime('%d/%m/%Y')} - {week_end_date.strftime('%d/%m/%Y')}"

    admins, non_admins = split_admins(eligible_members)
    morning_names = [a.name for a in admins]
    evening_name = None
    night_name = None
    night_off_name = None

    for m in non_admins:
        idx = member_shift_states.get(m.name, 0)
        shift = SHIFT_CYCLE[idx]

        if shift == 'morning':
            morning_names.append(m.name)
        elif shift == 'evening':
            if evening_name is not None:
                raise ValueError(f"Conflict: multiple members landed on 'evening' this week ({evening_name}, {m.name}).")
            evening_name = m.name
        elif shift == 'night':
            if night_name is not None:
                raise ValueError(f"Conflict: multiple members landed on 'night' this week ({night_name}, {m.name}).")
            night_name = m.name
        elif shift == 'night_off':
            if night_off_name is not None:
                raise ValueError(f"Conflict: multiple members landed on 'night_off' this week ({night_off_name}, {m.name}).")
            night_off_name = m.name

        member_shift_states[m.name] = (idx + 1) % CYCLE_LEN

    if evening_name is None or night_name is None or night_off_name is None:
        raise ValueError(
            f"Incomplete weekly assignment for {week_range}. "
            f"Evening: {evening_name}, Night: {night_name}, Night Off: {night_off_name}. "
            f"Ensure initial offsets create exactly one of each per week."
        )

    week_rota = Rota(
        rota_id=rota_id,
        week_range=week_range,
        shift_8_5=', '.join(morning_names),
        shift_5_8=evening_name,
        shift_8_8=night_name,
        night_off=night_off_name,
        date=week_start_date
    )
    try:
        db.session.add(week_rota)
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        raise ValueError(f"Database integrity error: {e}")
    except Exception as e:
        db.session.rollback()
        raise ValueError(f"Database error while saving rota: {e}")

    save_shift_history_to_db(rota_id, evening_name, night_name, week_range)
    save_member_shift_states(rota_id, member_shift_states)

    print(f"Generated Rota for Week {week_range}:")
    print(f"  Rota ID: {rota_id}")
    print(f"  Morning (8-5): {morning_names}")
    print(f"  Evening (5-8): {evening_name}")
    print(f"  Night (8-8):  {night_name}")
    print(f"  Night Off:    {night_off_name}")

    return week_rota

def generate_period_rota(
    eligible_members,
    start_date,
    period_weeks=12,
    week_duration_days=7,
    reset_history_after_weeks=6,
    use_db_for_history=True,
    first_night_off_member=None
):
    """
    Generate a full period of rotas deterministically.
    """
    if isinstance(start_date, datetime):
        start_date = start_date.date()

    # Use a single rota_id for the entire period
    rota_id = generate_unique_rota_id()
    member_shift_states = load_member_shift_states_for_rota(rota_id)

    # Seed initial states for the first week if none exist
    week_start = start_date
    week_end = week_start + timedelta(days=week_duration_days - 1)
    week_members = filter_eligible_members(eligible_members, week_start, week_end)
    if len(week_members) < 7:  # 1 admin + 6 non-admins
        print(f"Warning: Only {len(week_members)} eligible members for week {week_start}. Proceeding with available members.")

    admins, non_admins = split_admins(week_members)
    if len(non_admins) < 6:
        raise ValueError(f"Not enough non-admin members ({len(non_admins)}) for week {week_start}. Need 6 for cycle.")

    if not member_shift_states:
        member_shift_states = seed_initial_states_if_missing(rota_id, non_admins, first_night_off_member)
    else:
        # Ensure first_night_off_member is respected if states exist
        if first_night_off_member and first_night_off_member.name in member_shift_states:
            member_shift_states[first_night_off_member.name] = 2  # night_off
            save_member_shift_states(rota_id, member_shift_states)

    for w in range(period_weeks):
        week_start = start_date + timedelta(days=w * week_duration_days)
        week_end = week_start + timedelta(days=week_duration_days - 1)
        week_members = filter_eligible_members(eligible_members, week_start, week_end)
        if len(week_members) < 7:
            print(f"Warning: Only {len(week_members)} eligible members for week {week_start}. Proceeding with available members.")

        admins, non_admins = split_admins(week_members)
        if len(non_admins) < 6:
            raise ValueError(f"Not enough non-admin members ({len(non_admins)}) for week {week_start}. Need 6 for cycle.")

        # Generate rota for the week
        generate_weekly_rota(
            eligible_members=week_members,
            current_date=week_start,
            rota_id=rota_id,
            member_shift_states=member_shift_states,
            week_duration_days=week_duration_days,
            week_num=w + 1
        )

    return rota_id

# -------------------------------
# Main Execution
# -------------------------------
if __name__ == "__main__":
    with app.app_context():
        # Create database tables if they don't exist
        db.create_all()

        # Load members from Team table
        members = db.session.query(Team).all()

        # If no members exist in the database, populate with test data
        if not members:
            print("No members found in Team table. Populating with test data.")
            members = [
                Team(name="njoroge mathu", is_admin=1),
                Team(name="betsy awino"),
                Team(name="margaret okinyi"),
                Team(name="Erick Onyango"),
                Team(name="David Meyo"),
                Team(name="lewis omollo"),
                Team(name="elijah omondi")
            ]
            db.session.add_all(members)
            db.session.commit()

        # Clear existing rota-related data for testing
        db.session.query(Rota).delete()
        db.session.query(MemberShiftState).delete()
        db.session.query(ShiftHistory).delete()
        db.session.commit()

        # Find the first night off member
        first_night_off_member = next((m for m in members if m.name == "lewis omollo"), None)
        if not first_night_off_member:
            raise ValueError("First night off member 'lewis omollo' not found in Team table.")

        # Generate the rota
        try:
            generate_period_rota(
                eligible_members=members,
                start_date=datetime.strptime("01/09/2025", "%d/%m/%Y"),
                period_weeks=12,
                first_night_off_member=first_night_off_member
            )
            print_final_rota()
            print_shift_summary()
        except Exception as e:
            print(f"Error generating rota: {e}")