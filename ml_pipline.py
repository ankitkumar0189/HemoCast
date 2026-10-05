import sqlite3
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.utils.class_weight import compute_sample_weight
import xgboost as xgb
import joblib

DB_PATH = "blood_prediction.db"

# ==========================================================
# 1. SQLITE SCHEMA INITIALIZATION & DATA SEEDING
# ==========================================================
def setup_sqlite_database():
    """Initializes SQLite tables and seeds realistic operational data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Drop old tables if re-running
    cursor.execute("DROP TABLE IF EXISTS hospital_inventory_logs")
    cursor.execute("DROP TABLE IF EXISTS shortage_alerts")

    # Table 1: Historical records used for training
    cursor.execute("""
        CREATE TABLE hospital_inventory_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id TEXT,
            region_tier TEXT,
            blood_group TEXT,
            month INTEGER,
            day_of_week INTEGER,
            is_festival_season INTEGER,
            monsoon_dengue_peak INTEGER,
            emergency_admissions_past_24h INTEGER,
            scheduled_surgeries_next_48h INTEGER,
            current_stock_units INTEGER,
            avg_daily_consumption_7d REAL,
            expected_donations_next_24h INTEGER,
            shortage_risk INTEGER
        )
    """)

    # Table 2: Model output table for risk monitoring
    cursor.execute("""
        CREATE TABLE shortage_alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id TEXT,
            blood_group TEXT,
            predicted_status TEXT,
            critical_risk_probability REAL,
            warning_risk_probability REAL,
            safe_probability REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed 20,000 synthetic clinical records directly into SQLite
    np.random.seed(42)
    n_samples = 20000

    blood_groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
    hospitals = [f"HOSP_{i:02d}" for i in range(1, 16)]
    regions = ['Urban-Metro', 'Semi-Urban', 'Rural-District']

    df_seed = pd.DataFrame({
        'hospital_id': np.random.choice(hospitals, n_samples),
        'region_tier': np.random.choice(regions, n_samples, p=[0.55, 0.30, 0.15]),
        'blood_group': np.random.choice(blood_groups, n_samples, p=[0.24, 0.04, 0.32, 0.05, 0.08, 0.02, 0.21, 0.04]),
        'month': np.random.randint(1, 13, n_samples),
        'day_of_week': np.random.randint(0, 7, n_samples),
        'is_festival_season': np.random.choice([0, 1], n_samples, p=[0.85, 0.15]),
        'monsoon_dengue_peak': np.random.choice([0, 1], n_samples, p=[0.75, 0.25]),
        'emergency_admissions_past_24h': np.random.poisson(lam=7, size=n_samples),
        'scheduled_surgeries_next_48h': np.random.poisson(lam=14, size=n_samples),
        'current_stock_units': np.random.randint(2, 90, n_samples),
        'avg_daily_consumption_7d': np.random.uniform(4.0, 30.0, n_samples).round(2),
        'expected_donations_next_24h': np.random.poisson(lam=6, size=n_samples),
    })

    # Ground truth: net inventory balance over 48 hours
    projected_consumption = (
        df_seed['avg_daily_consumption_7d'] * 1.6
        + df_seed['emergency_admissions_past_24h'] * 2.1
        + df_seed['scheduled_surgeries_next_48h'] * 0.95
        + df_seed['monsoon_dengue_peak'] * 6.5
    )
    net_units = (df_seed['current_stock_units'] + df_seed['expected_donations_next_24h']) - projected_consumption

    df_seed['shortage_risk'] = np.select(
        [net_units < 0, (net_units >= 0) & (net_units < 12)],
        [2, 1],  # 2: Critical, 1: Warning
        default=0  # 0: Sufficient
    )

    # Insert into SQLite
    df_seed.to_sql('hospital_inventory_logs', conn, if_exists='append', index=False)
    conn.commit()
    conn.close()
    print(f" SQLite database '{DB_PATH}' seeded with {n_samples} records.")


