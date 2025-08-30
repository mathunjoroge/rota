# -*- coding: utf-8 -*-
"""
rota_logic.py

This module contains the core business logic for generating a fair, deterministic,
and balanced weekly staff rota. It is designed to handle various constraints,
including member-specific shift exemptions and mandatory rest periods (night_off).

The generation is deterministic, meaning for the same set of inputs (members,
start date, exemptions), it will always produce the exact same rota, eliminating
the unpredictability of random assignment.
"""

import logging
from datetime import date, timedelta
from models.models import db, Rota, Team, MemberShiftState, Leave

# Configure logging for this module
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base deterministic cycle for a standard member's shift rotation.
# This predictable pattern is the foundation of the fair rota.
SHIFT_CYCLE = ['morning', 'night', 'night_off', 'morning', 'evening', 'morning']
CYCLE_LEN = len(SHIFT_CYCLE)


def generate_unique_rota_id():
    """
    Generates a single, static rota ID for the entire generation period.
    In a real-world, multi-tenant application, this would likely be a UUID or
    a value from a database sequence to ensure true uniqueness.
    """
    return 2342


def split_admins(members):
    """
    Separates a list of members into two groups: admins (is_admin=1) and non-admins.
    Admins are assumed to work morning shifts only.

    Args:
        members (list[Team]): A list of Team member objects.

    Returns:
        tuple[list[Team], list[Team]]: A tuple containing the list of admins
                                       and the list of non-admins.
    
    Raises:
        ValueError: If no members with is_admin=1 are found.
    """
    admins = [m for m in members if m.is_admin == 1]
    non_admins = [m for m in members if m.is_admin != 1]
    if not admins:
        raise ValueError("No admin user found. At least one admin (is_admin=1) is required.")
    return admins, non_admins


def get_member_cycle(member):
    """
    Returns a member's specific shift cycle based on their exemptions.
    This allows for customized rota patterns for members with special conditions.

    Args:
        member (Team): The Team member object.

    Returns:
        list[str]: The shift cycle pattern for the member.
    """
    if member.is_admin == 2:  # Evening exempt member
        return ['morning', 'night', 'night_off', 'morning', 'morning', 'morning']
    if member.is_admin == 3:  # Night and Night Off exempt member
        return ['morning', 'evening', 'morning', 'morning', 'morning', 'evening']
    # Default cycle for standard members
    return SHIFT_CYCLE


def calculate_expected_shifts(member, period_weeks, evening_eligible_count, night_eligible_count):
    """
    Calculates the mathematically ideal number of shifts per type for a given
    member over the entire rota period. This is used for validation and summary.

    Args:
        member (Team): The member to calculate for.
        period_weeks (int): The total number of weeks in the rota.
        evening_eligible_count (int): Count of members who can work evening shifts.
        night_eligible_count (int): Count of members who can work night shifts.

    Returns:
        dict: A dictionary with the ideal counts for each shift type.
    """
    if member.is_admin == 1:
        return {'morning': period_weeks, 'evening': 0, 'night': 0, 'night_off': 0}

    # Calculate the average number of special shifts per eligible person
    expected_evening = period_weeks / evening_eligible_count if evening_eligible_count > 0 else 0
    expected_night = period_weeks / night_eligible_count if night_eligible_count > 0 else 0
    expected_night_off = period_weeks / night_eligible_count if night_eligible_count > 0 else 0

    if member.is_admin == 2:  # Evening exempt
        return {'morning': period_weeks - (expected_night + expected_night_off), 'evening': 0, 'night': expected_night, 'night_off': expected_night_off}
    if member.is_admin == 3:  # Night exempt
        return {'morning': period_weeks - expected_evening, 'evening': expected_evening, 'night': 0, 'night_off': 0}
    
    # Standard non-admin member
    return {'morning': period_weeks - (expected_evening + expected_night + expected_night_off), 'evening': expected_evening, 'night': expected_night, 'night_off': expected_night_off}


