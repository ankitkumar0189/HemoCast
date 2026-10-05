import os
import joblib
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler, label_binarize
from sklearn.metrics import confusion_matrix, roc_curve, auc, classification_report
import xgboost as xgb


class AutonomousBloodPredictor(BaseEstimator, ClassifierMixin):
    def __init__(self, n_estimators=250, learning_rate=0.05, max_depth=5, output_dir="outputs"):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.output_dir = output_dir

        self.class_names = ["Sufficient (0)", "Warning (1)", "Critical (2)"]
        self.categorical_features = ['hospital_id', 'region_tier', 'blood_group']
        self.numeric_features = [
            'month', 'day_of_week', 'is_festival_season', 'monsoon_dengue_peak',
            'emergency_admissions_past_24h', 'scheduled_surgeries_next_48h',
            'current_stock_units', 'avg_daily_consumption_7d', 'expected_donations_next_24h'
        ]

        # Pipeline components
        self.preprocessor = None
        self.model = None
        
        # Stored validation state for plotting
        self.X_val = None
        self.y_val = None
        self.y_val_pred = None
        self.y_val_prob = None

        os.makedirs(self.output_dir, exist_ok=True)

    def fit(self, X: pd.DataFrame, y: pd.Series):
        """Trains the model and caches a validation split to power internal plotting."""
        # Hold out an internal validation split for evaluation plots
        X_train, self.X_val, y_train, self.y_val = train_test_split(
            X, y, test_size=0.20, random_state=42, stratify=y
        )

        self.preprocessor = ColumnTransformer(
            transformers=[
                ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), self.categorical_features),
                ('num', StandardScaler(), self.numeric_features)
            ]
        )

        X_train_proc = self.preprocessor.fit_transform(X_train)
        X_val_proc = self.preprocessor.transform(self.X_val)

        self.model = xgb.XGBClassifier(
            n_estimators=self.n_estimators,
            learning_rate=self.learning_rate,
            max_depth=self.max_depth,
            objective='multi:softprob',
            num_class=3,
            eval_metric='mlogloss',
            random_state=42,
            n_jobs=-1
        )

        self.model.fit(X_train_proc, y_train)

        # Cache predictions for plotting
        self.y_val_pred = self.model.predict(X_val_proc)
        self.y_val_prob = self.model.predict_proba(X_val_proc)

        print("Model training complete.")
        return self

    def predict(self, X: pd.DataFrame):
        """Inference for class predictions."""
        X_proc = self.preprocessor.transform(X)
        return self.model.predict(X_proc)

    def predict_proba(self, X: pd.DataFrame):
        """Inference for class probability distributions."""
        X_proc = self.preprocessor.transform(X)
        return self.model.predict_proba(X_proc)

    # -------------------------------------------------------------
    # BUILT-IN PLOTTING METHODS
    # -------------------------------------------------------------

    def plot_confusion_matrix(self, filename="confusion_matrix.png"):
        """Generates and saves a normalized confusion matrix heatmap."""
        if self.y_val is None:
            raise ValueError("Model must be fitted before generating plots.")

        cm = confusion_matrix(self.y_val, self.y_val_pred, normalize='true')
        
        plt.figure(figsize=(7, 6))
        sns.heatmap(
            cm, annot=True, fmt=".2%", cmap="Blues",
            xticklabels=self.class_names,
            yticklabels=self.class_names
        )
        plt.title("Confusion Matrix (Normalized)", fontsize=13, fontweight='bold')
        plt.xlabel("Predicted Class")
        plt.ylabel("Actual True Class")
        plt.tight_layout()

        path = os.path.join(self.output_dir, filename)
        plt.savefig(path, dpi=300)
        plt.close()
        print(f" Plot saved: {path}")
        return path

    def plot_roc_curves(self, filename="roc_curves.png"):
        """Generates and saves One-vs-Rest multiclass ROC curves."""
        if self.y_val is None:
            raise ValueError("Model must be fitted before generating plots.")

        y_val_bin = label_binarize(self.y_val, classes=[0, 1, 2])
        colors = ['#10c99a', '#ffbd19', '#ff6276']

        plt.figure(figsize=(8, 6))
        for i in range(3):
            fpr, tpr, _ = roc_curve(y_val_bin[:, i], self.y_val_prob[:, i])
            roc_auc = auc(fpr, tpr)
            plt.plot(fpr, tpr, color=colors[i], lw=2.2, label=f"{self.class_names[i]} (AUC = {roc_auc:.3f})")

        plt.plot([0, 1], [0, 1], 'k--', lw=1.2, label="Random Guessing")
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.title("Multiclass ROC Curves", fontsize=13, fontweight='bold')
        plt.xlabel("False Positive Rate")
        plt.ylabel("True Positive Rate")
        plt.legend(loc="lower right")
        plt.grid(True, linestyle="--", alpha=0.5)
        plt.tight_layout()

        path = os.path.join(self.output_dir, filename)
        plt.savefig(path, dpi=300)
        plt.close()
        print(f" Plot saved: {path}")
        return path

    def plot_feature_importance(self, top_n=10, filename="feature_importance.png"):
        """Extracts preprocessed feature names and plots the top driving factors."""
        if self.model is None:
            raise ValueError("Model must be fitted before generating plots.")

        feature_names = self.preprocessor.get_feature_names_out()
        importances = self.model.feature_importances_

        df_fi = pd.DataFrame({
            'feature': [f.replace('num__', '').replace('cat__', '') for f in feature_names],
            'importance': importances
        }).sort_values(by='importance', ascending=False).head(top_n)

        plt.figure(figsize=(9, 5))
        sns.barplot(data=df_fi, x='importance', y='feature', palette='viridis')
        plt.title(f"Top {top_n} Factors Driving Blood Shortages", fontsize=13, fontweight='bold')
        plt.xlabel("Relative Importance Weight")
        plt.ylabel("Operational / Clinical Feature")
        plt.tight_layout()

        path = os.path.join(self.output_dir, filename)
        plt.savefig(path, dpi=300)
        plt.close()
        print(f" Plot saved: {path}")
        return path

    def generate_all_diagnostics(self):
        """Helper that runs all internal plotting functions at once."""
        print("Generating diagnostic plots from inside the model...")
        self.plot_confusion_matrix()
        self.plot_roc_curves()
        self.plot_feature_importance()
        print("All plots generated successfully.")

    def save(self, filepath="sqlite_blood_shortage_model.joblib"):
        """Serializes the self-plotting model object to disk."""
        joblib.dump(self, filepath)
        print(f"Saved self-plotting model to '{filepath}'")

    @classmethod
    def load(cls, filepath="sqlite_blood_shortage_model.joblib"):
        """Loads the self-plotting model object from disk."""
        return joblib.load(filepath)