import struct
import csv
import pandas as pd

VERSION = 1

def read_header(f):
    # Read magic
    magic = struct.unpack("<I", f.read(4))[0]
    if magic != 0xDEADBEEF:
        raise ValueError("Not a valid log file")

    # Read version
    version = struct.unpack("<B", f.read(1))[0]

    if (version != VERSION):
        print("Binary Decode Version MisMatch")

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

INPUT_FILE = "33658-09-27_01-30-09_data201.bin"
OUTPUT_FILE = "log.csv"

if __name__ == "__main__":
    df, id_map = convert_with_names(INPUT_FILE)
    print(df.head())
    df["time"] = pd.to_datetime(df["timestamp"], unit="ms")

    df_pivot = df.pivot_table(
        index="time",
        columns="name",   # 👈 use names instead of IDs
        values="value"
    )
    print(df_pivot.head())
    df_pivot.to_csv("log.csv", index=False)