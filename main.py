import os
import pickle
import psycopg2
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_PATH = os.getenv("MODEL_PATH", "model_with_threshold.pkl")

DB_HOST = os.getenv("DB_HOST", "postgres")
DB_NAME = os.getenv("DB_NAME", "mydb")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASSWORD = os.getenv("DB_PASSWORD", "123456")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

try:
    with open(MODEL_PATH, "rb") as f:
        data = pickle.load(f)
        model_loaded = data["model"]
        threshold = data["threshold"]
except Exception as e:
    print(f"Lỗi khi tải mô hình: {e}")
    model_loaded = None
    threshold = 0.5


class PatientData(BaseModel):
    Pregnancies: float
    Glucose: float
    BloodPressure: float
    BMI: float
    DiabetesPedigreeFunction: float
    Age: float


def save_to_sql(data: PatientData, prediction: int):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            port=DB_PORT
        )
        cursor = conn.cursor()

        insert_query = """
            INSERT INTO diabetes_table
            (pregnancies, glucose, bloodpressure, bmi, diabetespedigreefunction, age, outcome)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        record_to_insert = (
            data.Pregnancies, data.Glucose, data.BloodPressure,
            data.BMI, data.DiabetesPedigreeFunction, data.Age, prediction
        )

        cursor.execute(insert_query, record_to_insert)
        conn.commit()

    except Exception as e:
        raise Exception(f"Lỗi Database: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.post("/predict")
def predict_and_save(data: PatientData):
    try:
        if model_loaded is None:
            raise Exception("Model chưa được load thành công")

        X_test = np.array([[
            data.Pregnancies, data.Glucose, data.BloodPressure,
            data.BMI, data.DiabetesPedigreeFunction, data.Age
        ]])

        if hasattr(model_loaded, "predict_proba"):
            probabilities = model_loaded.predict_proba(X_test)
            prob_positive = probabilities[0][1]
            y_pred = 1 if prob_positive >= threshold else 0
        else:
            y_pred = int(model_loaded.predict(X_test)[0])

        save_to_sql(data, y_pred)

        return {
            "status": "success",
            "prediction": y_pred,
            "message": "Đã lưu vào Database thành công!"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))