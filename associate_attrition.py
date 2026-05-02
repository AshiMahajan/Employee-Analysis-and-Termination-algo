# import os
# import numpy as np
# import pandas as pd
# from dotenv import load_dotenv
# from pymongo import MongoClient
# import joblib

# from sklearn.model_selection import train_test_split
# from sklearn.impute import SimpleImputer
# from sklearn.preprocessing import StandardScaler, OneHotEncoder
# from sklearn.compose import ColumnTransformer
# from sklearn.pipeline import Pipeline
# # from sklearn.tree import DecisionTreeClassifier
# from sklearn.ensemble import RandomForestClassifier
# from sklearn.dummy import DummyClassifier
# from sklearn.metrics import classification_report, confusion_matrix

# load_dotenv()

# MONGO_URI     = os.getenv("MONGO_PY", "mongodb://localhost:27017/")
# DB_NAME       = os.getenv("DB_NAME", "employee_portal")
# COLLECTION    = os.getenv("COLLECTION_NAME", "associates")
# PIPELINE_PATH = os.getenv("ATTRITION_PIPELINE", "attrition_pipeline.pkl")
# FEATURES_PATH = os.getenv("ATTRITION_FEATURES", "features.pkl")

# TERMINATED_STATUSES = {
#     "voluntarily terminated",
#     "terminated for cause",
#     "terminated",
# }


# # ------------------ Fetch data ------------------
# def fetch_data():
#     client = MongoClient(MONGO_URI)
#     df = pd.DataFrame(list(client[DB_NAME][COLLECTION].find({}, {"_id": 0})))

#     if df.empty:
#         return df

#     if "employment_status" in df.columns:
#         def map_status(val):
#             if pd.isna(val):
#                 return np.nan
#             v = str(val).strip().lower()
#             if v == "active":
#                 return 0
#             elif v in TERMINATED_STATUSES:
#                 return 1
#             return np.nan

#         df["terminated"] = df["employment_status"].apply(map_status)

#     return df


# # ------------------ Helpers ------------------
# def infer_numeric_cols(X: pd.DataFrame):
#     numeric_cols = []
#     for c in X.columns:
#         coerced = pd.to_numeric(X[c], errors="coerce")
#         if coerced.notna().sum() >= max(1, len(X) // 2):
#             numeric_cols.append(c)
#     return numeric_cols


# def _cm_to_string(cm):
#     return "\n".join([", ".join(map(str, row)) for row in cm.tolist()])


# def _build_preprocessor(X: pd.DataFrame):
#     for col in X.columns:
#         try:
#             X[col] = pd.to_numeric(X[col])
#         except (ValueError, TypeError):
#             pass
#     numeric_cols     = infer_numeric_cols(X)
#     categorical_cols = [c for c in X.columns if c not in numeric_cols]

#     return ColumnTransformer(
#         transformers=[
#             ("num", Pipeline([
#                 ("imputer", SimpleImputer(strategy="median")),
#                 ("scaler",  StandardScaler()),
#             ]), numeric_cols),
#             ("cat", Pipeline([
#                 ("imputer", SimpleImputer(strategy="constant", fill_value="__MISSING__")),
#                 ("onehot",  OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
#             ]), categorical_cols),
#         ],
#         remainder="drop",
#         sparse_threshold=0,
#     )


# # ------------------ Train pipeline ------------------
# def train_model(force_retrain=False):
#     df = fetch_data()
#     if df.empty:
#         raise ValueError("No data found in MongoDB.")
#     if "terminated" not in df.columns:
#         raise ValueError("No 'terminated' column available.")

#     df.replace("", np.nan, inplace=True)

#     drop_cols = [
#         "associate_id", "associate_name", "dob", "dateofhire",
#         "LastPerformanceReview_Date", "last_review",
#         "employment_status",   # derived into 'terminated'
#         "termination_reason",  # leaks the target
#     ]
#     X_full = df.drop([c for c in drop_cols if c in df.columns], axis=1).copy()
#     y_full = pd.to_numeric(df["terminated"], errors="coerce")

#     mask   = y_full.notna()
#     X_full = X_full.loc[mask].copy()
#     y_full = y_full.loc[mask]

