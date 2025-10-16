import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import joblib

# Load the dataset
data = pd.read_csv("./libraries/drone_flight_data_stable.csv")

# Compute orientation errors (assuming command columns exist or are zero if not provided)
data['roll_error'] = data['filtered_roll'] - data.get('roll_command', 0)
data['pitch_error'] = data['filtered_pitch'] - data.get('pitch_command', 0)
data['yaw_error'] = data['filtered_yaw'] - data.get('yaw_command', 0)

# Select features and targets
features = ['gyro_x', 'gyro_y', 'gyro_z', 'motor_fl_cmd', 'motor_fr_cmd', 'motor_rl_cmd', 'motor_rr_cmd', 'total_thrust', 'stability_index']
X = data[features].fillna(0)  # Handle missing values
y = data[['roll_error', 'pitch_error', 'yaw_error']]

# Scale the features
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Split the data
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)

# Train a Linear Regression model
model = LinearRegression()
model.fit(X_train, y_train)

# Save the model and scaler
joblib.dump(model, 'orientation_model.pkl')
joblib.dump(scaler, 'scaler.pkl')

print("Model and scaler saved as orientation_model.pkl and scaler.pkl")