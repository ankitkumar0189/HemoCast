# Autonomous Blood Shortage Predictive Network & Dispatch Coordinator

A machine learning and logistics system designed to forecast regional blood shortages and optimize emergency inter-facility redistribution before critical depletion.

## Core Architecture
- **Inference Engine**: Stratified XGBoost Multi-Class Classifier trained on operational, seasonal, and emergency metrics.
- **Persistence Layer**: Local SQLite database storing transactional hospital inventory logs and real-time alerts.
- **Coordination Layer**: Multi-node resource allocator that pairs deficit facilities with compatible surplus units.
- **Explainability**: SHAP (SHapley Additive exPlanations) for clinical attribution on critical shortage decisions.

## Quickstart

### 1. Setup Environment
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install numpy pandas scikit-learn xgboost joblib scipy shap matplotlib seaborn pytest