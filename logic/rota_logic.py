import random
from datetime import datetime, timedelta
from models.models import db, Rota

def generate_unique_rota_id():
    """Generates a unique rota ID."""
    return str(random.randint(1000, 9999))
rota_id = generate_unique_rota_id()

def get_eligible_members(members, excludes):
    """Filters eligible members based on exclusions."""
    return [m for m in members if m.name not in excludes and m.is_admin != 1]

def select_shift_member(candidates, shift_history):
    """Selects a member for a shift, considering shift history."""
    candidates = [m for m in candidates if m.name not in shift_history]
    if not candidates:
        print("Resetting shift history: all members have done the shift.")
        shift_history.clear()
        candidates = get_eligible_members(eligible_members, assigned_members)
    if not candidates:
        raise ValueError("No members available for this shift.")
    return random.choice(candidates)

def generate_weekly_rota(
        
    eligible_members, current_date, last_night_shift_member, night_shift_history, evening_shift_history, first_night_off_member=None
):
    """Generates and assigns shifts for a given week."""
    # Ensure eligible_members is a valid list
    if not isinstance(eligible_members, list) or not all(hasattr(m, 'name') for m in eligible_members):
        raise ValueError("eligible_members must be a list of objects with a 'name' attribute.")

    # Initialize variables
    current_date = current_date.date() if isinstance(current_date, datetime) else current_date
    week_start_date = current_date
    week_end_date = current_date + timedelta(days=4)
    week_range = f"{week_start_date.strftime('%d/%m/%Y')} - {week_end_date.strftime('%d/%m/%Y')}"
    assigned_members = set()  # Tracks members assigned to shifts

    # Handle night off logic
    night_off_member = first_night_off_member or last_night_shift_member
    if night_off_member:
        eligible_members = [m for m in eligible_members if m.name != night_off_member.name]

    # Select evening shift member
    evening_shift_candidates = get_eligible_members(eligible_members, assigned_members)
    evening_shift_member = select_shift_member(evening_shift_candidates, evening_shift_history)
    assigned_members.add(evening_shift_member.name)
    evening_shift_history.add(evening_shift_member.name)

    # Select night shift member
    night_shift_candidates = get_eligible_members(eligible_members, assigned_members)
    night_shift_member = select_shift_member(night_shift_candidates, night_shift_history)
    assigned_members.add(night_shift_member.name)
    night_shift_history.add(night_shift_member.name)

    # Select morning shift members
    morning_shift_candidates = get_eligible_members(eligible_members, assigned_members)
    morning_shift_candidates = [m for m in morning_shift_candidates if m.name != evening_shift_member.name]
    morning_shift_candidates = [m for m in morning_shift_candidates if m.name != (night_off_member.name if night_off_member else None)]
    admin_members = [m for m in eligible_members if m.is_admin == 1]
    morning_shift_members = list(set(admin_members + random.sample(
        morning_shift_candidates,
        min(4 - len(admin_members), len(morning_shift_candidates))
    )))

    if len(morning_shift_members) < 2:
        if not morning_shift_members:
            raise ValueError("Error: No members available for morning shift.")
        print("Warning: Less than 2 members available for morning shift.")

    # Save rota to database
    
    week_rota = Rota(
        rota_id=rota_id,
        week_range=week_range,
        shift_8_5=', '.join(m.name for m in morning_shift_members),
        shift_5_8=evening_shift_member.name,
        shift_8_8=night_shift_member.name,
        night_off=night_off_member.name if night_off_member else None
    )
    try:
        db.session.add(week_rota)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise ValueError(f"Database error: {e}")

    # Debugging output
    print(f"Generated Rota for Week {week_range}:")
    print(f"Rota ID: {rota_id}")
    print(f"Morning Shift: {[m.name for m in morning_shift_members]}")
    print(f"Evening Shift: {evening_shift_member.name}")
    print(f"Night Shift: {night_shift_member.name}")
    print(f"Night Off: {night_off_member.name if night_off_member else 'None'}")

    return night_shift_member