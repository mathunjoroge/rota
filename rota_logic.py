import random
from datetime import timedelta
from models.models import db, Team, Rota

def generate_weekly_rota(eligible_members, current_date, last_night_shift_member, night_shift_history, evening_shift_history):
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

    # Ensure last night shift member is not included if they are supposed to be off this week for evening shift
    if last_night_shift_member and last_night_shift_member in eligible_members_for_this_week:
        eligible_members_for_this_week = [m for m in eligible_members_for_this_week if m.name != last_night_shift_member.name]

    # Function to select members not in a set of names
    def select_members(members, exclude_names):
        return [m for m in members if m.name not in exclude_names]

    # Select evening shift member, excluding last night shift member
    evening_shift_member = select_members(
        [m for m in eligible_members_for_this_week if m.name not in evening_shift_history], 
        assigned_members
    )
    if not evening_shift_member:
        evening_shift_member = select_members(eligible_members_for_this_week, assigned_members)
    if not evening_shift_member:
        return "Error: No members available for evening shift."
    evening_shift_member = random.choice(evening_shift_member)
    assigned_members.add(evening_shift_member.name)
    evening_shift_history.add(evening_shift_member.name)

    # Select night shift member ensuring all members have done this shift before anyone repeats
    all_members = set(m.name for m in eligible_members)
    members_not_done_night_shift = all_members - night_shift_history
    
    night_shift_candidates = select_members(eligible_members_for_this_week, assigned_members)
    if members_not_done_night_shift:
        night_shift_candidates = [m for m in night_shift_candidates if m.name in members_not_done_night_shift]
    
    if not night_shift_candidates:
        # If no one is available for night shift, reset history and try again
        print("All members have done night shift or are otherwise occupied. Resetting night shift history.")
        night_shift_history.clear()
        night_shift_candidates = select_members(eligible_members_for_this_week, assigned_members)
    
    if not night_shift_candidates:
        return "Error: No members available for night shift."
    night_shift_member = random.choice(night_shift_candidates)
    assigned_members.add(night_shift_member.name)
    night_shift_history.add(night_shift_member.name)

    # Select morning shift members, explicitly excluding both evening and night shift members
    morning_shift_members = select_members(
        eligible_members_for_this_week, 
        assigned_members
    )

    # Add the last night shift member to the morning shift since they are off this week
    if last_night_shift_member:
        morning_shift_members.insert(0, last_night_shift_member)  # Adding at the start to ensure they're included

    # Ensure we have at least 2 members for the morning shift
    if len(morning_shift_members) < 2:
        # If there are not enough members, we'll have to compromise on shift requirements
        if len(morning_shift_members) == 1:
            print("Warning: Only one member available for morning shift.")
        elif len(morning_shift_members) == 0:
            return "Error: No members available for morning shift."
    else:
        # Randomly select up to 4 members for morning shift but ensure at least 2
        morning_shift_members = random.sample(morning_shift_members, min(4, len(morning_shift_members)))

    # Update assigned members
    assigned_members.update(m.name for m in morning_shift_members)

    night_off_value = last_night_shift_member.name if last_night_shift_member else None

    week_rota = Rota(
        week_range=week_range,
        shift_8_5=', '.join([m.name for m in morning_shift_members]),
        shift_5_8=evening_shift_member.name,
        shift_8_8=night_shift_member.name,
        night_off=night_off_value
    )
    db.session.add(week_rota)
    db.session.commit()

    return night_shift_member