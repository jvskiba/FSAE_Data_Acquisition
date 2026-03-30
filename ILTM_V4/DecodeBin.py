import struct
import csv
import pandas as pd

# Struct format:
# <  = little endian (ESP32 is little endian)
# I  = uint32_t
# B  = uint8_t
# f  = float
STRUCT_FORMAT = "<IBf"
ENTRY_SIZE = struct.calcsize(STRUCT_FORMAT)

def convert_bin_to_csv(input_file, output_file):
    with open(input_file, "rb") as f, open(output_file, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        
        # Header
        writer.writerow(["timestamp", "id", "value"])
        
        while True:
            chunk = f.read(ENTRY_SIZE)
            if len(chunk) < ENTRY_SIZE:
                break
            
            timestamp, id_, value = struct.unpack(STRUCT_FORMAT, chunk)
            writer.writerow([timestamp, id_, value])

    print(f"Converted {input_file} → {output_file}")

import pandas as pd

def convert_to_dataframe(input_file):
    data = []

    with open(input_file, "rb") as f:
        while True:
            chunk = f.read(ENTRY_SIZE)
            if len(chunk) < ENTRY_SIZE:
                break
            data.append(struct.unpack(STRUCT_FORMAT, chunk))

    df = pd.DataFrame(data, columns=["timestamp", "id", "value"])
    return df

def resample_data(df, freq_hz=100):
    df = df.copy()
    
    # Convert timestamp → datetime (assuming ms)
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms")
    
    # Pivot: each ID becomes its own column
    df_pivot = df.pivot_table(index="time", columns="id", values="value")
    
    # Resample to fixed frequency
    interval_ms = int(1000 / freq_hz)
    df_resampled = df_pivot.resample(f"{interval_ms}ms").mean()
    
    # Interpolate missing values
    df_resampled = df_resampled.interpolate(method="linear").fillna(-1)
    
    # Optional: flatten column names
    df_resampled.columns = [f"ID_{int(col)}" for col in df_resampled.columns]
    
    return df_resampled.reset_index()

import struct

def read_header(f):
    # Read magic
    magic = struct.unpack("<I", f.read(4))[0]
    if magic != 0xDEADBEEF:
        raise ValueError("Not a valid log file")

    num_ids = struct.unpack("<B", f.read(1))[0]

    id_map = {}

    for _ in range(num_ids):
        id_ = struct.unpack("<B", f.read(1))[0]
        name_len = struct.unpack("<B", f.read(1))[0]
        name = f.read(name_len).decode()

        id_map[id_] = name

    return id_map

def convert_with_names(input_file):
    data = []

    with open(input_file, "rb") as f:
        id_map = read_header(f)

        STRUCT_FORMAT = "<IBf"
        ENTRY_SIZE = struct.calcsize(STRUCT_FORMAT)

        while True:
            chunk = f.read(ENTRY_SIZE)
            if len(chunk) < ENTRY_SIZE:
                break

            timestamp, id_, value = struct.unpack(STRUCT_FORMAT, chunk)
            data.append((timestamp, id_, value))

    df = pd.DataFrame(data, columns=["timestamp", "id", "value"])

    # Replace IDs with names
    df["name"] = df["id"].map(id_map)

    return df, id_map

INPUT_FILE = "33658-09-27_01-30-09_data197.bin"
OUTPUT_FILE = "log.csv"

if __name__ == "__main__":
    #convert_bin_to_csv(INPUT_FILE, OUTPUT_FILE)
    
    #df = convert_to_dataframe(INPUT_FILE)
    #print(df.head())
    #df2 = resample_data(df, 100)
    #print(df2.head())
    #df2.to_csv("log2.csv", index=False, na_rep="-1")
    #df.to_csv("log.csv", index=False)

    df, id_map = convert_with_names(INPUT_FILE)
    print(id_map)
    print(df.head())
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms")

    df_pivot = df.pivot_table(
        index="time",
        columns="name",   # 👈 use names instead of IDs
        values="value"
    )
    print(df_pivot.head())