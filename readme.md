HEMOCAST is a prototype for predictive blood inventory management and inter-hospital blood transfer.
The system monitors blood availability at multiple hospitals, estimates how long the available stock can last, identifies shortage risk, and supports transferring blood between hospitals.
Note: This prototype currently uses demo demand values and a rule-based risk score. It is not yet a trained machine-learning model.

Main Features
- Stores hospital and blood inventory data in SQLite.
- Supports all 8 common blood groups:
  - A+
  - A-
  - B+
  - B-
  - O+
  - O-
  - AB+
  - AB-
- Calculates estimated blood-stock reserve time.
- Generates a demo shortage-risk score.
- Allows hospital blood stock to be updated.
- Supports inter-hospital blood transfers.
- Tracks transfers as IN_TRANSIT and COMPLETED.
- Provides inventory data to the frontend through an API.
How It Works
Hospital Inventory
       |
       v
   SQLite Database
       |
       v
HEMONET Backend (server.py)
       |
       +--> Calculate estimated demand
       |
       +--> Calculate reserve hours
       |
       +--> Generate shortage-risk score
       |
       v
Shortage Alert / Transfer Decision
       |
       v
Inter-Hospital Blood Transfer
Current Prediction Logic
The prototype uses demo daily-demand values for each blood group.
For example:
O+  -> 9 units/day
A+  -> 6 units/day
B+  -> 7 units/day
The system also applies a hospital-specific demand multiplier.
It then estimates:
Reserve Hours = Available Units / Estimated Daily Use × 24
The current demo risk rules are:
Condition	Risk Score
Stock is at/below critical level OR reserve < 18 hours	99
Reserve < 36 hours	81
Reserve < 48 hours	59
Reserve >= 48 hours	32


Important: These scores are risk indicators, not probabilities.
API Endpoints
Get Inventory
GET /api/inventory
Returns current inventory and calculated risk information for the hospitals.
Update Stock
POST /api/update-stock
Example request:
{
  "hospital": "Hospital A",
  "group": "O+",
  "units": 20
}
This updates the available blood units in the SQLite database.
Dispatch Blood Transfer
POST /api/transfer
Example request:
{
  "group": "O+",
  "fromHospital": "Hospital B",
  "toHospital": "Hospital A",
  "units": 5
}
The source hospital's available stock is reduced immediately, and the transfer is created with status:
IN_TRANSIT
Complete Blood Transfer
POST /api/complete-transfer
Example request:
{
  "transferId": 1
}
When the receiving hospital confirms arrival, its inventory is increased and the transfer status becomes:
COMPLETED
Database
The backend expects a SQLite database named:
blood_prediction.db
It should be located in the same folder as server.py.
The prototype uses tables including:
- hospitals
- blood_inventory
- blood_transfers
Project Structure
HEMONET/
│
├── server.py
├── blood_prediction.db
├── index.html
├── style.css
├── script.js
└── README.md
The exact frontend filenames may differ depending on the prototype setup.
Requirements
- Python 3.x
- SQLite3 (included with standard Python installations)
- A modern web browser
The backend uses Python's built-in libraries, including:
http.server
sqlite3
json
pathlib
urllib
No external Python package is required by server.py.
Running the Prototype
1. Put server.py and blood_prediction.db in the same folder.
2. Open a terminal in that folder.
3. Run:
python server.py
4. Open:
http://127.0.0.1:8000
5. Press Ctrl+C in the terminal to stop the server.
Prototype Limitations
This is a demonstration prototype, so it should not be treated as a production healthcare system.
Current limitations include:
- Demand values are demo assumptions.
- Hospital demand multipliers are predefined.
- The shortage score is rule-based rather than machine-learning based.
- No real hospital database integration is included.
- No authentication or authorization system is implemented.
- No real patient data should be used.
- Blood compatibility and clinical transfusion decisions require proper medical validation.
- Real deployment would require secure APIs, encryption, access control, audit logs, data validation, and appropriate healthcare/privacy compliance.
Future Scope
The prototype can be extended with:
1. Real ML prediction
   - Train a model using historical blood usage.
   - Include surgery schedules, emergency demand, seasonal patterns, and inventory trends.
   - Predict blood requirements 24–48 hours in advance.
2. Hospital API Integration
   - Connect participating hospital systems through secure APIs.
   - Standardize blood inventory data before sending it to HEMONET.
3. Smart Transfer Recommendation
   - Find hospitals with surplus stock.
   - Consider distance, availability, expiry time, and compatibility.
   - Recommend the best transfer route.
4. Real-Time Alerts
   - Notify hospitals when shortage risk becomes critical.
5. Secure Deployment
   - Add authentication, role-based access, encryption, audit logs, and secure cloud infrastructure.