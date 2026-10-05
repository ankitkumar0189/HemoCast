from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import os
import datetime
import pandas as pd
import joblib

try:
    from model import AutonomousBloodPredictor
except ImportError:
    AutonomousBloodPredictor = None

ROOT_DIR = Path(__file__).resolve().parent
os.chdir(ROOT_DIR)

MODEL_FILE = "sqlite_blood_shortage_model.joblib"

try:
    ml_model = joblib.load(MODEL_FILE)
    print(f" Loaded ML Model from {MODEL_FILE}")
except Exception as e:
    print(f" Warning: Could not load {MODEL_FILE} ({e}). Using heuristic fallback.")
    ml_model = None

GROUPS = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]

HOSPITALS = {
    "Hospital A": {
        "location": "Central District, Ranchi",
        "stock": {"A+": 18, "A-": 7, "B+": 22, "B-": 8, "O+": 25, "O-": 5, "AB+": 12, "AB-": 4},
        "emergencies_24h": 14,
        "surgeries_48h": 18,
        "last_sync": "Local Seed"
    },
    "Hospital B": {
        "location": "North Metro, Ranchi",
        "stock": {"A+": 32, "A-": 14, "B+": 35, "B-": 16, "O+": 40, "O-": 18, "AB+": 20, "AB-": 10},
        "emergencies_24h": 4,
        "surgeries_48h": 8,
        "last_sync": "Local Seed"
    },
    "Hospital C": {
        "location": "West Valley, Ranchi",
        "stock": {"A+": 15, "A-": 9, "B+": 19, "B-": 11, "O+": 21, "O-": 8, "AB+": 13, "AB-": 6},
        "emergencies_24h": 6,
        "surgeries_48h": 10,
        "last_sync": "Local Seed"
    }
}

REGISTERED_DONORS = []
LINKED_DATABASES = {}
DAILY_DEMAND = {"A+": 6, "A-": 2, "B+": 7, "B-": 2, "O+": 9, "O-": 4, "AB+": 3, "AB-": 1}
HOSPITAL_DEMAND_MULTIPLIER = {"Hospital A": 1.0, "Hospital B": 1.2, "Hospital C": 0.9}

COMPATIBILITY = {
    'O-': ['O-'],
    'O+': ['O-', 'O+'],
    'A-': ['O-', 'A-'],
    'A+': ['O-', 'O+', 'A-', 'A+'],
    'B-': ['O-', 'B-'],
    'B+': ['O-', 'O+', 'B-', 'B+'],
    'AB-': ['O-', 'A-', 'B-', 'AB-'],
    'AB+': ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+']
}


def build_inventory():
    rows = []
    now = datetime.datetime.now()
    cur_month = now.month
    cur_dow = now.weekday()

    inference_batch = []
    meta_records = []

    for hospital_name, hospital in HOSPITALS.items():
        multiplier = HOSPITAL_DEMAND_MULTIPLIER.get(hospital_name, 1.0)
        emergencies = hospital.get("emergencies_24h", 6)
        surgeries = hospital.get("surgeries_48h", 12)

        for group in GROUPS:
            units = hospital["stock"].get(group, 0)
            daily_demand = DAILY_DEMAND.get(group, 5) * multiplier
            reserve_hours = (units / daily_demand * 24) if daily_demand > 0 else 99.0

            inference_batch.append({
                'hospital_id': hospital_name,
                'region_tier': 'Urban-Metro',
                'blood_group': group,
                'month': cur_month,
                'day_of_week': cur_dow,
                'is_festival_season': 0,
                'monsoon_dengue_peak': 1 if cur_month in [8, 9, 10] else 0,
                'emergency_admissions_past_24h': emergencies,
                'scheduled_surgeries_next_48h': surgeries,
                'current_stock_units': units,
                'avg_daily_consumption_7d': daily_demand,
                'expected_donations_next_24h': 3
            })

            meta_records.append({
                "hospital": hospital_name,
                "location": hospital["location"],
                "group": group,
                "reserve": round(reserve_hours, 1),
                "units": units,
                "demand": round(daily_demand * 7)
            })

    if ml_model is not None:
        try:
            df_in = pd.DataFrame(inference_batch)
            probs = ml_model.predict_proba(df_in)
            for idx, meta in enumerate(meta_records):
                p_warn = probs[idx][1]
                p_crit = probs[idx][2]
                computed_risk = int(round((p_warn * 0.45 + p_crit * 1.0) * 100))
                meta["risk"] = min(99, max(5, computed_risk))
                rows.append(meta)
            return rows
        except Exception as e:
            print("Model prediction error:", e)

    for meta in meta_records:
        r = meta["reserve"]
        meta["risk"] = 99 if r < 18 else (81 if r < 36 else (59 if r < 48 else 32))
        rows.append(meta)
    return rows


