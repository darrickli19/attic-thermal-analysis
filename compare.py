import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import subprocess
import pandas as pd
import numpy as np
import os
import requests
import io
import sys
from datetime import date

# ── CONFIG ─────────────────────────────────────────────────────────────────────
MOOSE_EXECUTABLE  = "moose-opt"
INPUT_FILE        = "attic.i"
TIMESTAMP_COLUMN  = "Timestamp"
SENSOR2_COLUMN    = "Sensor2_C"
SENSOR1_COLUMN    = "Sensor1_C"
SENSOR0_COLUMN    = "Sensor0_C"

SHEETS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ4L5OM-7F5fdqM_hsN7a8bDson6iTU4VgxNqDPoCiGhB0GKIc_dY2usliTCLjEolziN0OB8d6OXvsE/pub?gid=869676502&single=true&output=csv"

K_INSULATION          = 0.04
COLD_TEMP             = 24.44
CEILING_AREA_M2       = 154.4
AC_COP                = 3.0
COOLING_HOURS         = 4380
ELECTRICITY_RATE      = 0.12
INSULATION_COST_PER_INCH = 150

scenarios = [
    {"name": "R-19 (very low)",  "thickness": 0.152, "inches": 6},
    {"name": "R-38 (code min)",  "thickness": 0.305, "inches": 12},
    {"name": "R-51 (current)",   "thickness": 0.406, "inches": 16},
    {"name": "R-63 (upgrade)",   "thickness": 0.508, "inches": 20},
    {"name": "R-76 (very high)", "thickness": 0.610, "inches": 24},
]
colors = ['#e74c3c', '#e67e22', '#2ecc71', '#3498db', '#9b59b6']

# ── DATE ARGUMENT ──────────────────────────────────────────────────────────────
# Usage:
#   python run_scenarios.py              → uses today
#   python run_scenarios.py 2026-06-15   → uses that specific date
if len(sys.argv) > 1:
    RUN_DATE = sys.argv[1]
    try:
        pd.to_datetime(RUN_DATE)  # validate format
    except ValueError:
        print(f"Invalid date format: {RUN_DATE}. Use YYYY-MM-DD.")
        sys.exit(1)
else:
    RUN_DATE = date.today().strftime('%Y-%m-%d')

print(f"\n{'='*60}")
print(f"RUN DATE: {RUN_DATE}")
print(f"{'='*60}\n")

# ── DATED OUTPUT DIRS ──────────────────────────────────────────────────────────
output_dir   = f"output/{RUN_DATE}"
analysis_dir = f"analysis/{RUN_DATE}"
daily_dir    = f"data/daily"

os.makedirs(output_dir,   exist_ok=True)
os.makedirs(analysis_dir, exist_ok=True)
os.makedirs(daily_dir,    exist_ok=True)

# ── 1. FETCH DATA FROM GOOGLE SHEETS ──────────────────────────────────────────
print("Fetching sensor data from Google Sheets...")
try:
    response = requests.get(SHEETS_URL, timeout=10)
    response.raise_for_status()
    sensor_data = pd.read_csv(io.StringIO(response.text))
    sensor_data[TIMESTAMP_COLUMN] = pd.to_datetime(sensor_data[TIMESTAMP_COLUMN])
    sensor_data = sensor_data.sort_values(TIMESTAMP_COLUMN).reset_index(drop=True)
    sensor_data.to_csv('data/sensor_readings.csv', index=False)
    print(f"Fetched {len(sensor_data)} total rows from Google Sheets")
except Exception as e:
    print(f"Google Sheets fetch failed: {e}")
    print("Falling back to local sensor_readings.csv...")
    try:
        sensor_data = pd.read_csv('data/sensor_readings.csv')
        sensor_data[TIMESTAMP_COLUMN] = pd.to_datetime(sensor_data[TIMESTAMP_COLUMN])
        print(f"Loaded {len(sensor_data)} rows from local backup")
    except FileNotFoundError:
        print("No local data found. Run generate_fake_data.py first.")
        sys.exit(1)

