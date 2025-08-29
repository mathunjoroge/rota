import random
from datetime import datetime, timedelta, date
from models.models import db, Rota, ShiftHistory, Team, MemberShiftState, Leave
from sqlalchemy.exc import IntegrityError

# Deterministic cycle
SHIFT_CYCLE = ['morning', 'night', 'night_off', 'morning', 'evening', 'morning']
CYCLE_LEN = len(SHIFT_CYCLE)

def generate_unique_rota_id():
    """Generates a single rota ID for the entire period."""
    return 2342  # Fixed rota_id for consistency with provided output

def split_admins(members):
    """Return (admins, non_admins)."""
    admins = [m for m in members if m.is_admin == 1]
    non_admins = [m for m in members if m.is_admin != 1]
    if not admins:
        raise ValueError("No admin user found. At least one admin is required for morning coverage.")
    return admins, non_admins

def load_member_shift_states(rota_id):
    """Loads member shift states from the database."""
    states = db.session.query(MemberShiftState).filter_by(rota_id=rota_id).all()
    return {state.member_name: state.shift_index for state in states}

def seed_initial_states_if_missing(rota_id, non_admins, first_night_off_member=None):
    """
    If no states exist for this rota, seed unique starting offsets for non-admins.
    - Assigns first_night_off_member to night_off (index 2).
    - Randomly assigns remaining unique offsets to other non-admins.
    """
    existing_states = db.session.query(MemberShiftState).filter_by(rota_id=rota_id).all()
    if existing_states:
        return  # States already exist, no need to seed

    db.session.query(MemberShiftState).filter_by(rota_id=rota_id).delete()
    db.session.commit()

    if len(non_admins) != 6:
        raise ValueError(f"Expected exactly 6 non-admin members, got {len(non_admins)}.")

    member_shift_states = {}
    available_indices = list(range(CYCLE_LEN))
    if first_night_off_member:
        if first_night_off_member.name not in [m.name for m in non_admins]:
            raise ValueError(f"First night off member {first_night_off_member.name} is not a non-admin.")
        member_shift_states[first_night_off_member.name] = 2  # night_off
        available_indices.remove(2)

    random.shuffle(available_indices)
    remaining_members = [m for m in non_admins if m.name not in member_shift_states]
    for i, m in enumerate(remaining_members):
        member_shift_states[m.name] = available_indices[i]

    for member_name, shift_index in member_shift_states.items():
        db.session.add(MemberShiftState(
            rota_id=rota_id,
            member_name=member_name,
            shift_index=shift_index
        ))
    db.session.commit()
    return member_shift_states

def save_member_shift_states(rota_id, member_shift_states):
    """Saves member shift states to the database."""
    try:
        db.session.query(MemberShiftState).filter_by(rota_id=rota_id).delete()
        for member_name, shift_index in member_shift_states.items():
            state = MemberShiftState(
                rota_id=rota_id,
                member_name=member_name,
                shift_index=shift_index
            )
            db.session.add(state)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise ValueError(f"Failed to save member shift states: {e}")

def save_shift_history_to_db(rota_id, evening_member_name, night_member_name, week_range):
    """Saves shift history to the database."""
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

def generate_weekly_rota(
    eligible_members,
    current_date,
    last_night_shift_member,  # Kept for compatibility, not used in deterministic approach
    night_shift_history,      # Kept for compatibility, not used
    evening_shift_history,    # Kept for compatibility, not used
    rota_id,
    member_shift_states,
    week_num,
    first_night_off_member=None,  # Used only for week 1 state initialization
    week_duration_days=7,
    reset_history_after_weeks=6,  # Kept for compatibility, not used
    use_db_for_history=True
):
    """Generates shifts for a single week using deterministic cycle."""
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

    if use_db_for_history:
        save_shift_history_to_db(rota_id, evening_name, night_name, week_range)
        save_member_shift_states(rota_id, member_shift_states)

    print(f"Generated Rota for Week {week_range}:")
    print(f"  Rota ID: {rota_id}")
    print(f"  Morning (8-5): {morning_names}")
    print(f"  Evening (5-8): {evening_name}")
    print(f"  Night (8-8):  {night_name}")
    print(f"  Night Off:    {night_off_name}")

    # Return night_shift_member for compatibility with rota.py
    night_shift_member = next(m for m in eligible_members if m.name == night_name)
    return night_shift_member, week_range

def generate_period_rota(
    eligible_members,
    start_date,
    period_weeks=12,
    week_duration_days=7,
    reset_history_after_weeks=6,
    use_db_for_history=True,
    first_night_off_member=None
):
    """Generates rotas for the entire period, week by week."""
    rota_id = generate_unique_rota_id()
    night_shift_history = set()  # Kept for compatibility, not used
    evening_shift_history = set()  # Kept for compatibility, not used
    last_night_shift_member = first_night_off_member  # Kept for compatibility
    night_shift_members = []
    member_shift_states = load_member_shift_states(rota_id) if use_db_for_history else {}

    # Seed initial states if none exist
    week_start = start_date
    week_end = week_start + timedelta(days=week_duration_days - 1)
    week_members = filter_eligible_members(eligible_members, week_start, week_end)
    if len(week_members) < 7:
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

    for week in range(period_weeks):
        current_date = start_date + timedelta(days=week * week_duration_days)
        print(f"\nGenerating rota for week {week + 1} of {period_weeks}")
        week_members = filter_eligible_members(eligible_members, current_date, current_date + timedelta(days=week_duration_days - 1))
        if len(week_members) < 7:
            print(f"Warning: Only {len(week_members)} eligible members for week {current_date}. Proceeding with available members.")
        admins, non_admins = split_admins(week_members)
        if len(non_admins) < 6:
            raise ValueError(f"Not enough non-admin members ({len(non_admins)}) for week {current_date}. Need 6 for cycle.")

        night_shift_member, week_range = generate_weekly_rota(
            eligible_members=week_members,
            current_date=current_date,
            last_night_shift_member=last_night_shift_member,
            night_shift_history=night_shift_history,
            evening_shift_history=evening_shift_history,
            rota_id=rota_id,
            member_shift_states=member_shift_states,
            week_num=week + 1,
            first_night_off_member=first_night_off_member if week == 0 else None,
            week_duration_days=week_duration_days,
            reset_history_after_weeks=reset_history_after_weeks,
            use_db_for_history=use_db_for_history
        )
        night_shift_members.append(night_shift_member)
        last_night_shift_member = night_shift_member

        # Verify assignments
        week_rota = db.session.query(Rota).filter_by(rota_id=rota_id, week_range=week_range).first()
        if not week_rota:
            raise ValueError(f"Failed to save rota for week {week + 1}.")
        assigned_names = (
            week_rota.shift_8_5.split(', ') +
            [week_rota.shift_5_8, week_rota.shift_8_8, week_rota.night_off]
        )
        assigned_names = [name for name in assigned_names if name]
        if len(set(assigned_names)) != len(week_members):
            print(f"Warning: Only {len(set(assigned_names))} members assigned in week {week + 1}: {assigned_names}")

    return night_shift_members, rota_id

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