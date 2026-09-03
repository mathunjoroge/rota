# -*- coding: utf-8 -*-
"""
rota_logic.py

This module contains the core business logic for generating a weekly staff rota.
It includes a deterministic method for predictable rotas and an optimization-based
method using PuLP for dynamically fair shift distribution.
"""

import logging
import random
from datetime import date, timedelta
from tabulate import tabulate
from colorama import init, Fore, Style
import pulp  # Added PuLP import for optimization
from models.models import db, Rota, Team, MemberShiftState, Leave

# Configure logging for this module
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize colorama for cross-platform colored output
init(autoreset=True)

# Base deterministic cycle for a standard member's shift rotation.
SHIFT_CYCLE = ['morning', 'night', 'night_off', 'morning', 'evening', 'morning']
CYCLE_LEN = len(SHIFT_CYCLE)


# ############################################################################
# NEW RotaOptimizer CLASS USING PuLP
# ############################################################################

class RotaOptimizer:
    """
    Generates a fair rota by using linear optimization (PuLP) to distribute
    special shifts ('evening', 'night') as evenly as possible among eligible
    members over a given period.
    """
    def __init__(self, start_date, period_weeks):
        """
        Initializes the RotaOptimizer.

        Args:
            start_date (date): The start date of the rota period.
            period_weeks (int): The number of weeks to generate.
        """
        self.start_date = start_date
        self.period_weeks = period_weeks
        self.week_duration_days = 7
        self.rota_id = generate_unique_rota_id()
        self.all_members = db.session.query(Team).all()

        # Clean up any previous entries for this new rota ID
        db.session.query(Rota).filter(Rota.rota_id == self.rota_id).delete()
        db.session.commit()

    def _filter_eligible_members(self, members, week_start_date):
        """Filters out members on leave for the given week."""
        week_end_date = week_start_date + timedelta(days=self.week_duration_days - 1)
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

    def _solve_weekly_assignment(self, non_admins, last_night_member_name, shift_history):
        """
        Solves the shift assignment for a single week using PuLP.

        Args:
            non_admins (list[Team]): List of non-admin members eligible for the week.
            last_night_member_name (str): Name of the member who worked night shift last week.
            shift_history (dict): A dict tracking counts of special shifts per member.

        Returns:
            dict: A dictionary with the shift assignments for the week or an error.
        """
        prob = pulp.LpProblem("Weekly_Fair_Rota", pulp.LpMinimize)

        # 1. Determine mandatory 'night_off' member
        night_off_member = next((m for m in non_admins if m.name == last_night_member_name), None)
        
        # 2. Define the pool of members available for shifts
        available_for_assignment = [m for m in non_admins if m != night_off_member]

        if len(available_for_assignment) < 2:
            return {"error": f"Not enough members ({len(available_for_assignment)}) available to cover evening and night shifts."}

        shifts_to_assign = ['evening', 'night']
        
        # 3. Define Decision Variables
        # x[member.name][shift] is 1 if member is assigned, 0 otherwise
        x = pulp.LpVariable.dicts("assignment",
                                  ((m.name for m in available_for_assignment), shifts_to_assign),
                                  cat='Binary')

        # 4. Define Objective Function: Fairness
        # We want to assign special shifts to members who have done them the least.
        # The objective is to minimize the total historical shift count of the members chosen.
        prob += pulp.lpSum([
            (shift_history[m.name]['evening'] + shift_history[m.name]['night']) * x[m.name][s]
            for m in available_for_assignment for s in shifts_to_assign
        ]), "Fairness_Objective"

        # 5. Define Constraints
        # Constraint 1: Each special shift must be covered by exactly one person.
        for s in shifts_to_assign:
            prob += pulp.lpSum([x[m.name][s] for m in available_for_assignment]) == 1, f"Cover_{s}_Shift"

        # Constraint 2: Each member can be assigned at most one special shift.
        for m in available_for_assignment:
            prob += pulp.lpSum([x[m.name][s] for s in shifts_to_assign]) <= 1, f"One_Special_Shift_for_{m.name}"

        # Constraint 3: Handle exemptions from member profiles.
        for m in available_for_assignment:
            if m.is_admin == 2:  # Evening exempt
                prob += x[m.name]['evening'] == 0, f"Exempt_Evening_{m.name}"
            if m.is_admin == 3:  # Night and Night Off exempt
                prob += x[m.name]['night'] == 0, f"Exempt_Night_{m.name}"
        
        # 6. Solve the problem
        prob.solve(pulp.PULP_CBC_CMD(msg=0)) # msg=0 suppresses solver output

        # 7. Extract and return the results
        if pulp.LpStatus[prob.status] == "Optimal":
            assignments = {
                'evening': None, 'night': None, 'morning': [],
                'night_off': night_off_member.name if night_off_member else None
            }
            assigned_special = set()

            for m in available_for_assignment:
                for s in shifts_to_assign:
                    if pulp.value(x[m.name][s]) == 1:
                        assignments[s] = m.name
                        assigned_special.add(m.name)
            
            assignments['morning'] = sorted([m.name for m in available_for_assignment if m.name not in assigned_special])
            return assignments
        else:
            return {"error": f"Could not find an optimal solution. Status: {pulp.LpStatus[prob.status]}"}

    def generate_rota(self):
        """
        Main method to generate the full rota for the specified period. It iterates
        week by week, solving for the fairest assignment at each step.
        
        Returns:
            tuple[list, int]: An empty list and the generated rota_id, or -1 on failure.
        """
        logger.info(f"Starting optimized rota generation with PuLP for Rota ID: {self.rota_id}")

        admins, non_admins = split_admins(self.all_members)
        shift_history = {m.name: {'evening': 0, 'night': 0} for m in non_admins}

        # --- MODIFIED SECTION START ---
        # Check for a previous rota to ensure continuity for the first 'night_off'.
        last_rota_entry = db.session.query(Rota).filter(Rota.date < self.start_date).order_by(Rota.date.desc()).first()
        if last_rota_entry and last_rota_entry.shift_8_8:
            last_night_shift_member_name = last_rota_entry.shift_8_8
            logger.info(f"Continuity from previous rota: Assigning {last_night_shift_member_name} as the first night_off.")
        else:
            last_night_shift_member_name = None # Start fresh if no history exists
        # --- MODIFIED SECTION END ---

        for week in range(self.period_weeks):
            current_date = self.start_date + timedelta(days=week * self.week_duration_days)
            week_eligible_members = self._filter_eligible_members(self.all_members, current_date)
            
            if not week_eligible_members:
                logger.warning(f"No eligible members for week starting {current_date}. Skipping.")
                continue

            week_admins, week_non_admins = split_admins(week_eligible_members)

            # Solve for this week's assignments using PuLP
            assignments = self._solve_weekly_assignment(
                week_non_admins,
                last_night_shift_member_name,
                shift_history
            )

            if not assignments or "error" in assignments:
                 logger.error(f"Optimization failed for week {current_date}: {assignments.get('error', 'Unknown error')}")
                 print(f"{Fore.RED}Could not generate rota for week {current_date}. Aborting.{Style.RESET_ALL}")
                 return [], -1
            
            # Update history and track who worked the night shift for next week's 'night_off'
            if assignments['evening']:
                shift_history[assignments['evening']]['evening'] += 1
            if assignments['night']:
                shift_history[assignments['night']]['night'] += 1
                last_night_shift_member_name = assignments['night']
            else:
                last_night_shift_member_name = None

            # Combine morning shift members (admins + unassigned non-admins)
            morning_members = sorted(
                [m.name for m in week_admins] + assignments['morning']
            )
            
            # Save the weekly result to the database
            week_range = f"{current_date.strftime('%Y-%m-%d')} - {(current_date + timedelta(days=6)).strftime('%Y-%m-%d')}"
            new_rota = Rota(
                rota_id=self.rota_id, date=current_date, week_range=week_range,
                shift_8_5=', '.join(morning_members),
                shift_5_8=assignments['evening'] or '',
                shift_8_8=assignments['night'] or '',
                night_off=assignments['night_off'] or ''
            )
            db.session.add(new_rota)
            db.session.commit()
        
        logger.info(f"Successfully generated optimized Rota ID: {self.rota_id}.")
        display_rota_table(self.rota_id)
        return [], self.rota_id