#     # also drop 'terminated' from X if it slipped through
#     if "terminated" in X_full.columns:
#         X_full = X_full.drop(columns=["terminated"])

#     if X_full.empty:
#         raise ValueError("No valid rows after removing missing target.")

#     class_counts = y_full.value_counts()
#     print("Class distribution:\n", class_counts.to_dict())

#     preprocessor = _build_preprocessor(X_full.copy())

#     # Only one class → DummyClassifier
#     if len(class_counts) < 2:
#         print("⚠ Only one class — need both Active and Terminated employees to train.")
#         pipeline = Pipeline([("pre", preprocessor), ("clf", DummyClassifier(strategy="most_frequent"))])
#         pipeline.fit(X_full, y_full)
#         joblib.dump(pipeline, PIPELINE_PATH)
#         joblib.dump(list(X_full.columns), FEATURES_PATH)
#         return pipeline, preprocessor

#     # Small dataset → train on full data, no split
#     if len(X_full) < 30 or class_counts.min() < 5:
#         print("⚠ Small dataset — training on full data (no test split).")
#         pipeline = Pipeline([
#             ("pre", preprocessor),
#             ("clf", RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced")),
#         ])
#         pipeline.fit(X_full, y_full)
#         joblib.dump(pipeline, PIPELINE_PATH)
#         joblib.dump(list(X_full.columns), FEATURES_PATH)
#         return pipeline, preprocessor

#     # Normal train/test split
#     X_train, X_test, y_train, y_test = train_test_split(
#         X_full, y_full, test_size=0.25, random_state=42, stratify=y_full
#     )
#     pipeline = Pipeline([
#         ("pre", preprocessor),
#         ("clf", RandomForestClassifier(n_estimators=100, random_state=42, class_weight="balanced", max_depth=6, min_samples_split=5, min_samples_leaf=2)),
#     ])
#     pipeline.fit(X_train, y_train)
#     y_pred = pipeline.predict(X_test)
#     print("Classification Report:\n", classification_report(y_test, y_pred))
#     print("Confusion Matrix:\n", _cm_to_string(confusion_matrix(y_test, y_pred)))

#     joblib.dump(pipeline, PIPELINE_PATH)
#     joblib.dump(list(X_full.columns), FEATURES_PATH)
#     print(f"Saved pipeline → {PIPELINE_PATH}")
#     return pipeline, preprocessor


# # ------------------ Predict single employee ------------------
# def predict_employee(associate_name, retrain_if_missing=True):
#     df = fetch_data()
#     if df.empty or "associate_name" not in df.columns:
#         return None
#     if associate_name not in df["associate_name"].values:
#         return None

#     emp_series = df[df["associate_name"] == associate_name].iloc[0]
#     emp_raw    = emp_series.to_dict()

#     # If already terminated — no need to predict, just report it
#     terminated_val = emp_series.get("terminated", np.nan)
#     if pd.notna(terminated_val) and int(terminated_val) == 1:
#         return {
#             "name":             associate_name,
#             "prediction":       "Already Terminated",
#             "probability":      None,
#             "details":          emp_raw,
#             "numeric_insights": [],
#         }

#     # Load or train pipeline
#     if not os.path.exists(PIPELINE_PATH) or not os.path.exists(FEATURES_PATH):
#         if retrain_if_missing:
#             train_model()
#         else:
#             return None

#     pipeline = joblib.load(PIPELINE_PATH)
#     features = joblib.load(FEATURES_PATH)

#     # Build single-row DataFrame for prediction
#     emp_df = pd.DataFrame([emp_series])
#     drop_for_pred = ["terminated", "employment_status", "termination_reason"]
#     emp_df = emp_df.drop(columns=[c for c in drop_for_pred if c in emp_df.columns])
#     emp_df = emp_df.reindex(columns=features, fill_value=np.nan)

#     try:
#         proba = None
#         if hasattr(pipeline, "predict_proba"):
#             proba_val = pipeline.predict_proba(emp_df)[0]
#             proba     = float(proba_val[1]) if proba_val.shape[0] > 1 else float(proba_val[0])
#         proba_val = pipeline.predict_proba(emp_df)[0]
#         proba = float(proba_val[1]) if proba_val.shape[0] > 1 else float(proba_val[0])
#         prediction = 1 if proba >= 0.39 else 0
#     except Exception as e:
#         raise RuntimeError(f"Prediction failed: {e}")

