from flask import Flask, render_template, request, redirect, session, jsonify, url_for
import psycopg2
import psycopg2.extras
from flask_bcrypt import Bcrypt
import os
import pandas as pd
import re
import pickle
from werkzeug.utils import secure_filename

# استيراد ملفات السكريب والتدريب (تأكدي أنها موجودة بجانب app.py)
try:
    from scraper import scrape_data
    from retrain_model import retrain
except ImportError:
    def scrape_data(): print("Scraper not found")
    def retrain(): print("Retrain not found")

app = Flask(__name__)
app.secret_key = "secret123"
bcrypt = Bcrypt(app)

# إعدادات المجلدات
UPLOAD_FOLDER = 'static/uploads'
PROFILE_FOLDER = 'static/images/profiles'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROFILE_FOLDER, exist_ok=True)

# رابط قاعدة البيانات الصحيح
DATABASE_URL = "postgresql://real_estate_db_cg70_user:yh1FPDg40EqgIxP0fkcqj7c23ekARCS6@dpg-d7vplsbtqb8s73fjf1rg-a.oregon-postgres.render.com/real_estate_db_cg70"

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

# -------------------- ML LOGIC --------------------
def predict_logic(data_dict):
    try:
        with open('model.pkl', 'rb') as f:
            model = pickle.load(f)
        with open('encoders.pkl', 'rb') as f:
            encoders = pickle.load(f)

        prop_type = data_dict.get('property_type', 'Apartment')
        if 'Apartment' in prop_type: prop_type = 'Apartment'

        def safe_encode(encoder, value):
            return encoder.transform([value])[0] if value in encoder.classes_ else -1

        X_input = pd.DataFrame([[
            safe_encode(encoders['property_type'], prop_type),
            float(data_dict.get('area') or 0),
            int(data_dict.get('bedrooms') or 0),
            float(data_dict.get('bathrooms') or 0),
            safe_encode(encoders['governorate'], data_dict.get('governorate', '')),
            safe_encode(encoders['wilayat'], data_dict.get('wilayat', '')),
            float(re.findall(r'\d+', str(data_dict.get('floor') or 0))[0]) if re.findall(r'\d+', str(data_dict.get('floor') or 0)) else 0.0,
            float(re.findall(r'\d+', str(data_dict.get('building_age') or 0))[0]) if re.findall(r'\d+', str(data_dict.get('building_age') or 0)) else 0.0
        ]], columns=['property_type', 'area', 'bedrooms', 'bathrooms', 'governorate', 'wilayat', 'floor', 'building_age'])

        return float(model.predict(X_input)[0])
    except Exception as e:
        print(f"❌ Prediction Logic Error: {e}")
        return 0.0

# -------------------- ROUTES --------------------
@app.route('/predictions')
def predictions():
    return render_template('predictions.html')

@app.route('/buyer_profile')
def buyer_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM user_info WHERE id=%s", (session['user_id'],))
        user = cur.fetchone()
        if not user: return redirect(url_for('buyer_edit_profile'))
        return render_template('buyer_profile.html', username=user['username'], email=user['email'], phone=user['phone'], profile_image=user['profile_image'])
    finally:
        cur.close()
        db.close()

@app.route('/buyer_edit_profile', methods=['GET', 'POST'])
def buyer_edit_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            file = request.files.get('profile_image')
            img_name = "default.png"
            if file and file.filename != '':
                img_name = secure_filename(file.filename)
                file.save(os.path.join('static/images/profiles', img_name))
            
            cur.execute("""INSERT INTO user_info (id, username, email, phone, profile_image) 
                           VALUES (%s,%s,%s,%s,%s) 
                           ON CONFLICT (id) DO UPDATE SET username=EXCLUDED.username, email=EXCLUDED.email, phone=EXCLUDED.phone, profile_image=EXCLUDED.profile_image""",
                        (session['user_id'], request.form.get('username'), request.form.get('email'), request.form.get('phone'), img_name))
            db.commit()
            return redirect(url_for('buyer_profile'))
        
        cur.execute("SELECT * FROM user_info WHERE id=%s", (session['user_id'],))
        user = cur.fetchone() or {'username': '', 'email': '', 'phone': ''}
        return render_template('buyer_edit_profile.html', user=user)
    finally:
        cur.close()
        db.close()


