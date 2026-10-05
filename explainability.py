import joblib
import pandas as pd
import numpy as np
import shap

MODEL_PATH = "sqlite_blood_shortage_model.joblib"

def explain_prediction(sample_data: pd.DataFrame):
    # Load pipeline
    pipeline = joblib.load(MODEL_PATH)
    preprocessor = pipeline.named_steps['preprocessor']
    classifier = pipeline.named_steps['classifier']

    # Transform input features
    transformed_features = preprocessor.transform(sample_data)
    feature_names = preprocessor.get_feature_names_out()

    # Build TreeExplainer for XGBoost
    explainer = shap.TreeExplainer(classifier)
    shap_values = explainer.shap_values(transformed_features)

    # Class 2 corresponds to Critical Shortage
    critical_shap = shap_values[:, :, 2] if len(shap_values.shape) == 3 else shap_values[2]

    print("\n--- SHAP CLINICAL FEATURE ATTRIBUTION ---")
    for row_idx in range(len(sample_data)):
        print(f"\nFacility: {sample_data.iloc[row_idx]['hospital_id']} | Blood Group: {sample_data.iloc[row_idx]['blood_group']}")
        
        # Rank features by absolute impact on Critical Shortage class
        row_impacts = pd.DataFrame({
            'Feature': feature_names,
            'SHAP Value (Impact)': critical_shap[row_idx],
            'Absolute Impact': np.abs(critical_shap[row_idx])
        }).sort_values(by='Absolute Impact', ascending=False)

        top_contributors = row_impacts.head(5)
        for _, item in top_contributors.iterrows():
            direction = "INCREASED RISK" if item['SHAP Value (Impact)'] > 0 else "DECREASED RISK"
            print(f"  * {item['Feature']}: {direction} ({item['SHAP Value (Impact)']:+.4f})")

if __name__ == '__main__':
    # Sample high-risk test point
    test_case = pd.DataFrame([{
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
    }])
    explain_prediction(test_case)