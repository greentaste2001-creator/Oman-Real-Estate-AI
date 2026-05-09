import pandas as pd
import psycopg2
from datetime import datetime
import requests  # المكتبة الجديدة لجلب البيانات من الإنترنت

def get_live_oman_inflation():
    """جلب نسبة التضخم الحية لسلطنة عمان من البنك الدولي"""
    try:
        # رابط API البنك الدولي لبيانات التضخم في عمان
        url = "https://api.worldbank.org/v2/country/OMN/indicator/FP.CPI.TOTL.ZG?format=json"
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # البحث عن أول قيمة رقمية متوفرة في القائمة
        for record in data[1]:
            if record['value'] is not None:
                rate = float(record['value']) / 100
                print(f"🌍 تم جلب نسبة التضخم الحية من البنك الدولي: {rate*100:.2f}%")
                return rate
    except Exception as e:
        print(f"⚠️ تعذر الاتصال بالبنك الدولي، تم استخدام النسبة الافتراضية (3%): {e}")
    
    return 0.03  # القيمة الاحتياطية

def scrape_data():
    try:
        # 1. الاتصال بقاعدة البيانات
        db = psycopg2.connect(
            host="dpg-d7vplsbtqb8s73fjf1rg-a.oregon-postgres.render.com",
            user="real_estate_db_cg70_user",
            password="yh1FPDg40EqgIxP0fkcqj7c23ekARCS6",
            database="real_estate_db_cg70",
            port="5432"
        )
        cursor = db.cursor()

        # 2. جلب نسبة التضخم الحية
        inflation_rate = get_live_oman_inflation()
        day_of_year = datetime.now().timetuple().tm_yday
        adjustment_factor = 1 + ((inflation_rate / 365) * day_of_year)
        
        print(f"🔄 جاري تحديث الأسعار... معامل التعديل اليومي: {adjustment_factor:.6f}")

        # 3. قراءة ملف الإكسيل
        file_path = 'Copy of real state.xlsx'
        df = pd.read_excel(file_path)

        # مسح البيانات القديمة لتجنب التكرار
        cursor.execute("DELETE FROM market_data")

        # 4. تنظيف وإدخال البيانات
        for _, row in df.iterrows():
            # أ) معالجة السعر مع التضخم
            original_price = float(row['Price'])
            adjusted_price = original_price * adjustment_factor
            
            # ب) تنظيف عدد الغرف (Studio = 0)
            bd_raw = str(row['Bedrooms']).strip().lower()
            bd_val = 0 if 'studio' in bd_raw else int(float(bd_raw)) if bd_raw.replace('.','').isdigit() else 0

            # ج) إدخال البيانات
            sql = """INSERT INTO market_data 
                     (property_type, area, bedrooms, bathrooms, governorate, wilayat, floor, building_age, price) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            
            values = (
                str(row['Property Type']).strip(),
                row['Surface Area'],
                bd_val,
                row['Bathrooms'],
                str(row['Governorate']).strip(),
                str(row['Wilayat']).strip(),
                row['Floor'],
                str(row['Building Age']).strip(),
                adjusted_price
            )
            cursor.execute(sql, values)

        db.commit()
        print(f"✅ تم بنجاح مزامنة {len(df)} عقار بناءً على بيانات التضخم الحية.")

    except Exception as e:
        print(f"❌ خطأ في عملية المزامنة: {e}")
    finally:
        if db:
            cursor.close()
            db.close()
            print("🔒 تم إغلاق الاتصال بالقاعدة.")

if __name__ == "__main__":
    scrape_data()
