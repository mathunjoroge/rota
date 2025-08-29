from datetime import datetime, timedelta
from tabulate import tabulate
import pandas as pd

# ==============================
# CONFIGURATION
# ==============================
team_members = [
    "Njoroge Mathu",  # Admin, always morning
    "Alice", "Bob", "Charlie", "Diana", "Eve", "Frank"
]

shift_cycle = ["morning", "night", "night_off", "morning", "evening", "morning"]

# Offsets ensure fair rotation
member_shift_states = {
    "Alice": 0,
    "Bob": 1,
    "Charlie": 2,
    "Diana": 3,
    "Eve": 4,
    "Frank": 5,
}

admin_member = "Njoroge Mathu"
start_date = datetime.strptime("2025-09-01", "%Y-%m-%d")
weeks_to_generate = 12

# ==============================
# ROTA GENERATION
# ==============================
rota = []
for week in range(1, weeks_to_generate + 1):
    week_start = start_date + timedelta(weeks=week - 1)
    week_end = week_start + timedelta(days=6)
    week_data = {"week": week, "start": week_start.date(), "end": week_end.date(), "shifts": []}
    
    # Admin always morning
    week_data["shifts"].append({"member": admin_member, "shift": "morning"})
    
    # Rotating shifts for others
    for member, offset in member_shift_states.items():
        cycle_index = (week - 1 + offset) % len(shift_cycle)
        week_data["shifts"].append({"member": member, "shift": shift_cycle[cycle_index]})
    
    rota.append(week_data)

# ==============================
# DISPLAY ROTA IN TABLES
# ==============================
for week in rota:
    headers = ["Member", "Shift"]
    rows = [(shift["member"], shift["shift"]) for shift in week["shifts"]]
    print(f"\n📅 Week {week['week']} ({week['start']} → {week['end']})")
    print(tabulate(rows, headers=headers, tablefmt="grid"))

# ==============================
# EXPORT TO EXCEL (optional)
# ==============================
all_rows = []
for week in rota:
    for shift in week["shifts"]:
        all_rows.append({
            "Week": week["week"],
            "Start Date": week["start"],
            "End Date": week["end"],
            "Member": shift["member"],
            "Shift": shift["shift"]
        })

df = pd.DataFrame(all_rows)
df.to_excel("rota.xlsx", index=False)
print("\n✅ Rota exported to rota.xlsx")
