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

def make_therm_converter(adc1, temp1,
                         adc2, temp2,
                         adc3, temp3):
    """
    Creates a function that converts ADC readings to temperature
    using a quadratic fit through three calibration points.
    """

    adc = np.array([adc1, adc2, adc3], dtype=float)
    temp = np.array([temp1, temp2, temp3], dtype=float)

    # Fit T = a*ADC² + b*ADC + c
    a, b, c = np.polyfit(adc, temp, 2)

    def adc_to_temp(adc_value):
        return a * adc_value**2 + b * adc_value + c

    return adc_to_temp

if __name__ == "__main__":
    constants = generate_constants(
        adc_min=700,
        adc_max=3615,
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