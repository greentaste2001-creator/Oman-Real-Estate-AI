from flask import Flask, render_template, request, redirect, session, jsonify, url_for
import psycopg2
from flask_bcrypt import Bcrypt
import os
import joblib
import pandas as pd
import re
import pickle
from werkzeug.utils import secure_filename
from scraper import scrape_data
from retrain_model import retrain

app = Flask(__name__)
app.secret_key = "secret123"
bcrypt = Bcrypt(app)

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# -------------------- الاتصال بقاعدة البيانات --------------------
DATABASE_URL = "رابط_قاعدة_البيانات_هنا"
try:
    conn = psycopg2.connect(DATABASE_URL)
    # نستخدم DictCursor لجعل البيانات تعود على شكل قاموس كما في الكود الأصلي
    from psycopg2.extras import RealDictCursor
    db = conn # سوينا هذا السطر عشان الكود تحت ما يتلخبط بين conn و db
except Exception as e:
    print(f"❌ Database Connection Error: {e}")

# دالة مساعدة للحصول على cursor يعمل بنظام القواميس
def get_cursor():
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
# -------------------- التحديث التلقائي عند التشغيل --------------------
with app.app_context():
    try:
        print("🔄 System Initializing: Updating Inflation & AI Model...")
        scrape_data()
        retrain()
        print("✅ System Ready!")
    except Exception as e:
        print(f"⚠️ Initialization Warning: {e}")

# -------------------- ML PREDICTION LOGIC --------------------
def predict_logic(data_dict):
    try:
        with open('model.pkl', 'rb') as f:
            model = pickle.load(f)
        with open('encoders.pkl', 'rb') as f:
            encoders = pickle.load(f)

        prop_type = data_dict.get('property_type', '')
        if prop_type == 'Apartments':
            prop_type = 'Apartment'

        def safe_encode(encoder, value):
            return encoder.transform([value])[0] if value in encoder.classes_ else -1

        property_type_enc = safe_encode(encoders['property_type'], prop_type)
        governorate_enc = safe_encode(encoders['governorate'], data_dict.get('governorate', ''))
        wilayat_enc = safe_encode(encoders['wilayat'], data_dict.get('wilayat', ''))

        def clean_val(val):
            try:
                found = re.findall(r'\d+', str(val))
                return float(found[0]) if found else 0.0
            except:
                return 0.0

        X_input = pd.DataFrame([[
            property_type_enc,
            float(data_dict.get('area', 0)),
            int(data_dict.get('bedrooms', 0)),
            float(data_dict.get('bathrooms', 0)),
            governorate_enc,
            wilayat_enc,
            clean_val(data_dict.get('floor', 0)),
            clean_val(data_dict.get('building_age', 0))
        ]], columns=[
            'property_type', 'area', 'bedrooms', 'bathrooms',
            'governorate', 'wilayat', 'floor', 'building_age'
        ])

        prediction = model.predict(X_input)[0]
        return float(prediction)

    except Exception as e:
        print(f"❌ Prediction Error: {e}")
        raise e

# -------------------- PAGES --------------------
@app.route('/')
def homepage():
    return render_template('homepage.html')

@app.route('/predictions')
def predictions():
    return render_template('predictions.html')

@app.route('/exploring')
def exploring():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        cur = cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        cur.execute("SELECT username, profile_image FROM user_info WHERE id = %s", (session['user_id'],))
        user_data = cur.fetchone()

        query = """
    SELECT id, title, governorate, wilayat, price, 
           surface_area AS area, bedrooms, bathrooms, 
           property_type, furnishing, images AS image_url,
           phone  -- أضفنا هذا السطر هنا
    FROM properties 
    WHERE status IN ('Approved', 'Available', 'Pending')
    ORDER BY created_at DESC
"""
        cur.execute(query)
        properties_list = cur.fetchall()
        
        cur.close()
        
        name = user_data['username'] if user_data else "User"
        pic = user_data['profile_image'] if user_data else "default.png"

        return render_template('exploring.html', 
                               properties=properties_list, 
                               username=name, 
                               profile_image=pic)
        
    except Exception as e:
        print(f"❌ Database Error: {str(e)}")
        return f"Database Error: {str(e)}", 500

