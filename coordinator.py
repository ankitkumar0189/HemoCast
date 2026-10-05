import sqlite3
import pandas as pd
import numpy as np
from scipy.optimize import linear_sum_assignment

DB_PATH = "blood_prediction.db"

# Matrix of standard red blood cell compatibility
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

def coordinate_blood_transfers():
    conn = sqlite3.connect(DB_PATH)
    
    # 1. Fetch current statuses and stock
    query = """
        SELECT l.hospital_id, l.blood_group, l.current_stock_units, a.predicted_status, a.critical_risk_probability
        FROM hospital_inventory_logs l
        JOIN shortage_alerts a ON l.hospital_id = a.hospital_id AND l.blood_group = a.blood_group
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    # Identify Deficit (Critical) vs Surplus (Sufficient with stock > safety buffer)
    safety_buffer = 25
    deficits = df[df['predicted_status'] == 'Critical Shortage'].copy()
    surpluses = df[(df['predicted_status'] == 'Sufficient') & (df['current_stock_units'] > safety_buffer)].copy()

    if deficits.empty:
        print("No critical shortages detected across the network. Coordination not needed.")
        return
    if surpluses.empty:
        print("ALERT: Shortages detected, but no hospitals currently have surplus units above buffer.")
        return

    print(f"\n--- RESOURCE COORDINATION PLAN ({len(deficits)} Deficits Found) ---")

    dispatch_plan = []
    for _, deficit_row in deficits.iterrows():
        target_hosp = deficit_row['hospital_id']
        needed_bg = deficit_row['blood_group']
        compatible_donors = COMPATIBILITY[needed_bg]

        # Find potential donor hospitals with compatible blood
        eligible_donors = surpluses[surpluses['blood_group'].isin(compatible_donors)].copy()
        
        # Exclude same hospital
        eligible_donors = eligible_donors[eligible_donors['hospital_id'] != target_hosp]

        if not eligible_donors.empty:
            # Pick donor with highest surplus margin
            best_donor = eligible_donors.sort_values(by='current_stock_units', ascending=False).iloc[0]
            transfer_qty = min(15, best_donor['current_stock_units'] - safety_buffer)

            dispatch_plan.append({
                "Recipient Hospital": target_hosp,
                "Recipient Needs": needed_bg,
                "Donor Hospital": best_donor['hospital_id'],
                "Dispatched Blood Group": best_donor['blood_group'],
                "Units to Transfer": transfer_qty,
                "Recipient Deficit Risk": f"{deficit_row['critical_risk_probability']*100:.1f}%"
            })
            
            # Decrement locally to avoid double-allocation
            surpluses.loc[surpluses.index == best_donor.name, 'current_stock_units'] -= transfer_qty

    plan_df = pd.DataFrame(dispatch_plan)
    if not plan_df.empty:
        print(plan_df.to_string(index=False))
    else:
        print("Unable to match compatible donor inventory for active deficits.")

if __name__ == '__main__':
    coordinate_blood_transfers()