import joblib
from sklearn.datasets import load_breast_cancer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# 1. Load data
data = load_breast_cancer()
X, y = data.data, data.target

# 2. Split into Train (80%) and Test (20%) sets
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.20, random_state=42, stratify=y
)

# 3. Preprocess / Scale features
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)  # Never fit on test data!

# 4. Initialize and Train the Model
model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train_scaled, y_train)

# 5. Evaluate on unseen test data
y_pred = model.predict(X_test_scaled)
print(classification_report(y_test, y_pred, target_names=data.target_names))

# 6. Save the trained model for production
joblib.dump({"scaler": scaler, "model": model}, "cancer_classifier.joblib")