import pandas as pd
import psycopg2
from xgboost import XGBRegressor
from sklearn.preprocessing import LabelEncoder
import pickle

def retrain():
    db = None # تعريف المتغير خارج try لتجنب خطأ في finally
    try:
        # 1. الاتصال بـ Render
        db = psycopg2.connect(
            host="dpg-d7vplsbtqb8s73fjf1rg-a.oregon-postgres.render.com",
            user="real_estate_db_cg70_user",
            password="yh1FPDg40EqgIxP0fkcqj7c23ekARCS6",
            database="real_estate_db_cg70",
            port="5432"
        )
        
        # 2. جلب البيانات
        query = "SELECT * FROM market_data"
        df = pd.read_sql(query, db)
        
        # توحيد المسميات
        df['property_type'] = df['property_type'].replace('Apartments', 'Apartment')
        
        # تنظيف القيم الشاذة
        df = df[df['price'] < df['price'].quantile(0.95)] 

        # 3. تحويل النصوص لأرقام
        le_props = LabelEncoder()
        le_gov = LabelEncoder()
        le_wilayat = LabelEncoder()

        df['property_type'] = le_props.fit_transform(df['property_type'])
        df['governorate'] = le_gov.fit_transform(df['governorate'])
        df['wilayat'] = le_wilayat.fit_transform(df['wilayat'])
        
        df['building_age'] = pd.to_numeric(df['building_age'], errors='coerce').fillna(0)
        df['floor'] = pd.to_numeric(df['floor'], errors='coerce').fillna(0)

        X = df[['property_type', 'area', 'bedrooms', 'bathrooms', 'governorate', 'wilayat', 'floor', 'building_age']]
        y = df['price']

        # 4. تدريب الموديل
        model = XGBRegressor(
            n_estimators=200, 
            learning_rate=0.05, 
            max_depth=6, 
            random_state=42
        )
        model.fit(X, y)

        # 5. حفظ الموديل والمشفرات
        with open('model.pkl', 'wb') as f:
            pickle.dump(model, f)
        
        encoders = {'property_type': le_props, 'governorate': le_gov, 'wilayat': le_wilayat}
        with open('encoders.pkl', 'wb') as f:
            pickle.dump(encoders, f)

        print(f"🎯 XGBoost Model Retrained Successfully! Data size: {len(df)}")

    except Exception as e:
        print(f"❌ Error during retraining: {e}")
    finally:
        if db:
            db.close()
            print("🔒 Connection closed.")

if __name__ == "__main__":
    retrain()
