import urllib.request
import sqlite3
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import xgboost as xgb

UCI_URL = "https://archive.ics.uci.edu/ml/machine-learning-databases/blood-transfusion/transfusion.data"
DB_PATH = "blood_prediction.db"

def ingest_and_train_uci():
    print("Downloading UCI Blood Transfusion Service Center dataset...")
    df_raw = pd.read_csv(UCI_URL)

    # Standardize column naming
    df_raw.columns = [
        "months_since_last_donation",
        "total_donations",
        "total_volume_cc",
        "months_since_first_donation",
        "donated_target"
    ]

    # 1. Save directly into SQLite
    conn = sqlite3.connect(DB_PATH)
    df_raw.to_sql("uci_donor_history", conn, if_exists="replace", index=False)
    print(f"Persisted {len(df_raw)} records to table 'uci_donor_history' in {DB_PATH}.")

    # 2. Prepare Features & Target
    X = df_raw.drop(columns=["donated_target"])
    y = df_raw["donated_target"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    # 3. Train Donor Likelihood Estimator
    donor_model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.05,
        scale_pos_weight=(len(y) - sum(y)) / sum(y), # Handle class imbalance
        random_state=42
    )

    print("Training donor re-donation model...")
    donor_model.fit(X_train, y_train)

    preds = donor_model.predict(X_test)
    print("\nUCI Donor Prediction Performance:")
    print(classification_report(y_test, preds, target_names=["No Donation (0)", "Donated (1)"]))

    conn.close()

if __name__ == '__main__':
    ingest_and_train_uci()