# ############################################################################
# ORIGINAL DETERMINISTIC LOGIC (UNCHANGED)
# ############################################################################

def generate_unique_rota_id():
    """
    Generates a unique 10-digit rota ID, ensuring it doesn't exist in the database.

    Returns:
        int: A unique 10-digit rota ID.
    """
    while True:
        rota_id = random.randint(10**9, 10**10 - 1)
        if not db.session.query(Rota).filter_by(rota_id=rota_id).first():
            return rota_id

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
    """
    Seeds initial shift states for non-admin members in the database.

    Args:
        rota_id (int): The unique ID of the rota.
        non_admins (list[Team]): List of non-admin Team member objects.
        first_night_off_member (Team, optional): Member to assign the first night_off shift.

    Returns:
        dict: A dictionary mapping member names to their initial shift indices.

    Raises:
        ValueError: If fewer than 3 non-admin members or if first_night_off_member is night-exempt.
    """
    logger.info(f"Seeding initial shift states for Rota ID: {rota_id}.")
    db.session.query(MemberShiftState).filter_by(rota_id=rota_id).delete()
    logger.info("Deleted existing shift states")
    db.session.commit()
    logger.info("Commit after delete successful")

    if len(non_admins) < 3:
        raise ValueError(f"Rota generation requires at least 3 non-admin members, but found {len(non_admins)}.")

    member_shift_states = {}
    night_off_index = 2 # This is the fixed index for 'night_off' in the SHIFT_CYCLE

    # Assign the specified first night_off member and protect their index.
    if first_night_off_member:
        if first_night_off_member.is_admin == 3:
            raise ValueError(f"Member {first_night_off_member.name} is night-exempt and cannot be assigned 'night_off'.")
        logger.info(f"Assigning {first_night_off_member.name} as the first night_off.")
        member_shift_states[first_night_off_member.name] = night_off_index

    # Sort the remaining members to ensure deterministic assignment.
    remaining_members = sorted([m for m in non_admins if m.name not in member_shift_states], key=lambda m: m.name)
    logger.info(f"Remaining members: {[m.name for m in remaining_members]}")
    
    # Create a list of indices available for the rest of the team, excluding the protected one.
    available_indices = [i for i in range(CYCLE_LEN) if i != night_off_index]
    
    # Assign the remaining members by cycling ONLY through the available indices.
    if not available_indices:
         raise ValueError("Cannot assign remaining members as no indices are available.")

    for i, member in enumerate(remaining_members):
        # This cycles through [0, 1, 3, 4, 5] and wraps around if needed.
        current_index = available_indices[i % len(available_indices)]
        member_shift_states[member.name] = current_index
        logger.info(f"Assigned {member.name} to index {current_index}")

    # Persist the final, correct states to the database.
    logger.info("Persisting shift states to database")
    for member_name, shift_index in member_shift_states.items():
        logger.info(f"Adding state for {member_name}: shift_index={shift_index}")
        db.session.add(MemberShiftState(rota_id=rota_id, member_name=member_name, shift_index=shift_index))
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
    """
    Generates a single week's rota, enforcing shift constraints and updating states.

    Args:
        eligible_members (list[Team]): Members eligible for the week.
        current_date (date): The start date of the week.
        last_night_shift_member (Team): Member who worked the night shift last week.
        rota_id (int): The unique ID of the rota.
        member_shift_states (dict): Current shift states for non-admin members.
        week_duration_days (int): Number of days in a week (default: 7).

    Returns:
        tuple[Team, Team]: The members assigned to night and evening shifts.
    """
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

    # Rule 2: Build candidate pools, enforcing morning after evening/night_off.
    pools = {'morning': [], 'evening': [], 'night': [], 'night_off': []}
    for m in available:
        state = member_shift_states[m.name]
        preferred_shift = state['cycle'][state['idx']]
        if 'last_shift' in state and state['last_shift'] in ['evening', 'night_off'] and preferred_shift != 'morning':
            logger.info(f"Forcing {m.name} to morning due to {state['last_shift']} last week")
            preferred_shift = 'morning'
        pools[preferred_shift].append(m)

    # Helper: Pick the best candidate, capping special shifts at 3.
    def pick_best(candidates, shift_type):
        if not candidates:
            return None
        # Filter candidates based on exemptions
        if shift_type == 'evening':
            candidates = [m for m in candidates if m.is_admin != 2]
        elif shift_type == 'night':
            candidates = [m for m in candidates if m.is_admin != 3]
        elif shift_type == 'night_off':
            candidates = [m for m in candidates if m.is_admin != 3]
        if not candidates:
            return None
        # Exclude members with 3 or more of this shift type
        candidates = [m for m in candidates if member_shift_states[m.name]['counts'][shift_type] < 3]
        if not candidates:
            return None
        # Prefer members with fewer shifts of this type, then total special shifts
        return sorted(candidates, key=lambda m: (
            member_shift_states[m.name]['counts'][shift_type],  # Prefer 0 or 1 shifts
            sum(member_shift_states[m.name]['counts'][s] for s in ['evening', 'night', 'night_off']),
            m.name
        ))[0]

    # Sequentially fill remaining special shifts.
    for shift in ['night_off', 'evening', 'night']:
        if assignments[shift]:
            continue

        # Try to assign from members due for this shift.
        candidate = pick_best(pools[shift], shift)
        
        # If no one is due, borrow from morning pool.
        if not candidate:
            candidate = pick_best(pools['morning'], shift)
            if candidate:
                logger.info(f"No one is due for {shift}. Borrowing {candidate.name} from morning pool.")

        if candidate:
            logger.info(f"Assigning {candidate.name} to {shift}.")
            assignments[shift] = candidate
            available.remove(candidate)
            for pool in pools.values():
                if candidate in pool:
                    pool.remove(candidate)
                    break
    
    # All remaining non-admins and admins are assigned to morning.
    final_morning_members = [m.name for m in admins] + [m.name for m in available]

    # Update counts, last shift, and cycle index.
    for member in non_admins:
        state = member_shift_states[member.name]
        if member == assignments['evening']:
            state['counts']['evening'] += 1
            state['last_shift'] = 'evening'
        elif member == assignments['night']:
            state['counts']['night'] += 1
            state['last_shift'] = 'night'
        elif member == assignments['night_off']:
            state['counts']['night_off'] += 1
            state['last_shift'] = 'night_off'
        else:
            state['counts']['morning'] += 1
            state['last_shift'] = 'morning'
        state['idx'] = (state['idx'] + 1) % len(state['cycle'])

    # Save the rota entry.
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

