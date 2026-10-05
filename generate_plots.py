import os
import sqlite3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, roc_curve, auc
from sklearn.preprocessing import label_binarize
import joblib

os.makedirs("outputs", exist_ok=True)
DB_PATH = "blood_prediction.db"
MODEL_PATH = "sqlite_blood_shortage_model.joblib"

# 1. Load data
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query("SELECT * FROM hospital_inventory_logs", conn)
conn.close()

categorical_features = ['hospital_id', 'region_tier', 'blood_group']
numeric_features = [
    'month', 'day_of_week', 'is_festival_season', 'monsoon_dengue_peak',
    'emergency_admissions_past_24h', 'scheduled_surgeries_next_48h',
    'current_stock_units', 'avg_daily_consumption_7d', 'expected_donations_next_24h'
]

X = df[categorical_features + numeric_features]
y = df['shortage_risk']

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

# 2. Load Pipeline
pipeline = joblib.load(MODEL_PATH)
y_pred = pipeline.predict(X_test)
y_prob = pipeline.predict_proba(X_test)

# --- CHART 1: CONFUSION MATRIX ---
plt.figure(figsize=(7, 6))
cm = confusion_matrix(y_test, y_pred, normalize='true')
sns.heatmap(
    cm, annot=True, fmt=".2%", cmap="Blues",
    xticklabels=['Sufficient (0)', 'Warning (1)', 'Critical (2)'],
    yticklabels=['Sufficient (0)', 'Warning (1)', 'Critical (2)']
)
plt.title("Normalized Confusion Matrix - Blood Shortage Risk")
plt.xlabel("Predicted Class")
plt.ylabel("True Class")
plt.tight_layout()
plt.savefig("outputs/confusion_matrix.png", dpi=300)
plt.close()
print(" Saved: outputs/confusion_matrix.png")

# --- CHART 2: MULTICLASS ROC CURVE ---
y_test_bin = label_binarize(y_test, classes=[0, 1, 2])
plt.figure(figsize=(8, 6))
colors = ['#2ca02c', '#ff7f0e', '#d62728']
labels = ['Sufficient', 'Warning', 'Critical Shortage']

for i in range(3):
    fpr, tpr, _ = roc_curve(y_test_bin[:, i], y_prob[:, i])
    roc_auc = auc(fpr, tpr)
    plt.plot(fpr, tpr, color=colors[i], lw=2, label=f'{labels[i]} (AUC = {roc_auc:.3f})')

plt.plot([0, 1], [0, 1], 'k--', lw=1.5)
plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('Multiclass Receiver Operating Characteristic (One-vs-Rest)')
plt.legend(loc="lower right")
plt.grid(True, linestyle="--", alpha=0.6)
plt.tight_layout()
plt.savefig("outputs/roc_curves.png", dpi=300)
plt.close()
print(" Saved: outputs/roc_curves.png")

# --- CHART 3: TOP FEATURE IMPORTANCES ---
model = pipeline.named_steps['classifier']
preprocessor = pipeline.named_steps['preprocessor']
feature_names = preprocessor.get_feature_names_out()
importances = model.feature_importances_

fi_df = pd.DataFrame({'feature': feature_names, 'importance': importances})
fi_df = fi_df.sort_values(by='importance', ascending=False).head(10)

plt.figure(figsize=(9, 5))
sns.barplot(data=fi_df, x='importance', y='feature', palette='viridis')
plt.title("Top 10 Drivers of Blood Supply Deficits")
plt.xlabel("Relative Importance Weight")
plt.ylabel("Clinical / Operational Feature")
plt.tight_layout()
plt.savefig("outputs/feature_importance.png", dpi=300)
plt.close()
print(" Saved: outputs/feature_importance.png")