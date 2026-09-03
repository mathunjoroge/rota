# rota_pulp.py

import logging
from datetime import date, timedelta
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus, PULP_CBC_CMD
from models.models import db, Rota, RotaAssignment, Department, Team
from .rota_logic import generate_unique_rota_id, filter_eligible_members, display_rota_table

# Configure logging
logger = logging.getLogger(__name__)

def generate_rota_with_pulp(all_members, start_date, period_weeks, first_night_off_member=None, department_id=None):
    """
    Generates a fair and balanced rota using the PuLP optimization library.
    Optionally scoped to a specific department.

    Args:
        all_members (list[Team]): List of all Team member objects.
        start_date (date): The start date of the rota period.
        period_weeks (int): The number of weeks to generate.
        first_night_off_member (Team, optional): Member forced to have the first night off.
        department_id (int, optional): The ID of the department to filter members by.

    Returns:
        int: The unique ID of the generated rota, or None if no solution is found.
    """
    logger.info(f"--- Starting Rota Generation with PuLP for {period_weeks} weeks (Dept ID: {department_id}) ---")

    # If department_id is provided, filter members to those belonging to the department
    if department_id:
        all_members = [m for m in all_members if m.department_id == department_id]

    if not all_members:
        logger.error("No eligible members found for the specified department.")
        return [], None

    # 1. SETUP: Define the problem dimensions
    # ============================================
    rota_id = generate_unique_rota_id()
    weeks = range(period_weeks)
    shifts = ['morning', 'evening', 'night', 'night_off', 'on_leave']
    
    # Create a mapping for easy access to member properties
    member_map = {m.name: m for m in all_members}
    member_names = list(member_map.keys())

    # Identify non-admin members for fairness objective (admins always work mornings)
    non_admin_names = [m.name for m in all_members if m.is_admin != 1]

    # Pre-calculate weekly eligibility to handle leave
    weekly_eligible = {}
    for w in weeks:
        week_start = start_date + timedelta(days=w * 7)
        week_end = week_start + timedelta(days=6)
        eligible_for_week = filter_eligible_members(all_members, week_start, week_end)
        weekly_eligible[w] = {m.name for m in eligible_for_week}

    # 2. MODEL INITIALIZATION
    # ============================================
    model = LpProblem("Fair_Rota_Scheduling", LpMinimize)

    # 3. DECISION VARIABLES
    # ============================================
    # x(m, s, w) is 1 if member m works shift s in week w, 0 otherwise.
    assign = LpVariable.dicts("Assign", (member_names, shifts, weeks), cat='Binary')

    # Variables to track the number of special shifts for fairness objective
    special_shifts = ['evening', 'night']
    total_special_shifts = LpVariable.dicts("TotalSpecialShifts", non_admin_names, lowBound=0, cat='Integer')
    min_shifts = LpVariable("MinSpecialShifts", lowBound=0, cat='Integer')
    max_shifts = LpVariable("MaxSpecialShifts", lowBound=0, cat='Integer')

    # 4. OBJECTIVE FUNCTION: Minimize the gap between the most and least worked member
    # =================================================================================
    model += (max_shifts - min_shifts), "Minimize_Shift_Imbalance"

    # 5. CONSTRAINTS
    # =================================================================================
    logger.info("Defining model constraints...")

    for w in weeks:
        # Constraint: Each week must have exactly one evening, night, and night_off shift.
        for s in ['evening', 'night', 'night_off']:
            model += lpSum(assign[m][s][w] for m in weekly_eligible[w]) == 1, f"One_{s}_Shift_per_Week_{w}"

        for m_name in member_names:
            member = member_map[m_name]

            # Constraint: Each member must have exactly one assignment per week (work or leave).
            if m_name in weekly_eligible[w]:
                model += lpSum(assign[m_name][s][w] for s in shifts if s != 'on_leave') == 1, f"Member_{m_name}_One_Shift_Week_{w}"
                model += assign[m_name]['on_leave'][w] == 0, f"Member_{m_name}_Not_On_Leave_Week_{w}"

                # Member-specific shift exemptions (inside eligibility check to avoid
                # conflicting with on-leave constraints that force all work shifts to 0).
                if member.is_admin == 1:  # Admins only work mornings
                    model += assign[m_name]['morning'][w] == 1, f"Admin_{m_name}_Morning_Only_Week_{w}"
                if member.is_admin == 2:  # Evening exempt
                    model += assign[m_name]['evening'][w] == 0, f"Evening_Exempt_{m_name}_Week_{w}"
                if member.is_admin == 3:  # Night exempt
                    model += assign[m_name]['night'][w] == 0, f"Night_Exempt_{m_name}_Night_Week_{w}"
                    model += assign[m_name]['night_off'][w] == 0, f"Night_Exempt_{m_name}_NightOff_Week_{w}"
            else:
                model += assign[m_name]['on_leave'][w] == 1, f"Member_{m_name}_Is_On_Leave_Week_{w}"
                for s in shifts:
                    if s != 'on_leave':
                        model += assign[m_name][s][w] == 0, f"Member_{m_name}_No_{s}_On_Leave_Week_{w}"

    # Constraint: A night shift must be followed by a night_off shift.
    for w in range(period_weeks - 1):
        for m_name in member_names:
            model += assign[m_name]['night'][w] <= assign[m_name]['night_off'][w + 1], f"Night_Followed_By_NightOff_{m_name}_Week_{w}"

    # Constraint: If a specific member is chosen for the first night off.
    if first_night_off_member and first_night_off_member.name in weekly_eligible.get(0, set()):
        model += assign[first_night_off_member.name]['night_off'][0] == 1, f"Forced_First_NightOff_{first_night_off_member.name}"

    # Constraints for fairness objective (only non-admin members who rotate through special shifts)
    for m_name in non_admin_names:
        # Link total_special_shifts to the assignment variables
        model += total_special_shifts[m_name] == lpSum(assign[m_name][s][w] for s in special_shifts for w in weeks), f"Count_Special_Shifts_{m_name}"

        # Link min/max variables
        model += max_shifts >= total_special_shifts[m_name], f"Max_Shifts_Bound_{m_name}"
        model += min_shifts <= total_special_shifts[m_name], f"Min_Shifts_Bound_{m_name}"

    # 6. SOLVE THE MODEL
    # =================================================================================
    logger.info("Solving the optimization problem...")
    model.solve(PULP_CBC_CMD(msg=0)) # Use CBC solver, suppress verbose output

    # 7. PROCESS AND SAVE THE RESULTS
    # =================================================================================
    if LpStatus[model.status] == 'Optimal':
        logger.info("Optimal solution found! Processing and saving results.")
        
        # Clear any existing data for this new rota_id
        db.session.query(Rota).filter(Rota.rota_id == rota_id).delete()
        db.session.query(RotaAssignment).filter(RotaAssignment.rota_id == rota_id).delete()
        db.session.commit()

        for w in weeks:
            week_start = start_date + timedelta(days=w * 7)
            week_end = week_start + timedelta(days=6)
            week_range = f"{week_start.strftime('%Y-%m-%d')} - {week_end.strftime('%Y-%m-%d')}"
            
            assignments = {s: [] for s in shifts}
            for m_name in member_names:
                member_obj = member_map[m_name]
                for s in shifts:
                    if assign[m_name][s][w].varValue == 1:
                        assignments[s].append(m_name)
                        # Save normalized RotaAssignment
                        assignment_rec = RotaAssignment(
                            rota_id=rota_id,
                            department_id=department_id or member_obj.department_id,
                            member_id=member_obj.id,
                            shift_name=s,
                            date=week_start
                        )
                        db.session.add(assignment_rec)

            new_rota = Rota(
                rota_id=rota_id,
                department_id=department_id,
                date=week_start,
                week_range=week_range,
                shift_8_5=', '.join(sorted(assignments['morning'])),
                shift_5_8=assignments['evening'][0] if assignments['evening'] else '',
                shift_8_8=assignments['night'][0] if assignments['night'] else '',
                night_off=assignments['night_off'][0] if assignments['night_off'] else ''
            )
            db.session.add(new_rota)
        
        db.session.commit()
        logger.info(f"Successfully generated and saved Rota ID: {rota_id}")
        
        # Use the existing display function
        display_rota_table(rota_id)
        
        return [], rota_id
    else:
        logger.error(f"Could not find an optimal solution. Status: {LpStatus[model.status]}")
        return [], None