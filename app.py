from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_pymongo import PyMongo

app = Flask(__name__)
app.secret_key = "your_secret_key"

# MongoDB connection string (default localhost:27017)
app.config["MONGO_URI"] = "mongodb://localhost:27017/employee_portal"
mongo = PyMongo(app)


# Home route → directly render home page
@app.route("/")
def index():
    return render_template("home.html")


# Signup Page
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        # Check if user exists
        if mongo.db.users.find_one({"email": email}):
            flash("Account already exists. Please login.")
            return redirect(url_for("login"))

        # Insert user into MongoDB
        mongo.db.users.insert_one({"name": name, "email": email, "password": password})

        flash("Account created successfully! Please login.")
        return redirect(url_for("login"))

    return render_template("signup.html")


# Login Page
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        # Match both email and password
        user = mongo.db.users.find_one({"email": email, "password": password})
        if user:
            session["user"] = user["name"]  # ✅ store in session
            flash("Login successful!")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


# Dashboard (after login)
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please login first.")
        return redirect(url_for("login"))

    return render_template("dashboard.html", user=session["user"])


# Logout
@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Logged out successfully.")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run()
