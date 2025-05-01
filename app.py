from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, Response
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect
import sqlite3
import os
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import io
import base64
from io import BytesIO
from fpdf import FPDF
import json
import numpy as np
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Session lasts 7 days
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)

# Database setup
def get_db_connection():
    conn = sqlite3.connect('expense.db')
    conn.row_factory = sqlite3.Row  # This enables column access by name
    return conn

def create_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, 
                username TEXT UNIQUE, 
                password TEXT,
                email TEXT UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    
    # Check if email column exists and add it if not
    c.execute("PRAGMA table_info(users)")
    columns = [col['name'] for col in c.fetchall()]
    if 'email' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT")
    
    # Categories table
    c.execute('''CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY, 
                name TEXT,
                user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    # Expenses table
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY, 
                user_id INTEGER, 
                category_id INTEGER,
                description TEXT,
                amount REAL, 
                date TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(category_id) REFERENCES categories(id))''')
    
    # Budgets table
    c.execute('''CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                category_id INTEGER,
                amount REAL,
                period TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(category_id) REFERENCES categories(id))''')
    
    # Income table
    c.execute('''CREATE TABLE IF NOT EXISTS income (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                source TEXT,
                amount REAL,
                date TEXT,
                FOREIGN KEY(user_id) REFERENCES users(id))''')
    
    conn.commit()
    conn.close()

create_db()

# User model
class User(UserMixin):
    def __init__(self, id, username=None, email=None):
        self.id = id
        self.username = username
        self.email = email

# Load user function
@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user_data = c.fetchone()
    conn.close()
    
    if user_data:
        user_data_dict = dict(user_data)
        return User(user_data_dict['id'], user_data_dict['username'], user_data_dict.get('email'))
    return None
# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id != 1:  # Assuming user with ID 1 is admin
            flash('You need admin privileges to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get date range for filtering
    filter_period = request.args.get('period', 'month')
    today = datetime.today().date()
    
    if filter_period == 'week':
        start_date = (today - timedelta(days=today.weekday())).isoformat()
        date_filter = f"date >= '{start_date}'"
        period_name = "This Week"
    elif filter_period == 'month':
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    elif filter_period == 'year':
        start_date = f"{today.year}-01-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.year}"
    elif filter_period == 'all':
        date_filter = "1=1"  # No filter
        period_name = "All Time"
    else:
        # Default to current month
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    
    # Get expenses with category names
    c.execute(f"""
        SELECT e.id, e.amount, e.date, e.description, c.name as category_name, c.id as category_id
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = ? AND {date_filter}
        ORDER BY e.date DESC
    """, (current_user.id,))
    expenses = c.fetchall()
    
    # Get categories for this user
    c.execute("SELECT * FROM categories WHERE user_id = ? OR user_id IS NULL", (current_user.id,))
    categories = c.fetchall()
    
    # Calculate total expenses for the period
    c.execute(f"""
        SELECT SUM(amount) as total
        FROM expenses
        WHERE user_id = ? AND {date_filter}
    """, (current_user.id,))
    total_expenses = c.fetchone()['total'] or 0
    
    # Get income for the period
    c.execute(f"""
        SELECT SUM(amount) as total
        FROM income
        WHERE user_id = ? AND {date_filter}
    """, (current_user.id,))
    total_income = c.fetchone()['total'] or 0
    
    # Get budget information
    c.execute("""
        SELECT b.id, b.amount, b.period, c.name as category_name, c.id as category_id
        FROM budgets b
        JOIN categories c ON b.category_id = c.id
        WHERE b.user_id = ?
    """, (current_user.id,))
    budgets = c.fetchall()
    
    # Calculate budget usage
    budget_usage = {}
    for budget in budgets:
        if budget['period'] == filter_period or (budget['period'] == 'month' and filter_period == 'month'):
            c.execute(f"""
                SELECT SUM(amount) as spent
                FROM expenses
                WHERE user_id = ? AND category_id = ? AND {date_filter}
            """, (current_user.id, budget['category_id']))
            spent = c.fetchone()['spent'] or 0
            
            budget_usage[budget['category_id']] = {
                'budget': budget['amount'],
                'spent': spent,
                'percentage': min(100, round((spent / budget['amount']) * 100)) if budget['amount'] > 0 else 0
            }
    
    conn.close()
    
    # If no categories exist, redirect to add category page
    if not categories:
        flash('Please add some expense categories first.', 'info')
        return redirect(url_for('add_category'))
    
    return render_template('index.html', 
                          expenses=expenses, 
                          categories=categories, 
                          today=today,
                          period=filter_period,
                          period_name=period_name,
                          total_expenses=total_expenses,
                          total_income=total_income,
                          balance=total_income - total_expenses,
                          budgets=budgets,
                          budget_usage=budget_usage)

@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    category_id = request.form['category_id']
    amount = request.form['amount']
    date = request.form['date']
    description = request.form.get('description', '')
    
    if category_id and amount:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            INSERT INTO expenses (user_id, category_id, amount, date, description) 
            VALUES (?, ?, ?, ?, ?)
        """, (current_user.id, category_id, float(amount), date, description))
        conn.commit()
        conn.close()
        flash('Expense added successfully!', 'success')
    else:
        flash('Please fill in all required fields.', 'danger')
    
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
@login_required
def delete_expense(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Verify the expense belongs to the current user
    c.execute("SELECT user_id FROM expenses WHERE id=?", (id,))
    expense = c.fetchone()
    
    if expense and expense['user_id'] == current_user.id:
        c.execute("DELETE FROM expenses WHERE id=?", (id,))
        conn.commit()
        flash('Expense deleted successfully!', 'success')
    else:
        flash('You do not have permission to delete this expense.', 'danger')
    
    conn.close()
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_expense(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Verify the expense belongs to the current user
    c.execute("SELECT * FROM expenses WHERE id=? AND user_id=?", (id, current_user.id))
    expense_data = c.fetchone()
    
    if not expense_data:
        flash('You do not have permission to edit this expense.', 'danger')
        conn.close()
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        category_id = request.form['category_id']
        amount = request.form['amount']
        date = request.form['date']
        description = request.form.get('description', '')

        c.execute("""
            UPDATE expenses 
            SET category_id=?, amount=?, date=?, description=? 
            WHERE id=? AND user_id=?
        """, (category_id, float(amount), date, description, id, current_user.id))
        conn.commit()
        flash('Expense updated successfully!', 'success')
        conn.close()
        return redirect(url_for('index'))

    # Fetch categories for dropdown selection
    c.execute("SELECT * FROM categories WHERE user_id = ? OR user_id IS NULL", (current_user.id,))
    categories = c.fetchall()

    conn.close()

    return render_template('edit_expense.html', expense=expense_data, categories=categories)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form.get('email', '')
        
        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('register.html')
            
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        try:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, email) VALUES (?, ?, ?)", 
                     (username, hashed_password, email))
            conn.commit()
            
            # Create default categories for new user
            user_id = c.lastrowid
            default_categories = ['Food', 'Transportation', 'Housing', 'Entertainment', 'Utilities', 'Healthcare', 'Other']
            for category in default_categories:
                c.execute("INSERT INTO categories (name, user_id) VALUES (?, ?)", (category, user_id))
            
            conn.commit()
            conn.close()
            
            flash('Account created successfully! You can now log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists!', 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = 'remember' in request.form
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user_data = c.fetchone()
        conn.close()
        
        if user_data and bcrypt.check_password_hash(user_data['password'], password):
            # Convert sqlite3.Row to dict
            user_data_dict = dict(user_data)
            user = User(user_data_dict['id'], user_data_dict['username'], user_data_dict.get('email'))
            login_user(user, remember=remember)
            session['user_id'] = user_data_dict['id']
            session.permanent = remember
            
            # Get the next page from the URL if it exists
            next_page = request.args.get('next')
            
            flash(f'Welcome back, {username}!', 'success')
            return redirect(next_page or url_for('index'))
        else:
            flash('Login failed. Please check your username and password.', 'danger')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('user_id', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/add_category', methods=['GET', 'POST'])
@login_required
def add_category():
    if request.method == 'POST':
        category_name = request.form['category_name']
        
        if category_name:
            conn = get_db_connection()
            c = conn.cursor()
            
            # Check if category already exists for this user
            c.execute("SELECT * FROM categories WHERE name=? AND user_id=?", (category_name, current_user.id))
            if c.fetchone():
                flash('This category already exists.', 'warning')
                conn.close()
                return redirect(url_for('add_category'))
                
            c.execute("INSERT INTO categories (name, user_id) VALUES (?, ?)", (category_name, current_user.id))
            conn.commit()
            conn.close()
            flash('Category added successfully!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Category name cannot be empty.', 'danger')
    
    # Get existing categories
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM categories WHERE user_id=? OR user_id IS NULL", (current_user.id,))
    categories = c.fetchall()
    conn.close()
    
    return render_template('add_category.html', categories=categories)

@app.route('/delete_category/<int:id>')
@login_required
def delete_category(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check if category belongs to user
    c.execute("SELECT * FROM categories WHERE id=? AND user_id=?", (id, current_user.id))
    category = c.fetchone()
    
    if not category:
        flash('You do not have permission to delete this category.', 'danger')
        conn.close()
        return redirect(url_for('add_category'))
    
    # Check if category is in use
    c.execute("SELECT COUNT(*) as count FROM expenses WHERE category_id=?", (id,))
    count = c.fetchone()['count']
    
    if count > 0:
        flash('Cannot delete category that is in use. Please reassign or delete expenses first.', 'danger')
    else:
        c.execute("DELETE FROM categories WHERE id=? AND user_id=?", (id, current_user.id))
        conn.commit()
        flash('Category deleted successfully!', 'success')
    
    conn.close()
    return redirect(url_for('add_category'))

@app.route('/analytics')
@login_required
def analytics():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get date range for filtering
    filter_period = request.args.get('period', 'month')
    today = datetime.today().date()
    
    if filter_period == 'week':
        start_date = (today - timedelta(days=today.weekday())).isoformat()
        date_filter = f"date >= '{start_date}'"
        period_name = "This Week"
    elif filter_period == 'month':
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    elif filter_period == 'year':
        start_date = f"{today.year}-01-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.year}"
    elif filter_period == 'all':
        date_filter = "1=1"  # No filter
        period_name = "All Time"
    else:
        # Default to current month
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    
    # Fetch expenses grouped by category
    c.execute(f"""
        SELECT c.name, SUM(e.amount) as total
        FROM expenses e 
        JOIN categories c ON e.category_id = c.id 
        WHERE e.user_id = ? AND {date_filter}
        GROUP BY c.name
        ORDER BY total DESC
    """, (current_user.id,))
    
    category_data = c.fetchall()
    
    # Fetch expenses by day for line chart
    if filter_period in ['week', 'month']:
        c.execute(f"""
            SELECT date, SUM(amount) as total
            FROM expenses
            WHERE user_id = ? AND {date_filter}
            GROUP BY date
            ORDER BY date
        """, (current_user.id,))
        daily_expenses = c.fetchall()
        
        # Fill in missing dates with zero values
        if filter_period == 'week':
            days = 7
        else:  # month
            # Get the number of days in the current month
            if today.month == 12:
                last_day = datetime(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(today.year, today.month + 1, 1) - timedelta(days=1)
            days = last_day.day
            
        date_totals = {row['date']: row['total'] for row in daily_expenses}
        
        daily_data = []
        for i in range(days):
            if filter_period == 'week':
                date = (datetime.strptime(start_date, '%Y-%m-%d') + timedelta(days=i)).strftime('%Y-%m-%d')
            else:
                date = f"{today.year}-{today.month:02d}-{i+1:02d}"
                
            if date <= today.isoformat():  # Only include dates up to today
                daily_data.append({
                    'date': date,
                    'total': date_totals.get(date, 0)
                })
    else:
        daily_data = []
    
    # Get top 5 expenses
    c.execute(f"""
        SELECT e.amount, e.date, e.description, c.name as category
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = ? AND {date_filter}
        ORDER BY e.amount DESC
        LIMIT 5
    """, (current_user.id,))
    top_expenses = c.fetchall()
    
    # Calculate income vs expenses
    c.execute(f"""
        SELECT SUM(amount) as total
        FROM expenses
        WHERE user_id = ? AND {date_filter}
    """, (current_user.id,))
    total_expenses = c.fetchone()['total'] or 0
    
    c.execute(f"""
        SELECT SUM(amount) as total
        FROM income
        WHERE user_id = ? AND {date_filter}
    """, (current_user.id,))
    total_income = c.fetchone()['total'] or 0
    
    conn.close()
    
    # Prepare data for charts
    categories = [row['name'] for row in category_data]
    amounts = [row['total'] for row in category_data]
    
    # Create a pie chart
    if categories and amounts:
        plt.figure(figsize=(8, 6))
        plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=140)
        plt.title(f'Expenses by Category - {period_name}')
        
        # Save it to a BytesIO object
        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        
        # Encode the image to base64
        pie_chart = base64.b64encode(img.getvalue()).decode()
        plt.close()
    else:
        pie_chart = None
    
    # Create a line chart for daily expenses
    if daily_data:
        dates = [item['date'] for item in daily_data]
        daily_amounts = [item['total'] for item in daily_data]
        
        plt.figure(figsize=(10, 5))
        plt.plot(dates, daily_amounts, marker='o')
        plt.title(f'Daily Expenses - {period_name}')
        plt.xlabel('Date')
        plt.ylabel('Amount')
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save it to a BytesIO object
        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        
        # Encode the image to base64
        line_chart = base64.b64encode(img.getvalue()).decode()
        plt.close()
    else:
        line_chart = None
    
    # Create a bar chart for income vs expenses
    plt.figure(figsize=(6, 4))
    plt.bar(['Income', 'Expenses'], [total_income, total_expenses])
    plt.title(f'Income vs Expenses - {period_name}')
    plt.ylabel('Amount')
    
    # Save it to a BytesIO object
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    
    # Encode the image to base64
    bar_chart = base64.b64encode(img.getvalue()).decode()
    plt.close()

    return render_template('analytics.html', 
                          pie_chart=pie_chart,
                          line_chart=line_chart,
                          bar_chart=bar_chart,
                          period=filter_period,
                          period_name=period_name,
                          top_expenses=top_expenses,
                          total_expenses=total_expenses,
                          total_income=total_income,
                          balance=total_income - total_expenses)

@app.route('/budget', methods=['GET', 'POST'])
@login_required
def budget():
    conn = get_db_connection()
    c = conn.cursor()
    
    if request.method == 'POST':
        category_id = request.form['category_id']
        amount = request.form['amount']
        period = request.form['period']
        
        if category_id and amount and period:
            # Check if budget already exists for this category and period
            c.execute("""
                SELECT * FROM budgets 
                WHERE user_id=? AND category_id=? AND period=?
            """, (current_user.id, category_id, period))
            
            existing_budget = c.fetchone()
            
            if existing_budget:
                # Update existing budget
                c.execute("""
                    UPDATE budgets 
                    SET amount=? 
                    WHERE id=?
                """, (float(amount), existing_budget['id']))
                flash('Budget updated successfully!', 'success')
            else:
                # Create new budget
                c.execute("""
                    INSERT INTO budgets (user_id, category_id, amount, period)
                    VALUES (?, ?, ?, ?)
                """, (current_user.id, category_id, float(amount), period))
                flash('Budget created successfully!', 'success')
                
            conn.commit()
    
    # Get categories
    c.execute("SELECT * FROM categories WHERE user_id=? OR user_id IS NULL", (current_user.id,))
    categories = c.fetchall()
    
    # Get existing budgets
    c.execute("""
        SELECT b.id, b.amount, b.period, c.name as category_name, c.id as category_id
        FROM budgets b
        JOIN categories c ON b.category_id = c.id
        WHERE b.user_id = ?
    """, (current_user.id,))
    budgets = c.fetchall()
    
    # Calculate budget usage for current month
    today = datetime.today().date()
    start_date = f"{today.year}-{today.month:02d}-01"
    
    budget_usage = {}
    for budget in budgets:
        if budget['period'] == 'month':
            c.execute(f"""
                SELECT SUM(amount) as spent
                FROM expenses
                WHERE user_id = ? AND category_id = ? AND date >= '{start_date}'
            """, (current_user.id, budget['category_id']))
            spent = c.fetchone()['spent'] or 0
            
            budget_usage[budget['category_id']] = {
                'budget': budget['amount'],
                'spent': spent,
                'percentage': min(100, round((spent / budget['amount']) * 100)) if budget['amount'] > 0 else 0
            }
    
    conn.close()
    
    return render_template('budget.html', 
                          categories=categories, 
                          budgets=budgets,
                          budget_usage=budget_usage)

@app.route('/delete_budget/<int:id>')
@login_required
def delete_budget(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Verify the budget belongs to the current user
    c.execute("SELECT * FROM budgets WHERE id=? AND user_id=?", (id, current_user.id))
    budget = c.fetchone()
    
    if budget:
        c.execute("DELETE FROM budgets WHERE id=?", (id,))
        conn.commit()
        flash('Budget deleted successfully!', 'success')
    else:
        flash('You do not have permission to delete this budget.', 'danger')
    
    conn.close()
    return redirect(url_for('budget'))

@app.route('/income', methods=['GET', 'POST'])
@login_required
def income():
    conn = get_db_connection()
    c = conn.cursor()
    
    if request.method == 'POST':
        source = request.form['source']
        amount = request.form['amount']
        date = request.form['date']
        
        if source and amount and date:
            c.execute("""
                INSERT INTO income (user_id, source, amount, date)
                VALUES (?, ?, ?, ?)
            """, (current_user.id, source, float(amount), date))
            conn.commit()
            flash('Income added successfully!', 'success')
        else:
            flash('Please fill in all required fields.', 'danger')
    
    # Get date range for filtering
    filter_period = request.args.get('period', 'month')
    today = datetime.today().date()
    
    if filter_period == 'week':
        start_date = (today - timedelta(days=today.weekday())).isoformat()
        date_filter = f"date >= '{start_date}'"
        period_name = "This Week"
    elif filter_period == 'month':
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    elif filter_period == 'year':
        start_date = f"{today.year}-01-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.year}"
    elif filter_period == 'all':
        date_filter = "1=1"  # No filter
        period_name = "All Time"
    else:
        # Default to current month
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    
    # Get income entries
    c.execute(f"""
        SELECT * FROM income
        WHERE user_id = ? AND {date_filter}
        ORDER BY date DESC
    """, (current_user.id,))
    income_entries = c.fetchall()
    
    # Calculate total income
    c.execute(f"""
        SELECT SUM(amount) as total
        FROM income
        WHERE user_id = ? AND {date_filter}
    """, (current_user.id,))
    total_income = c.fetchone()['total'] or 0
    
    conn.close()
    
    return render_template('income.html',
                          income_entries=income_entries,
                          total_income=total_income,
                          today=today,
                          period=filter_period,
                          period_name=period_name)

@app.route('/delete_income/<int:id>')
@login_required
def delete_income(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Verify the income entry belongs to the current user
    c.execute("SELECT * FROM income WHERE id=? AND user_id=?", (id, current_user.id))
    income = c.fetchone()
    
    if income:
        c.execute("DELETE FROM income WHERE id=?", (id,))
        conn.commit()
        flash('Income entry deleted successfully!', 'success')
    else:
        flash('You do not have permission to delete this income entry.', 'danger')
    
    conn.close()
    return redirect(url_for('income'))

@app.route('/edit_income/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_income(id):
    conn = get_db_connection()
    c = conn.cursor()
    
    # Verify the income entry belongs to the current user
    c.execute("SELECT * FROM income WHERE id=? AND user_id=?", (id, current_user.id))
    income_data = c.fetchone()
    
    if not income_data:
        flash('You do not have permission to edit this income entry.', 'danger')
        conn.close()
        return redirect(url_for('income'))
    
    if request.method == 'POST':
        source = request.form['source']
        amount = request.form['amount']
        date = request.form['date']

        c.execute("""
            UPDATE income 
            SET source=?, amount=?, date=? 
            WHERE id=? AND user_id=?
        """, (source, float(amount), date, id, current_user.id))
        conn.commit()
        flash('Income entry updated successfully!', 'success')
        conn.close()
        return redirect(url_for('income'))

    conn.close()
    return render_template('edit_income.html', income=income_data)

@app.route('/download_report', methods=['GET'])
@login_required
def download_report():
    report_type = request.args.get('type', 'expenses')
    period = request.args.get('period', 'month')
    
    # Get date range for filtering
    today = datetime.today().date()
    
    if period == 'week':
        start_date = (today - timedelta(days=today.weekday())).isoformat()
        date_filter = f"date >= '{start_date}'"
        period_name = "This Week"
    elif period == 'month':
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    elif period == 'year':
        start_date = f"{today.year}-01-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.year}"
    elif period == 'all':
        date_filter = "1=1"  # No filter
        period_name = "All Time"
    else:
        # Default to current month
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    
    # Connect to database
    conn = get_db_connection()
    c = conn.cursor()
    
    # Initialize PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", style='B', size=16)
    
    if report_type == 'expenses':
        # Fetch expense data
        c.execute(f"""
            SELECT e.id, c.name AS category, e.description, e.amount, e.date 
            FROM expenses e
            JOIN categories c ON e.category_id = c.id
            WHERE e.user_id = ? AND {date_filter}
            ORDER BY e.date DESC
        """, (current_user.id,))
        data = c.fetchall()
        
        # Add title
        pdf.cell(200, 10, txt=f"Expense Report - {period_name}", ln=True, align='C')
        
        # Add summary
        c.execute(f"""
            SELECT SUM(amount) as total
            FROM expenses
            WHERE user_id = ? AND {date_filter}
        """, (current_user.id,))
        total = c.fetchone()['total'] or 0
        
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Total Expenses: ${total:.2f}", ln=True)
        
        # Add category breakdown
        c.execute(f"""
            SELECT c.name, SUM(e.amount) as total
            FROM expenses e 
            JOIN categories c ON e.category_id = c.id 
            WHERE e.user_id = ? AND {date_filter}
            GROUP BY c.name
            ORDER BY total DESC
        """, (current_user.id,))
        categories = c.fetchall()
        
        pdf.ln(5)
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(200, 10, txt="Expenses by Category:", ln=True)
        
        pdf.set_font("Arial", size=12)
        for cat in categories:
            pdf.cell(100, 10, txt=f"{cat['name']}", ln=False)
            pdf.cell(100, 10, txt=f"${cat['total']:.2f}", ln=True)
        
        # Add table header
        pdf.ln(10)
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(10, 10, txt="ID", border=1)
        pdf.cell(40, 10, txt="Date", border=1)
        pdf.cell(40, 10, txt="Category", border=1)
        pdf.cell(70, 10, txt="Description", border=1)
        pdf.cell(30, 10, txt="Amount", border=1, ln=True)
        
        # Add table rows
        pdf.set_font("Arial", size=10)
        for row in data:
            pdf.cell(10, 10, txt=str(row['id']), border=1)
            pdf.cell(40, 10, txt=row['date'], border=1)
            pdf.cell(40, 10, txt=row['category'], border=1)
            
            # Handle long descriptions
            description = row['description'] if row['description'] else ""
            if len(description) > 30:
                description = description[:27] + "..."
            pdf.cell(70, 10, txt=description, border=1)
            
            pdf.cell(30, 10, txt=f"${row['amount']:.2f}", border=1, ln=True)
        
        filename = f"expense_report_{period}_{today.isoformat()}.pdf"
    
    elif report_type == 'income':
        # Fetch income data
        c.execute(f"""
            SELECT id, source, amount, date 
            FROM income
            WHERE user_id = ? AND {date_filter}
            ORDER BY date DESC
        """, (current_user.id,))
        data = c.fetchall()
        
        # Add title
        pdf.cell(200, 10, txt=f"Income Report - {period_name}", ln=True, align='C')
        
        # Add summary
        c.execute(f"""
            SELECT SUM(amount) as total
            FROM income
            WHERE user_id = ? AND {date_filter}
        """, (current_user.id,))
        total = c.fetchone()['total'] or 0
        
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Total Income: ${total:.2f}", ln=True)
        
        # Add source breakdown
        c.execute(f"""
            SELECT source, SUM(amount) as total
            FROM income
            WHERE user_id = ? AND {date_filter}
            GROUP BY source
            ORDER BY total DESC
        """, (current_user.id,))
        sources = c.fetchall()
        
        pdf.ln(5)
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(200, 10, txt="Income by Source:", ln=True)
        
        pdf.set_font("Arial", size=12)
        for src in sources:
            pdf.cell(100, 10, txt=f"{src['source']}", ln=False)
            pdf.cell(100, 10, txt=f"${src['total']:.2f}", ln=True)
        
        # Add table header
        pdf.ln(10)
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(20, 10, txt="ID", border=1)
        pdf.cell(50, 10, txt="Date", border=1)
        pdf.cell(70, 10, txt="Source", border=1)
        pdf.cell(50, 10, txt="Amount", border=1, ln=True)
        
        # Add table rows
        pdf.set_font("Arial", size=10)
        for row in data:
            pdf.cell(20, 10, txt=str(row['id']), border=1)
            pdf.cell(50, 10, txt=row['date'], border=1)
            pdf.cell(70, 10, txt=row['source'], border=1)
            pdf.cell(50, 10, txt=f"${row['amount']:.2f}", border=1, ln=True)
        
        filename = f"income_report_{period}_{today.isoformat()}.pdf"
    
    else:  # summary report
        # Add title
        pdf.cell(200, 10, txt=f"Financial Summary - {period_name}", ln=True, align='C')
        
        # Get expense total
        c.execute(f"""
            SELECT SUM(amount) as total
            FROM expenses
            WHERE user_id = ? AND {date_filter}
        """, (current_user.id,))
        total_expenses = c.fetchone()['total'] or 0
        
        # Get income total
        c.execute(f"""
            SELECT SUM(amount) as total
            FROM income
            WHERE user_id = ? AND {date_filter}
        """, (current_user.id,))
        total_income = c.fetchone()['total'] or 0
        
        # Calculate balance
        balance = total_income - total_expenses
        
        # Add summary
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Total Income: ${total_income:.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Total Expenses: ${total_expenses:.2f}", ln=True)
        pdf.cell(200, 10, txt=f"Balance: ${balance:.2f}", ln=True)
        
        # Add category breakdown
        c.execute(f"""
            SELECT c.name, SUM(e.amount) as total
            FROM expenses e 
            JOIN categories c ON e.category_id = c.id 
            WHERE e.user_id = ? AND {date_filter}
            GROUP BY c.name
            ORDER BY total DESC
        """, (current_user.id,))
        categories = c.fetchall()
        
        pdf.ln(5)
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(200, 10, txt="Expenses by Category:", ln=True)
        
        pdf.set_font("Arial", size=12)
        for cat in categories:
            pdf.cell(100, 10, txt=f"{cat['name']}", ln=False)
            pdf.cell(100, 10, txt=f"${cat['total']:.2f}", ln=True)
        
        # Add income sources
        c.execute(f"""
            SELECT source, SUM(amount) as total
            FROM income
            WHERE user_id = ? AND {date_filter}
            GROUP BY source
            ORDER BY total DESC
        """, (current_user.id,))
        sources = c.fetchall()
        
        pdf.ln(5)
        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(200, 10, txt="Income by Source:", ln=True)
        
        pdf.set_font("Arial", size=12)
        for src in sources:
            pdf.cell(100, 10, txt=f"{src['source']}", ln=False)
            pdf.cell(100, 10, txt=f"${src['total']:.2f}", ln=True)
        
        filename = f"financial_summary_{period}_{today.isoformat()}.pdf"
    
    conn.close()
    
    # Use BytesIO for in-memory PDF storage
    pdf_output = BytesIO()
    pdf_output.write(pdf.output(dest='S').encode('latin1'))
    pdf_output.seek(0)
    
    # Return the PDF as a Flask response
    return Response(
        pdf_output,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

@app.route('/download_chart')
@login_required
def download_chart():
    # Get date range for filtering
    filter_period = request.args.get('period', 'month')
    today = datetime.today().date()
    
    if filter_period == 'week':
        start_date = (today - timedelta(days=today.weekday())).isoformat()
        date_filter = f"date >= '{start_date}'"
        period_name = "This Week"
    elif filter_period == 'month':
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    elif filter_period == 'year':
        start_date = f"{today.year}-01-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.year}"
    elif filter_period == 'all':
        date_filter = "1=1"  # No filter
        period_name = "All Time"
    else:
        # Default to current month
        start_date = f"{today.year}-{today.month:02d}-01"
        date_filter = f"date >= '{start_date}'"
        period_name = f"{today.strftime('%B %Y')}"
    
    # Connect to database
    conn = get_db_connection()
    c = conn.cursor()
    
    # Fetch expenses grouped by category
    c.execute(f"""
        SELECT c.name, SUM(e.amount) as total
        FROM expenses e 
        JOIN categories c ON e.category_id = c.id 
        WHERE e.user_id = ? AND {date_filter}
        GROUP BY c.name
        ORDER BY total DESC
    """, (current_user.id,))
    
    category_data = c.fetchall()
    conn.close()
    
    # Prepare data for the chart
    categories = [row['name'] for row in category_data]
    amounts = [row['total'] for row in category_data]
    
    # Create the pie chart
    if categories and amounts:
        plt.figure(figsize=(8, 6))
        plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=140)
        plt.title(f'Expenses by Category - {period_name}')
        
        # Save chart to a BytesIO object
        img = io.BytesIO()
        plt.savefig(img, format='png')
        img.seek(0)
        plt.close()
        
        # Send the image as a downloadable file
        return send_file(
            img,
            mimetype='image/png',
            as_attachment=True,
            download_name=f'expenses_by_category_{filter_period}_{today.isoformat()}.png'
        )
    
    # If no data, flash a message and redirect
    flash('No expense data available to generate the chart.', 'warning')
    return redirect(url_for('analytics', period=filter_period))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get user data
    c.execute("SELECT * FROM users WHERE id=?", (current_user.id,))
    user_data = c.fetchone()
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        
        # Update username and email
        if username and username != user_data['username']:
            try:
                c.execute("UPDATE users SET username=? WHERE id=?", (username, current_user.id))
                flash('Username updated successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('Username already exists!', 'danger')
        
        if email and email != (user_data['email'] or ''):
            try:
                c.execute("UPDATE users SET email=? WHERE id=?", (email, current_user.id))
                flash('Email updated successfully!', 'success')
            except sqlite3.IntegrityError:
                flash('Email already exists!', 'danger')
        
        # Update password
        if current_password and new_password:
            if bcrypt.check_password_hash(user_data['password'], current_password):
                hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
                c.execute("UPDATE users SET password=? WHERE id=?", (hashed_password, current_user.id))
                flash('Password updated successfully!', 'success')
            else:
                flash('Current password is incorrect!', 'danger')
        
        conn.commit()
        
        # Refresh user data
        c.execute("SELECT * FROM users WHERE id=?", (current_user.id,))
        user_data = c.fetchone()
    
    # Get statistics
    c.execute("SELECT COUNT(*) as count FROM expenses WHERE user_id=?", (current_user.id,))
    expense_count = c.fetchone()['count']
    
    c.execute("SELECT SUM(amount) as total FROM expenses WHERE user_id=?", (current_user.id,))
    total_expenses = c.fetchone()['total'] or 0
    
    c.execute("SELECT COUNT(*) as count FROM income WHERE user_id=?", (current_user.id,))
    income_count = c.fetchone()['count']
    
    c.execute("SELECT SUM(amount) as total FROM income WHERE user_id=?", (current_user.id,))
    total_income = c.fetchone()['total'] or 0
    
    conn.close()
    
    return render_template('profile.html', 
                          user=user_data,
                          expense_count=expense_count,
                          total_expenses=total_expenses,
                          income_count=income_count,
                          total_income=total_income,
                          balance=total_income - total_expenses)
@app.route('/export_data')
@login_required
def export_data():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Get user's data
    c.execute("SELECT * FROM expenses WHERE user_id=?", (current_user.id,))
    expenses = [dict(row) for row in c.fetchall()]
    
    c.execute("SELECT * FROM income WHERE user_id=?", (current_user.id,))
    income = [dict(row) for row in c.fetchall()]
    
    c.execute("SELECT * FROM categories WHERE user_id=?", (current_user.id,))
    categories = [dict(row) for row in c.fetchall()]
    
    c.execute("SELECT * FROM budgets WHERE user_id=?", (current_user.id,))
    budgets = [dict(row) for row in c.fetchall()]
    
    conn.close()
    
    # Create data dictionary
    data = {
        'expenses': expenses,
        'income': income,
        'categories': categories,
        'budgets': budgets
    }
    
    # Convert to JSON
    json_data = json.dumps(data, indent=4)
    
    # Create response
    response = Response(
        json_data,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment;filename=expense_tracker_data.json"}
    )
    
    return response

@app.route('/import_data', methods=['GET', 'POST'])
@login_required
def import_data():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file', 'danger')
            return redirect(request.url)
        
        if file:
            try:
                # Read JSON data
                data = json.loads(file.read())
                
                conn = get_db_connection()
                c = conn.cursor()
                
                # Import categories
                if 'categories' in data:
                    for category in data['categories']:
                        # Check if category already exists
                        c.execute("SELECT * FROM categories WHERE name=? AND user_id=?", 
                                 (category['name'], current_user.id))
                        if not c.fetchone():
                            c.execute("INSERT INTO categories (name, user_id) VALUES (?, ?)",
                                     (category['name'], current_user.id))
                
                # Get category mappings
                c.execute("SELECT id, name FROM categories WHERE user_id=? OR user_id IS NULL", 
                         (current_user.id,))
                categories = {row['name']: row['id'] for row in c.fetchall()}
                
                # Import expenses
                if 'expenses' in data:
                    for expense in data['expenses']:
                        # Get category name for this expense
                        c.execute("SELECT name FROM categories WHERE id=?", (expense['category_id'],))
                        category_result = c.fetchone()
                        
                        if category_result:
                            category_name = category_result['name']
                            category_id = categories.get(category_name)
                            
                            if category_id:
                                # Check if this expense already exists
                                c.execute("""
                                    SELECT * FROM expenses 
                                    WHERE user_id=? AND category_id=? AND amount=? AND date=?
                                """, (current_user.id, category_id, expense['amount'], expense['date']))
                                
                                if not c.fetchone():
                                    description = expense.get('description', '')
                                    c.execute("""
                                        INSERT INTO expenses (user_id, category_id, amount, date, description)
                                        VALUES (?, ?, ?, ?, ?)
                                    """, (current_user.id, category_id, expense['amount'], expense['date'], description))
                
                # Import income
                if 'income' in data:
                    for income in data['income']:
                        # Check if this income already exists
                        c.execute("""
                            SELECT * FROM income 
                            WHERE user_id=? AND source=? AND amount=? AND date=?
                        """, (current_user.id, income['source'], income['amount'], income['date']))
                        
                        if not c.fetchone():
                            c.execute("""
                                INSERT INTO income (user_id, source, amount, date)
                                VALUES (?, ?, ?, ?)
                            """, (current_user.id, income['source'], income['amount'], income['date']))
                
                # Import budgets
                if 'budgets' in data:
                    for budget in data['budgets']:
                        # Get category name for this budget
                        c.execute("SELECT name FROM categories WHERE id=?", (budget['category_id'],))
                        category_result = c.fetchone()
                        
                        if category_result:
                            category_name = category_result['name']
                            category_id = categories.get(category_name)
                            
                            if category_id:
                                # Check if budget already exists
                                c.execute("""
                                    SELECT * FROM budgets 
                                    WHERE user_id=? AND category_id=? AND period=?
                                """, (current_user.id, category_id, budget['period']))
                                
                                existing_budget = c.fetchone()
                                
                                if existing_budget:
                                    c.execute("""
                                        UPDATE budgets SET amount=? WHERE id=?
                                    """, (budget['amount'], existing_budget['id']))
                                else:
                                    c.execute("""
                                        INSERT INTO budgets (user_id, category_id, amount, period)
                                        VALUES (?, ?, ?, ?)
                                    """, (current_user.id, category_id, budget['amount'], budget['period']))
                
                conn.commit()
                conn.close()
                
                flash('Data imported successfully!', 'success')
                return redirect(url_for('index'))
            
            except Exception as e:
                flash(f'Error importing data: {str(e)}', 'danger')
    
    return render_template('import_data.html')

if __name__ == "__main__":
    app.run(debug=True)
