# associate_attrition.py
import os
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
import joblib

from sklearn.model_selection import train_test_split
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeClassifier
from sklearn.dummy import DummyClassifier
from sklearn.metrics import classification_report, confusion_matrix

load_dotenv()

MONGO_URI = os.getenv("MONGO_PY", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "employee_portal")
COLLECTION = os.getenv("COLLECTION_NAME", "associates")

# files to persist
PIPELINE_PATH = os.getenv("ATTRITION_PIPELINE", "attrition_pipeline.pkl")
FEATURES_PATH = os.getenv("ATTRITION_FEATURES", "features.pkl")


# ------------------ Fetch data ------------------
def fetch_data():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    coll = db[COLLECTION]
    data = list(coll.find({}, {"_id": 0}))
    df = pd.DataFrame(data) if data else pd.DataFrame()

    # create 'terminated' if employment_status exists and terminated missing
    if (
        not df.empty
        and "terminated" not in df.columns
        and "employment_status" in df.columns
    ):
        df["terminated"] = (
            df["employment_status"]
            .apply(lambda x: 0 if str(x).strip().lower() == "active" else 1)
            .astype(int)
        )

    return df


# ------------------ Helpers ------------------
def infer_numeric_cols(X: pd.DataFrame):
    """Heuristically find numeric columns: if coercion to numeric gives >50% non-null then treat as numeric."""
    numeric_cols = []
    for c in X.columns:
        coerced = pd.to_numeric(X[c], errors="coerce")
        non_null = coerced.notna().sum()
        if non_null >= max(1, (len(X) // 2)):  # at least half values numeric
            numeric_cols.append(c)
    return numeric_cols


# ------------------ Train pipeline ------------------
def train_model(force_retrain=False):
    """
    Train a preprocessing + DecisionTree pipeline and save it.
    - If the data is too small or only one class present, behaves safely:
       * Only-one-class -> DummyClassifier (most frequent)
       * Small dataset -> train on full dataset (no test split), but still save pipeline
    """
    df = fetch_data()
    if df.empty:
        raise ValueError("No data found in MongoDB to train on.")

    if "terminated" not in df.columns:
        raise ValueError("No 'terminated' column available to train on.")

    # Drop identifier / date columns that shouldn't be model inputs
    drop_cols = [
        "associate_id",
        "associate_name",
        "dob",
        "dateofhire",
        "LastPerformanceReview_Date",
        "last_review",
    ]
    X_full = df.drop(
        [c for c in drop_cols if c in df.columns], axis=1, errors="ignore"
    ).copy()
    y_full = df["terminated"].astype(int)

    # Remove rows where target is missing
    mask = y_full.notna()
    X_full = X_full.loc[mask]
    y_full = y_full.loc[mask]

    if X_full.empty or y_full.empty:
        raise ValueError("No valid rows after removing missing target.")

    class_counts = y_full.value_counts()
    print("Class distribution:\n", class_counts.to_dict())

    # Determine numeric/categorical columns
    numeric_cols = infer_numeric_cols(X_full)
    categorical_cols = [c for c in X_full.columns if c not in numeric_cols]

    # Build preprocessing pipelines
    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="constant", fill_value="__MISSING__")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, numeric_cols),
            ("cat", categorical_pipeline, categorical_cols),
        ],
        remainder="drop",
        sparse_threshold=0,
    )

    # Decide classifier
    if len(class_counts) < 2:
        print("⚠ Only one class in target. Using DummyClassifier (most frequent).")
        clf = DummyClassifier(strategy="most_frequent")
        pipeline = Pipeline([("pre", preprocessor), ("clf", clf)])
        pipeline.fit(X_full, y_full)
        # Save pipeline and feature list (original feature names before preprocessing)
        joblib.dump(pipeline, PIPELINE_PATH)
        joblib.dump(list(X_full.columns), FEATURES_PATH)
        print(f"Saved pipeline to {PIPELINE_PATH} (dummy classifier).")
        return pipeline, preprocessor

    # If dataset is small (few samples or class min count small) skip test split
    small_data = len(X_full) < 30 or class_counts.min() < 5
    if small_data:
        print(
            "⚠ Small dataset detected. Training on full dataset (no test split). Overfitting likely."
        )
        clf = DecisionTreeClassifier(random_state=42, class_weight="balanced")
        pipeline = Pipeline([("pre", preprocessor), ("clf", clf)])
        pipeline.fit(X_full, y_full)
        joblib.dump(pipeline, PIPELINE_PATH)
        joblib.dump(list(X_full.columns), FEATURES_PATH)
        print(f"Saved pipeline to {PIPELINE_PATH} (trained on full data).")
        return pipeline, preprocessor

    # Enough data -> do train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X_full, y_full, test_size=0.25, random_state=42, stratify=y_full
    )

    clf = DecisionTreeClassifier(random_state=42, class_weight="balanced")
    pipeline = Pipeline([("pre", preprocessor), ("clf", clf)])

    pipeline.fit(X_train, y_train)

    # Evaluate
    y_pred = pipeline.predict(X_test)
    print("Classification Report:\n", classification_report(y_test, y_pred))
    print(
        "Confusion Matrix:\n",
        classification_matrix_to_string(confusion_matrix(y_test, y_pred)),
    )

    joblib.dump(pipeline, PIPELINE_PATH)
    joblib.dump(list(X_full.columns), FEATURES_PATH)

    print(f"Saved pipeline to {PIPELINE_PATH} with features list in {FEATURES_PATH}")
    return pipeline, preprocessor


