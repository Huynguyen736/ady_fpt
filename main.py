from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pickle
import psycopg2
import numpy as np
import pandas as pd
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Tải Model và Threshold
try:
    with open("model_with_threshold.pkl", "rb") as f:
        data = pickle.load(f)
        model_loaded = data["model"]
        threshold = data["threshold"]
        scaler_loaded = data.get("scaler")
except Exception as e:
    print(f"Lỗi khi tải mô hình: {e}")
    model_loaded = None
    threshold = 0.5  # fallback
    scaler_loaded = None

# 2. Khai báo cấu trúc dữ liệu
# Lưu ý: Tên biến ở đây PHẢI khớp chính xác 100% với key trong file JSON/Frontend gửi lên
class PatientData(BaseModel):
    Pregnancies: float
    Glucose: float
    BloodPressure: float
    BMI: float
    DiabetesPedigreeFunction: float  # Đã chuẩn hóa tên
    Age: float


def _normalize_feature_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _align_input_to_target_columns(input_row: dict, target_columns: list[str]) -> pd.DataFrame:
    """Map input fields to target feature names without introducing NaN values."""
    normalized_input = {_normalize_feature_name(k): v for k, v in input_row.items()}
    aligned_data = {}
    missing_columns = []

    for col in target_columns:
        if col in input_row:
            aligned_data[col] = input_row[col]
            continue

        norm_col = _normalize_feature_name(col)
        if norm_col in normalized_input:
            aligned_data[col] = normalized_input[norm_col]
        else:
            missing_columns.append(col)

    if missing_columns:
        raise HTTPException(
            status_code=422,
            detail=f"Thiếu dữ liệu cho các cột đặc trưng: {missing_columns}"
        )

    return pd.DataFrame([aligned_data], columns=target_columns)


def _model_has_internal_scaler(model) -> bool:
    """Detect if model is a sklearn Pipeline that already contains a StandardScaler step."""
    if not hasattr(model, "named_steps"):
        return False

    for step in model.named_steps.values():
        if step.__class__.__name__ == "StandardScaler":
            return True
    return False


@app.get("/")
def health_check():
    return {
        "status": "ok",
        "message": "Diabetes prediction API is running",
        "model_loaded": model_loaded is not None,
        "scaler_loaded": scaler_loaded is not None
    }

# 3. Hàm kết nối và lưu vào SQL
def save_to_sql(data: PatientData, prediction: int):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(
            host="192.168.1.104",
            database="mydb",
            user="admin",
            password="123456",
            port=5432
        )
        cursor = conn.cursor()
        
        # BỎ cột 'id' khỏi câu lệnh INSERT. Database sẽ tự lo việc tăng số.
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

# 4. API Endpoint
@app.post("/predict")
def predict_and_save(data: PatientData):
    try:
        if model_loaded is None:
            raise Exception("Model chưa được tải thành công")

        input_row = {
            "Pregnancies": data.Pregnancies,
            "Glucose": data.Glucose,
            "BloodPressure": data.BloodPressure,
            "BMI": data.BMI,
            "DiabetesPedigreeFunction": data.DiabetesPedigreeFunction,
            "Age": data.Age,
        }

        default_feature_names = [
            "Pregnancies", "Glucose", "BloodPressure", "BMI", "DiabetesPedigreeFunction", "Age"
        ]

        # Giữ tên cột để tránh cảnh báo "X does not have valid feature names".
        model_feature_names = list(getattr(model_loaded, "feature_names_in_", default_feature_names))
        X_test_df = _align_input_to_target_columns(input_row, model_feature_names)

        # Chuẩn hóa dữ liệu đầu vào bằng scaler đã fit trong lúc train (nếu có).
        scaler_applied = False
        if scaler_loaded is not None:
            scaler_feature_names = list(getattr(scaler_loaded, "feature_names_in_", model_feature_names))
            X_for_scaler = _align_input_to_target_columns(input_row, scaler_feature_names)
            X_scaled = scaler_loaded.transform(X_for_scaler)
            scaler_applied = True

            # Sau khi scale, gắn lại tên cột nếu model có feature names.
            if hasattr(model_loaded, "feature_names_in_") and X_scaled.shape[1] == len(model_feature_names):
                X_for_model = pd.DataFrame(X_scaled, columns=model_feature_names)
            else:
                X_for_model = X_scaled
        elif _model_has_internal_scaler(model_loaded):
            # Model dạng Pipeline có StandardScaler bên trong, không cần scale ở ngoài.
            X_for_model = X_test_df
        else:
            raise HTTPException(
                status_code=500,
                detail="Chua tim thay scaler da fit. Hay luu scaler vao model_with_threshold.pkl voi key 'scaler'."
            )

        # Debug: in dữ liệu đưa vào model để theo dõi trên terminal.
        print("[Predict] Raw input:", X_test_df.to_dict(orient="records")[0], flush=True)
        print("[Predict] Scaler applied:", scaler_applied, flush=True)
        print("[Predict] Input before model:", flush=True)
        if hasattr(X_for_model, "to_dict"):
            print(X_for_model.to_dict(orient="records")[0], flush=True)
        else:
            print(np.asarray(X_for_model).tolist(), flush=True)
        
        # Sử dụng threshold để tính dự đoán (thay vì predict mặc định)
        if hasattr(model_loaded, "predict_proba"):
            probabilities = model_loaded.predict_proba(X_for_model)
            prob_positive = probabilities[0][1] # Xác suất bị tiểu đường
            y_pred = 1 if prob_positive >= threshold else 0
        else:
            # Fallback nếu model không hỗ trợ trả về xác suất
            y_pred = int(model_loaded.predict(X_for_model)[0])
        
        save_to_sql(data, y_pred)
        
        return {"status": "success", "prediction": y_pred, "message": "Đã lưu vào Database thành công!"}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# uvicorn main:app --reload