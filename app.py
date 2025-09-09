from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_mail import Mail, Message
import os
from dotenv import load_dotenv

load_dotenv()  # loads .env into environment variables
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# MongoDB connection string
app.config["MONGO_URI"] = os.getenv("MONGO_URI")
mongo = PyMongo(app)

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USE_SSL"] = False
mail = Mail(app)


# Function to generate HR ID
def generate_hr_id():
    count = mongo.db.users.count_documents({})
    return f"HR{count+1:03d}"


# Home route → directly render home page
@app.route("/")
def index():
    return render_template("home.html")


# Function to send email
def send_email(to_email, subject, body):
    try:
        msg = Message(
            subject,
            sender=app.config["MAIL_USERNAME"],
            recipients=[to_email],
            body=body,
        )
        mail.send(msg)
        print("✅ Email sent successfully!")
    except Exception as e:
        print("❌ Error sending email:", e)


# Signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        # Check if email already exists
        if mongo.db.users.find_one({"email": email}):
            flash("Account already exists. Please login.")
            return redirect(url_for("login"))

        # Generate HR ID
        hr_id = generate_hr_id()

        # Insert into DB
        mongo.db.users.insert_one(
            {"hr_id": hr_id, "name": name, "email": email, "password": password}
        )

        # Send HR ID via email
        subject = "Your HR System ID"
        body = (
            f"Hello {name},\n\nYour HR System ID is: {hr_id}\n\nUse this ID to login."
        )
        send_email(email, subject, body)

        flash("Account created! Check your email for HR ID.")
        return redirect(url_for("login"))

    return render_template("signup.html")


# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        hr_id = request.form["hr_id"]
        password = request.form["password"]

        user = mongo.db.users.find_one({"hr_id": hr_id, "password": password})
        if user:
            session["user"] = user["name"]
            session["hr_id"] = user["hr_id"]
            flash("Login successful!")
            return redirect(url_for("dashboard"))

        flash("Invalid HR ID or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


# Dashboard
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("login"))

    # Fetch all employees from MongoDB
    employees = list(mongo.db.employees.find({}, {"_id": 0}))  # exclude _id

    return render_template(
        "dashboard.html",
        user=session["user"],
        hr_id=session["hr_id"],
        employees=employees,
    )


# Enter employee data
@app.route("/manager", methods=["GET", "POST"])
def add_manager():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("login"))

    if request.method == "POST":
        # Get employee details from form
        manager_name = request.form["manager_name"]
        manager_id = request.form["manager_id"]
        # Add more fields as needed

        # Insert into MongoDB
        mongo.db.employees.insert_one(
            {
                "manager_name": manager_name,
                "manager_id": manager_id,
                # Add more fields here
            }
        )

        flash("Manager added successfully!")
        return redirect(url_for("dashboard"))

    return render_template(
        "add_manager.html",
        user=session["user"],
        hr_id=session["hr_id"],
    )


@app.route("/associate", methods=["GET", "POST"])
def add_associate():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("login"))

    if request.method == "POST":
        # Get employee details from form
        associate_name = request.form["associate_name"]
        associate_id = request.form["associate_id"]
        department = request.form["department"]
        # Add more fields as needed

        # Insert into MongoDB
        mongo.db.employees.insert_one(
            {
                "associate_name": associate_name,
                "associate_id": associate_id,
                "department": department,
                # Add more fields here
            }
        )

        flash("Associate added successfully!")
        return redirect(url_for("dashboard"))

    return render_template(
        "add_associate.html",
        user=session["user"],
        hr_id=session["hr_id"],
    )


@app.route("/edit_employee/<emp_id>", methods=["GET", "POST"])
def edit_employee(emp_id):
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("login"))

    # Fetch employee details
    emp = mongo.db.employees.find_one({"emp_id": emp_id}, {"_id": 0})
    if not emp:
        flash("Employee not found.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        # Update employee details from form
        name = request.form.get("name")
        department = request.form.get("department")
        salary = request.form.get("salary")

        mongo.db.employees.update_one(
            {"emp_id": emp_id},
            {"$set": {"name": name, "department": department, "salary": salary}},
        )

        flash("Employee updated successfully!")
        return redirect(url_for("dashboard"))

    return render_template("edit_employee.html", employee=emp)


# Logout
@app.route("/logout")
def logout():
    session.clear()  # clears the entire session
    flash("Logged out successfully.")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run()
