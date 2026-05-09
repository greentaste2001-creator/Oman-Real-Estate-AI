import pandas as pd
import psycopg2
import pickle
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score

def evaluate():
    db = None
    try:
        # الاتصال المباشر (نفس الطريقة اللي نجحت معك في الملفات السابقة)
        db = psycopg2.connect(
            host="dpg-d7vplsbtqb8s73fjf1rg-a.oregon-postgres.render.com",
            user="real_estate_db_cg70_user",
            password="yh1FPDg40EqgIxP0fkcqj7c23ekARCS6",
            database="real_estate_db_cg70",
            port="5432"
        )
        
        # جلب البيانات
        query = "SELECT * FROM market_data"
        df = pd.read_sql(query, db)
        
        if df.empty:
            print("⚠️ قاعدة البيانات فارغة!")
            return

        # تحميل الموديل والمشفرات
        with open('model.pkl', 'rb') as f:
            model = pickle.load(f)
        with open('encoders.pkl', 'rb') as f:
            encoders = pickle.load(f)

        def safe_transform(encoder, column):
            return df[column].apply(lambda x: encoder.transform([x])[0] if x in encoder.classes_ else -1)

        # معالجة البيانات
        df['property_type'] = safe_transform(encoders['property_type'], 'property_type')
        df['governorate'] = safe_transform(encoders['governorate'], 'governorate')
        df['wilayat'] = safe_transform(encoders['wilayat'], 'wilayat')
        
        df['building_age'] = pd.to_numeric(df['building_age'], errors='coerce').fillna(0)
        df['floor'] = pd.to_numeric(df['floor'], errors='coerce').fillna(0)
        df['area'] = pd.to_numeric(df['area'], errors='coerce').fillna(0)

        # الترتيب الـ 8 أعمدة
        features = ['property_type', 'area', 'bedrooms', 'bathrooms', 'governorate', 'wilayat', 'floor', 'building_age']
        X = df[features]
        y_true = df['price']

        y_pred = model.predict(X)

        print("\n✅ تم التقييم بنجاح:")
        print(f"📊 متوسط الخطأ (MAE): {mean_absolute_error(y_true, y_pred):.2f} ريال")
        print(f"📈 دقة الموديل (R2 Score): {r2_score(y_true, y_pred):.4f}")

    except Exception as e:
        print(f"❌ خطأ: {e}")
    finally:
        if 'db' in locals() and db:
            db.close()
            print("🔒 تم إغلاق الاتصال.")

if __name__ == "__main__":
    evaluate()
