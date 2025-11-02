import io
import base64
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime


def save_plot_to_base64():
    """Save current matplotlib figure to base64 string."""
    buf = io.BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
    buf.close()
    plt.close()
    return encoded


def analyze_salary(df, associate_name):
    """
    Run salary analysis for given associate.
    Returns dict with:
      text_output -> list of strings
      figures -> list of base64 charts
    """
    text_output = []
    figs = []

    # Filter for associate
    employee_data = df[df["associate_name"] == associate_name]
    if employee_data.empty:
        return {
            "text_output": [f"Associate '{associate_name}' not found."],
            "figures": [],
        }

    # Check termination
    if (
        "termination" in employee_data.columns
        and str(employee_data.iloc[0]["termination"]) != "0"
    ):
        return {
            "text_output": [
                f"{associate_name} is not currently employed. Analysis stopped."
            ],
            "figures": [],
        }

    # --- Compute Age from DOB ---
    dob_val = employee_data.iloc[0].get("dob", None)
    if dob_val:
        try:
            dob_val = pd.to_datetime(dob_val)
            age = datetime.now().year - dob_val.year
        except Exception:
            age = "N/A"
    else:
        age = "N/A"

    # --- Compute Experience from Date of Hire ---
    doh_val = employee_data.iloc[0].get("dateofhire", None)
    if doh_val:
        try:
            doh_val = pd.to_datetime(doh_val)
            experience = datetime.now().year - doh_val.year
        except Exception:
            experience = "N/A"
    else:
        experience = "N/A"

    # --- Extract Salary ---
    current_salary = employee_data.iloc[0].get("salary", None)

    text_output.append(f"Current salary: ${current_salary}")
    text_output.append(f"Age: {age} years")
    text_output.append(f"Experience: {experience} years")

    # --- Chart: salary vs Department Average ---
    dept = employee_data.iloc[0].get("department", None)
    if "termination" in df.columns:
        still_employed_df = df[df["termination"] == "0"]
    else:
        still_employed_df = df.copy()  # fallback

    if dept and "salary" in df.columns:
        dept_avg = still_employed_df[still_employed_df["department"] == dept][
            "salary"
        ].mean()

        comp_df = pd.DataFrame(
            {
                "Category": [associate_name, f"{dept} Avg"],
                "salary": [current_salary, dept_avg],
            }
        )

        plt.figure(figsize=(6, 4))
        sns.barplot(data=comp_df, x="Category", y="salary", palette="viridis")
        for index, value in enumerate(comp_df["salary"]):
            plt.text(index, value, f"{value:.1f}", ha="center", va="bottom")
        figs.append(save_plot_to_base64())

    return {"text_output": text_output, "figures": figs}