@app.route('/favorite')
def favorite():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    cur = cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # التعديل هنا: جلب كافة التفاصيل لعرضها في البطاقة
    query = """
    SELECT p.id, p.title, p.governorate, p.wilayat, p.price, 
           p.surface_area AS area, p.bedrooms, p.bathrooms, 
           p.property_type, p.furnishing, p.images AS image_url 
    FROM properties p
    JOIN favorites f ON p.id = f.property_id
    WHERE f.user_id = %s
    """
    cur.execute(query, (user_id,))
    favorite_properties = cur.fetchall()

    cur.execute("SELECT username, profile_image FROM user_info WHERE id=%s", (user_id,))
    user_data = cur.fetchone()
    
    profile_image = user_data['profile_image'] if user_data and user_data['profile_image'] else 'default.png'
    username = user_data['username'] if user_data else session.get('name')
    
    cur.close()

    return render_template('favorite.html', 
                           favorite_properties=favorite_properties,
                           username=username,
                           profile_image=profile_image)

@app.route('/property_details/<int:property_id>')
def property_details(property_id):
    cur = cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM properties WHERE id = %s", (property_id,))
    property_data = cur.fetchone()
    cur.close()
    
    if property_data:
        return render_template('property_details.html', property=property_data)
    else:
        return "Property not found", 404

