import pickle
import pandas as pd
import os
import re
import sys

def predict(data_dict):
    """
    تستقبل بيانات العقار وتُرجع السعر المتوقع باستخدام XGBoost والمشفرات الرقمية.
    """
    try:
        # 1. تحديد مسارات الملفات (تأكدي أنها في نفس المجلد)
        model_path = "model.pkl"
        encoders_path = "encoders.pkl"

        if not os.path.exists(model_path) or not os.path.exists(encoders_path):
            return "Error: لم يتم العثور على model.pkl أو encoders.pkl. يرجى تشغيل retrain_model.py أولاً."

        # 2. تحميل الموديل والمشفرات باستخدام pickle
        with open(model_path, 'rb') as f:
            model = pickle.load(f)
        with open(encoders_path, 'rb') as f:
            encoders = pickle.load(f)

        # 3. معالجة البيانات النصية وتوحيدها
        prop_type = str(data_dict.get('property_type', 'Apartment'))
        if prop_type == 'Apartments': 
            prop_type = 'Apartment'

        # دالة لتحويل النص لرقم باستخدام المشفر (Encoder)
        def get_encoded_value(encoder, value):
            try:
                if value in encoder.classes_:
                    return encoder.transform([value])[0]
                return -1  # قيمة افتراضية للبيانات الجديدة
            except:
                return -1

        # تحويل النصوص إلى أرقام (البديل الذكي لـ get_dummies)
        property_type_encoded = get_encoded_value(encoders['property_type'], prop_type)
        governorate_encoded = get_encoded_value(encoders['governorate'], data_dict.get('governorate', ''))
        wilayat_encoded = get_encoded_value(encoders['wilayat'], data_dict.get('wilayat', ''))

        # 4. تنظيف وتحويل القيم الرقمية (المساحة، الغرف، الطابق، العمر)
        def extract_number(val):
            try:
                # استخراج أول رقم يظهر في النص (مثلاً "2 years" تصبح 2)
                nums = re.findall(r'\d+', str(val))
                return float(nums[0]) if nums else 0.0
            except:
                return 0.0

        area = float(data_dict.get('area', 0))
        bedrooms = int(data_dict.get('bedrooms', 0))
        bathrooms = int(data_dict.get('bathrooms', 0))
        floor = extract_number(data_dict.get('floor', 0))
        age = extract_number(data_dict.get('building_age', 0))

        # 5. بناء الـ DataFrame النهائي (8 أعمدة رقمية بالترتيب الصحيح)
        # الترتيب الدقيق: property_type, area, bedrooms, bathrooms, governorate, wilayat, floor, building_age
        X_input = pd.DataFrame([[
            property_type_encoded, 
            area, 
            bedrooms, 
            bathrooms, 
            governorate_encoded, 
            wilayat_encoded, 
            float(floor), 
            float(age)
        ]], columns=['property_type', 'area', 'bedrooms', 'bathrooms', 'governorate', 'wilayat', 'floor', 'building_age'])

        # 6. إجراء التنبؤ باستخدام الموديل
        prediction = model.predict(X_input)[0]
        
        # إرجاع السعر مقرباً لخانة عشرية واحدة
        return round(float(prediction), 1)

    except Exception as e:
        return f"❌ خطأ برمجبي: {str(e)}"

# --- هذا الجزء للتشغيل من خلال PHP أو الـ Terminal ---
if __name__ == "__main__":
    # إذا كان هناك بيانات مرسلة عبر Command Line (كـ JSON)
    if len(sys.argv) > 1:
        import json
        try:
            input_json = sys.argv[1]
            data = json.loads(input_json)
            result = predict(data)
            print(result)
        except:
            print("Error: Invalid JSON input")
    else:
        # تجربة يدوية للتأكد من عمل الكود
        sample = {
            "property_type": "Villa",
            "area": 350,
            "bedrooms": 4,
            "bathrooms": 3,
            "governorate": "Muscat",
            "wilayat": "Seeb",
            "floor": 0,
            "building_age": "2"
        }
        print(f"السعر المتوقع للتجربة: {predict(sample)} ريال عماني")