def classification_matrix_to_string(cm):
    return "\n".join([", ".join(map(str, row)) for row in cm.tolist()])


# ------------------ Predict single employee ------------------
def predict_employee(associate_name, retrain_if_missing=True):
    """
    Return dict with:
      - name
      - prediction ("High Risk" or "Low Risk")
      - probability (percent)
      - details: raw DB row as dict
      - numeric_insights: list of (field, emp_value, company_median, diff)
    """
    df = fetch_data()
    if df.empty or "associate_name" not in df.columns:
        return None

    if associate_name not in df["associate_name"].values:
        return None

    # train pipeline if missing
    if not os.path.exists(PIPELINE_PATH) or not os.path.exists(FEATURES_PATH):
        if retrain_if_missing:
            try:
                train_model()
            except Exception as e:
                raise RuntimeError(f"Failed to train model: {e}")
        else:
            return None

    pipeline = joblib.load(PIPELINE_PATH)
    features = joblib.load(FEATURES_PATH)

    # employee raw and processed row
    emp_raw = df[df["associate_name"] == associate_name].iloc[0].to_dict()
    emp_df = pd.DataFrame([df[df["associate_name"] == associate_name].iloc[0]])

    # if 'terminated' present drop it for prediction
    if "terminated" in emp_df.columns:
        emp_df = emp_df.drop(columns=["terminated"])

    # Align employee to training features (original columns before preprocessing)
    emp_df = emp_df.reindex(columns=features, fill_value=np.nan)

    # Predict
    try:
        proba = None
        if hasattr(pipeline, "predict_proba"):
            proba_val = pipeline.predict_proba(emp_df)[0]
            # probability of class 1 (terminated)
            # if only one class in pipeline (dummy), predict_proba still exists and will give single column
            if proba_val.shape[0] == 1:
                proba = float(proba_val[0])
            else:
                proba = float(proba_val[1])
        prediction = pipeline.predict(emp_df)[0]
    except Exception as e:
        raise RuntimeError(f"Prediction failed: {e}")

    # numeric insights versus company median
    # we compute medians from the training dataset (fetch_data)
    all_df = fetch_data()
    # compute company medians for numeric columns
    candidate_numeric_cols = []
    for c in emp_df.columns:
        try:
            col_series = pd.to_numeric(all_df[c], errors="coerce")
            if col_series.notna().sum() > 0:
                candidate_numeric_cols.append(c)
        except Exception:
            continue

    numeric_insights = []
    if candidate_numeric_cols:
        company_medians = (
            all_df[candidate_numeric_cols]
            .apply(pd.to_numeric, errors="coerce")
            .median(numeric_only=True)
        )
        for col in candidate_numeric_cols:
            try:
                emp_val = float(pd.to_numeric(emp_df.iloc[0][col], errors="coerce"))
                med = (
                    float(company_medians[col])
                    if not np.isnan(company_medians[col])
                    else 0.0
                )
                diff = emp_val - med
                numeric_insights.append(
                    {
                        "field": col,
                        "employee": emp_val,
                        "company_median": med,
                        "diff": diff,
                    }
                )
            except Exception:
                continue

    return {
        "name": associate_name,
        "prediction": "High Risk" if int(prediction) == 1 else "Low Risk",
        "probability": round(proba * 100, 2) if proba is not None else None,
        "details": emp_raw,
        "numeric_insights": sorted(
            numeric_insights, key=lambda x: abs(x["diff"]), reverse=True
        )[:8],
    }