#     # Numeric insights vs company median
#     all_df           = fetch_data()
#     numeric_insights = []
#     for col in emp_df.columns:
#         try:
#             col_numeric = pd.to_numeric(all_df[col], errors="coerce")
#             if col_numeric.notna().sum() == 0:
#                 continue
#             emp_val = float(pd.to_numeric(emp_df.iloc[0][col], errors="coerce"))
#             if np.isnan(emp_val):
#                 continue
#             med = float(col_numeric.median())
#             numeric_insights.append({
#                 "field":          col,
#                 "employee":       emp_val,
#                 "company_median": med,
#                 "diff":           emp_val - med,
#             })
#         except Exception:
#             continue

#     return {
#         "name":             associate_name,
#         "prediction":       "High Risk" if prediction == 1 else "Low Risk",
#         "probability":      round(proba * 100, 2) if proba is not None else None,
#         "details":          emp_raw,
#         "numeric_insights": sorted(numeric_insights, key=lambda x: abs(x["diff"]), reverse=True)[:8],
#     }


# if __name__ == "__main__":
#     print("Training attrition pipeline...")
#     train_model(force_retrain=True)
#     print("Done.")

import os
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
import joblib

from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import classification_report, confusion_matrix

load_dotenv()


MONGO_URI = os.getenv("MONGO_PY", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "employee_portal")
COLLECTION = os.getenv("COLLECTION_NAME", "associates")

PIPELINE_PATH = "attrition_pipeline.pkl"
FEATURES_PATH = "features.pkl"


TERMINATED_STATUSES = {"voluntarily terminated", "terminated for cause", "terminated"}


# ================= FETCH DATA =================


def fetch_data():

    client = MongoClient(MONGO_URI)

    df = pd.DataFrame(list(client[DB_NAME][COLLECTION].find({}, {"_id": 0})))

    if df.empty:
        return df

    df.replace("", np.nan, inplace=True)

    # normalize strings

    df = df.map(lambda x: str(x).strip() if isinstance(x, str) else x)

    def map_status(val):

        if pd.isna(val):
            return np.nan

        v = str(val).lower()

        if v == "active":
            return 0

        if v in TERMINATED_STATUSES:
            return 1

        return np.nan

    df["terminated"] = df["employment_status"].apply(map_status)

    return df


# ================= FEATURE ENGINEERING =================


def engineer_features(df):

    today = pd.Timestamp.today()

    if "dob" in df.columns:

        df["age"] = (today - pd.to_datetime(df["dob"], errors="coerce")).dt.days / 365

    if "dateofhire" in df.columns:
        df["years_at_company"] = (
            today - pd.to_datetime(df["dateofhire"], errors="coerce")
        ).dt.days / 365

    df["years_at_company"] = df["years_at_company"].clip(lower=0)
    df["attendance_risk"] = pd.to_numeric(df.get("days_late"), errors="coerce").fillna(
        0
    ) + pd.to_numeric(df.get("absences"), errors="coerce").fillna(0)

    df["disengagement_score"] = (
        (5 - pd.to_numeric(df.get("engagement_score"), errors="coerce").fillna(0))
        + (
            5
            - pd.to_numeric(df.get("employee_satisfaction"), errors="coerce").fillna(0)
        )
        + df["attendance_risk"]
    )

    return df


# ================= PREPROCESSOR =================


def build_preprocessor(X):

    numeric_cols = []
    categorical_cols = []

    for col in X.columns:

        try:
            X[col] = pd.to_numeric(X[col])
            numeric_cols.append(col)

        except:
            X[col] = X[col].fillna("__MISSING__").astype(str)
            categorical_cols.append(col)

    return ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), numeric_cols),
            (
                "cat",
                Pipeline(
                    [
                        (
                            "imputer",
                            SimpleImputer(
                                strategy="constant", fill_value="__MISSING__"
                            ),
                        ),
                        (
                            "onehot",
                            OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                        ),
                    ]
                ),
                categorical_cols,
            ),
        ]
    )


# ================= TRAIN MODEL =================