# ── 2. FILTER TO RUN DATE ──────────────────────────────────────────────────────
day_data = sensor_data[
    sensor_data[TIMESTAMP_COLUMN].dt.strftime('%Y-%m-%d') == RUN_DATE
].copy().reset_index(drop=True)

if len(day_data) == 0:
    print(f"\nNo data found for {RUN_DATE}.")
    print(f"Available dates: {sorted(sensor_data[TIMESTAMP_COLUMN].dt.strftime('%Y-%m-%d').unique())}")
    sys.exit(1)

print(f"Filtered to {RUN_DATE}: {len(day_data)} rows")
print(f"Sensor 2 — avg: {day_data[SENSOR2_COLUMN].mean():.2f}°C  "
      f"min: {day_data[SENSOR2_COLUMN].min():.2f}°C  "
      f"max: {day_data[SENSOR2_COLUMN].max():.2f}°C")

hot_temp = day_data[SENSOR2_COLUMN].mean()

# ── 3. GENERATE MOOSE BC FILE FROM TODAY'S SENSOR 2 ───────────────────────────
print("\nGenerating MOOSE BC file...")
day_data['time_seconds'] = (
    day_data[TIMESTAMP_COLUMN] - day_data[TIMESTAMP_COLUMN].iloc[0]
).dt.total_seconds()

bc_file = f"{daily_dir}/{RUN_DATE}_bc.csv"
bc_df = day_data[['time_seconds', SENSOR2_COLUMN]].copy()
bc_df.columns = ['time', 'temperature']

# Add one extra row past the end so MOOSE doesn't run out of BC data
last_time = bc_df['time'].iloc[-1] + 60
last_temp = bc_df['temperature'].iloc[-1]
bc_df = pd.concat([bc_df, pd.DataFrame({'time': [last_time], 'temperature': [last_temp]})],
                  ignore_index=True)

bc_df.to_csv(bc_file, index=False, header=False)
bc_df.to_csv('data/sensor2_bc.csv', index=False, header=False)  # MOOSE always reads this path

end_time = min(int(bc_df['time'].iloc[-2]), 86400)  # cap at 1 day
print(f"BC file written: {bc_file} ({len(bc_df)} rows, {end_time/3600:.1f} hours)")

# ── 4. RUN MOOSE FOR EACH SCENARIO ────────────────────────────────────────────
print("\nRunning MOOSE simulations...")
for s in scenarios:
    label = s['name'].replace(' ', '_').replace('(', '').replace(')', '')
    out_base = f"{output_dir}/{label}"
    print(f"  {s['name']}...", end=' ', flush=True)
    result = subprocess.run([
        MOOSE_EXECUTABLE,
        "-i", INPUT_FILE,
        f"insulation_thickness={s['thickness']}",
        f"Executioner/end_time={end_time}",
        f"Outputs/file_base={out_base}"
    ], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR")
        print(result.stderr[-300:])
    else:
        print(f"Done")

# ── 5. STEADY STATE HEAT FLUX AND DOLLARS ─────────────────────────────────────
print(f"\n{'='*60}")
print(f"STEADY STATE RESULTS — {RUN_DATE}")
print(f"{'='*60}")

results = []
for s in scenarios:
    delta_T     = hot_temp - COLD_TEMP
    heat_flux   = K_INSULATION * delta_T / s['thickness']
    total_watts = heat_flux * CEILING_AREA_M2
    ac_watts    = total_watts / AC_COP
    annual_kwh  = ac_watts * COOLING_HOURS / 1000
    annual_cost = annual_kwh * ELECTRICITY_RATE
    results.append({
        "name": s['name'], "inches": s['inches'],
        "thickness": s['thickness'], "heat_flux": heat_flux,
        "total_watts": total_watts, "annual_cost": annual_cost,
    })

current = next(r for r in results if "current" in r['name'].lower())
upgrade = next(r for r in results if "upgrade" in r['name'].lower())

print(f"\n{'Scenario':<25} {'In':>4} {'Heat Flux':>12} {'Annual Cost':>13} {'vs Current':>12}")
print("-"*70)
for r in results:
    savings = current['annual_cost'] - r['annual_cost']
    s_str = f"${savings:+.0f}/yr" if r['name'] != current['name'] else "baseline"
    print(f"{r['name']:<25} {r['inches']:>3}\"  "
          f"{r['heat_flux']:>9.2f} W/m²  ${r['annual_cost']:>9.0f}/yr  {s_str:>12}")

added   = upgrade['inches'] - current['inches']
u_cost  = added * INSULATION_COST_PER_INCH
savings = current['annual_cost'] - upgrade['annual_cost']
if savings > 0:
    print(f"\nUpgrade cost (add {added}\"): ${u_cost:.0f}")
    print(f"Annual savings: ${savings:.0f}/yr")
    print(f"Payback period: {u_cost/savings:.1f} years")

# ── 6. PLOT: STEADY STATE BARS ─────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle(f'Attic Insulation Analysis — {RUN_DATE}\n'
             f'Sensor 2 avg: {hot_temp:.1f}°C  |  Thermostat: {COLD_TEMP}°C  |  '
             f'House: {CEILING_AREA_M2}m²', fontsize=13)

