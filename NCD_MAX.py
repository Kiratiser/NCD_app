import json
import os
import re
import math
import pandas as pd
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
import io
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt


# ==============================================================================
# 1. การตั้งค่า Application และ Database
# ==============================================================================
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'default_fallback_key')
DATABASE_URL = os.environ.get('DATABASE_URL')
# Tip: Render ให้ URL มาเป็น postgres:// แต่ SQLAlchemy ต้องการ postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'connect_args': {'connect_timeout': 60}}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # ถ้ายังไม่ login จะถูกส่งไปหน้านี้
login_manager.login_message_category = 'info'

# ==============================================================================
# 2. การสร้างโมเดลฐานข้อมูล (Database Models)
# ==============================================================================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    order_method = db.Column(db.String(50))
    order_total = db.Column(db.Float, default=0.0)
    date = db.Column(db.Date, nullable=False)
    items = db.relationship('OrderItem', backref='customer', cascade="all, delete-orphan")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_string = db.Column(db.String(200), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)

class MenuCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    items = db.relationship('MenuItem', backref='category', cascade="all, delete-orphan")

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('menu_category.id'), nullable=False)

# ==============================================================================
# 3. ส่วนค่าคงที่และฟังก์ชันผู้ช่วย
# ==============================================================================
ORDER_METHODS = ['Dine-in', 'Grab', 'Shopee Food', 'Line Man']
ITEM_TYPES = ["Hot", "Iced", "Frappe", "Other"]
SWEETNESS_LEVELS = ["100%", "75%", "50% (Normal)", "25%", "0% (No Sugar)"]
PER_PAGE = 10 
dashboard_cache = {}
CATEGORY_ORDER = ["Coffee", "Tea", "Fruit Frappe", "Smoothies", "Rice", "Other"]

TAG_STYLES = {
    "Hot": "tag-hot", "Iced": "tag-iced", "Frappe": "tag-frappe",
    "100%": "tag-s100", "75%": "tag-s75", "50% (Normal)": "tag-s50",
    "25%": "tag-s25", "0% (No Sugar)": "tag-s0",
    "Dine-in": "tag-dinein", "Grab": "tag-grab", 
    "Shopee Food": "tag-shopee", "Line Man": "tag-lineman"
}
TAG_PATTERN = re.compile('|'.join(re.escape(k) for k in TAG_STYLES.keys()))

def process_item_tags(item_string):
    match = re.match(r'^(.*?)\s*\((.*)\)$', item_string)
    if match:
        main_item, details_str = match.groups()
        details_str = details_str.replace(',', ' ')
        formatted_string = f"{main_item} {details_str}"
    else:
        formatted_string = item_string
    def replacer(match):
        keyword = match.group(0)
        css_class = TAG_STYLES.get(keyword, "")
        return f'<span class="item-tag {css_class}">{keyword}</span>'
    return TAG_PATTERN.sub(replacer, formatted_string)

def get_dashboard_data(all_customers_objects, selected_month, selected_method):
    if not all_customers_objects:
        return {"summary": {'total_revenue': 0, 'total_orders': 0, 'average_sale': 0}, "sales_chart": {'labels': [], 'data': []}, "orders_chart": {'labels': [], 'data': []}}
    all_customers_dicts = [c.__dict__ for c in all_customers_objects]
    df = pd.DataFrame(all_customers_dicts); df['date'] = pd.to_datetime(df['date'])
    df_filtered = df
    if selected_month: df_filtered = df_filtered[df_filtered['date'].dt.strftime('%Y-%m') == selected_month]
    if selected_method: df_filtered = df_filtered[df_filtered['order_method'] == selected_method]
    if not df_filtered.empty:
        total_revenue = df_filtered['order_total'].sum(); total_orders = len(df_filtered); average_sale = df_filtered['order_total'].mean() if total_orders > 0 else 0
        summary_data = {'total_revenue': total_revenue, 'total_orders': total_orders, 'average_sale': average_sale}
        sales_over_time = df_filtered.groupby(df_filtered['date'].dt.date)['order_total'].sum().sort_index()
        sales_chart_data = {'labels': [d.strftime('%d/%m') for d in sales_over_time.index], 'data': [float(v) for v in sales_over_time.values]}
        orders_over_time = df_filtered.groupby(df_filtered['date'].dt.date).size().sort_index()
        orders_chart_data = {'labels': [d.strftime('%d/%m') for d in orders_over_time.index], 'data': [int(v) for v in orders_over_time.values]}
    else:
        summary_data = {'total_revenue': 0, 'total_orders': 0, 'average_sale': 0}; sales_chart_data = {'labels': [], 'data': []}; orders_chart_data = {'labels': [], 'data': []}
    return {"summary": summary_data, "sales_chart": sales_chart_data, "orders_chart": orders_chart_data}

