import random
from datetime import timedelta
from models.models import db, Rota

def generate_weekly_rota(
    eligible_members, current_date, last_night_shift_member, night_shift_history, evening_shift_history, first_night_off_member=None
):
    week_start_date = current_date
    week_end_date = current_date + timedelta(days=4)  # Friday (End of the week)
    week_range = f"{week_start_date.strftime('%d/%m/%Y')} - {week_end_date.strftime('%d/%m/%Y')}"

    # Track members assigned to shifts during the week
    assigned_members = set()

    # Remove members who have leaves during the week
    eligible_members_for_this_week = [
        m for m in eligible_members if not any(
            leave.start_date <= current_date <= leave.end_date for leave in m.leaves
        )
    ]

    # Handle night off logic
    night_off_member = None
    if first_night_off_member:  # Use the first week's night off member
        night_off_member = first_night_off_member
        eligible_members_for_this_week = [
            m for m in eligible_members_for_this_week if m.name != night_off_member.name
        ]
    elif last_night_shift_member:  # Use last week's night shift member as night off
        night_off_member = last_night_shift_member
        eligible_members_for_this_week = [
            m for m in eligible_members_for_this_week if m.name != night_off_member.name
        ]

    # Utility function to select members not already assigned and not admins
    def select_members(members, exclude_names):
        return [m for m in members if m.name not in exclude_names and m.is_admin != 1]

    # Select evening shift member
    evening_shift_candidates = select_members(eligible_members_for_this_week, assigned_members)
    members_not_done_evening_shift = set(m.name for m in eligible_members) - evening_shift_history

    if members_not_done_evening_shift:
        evening_shift_candidates = [m for m in evening_shift_candidates if m.name in members_not_done_evening_shift]

    if not evening_shift_candidates:
        print("Resetting evening shift history: all members have done the shift.")
        evening_shift_history.clear()
        evening_shift_candidates = select_members(eligible_members_for_this_week, assigned_members)

    if not evening_shift_candidates:
        raise ValueError("Error: No members available for evening shift.")

    evening_shift_member = random.choice(evening_shift_candidates)
    assigned_members.add(evening_shift_member.name)
    evening_shift_history.add(evening_shift_member.name)

    # Select night shift member
    night_shift_candidates = select_members(eligible_members_for_this_week, assigned_members)
    members_not_done_night_shift = set(m.name for m in eligible_members) - night_shift_history

    if members_not_done_night_shift:
        night_shift_candidates = [m for m in night_shift_candidates if m.name in members_not_done_night_shift]

    if not night_shift_candidates:
        print("Resetting night shift history: all members have done the shift.")
        night_shift_history.clear()
        night_shift_candidates = select_members(eligible_members_for_this_week, assigned_members)

    if not night_shift_candidates:
        raise ValueError("Error: No members available for night shift.")

    night_shift_member = random.choice(night_shift_candidates)
    assigned_members.add(night_shift_member.name)
    night_shift_history.add(night_shift_member.name)

    # Select morning shift members
    morning_shift_candidates = select_members(eligible_members_for_this_week, assigned_members)

    # Exclude the evening shift member from the morning shift candidates
    morning_shift_candidates = [
        m for m in morning_shift_candidates if m.name != evening_shift_member.name
    ]

    # Exclude members in night shift or night off from morning shift
    morning_shift_candidates = [
        m for m in morning_shift_candidates
        if m.name not in {night_shift_member.name, night_off_member.name if night_off_member else None}
    ]

    # Always include admins in the morning shift
    admin_members = [m for m in eligible_members if m.is_admin == 1]
    morning_shift_members = list(set(admin_members + random.sample(
        morning_shift_candidates,
        min(4 - len(admin_members), len(morning_shift_candidates))
    )))

    if len(morning_shift_members) < 2:
        if not morning_shift_members:
            raise ValueError("Error: No members available for morning shift.")
        print("Warning: Less than 2 members available for morning shift.")

    # Save the week's rota to the database
    # Generate a unique rota ID
    rota_id = random.randint(1000, 9999)

    # Save the week's rota to the database
    week_rota = Rota(
        rota_id=rota_id,
        week_range=week_range,
        shift_8_5=', '.join(m.name for m in morning_shift_members),
        shift_5_8=evening_shift_member.name,
        shift_8_8=night_shift_member.name,
        night_off=night_off_member.name if night_off_member else None
    )

    # Debugging output for visibility
    print(f"Generated Rota for Week {week_range}:")
    print(f"rota id: {rota_id}")
    print(f"Morning Shift: {[m.name for m in morning_shift_members]}")
    print(f"Evening Shift: {evening_shift_member.name}")
    print(f"Night Shift: {night_shift_member.name}")
    print(f"Night Off: {night_off_member.name if night_off_member else 'None'}")

    db.session.add(week_rota)
    db.session.commit()

    return night_shift_member