@app.route('/profile')
def profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # لاحظي: غيرنا اسم الجدول لـ user_info واسم العمود لـ user_id
        cur.execute("SELECT * FROM user_info WHERE user_id=%s", (session['user_id'],))
        user_data = cur.fetchone()
        
        # نرسل user_data للمتصفح
        return render_template('profile.html', user=user_data)
    finally:
        cur.close()
        db.close()

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            new_name = request.form.get('username')
            new_email = request.form.get('email')
            new_phone = request.form.get('phone') # أضفت الهاتف لأنه موجود في جدولك

            # تحديث جدول user_info باستخدام user_id
            cur.execute("""
                UPDATE user_info 
                SET username=%s, email=%s, phone=%s 
                WHERE user_id=%s
            """, (new_name, new_email, new_phone, session['user_id']))
            db.commit()
            
            session['name'] = new_name # لتحديث الاسم في الهيدر
            return redirect(url_for('profile'))

        # في الـ GET جلب البيانات من user_info
        cur.execute("SELECT * FROM user_info WHERE user_id=%s", (session['user_id'],))
        user_data = cur.fetchone()
        return render_template('edit_profile.html', user=user_data)
    finally:
        cur.close()
        db.close()

# --- راوترات إضافية (تحسباً للأخطاء الجاية) ---

@app.route('/property_details/<int:property_id>')
def property_details(property_id):
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM properties WHERE id = %s", (property_id,))
        property_data = cur.fetchone()
        return render_template('property_details.html', property=property_data)
    finally:
        cur.close()
        db.close()


