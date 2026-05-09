# model.py
from xgboost import XGBRegressor

def build_model():
    # استخدام XGBoost لتحسين دقة التنبؤ
    model = XGBRegressor(
        n_estimators=200,
        learning_rate=0.05, # إضافة معدل التعلم يحسن النتائج جداً
        max_depth=6,        # يمنع الموديل من حفظ البيانات (Overfitting)
        random_state=42
    )
    return model
