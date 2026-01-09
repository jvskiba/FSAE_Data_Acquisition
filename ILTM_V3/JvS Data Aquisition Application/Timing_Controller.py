class Sector:
    def __init__(self, start_gate, end_gate):
        self.start_gate = start_gate
        self.end_gate = end_gate
        self.last_start_time = None

class Lap:
    def __init__(self, lap_number, sectors):
        self.lap_number = lap_number
        self.sector_times = {f"{s.start_gate}->{s.end_gate}": None for s in sectors}

class TimingController:
    def __init__(self, sectors, lap_start_gate=1):
        self.sectors = sectors
        self.laps = []
        self.current_lap = None
        self.lap_start_gate = lap_start_gate
        self.gate_to_sectors = {}
        for s in sectors:
            self.gate_to_sectors.setdefault(s.start_gate, []).append(s)
            self.gate_to_sectors.setdefault(s.end_gate, []).append(s)
        self.lap_counter = 0
        self.current_lap = Lap(self.lap_counter, self.sectors)

    def record_event(self, event):
        gate_id = event["gate_id"]
        timestamp = event["timestamp"]

        for sector in self.sectors:
            if gate_id == sector.end_gate and sector.last_start_time:
                duration = timestamp - sector.last_start_time
                if self.current_lap: # not needed
                    self.current_lap.sector_times[f"{sector.start_gate}->{sector.end_gate}"] = duration
            
            if gate_id == sector.start_gate:
                sector.last_start_time = timestamp
        if gate_id == self.lap_start_gate:
            self.laps.append(self.current_lap)
            self._start_new_lap()

    def _start_new_lap(self):
        self.lap_counter += 1
        self.current_lap = Lap(self.lap_counter, self.sectors)

    def get_lap_times(self):
        laps = self.laps.copy()
        if self.current_lap:
            laps.append(self.current_lap)
        return laps
    
    def print(self):
        for lap in self.get_lap_times():
            print(f"Lap {lap.lap_number}: {lap.sector_times}")


# -------------------------------
# Example usage
# -------------------------------
if __name__ == "__main__":
    sectors = [
        Sector(start_gate=1, end_gate=1),
        Sector(start_gate=1, end_gate=2),
        Sector(start_gate=2, end_gate=3),
    ]

    tc = TimingController(sectors)

    events = [
        {"gate_id": 2, "timestamp": 200},
        {"gate_id": 3, "timestamp": 500},
        {"gate_id": 1, "timestamp": 1000},
        {"gate_id": 2, "timestamp": 3000},
        {"gate_id": 3, "timestamp": 3500},
        {"gate_id": 1, "timestamp": 5000},
        {"gate_id": 2, "timestamp": 6000},
    ]

    for e in events:
        tc.record_event(e)

    tc.print()