def train_model(force_retrain=False):

    if (
        os.path.exists(PIPELINE_PATH)
        and os.path.exists(FEATURES_PATH)
        and not force_retrain
    ):
        return joblib.load(PIPELINE_PATH)

    df = fetch_data()

    if df.empty:
        raise ValueError("MongoDB dataset empty")

    df = engineer_features(df)

    drop_cols = [
        "associate_id",
        "associate_name",
        "zip",
        "dob",
        "dateofhire",
        "last_review",
        "employment_status",
        "termination_reason",
    ]

    X_full = df.drop([c for c in drop_cols if c in df.columns], axis=1)

    y_full = pd.to_numeric(df["terminated"], errors="coerce")

    mask = y_full.notna()

    X_full = X_full.loc[mask]

    y_full = y_full.loc[mask]

    if "terminated" in X_full.columns:
        X_full = X_full.drop(columns=["terminated"])

    print("Class distribution:", y_full.value_counts().to_dict())

    preprocessor = build_preprocessor(X_full.copy())

    if len(y_full.unique()) < 2:

        print("Only one class → DummyClassifier used")

        pipeline = Pipeline(
            [("pre", preprocessor), ("clf", DummyClassifier(strategy="most_frequent"))]
        )

        pipeline.fit(X_full, y_full)

        joblib.dump(pipeline, PIPELINE_PATH)
        joblib.dump(list(X_full.columns), FEATURES_PATH)

        return pipeline

    X_train, X_test, y_train, y_test = train_test_split(
        X_full, y_full, test_size=0.25, stratify=y_full, random_state=42
    )

    pipeline = Pipeline(
        [
            ("pre", preprocessor),
            (
                "clf",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=12,
                    min_samples_split=4,
                    min_samples_leaf=2,
                    class_weight={0: 1, 1: 2},
                    random_state=42,
                ),
            ),
        ]
    )

    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)

    print(classification_report(y_test, y_pred))
    print(confusion_matrix(y_test, y_pred))

    joblib.dump(pipeline, PIPELINE_PATH)
    joblib.dump(list(X_full.columns), FEATURES_PATH)

    print("Pipeline saved successfully")

    return pipeline


# ================= PREDICT EMPLOYEE =================


def predict_employee(associate_name):

    df = fetch_data()

    df = engineer_features(df)

    if associate_name not in df["associate_name"].values:
        return None

    emp_series = df[df["associate_name"] == associate_name].iloc[0]

    if emp_series["terminated"] == 1:

        return {
            "prediction": "Already Terminated",
            "probability": None,
            "details": emp_series.to_dict(),
            "numeric_insights": [],
        }

    if not os.path.exists(PIPELINE_PATH):
        train_model()

    pipeline = joblib.load(PIPELINE_PATH)

    features = joblib.load(FEATURES_PATH)

    emp_df = pd.DataFrame([emp_series])

    emp_df = emp_df.drop(
        columns=[
            c
            for c in ["terminated", "employment_status", "termination_reason"]
            if c in emp_df.columns
        ]
    )

    emp_df = emp_df.reindex(columns=features, fill_value=np.nan)
    hide_from_insights = {"age", "manager_id", "department_id", "years_at_company"}

    proba = pipeline.predict_proba(emp_df)[0][1]

    prediction = pipeline.predict(emp_df)[0]

    numeric_insights = []

    for col in emp_df.columns:

        try:

            col_numeric = pd.to_numeric(df[col], errors="coerce")

            if col_numeric.notna().sum() == 0:
                continue

            emp_val = float(pd.to_numeric(emp_df.iloc[0][col], errors="coerce"))

            if np.isnan(emp_val):
                continue

            med = float(col_numeric.median())

            numeric_insights.append(
                {
                    "field": col,
                    "employee": emp_val,
                    "company_median": med,
                    "diff": emp_val - med,
                }
            )

        except:
            continue

    return {
        "prediction": "High Risk" if prediction == 1 else "Low Risk",
        "probability": round(proba * 100, 2),
        "details": emp_series.to_dict(),
        "numeric_insights": [
            x
            for x in sorted(
                numeric_insights, key=lambda x: abs(x["diff"]), reverse=True
            )
            if x["field"] not in hide_from_insights
        ][:8],
    }


if __name__ == "__main__":

    print("Training attrition pipeline...")

    train_model(force_retrain=True)

    print("Done.")
