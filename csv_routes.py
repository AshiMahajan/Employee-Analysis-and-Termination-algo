import os
import pandas as pd
from flask import Blueprint, request, jsonify, flash, redirect, url_for
from pymongo import MongoClient
from werkzeug.utils import secure_filename
from datetime import datetime

# ---------------- Config ----------------
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"csv", "xls", "xlsx"}

csv_bp = Blueprint("csv_bp", __name__, template_folder="templates")

# MongoDB
MONGO_URI = os.getenv("MONGO_PY")
DB_NAME = os.getenv("DB_NAME", "employee_portal")
COLLECTION = os.getenv("COLLECTION_NAME", "associates")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION]


# ---------------- Helpers ----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def normalize_columns(df):
    COLUMN_MAP = {
        "associate_id": ["id", "emp_id", "associateid", "employee_id", "EmpID"],
        "associate_name": ["name", "full_name", "employee_name", "Employee_Name"],
        "gender": ["gender", "Sex"],
        "marital_status": ["marital_status", "married_status", "MaritalDesc"],
        "department": ["Department", "dept", "division"],
        "department_id": ["department_id", "dept_id", "division_id", "DeptID"],
        "employment_status": ["employment_status", "EmploymentStatus", "job_status"],
        "manager_name": ["ManagerName", "manager_name", "supervisor"],
        "manager_id": ["ManagerID", "supervisor_id"],
        "recruitment": ["RecruitmentSource", "hiring_source", "source"],
        "performance_score": ["PerformanceScore", "review_score", "perf_score"],
        "engagement_score": ["EngagementSurvey", "employee_engagement"],
        "employee_satisfaction": [
            "employee_satisfaction",
            "EmpSatisfaction",
            "job_satisfaction",
        ],
        "termination_reason": ["TermReason", "reason_for_termination"],
        "salary": ["Salary", "pay", "ctc", "wage"],
        "special_project": ["SpecialProjectsCount", "project", "extra_project"],
        "country": ["Country", "nation"],
        "state": ["State", "province", "region"],
        "zip": ["Zip", "zipcode", "postal_code"],
        "dob": ["DOB", "dateofbirth", "date_of_birth", "birthdate"],
        "dateofhire": ["DateofHire", "hire_date", "joining_date"],
        "race": ["RaceDesc", "ethnicity", "ethnic_group"],
        "last_review": [
            "LastPerformanceReview_Date",
            "last_review_date",
            "last_performance_review",
        ],
        "days_late": ["DaysLateLast30", "lateness_days", "days_late_work"],
        "absences": ["Absences", "absence_days", "days_absent"],
    }

    rename_dict = {}
    for canonical, variants in COLUMN_MAP.items():
        for col in df.columns:
            col_norm = col.lower().replace(" ", "_")
            if col_norm in [
                v.lower().replace(" ", "_") for v in variants
            ]:  # Normalize variants too
                rename_dict[col] = canonical

    return df.rename(columns=rename_dict)


def clean_dataframe(df):
    str_cols = df.select_dtypes(include="object").columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()

    if "dob" in df.columns:

        def clean_dob(x):
            for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(str(x), fmt).strftime("%d-%m-%Y")
                except:
                    continue
            return None

        df["dob"] = df["dob"].apply(clean_dob)

    if "dateofhire" in df.columns:

        def clean_hire(x):
            for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(str(x), fmt).strftime("%d-%m-%Y")
                except:
                    continue
            return None

        df["dateofhire"] = df["dateofhire"].apply(clean_hire)

    numeric_cols = [
        "salary",
        "performance_score",
        "engagement_score",
        "employee_satisfaction",
        "days_late",
        "absences",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


# ---------------- Routes ----------------
@csv_bp.route("/csv", methods=["POST"])
def csv_upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        return jsonify({"success": False, "message": "No file selected."}), 400

    if not allowed_file(file.filename):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Invalid file type. Only CSV/XLS/XLSX allowed.",
                }
            ),
            400,
        )

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    file.save(filepath)

    try:
        ext = filename.rsplit(".", 1)[1].lower()
        if ext == "csv":
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        df = normalize_columns(df)
        df = clean_dataframe(df)
        df = df.dropna(subset=["associate_id", "associate_name"])

        if df.empty:
            os.remove(filepath)
            return (
                jsonify(
                    {"success": False, "message": "No valid rows found after cleaning."}
                ),
                400,
            )

        records = df.to_dict(orient="records")
        result = collection.insert_many(records)
        inserted_count = len(result.inserted_ids)

        os.remove(filepath)

        return jsonify(
            {
                "success": True,
                "message": f"✅ Successfully uploaded and saved {inserted_count} records into MongoDB.",
            }
        )

    except Exception as e:
        if os.path.exists(filepath):
            os.remove(filepath)
        return (
            jsonify({"success": False, "message": f"Processing error: {str(e)}"}),
            500,
        )