def prepare_comparison_chart_data(data_a, data_b, month_a, month_b):
    try:
        days_in_month_a = pd.Period(month_a).days_in_month; days_in_month_b = pd.Period(month_b).days_in_month
    except (ValueError, TypeError):
        days_in_month_a = 31; days_in_month_b = 31
    max_days = max(days_in_month_a, days_in_month_b); labels = list(range(1, max_days + 1))
    sales_a = [0] * max_days; sales_b = [0] * max_days
    for label, data in zip(data_a['sales_chart']['labels'], data_a['sales_chart']['data']):
        day_index = int(label.split('/')[0]) - 1
        if 0 <= day_index < max_days: sales_a[day_index] = data
    for label, data in zip(data_b['sales_chart']['labels'], data_b['sales_chart']['data']):
        day_index = int(label.split('/')[0]) - 1
        if 0 <= day_index < max_days: sales_b[day_index] = data
    return {'labels': labels, 'data_a': sales_a, 'data_b': sales_b}

# ==============================================================================
# 4. ส่วนของ Flask Routes
# ==============================================================================
@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('home'))
        else:
            flash('Login failed. Check username and password.', 'danger')
    return render_template('login.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))
        
@app.route("/register", methods=['GET', 'POST'])
@login_required
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists.', 'danger')
            return redirect(url_for('register'))
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route("/")
@login_required
def home():
    return render_template("home.html")

@app.route("/customers")
@login_required
def customers_list():
    page = request.args.get('page', 1, type=int)
    name_query = request.args.get('name_query', '').strip()
    phone_query = request.args.get('phone_query', '').strip()
    start_date_query = request.args.get('start_date_query', '').strip()
    end_date_query = request.args.get('end_date_query', '').strip()
    method_query = request.args.get('method_query', '').strip()
    
    query = Customer.query.order_by(Customer.date.desc(), Customer.id.desc())
    search_active = any([name_query, phone_query, start_date_query, end_date_query, method_query])

    if search_active:
        if name_query: query = query.filter(Customer.name.ilike(f'%{name_query}%'))
        if phone_query: query = query.filter(Customer.phone == phone_query)
        if method_query: query = query.filter(Customer.order_method == method_query)
        if start_date_query:
            try:
                start_date = datetime.strptime(start_date_query, '%Y-%m-%d').date()
                query = query.filter(Customer.date >= start_date)
            except ValueError: pass
        if end_date_query:
            try:
                end_date = datetime.strptime(end_date_query, '%Y-%m-%d').date()
                query = query.filter(Customer.date <= end_date)
            except ValueError: pass
    else:
        query = Customer.query.filter_by(id=None)

    all_results_for_summary = query.all()
    total_sales = sum(c.order_total for c in all_results_for_summary)
    record_count = len(all_results_for_summary)
    
    pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)
    
    customers_processed = []
    all_customers_for_index = Customer.query.all() # ใช้สำหรับหา index เท่านั้น

    print("\n--- DEBUG: Processing Items for Display ---")
    for customer in pagination.items:
        customer.processed_method = process_item_tags(customer.order_method)
        
        # ส่วนประมวลผลรายการสินค้า
        customer.processed_items = []
        print(f"Processing customer: {customer.name}")
        for item in customer.items:
            original_string = item.item_string
            processed_string = process_item_tags(original_string)
            print(f"  Original: '{original_string}'  =>  Processed: '{processed_string}'")
            customer.processed_items.append(processed_string)

        # หา original index
        customer.original_index = next((i for i, original_c in enumerate(all_customers_for_index) if original_c.id == customer.id), -1)
        
        customers_processed.append(customer)
    print("-----------------------------------------\n")
        
    return render_template(
        "customers.html", customers=customers_processed, pagination=pagination,
        search_active=search_active, total_sales=total_sales, record_count=record_count,
        order_methods=ORDER_METHODS, name_query=name_query, phone_query=phone_query,
        start_date_query=start_date_query, end_date_query=end_date_query, method_query=method_query
    )

