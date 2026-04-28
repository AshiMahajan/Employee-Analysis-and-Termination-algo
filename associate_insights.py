import os
import pandas as pd
from pymongo import MongoClient
import plotly.express as px
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "associate_portal")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "associates")


def _get_collection():
    client = MongoClient(MONGO_URI)
    return client[DB_NAME][COLLECTION_NAME]


def get_associate_dataframe():
    """Fetch all associates from MongoDB and return as DataFrame."""
    collection = _get_collection()
    data = list(collection.find({}, {"_id": 0}))
    return pd.DataFrame(data)


def get_associate_names():
    """Return sorted list of associate names."""
    collection = _get_collection()

    docs = collection.find(
        {"associate_name": {"$exists": True, "$ne": None}},
        {"associate_name": 1, "_id": 0},
    )

    names = sorted(
        set(doc["associate_name"] for doc in docs if doc.get("associate_name"))
    )

    return names


def get_associate_insights(search_term: str):
    """
    Accepts:
        associate_name
        OR associate_id
    Handles MongoDB int32 ID correctly.
    """

    collection = _get_collection()

    term = search_term.strip()

    associate = None

    # FIRST: Try searching by name
    associate = collection.find_one({"associate_name": term}, {"_id": 0})

    # SECOND: Try searching by ID (convert string → int if numeric)
    if not associate:
        try:
            term_int = int(term)

            associate = collection.find_one({"associate_id": term_int}, {"_id": 0})

        except ValueError:
            pass

    # STILL nothing found
    if not associate:
        return {"error": f"No employee found for '{search_term}'"}, []

    df = get_associate_dataframe()

    # LOCATION FORMAT
    location_parts = [
        associate.get("state"),
        associate.get("zip"),
    ]

    location = ", ".join(str(p) for p in location_parts if p)

    insights = {
        "Associate Name": associate.get("associate_name"),
        "Department": associate.get("department"),
        "Manager": associate.get("manager_name"),
        "Location": location,
        "Employment Status": associate.get("employment_status"),
        "Gender": associate.get("gender"),
        "Marital Status": associate.get("marital_status"),
        "Date of Hire": associate.get("dateofhire"),
        "Recruitment": associate.get("recruitment"),
        "Performance Score": associate.get("performance_score"),
        "Engagement Score": associate.get("engagement_score"),
        "Employee Satisfaction": associate.get("employee_satisfaction"),
        "Salary": f"${associate.get('salary'):,}" if associate.get("salary") else None,
        "Days Late": associate.get("days_late"),
        "Absences": associate.get("absences"),
        "Special Project": associate.get("special_project"),
        "Last Review": associate.get("last_review"),
        "Termination Reason": (
            associate.get("termination_reason")
            if associate.get("employment_status") != "Active"
            else None
        ),
    }

    # OPTIONAL VISUALS
    figs = []

    if "department" in df.columns:
        figs.append(px.histogram(df, x="department", title="Associates per Department"))

    if "gender" in df.columns:
        figs.append(px.pie(df, names="gender", title="Gender Distribution"))

    return insights, figs