def display_rota_table(rota_id):
    """
    Displays the rota for a given rota_id in a tabulated format in the console with colored output.

    Args:
        rota_id (int): The unique ID of the rota to display.
    """
    logger.info(f"Displaying rota table for Rota ID: {rota_id}")
    
    # Query all rota entries for the given rota_id
    rota_entries = db.session.query(Rota).filter_by(rota_id=rota_id).order_by(Rota.date).all()
    
    if not rota_entries:
        logger.warning(f"No rota entries found for Rota ID: {rota_id}")
        print(f"{Fore.RED}No rota entries found for Rota ID: {rota_id}{Style.RESET_ALL}")
        return
    
    # Prepare table data
    table_data = []
    headers = [
        f"{Fore.CYAN}Week Range{Style.RESET_ALL}",
        f"{Fore.GREEN}Morning (8-5){Style.RESET_ALL}",
        f"{Fore.YELLOW}Evening (5-8){Style.RESET_ALL}",
        f"{Fore.MAGENTA}Night (8-8){Style.RESET_ALL}",
        f"{Fore.BLUE}Night Off{Style.RESET_ALL}"
    ]
    
    for entry in rota_entries:
        table_data.append([
            entry.week_range,
            f"{Fore.GREEN}{entry.shift_8_5}{Style.RESET_ALL}",
            f"{Fore.YELLOW}{entry.shift_5_8 or '-'}{Style.RESET_ALL}",
            f"{Fore.MAGENTA}{entry.shift_8_8 or '-'}{Style.RESET_ALL}",
            f"{Fore.BLUE}{entry.night_off or '-'}{Style.RESET_ALL}"
        ])
    
    # Print the table using tabulate
    print(f"\n{Fore.CYAN}Rota ID: {rota_id}{Style.RESET_ALL}")
    print(tabulate(table_data, headers=headers, tablefmt="fancy_grid"))
    logger.info(f"Displayed rota table for Rota ID: {rota_id}")