names  = [r['name'] for r in results]
fluxes = [r['heat_flux'] for r in results]
costs  = [r['annual_cost'] for r in results]

ax1 = axes[0]
bars = ax1.bar(names, fluxes, color=colors)
ax1.set_ylabel('Heat Flux (W/m²)')
ax1.set_title('Heat Flux Through Ceiling')
ax1.set_xticks(range(len(names)))
ax1.set_xticklabels(names, rotation=15, ha='right')
for bar, val in zip(bars, fluxes):
    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
             f'{val:.2f}', ha='center', va='bottom', fontsize=9)

ax2 = axes[1]
bars2 = ax2.bar(names, costs, color=colors)
ax2.set_ylabel('Annual AC Cost from Ceiling ($/yr)')
ax2.set_title('Estimated Annual Cooling Cost')
ax2.set_xticks(range(len(names)))
ax2.set_xticklabels(names, rotation=15, ha='right')
for bar, val in zip(bars2, costs):
    ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
             f'${val:.0f}', ha='center', va='bottom', fontsize=9)

plt.tight_layout()
path = f"{analysis_dir}/insulation_comparison.png"
plt.savefig(path, dpi=150)
print(f"\nSaved: {path}")

# ── 7. PLOT: TEMPERATURE PROFILES ─────────────────────────────────────────────
fig2, ax3 = plt.subplots(figsize=(10, 6))
for s, color in zip(scenarios, colors):
    thickness = s['thickness']
    total  = thickness + 0.016
    R_ins  = thickness / K_INSULATION
    R_dry  = 0.016 / 0.17
    R_tot  = R_ins + R_dry
    T_int  = hot_temp - (hot_temp - COLD_TEMP) * (R_ins / R_tot)
    x = [0, thickness * 1000, total * 1000]
    T = [hot_temp, T_int, COLD_TEMP]
    ax3.plot(x, T, color=color, linewidth=2.5, label=s['name'])
    ax3.plot(thickness * 1000, T_int, 'o', color=color, markersize=6)
    ax3.axvline(x=thickness * 1000, color=color, linestyle='--', alpha=0.3)

ax3.set_xlabel('Position through ceiling (mm)')
ax3.set_ylabel('Temperature (°C)')
ax3.set_title(f'Temperature Profile Through Ceiling — {RUN_DATE}\n'
              f'Hot side: {hot_temp:.1f}°C  |  Cold side: {COLD_TEMP}°C')
ax3.legend()
ax3.grid(True, alpha=0.3)
plt.tight_layout()
path = f"{analysis_dir}/temperature_profiles.png"
plt.savefig(path, dpi=150)
print(f"Saved: {path}")

# ── 8. PLOT: TRANSIENT ANALYSIS ────────────────────────────────────────────────
print("\nGenerating transient plots...")
time_hours = day_data['time_seconds'] / 3600

fig3, axes2 = plt.subplots(2, 1, figsize=(14, 10))
fig3.suptitle(f'Transient Analysis — {RUN_DATE}', fontsize=13)
ax4, ax5 = axes2

# Plot all 3 sensors as context
ax4.plot(time_hours, day_data[SENSOR0_COLUMN], color='gray',
         linewidth=1, linestyle=':', label='Sensor 0 (vent proxy)', alpha=0.6)
