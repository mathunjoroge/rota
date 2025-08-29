import random
from datetime import datetime, timedelta

# --- Data Structures (Classes remain the same) ---
class TeamMember:
    def __init__(self, name, is_admin=0):
        self.name = name
        self.is_admin = is_admin

class Rota:
    def __init__(self, rota_id, week_range, shift_8_5, shift_5_8, shift_8_8, night_off, date):
        self.rota_id = rota_id
        self.week_range = week_range
        self.shift_8_5 = shift_8_5
        self.shift_5_8 = shift_5_8
        self.shift_8_8 = shift_8_8
        self.night_off = night_off
        self.date = date

# --- Initialization ---
members = [
    TeamMember("njoroge mathu", is_admin=1),
    TeamMember("betsy awino"),
    TeamMember("margaret okinyi"),
    TeamMember("Erick Onyango"),
    TeamMember("David Meyo"),
    TeamMember("lewis omollo"),
    TeamMember("elijah omondi")
]

# The defined 6-step cycle for the 6 non-admin members
shift_cycle = ['morning', 'night', 'night_off', 'morning', 'evening', 'morning']

# Initial state: Each non-admin member is placed at a unique starting point in the cycle.
# This ensures shifts are covered from week 1.
member_shift_states = {
    "betsy awino": 0,     # Starts at cycle index 0: morning
    "margaret okinyi": 1, # Starts at cycle index 1: night
    "Erick Onyango": 2,   # Starts at cycle index 2: night_off
    "David Meyo": 3,      # Starts at cycle index 3: morning
    "lewis omollo": 4,    # Starts at cycle index 4: evening
    "elijah omondi": 5    # Starts at cycle index 5: morning
}

rotas = [] # This will hold the final, perfect rota

def generate_perfect_rota(start_date_str, num_weeks):
    """
    Generates a perfectly balanced rota for a given period using a deterministic, cyclical approach.
    """
    global rota_id
    start_date = datetime.strptime(start_date_str, "%d/%m/%Y").date()
    non_admin_members = [m for m in members if not m.is_admin]
    admin_member = next(m for m in members if m.is_admin)

    for week_num in range(num_weeks):
        current_date = start_date + timedelta(days=week_num * 7)
        week_end_date = current_date + timedelta(days=6)
        week_range = f"{current_date.strftime('%d/%m/%Y')} - {week_end_date.strftime('%d/%m/%Y')}"

        # Initialize shift assignments for the week
        morning_shift_members = [admin_member.name]
        evening_shift_member = None
        night_shift_member = None
        night_off_member = None

        # Deterministically assign shifts based on the cycle
        for member in non_admin_members:
            # Get the member's current position in the cycle
            current_index = member_shift_states[member.name]
            current_shift = shift_cycle[current_index]

            # Assign member to the correct shift for this week
            if current_shift == 'morning':
                morning_shift_members.append(member.name)
            elif current_shift == 'evening':
                evening_shift_member = member.name
            elif current_shift == 'night':
                night_shift_member = member.name
            elif current_shift == 'night_off':
                night_off_member = member.name
            
            # **Crucially, advance the member to the next step for the next week**
            member_shift_states[member.name] = (current_index + 1) % len(shift_cycle)

        # Create and store the rota for the week
        week_rota = Rota(
            rota_id=2342 + week_num,
            week_range=week_range,
            shift_8_5=', '.join(morning_shift_members),
            shift_5_8=evening_shift_member,
            shift_8_8=night_shift_member,
            night_off=night_off_member,
            date=current_date
        )
        rotas.append(week_rota)

def print_final_rota():
    """Prints the generated rota in a formatted table."""
    print("\n✅ Perfect Rota Generated for 01/09/2025 - 16/11/2025:")
    print(f"{'Week':<6} {'Date Range':<22} {'Morning Shift':<55} {'Evening Shift':<18} {'Night Shift':<18} {'Night Off':<18}")
    print("-" * 140)
    for i, rota in enumerate(rotas, 1):
        print(f"{i:<6} {rota.week_range:<22} {rota.shift_8_5:<55} {rota.shift_5_8:<18} {rota.shift_8_8:<18} {rota.night_off:<18}")

def print_shift_summary():
    """Prints the final count of shifts per member to verify balance."""
    print("\n📊 Final Shift Distribution Summary:")
    print("-" * 70)
    for member in members:
        if member.is_admin: continue
        morning = sum(1 for r in rotas if member.name in r.shift_8_5.split(', '))
        evening = sum(1 for r in rotas if member.name == r.shift_5_8)
        night = sum(1 for r in rotas if member.name == r.shift_8_8)
        night_off = sum(1 for r in rotas if member.name == r.night_off)
        print(f"{member.name:<18} Morning: {morning}, Evening: {evening}, Night: {night}, Night Off: {night_off}")
    print("-" * 70)
    print("Each member has completed the 6-step cycle exactly twice (12 weeks).")


# --- Main Execution ---
if __name__ == "__main__":
    generate_perfect_rota(start_date_str="01/09/2025", num_weeks=12)
    print_final_rota()
    print_shift_summary()