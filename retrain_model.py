import pandas as pd
import mysql.connector
from xgboost import XGBRegressor
from sklearn.preprocessing import LabelEncoder
import pickle

def retrain():
    try:
        db = mysql.connector.connect(
            host="localhost", user="root", password="", database="real_estate_vision"
        )
        # جلب البيانات
        df = pd.read_sql("SELECT * FROM market_data", db)
        # توحيد المسميات عشان الموديل ما يتلخبط
        df['property_type'] = df['property_type'].replace('Apartments', 'Apartment')
        
        # 1. تنظيف البيانات من القيم الشاذة (تحسين مهم للدقة)
        # حذف العقارات اللي سعرها مبالغ فيه جداً مقارنة بالمساحة
        df = df[df['price'] < df['price'].quantile(0.95)] 

        # 2. تحويل النصوص إلى أرقام بطريقة ذكية (Label Encoding)
        # هذه الخطوة تحل مشكلة الـ Fragmentation وتساعد XGBoost
        le_props = LabelEncoder()
        le_gov = LabelEncoder()
        le_wilayat = LabelEncoder()

        df['property_type'] = le_props.fit_transform(df['property_type'])
        df['governorate'] = le_gov.fit_transform(df['governorate'])
        df['wilayat'] = le_wilayat.fit_transform(df['wilayat'])
        
        # تحويل "عمر المبنى" و "الطابق" لأرقام إذا كانت نصوصاً
        df['building_age'] = pd.to_numeric(df['building_age'], errors='coerce').fillna(0)
        df['floor'] = pd.to_numeric(df['floor'], errors='coerce').fillna(0)

        X = df[['property_type', 'area', 'bedrooms', 'bathrooms', 'governorate', 'wilayat', 'floor', 'building_age']]
        y = df['price']

        # 3. استخدام XGBoost
        model = XGBRegressor(
            n_estimators=200, 
            learning_rate=0.05, 
            max_depth=6, 
            random_state=42
        )
        model.fit(X, y)

        # 4. حفظ الموديل والمشفرات (encoders) لاستخدامها في التنبؤ
        with open('model.pkl', 'wb') as f:
            pickle.dump(model, f)
        
        # حفظ الـ encoders ضروري عشان الموقع يعرف يترجم كلام المستخدم لأرقام
        encoders = {'property_type': le_props, 'governorate': le_gov, 'wilayat': le_wilayat}
        with open('encoders.pkl', 'wb') as f:
            pickle.dump(encoders, f)

        print(f"🎯 XGBoost Model Retrained Successfully! Data size: {len(df)}")

    except Exception as e:
        print(f"❌ Error during retraining: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    retrain()