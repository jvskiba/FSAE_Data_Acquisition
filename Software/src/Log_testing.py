import pandas as pd
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import numpy as np


def load_csv(file_path: str) -> pd.DataFrame:
    """
    Load a telemetry CSV into a pandas DataFrame.
    """
    df = pd.read_csv(
        file_path,
        dtype={
            "timestamp_ms": "int64",
            "id": "int32",
            "signal": "string",
            "value": "float64",
        }
    )

    return df

def calculate_signal_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate the time difference between consecutive occurrences
    of each signal.

    Returns a DataFrame containing:
        timestamp_ms
        <signal>_dt_ms for every unique signal
    """

    # Sort chronologically
    df = df.sort_values("timestamp_ms").reset_index(drop=True)

    # Calculate time since the previous occurrence of each signal
    df["dt_ms"] = (
        df.groupby("signal")["timestamp_ms"]
        .diff()
    )

    # Start the output with timestamps
    result = pd.DataFrame({
        "timestamp_ms": df["timestamp_ms"]
    })

    # Add one column for each signal
    for signal in df["signal"].dropna().unique():

        mask = df["signal"] == signal

        # Create a column for this signal
        column_name = f"{signal}_dt_ms"

        result[column_name] = pd.NA

        # Put the calculated interval at the appropriate timestamp
        result.loc[mask, column_name] = df.loc[mask, "dt_ms"].values

    return result


def normalize_log(
    df, output_csv="normalized.csv", hz=100, interpolate=True, method="nearest"
):
    # -----------------------------------
    # Create time index
    # -----------------------------------
    timestep_ms = int(1000 / hz)

    start_time = df["timestamp_ms"].min()
    end_time = df["timestamp_ms"].max()

    timeline = np.arange(start_time, end_time + timestep_ms, timestep_ms)

    # -----------------------------------
    # Pivot signals into columns
    # -----------------------------------
    pivoted = df.pivot_table(
        index="timestamp_ms", columns="signal", values="value", aggfunc="last"
    )

    print("timeline length:", len(timeline))
    print("timeline start:", timeline[0])
    print("timeline end:", timeline[-1])

    # -----------------------------------
    # Resampling without dropping unaligned timestamps
    # -----------------------------------
    if interpolate:
        # 1. Combine original timestamps + timeline grid into one unified index
        combined_index = pivoted.index.union(timeline).unique().sort_values()

        # 2. Reindex to combined index so original data points aren't lost, then interpolate
        pivoted = pivoted.reindex(combined_index).interpolate(method="linear")

        # 3. Slice to the final target timeline grid and handle outer edges
        pivoted = pivoted.loc[timeline].ffill().bfill()

    else:
        if method == "nearest":
            # Snaps grid timestamps to the closest available data point in time
            pivoted_reset = pivoted.reset_index().sort_values("timestamp_ms")
            grid_df = pd.DataFrame({"timestamp_ms": timeline})

            pivoted = pd.merge_asof(
                grid_df, pivoted_reset, on="timestamp_ms", direction="nearest"
            ).set_index("timestamp_ms")

        elif method == "ffill":
            # Union index and forward-fill (copies last value until a new one arrives)
            combined_index = (
                pivoted.index.union(timeline).unique().sort_values()
            )
            pivoted = (
                pivoted.reindex(combined_index).ffill().bfill().loc[timeline]
            )

    # -----------------------------------
    # Save CSV
    # -----------------------------------
    pivoted.index.name = "timestamp_ms"
    pivoted.to_csv(output_csv)

    print(f"Saved normalized CSV: {output_csv}")
    return pivoted

def summarize_signal_rates(df: pd.DataFrame):
    """
    Print a summary of the timing/rate of every signal.

    Jitter is reported as the standard deviation of the
    time between consecutive signal occurrences.
    """

    # Sort chronologically
    df = df.sort_values("timestamp_ms").reset_index(drop=True)

    # Calculate interval between consecutive occurrences
    df["dt_ms"] = (
        df.groupby("signal")["timestamp_ms"]
        .diff()
    )

    summary = []

    for signal, group in df.groupby("signal"):

        # Remove the first occurrence (no previous timestamp)
        intervals = group["dt_ms"].dropna()

        if len(intervals) == 0:
            continue

        avg_dt = intervals.mean()
        jitter = intervals.std()
        min_dt = intervals.min()
        max_dt = intervals.max()

        # Convert period to frequency
        avg_hz = 1000.0 / avg_dt

        summary.append({
            "Signal": signal,
            "Avg Period (ms)": avg_dt,
            "Avg Rate (Hz)": avg_hz,
            "Jitter (ms)": jitter,
            "Min (ms)": min_dt,
            "Max (ms)": max_dt,
            "Samples": len(intervals),
        })

    # Create summary DataFrame
    summary_df = pd.DataFrame(summary)

    # Print nicely formatted table
    print("\nSignal Rate Summary")
    print("-" * 80)

    if summary_df.empty:
        print("No signal intervals found.")
        return summary_df

    print(
        summary_df.to_string(
            index=False,
            formatters={
                "Avg Period (ms)": "{:.3f}".format,
                "Avg Rate (Hz)": "{:.3f}".format,
                "Jitter (ms)": "{:.3f}".format,
                "Min (ms)": "{:.3f}".format,
                "Max (ms)": "{:.3f}".format,
            }
        )
    )

    print()

    return summary_df

def main():
    # Open file picker
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select telemetry CSV",
        filetypes=[
            ("CSV files", "*.csv"),
            ("All files", "*.*")
        ]
    )

    if not file_path:
        print("No file selected.")
        return

    print(f"Loading: {file_path}")

    df = load_csv(file_path)

    print(f"Loaded {len(df):,} rows")
    print(f"Found {df['signal'].nunique()} unique signals")

    # Calculate intervals
    result = calculate_signal_intervals(df)

    # Output filename
    input_path = Path(file_path)

    output_path = (
        input_path.parent /
        f"{input_path.stem}_signal_intervals.csv"
    )

    # Save
    result.to_csv(output_path, index=False)

    print(f"\nOutput written to:")
    print(output_path)


def main2():
    # Open file picker
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select telemetry CSV",
        filetypes=[
            ("CSV files", "*.csv"),
            ("All files", "*.*")
        ]
    )

    if not file_path:
        print("No file selected.")
        return

    print(f"Loading: {file_path}")

    df = load_csv(file_path)

    print(f"Loaded {len(df):,} rows")
    print(f"Found {df['signal'].nunique()} unique signals")

    output_path = file_path.replace('.csv', '_Normalized2.csv')

    summarize_signal_rates(df)
    
    normalize_log(df, output_path, 100, False, "ffill")

    print(f"\nOutput written to:")
    print(output_path)


if __name__ == "__main__":
    #main()
    main2()