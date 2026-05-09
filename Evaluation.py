import pandas as pd
import psycopg2
import pickle
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score

def evaluate():
    try:
        db_url = "postgresql://real_estate_db_cg70_user:yh1FPDg40EqgIxP0fkcqj7c23ekARCS6@dpg-d7vplsbtqb8s73fjf1rg-a.oregon-postgres.render.com/real_estate_db_cg70"
        engine = create_engine(db_url)
        df = pd.read_sql("SELECT * FROM market_data", engine)
        if df.empty:
            print("⚠️ قاعدة البيانات فارغة، تأكدي من تشغيل السكريب أولاً.")
            return
        # تحميل الموديل والمشفرات فقط
        with open('model.pkl', 'rb') as f:
            model = pickle.load(f)
        with open('encoders.pkl', 'rb') as f:
            encoders = pickle.load(f)

        def safe_transform(encoder, column):
            return df[column].apply(lambda x: encoder.transform([x])[0] if x in encoder.classes_ else -1)

        df['property_type'] = safe_transform(encoders['property_type'], 'property_type')
        df['governorate'] = safe_transform(encoders['governorate'], 'governorate')
        df['wilayat'] = safe_transform(encoders['wilayat'], 'wilayat')
        
        # تجهيز باقي الأعمدة
        df['building_age'] = pd.to_numeric(df['building_age'], errors='coerce').fillna(0)
        df['floor'] = pd.to_numeric(df['floor'], errors='coerce').fillna(0)

        # الترتيب الـ 8 أعمدة المطلوب
        features = ['property_type', 'area', 'bedrooms', 'bathrooms', 'governorate', 'wilayat', 'floor', 'building_age']
        X = df[features]
        y_true = df['price']

        y_pred = model.predict(X)

        print("\n✅ التقييم تم بنجاح:")
        print(f"MAE: {mean_absolute_error(y_true, y_pred):.2f}")
        print(f"R2 Score: {r2_score(y_true, y_pred):.4f}")

    except Exception as e:
        print(f"❌ خطأ: {e}")
    finally:
        if engine:
            engine.dispose()

if __name__ == "__main__":
    evaluate()
