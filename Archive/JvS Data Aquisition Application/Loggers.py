import os
import csv
from collections import deque
from datetime import datetime
from typing import Optional

class BufferedLogger:
    def __init__(self, file_path, headers, buffer_size=50, add_timestamp=True):
        self.file_path = file_path
        self.headers = headers.copy()
        self.buffer_size = buffer_size
        self.add_timestamp = add_timestamp

        if add_timestamp and "timestamp" not in self.headers:
            self.headers.insert(0, "timestamp")

        self.buffer = deque()
        self._init_file()

    def _init_file(self):
        file_exists = os.path.exists(self.file_path)
        self.csv_file = open(self.file_path, "a", newline="")
        self.writer = csv.DictWriter(self.csv_file, fieldnames=self.headers)
        if not file_exists:
            self.writer.writeheader()
            self.csv_file.flush()

    def log_frame(self, frame):
        if self.add_timestamp:
            frame_dict = {"timestamp": datetime.now().isoformat()}
        else:
            frame_dict = {}

        if isinstance(frame, dict):
            for col in self.headers:
                if col == "timestamp" and self.add_timestamp:
                    continue
                frame_dict[col] = frame.get(col, "")
        elif hasattr(frame, "__dataclass_fields__"):
            for col in self.headers:
                if col == "timestamp" and self.add_timestamp:
                    continue
                frame_dict[col] = getattr(frame, col, "")
        else:
            for i, col in enumerate(self.headers):
                if col == "timestamp" and self.add_timestamp:
                    continue
                frame_dict[col] = frame[i]

        self.buffer.append(frame_dict)

        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self):
        while self.buffer:
            self.writer.writerow(self.buffer.popleft())
        self.csv_file.flush()

    def close(self):
        self.flush()
        self.csv_file.close()


class SessionLogger:
    

    def __init__(self, base_dir="logs"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

        self.index_file = os.path.join(base_dir, "index.csv")
        self._init_index()

        self.session_active = False
        self.log_number = self._get_next_log_number()
        self.telemetry_logger: Optional[BufferedLogger] = None
        self.events_logger = None
        self.session_start_time = None

    def _init_index(self):
        if not os.path.exists(self.index_file):
            with open(self.index_file, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "log_number", "start_time", "end_time",
                    "telemetry_file", "events_file", "notes"
                ])

    def _get_next_log_number(self):
        if not os.path.exists(self.index_file):
            return 1
        with open(self.index_file, "r") as f:
            reader = csv.DictReader(f)
            nums = [int(row["log_number"]) for row in reader if row["log_number"].isdigit()]
        return max(nums, default=0) + 1

    def start_session(self, telem_cols=[], notes=""):
        if self.session_active:
            raise RuntimeError("Session already active")

        self.session_start_time = datetime.now().isoformat()

        telemetry_file = os.path.join(self.base_dir, f"log{self.log_number}_telemetry.csv")
        events_file = os.path.join(self.base_dir, f"log{self.log_number}_events.csv")

        # Create loggers
        self.telemetry_logger = BufferedLogger(
            telemetry_file,
            headers=telem_cols,
            buffer_size=50,
            add_timestamp=True
        )
        self.events_logger = BufferedLogger(
            events_file,
            headers=["type", "value"],
            buffer_size=1,
            add_timestamp=True
        )

        # Add entry to index with empty end_time for now
        with open(self.index_file, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                self.log_number,
                self.session_start_time,
                "",  # end_time filled on stop
                os.path.basename(telemetry_file),
                os.path.basename(events_file),
                notes
            ])

        self.session_active = True
        print(f"[SessionLogger] Started log {self.log_number}")

    def stop_session(self):
        if not self.session_active:
            return
        assert self.telemetry_logger is not None
        assert self.events_logger is not None

        self.telemetry_logger.close()
        self.events_logger.close()
        end_time = datetime.now().isoformat()

        # Update end_time in index file
        rows = []
        with open(self.index_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if int(row["log_number"]) == self.log_number and row["end_time"] == "":
                    row["end_time"] = end_time
                rows.append(row)

        with open(self.index_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        self.session_active = False
        self.log_number += 1
        print(f"[SessionLogger] Stopped log {self.log_number - 1}")

    def log_telemetry(self, frame):
        if self.session_active:
            assert self.telemetry_logger is not None
            self.telemetry_logger.log_frame(frame)

    def log_event(self, frame):
        if self.session_active:
            assert self.events_logger is not None
            self.events_logger.log_frame(frame)
            print("Ahhhhh")