def seed_initial_states_if_missing(rota_id, non_admins, first_night_off_member=None):
    logger.info(f"Seeding initial shift states for Rota ID: {rota_id}.")
    db.session.query(MemberShiftState).filter_by(rota_id=rota_id).delete()
    logger.info("Deleted existing shift states")
    db.session.commit()
    logger.info("Commit after delete successful")

    if len(non_admins) < 3:
        raise ValueError(f"Rota generation requires at least 3 non-admin members, but found {len(non_admins)}.")

    member_shift_states = {}
    assigned_indices = set()

    # Priority 1: Assign the designated first night-off member if provided.
    if first_night_off_member:
        if first_night_off_member.is_admin == 3:
            raise ValueError(f"Member {first_night_off_member.name} is night-exempt and cannot be assigned 'night_off'.")
        logger.info(f"Assigning {first_night_off_member.name} as the first night_off.")
        night_off_index = 2  # Index of 'night_off' in the base cycle
        member_shift_states[first_night_off_member.name] = night_off_index
        assigned_indices.add(night_off_index)

    # Sort remaining members by name to ensure deterministic assignment order.
    remaining_members = sorted([m for m in non_admins if m.name not in member_shift_states], key=lambda m: m.name)
    logger.info(f"Remaining members: {[m.name for m in remaining_members]}")
    
    # Assign indices, allowing reuse if necessary
    current_index = 0
    for member in remaining_members:
        logger.info(f"Processing {member.name}, current_index: {current_index}")
        start_index = current_index
        while current_index in assigned_indices and len(assigned_indices) < CYCLE_LEN:
            current_index = (current_index + 1) % CYCLE_LEN
        member_shift_states[member.name] = current_index
        assigned_indices.add(current_index)
        logger.info(f"Assigned {member.name} to index {current_index}")

    # Persist the seeded states to the database for record-keeping.
    logger.info("Persisting shift states to database")
    for member_name, shift_index in member_shift_states.items():
        logger.info(f"Adding state for {member_name}: shift_index={shift_index}")
        db.session.add(MemberShiftState(rota_id=rota_id, member_name=member_name, shift_index=shift_index))
    logger.info("Committing shift states")
    db.session.commit()
    logger.info("Commit successful")
    logger.info("Finished seeding initial states.")
    return member_shift_states


def filter_eligible_members(members, week_start_date, week_end_date):
    """
    Filters out members who are on leave for any part of the given week.

    Args:
        members (list[Team]): The list of all members.
        week_start_date (date): The start date of the week to check.
        week_end_date (date): The end date of the week to check.

    Returns:
        list[Team]: A list of members who are not on leave and are eligible to work.
    """
    eligible = []
    for member in members:
        on_leave = db.session.query(Leave).filter(
            Leave.member_id == member.id,
            Leave.start_date <= week_end_date,
            Leave.end_date >= week_start_date
        ).first()

        if not on_leave:
            eligible.append(member)
        else:
            logger.info(f"Filtering out {member.name} due to leave from {on_leave.start_date} to {on_leave.end_date}.")
            
    return eligible


def _generate_weekly_rota(eligible_members, current_date, last_night_shift_member, rota_id, member_shift_states, week_duration_days=7):
    week_start = current_date
    week_end = current_date + timedelta(days=week_duration_days - 1)
    week_range = f"{week_start.strftime('%Y-%m-%d')} - {week_end.strftime('%Y-%m-%d')}"
    logger.info(f"--- Generating Rota for Week: {week_range} ---")

    admins, non_admins = split_admins(eligible_members)
    if len(non_admins) < 3:
        raise ValueError(f"Not enough non-admin members ({len(non_admins)}) for week {week_start}. Need at least 3.")

    assignments = {'evening': None, 'night': None, 'night_off': None}
    available = set(non_admins)

    # Rule 1: Hard constraint for 'night_off' post-night shift.
    if last_night_shift_member and last_night_shift_member in available:
        if last_night_shift_member.is_admin == 3:
            logger.warning(f"Skipping night_off for {last_night_shift_member.name} (is_admin=3, night-exempt)")
        else:
            logger.info(f"Assigning {last_night_shift_member.name} to night_off (mandatory post-night shift).")
            assignments['night_off'] = last_night_shift_member
            available.remove(last_night_shift_member)

    # Rule 2: Build candidate pools based on each member's cycle preference.
    pools = {'morning': [], 'evening': [], 'night': [], 'night_off': []}
    for m in available:
        state = member_shift_states[m.name]
        preferred_shift = state['cycle'][state['idx']]
        pools[preferred_shift].append(m)

    # Helper for Rule 3 & 4: Pick the best candidate based on lowest shift count, respecting exemptions.
    def pick_best(candidates, shift_type):
        if not candidates:
            return None
        # Filter candidates based on exemptions
        if shift_type == 'evening':
            candidates = [m for m in candidates if m.is_admin != 2]  # Exclude evening-exempt
        elif shift_type == 'night':
            candidates = [m for m in candidates if m.is_admin != 3]  # Exclude night-exempt
        elif shift_type == 'night_off':
            candidates = [m for m in candidates if m.is_admin != 3]  # Exclude night-exempt
        if not candidates:
            return None
        # Sort by count, then by name for deterministic tie-breaking.
        return sorted(candidates, key=lambda m: (member_shift_states[m.name]['counts'][shift_type], m.name))[0]

    # Sequentially fill remaining special shifts.
    for shift in ['night_off', 'evening', 'night']:
        if assignments[shift]:
            continue  # Skip if already filled by hard constraint.

        # Try to assign from members who are naturally due for this shift.
        candidate = pick_best(pools[shift], shift)
        
        # If no one is due, borrow fairly from the 'morning' pool, respecting exemptions.
        if not candidate:
            candidate = pick_best(pools['morning'], shift)
            if candidate:
                logger.info(f"No one is due for {shift}. Borrowing {candidate.name} from morning pool.")

        if candidate:
            logger.info(f"Assigning {candidate.name} to {shift}.")
            assignments[shift] = candidate
            available.remove(candidate)
            # Remove the assigned member from whichever pool they were in.
            for pool in pools.values():
                if candidate in pool:
                    pool.remove(candidate)
                    break
    
    # All remaining non-admins and all admins are assigned to the morning shift.
    final_morning_members = [m.name for m in admins] + [m.name for m in available]

    # Update counts and advance cycle index for every non-admin for the next week.
    for member in non_admins:
        state = member_shift_states[member.name]
        if member == assignments['evening']:
            state['counts']['evening'] += 1
        elif member == assignments['night']:
            state['counts']['night'] += 1
        elif member == assignments['night_off']:
            state['counts']['night_off'] += 1
        else:
            state['counts']['morning'] += 1
        state['idx'] = (state['idx'] + 1) % len(state['cycle'])

    # Create and save the Rota entry for this week.
    new_rota = Rota(
        rota_id=rota_id, date=week_start, week_range=week_range,
        shift_8_5=', '.join(sorted(final_morning_members)),
        shift_5_8=assignments['evening'].name if assignments['evening'] else '',
        shift_8_8=assignments['night'].name if assignments['night'] else '',
        night_off=assignments['night_off'].name if assignments['night_off'] else ''
    )
    db.session.add(new_rota)
    db.session.commit()

    return assignments['night'], assignments['evening']


