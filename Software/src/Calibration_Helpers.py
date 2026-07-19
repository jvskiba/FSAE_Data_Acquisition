from fractions import Fraction
import numpy as np

def gen_lin_adc_constants(adc_min, adc_max, eng_min, eng_max, max_denominator=100000):
    slope = (eng_max - eng_min) / (adc_max - adc_min)
    frac = Fraction(slope).limit_denominator(max_denominator)
    mult = frac.numerator
    div = frac.denominator
    add = eng_min - (adc_min * mult / div)
    add = round(add) #Less accurate but accounts for low storage requirements on Embedded systems

    return {
        "mult": mult,
        "div": div,
        "add": add,
        "slope": slope
    }

def gen_steinhart_adc_constants(adc1, temp1,
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

    return a, b, c

if __name__ == "__main__":
    constants = gen_lin_adc_constants(
        adc_min=410,
        adc_max=3685,
        eng_min=0,
        eng_max=100
    )

    print(f"mult = {constants['mult']}")
    print(f"div = {constants['div']}")
    print(f"add = {constants['add']}")

    a, b, c = gen_steinhart_adc_constants(
        3500, 0.0,
        2200, 25.0,
        900, 100.0,
        r_fixed=1000
    )

    print(f"a = {a}, b = {b}, c = {c}")