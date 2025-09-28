# emp_insights.py

import os
import pandas as pd
from pymongo import MongoClient
import plotly.express as px
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "associate_portal")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "associates")


def get_associate_dataframe():
    """Fetch data from MongoDB and return as DataFrame"""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]
    data = list(collection.find({}, {"_id": 0}))
    return pd.DataFrame(data)


def get_associate_names():
    """Return list of all associate names"""
    df = get_associate_dataframe()
    if df.empty:
        return []
    return sorted(df["associate_name"].dropna().unique().tolist())


def get_associate_insights(associate_name: str):
    """Generate insights + visualizations for a selected associate"""
    df = get_associate_dataframe()
    if df.empty:
        return {"error": "No data found"}, []

    emp = df[df["associate_name"].str.lower() == associate_name.lower()]
    if emp.empty:
        return {"error": f"Associate '{associate_name}' not found"}, []

    emp = emp.iloc[0].to_dict()

    # --- Insights ---
    insights = {
        "Associate Name": emp.get("associate_name"),
        "Department": emp.get("department"),
        "Manager": emp.get("manager_name"),
        "Location": f"{emp.get('state')}, {emp.get('country')}",
        "Employment Status": emp.get("employment_status"),
        "Recruitment": emp.get("recruitment"),
        "Performance Score": emp.get("performance_score"),
        "Engagement Score": emp.get("engagement_score"),
        "Employee Satisfaction": emp.get("employee_satisfaction"),
        "Salary": emp.get("salary"),
        "Special Project": emp.get("special_project"),
        "Termination Reason": (
            emp.get("termination_reason")
            if emp.get("employment_status") == "Non-Active"
            else None
        ),
    }

    # --- Visualizations ---
    figs = []

    # Department distribution
    figs.append(px.histogram(df, x="department", title="Associates per Department"))

    # Gender distribution
    figs.append(px.pie(df, names="gender", title="Gender Distribution"))

    # Gender per department
    figs.append(
        px.histogram(
            df,
            x="department",
            color="gender",
            barmode="group",
            title="Gender Count per Department",
        )
    )

    # Recruitment source
    figs.append(px.pie(df, names="recruitment", title="Recruitment Sources"))

    # Country → State drilldown
    figs.append(
        px.sunburst(
            df, path=["country", "state"], title="Associates by Country and State"
        )
    )

    # Termination reasons (only Non-Active)
    non_active = df[df["employment_status"] == "Non-Active"]
    if not non_active.empty:
        figs.append(
            px.histogram(
                non_active, x="termination_reason", title="Termination Reasons"
            )
        )

    return insights, figs
