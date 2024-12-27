from flask import Flask, render_template, request, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from flask_bcrypt import Bcrypt
import sqlite3
import os
from datetime import datetime
import matplotlib.pyplot as plt
import io
import base64
from flask import send_file, Response
from io import BytesIO
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Generates a random 24-byte string
login_manager = LoginManager()
login_manager.init_app(app)
bcrypt = Bcrypt(app)

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login'))

# Database setup
def create_db():
    conn = sqlite3.connect('expense.db')  # Corrected database name to 'expense.db'
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, user_id INTEGER, category_id INTEGER,
                 amount REAL, date TEXT,
                 FOREIGN KEY(user_id) REFERENCES users(id),
                 FOREIGN KEY(category_id) REFERENCES categories(id))''')
    conn.commit()
    conn.close()

create_db()

# User model
class User(UserMixin):
    def __init__(self, id):
        self.id = id

# Load user function
@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

@app.route('/')
@login_required
def index():
    conn = sqlite3.connect('expense.db')  # Corrected database name
    c = conn.cursor()
    c.execute("SELECT * FROM expenses WHERE user_id=?", (session['user_id'],))
    expenses = c.fetchall()
    
    c.execute("SELECT * FROM categories")
    categories = c.fetchall()
    
    conn.close()

    # If no categories exist, redirect to add category page
    if not categories:
        return redirect(url_for('add_category'))
    
    return render_template('index.html', expenses=expenses, categories=categories, today=datetime.today().date())

@app.route('/add', methods=['POST'])
@login_required
def add_expense():
    category_id = request.form['category_id']
    amount = request.form['amount']
    date = request.form['date']
    
    if category_id and amount:
        conn = sqlite3.connect('expense.db')  # Corrected database name
        c = conn.cursor()
        c.execute("INSERT INTO expenses (user_id, category_id, amount, date) VALUES (?, ?, ?, ?)", 
                  (session['user_id'], category_id, float(amount), date))
        conn.commit()
        conn.close()
    
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
@login_required
def delete_expense(id):
    conn = sqlite3.connect('expense.db')  # Corrected database name
    c = conn.cursor()
    c.execute("DELETE FROM expenses WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_expense(id):
    if request.method == 'POST':
        category_id = request.form['category_id']
        amount = request.form['amount']
        date = request.form['date']

        conn = sqlite3.connect('expense.db')  # Corrected database name
        c = conn.cursor()
        c.execute("UPDATE expenses SET category_id=?, amount=?, date=? WHERE id=?", 
                  (category_id, float(amount), date, id))
        conn.commit()
        conn.close()
        
        return redirect(url_for('index'))

    # Fetch existing expense data for editing
    conn = sqlite3.connect('expense.db')  # Corrected database name
    c = conn.cursor()
    c.execute("SELECT * FROM expenses WHERE id=?", (id,))
    expense_data = c.fetchone()

    # Fetch categories for dropdown selection
    c.execute("SELECT * FROM categories")
    categories = c.fetchall()

    conn.close()

    return render_template('edit_expense.html', expense=expense_data, categories=categories)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        
        try:
            conn = sqlite3.connect('expense.db')  # Corrected database name
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "Username already exists!"
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('expense.db')  # Corrected database name
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user_data = c.fetchone()  # Fetch user data
        
        if user_data and bcrypt.check_password_hash(user_data[2], password):
            user = User(user_data[0])
            login_user(user)
            session['user_id'] = user_data[0]
            
            # Check if the user has any categories
            c.execute("SELECT * FROM categories WHERE id IN (SELECT category_id FROM expenses WHERE user_id=?)", (session['user_id'],))
            if not c.fetchall():  # Check for existing categories
                return redirect(url_for('add_category'))  # Redirect to add category if none exist
            
            return redirect(url_for('index'))  # Redirect to index if categories exist
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/add_category', methods=['GET', 'POST'])
@login_required
def add_category():
    if request.method == 'POST':
        category_name = request.form['category_name']
        
        if category_name:
            conn = sqlite3.connect('expense.db')  # Corrected database name
            c = conn.cursor()
            c.execute("INSERT INTO categories (name) VALUES (?)", (category_name,))
            conn.commit()
            conn.close()
            return redirect(url_for('index'))
    
    return render_template('add_category.html')

@app.route('/show_chart')
@login_required
def show_chart():
    conn = sqlite3.connect('expense.db')  # Corrected database name
    c = conn.cursor()
    
    # Fetch expenses grouped by category
    c.execute('''SELECT c.name, SUM(e.amount) 
                 FROM expenses e 
                 JOIN categories c ON e.category_id = c.id 
                 WHERE e.user_id = ? 
                 GROUP BY c.name''', (session['user_id'],))
    
    data = c.fetchall()
    conn.close()

    # Prepare data for pie chart
    categories = [row[0] for row in data]
    amounts = [row[1] for row in data]

    # Create a pie chart
    plt.figure(figsize=(8, 6))
    plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=140)
    plt.title('Expenses by Category')

    # Save it to a BytesIO object
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    
    # Encode the image to base64
    plot_url = base64.b64encode(img.getvalue()).decode()

    return render_template('chart.html', plot_url=plot_url)


@app.route('/download_table', methods=['GET'])
def download_table():
    # Connect to your database
    conn = sqlite3.connect('expense.db')  # Replace with your database connection
    cursor = conn.cursor()

    # Fetch the expense data dynamically
    cursor.execute('''SELECT e.id, c.name AS category, e.amount, e.date 
                    FROM expenses e
                    JOIN categories c ON e.category_id = c.id''')  # Adjust this query for your expenses table
    table_data = cursor.fetchall()
    column_names = [description[0] for description in cursor.description]

    # Initialize PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Add table header
    pdf.set_font("Arial", style='B', size=12)
    header = " | ".join(column_names)  # e.g., "ID | Category | Amount | Date"
    pdf.cell(200, 10, txt=header, ln=True, align='C')

    # Add table rows
    pdf.set_font("Arial", size=12)
    for row in table_data:
        row_text = " | ".join(str(item) for item in row)
        pdf.cell(200, 10, txt=row_text, ln=True)

    # Close the database connection
    conn.close()

    # Use BytesIO for in-memory PDF storage
    pdf_output = BytesIO()
    # Save the PDF to the BytesIO object
    pdf_output.write(pdf.output(dest='S').encode('latin1'))
    pdf_output.seek(0)  # Move to the beginning of the BytesIO object

    # Return the PDF as a Flask response
    return Response(
        pdf_output,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment;filename=expenses_table.pdf"}
    )


@app.route('/download_chart')
@login_required
def download_chart():
    conn = sqlite3.connect('expense.db')  # Corrected database name
    c = conn.cursor()
    c.execute('''SELECT c.name, SUM(e.amount) 
                 FROM expenses e 
                 JOIN categories c ON e.category_id = c.id 
                 WHERE e.user_id = ? 
                 GROUP BY c.name''', (session['user_id'],))
    data = c.fetchall()
    conn.close()

    categories = [row[0] for row in data]
    amounts = [row[1] for row in data]

    plt.figure(figsize=(8, 6))
    plt.pie(amounts, labels=categories, autopct='%1.1f%%', startangle=140)
    plt.title('Expenses by Category')

    img = io.BytesIO()
    plt.savefig(img, format='pdf')
    img.seek(0)

    return send_file(img, as_attachment=True, download_name="expense_chart.pdf", mimetype="application/pdf")


if __name__ == "__main__":
    app.run(debug=True)