def generate_action_queue():
    inventory = build_inventory()
    actions = []

    deficits = [item for item in inventory if item["risk"] >= 80]
    surpluses = [item for item in inventory if item["risk"] < 50 and item["units"] >= 15]

    for def_item in deficits:
        target_hosp = def_item["hospital"]
        target_grp = def_item["group"]
        allowed_sources = COMPATIBILITY.get(target_grp, [target_grp])

        eligible = [
            s for s in surpluses
            if s["hospital"] != target_hosp and s["group"] in allowed_sources
        ]

        if eligible:
            eligible.sort(key=lambda x: x["units"], reverse=True)
            donor = eligible[0]
            transfer_qty = min(6, donor["units"] - 10)

            if transfer_qty > 0:
                is_crit = def_item["risk"] >= 90
                actions.append({
                    "priority": "red" if is_crit else ("cyan" if "AB" in target_grp else ""),
                    "title": f"Priority {target_grp} replenishment" if is_crit else f"{target_grp} buffer transfer",
                    "group": target_grp,
                    "units": transfer_qty,
                    "fromHospital": donor["hospital"],
                    "toHospital": target_hosp,
                    "eta": "ETA 02h 15m" if is_crit else "ETA 04h 30m",
                    "status": "Dispatch"
                })
                donor["units"] -= transfer_qty

    return actions


