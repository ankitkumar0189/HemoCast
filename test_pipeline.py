import pytest
import sqlite3
import numpy as np
import pandas as pd
import joblib
from coordinator import COMPATIBILITY

DB_PATH = "blood_prediction.db"
MODEL_PATH = "sqlite_blood_shortage_model.joblib"

def test_database_tables_exist():
    """Verify that required SQLite tables exist and have seeded data."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM hospital_inventory_logs")
    log_count = cursor.fetchone()[0]
    conn.close()
    assert log_count > 0, "hospital_inventory_logs should not be empty."

def test_ml_pipeline_inference_bounds():
    """Verify inference probabilities are mathematically bounded."""
    pipeline = joblib.load(MODEL_PATH)
    dummy_input = pd.DataFrame([{
        'hospital_id': 'HOSP_01',
        'region_tier': 'Urban-Metro',
        'blood_group': 'O+',
        'month': 5,
        'day_of_week': 2,
        'is_festival_season': 0,
        'monsoon_dengue_peak': 0,
        'emergency_admissions_past_24h': 4,
        'scheduled_surgeries_next_48h': 8,
        'current_stock_units': 35,
        'avg_daily_consumption_7d': 12.0,
        'expected_donations_next_24h': 5
    }])
    
    probs = pipeline.predict_proba(dummy_input)[0]
    pred = pipeline.predict(dummy_input)[0]

    assert pred in [0, 1, 2], f"Predicted class {pred} out of valid range [0, 1, 2]."
    assert np.isclose(np.sum(probs), 1.0, atol=1e-4), "Probabilities must sum to 1.0."
    assert all(0.0 <= p <= 1.0 for p in probs), "Individual probabilities must be bounded [0, 1]."

def test_blood_compatibility_matrix():
    """Verify clinical transfer rules (e.g., O- can only receive O-)."""
    assert COMPATIBILITY['O-'] == ['O-'], "O- cannot receive non-O- red cells."
    assert 'O-' in COMPATIBILITY['AB+'], "AB+ must be a universal recipient for RBC."
    assert 'A+' not in COMPATIBILITY['O-'], "A+ must never be allocated to an O- deficit."