@app.route("/add", methods=['GET', 'POST'])
@login_required
def add_order():
    if request.method == 'POST':
        order_date_str = request.form.get('order_date')
        order_date = datetime.strptime(order_date_str, '%Y-%m-%d').date() if order_date_str else datetime.utcnow().date()
        new_customer = Customer(name=request.form.get('name'), phone=request.form.get('phone', ''), order_method=request.form.get('order_method'), order_total=request.form.get('order_total', 0, type=float), date=order_date)
        ordered_items_str = request.form.get('ordered_items_hidden', '')
        ordered_items = [item.strip() for item in ordered_items_str.split('|||') if item.strip()]
        for item_str in ordered_items:
            order_item = OrderItem(item_string=item_str)
            new_customer.items.append(order_item)
        db.session.add(new_customer); db.session.commit()
        dashboard_cache.clear(); flash(f"Order for '{new_customer.name}' saved successfully!", 'success'); return redirect(url_for('add_order'))
    else: 
        all_categories = MenuCategory.query.all()
        all_categories.sort(key=lambda cat: CATEGORY_ORDER.index(cat.name) if cat.name in CATEGORY_ORDER else len(CATEGORY_ORDER))
        menu_config = {cat.name: sorted([item.name for item in cat.items]) for cat in all_categories}
        return render_template(
            "add_order.html", order_methods=ORDER_METHODS, menu_config=menu_config,
            item_types=ITEM_TYPES, sweetness_levels=SWEETNESS_LEVELS, today_date=datetime.now().strftime('%Y-%m-%d')
        )

@app.route("/manage-menu", methods=['GET', 'POST'])
@login_required
def manage_menu():
    if request.method == 'POST':
        category_id = request.form.get('category')
        new_item_name = request.form.get('new_item', '').strip()
        if category_id and new_item_name:
            category = MenuCategory.query.get(category_id)
            exists = MenuItem.query.filter_by(name=new_item_name, category_id=category.id).first()
            if not exists:
                new_item = MenuItem(name=new_item_name, category=category)
                db.session.add(new_item); db.session.commit()
        return redirect(url_for('manage_menu'))
    all_categories = MenuCategory.query.all()
    all_categories.sort(key=lambda cat: CATEGORY_ORDER.index(cat.name) if cat.name in CATEGORY_ORDER else len(CATEGORY_ORDER))
    return render_template('manage_menu.html', categories=all_categories)

@app.route("/delete-item", methods=['POST'])
@login_required
def delete_item():
    item_id = request.form.get('item_id')
    item = MenuItem.query.get(item_id)
    if item:
        db.session.delete(item); db.session.commit()
    return redirect(url_for('manage_menu'))