def generate_period_rota(eligible_members, start_date, period_weeks, week_duration_days=7, reset_history_after_weeks=6, use_db_for_history=True, first_night_off_member=None):
    """
    Generates a complete, multi-week rota. This function serves as a compatible
    wrapper that orchestrates the weekly generation process for the Flask blueprint.

    Args:
        eligible_members (list[Team]): The full list of members for the rota period.
        start_date (date): The starting date of the rota.
        period_weeks (int): The number of weeks to generate.
        week_duration_days (int): The number of days in a rota week (usually 7).
        reset_history_after_weeks (int): (Compatibility arg, not used in new logic).
        use_db_for_history (bool): (Compatibility arg, not used in new logic).
        first_night_off_member (Team, optional): Member to have the first 'night_off'.

    Returns:
        tuple[list, int]: A tuple containing an empty list (for compatibility)
                          and the generated rota_id.
    """
    logger.info(f"Starting rota generation for {period_weeks} weeks from {start_date}.")
    rota_id = generate_unique_rota_id()
    
    # Clean up any previous data for this specific rota ID to prevent conflicts.
    db.session.query(Rota).filter(Rota.rota_id == rota_id).delete()
    db.session.query(MemberShiftState).filter(MemberShiftState.rota_id == rota_id).delete()
    db.session.commit()
    
    admins, non_admins = split_admins(eligible_members)
    last_night_shift_member = None
    
    # 1. Deterministically seed the initial state for each member's cycle.
    simple_states = seed_initial_states_if_missing(rota_id, non_admins, first_night_off_member)
    
    # 2. Build the main state dictionary to track counts and cycle positions.
    member_shift_states = {
        m.name: {
            'idx': simple_states.get(m.name, 0),
            'cycle': get_member_cycle(m),
            'counts': {'morning': 0, 'evening': 0, 'night': 0, 'night_off': 0}
        } for m in non_admins
    }
    
    # 3. Loop through each week and generate the rota.
    for week in range(period_weeks):
        current_date = start_date + timedelta(days=week * week_duration_days)
        week_end_date = current_date + timedelta(days=week_duration_days - 1)
        
        # Filter for members available to work during this specific week.
        week_eligible_members = filter_eligible_members(eligible_members, current_date, week_end_date)
        
        # Generate the weekly rota and get the member who worked the night shift.
        night_member, _ = _generate_weekly_rota(
            eligible_members=week_eligible_members,
            current_date=current_date,
            last_night_shift_member=last_night_shift_member,
            rota_id=rota_id,
            member_shift_states=member_shift_states,
            week_duration_days=week_duration_days,
        )
        
        # This member will be assigned 'night_off' in the next iteration.
        last_night_shift_member = night_member

    logger.info(f"Successfully generated Rota ID: {rota_id}.")
    # Return values in the format expected by the rota.py blueprint.
    return [], rota_id

