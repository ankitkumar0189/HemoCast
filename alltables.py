import sqlite3
import pandas as pd

# Set display options so pandas doesn't truncate rows or columns
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)

conn = sqlite3.connect("blood_prediction.db")

print("=" * 60)
print("1. ALL PREDICTION ALERTS (Including Sufficient / Safe)")
print("=" * 60)
alerts_df = pd.read_sql_query("SELECT * FROM shortage_alerts", conn)
print(alerts_df)

print("\n" + "=" * 60)
print("2. HISTORICAL INVENTORY LOGS (First 10 of 20,000)")
print("=" * 60)
sample_logs = pd.read_sql_query("SELECT * FROM hospital_inventory_logs LIMIT 10", conn)
print(sample_logs)

print("\n" + "=" * 60)
print("3. HISTORICAL SUMMARY BY STATUS")
print("=" * 60)
summary_df = pd.read_sql_query("""
    SELECT 
        CASE shortage_risk 
            WHEN 0 THEN 'Sufficient' 
            WHEN 1 THEN 'Warning' 
            WHEN 2 THEN 'Critical Shortage' 
        END AS risk_category,
        COUNT(*) AS total_count,
        ROUND(AVG(current_stock_units), 2) AS avg_stock,
        ROUND(AVG(emergency_admissions_past_24h), 2) AS avg_emergencies
    FROM hospital_inventory_logs
    GROUP BY shortage_risk
""", conn)
print(summary_df)

conn.close()