@app.route("/edit-item/<int:item_id>", methods=['GET', 'POST'])
@login_required
def edit_item(item_id):
    item = MenuItem.query.get_or_404(item_id)
    if request.method == 'POST':
        new_name = request.form.get('new_item_name', '').strip()
        if new_name:
            item.name = new_name
            db.session.commit()
        return redirect(url_for('manage_menu'))
    return render_template('edit_item.html', item=item)

@app.route('/delete-customer/<int:customer_id>', methods=['POST'])
@login_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    dashboard_cache.clear()
    flash(f"Record for {customer.name} has been deleted.", 'success')
    redirect_args = {k: v for k, v in request.form.items() if k != 'customer_id'}
    return redirect(url_for('customers_list', **redirect_args))

@app.route("/dashboard")
@login_required
def dashboard():
    current_month_str = datetime.now().strftime('%Y-%m')
    selected_month = request.args.get('month', current_month_str)
    selected_method = request.args.get('method', '')
    cache_key = f"{selected_month}-{selected_method}"
    if cache_key in dashboard_cache:
        return render_template("dashboard.html", **dashboard_cache[cache_key])
    all_customers = Customer.query.all()
    data = get_dashboard_data(all_customers, selected_month, selected_method)
    template_data = {"summary": {'total_revenue': f"{data['summary']['total_revenue']:,.2f}", 'total_orders': f"{data['summary']['total_orders']:,}", 'average_sale': f"{data['summary']['average_sale']:,.2f}"}, 'sales_chart': data['sales_chart'], 'orders_chart': data['orders_chart'], "selected_month": selected_month, "selected_method": selected_method, "order_methods": ORDER_METHODS}
    dashboard_cache[cache_key] = template_data
    return render_template("dashboard.html", **template_data)

@app.route("/compare")
@login_required
def compare():
    all_customers = Customer.query.all()
    month_a = request.args.get('month_a', ''); method_a = request.args.get('method_a', '')
    month_b = request.args.get('month_b', ''); method_b = request.args.get('method_b', '')
    data_a = None; data_b = None; comparison = {}; combined_chart_data = None
    if month_a and month_b:
        data_a = get_dashboard_data(all_customers, month_a, method_a)
        data_b = get_dashboard_data(all_customers, month_b, method_b)
        summary_a = data_a['summary']; summary_b = data_b['summary']
        revenue_diff = summary_b['total_revenue'] - summary_a['total_revenue']
        orders_diff = summary_b['total_orders'] - summary_a['total_orders']
        revenue_pct = (revenue_diff / summary_a['total_revenue']) * 100 if summary_a['total_revenue'] > 0 else float('inf') if revenue_diff > 0 else 0
        comparison = {'revenue_diff': revenue_diff, 'orders_diff': orders_diff, 'revenue_pct': revenue_pct}
        combined_chart_data = prepare_comparison_chart_data(data_a, data_b, month_a, month_b)
    return render_template(
        "compare.html", data_a=data_a, data_b=data_b, comparison=comparison,
        month_a=month_a, method_a=method_a, month_b=month_b, method_b=method_b,
        order_methods=ORDER_METHODS, combined_chart_data=combined_chart_data
    )

# VVVVVV  โค้ดสำหรับทดสอบ ใส่ไว้ท้ายไฟล์ app.py ได้เลย VVVVVV
@app.route('/test-db')
def test_db():
    try:
        # ลองสั่งคำสั่งง่ายๆ ไปที่ฐานข้อมูล
        # db.session.query(1) คือการ SELECT 1 ซึ่งเป็นวิธีที่เร็วที่สุดในการเช็คการเชื่อมต่อ
        db.session.query(1).first()
        return '<h1>SUCCESS: Database connection is working!</h1>'
    except Exception as e:
        # ถ้ามี Error ให้แสดง Error นั้นออกมาที่หน้าเว็บเลย
        return f'<h1>ERROR: Database connection failed.</h1><p>Error details: {e}</p>'
# ^^^^^^ สิ้นสุดโค้ดสำหรับทดสอบ ^^^^^^

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

