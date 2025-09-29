from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_mail import Mail, Message
import os
from dotenv import load_dotenv
import requests
from flask import jsonify, request
import pandas as pd

# CSV
from csv_routes import csv_bp

#

load_dotenv()  # loads .env into environment variables
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# for CSV
app.register_blueprint(csv_bp)

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

# Initialize default dropdown values (run once at app start)
default_values = {
    "department": ["IT", "HR"],
    "gender": ["Male", "Female", "Other"],
    "marital_status": ["Single", "Married"],
    "termination_reason": ["Resigned", "Fired", "Retired"],
    "recruitment": ["Referral", "Job Portal", "Campus"],
}

for field, options in default_values.items():
    mongo.db.dropdown_values.update_one(
        {"field": field},
        {"$setOnInsert": {"options": options}},
        upsert=True,
    )


#
API_KEY = os.getenv("CSC_API_KEY")
BASE_URL = "https://api.countrystatecity.in/v1"
HEADERS = {"X-CSCAPI-KEY": API_KEY}


@app.route("/api/countries")
def get_countries():
    url = f"{BASE_URL}/countries"
    response = requests.get(url, headers=HEADERS)
    return jsonify(response.json())


@app.route("/api/states/<country_iso>")
def get_states(country_iso):
    url = f"{BASE_URL}/countries/{country_iso}/states"
    response = requests.get(url, headers=HEADERS)
    return jsonify(response.json())


#
# --------- Load dropdown values ---------
def get_dropdown(field):
    record = mongo.db.dropdown_values.find_one({"field": field})
    return record["options"] if record else []


@app.route("/delete_dropdown/<field>/<value>")
def delete_dropdown_option(field, value):
    mongo.db.dropdown_values.update_one({"field": field}, {"$pull": {"options": value}})
    flash(f"{value} removed from {field} dropdown")
    return redirect(url_for("manage_dropdowns"))  # adjust route name


#
@app.route("/dropdowns", methods=["GET", "POST"])
def manage_dropdowns():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("login"))

    if request.method == "POST":
        field = request.form.get("field")
        value = request.form.get("value")

        if field and value:
            mongo.db.dropdown_values.update_one(
                {"field": field},
                {"$addToSet": {"options": value}},  # prevents duplicates
                upsert=True,
            )
            flash(f"Added '{value}' to {field}")

    # fetch dropdowns from DB
    dropdowns = list(mongo.db.dropdown_values.find({}, {"_id": 0}))

    return render_template(
        "manage_dropdowns.html",
        dropdowns=dropdowns,
        user=session.get("user"),  # safe lookup
        hr_id=session.get("hr_id"),  # safe lookup
    )


#


# Function to generate HR ID
def generate_hr_id():
    count = mongo.db.users.count_documents({})
    return f"HR{count+1:03d}"


# Home route → directly render home page
@app.route("/")
def index():
    return render_template("home.html")


# --------- Add new option to dropdown ---------
@app.route("/add_option", methods=["POST"])
def add_option():
    data = request.get_json()
    field = data.get("field")
    new_value = data.get("value")

    if field and new_value:
        mongo.db.dropdown_values.update_one(
            {"field": field},
            {"$addToSet": {"options": new_value}},  # add only if not exists
            upsert=True,
        )
        return {"status": "success", "message": f"{new_value} added to {field}"}, 200
    return {"status": "error", "message": "Invalid data"}, 400


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


# Visualization
from ml_utils import (
    get_employee_dataframe,
    plot_department_count,
    plot_recruitment_pie,
    plot_gender_distribution,
    plot_country_state,
    plot_termination_reason,
)


@app.route("/visualization")
def visualization():
    df = get_employee_dataframe()
    if df.empty:
        return render_template(
            "visualization.html", plots=None, message="No employee data available."
        )

    plots = {
        "Department Count": plot_department_count(df),
        "Recruitment Source": plot_recruitment_pie(df),
        "Gender Distribution": plot_gender_distribution(df),
        "Country-wise Employees": plot_country_state(df),
        "Termination Reasons": plot_termination_reason(df),
    }

    return render_template(
        "visualization.html",
        plots=plots,
        message=None,
        user=session["user"],
        hr_id=session["hr_id"],
    )


#

from associate_insights import (
    get_associate_dataframe,
    get_associate_names,
    get_associate_insights,
)


@app.route("/associate_insights", methods=["GET", "POST"])
def associate_insights():
    associate_names = get_associate_names()
    selected_name = request.form.get("associate_name")

    insights, figs = ({}, [])
    if selected_name:
        insights, figs = get_associate_insights(selected_name)

    graphs_html = [f.to_html(full_html=False) for f in figs]

    return render_template(
        "associate_insights.html",
        associate_names=associate_names,
        selected_name=selected_name,
        insights=insights,
        graphs_html=graphs_html,
    )


# Attrition Prediction
from associate_attrition import predict_employee, fetch_data, train_model


@app.route("/associate_attrition", methods=["GET", "POST"])
def associate_attrition():
    result = None
    selected_name = None

    # Fetch associates for dropdown
    df = fetch_data()
    if df.empty or "associate_name" not in df.columns:
        associate_names = []
    else:
        associate_names = df["associate_name"].dropna().unique().tolist()

    if request.method == "POST":
        selected_name = request.form.get("associate_name")

        # Train model on current data before prediction
        try:
            train_model()
        except Exception as e:
            print("⚠ Model training failed:", e)

        # Predict attrition for selected associate
        result = predict_employee(selected_name)

    return render_template(
        "attrition.html",
        result=result,
        associate_names=associate_names,
        selected_name=selected_name,
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
            return redirect(url_for("add_associate"))  # reload with data prefilled

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
        dropdowns={
            "gender": genders,
            "marital_status": marital_statuses,
            "department": departments,
            "termination_reason": term_reasons,
            "managers": managers,
            "recruitment": recruitments,
        },
        zip="zip",
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
