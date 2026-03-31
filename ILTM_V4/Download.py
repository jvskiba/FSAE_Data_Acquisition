import requests

ESP_IP = "http://192.168.8.175"

def get_latest_log():
    # Get file list from logs directory
    r = requests.get(f"{ESP_IP}/files", params={"dir": "/logs"})
    r.raise_for_status()

    files = r.json()

    # Filter for .bin files
    bin_files = [f for f in files if f.endswith(".bin")]

    if not bin_files:
        raise Exception("No .bin files found in /logs")

    # Sort (assumes names reflect order)
    bin_files.sort()

    latest = bin_files[-1]
    return latest


def download_file(filename):
    print(f"Downloading: {filename}")

    r = requests.get(
        f"{ESP_IP}/download",
        params={"name": f"/logs/{filename}"}
    )
    r.raise_for_status()

    with open(filename, "wb") as f:
        f.write(r.content)

    print("Done.")


if __name__ == "__main__":
    latest = get_latest_log()
    download_file(latest)