@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
def edit_property(property_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if request.method == 'POST':
            # كود التحديث (Update) لبيانات العقار
            db.commit()
            return redirect(url_for('my_listings'))
        
        cur.execute("SELECT * FROM properties WHERE id=%s AND seller_id=%s", (property_id, session['user_id']))
        prop = cur.fetchone()
        return render_template('seller_edit_property.html', property=prop)
    finally:
        cur.close()
        db.close()

@app.route('/delete_property/<int:property_id>', methods=['POST'])
def delete_property(property_id):
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM favorites WHERE property_id=%s", (property_id,))
        cur.execute("DELETE FROM properties WHERE id=%s AND seller_id=%s", (property_id, session['user_id']))
        db.commit()
        return redirect(url_for('my_listings'))
    finally:
        cur.close()
        db.close()

@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('user_type') != 'admin': return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
        db.commit()
        return redirect(url_for('admin_dashboard'))
    finally:
        cur.close()
        db.close()

@app.route('/approve_property/<int:property_id>', methods=['POST'])
def approve_property(property_id):
    db = get_db_connection()
    cur = db.cursor()
    cur.execute("UPDATE properties SET status='Approved' WHERE id=%s", (property_id,))
    db.commit()
    return redirect(url_for('admin_dashboard'))


@app.route('/')
def homepage():
    return render_template('homepage.html')
@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        db = get_db_connection()
        cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # البحث في جدول user_info حسب صورتك
        cur.execute("SELECT * FROM user_info WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        db.close()

        if user and bcrypt.check_password_hash(user['password'], password):
            # تخزين البيانات في الجلسة (Session)
            session['user_id'] = user['user_id']
            session['name'] = user['username']
            session['user_type'] = user['user_type']

            # التوجيه حسب النوع
            if user['user_type'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif user['user_type'] == 'seller':
                return redirect(url_for('seller_dashboard'))
            else:
                return redirect(url_for('buyer_dashboard'))
        else:
            return "Incorrect Email or Password", 401
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        db = get_db_connection()
        cur = db.cursor()
        try:
            pw = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
            cur.execute("INSERT INTO users (name, email, password, user_type) VALUES (%s,%s,%s,%s)",
                        (request.form['name'], request.form['email'], pw, request.form['user_type']))
            db.commit()
            return redirect(url_for('login'))
        finally:
            cur.close()
            db.close()
    return render_template('register.html')

# --- BUYER ROUTES ---
@app.route('/buyer_dashboard')
def buyer_dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as total FROM properties WHERE status='Approved'")
        avail = cur.fetchone()['total']
        cur.execute("SELECT COUNT(*) as total FROM favorites WHERE user_id=%s", (session['user_id'],))
        favs = cur.fetchone()['total']
        return render_template('buyer_home.html', username=session['name'], available_count=avail, favorite_count=favs)
    finally:
        cur.close()
        db.close()

@app.route('/exploring')
def exploring():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM properties WHERE status IN ('Approved', 'Available') ORDER BY created_at DESC")
        props = cur.fetchall()
        return render_template('exploring.html', properties=props, username=session['name'])
    finally:
        cur.close()
        db.close()

@app.route('/favorite')
def favorite():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""SELECT p.* FROM properties p JOIN favorites f ON p.id = f.property_id WHERE f.user_id = %s""", (session['user_id'],))
        fav_props = cur.fetchall()
        return render_template('favorite.html', favorite_properties=fav_props, username=session['name'])
    finally:
        cur.close()
        db.close()

@app.route('/add_to_favorite/<int:property_id>', methods=['POST'])
def add_to_favorite(property_id):
    if 'user_id' not in session: return jsonify({"status": "error"}), 401
    db = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO favorites (user_id, property_id) VALUES (%s, %s) ON CONFLICT DO NOTHING", (session['user_id'], property_id))
        db.commit()
        return jsonify({"status": "success"})
    finally:
        cur.close()
        db.close()

# --- SELLER ROUTES ---
@app.route('/seller')
def seller_dashboard():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as total FROM properties WHERE seller_id=%s", (session['user_id'],))
        total = cur.fetchone()['total']
        return render_template('seller_dashboard.html', username=session['name'], total_properties=total)
    finally:
        cur.close()
        db.close()

@app.route('/my_listings')
def my_listings():
    if 'user_id' not in session: return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM properties WHERE seller_id=%s", (session['user_id'],))
        props = cur.fetchall()
        return render_template('seller_my_listings.html', properties=props, username=session['name'])
    finally:
        cur.close()
        db.close()

@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        db = get_db_connection()
        cur = db.cursor()
        try:
            img = request.files.get('images')
            fname = secure_filename(img.filename) if img else None
            if fname: img.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            
            cur.execute("""INSERT INTO properties (seller_id, title, governorate, wilayat, property_type, surface_area, bedrooms, bathrooms, floor, building_age, furnishing, price, status, phone, images)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending',%s,%s)""",
                        (session['user_id'], request.form['title'], request.form['governorate'], request.form['wilayat'], request.form['property_type'],
                         request.form['surface_area'], request.form['bedrooms'], request.form['bathrooms'], request.form['floor'], request.form['building_age'],
                         request.form['furnishing'], request.form['price'], request.form['phone'], fname))
            db.commit()
            return redirect(url_for('my_listings'))
        finally:
            cur.close()
            db.close()
    return render_template('seller_add_property.html', username=session['name'])

# --- ADMIN ROUTES ---
@app.route('/admin')
def admin_dashboard():
    if session.get('user_type') != 'admin': return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM users")
        u = cur.fetchall()
        cur.execute("SELECT * FROM properties")
        p = cur.fetchall()
        return render_template('admin_dashboard.html', users=u, properties=p, total_users=len(u), total_properties=len(p))
    finally:
        cur.close()
        db.close()

# --- PREDICT API ---
@app.route('/predict', methods=['POST'])
def make_prediction():
    data = {k: request.form.get(k) for k in ['governorate', 'wilayat', 'property_type', 'area', 'bedrooms', 'bathrooms', 'floor', 'building_age']}
    price = predict_logic(data)
    return jsonify({"predicted_price": round(float(price), 2)})
@app.route('/reject_property/<int:property_id>', methods=['POST'])
def reject_property(property_id):
    if session.get('user_type') != 'admin': return redirect(url_for('login'))
    db = get_db_connection()
    cur = db.cursor()
    try:
        cur.execute("UPDATE properties SET status='Rejected' WHERE id=%s", (property_id,))
        db.commit()
        return redirect(url_for('admin_dashboard'))
    finally:
        cur.close()
        db.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('homepage'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
