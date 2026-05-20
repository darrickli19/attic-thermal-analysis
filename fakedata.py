import numpy as np
import pandas as pd
import os
from datetime import datetime, timedelta

os.makedirs('data', exist_ok=True)

# ── Sensor readings CSV (for Python analysis script) ──────────────────────────
start = datetime(2026, 6, 8, 0, 0, 0)
minutes = 60 * 24 * 7  # 7 days
timestamps = [start + timedelta(minutes=i) for i in range(minutes)]

t = np.arange(minutes)
hours = (t / 60) % 24

sensor0 = 22 + 16 * (np.sin((hours - 6) * np.pi / 12)) ** 2 + np.random.normal(0, 0.3, minutes)
sensor1 = 30 + 25 * (np.sin((hours - 8) * np.pi / 12)) ** 2 + np.random.normal(0, 0.4, minutes)
sensor2 = 28 + 21 * (np.sin((hours - 9) * np.pi / 12)) ** 2 + np.random.normal(0, 0.3, minutes)

df = pd.DataFrame({
    'Timestamp': timestamps,
    'Sensor0_C': np.round(sensor0, 2),
    'Sensor1_C': np.round(sensor1, 2),
    'Sensor2_C': np.round(sensor2, 2),
})
df.to_csv('data/sensor_readings.csv', index=False)
print(f"Generated sensor_readings.csv: {len(df)} rows")
print(f"Sensor 2 range: {df['Sensor2_C'].min():.1f} - {df['Sensor2_C'].max():.1f} °C")

# ── MOOSE BC file (time in seconds, temperature in Celsius) ───────────────────
t_sec = np.arange(0, 86460, 60)  # one extra step past 86400
hours_bc = t_sec / 3600
T_bc = 28 + 21 * (np.sin((hours_bc - 9) * np.pi / 12)) ** 2

with open('data/sensor2_bc.csv', 'w') as f:
    for ti, Ti in zip(t_sec, T_bc):
        f.write(f'{ti},{Ti:.2f}\n')

print(f"Generated sensor2_bc.csv: {len(t_sec)} rows")
print(f"BC temp range: {T_bc.min():.1f} - {T_bc.max():.1f} °C")