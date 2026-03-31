from typing import Dict, Any

class StateManager:
    def __init__(self):
        # In-memory store for satellite and debris states
        self.satellites: Dict[str, Any] = {}
        self.debris: Dict[str, Any] = {}

    def update_satellite(self, sat_id: str, data: Any):
        self.satellites[sat_id] = data

    def get_satellite(self, sat_id: str) -> Any:
        return self.satellites.get(sat_id)

    def get_all_satellites(self) -> Dict[str, Any]:
        return self.satellites

    def update_debris(self, deb_id: str, data: Any):
        self.debris[deb_id] = data

    def get_all_debris(self) -> Dict[str, Any]:
        return self.debris

# Global instance for the application
state = StateManager()
