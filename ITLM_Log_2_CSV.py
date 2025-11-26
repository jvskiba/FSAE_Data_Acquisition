import pandas as pd

def split_csv_by_source(input_csv, output_csv, source_type):
    # Load the CSV
    df = pd.read_csv(input_csv, low_memory=False)

    # Filter rows by the desired type
    filtered = df[df['source'] == source_type]

    # Drop columns that are completely empty for this source
    filtered = filtered.dropna(axis=1, how='all')

    # Save cleaned CSV
    filtered.to_csv(output_csv, index=False)
    print(f"Saved {source_type} data to {output_csv}")

def merge_can_anlg(input_csv, output_csv):
    # Load CSV
    df = pd.read_csv(input_csv)

    # Separate by source
    can  = df[df["source"] == "CAN"].copy()
    anlg = df[df["source"] == "ANLG"].copy()

    # Drop empty columns
    can  = can.dropna(axis=1, how="all")
    anlg = anlg.dropna(axis=1, how="all")

    # Make sure timestamps are sorted
    can  = can.sort_values("timestamp")
    anlg = anlg.sort_values("timestamp")

    # Merge analogue signals onto CAN rows using nearest timestamp
    merged = pd.merge_asof(
        can,
        anlg.drop(columns=["source"]),
        on="timestamp",
        direction="nearest",
        suffixes=("", "_ANLG")
    )

    # Save output
    merged.to_csv(output_csv, index=False)
    print(f"Saved merged file → {output_csv}")


# EXAMPLE USAGE:
src = "1970-01-01_00-00-03_data46.csv"
if False:
    split_csv_by_source(src, "can_only.csv", "CAN")
    split_csv_by_source(src, "anlg_only.csv", "ANLG")
    split_csv_by_source(src, "gps_only.csv", "GPS")

# Example
merge_can_anlg(src, "merged_can_anlg.csv")

