from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import json
import os
import sqlite3


# Keep blood_prediction.db in the same folder as server.py.
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "blood_prediction.db"
os.chdir(BASE_DIR)

GROUPS = ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]

# Demo demand assumptions, in units per day.
# Replace these with real usage data when you have authorized access.
DAILY_DEMAND = {
    "A+": 6,
    "A-": 2,
    "B+": 7,
    "B-": 2,
    "O+": 9,
    "O-": 4,
    "AB+": 3,
    "AB-": 2,
}

# Demo demand multipliers from your earlier server.py.
HOSPITAL_DEMAND_MULTIPLIER = {
    "Hospital A": 1.0,
    "Hospital B": 1.2,
    "Hospital C": 0.9,
}


def connect_db():
    if not DB_FILE.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_FILE}\n"
            "Put blood_prediction.db in the same folder as server.py."
        )

    connection = sqlite3.connect(DB_FILE, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def normalize_group(value):
    """Convert Unicode minus to a regular hyphen; for example, O− to O-."""
    return str(value).replace("−", "-").strip().upper()


def build_inventory():
    connection = connect_db()

    try:
        records = connection.execute("""
            SELECT
                h.hospital_name AS hospital,
                h.location AS location,
                h.city AS city,
                bi.blood_group AS blood_group,
                bi.total_units AS total_units,
                bi.available_units AS available_units,
                bi.reserved_units AS reserved_units,
                bi.critical_units AS critical_units,
                bi.last_updated AS last_updated
            FROM hospitals AS h
            JOIN blood_inventory AS bi
                ON bi.hospital_id = h.id
            ORDER BY h.hospital_name, bi.blood_group
        """).fetchall()

        inventory = []

        for item in records:
            group = normalize_group(item["blood_group"])
            available = item["available_units"] or 0

            # These are demo estimates, not actual hospital demand.
            base_daily_demand = DAILY_DEMAND.get(group, 1)
            multiplier = HOSPITAL_DEMAND_MULTIPLIER.get(
                item["hospital"], 1.0
            )
            daily_use = base_daily_demand * multiplier

            if daily_use > 0:
                reserve_hours = (available / daily_use) * 24
            else:
                reserve_hours = 999

            critical_threshold = item["critical_units"] or 0

            # Rule-based risk score; it is not a probability.
            if available <= critical_threshold or reserve_hours < 18:
                risk = 99
            elif reserve_hours < 36:
                risk = 81
            elif reserve_hours < 48:
                risk = 59
            else:
                risk = 32

            location_parts = [item["location"], item["city"]]
            location = ", ".join(
                str(part) for part in location_parts if part
            )

            inventory.append({
                # These fields match the format expected by your frontend.
                "hospital": item["hospital"],
                "location": location,
                "group": group,
                "reserve": round(reserve_hours, 1),
                "units": available,
                "demand": round(daily_use * 7),
                "risk": risk,

                # Extra fields are available if the frontend needs them.
                "totalUnits": item["total_units"],
                "reservedUnits": item["reserved_units"],
                "criticalUnits": item["critical_units"],
                "lastUpdated": item["last_updated"],
            })

        return inventory

    finally:
        connection.close()


class Handler(SimpleHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))

        if length <= 0:
            return {}

        return json.loads(self.rfile.read(length))

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/inventory":
            try:
                self.send_json(build_inventory())
            except (sqlite3.Error, FileNotFoundError) as error:
                self.send_json({"error": str(error)}, 500)
            return

        # Serve index.html, CSS, JavaScript and other static files.
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        try:
            data = self.read_json()

            # Update a hospital's available stock.
            if path == "/api/update-stock":
                hospital = data["hospital"]
                group = normalize_group(data["group"])
                units = int(data["units"])

                if group not in GROUPS or units < 0:
                    self.send_json({
                        "error": "Check the blood group and units"
                    }, 400)
                    return

                connection = connect_db()

                try:
                    result = connection.execute("""
                        UPDATE blood_inventory
                        SET available_units = ?,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE hospital_id = (
                            SELECT id
                            FROM hospitals
                            WHERE hospital_name = ?
                        )
                        AND blood_group = ?
                        AND ? >= COALESCE(reserved_units, 0)
                    """, (units, hospital, group, units))

                    if result.rowcount == 0:
                        connection.rollback()
                        self.send_json({
                            "error": (
                                "Stock row not found, or available units "
                                "cannot be less than reserved units"
                            )
                        }, 400)
                        return

                    connection.commit()

                finally:
                    connection.close()

                self.send_json({
                    "message": "Available stock updated in SQLite",
                    "inventory": build_inventory()
                })
                return

            # Dispatch a transfer.
            # Source stock is reduced now; destination stock increases
            # only after the receiving hospital confirms arrival.
            if path == "/api/transfer":
                group = normalize_group(data["group"])
                source_hospital = data["fromHospital"]
                destination_hospital = data["toHospital"]
                units = int(data["units"])

                if (
                    group not in GROUPS
                    or units <= 0
                    or source_hospital == destination_hospital
                ):
                    self.send_json({
                        "error": "Check the transfer details"
                    }, 400)
                    return

                connection = connect_db()

                try:
                    with connection:
                        source = connection.execute("""
                            SELECT
                                h.id AS hospital_id,
                                bi.available_units AS available_units
                            FROM hospitals AS h
                            JOIN blood_inventory AS bi
                                ON bi.hospital_id = h.id
                            WHERE h.hospital_name = ?
                              AND bi.blood_group = ?
                        """, (source_hospital, group)).fetchone()

                        destination = connection.execute("""
                            SELECT
                                h.id AS hospital_id
                            FROM hospitals AS h
                            JOIN blood_inventory AS bi
                                ON bi.hospital_id = h.id
                            WHERE h.hospital_name = ?
                              AND bi.blood_group = ?
                        """, (destination_hospital, group)).fetchone()

                        if source is None or destination is None:
                            self.send_json({
                                "error": (
                                    "Hospital or blood-group inventory "
                                    "was not found"
                                )
                            }, 400)
                            return

                        if source["available_units"] < units:
                            self.send_json({
                                "error": "Not enough available stock"
                            }, 400)
                            return

                        # Remove dispatched units from the source hospital.
                        connection.execute("""
                            UPDATE blood_inventory
                            SET available_units = available_units - ?,
                                last_updated = CURRENT_TIMESTAMP
                            WHERE hospital_id = ?
                              AND blood_group = ?
                        """, (units, source["hospital_id"], group))

                        # IMPORTANT: status must match the database constraint.
                        # Do not use lowercase "completed" here.
                        cursor = connection.execute("""
                            INSERT INTO blood_transfers (
                                from_hospital_id,
                                to_hospital_id,
                                blood_group,
                                units,
                                status,
                                requested_at,
                                completed_at
                            )
                            VALUES (
                                ?, ?, ?, ?, 'IN_TRANSIT',
                                CURRENT_TIMESTAMP, NULL
                            )
                        """, (
                            source["hospital_id"],
                            destination["hospital_id"],
                            group,
                            units
                        ))

                        transfer_id = cursor.lastrowid

                    self.send_json({
                        "message": "Transfer dispatched and marked IN_TRANSIT",
                        "transferId": transfer_id,
                        "inventory": build_inventory()
                    })
                finally:
                    connection.close()

                return

            # Confirm that an in-transit transfer has arrived.
            if path == "/api/complete-transfer":
                transfer_id = int(data["transferId"])

                connection = connect_db()

                try:
                    with connection:
                        transfer = connection.execute("""
                            SELECT
                                id,
                                to_hospital_id,
                                blood_group,
                                units,
                                status
                            FROM blood_transfers
                            WHERE id = ?
                        """, (transfer_id,)).fetchone()

                        if transfer is None:
                            self.send_json({
                                "error": "Transfer was not found"
                            }, 404)
                            return

                        if transfer["status"] != "IN_TRANSIT":
                            self.send_json({
                                "error": "Transfer is not in transit"
                            }, 400)
                            return

                        # Add received units to the destination hospital.
                        result = connection.execute("""
                            UPDATE blood_inventory
                            SET available_units = available_units + ?,
                                last_updated = CURRENT_TIMESTAMP
                            WHERE hospital_id = ?
                              AND blood_group = ?
                        """, (
                            transfer["units"],
                            transfer["to_hospital_id"],
                            normalize_group(transfer["blood_group"])
                        ))

                        if result.rowcount == 0:
                            self.send_json({
                                "error": (
                                    "Destination inventory row was not found"
                                )
                            }, 400)
                            return

                        # Use the uppercase status allowed by your database.
                        connection.execute("""
                            UPDATE blood_transfers
                            SET status = 'COMPLETED',
                                completed_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (transfer_id,))

                    self.send_json({
                        "message": "Transfer received and marked COMPLETED",
                        "inventory": build_inventory()
                    })
                finally:
                    connection.close()

                return

            self.send_json({"error": "Route not found"}, 404)

        except (KeyError, ValueError, json.JSONDecodeError) as error:
            self.send_json({
                "error": f"Invalid request data: {error}"
            }, 400)

        except (sqlite3.Error, FileNotFoundError) as error:
            self.send_json({"error": str(error)}, 500)


server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)

print("Demo running at http://127.0.0.1:8000")
print("Using database:", DB_FILE)
print("Press Ctrl+C to stop the server.")

server.serve_forever()