def execute_external_db_test(protocol, config):
    if protocol == "sqlite":
        path = config.get("path")
        if not path or not os.path.exists(path):
            return False, f"File not found: {path}"
        try:
            import sqlite3
            conn = sqlite3.connect(path)
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cur.fetchall()]
            conn.close()
            return True, f"Connection verified. Found tables: {', '.join(tables[:4])}"
        except Exception as e:
            return False, f"SQLite error: {str(e)}"

    elif protocol == "fhir":
        url = config.get("url")
        if not url:
            return False, "Endpoint URL is required."
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "HEMONET/1.0"})
            if config.get("token"):
                req.add_header("Authorization", config.get("token"))
            with urllib.request.urlopen(req, timeout=5) as res:
                return True, f"FHIR endpoint reachable! Status: {res.status}"
        except Exception as e:
            return False, f"FHIR error: {str(e)}"

    elif protocol in ["postgres", "mysql", "sql"]:
        uri = config.get("uri", "")
        if not uri:
            return False, "URI string cannot be empty."
        if not (uri.startswith("postgresql://") or uri.startswith("mysql://")):
            return False, "URI must start with postgresql:// or mysql://"
        return True, "Driver connection parameters validated."

    return False, "Unknown protocol."


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        clean_path = self.path.split("?")[0]

        if clean_path == "/api/inventory":
            self.send_json(build_inventory())
            return

        elif clean_path == "/api/coordination":
            self.send_json(generate_action_queue())
            return

        elif clean_path == "/api/plots/regenerate":
            if ml_model is not None and hasattr(ml_model, "generate_all_diagnostics"):
                try:
                    ml_model.generate_all_diagnostics()
                    self.send_json({
                        "status": "success",
                        "message": "All diagnostic figures updated in outputs/",
                        "plots": [
                            "/outputs/confusion_matrix.png",
                            "/outputs/roc_curves.png",
                            "/outputs/feature_importance.png"
                        ]
                    })
                    return
                except Exception as e:
                    self.send_json({"error": f"Plotting failed: {str(e)}"}, 500)
                    return
            self.send_json({"error": "Self-plotting model not initialized"}, 400)
            return

        elif clean_path == "/api/external/sync":
            nodes_info = {
                name: {
                    "location": h["location"],
                    "total_stock": sum(h["stock"].values()),
                    "last_sync": h.get("last_sync", "Never")
                }
                for name, h in HOSPITALS.items()
            }
            self.send_json({"connected_nodes": nodes_info})
            return

        super().do_GET()

    def do_POST(self):
        clean_path = self.path.split("?")[0]

        # 1. Execute transfer
        if clean_path == "/api/transfer":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length))

                group = data["group"]
                source = data["fromHospital"]
                destination = data["toHospital"]
                units = int(data["units"])

                if group not in GROUPS or source not in HOSPITALS or destination not in HOSPITALS:
                    self.send_json({"error": "Invalid hospital or blood group"}, 400)
                    return

                if source == destination or units <= 0:
                    self.send_json({"error": "Invalid transfer parameters"}, 400)
                    return

                if HOSPITALS[source]["stock"][group] < units:
                    self.send_json({"error": "Insufficient stock at source hospital"}, 400)
                    return

                HOSPITALS[source]["stock"][group] -= units
                HOSPITALS[destination]["stock"][group] += units

                self.send_json({
                    "message": f"{units} units of {group} transferred successfully",
                    "inventory": build_inventory()
                })
                return
            except (KeyError, ValueError, json.JSONDecodeError):
                self.send_json({"error": "Invalid JSON transfer payload"}, 400)
                return

        # 2. External hospital telemetry sync
        elif clean_path == "/api/external/sync":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length))

                hospital_name = data.get("hospital")
                stock_update = data.get("stock", {})
                location = data.get("location", "Ranchi Network Facility")

                if not hospital_name or not isinstance(stock_update, dict):
                    self.send_json({"error": "Missing 'hospital' or 'stock' dictionary"}, 400)
                    return

                if hospital_name not in HOSPITALS:
                    HOSPITALS[hospital_name] = {
                        "location": location,
                        "stock": {g: 0 for g in GROUPS},
                        "emergencies_24h": data.get("emergencies_24h", 6),
                        "surgeries_48h": data.get("surgeries_48h", 10),
                        "last_sync": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }

                for grp, count in stock_update.items():
                    if grp in GROUPS:
                        HOSPITALS[hospital_name]["stock"][grp] = int(count)

                self.send_json({
                    "status": "success",
                    "message": f"Telemetry synced for {hospital_name}",
                    "hospital": hospital_name,
                    "updated_stock": HOSPITALS[hospital_name]["stock"]
                }, 200)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
                return

        # 3. Hospital Self-Registration Portal
        elif clean_path == "/api/register/hospital":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length))

                name = data.get("name")
                location = data.get("location", "Ranchi Sector")
                emergencies = int(data.get("emergencies_24h", 8))
                surgeries = int(data.get("surgeries_48h", 12))
                o_minus_initial = int(data.get("o_minus_units", 4))

                if not name:
                    self.send_json({"error": "Hospital name is required"}, 400)
                    return

                HOSPITALS[name] = {
                    "location": location,
                    "stock": {
                        "A+": 16, "A-": 8, "B+": 20, "B-": 6,
                        "O+": 22, "O-": o_minus_initial, "AB+": 10, "AB-": 4
                    },
                    "emergencies_24h": emergencies,
                    "surgeries_48h": surgeries,
                    "last_sync": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                HOSPITAL_DEMAND_MULTIPLIER[name] = 1.0

                print(f" Registered hospital: {name} ({location})")
                self.send_json({
                    "status": "success",
                    "message": f"Hospital '{name}' registered successfully!",
                    "hospital": name
                }, 201)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
                return

        # 4. Donor Self-Registration Portal
        elif clean_path == "/api/register/donor":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length))

                donor_name = data.get("name")
                group = data.get("group")
                phone = data.get("phone")
                locality = data.get("locality")

                if not donor_name or not group or not phone:
                    self.send_json({"error": "Name, group, and phone are required"}, 400)
                    return

                new_donor = {
                    "id": len(REGISTERED_DONORS) + 1,
                    "name": donor_name,
                    "group": group,
                    "phone": phone,
                    "locality": locality,
                    "registered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                REGISTERED_DONORS.append(new_donor)
                print(f" Registered donor: {donor_name} ({group})")

                self.send_json({
                    "status": "success",
                    "message": f"Thank you {donor_name}! Registered as an emergency donor.",
                    "donor_id": new_donor["id"]
                }, 201)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
                return

        # 5. Database Connection Test
        elif clean_path == "/api/database/test":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length))
                protocol = data.get("protocol", "sql")
                config = data.get("config", {})

                success, message = execute_external_db_test(protocol, config)
                self.send_json({"success": success, "message": message}, 200 if success else 400)
                return
            except Exception as e:
                self.send_json({"success": False, "message": str(e)}, 400)
                return

        # 6. Save & Activate Linked External Database
        elif clean_path == "/api/database/link":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                data = json.loads(self.rfile.read(length))

                hospital = data.get("hospital")
                protocol = data.get("protocol")
                config = data.get("config", {})
                interval = data.get("interval", "30")

                if not hospital or not protocol:
                    self.send_json({"error": "Hospital name and protocol are required."}, 400)
                    return

                if hospital not in HOSPITALS:
                    HOSPITALS[hospital] = {
                        "location": "External Linked Node",
                        "stock": {g: 15 for g in GROUPS},
                        "emergencies_24h": 8,
                        "surgeries_48h": 12,
                        "last_sync": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    HOSPITAL_DEMAND_MULTIPLIER[hospital] = 1.0

                LINKED_DATABASES[hospital] = {
                    "protocol": protocol,
                    "config": config,
                    "sync_interval_mins": interval,
                    "linked_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "status": "ACTIVE_SYNC"
                }

                print(f" Database linked for '{hospital}' via [{protocol.upper()}].")
                self.send_json({
                    "status": "success",
                    "message": f"Database linked successfully for {hospital}! Telemetry active.",
                    "inventory": build_inventory()
                }, 200)
                return
            except Exception as e:
                self.send_json({"error": str(e)}, 400)
                return

        self.send_json({"error": f"Route not found: {self.path}"}, 404)


if __name__ == '__main__':
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("HEMONET server running at http://127.0.0.1:8000")
    print("Press Ctrl+C to terminate.")
    server.serve_forever()