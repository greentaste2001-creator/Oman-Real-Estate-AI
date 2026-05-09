import pandas as pd

def clean_data():
    file_name = 'Copy of real state.xlsx'
    try:
        df = pd.read_excel(file_name)
        print(f"📊 عدد البيانات قبل التنظيف: {len(df)}")

        # حذف المتطرفين (أقل من 5% وأعلى من 5%)
        lower_limit = df['Price'].quantile(0.05)
        upper_limit = df['Price'].quantile(0.95)

        df_cleaned = df[(df['Price'] >= lower_limit) & (df['Price'] <= upper_limit)]
        
        # حفظ التعديل على نفس الملف
        df_cleaned.to_excel(file_name, index=False)
        print(f"✅ تم التنظيف. النطاق المنطقي: {lower_limit:.0f} - {upper_limit:.0f}")
        print(f"📊 عدد البيانات بعد التنظيف: {len(df_cleaned)}")
    except Exception as e:
        print(f"❌ خطأ: تأكدي من إغلاق ملف الإكسيل أولاً. {e}")

if __name__ == "__main__":
    clean_data()