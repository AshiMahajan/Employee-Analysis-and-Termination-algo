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

mongo.db.dropdown_values.insert_many(
    [
        {"field": "department", "options": ["IT", "HR"]},
        {"field": "role", "options": ["Manager", "Developer"]},
    ]
)


# Function to generate HR ID
def generate_hr_id():
    count = mongo.db.users.count_documents({})
    return f"HR{count+1:03d}"


# Home route → directly render home page
@app.route("/")
def index():
    return render_template("home.html")


# --------- Load dropdown values ---------
def get_dropdown(field):
    record = mongo.db.dropdown_values.find_one({"field": field})
    return record["options"] if record else []


# --------- Add new option to dropdown ---------
@app.route("/add_option", methods=["POST"])
def add_option():
    field = request.form.get("field")
    new_value = request.form.get("value")

    if field and new_value:
        mongo.db.dropdown_values.update_one(
            {"field": field},
            {"$addToSet": {"options": new_value}},  # add only if not exists
            upsert=True,
        )
        flash(f"New {field} option '{new_value}' added!")

    return redirect(url_for("add_associate"))


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
    filter_type = request.args.get("filter", None)

    managers = list(mongo.db.managers.find({}, {"_id": 0}))
    associates = list(mongo.db.associates.find({}, {"_id": 0}))

    return render_template(
        "dashboard.html",
        user=session["user"],
        hr_id=session["hr_id"],
        filter=filter_type,
        managers=managers,
        associates=associates,
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
        mongo.db.managers.insert_one(
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

    if "new_associate" not in session:
        session["new_associate"] = {}

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_section":
            section_data = {
                k: v
                for k, v in request.form.items()
                if k not in ["action", "csrf_token"]
            }
            session["new_associate"].update(section_data)
            session.modified = True
            flash("Section saved! (Not yet stored in DB)")

        elif action == "proceed":
            associate_data = session.get("new_associate", {})
            mongo.db.associates.insert_one(associate_data)
            flash("Associate added successfully!")
            session.pop("new_associate", None)
            return redirect(url_for("dashboard"))

    # Load dropdowns dynamically from DB
    genders = get_dropdown("gender")
    marital_statuses = get_dropdown("marital_status")
    departments = get_dropdown("department")
    term_reasons = get_dropdown("termination_reason")
    managers = list(
        mongo.db.managers.find({}, {"_id": 0, "manager_name": 1, "manager_id": 1})
    )
    recruitments = get_dropdown("recruitment")
    countries = get_dropdown("country")

    return render_template(
        "add_associate.html",
        user=session["user"],
        hr_id=session["hr_id"],
        form_data=session.get("new_associate", {}),
        genders=genders,
        marital_statuses=marital_statuses,
        departments=departments,
        term_reasons=term_reasons,
        managers=managers,
        recruitments=recruitments,
        countries=countries,
    )


@app.route("/edit_employee/<emp_id>", methods=["GET", "POST"])
def edit_employee(emp_id):
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("login"))

    # Fetch employee details
    emp = mongo.db.associates.find_one({"emp_id": emp_id}, {"_id": 0})
    if not emp:
        flash("Employee not found.")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        # Update employee details from form
        name = request.form.get("name")
        department = request.form.get("department")
        salary = request.form.get("salary")

        mongo.db.associates.update_one(
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
