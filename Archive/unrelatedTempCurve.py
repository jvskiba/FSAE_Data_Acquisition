import numpy as np

# -----------------------------
# CONFIG
# -----------------------------
VREF = 5.0              # ADC reference voltage
ADC_MAX = 1023
R_PULLUP = 2490.0      # ohms (CHANGE THIS)

# Your full dataset: [Temp °C, Resistance ohms]
data_all = np.array([
    [-10, 34127.6],
    [10, 13269.5],
    [30, 5439.9],
    [50, 2392.3],
    [70, 1150.3],
    [90, 599.3],
    [100, 439.4],
    [120, 246]
])

# Sort by resistance (important for nearest lookup)
data_all = data_all[data_all[:,1].argsort()]

temps_C = data_all[:,0]
resistances = data_all[:,1]


# -----------------------------
# Helpers
# -----------------------------

def adc_to_voltage(adc):
    return (adc / ADC_MAX) * VREF


def voltage_to_resistance(v):
    # Voltage divider: V = Vref * (R_therm / (R_pullup + R_therm))
    # Solve for R_therm
    if v <= 0:
        return np.inf
    if v >= VREF:
        return 0
    return R_PULLUP * v / (VREF - v)


def steinhart_hart_coeffs(temps_C, resistances):
    T = temps_C + 273.15
    Y = 1 / T
    L = np.log(resistances)

    X = np.column_stack([np.ones(len(L)), L, L**3])
    A, B, C = np.linalg.solve(X, Y)
    return A, B, C


def steinhart_temp(R, A, B, C):
    L = np.log(R)
    inv_T = A + B*L + C*(L**3)
    return (1 / inv_T) - 273.15


def get_closest_3(R):
    idx = np.argsort(np.abs(resistances - R))
    sel = idx[:3]
    return temps_C[sel], resistances[sel]


# -----------------------------
# Generate table
# -----------------------------

lines = []
lines.append(";Fmt\tValue\tType\tComment\tADC\tEmpty\tValue\tEmpty\tVolts")

for adc in range(1024):
    v = adc_to_voltage(adc)
    R = voltage_to_resistance(v)

    if np.isinf(R) or R <= 0:
        temp = -273.15  # fallback (physically nonsense, but safe)
    else:
        t_sel, r_sel = get_closest_3(R)
        A, B, C = steinhart_hart_coeffs(t_sel, r_sel)
        temp = steinhart_temp(R, A, B, C)

    # ECU formatting (looks like temp * 10)
    scaled = int(round(temp * 10))

    line = f"DB {temp:.2f} T ; {adc} - {scaled} ; {v:.3f}"
    lines.append(line)


# -----------------------------
# Write file
# -----------------------------
with open("thermistor_table.inc", "w") as f:
    f.write("\n".join(lines))

print("Done. Generated thermistor_table.inc")