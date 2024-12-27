![image (7)](https://github.com/user-attachments/assets/56bcbf19-968f-473b-af60-83791ee17776)

# **Expense Tracker**

**Expense Tracker** is a simple yet powerful web application designed to help users manage and track their personal expenses. The app allows users to input, view, and organize their expenses, making it easier to stay on top of their financial situation.

---

## **Features**

- **User Authentication**
  - User Login and Signup Options.

- **Visualization**
  - Pie chart Enhancements with option to download
    
- **Expense Management**: 
  - Add new expenses with details like amount, description, and category.
  - View a list of all expenses in a simple and easy-to-read table format.
  - Edit and delete expenses as needed.

- **Categorization**:
  - Expenses can be categorized (e.g., Food, Transportation, Utilities) for easier tracking and reporting.
  
- **Date Management**:
  - Expenses are tagged with the date of entry to track when each expense occurred.

- **Report Generation**:
  - Generate PDF reports of all expenses, providing a detailed breakdown that can be downloaded for offline use.

- **User-Friendly Interface**:
  - Simple and intuitive design for ease of use, making it accessible to all users.

---

## **Gallery**
![image](https://github.com/user-attachments/assets/71e2c696-04c6-4e46-ad3e-e3ae17462874)
![image](https://github.com/user-attachments/assets/bf5564c4-fc9b-4fba-8667-8340f7d6be0b)
![image](https://github.com/user-attachments/assets/f6d7e341-56b1-40aa-886e-52fda9a73393)
![image](https://github.com/user-attachments/assets/8a252ee7-ec8c-41b3-aa96-90e60ffa2ec8)
![image](https://github.com/user-attachments/assets/d27c2a31-6a8d-4d44-94e4-9dcd62292c11)
![image](https://github.com/user-attachments/assets/d7841e54-a90e-4dc9-9f1b-5adcfb62a397)

## **Technologies Used**

- **Frontend**: 
  - HTML, CSS, JavaScript for a responsive and dynamic interface.
  - Bootstrap for quick layout and styling.
  - **Responsive Design**: The application adapts to various screen sizes, ensuring a seamless experience on both desktop and mobile devices.

- **Backend**:
  - **Flask**: A lightweight web framework used for handling HTTP requests, user input, and server-side processing.
  - **SQLite**: A lightweight database engine to store user expenses.
  
- **PDF Generation**:
  - **FPDF**: A library to generate expense reports in PDF format, which can be downloaded by users.

---

## **Responsive Design**

The web application is fully **responsive** and designed to provide an optimal user experience across a wide range of devices, including:

- **Mobile**: The design adapts to smaller screens with easy-to-use navigation and an intuitive layout.
- **Tablet**: The app offers an expanded layout for medium-sized screens, maintaining readability and accessibility.
- **Desktop**: The design scales well on larger screens, providing ample space for viewing and managing expenses.

---

## **How to Run Locally**

1. **Clone the Repository**:
   ```
   git clone <repository_url>
   cd Expense_Tracker
   ```

2. **Create a Virtual Environment**:
   ```
   python3 -m venv myenv
   source myenv/bin/activate  # On Windows: myenv\Scripts\activate
   ```

3. **Install Dependencies**:
   ```
   pip install -r requirements.txt
   ```

4. **Run the Flask App**:
   ```
   python app.py
   ```

5. Open your browser and go to `http://127.0.0.1:5000/` to view the app.

---

## **How to Deploy on PythonAnywhere**

1. **Create an Account on PythonAnywhere**: Sign up for a free account at [PythonAnywhere](https://www.pythonanywhere.com/).

2. **Upload Your Files**:
   - Use the PythonAnywhere file manager to upload the files from your project.

3. **Configure WSGI File**:
   - Edit the WSGI file to point to your Flask app (e.g., `from app import app as application`).

4. **Set Up Virtual Environment**:
   - Follow the instructions on PythonAnywhere to create and configure a virtual environment for your app.

5. **Install Dependencies**:
   - In the PythonAnywhere bash console, activate the virtual environment and run:
     ```
     pip install -r requirements.txt
     ```

6. **Reload the Web App**:
   - Go to the **Web** tab on PythonAnywhere and click **Reload** to start your app.

---

## **Known Issues**

- **Limited free-tier database**: The free version of PythonAnywhere has limited database access, which could limit the number of expenses that can be stored.
- **Performance**: For larger-scale projects, a more robust database solution (e.g., PostgreSQL) may be necessary.

---

## **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Feel free to adjust or extend the content based on your specific project setup, deployment instructions, and any additional features you might have implemented!
