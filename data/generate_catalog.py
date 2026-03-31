import json
import random

def generate_catalog():
    catalog = {
        "satellites": {},
        "debris": {}
    }

    # Generate 1000 satellites
    for i in range(1, 1001):
        sat_id = f"SAT-{i:04d}"
        catalog["satellites"][sat_id] = {
            "id": sat_id,
            "position": {
                "x": random.uniform(-7000, 7000),
                "y": random.uniform(-7000, 7000),
                "z": random.uniform(-7000, 7000)
            },
            "velocity": {
                "vx": random.uniform(-7.5, 7.5),
                "vy": random.uniform(-7.5, 7.5),
                "vz": random.uniform(-7.5, 7.5)
            },
            "status": "nominal"
        }

    # Generate 5000 debris objects
    for i in range(1, 5001):
        deb_id = f"DEB-{i:05d}"
        catalog["debris"][deb_id] = {
            "id": deb_id,
            "position": {
                "x": random.uniform(-8000, 8000),
                "y": random.uniform(-8000, 8000),
                "z": random.uniform(-8000, 8000)
            },
            "velocity": {
                "vx": random.uniform(-8, 8),
                "vy": random.uniform(-8, 8),
                "vz": random.uniform(-8, 8)
            },
            "risk_level": random.choice(["low", "medium", "high"])
        }

    with open("catalog.json", "w") as f:
        json.dump(catalog, f, indent=2)

if __name__ == "__main__":
    generate_catalog()
    print("Generated catalog.json with 1000 satellites and 5000 debris objects.")
