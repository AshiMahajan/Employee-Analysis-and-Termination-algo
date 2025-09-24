import pandas as pd
from pymongo import MongoClient
import plotly.express as px
import plotly.graph_objects as go

import os
from dotenv import load_dotenv


load_dotenv()

MONGO_URI = os.getenv("MONGO_PY")
DB_NAME = os.getenv("DB_NAME", "employee_portal")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "associates")


def get_employee_dataframe():
    """Fetch data from MongoDB and return as DataFrame"""
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    data = list(collection.find({}, {"_id": 0}))
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)


# ----------------- Visualizations -----------------
def plot_department_count(df):
    """Bar chart: Employees per department"""
    if "department" not in df.columns:
        return "<p>No 'department' data available.</p>"
    dept_counts = df["department"].value_counts().reset_index()
    dept_counts.columns = ["Department", "Count"]
    fig = px.bar(
        dept_counts,
        x="Department",
        y="Count",
        title="Employees per Department",
        text="Count",
        color="Department",
    )
    fig.update_traces(textposition="outside")
    return fig.to_html(full_html=False)


def plot_recruitment_pie(df):
    """Pie chart: Recruitment source distribution"""
    if "recruitment" not in df.columns:
        return "<p>No 'recruitment' data available.</p>"
    rec_counts = df["recruitment"].value_counts().reset_index()
    rec_counts.columns = ["Recruitment", "Count"]
    fig = px.pie(
        rec_counts,
        values="Count",
        names="Recruitment",
        title="Recruitment Source Distribution",
    )
    return fig.to_html(full_html=False)


def plot_gender_distribution(df):
    """Grouped bar: Gender overall and per department"""
    if "gender" not in df.columns or "department" not in df.columns:
        return "<p>No 'gender' or 'department' data available.</p>"
    gender_dept = df.groupby(["department", "gender"]).size().reset_index(name="Count")
    fig = px.bar(
        gender_dept,
        x="department",
        y="Count",
        color="gender",
        title="Gender Distribution per Department",
        barmode="group",
    )
    return fig.to_html(full_html=False)


def plot_country_state(df):
    """Interactive: Employees by country and state"""
    if "country" not in df.columns:
        return "<p>No 'country' data available.</p>"
    country_counts = df.groupby("country").size().reset_index(name="Count")
    fig = px.bar(
        country_counts,
        x="country",
        y="Count",
        title="Employees per Country",
        hover_data=["country", "Count"],
        text="Count",
    )

    return fig.to_html(full_html=False)


def plot_termination_reason(df):
    """Bar chart: Termination reason for Non-Active employees"""
    if "employment_status" not in df.columns or "termination_reason" not in df.columns:
        return "<p>No required data available.</p>"
    terminated_df = df[df["employment_status"].str.lower() != "active"]
    if terminated_df.empty:
        return "<p>No terminated employees.</p>"
    term_counts = terminated_df["termination_reason"].value_counts().reset_index()
    term_counts.columns = ["Termination Reason", "Count"]
    fig = px.bar(
        term_counts,
        x="Termination Reason",
        y="Count",
        title="Termination Reasons (Non-Active Employees)",
        text="Count",
    )
    fig.update_traces(textposition="outside")
    return fig.to_html(full_html=False)