ax4.plot(time_hours, day_data[SENSOR1_COLUMN], color='gray',
         linewidth=1, linestyle='--', label='Sensor 1 (attic air)', alpha=0.6)
ax4.plot(time_hours, day_data[SENSOR2_COLUMN], 'k-',
         linewidth=2, label='Sensor 2 (insulation surface — MOOSE hot BC)')

# Load MOOSE output for each scenario and plot ceiling surface temperature
for s, color in zip(scenarios, colors):
    label    = s['name'].replace(' ', '_').replace('(', '').replace(')', '')
    csv_path = f"{output_dir}/{label}_csv.csv"
    try:
        df = pd.read_csv(csv_path)
        time_col  = df.columns[0]
        temp_cols = [c for c in df.columns if 'Temperature' in c or 'temperature' in c]
        if not temp_cols:
            print(f"  No temperature columns in {csv_path}")
            continue
        t_hrs = df[time_col] / 3600
        # Ceiling surface = node at x = total thickness = last x position
        # Take the column with the lowest average temperature (coldest = closest to cold BC)
        coldest_col = min(temp_cols, key=lambda c: df[c].mean())
        ax4.plot(t_hrs, df[coldest_col], color=color, linewidth=1.8,
                 label=f"{s['name']} — ceiling surface")

        # Heat flux over time
        hottest_col = max(temp_cols, key=lambda c: df[c].mean())
        flux_t = K_INSULATION * (df[hottest_col] - COLD_TEMP) / s['thickness']
        ax5.plot(t_hrs, flux_t, color=color, linewidth=1.8, label=s['name'])

    except FileNotFoundError:
        print(f"  MOOSE output not found: {csv_path}")

ax4.set_xlabel('Hour of day')
ax4.set_ylabel('Temperature (°C)')
ax4.set_title('Sensor Readings vs MOOSE Predicted Ceiling Surface Temperature\n'
              '(Black = measured attic floor input, colored = predicted ceiling surface below)')
ax4.legend(fontsize=8)
ax4.grid(True, alpha=0.3)

ax5.set_xlabel('Hour of day')
ax5.set_ylabel('Heat Flux (W/m²)')
ax5.set_title('Heat Flux Through Ceiling Over Time')
ax5.legend(fontsize=8)
ax5.grid(True, alpha=0.3)

plt.tight_layout()
path = f"{analysis_dir}/transient_analysis.png"
plt.savefig(path, dpi=150)
print(f"Saved: {path}")

# ── 9. APPEND TO DAILY SUMMARY ────────────────────────────────────────────────
summary_file = 'data/daily_summary.csv'
current_result = next(r for r in results if "current" in r['name'].lower())

summary_row = pd.DataFrame([{
    'date':           RUN_DATE,
    'avg_sensor2_C':  round(hot_temp, 2),
    'max_sensor2_C':  round(day_data[SENSOR2_COLUMN].max(), 2),
    'min_sensor2_C':  round(day_data[SENSOR2_COLUMN].min(), 2),
    'avg_sensor1_C':  round(day_data[SENSOR1_COLUMN].mean(), 2),
    'avg_heat_flux':  round(current_result['heat_flux'], 3),
    'annual_cost_est': round(current_result['annual_cost'], 2),
    'rows_logged':    len(day_data),
}])

if os.path.exists(summary_file):
    summary = pd.read_csv(summary_file)
    # Update existing row for this date or append
    summary = summary[summary['date'] != RUN_DATE]
    summary = pd.concat([summary, summary_row], ignore_index=True)
else:
    summary = summary_row

summary = summary.sort_values('date').reset_index(drop=True)
summary.to_csv(summary_file, index=False)
print(f"Saved: {summary_file}")

# ── DONE ──────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"DONE — {RUN_DATE}")
print(f"  output/{RUN_DATE}/          — MOOSE exodus + CSV files")
print(f"  analysis/{RUN_DATE}/        — 3 PNG figures")
print(f"  data/daily/{RUN_DATE}_bc.csv — BC file for this day")
print(f"  data/daily_summary.csv      — running summer summary")
print(f"{'='*60}\n")