def generate_period_rota(eligible_members, start_date, period_weeks, week_duration_days=7, reset_history_after_weeks=6, use_db_for_history=True, first_night_off_member=None):
    """
    Generates a rota for a specified period, storing it in the database and displaying it as a colored table.

    Args:
        eligible_members (list[Team]): List of eligible Team member objects.
        start_date (date): The start date of the rota.
        period_weeks (int): Number of weeks to generate the rota for.
        week_duration_days (int): Number of days in a week (default: 7).
        reset_history_after_weeks (int): Weeks after which to reset shift history (default: 6).
        use_db_for_history (bool): Whether to use the database for shift history (default: True).
        first_night_off_member (Team, optional): Member to assign the first night_off shift.

    Returns:
        tuple[list, int]: An empty list (for compatibility) and the generated rota_id.
    """
    logger.info(f"Starting rota generation for {period_weeks} weeks from {start_date}.")
    rota_id = generate_unique_rota_id()
    
    db.session.query(Rota).filter(Rota.rota_id == rota_id).delete()
    db.session.query(MemberShiftState).filter(MemberShiftState.rota_id == rota_id).delete()
    db.session.commit()
    
    admins, non_admins = split_admins(eligible_members)
    
    # --- MODIFIED SECTION START ---
    # If a first night_off member isn't specified, check the last rota for continuity.
    if not first_night_off_member:
        last_rota_entry = db.session.query(Rota).filter(Rota.date < start_date).order_by(Rota.date.desc()).first()
        if last_rota_entry and last_rota_entry.shift_8_8:
            last_night_worker_name = last_rota_entry.shift_8_8
            # Find the full member object from the current list of eligible members.
            potential_member = next((m for m in eligible_members if m.name == last_night_worker_name), None)
            if potential_member:
                first_night_off_member = potential_member
                logger.info(f"Continuity from previous rota: Assigning {first_night_off_member.name} as the first night_off.")
    # --- MODIFIED SECTION END ---
    
    last_night_shift_member = None
    
    # Seed initial states.
    simple_states = seed_initial_states_if_missing(rota_id, non_admins, first_night_off_member)
    
    # Build state dictionary with last_shift.
    member_shift_states = {
        m.name: {
            'idx': simple_states.get(m.name, 0),
            'cycle': get_member_cycle(m),
            'counts': {'morning': 0, 'evening': 0, 'night': 0, 'night_off': 0},
            'last_shift': 'morning'
        } for m in non_admins
    }
    
    # Generate rota for each week.
    for week in range(period_weeks):
        current_date = start_date + timedelta(days=week * week_duration_days)
        week_end_date = current_date + timedelta(days=week_duration_days - 1)
        
        week_eligible_members = filter_eligible_members(eligible_members, current_date, week_end_date)
        
        night_member, _ = _generate_weekly_rota(
            eligible_members=week_eligible_members,
            current_date=current_date,
            last_night_shift_member=last_night_shift_member,
            rota_id=rota_id,
            member_shift_states=member_shift_states,
            week_duration_days=week_duration_days,
        )
        
        last_night_shift_member = night_member

    logger.info(f"Successfully generated Rota ID: {rota_id}.")
    
    # Display the generated rota as a colored table
    display_rota_table(rota_id)
    
    return [], rota_id