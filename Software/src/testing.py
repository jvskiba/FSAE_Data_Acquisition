from fractions import Fraction

def generate_constants(adc_min, adc_max, eng_min, eng_max, max_denominator=100000):
    slope = (eng_max - eng_min) / (adc_max - adc_min)
    frac = Fraction(slope).limit_denominator(max_denominator)
    mult = frac.numerator
    div = frac.denominator
    add = eng_min - (adc_min * mult / div)

    return {
        "mult": mult,
        "div": div,
        "add": add,
        "slope": slope
    }

import numpy as np

import numpy as np

def make_therm_converter(adc1, temp1,
                         adc2, temp2,
                         adc3, temp3,
                         r_fixed=1000,
                         adc_max=4095,
                         thermistor_to_gnd=True):

    def adc_to_resistance(adc):
        if thermistor_to_gnd:
            if (adc_max - adc) == 0:
                return -1
            return r_fixed * adc / (adc_max - adc)
        else:
            if adc == 0:
                return -1
            return r_fixed * (adc_max - adc) / adc

    R = np.array([
        adc_to_resistance(adc1),
        adc_to_resistance(adc2),
        adc_to_resistance(adc3)
    ])

    T = np.array([
        temp1,
        temp2,
        temp3
    ]) + 459.67          # Fahrenheit -> Rankine
    T = T * 5 / 9         # Rankine -> Kelvin

    L = np.log(R)

    A = np.column_stack([
        np.ones(3),
        L,
        L**3
    ])

    a, b, c = np.linalg.solve(A, 1 / T)

    def adc_to_temp(adc):

        R = adc_to_resistance(adc)
        L = np.log(R)

        T = 1 / (a + b * L + c * L**3)

        return T * 9 / 5 - 459.67   # Kelvin -> Fahrenheit

    return adc_to_temp

if __name__ == "__main__":
    constants = generate_constants(
        adc_min=410,
        adc_max=3685,
        eng_min=0,
        eng_max=100
    )

    print(f"mult = {constants['mult']}")
    print(f"div = {constants['div']}")
    print(f"add = {constants['add']}")

    adc_to_temp = make_therm_converter(
        3500, 0.0,
        2200, 25.0,
        900, 100.0
    )

    print(adc_to_temp(2200))
    print(adc_to_temp(1500))
    print(adc_to_temp(1000))


def make_therm_coefficients(adc1, temp1,
                            adc2, temp2,
                            adc3, temp3):

    adc = np.array([adc1, adc2, adc3], dtype=float)
    temp = np.array([temp1, temp2, temp3], dtype=float)

    a, b, c = np.polyfit(adc, temp, 2)
    return a, b, c