# ==========================================================
# 2. LOAD DATA FROM SQLITE & TRAIN ML MODEL
# ==========================================================
def train_model_from_sqlite():
    """Pulls data from SQLite, trains the model, and validates performance."""
    conn = sqlite3.connect(DB_PATH)

    # Fetch training records via SQL query
    query = """
        SELECT hospital_id, region_tier, blood_group, month, day_of_week,
               is_festival_season, monsoon_dengue_peak, emergency_admissions_past_24h,
               scheduled_surgeries_next_48h, current_stock_units, avg_daily_consumption_7d,
               expected_donations_next_24h, shortage_risk
        FROM hospital_inventory_logs
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    categorical_features = ['hospital_id', 'region_tier', 'blood_group']
    numeric_features = [
        'month', 'day_of_week', 'is_festival_season', 'monsoon_dengue_peak',
        'emergency_admissions_past_24h', 'scheduled_surgeries_next_48h',
        'current_stock_units', 'avg_daily_consumption_7d', 'expected_donations_next_24h'
    ]

    X = df[categorical_features + numeric_features]
    y = df['shortage_risk']

    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_features),
            ('num', StandardScaler(), numeric_cols := numeric_features)
        ]
    )

    sample_weights = compute_sample_weight('balanced', y)

    pipeline = Pipeline(steps=[
        ('preprocessor', preprocessor),
        ('classifier', xgb.XGBClassifier(
            n_estimators=200,
            learning_rate=0.06,
            max_depth=5,
            objective='multi:softprob',
            num_class=3,
            eval_metric='mlogloss',
            random_state=42,
            n_jobs=-1
        ))
    ])

    print("\n Training model on SQLite dataset...")
    pipeline.fit(X, y, classifier__sample_weight=sample_weights)

    joblib.dump(pipeline, "sqlite_blood_shortage_model.joblib")
    print(" Model trained and serialized to 'sqlite_blood_shortage_model.joblib'.")
    return pipeline


# ==========================================================
# 3. INFERENCE ENGINE & SAVING RESULTS TO SQLITE
# ==========================================================
def predict_and_store_alerts(new_data: pd.DataFrame):
    """Generates predictions and writes shortage alerts back into SQLite."""
    pipeline = joblib.load("sqlite_blood_shortage_model.joblib")

    probs = pipeline.predict_proba(new_data)
    preds = pipeline.predict(new_data)

    labels = {0: "Sufficient", 1: "Warning", 2: "Critical Shortage"}

    results_df = pd.DataFrame({
        'hospital_id': new_data['hospital_id'],
        'blood_group': new_data['blood_group'],
        'predicted_status': [labels[p] for p in preds],
        'critical_risk_probability': probs[:, 2].round(4),
        'warning_risk_probability': probs[:, 1].round(4),
        'safe_probability': probs[:, 0].round(4)
    })

    # Save alerts into SQLite
    conn = sqlite3.connect(DB_PATH)
    results_df.to_sql('shortage_alerts', conn, if_exists='append', index=False)

    # Read back high-risk rows from SQLite
    high_risk_query = """
        SELECT hospital_id, blood_group, predicted_status, critical_risk_probability
        FROM shortage_alerts
        WHERE predicted_status IN ('Critical Shortage', 'Warning')
        ORDER BY critical_risk_probability DESC
    """
    alerts = pd.read_sql_query(high_risk_query, conn)
    conn.close()

    return alerts


# ==========================================================
# 4. EXECUTION
# ==========================================================
if __name__ == '__main__':
    # 1. Initialize SQLite database
    setup_sqlite_database()

    # 2. Train model from SQLite data
    train_model_from_sqlite()

    # 3. Test on new incoming hospital status
    incoming_data = pd.DataFrame([
        {
            'hospital_id': 'HOSP_02',
            'region_tier': 'Urban-Metro',
            'blood_group': 'O-',
            'month': 10,
            'day_of_week': 1,
            'is_festival_season': 0,
            'monsoon_dengue_peak': 1,
            'emergency_admissions_past_24h': 16,
            'scheduled_surgeries_next_48h': 24,
            'current_stock_units': 4,
            'avg_daily_consumption_7d': 22.0,
            'expected_donations_next_24h': 2
        },
        {
            'hospital_id': 'HOSP_05',
            'region_tier': 'Rural-District',
            'blood_group': 'B+',
            'month': 10,
            'day_of_week': 1,
            'is_festival_season': 0,
            'monsoon_dengue_peak': 0,
            'emergency_admissions_past_24h': 2,
            'scheduled_surgeries_next_48h': 4,
            'current_stock_units': 50,
            'avg_daily_consumption_7d': 6.0,
            'expected_donations_next_24h': 8
        }
    ])

    print("\n Predicting and persisting alerts to SQLite...")
    alerts = predict_and_store_alerts(incoming_data)
    print("\n--- HIGH-RISK ALERTS PERSISTED IN SQLITE ---")
    print(alerts)