import pandas as pd
from pymongo import MongoClient
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, confusion_matrix
import joblib, os
from dotenv import load_dotenv

# -------------------- Load env vars --------------------
load_dotenv()
MONGO_URI = os.getenv("MONGO_PY")
DB_NAME = os.getenv("DB_NAME", "employee_portal")
COLLECTION = os.getenv("COLLECTION_NAME", "associates")


# -------------------- Fetch Data --------------------
def fetch_data():
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION]
    data = list(collection.find({}, {"_id": 0}))
    df = pd.DataFrame(data) if data else pd.DataFrame()

    if not df.empty:
        # Create "terminated" column based on employment_status
        if "employment_status" in df.columns:
            df["terminated"] = df["employment_status"].apply(
                lambda x: 0 if str(x).strip().lower() == "active" else 1
            )

    return df


# -------------------- Preprocessing --------------------
def preprocess(df):
    # Drop identifiers and date columns (not useful for prediction)
    drop_cols = [
        "associate_id",
        "associate_name",
        "dob",
        "dateofhire",
        "LastPerformanceReview_Date",
    ]
    df = df.drop([c for c in drop_cols if c in df.columns], axis=1, errors="ignore")

    # Ensure target exists
    if "terminated" not in df.columns:
        raise ValueError("⚠ No 'terminated' column found in dataset!")

    # Convert categorical features to dummies
    df = pd.get_dummies(df, drop_first=True)

    # Split features and target
    X = df.drop("terminated", axis=1)
    y = df["terminated"].astype(int)  # make sure it's int (0 or 1)

    return X, y


# -------------------- Train Model --------------------
def train_model():
    df = fetch_data()
    if df.empty:
        raise ValueError("⚠ No data found in MongoDB!")

    X, y = preprocess(df)

    # Check class distribution
    class_counts = y.value_counts()
    print("ℹ Class distribution:\n", class_counts)

    if len(class_counts) < 2 or class_counts.min() < 2:
        print("⚠ Not enough data to train a reliable model.")
        print("  Each class should have at least 2 samples.")
        print(
            "  Training will proceed on full dataset without test split (overfitting likely)."
        )
        # Scale full dataset
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = LogisticRegression(max_iter=2000)
        model.fit(X_scaled, y)

        # Save model, scaler, and features
        joblib.dump(model, "attrition_model.pkl")
        joblib.dump(scaler, "scaler.pkl")
        joblib.dump(list(X.columns), "features.pkl")

        print("✅ Model trained on full dataset (small dataset, overfitting expected).")
        return model, scaler

    # If enough data, do normal train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(max_iter=2000)
    model.fit(X_train_scaled, y_train)

    y_pred = model.predict(X_test_scaled)
    print("📊 Classification Report:\n", classification_report(y_test, y_pred))
    print("📉 Confusion Matrix:\n", confusion_matrix(y_test, y_pred))

    # Save model, scaler, and features
    joblib.dump(model, "attrition_model.pkl")
    joblib.dump(scaler, "scaler.pkl")
    joblib.dump(list(X.columns), "features.pkl")

    print("✅ Model trained and saved with train-test split.")
    return model, scaler


# -------------------- Predict for One Employee --------------------
def predict_employee(associate_name):
    df = fetch_data()
    if df.empty or "associate_name" not in df.columns:
        return None

    if associate_name not in df["associate_name"].values:
        return None

    # Keep raw copy for details
    emp_raw = df[df["associate_name"] == associate_name].copy()

    # Preprocess full dataset for consistent dummies/features
    X, y = preprocess(df)

    # Load model and metadata
    model = joblib.load("attrition_model.pkl")
    scaler = joblib.load("scaler.pkl")
    features = joblib.load("features.pkl")

    # Prepare employee row
    emp = emp_raw.copy()
    if "terminated" in emp.columns:
        emp = emp.drop("terminated", axis=1)  # only drop if present

    emp = pd.get_dummies(emp, drop_first=True)

    # Align with training features
    emp = emp.reindex(columns=features, fill_value=0)

    # Scale features
    emp_scaled = scaler.transform(emp)

    # Predict
    prediction = model.predict(emp_scaled)[0]
    proba = model.predict_proba(emp_scaled)[0][1]

    return {
        "name": associate_name,
        "prediction": "High Risk" if prediction == 1 else "Low Risk",
        "probability": round(proba * 100, 2),
        "details": emp_raw.to_dict(orient="records")[0],
    }