@app.route('/add_to_favorite/<int:property_id>', methods=['POST'])
def add_to_favorite(property_id):
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Please login first"}), 401

    user_id = session['user_id']
    cur = cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM favorites WHERE user_id = %s AND property_id = %s", (user_id, property_id))
        if cur.fetchone():
            return jsonify({"status": "info", "message": "Property is already in your favorites!"})

        cur.execute("INSERT INTO favorites (user_id, property_id) VALUES (%s, %s)", (user_id, property_id))
        db.commit()
        return jsonify({"status": "success", "message": "Added to favorites! ❤️"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        cur.close()

# -------------------- REGISTER --------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        user_type = request.form['user_type']

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        cursor.execute("""
            INSERT INTO users (name, email, password, user_type)
            VALUES (%s,%s,%s,%s)
        """, (name, email, hashed_password, user_type))
        db.commit()

        return redirect(url_for('login'))

    return render_template('register.html')

# -------------------- SIGNUP --------------------
@app.route('/signup')
def signup():
    return render_template('signup.html')

# -------------------- LOGIN --------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()

        if user and bcrypt.check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_type'] = user['user_type']
            session['name'] = user['name']

            if user['user_type'] == 'seller':
                return redirect(url_for('seller_dashboard'))
            elif user['user_type'] == 'buyer':
                return redirect(url_for('buyer_dashboard'))
            elif user['user_type'] == 'admin':
                return redirect(url_for('admin_dashboard'))

        return "Email or Password incorrect"

    return render_template('login.html')

# -------------------- ADMIN DASHBOARD --------------------
@app.route('/admin')
def admin_dashboard():
    if 'user_id' not in session or session['user_type'] != 'admin':
        return redirect(url_for('login'))

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    cursor.execute("SELECT * FROM properties")
    properties = cursor.fetchall()

    cursor.execute("SELECT COUNT(*) AS total FROM users")
    total_users = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM properties")
    total_properties = cursor.fetchone()['total']

    return render_template(
        "admin_dashboard.html",
        users=users,
        properties=properties,
        total_users=total_users,
        total_properties=total_properties,
        username=session.get('name')
    )

# -------------------- DELETE USER (ADMIN) --------------------
@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if session.get('user_type') != 'admin':
        return redirect(url_for('login'))

    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
    db.commit()
    return redirect(url_for('admin_dashboard'))

# -------------------- DELETE PROPERTY (ADMIN) --------------------
@app.route('/delete_property_admin/<int:property_id>', methods=['POST'])
def delete_property_admin(property_id):
    try:
        cursor.execute("DELETE FROM favorites WHERE property_id = %s", (property_id,))
        cursor.execute("DELETE FROM properties WHERE id = %s", (property_id,))
        db.commit()
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        db.rollback()
        return f"حدث خطأ: {e}"

# -------------------- APPROVE PROPERTY (ADMIN) --------------------
@app.route('/approve_property/<int:property_id>', methods=['POST'])
def approve_property(property_id):
    if session.get('user_type') != 'admin':
        return redirect(url_for('login'))

    cursor.execute("UPDATE properties SET status='Approved' WHERE id=%s", (property_id,))
    db.commit()
    return redirect(url_for('admin_dashboard'))

# -------------------- REJECT PROPERTY (ADMIN) --------------------
@app.route('/reject_property/<int:property_id>', methods=['POST'])
def reject_property(property_id):
    if session.get('user_type') != 'admin':
        return redirect(url_for('login'))

    cursor.execute("UPDATE properties SET status='Rejected' WHERE id=%s", (property_id,))
    db.commit()
    return redirect(url_for('admin_dashboard'))


# -------------------- BUYER DASHBOARD --------------------
@app.route('/buyer_dashboard')
def buyer_dashboard():
    # التأكد من تسجيل الدخول ونوع المستخدم
    if 'user_id' not in session or session.get('user_type') != 'buyer':
        return redirect(url_for('login'))

    buyer_id = session['user_id']
    # ملاحظة: تأكد من تعريف الـ cursor داخل الدالة إذا كنت تستخدم flask-mysqldb
    # cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # 1. جلب بيانات المستخدم (الاسم والصورة)
    cursor.execute("SELECT username, profile_image FROM user_info WHERE id=%s", (buyer_id,))
    user_data = cursor.fetchone()
    
    profile_image = user_data['profile_image'] if user_data and user_data['profile_image'] else 'default.png'
    username = user_data['username'] if user_data else session.get('name')

    # 2. حساب عدد العقارات المتاحة فقط (COUNT بدلاً من جلب البيانات كاملة)
    cursor.execute("SELECT COUNT(*) AS total FROM properties WHERE status IN ('Approved', 'Available')")
    available_count = cursor.fetchone()['total']

    # 3. حساب عدد المفضلات لهذا المستخدم فقط
    cursor.execute("SELECT COUNT(*) AS total FROM favorites WHERE user_id = %s", (buyer_id,))
    favorite_count = cursor.fetchone()['total']

    # إرسال البيانات الضرورية فقط للـ HTML
    return render_template(
        'buyer_home.html', # تأكد أن اسم الملف مطابق لما لديك (سواء home أو dashboard)
        username=username,
        profile_image=profile_image,
        available_count=available_count,
        favorite_count=favorite_count
    )

# -------------------- REMOVE FAVORITE (BUYER) --------------------
@app.route('/remove_favorite/<int:property_id>', methods=['POST'])
def remove_favorite(property_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    buyer_id = session['user_id']
    try:
        cursor.execute("DELETE FROM favorites WHERE user_id=%s AND property_id=%s", (buyer_id, property_id))
        db.commit()
    except Exception as e:
        print(f"Error removing favorite: {e}")
        
    # التحويل لصفحة المفضلة بدلاً من الداشبورد لتجربة مستخدم أفضل
    return redirect(url_for('favorite'))


# -------------------- SELLER DASHBOARD & MY LISTINGS --------------------
@app.route('/seller')
def seller_dashboard():
    if 'user_id' not in session or session.get('user_type') != 'seller':
        return redirect(url_for('login'))

    seller_id = session['user_id']

    # 1. جلب صورة البروفايل واسم المستخدم
    cursor.execute("SELECT username, profile_image FROM user_info WHERE id=%s", (seller_id,))
    user_data = cursor.fetchone()
    profile_image = user_data['profile_image'] if user_data and user_data['profile_image'] else 'default.png'
    username = user_data['username'] if user_data else session.get('name')

    # 2. حساب إجمالي العقارات التي أضافها هذا البائع
    cursor.execute("SELECT COUNT(*) AS total FROM properties WHERE seller_id=%s", (seller_id,))
    total_properties = cursor.fetchone()['total']

    # 3. حساب إجمالي الـ Favorites (كم شخص حط لايك لعقارات هذا البائع)
    cursor.execute("""
        SELECT COUNT(f.id) AS total_favs 
        FROM favorites f
        JOIN properties p ON f.property_id = p.id
        WHERE p.seller_id = %s
    """, (seller_id,))
    total_favorites = cursor.fetchone()['total_favs']

    

    # 5. جلب قائمة العقارات (إذا كنت لا تزال تريد عرضها في مكان ما، وإلا يمكن حذفها)
    cursor.execute("SELECT * FROM properties WHERE seller_id=%s", (seller_id,))
    properties = cursor.fetchall()

    return render_template(
        "seller_dashboard.html",
        username=username,
        total_properties=total_properties,
        total_favorites=total_favorites,
        profile_image=profile_image,
        properties=properties
    )

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/my_listings')
def my_listings():
    if 'user_id' not in session or session['user_type'] != 'seller':
        return redirect(url_for('login'))

    seller_id = session['user_id']
    
    try:
        cur = cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        query_properties = "SELECT * FROM properties WHERE seller_id=%s"
        cur.execute(query_properties, (seller_id,))
        properties = cur.fetchall()

        query_user = "SELECT profile_image FROM user_info WHERE id=%s"
        cur.execute(query_user, (seller_id,))
        img = cur.fetchone()
        
        cur.close()

        profile_image = img['profile_image'] if img and img['profile_image'] else 'default.png'

        return render_template(
            'seller_my_listings.html',
            properties=properties,
            username=session.get('name'),
            profile_image=profile_image
        )

    except Exception as e:
        print(f"Error: {e}")
        return "حدث خطأ أثناء جلب البيانات من قاعدة البيانات."

# -------------------- ADD PROPERTY (SELLER) --------------------
@app.route('/add_property', methods=['GET', 'POST'])
def add_property():
    if 'user_id' not in session or session['user_type'] != 'seller':
        return redirect(url_for('login'))

    seller_id = session['user_id']
    if request.method == 'POST':
        title = request.form.get('title')
        governorate = request.form.get('governorate')
        wilayat = request.form.get('wilayat')
        property_type = request.form.get('property_type')
        area_val = request.form.get('surface_area') 
        bedrooms = request.form.get('bedrooms')
        bathrooms = request.form.get('bathrooms')
        floor = request.form.get('floor')
        building_age = request.form.get('building_age')
        furnishing = request.form.get('furnishing')
        phone = request.form.get('phone')
        price = request.form.get('price')

        file = request.files.get('images') 
        filename = None
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        try:
            cursor.execute("""
                INSERT INTO properties 
                (seller_id, title, governorate, wilayat, property_type, surface_area, bedrooms, bathrooms, floor, building_age, furnishing, price, status, phone, images)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Pending', %s, %s)
            """, (seller_id, title, governorate, wilayat, property_type, area_val, bedrooms, bathrooms, floor, building_age, furnishing, price, phone, filename))
            db.commit()
            return redirect(url_for('my_listings'))
        except Exception as e:
            return f"Error: {e}"

    cursor.execute("SELECT profile_image FROM user_info WHERE id=%s", (seller_id,))
    img = cursor.fetchone()
    profile_image = img['profile_image'] if img and img['profile_image'] else 'default.png'
    return render_template('seller_add_property.html', username=session.get('name'), profile_image=profile_image)

@app.route('/edit_property/<int:property_id>', methods=['GET', 'POST'])
def edit_property(property_id):
    if 'user_id' not in session or session['user_type'] != 'seller':
        return redirect(url_for('login'))

    seller_id = session['user_id']
    cursor.execute("SELECT * FROM properties WHERE id=%s AND seller_id=%s", (property_id, seller_id))
    property_data = cursor.fetchone()
    
    if not property_data:
        return "Property not found", 404

    if request.method == 'POST':
        area_val = request.form.get('surface_area') or property_data['surface_area']
        
        image_file = request.files.get('images')
        if image_file and image_file.filename != '':
            filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            new_image_name = filename
        else:
            new_image_name = property_data['images']

        try:
            cursor.execute("""
                UPDATE properties SET 
                title=%s, governorate=%s, wilayat=%s, property_type=%s, surface_area=%s, 
                bedrooms=%s, bathrooms=%s, floor=%s, building_age=%s, furnishing=%s, 
                price=%s, images=%s
                WHERE id=%s AND seller_id=%s
            """, (
                request.form.get('title'), 
                request.form.get('governorate'), 
                request.form.get('wilayat'), 
                request.form.get('property_type'), 
                area_val, 
                request.form.get('bedrooms'), 
                request.form.get('bathrooms'), 
                request.form.get('floor'), 
                request.form.get('building_age'), 
                request.form.get('furnishing'), 
                request.form.get('price'),
                new_image_name,
                property_id, 
                seller_id
            ))
            db.commit()
            return redirect(url_for('my_listings'))
        except Exception as e:
            return f"Error: {e}"

    return render_template('seller_edit_property.html', property=property_data)

# -------------------- DELETE PROPERTY (SELLER) --------------------
@app.route('/delete_property/<int:property_id>', methods=['POST'])
def delete_property(property_id):
    if 'user_id' not in session or session['user_type'] != 'seller':
        return redirect(url_for('login'))

    seller_id = session['user_id']
    cursor.execute("DELETE FROM favorites WHERE property_id=%s", (property_id,))
    cursor.execute("DELETE FROM properties WHERE id=%s AND seller_id=%s", (property_id, seller_id))
    db.commit()
    return redirect(url_for('my_listings'))


# -------------------- PROFILE & EDIT PROFILE --------------------
@app.route('/profile')
def profile():
    if 'user_id' not in session or session.get('user_type') != 'seller':
        return redirect(url_for('login'))

    user_id = session['user_id']
    cursor.execute("SELECT * FROM user_info WHERE id=%s", (user_id,))
    user_data = cursor.fetchone()

    if not user_data:
        return redirect(url_for('edit_profile'))
        
    return render_template('profile.html', 
                            username=user_data['username'], 
                            email=user_data['email'], 
                            phone=user_data.get('phone', 'N/A'), 
                            profile_image=user_data.get('profile_image', 'default.png'))

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session or session.get('user_type') != 'seller':
        return redirect(url_for('login'))

    user_id = session['user_id']

    if request.method == 'POST':
        new_name = request.form.get('username')
        new_email = request.form.get('email')
        new_phone = request.form.get('phone')
        file = request.files.get('profile_image')
        
        cursor.execute("SELECT profile_image FROM user_info WHERE id=%s", (user_id,))
        old_data = cursor.fetchone()
        image_name = old_data['profile_image'] if old_data and old_data['profile_image'] else 'default.png'

        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join('static/images/profiles', filename))
            image_name = filename

        cursor.execute("SELECT id FROM user_info WHERE id=%s", (user_id,))
        if cursor.fetchone():
            cursor.execute("""
                UPDATE user_info 
                SET username=%s, email=%s, phone=%s, profile_image=%s 
                WHERE id=%s
            """, (new_name, new_email, new_phone, image_name, user_id))
        else:
            cursor.execute("""
                INSERT INTO user_info (id, username, email, phone, profile_image) 
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, new_name, new_email, new_phone, image_name))
        
        db.commit()

        session['name'] = new_name
        session['profile_image'] = image_name
        
        return redirect(url_for('profile'))

    cursor.execute("SELECT * FROM user_info WHERE id=%s", (user_id,))
    user_data = cursor.fetchone() or {'username': '', 'email': '', 'phone': '', 'profile_image': 'default.png'}
    
    return render_template('edit_profile.html', user=user_data)

@app.route('/buyer_profile')
def buyer_profile():
    if 'user_id' not in session or session.get('user_type') != 'buyer':
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    cursor.execute("SELECT * FROM user_info WHERE id=%s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        return redirect(url_for('buyer_edit_profile'))
        
    return render_template('buyer_profile.html', 
                            username=user['username'], 
                            email=user['email'], 
                            phone=user['phone'], 
                            profile_image=user['profile_image'])

@app.route('/buyer_edit_profile', methods=['GET', 'POST'])
def buyer_edit_profile():
    if 'user_id' not in session or session.get('user_type') != 'buyer':
        return redirect(url_for('login'))

    user_id = session['user_id']
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        phone = request.form.get('phone')
        file = request.files.get('profile_image')
        
        cursor.execute("SELECT profile_image FROM user_info WHERE id=%s", (user_id,))
        old_img = cursor.fetchone()
        image_name = old_img['profile_image'] if old_img else 'default.png'

        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join('static/images/profiles', filename))
            image_name = filename

        cursor.execute("SELECT id FROM user_info WHERE id=%s", (user_id,))
        if cursor.fetchone():
            cursor.execute("UPDATE user_info SET username=%s, email=%s, phone=%s, profile_image=%s WHERE id=%s",
                           (username, email, phone, image_name, user_id))
        else:
            cursor.execute("INSERT INTO user_info (id, username, email, phone, profile_image) VALUES (%s,%s,%s,%s,%s)",
                           (user_id, username, email, phone, image_name))
        
        db.commit()

        session['profile_image'] = image_name 
        session['name'] = username
        
        return redirect(url_for('buyer_profile'))

    cursor.execute("SELECT * FROM user_info WHERE id=%s", (user_id,))
    user = cursor.fetchone() or {'username': '', 'email': '', 'phone': ''}
    return render_template('buyer_edit_profile.html', user=user)

# -------------------- PREDICT API --------------------
@app.route('/predict', methods=['POST'])
def make_prediction():
    try:
        data_for_model = {
            'governorate': request.form.get("governorate"),
            'wilayat': request.form.get("wilayat"),
            'property_type': request.form.get("property_type"),
            'area': float(request.form.get("area") or 0),
            'bedrooms': int(request.form.get("bedrooms") or 0),
            'bathrooms': float(request.form.get("bathrooms") or 0),
            'floor': int(request.form.get("floor") or 0),
            'building_age': request.form.get("building_age")
        }

        price = predict_logic(data_for_model)

        cursor.execute("""
            INSERT INTO market_data
            (governorate, wilayat, property_type, area, bedrooms, bathrooms, floor, building_age, price)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            data_for_model['governorate'],
            data_for_model['wilayat'],
            data_for_model['property_type'],
            data_for_model['area'],
            data_for_model['bedrooms'],
            data_for_model['bathrooms'],
            data_for_model['floor'],
            data_for_model['building_age'],
            price
        ))

        db.commit()

        return jsonify({"predicted_price": round(float(price), 2)})

    except Exception as e:
        return jsonify({"error": str(e)})


# -------------------- LOGOUT --------------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('homepage'))


# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True)
