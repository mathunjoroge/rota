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

    # Ensure no member appears in two shifts in the same week
    def exclude_assigned_members(members):
        return [m for m in members if m.name not in assigned_members]

    # Remove last night shift member if present
    if last_night_shift_member in eligible_members_for_this_week:
        eligible_members_for_this_week.remove(last_night_shift_member)

    remaining_members_evening = exclude_assigned_members([m for m in eligible_members_for_this_week if m.name not in evening_shift_history])
    remaining_members_night = exclude_assigned_members([m for m in eligible_members_for_this_week if m.name not in night_shift_history])

    if not remaining_members_evening:
        remaining_members_evening = exclude_assigned_members(eligible_members_for_this_week)
    if not remaining_members_night:
        remaining_members_night = exclude_assigned_members(eligible_members_for_this_week)

    # Select evening shift member
    evening_shift_member = random.choice(remaining_members_evening)
    assigned_members.add(evening_shift_member.name)
    if evening_shift_member in eligible_members_for_this_week:
        eligible_members_for_this_week.remove(evening_shift_member)
    evening_shift_history.add(evening_shift_member.name)

    # Select night shift member
    night_shift_member = random.choice(remaining_members_night)
    assigned_members.add(night_shift_member.name)
    if night_shift_member in eligible_members_for_this_week:
        eligible_members_for_this_week.remove(night_shift_member)
    night_shift_history.add(night_shift_member.name)

    # Ensure we have enough members for morning shifts
    morning_shift_members = random.sample(exclude_assigned_members(eligible_members_for_this_week), min(4, len(eligible_members_for_this_week)))

    if last_night_shift_member and len(morning_shift_members) < 4:
        morning_shift_members.insert(0, last_night_shift_member)

    # Ensure the morning shift has at least two members
    if len(morning_shift_members) < 2:
        return "Morning shift must have at least two members."

    # Add morning shift members to assigned members
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