# rota_pulp.py

import logging
from datetime import date, timedelta
from pulp import LpProblem, LpMinimize, LpVariable, lpSum, LpStatus, PULP_CBC_CMD
from models.models import db, Rota, RotaAssignment, Department, Team, Shift
from .rota_logic import generate_unique_rota_id, filter_eligible_members, display_rota_table

# Configure logging
logger = logging.getLogger(__name__)

def generate_rota_with_pulp(all_members, start_date, period_weeks, first_night_off_member=None, department_id=None):
    """
    Generates a fair and balanced rota using the PuLP optimization library.
    Incorporates hospital departmental rules, staff level exemptions, and min/max coverage bounds.

    Args:
        all_members (list[Team]): List of all Team member objects.
        start_date (date): The start date of the rota period.
        period_weeks (int): The number of weeks to generate.
        first_night_off_member (Team, optional): Member forced to have the first night off.
        department_id (int, optional): The ID of the department to filter members by.

    Returns:
        tuple[list, int]: Empty list and the unique ID of the generated rota, or ([], None) if unsolvable.
    """
    logger.info(f"--- Starting Rota Generation with PuLP for {period_weeks} weeks (Dept ID: {department_id}) ---")

    # If department_id is provided, filter members to those belonging to the department
    if department_id:
        all_members = [m for m in all_members if m.department_id == department_id]

    if not all_members:
        logger.error("No eligible members found for the specified department.")
        return [], None

    # Fetch Department Shift coverage rules if defined
    min_evening, max_evening = 1, 1
    min_night, max_night = 1, 1
    min_morning, max_morning = 1, len(all_members)

    if department_id:
        dept_shifts = Shift.query.filter_by(department_id=department_id).all()
        for s in dept_shifts:
            s_name = s.name.lower()
            if 'evening' in s_name or '5-8' in s_name:
                min_evening = s.min_members if s.min_members is not None else 1
                max_evening = max(s.max_members if s.max_members is not None else 1, min_evening)
            elif 'night' in s_name or '8-8' in s_name:
                min_night = s.min_members if s.min_members is not None else 1
                max_night = max(s.max_members if s.max_members is not None else 1, min_night)
            elif 'morning' in s_name or '8-5' in s_name:
                min_morning = s.min_members if s.min_members is not None else 1

    # 1. SETUP: Define problem dimensions
    rota_id = generate_unique_rota_id()
    weeks = range(period_weeks)
    shifts = ['morning', 'evening', 'night', 'night_off', 'on_leave']

    member_map = {m.name: m for m in all_members}
    member_names = list(member_map.keys())

    # Non-admin members for fairness objective (admins/senior staff work mornings or dedicated shifts)
    non_admin_names = [m.name for m in all_members if m.is_admin != 1]

    # Pre-calculate weekly eligibility to handle leave
    weekly_eligible = {}
    for w in weeks:
        week_start = start_date + timedelta(days=w * 7)
        week_end = week_start + timedelta(days=6)
        eligible_for_week = filter_eligible_members(all_members, week_start, week_end)
        weekly_eligible[w] = {m.name for m in eligible_for_week}

    # 2. MODEL INITIALIZATION
    model = LpProblem("Fair_Hospital_Rota_Scheduling", LpMinimize)

    # 3. DECISION VARIABLES
    assign = LpVariable.dicts("Assign", (member_names, shifts, weeks), cat='Binary')

    special_shifts = ['evening', 'night']
    total_special_shifts = LpVariable.dicts("TotalSpecialShifts", non_admin_names, lowBound=0, cat='Integer')
    min_shifts = LpVariable("MinSpecialShifts", lowBound=0, cat='Integer')
    max_shifts = LpVariable("MaxSpecialShifts", lowBound=0, cat='Integer')

    # 4. OBJECTIVE FUNCTION: Shift fairness balance + staff preferences
    from models.models import StaffPreference
    pref_penalties = []
    for w in weeks:
        week_start = start_date + timedelta(days=w * 7)
        prefs = StaffPreference.query.filter_by(week_start=week_start).all()
        for p in prefs:
            if p.member and p.member.name in member_names:
                for s in ['evening', 'night']:
                    pref_penalties.append(10 * assign[p.member.name][s][w])

    model += (max_shifts - min_shifts) + lpSum(pref_penalties), "Minimize_Shift_Imbalance_And_Preference_Clashes"

    # 5. CONSTRAINTS
    logger.info("Defining model constraints for department rules...")

    for w in weeks:
        eligible_count = len(weekly_eligible[w])

        # Enforce shift minimum & maximum bounds per week
        eff_min_evening = min(min_evening, eligible_count)
        eff_min_night = min(min_night, eligible_count)

        model += lpSum(assign[m]['evening'][w] for m in weekly_eligible[w]) >= eff_min_evening, f"Min_Evening_Week_{w}"
        model += lpSum(assign[m]['evening'][w] for m in weekly_eligible[w]) <= max_evening, f"Max_Evening_Week_{w}"

        model += lpSum(assign[m]['night'][w] for m in weekly_eligible[w]) >= eff_min_night, f"Min_Night_Week_{w}"
        model += lpSum(assign[m]['night'][w] for m in weekly_eligible[w]) <= max_night, f"Max_Night_Week_{w}"

        # Night-off count matches previous night shift count requirement
        model += lpSum(assign[m]['night_off'][w] for m in weekly_eligible[w]) >= eff_min_night, f"Min_NightOff_Week_{w}"

        for m_name in member_names:
            member = member_map[m_name]

            if m_name in weekly_eligible[w]:
                model += lpSum(assign[m_name][s][w] for s in shifts if s != 'on_leave') == 1, f"Member_{m_name}_One_Shift_Week_{w}"
                model += assign[m_name]['on_leave'][w] == 0, f"Member_{m_name}_Not_On_Leave_Week_{w}"

                # Staff level & explicit shift exemption rules
                if member.is_admin == 1:  # Admin 1 / Dept Head: Morning only
                    model += assign[m_name]['morning'][w] == 1, f"Admin_{m_name}_Morning_Only_Week_{w}"

                if member.is_admin == 2 or getattr(member, 'exempt_evening', False):  # Admin 2 / Evening Exempt
                    model += assign[m_name]['evening'][w] == 0, f"Evening_Exempt_{m_name}_Week_{w}"

                if member.is_admin == 3 or getattr(member, 'exempt_night', False):  # Night Exempt
                    model += assign[m_name]['night'][w] == 0, f"Night_Exempt_{m_name}_Night_Week_{w}"
                    model += assign[m_name]['night_off'][w] == 0, f"Night_Exempt_{m_name}_NightOff_Week_{w}"
            else:
                model += assign[m_name]['on_leave'][w] == 1, f"Member_{m_name}_Is_On_Leave_Week_{w}"
                for s in shifts:
                    if s != 'on_leave':
                        model += assign[m_name][s][w] == 0, f"Member_{m_name}_No_{s}_On_Leave_Week_{w}"

    # Constraint: Night shift followed by night_off
    for w in range(period_weeks - 1):
        for m_name in member_names:
            model += assign[m_name]['night'][w] <= assign[m_name]['night_off'][w + 1], f"Night_Followed_By_NightOff_{m_name}_Week_{w}"

    # Forced first night off
    if first_night_off_member and first_night_off_member.name in weekly_eligible.get(0, set()):
        model += assign[first_night_off_member.name]['night_off'][0] == 1, f"Forced_First_NightOff_{first_night_off_member.name}"

    # Fairness objective
    for m_name in non_admin_names:
        model += total_special_shifts[m_name] == lpSum(assign[m_name][s][w] for s in special_shifts for w in weeks), f"Count_Special_Shifts_{m_name}"
        model += max_shifts >= total_special_shifts[m_name], f"Max_Shifts_Bound_{m_name}"
        model += min_shifts <= total_special_shifts[m_name], f"Min_Shifts_Bound_{m_name}"

    # 6. SOLVE MODEL
    logger.info("Solving the optimization problem...")
    model.solve(PULP_CBC_CMD(msg=0))

    # 7. PROCESS & SAVE RESULTS
    if LpStatus[model.status] == 'Optimal':
        logger.info("Optimal solution found! Processing and saving results.")
        
        db.session.query(Rota).filter(Rota.rota_id == rota_id).delete()
        db.session.query(RotaAssignment).filter(RotaAssignment.rota_id == rota_id).delete()
        db.session.commit()

        for w in weeks:
            week_start = start_date + timedelta(days=w * 7)
            week_end = week_start + timedelta(days=6)
            week_range = f"{week_start.strftime('%Y-%m-%d')} - {week_end.strftime('%Y-%m-%d')}"
            
            # Clear existing rotas for this department and date to avoid conflicts
            if department_id:
                db.session.query(Rota).filter(Rota.department_id == department_id, Rota.date == week_start).delete()
            else:
                db.session.query(Rota).filter(Rota.date == week_start).delete()
            db.session.commit()

            assignments = {s: [] for s in shifts}
            for m_name in member_names:
                member_obj = member_map[m_name]
                for s in shifts:
                    if assign[m_name][s][w].varValue == 1:
                        assignments[s].append(m_name)
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
                shift_5_8=', '.join(sorted(assignments['evening'])),
                shift_8_8=', '.join(sorted(assignments['night'])),
                night_off=', '.join(sorted(assignments['night_off']))
            )
            db.session.add(new_rota)
        
        db.session.commit()
        logger.info(f"Successfully generated and saved Rota ID: {rota_id}")
        
        display_rota_table(rota_id)
        return [], rota_id
    else:
        logger.error(f"Could not find an optimal solution. Status: {LpStatus[model.status]}")
        return [], None