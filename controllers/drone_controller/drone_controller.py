from controller import Robot, Camera, Compass, GPS, Gyro, InertialUnit, Keyboard, LED, Motor
import math
import time
import json
import socket
import os
import numpy as np
import pandas as pd
from threading import Thread
from queue import Queue

try:
    import joblib
    ML_AVAILABLE = True
    # print("✓ ML libraries loaded successfully")
except ImportError:
    ML_AVAILABLE = False
    # print("⚠️ ML libraries not available")

# Helper functions
def sign(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)

def clamp(value, low, high):
    return low if value < low else (high if value > high else value)

# BALANCED PARAMETERS FOR STABLE FLIGHT
MAX_ROLL_RATE = 0.3
MAX_PITCH_RATE = 0.3
MAX_YAW_RATE = 0.4
MOVEMENT_SMOOTHING = 0.85
STRAFE_POWER = 0.3
FORWARD_POWER = 0.3
YAW_POWER = 0.25

class TCPSender:
    def __init__(self, host='localhost', port=8766):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.connect()
    
    def connect(self):
        try:
            if self.socket:
                self.socket.close()
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            print("Connected to TCP server")
        except Exception as e:
            self.connected = False
            print(f"TCP connection error: {e}")

    def send(self, data):
        if not self.connected:
            self.connect()
        
        try:
            message = json.dumps(data) + '\n'
            self.socket.sendall(message.encode('utf-8'))
        except Exception as e:
            print(f"TCP send error: {e}")
            self.connected = False

class MLOrientationPredictor:
    def __init__(self):
        self.model = None
        self.scaler = None
        self.model_loaded = False
        self.feature_names = [
            'gyro_x', 'gyro_y', 'gyro_z',
            'motor_fl_cmd', 'motor_fr_cmd', 'motor_rl_cmd', 'motor_rr_cmd',
            'total_thrust', 'stability_index'
        ]
        self.load_model()
    
    def load_model(self):
        if not ML_AVAILABLE:
            print("⚠️ Cannot load ML model - libraries not available")
            return
            
        try:
            controller_dir = os.path.dirname(os.path.abspath(__file__))
            model_path = os.path.join(controller_dir, 'orientation_model.pkl')
            scaler_path = os.path.join(controller_dir, 'scaler.pkl')
            
            if os.path.exists(model_path) and os.path.exists(scaler_path):
                self.model = joblib.load(model_path)
                self.scaler = joblib.load(scaler_path)
                self.model_loaded = True
                print("✓ ML model and scaler loaded successfully")
            else:
                print(f"❌ Model files not found at {model_path}")
                
        except Exception as e:
            print(f"❌ Error loading ML model: {e}")
            self.model_loaded = False

    def predict(self, gyro_values, motor_velocities, stability_index):
        if not self.model_loaded:
            return [0.0, 0.0, 0.0]
            
        try:
            total_thrust = sum(abs(v) for v in motor_velocities)
            
            features = [
                gyro_values[0], gyro_values[1], gyro_values[2],
                motor_velocities[0], motor_velocities[1], motor_velocities[2], motor_velocities[3],
                total_thrust, stability_index
            ]
            
            feature_df = pd.DataFrame([features], columns=self.feature_names)
            scaled_features = self.scaler.transform(feature_df)
            predictions = self.model.predict(scaled_features)
            
            return predictions[0].tolist()
            
        except Exception as e:
            print(f"❌ Error in ML prediction: {e}")
            return [0.0, 0.0, 0.0]

class DroneController:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # Initialize devices
        self.camera = Camera("camera")
        self.camera.enable(self.timestep)
        self.front_left_led = LED("front left led")
        self.front_right_led = LED("front right led")
        self.imu = InertialUnit("inertial unit")
        self.imu.enable(self.timestep)
        self.gps = GPS("gps")
        self.gps.enable(self.timestep)
        self.compass = Compass("compass")
        self.compass.enable(self.timestep)
        self.gyro = Gyro("gyro")
        self.gyro.enable(self.timestep)
        self.keyboard = Keyboard()
        self.keyboard.enable(self.timestep)
        self.camera_roll_motor = Motor("camera roll")
        self.camera_pitch_motor = Motor("camera pitch")
        
        # Initialize motors with proper setup for flight
        self.motors = [
            Motor("front left propeller"),
            Motor("front right propeller"),
            Motor("rear left propeller"),
            Motor("rear right propeller")
        ]
        
        for motor in self.motors:
            motor.setPosition(float('inf'))
            motor.setVelocity(1.0)  # Start with minimal velocity
                
        # ML components
        self.ml_predictor = MLOrientationPredictor()
        self.tcp_sender = TCPSender()
        
        # TUNED PID PARAMETERS from working code
        self.k_vertical_thrust = 68.5
        self.k_vertical_offset = 0.6
        self.k_vertical_p = 2.5
        self.k_roll_p = 6.0
        self.k_pitch_p = 6.0
        self.k_yaw_p = 2.0
        self.k_roll_d = 3.0
        self.k_pitch_d = 3.0
        self.k_yaw_d = 2.0
        
        # Movement variables
        self.target_altitude = 1.0
        self.smooth_roll_cmd = 0.0
        self.smooth_pitch_cmd = 0.0
        self.smooth_yaw_cmd = 0.0
        
        # Filtering
        self.alpha = 0.9
        self.filtered_roll = 0.0
        self.filtered_pitch = 0.0
        self.filtered_yaw = 0.0
        self.filtered_gyro = [0.0, 0.0, 0.0]
        
        # PID integral terms
        self.roll_integral = 0.0
        self.pitch_integral = 0.0
        self.yaw_integral = 0.0
        self.integral_limit = 0.5
        self.integral_decay = 0.98
        
        # Wait for initialization
        print("Waiting for sensor initialization...")
        while self.robot.step(self.timestep) != -1:
            if self.robot.getTime() > 1.0:
                break
        
        print("🚁 DRONE CONTROLLER WITH ML INTEGRATION")
        print("🎮 CONTROL SCHEME:")
        print("Movement:")
        print("  ↑ UP ARROW    : Move Forward")
        print("  ↓ DOWN ARROW  : Move Backward") 
        print("  ← LEFT ARROW  : Strafe Left")
        print("  → RIGHT ARROW : Strafe Right")
        print("Rotation:")
        print("  A KEY         : Rotate Left")
        print("  D KEY         : Rotate Right")
        print("Altitude:")
        print("  W KEY         : Increase Altitude")
        print("  S KEY         : Decrease Altitude")
        print("  END KEY       : Stop\n")
        print("🟢 Drone ready! Starting ML-enhanced flight control...")
        
    def handle_keyboard_input(self):
        """Handle keyboard input for drone control - using working logic"""
        user_inputs = [0] * 8
        target_roll_cmd = 0.0
        target_pitch_cmd = 0.0
        target_yaw_cmd = 0.0
        user_yaw_input = False
        
        key = self.keyboard.getKey()
        
        while key > 0:
            if key == Keyboard.UP:
                target_pitch_cmd = -FORWARD_POWER
                user_inputs[0] = 1
            elif key == Keyboard.DOWN:
                target_pitch_cmd = FORWARD_POWER
                user_inputs[1] = 1
            elif key == Keyboard.LEFT:
                target_roll_cmd = -STRAFE_POWER
                user_inputs[2] = 1
            elif key == Keyboard.RIGHT:
                target_roll_cmd = STRAFE_POWER
                user_inputs[3] = 1
            elif key in (ord('A'), ord('a')):
                target_yaw_cmd = YAW_POWER
                user_inputs[4] = 1
                user_yaw_input = True
            elif key in (ord('D'), ord('d')):
                target_yaw_cmd = -YAW_POWER
                user_inputs[5] = 1
                user_yaw_input = True
            elif key in (ord('W'), ord('w')):
                self.target_altitude += 0.05
                user_inputs[6] = 1
                print(f"Target altitude: {self.target_altitude:.2f} m")
            elif key in (ord('S'), ord('s')):
                self.target_altitude -= 0.05
                self.target_altitude = max(self.target_altitude, 0.1)
                user_inputs[7] = 1
                print(f"Target altitude: {self.target_altitude:.2f} m")
            elif key == Keyboard.END:
                return None, user_inputs  # Signal to end
                
            key = self.keyboard.getKey()
        
        return (target_roll_cmd, target_pitch_cmd, target_yaw_cmd, user_yaw_input), user_inputs
    
    def update_motor_velocities(self, imu_values, gyro_values, altitude, dt):
        """Update motor velocities using working flight control logic"""
        roll, pitch, yaw = imu_values
        roll_velocity, pitch_velocity, yaw_velocity = gyro_values
        
        # Handle keyboard input
        input_result = self.handle_keyboard_input()
        if input_result[0] is None:  # END key pressed
            return None, [0] * 8
            
        (target_roll_cmd, target_pitch_cmd, target_yaw_cmd, user_yaw_input), user_inputs = input_result
        
        # Filtering
        self.filtered_roll = self.alpha * self.filtered_roll + (1 - self.alpha) * roll
        self.filtered_pitch = self.alpha * self.filtered_pitch + (1 - self.alpha) * pitch
        self.filtered_yaw = self.alpha * self.filtered_yaw + (1 - self.alpha) * yaw
        
        for i in range(3):
            self.filtered_gyro[i] = self.alpha * self.filtered_gyro[i] + (1 - self.alpha) * gyro_values[i]
        
        # LED control
        led_state = int(self.robot.getTime()) % 2
        self.front_left_led.set(led_state)
        self.front_right_led.set(1 if not led_state else 0)
        
        # Camera stabilization
        self.camera_roll_motor.setPosition(-0.03 * self.filtered_gyro[0])
        self.camera_pitch_motor.setPosition(-0.03 * self.filtered_gyro[1])
        
        # Movement smoothing
        self.smooth_roll_cmd = MOVEMENT_SMOOTHING * self.smooth_roll_cmd + (1.0 - MOVEMENT_SMOOTHING) * target_roll_cmd
        self.smooth_pitch_cmd = MOVEMENT_SMOOTHING * self.smooth_pitch_cmd + (1.0 - MOVEMENT_SMOOTHING) * target_pitch_cmd
        self.smooth_yaw_cmd = MOVEMENT_SMOOTHING * self.smooth_yaw_cmd + (1.0 - MOVEMENT_SMOOTHING) * target_yaw_cmd
        
        # Rate limiting
        self.smooth_roll_cmd = clamp(self.smooth_roll_cmd, -MAX_ROLL_RATE, MAX_ROLL_RATE)
        self.smooth_pitch_cmd = clamp(self.smooth_pitch_cmd, -MAX_PITCH_RATE, MAX_PITCH_RATE)
        self.smooth_yaw_cmd = clamp(self.smooth_yaw_cmd, -MAX_YAW_RATE, MAX_YAW_RATE)
        
        # PID control
        roll_error = self.filtered_roll
        pitch_error = self.filtered_pitch
        
        # Integral terms
        if abs(roll_error) > 0.05 or abs(target_roll_cmd) > 0.01:
            self.roll_integral = clamp(self.roll_integral + roll_error * dt, -self.integral_limit, self.integral_limit)
        else:
            self.roll_integral *= self.integral_decay
            
        if abs(pitch_error) > 0.05 or abs(target_pitch_cmd) > 0.01:
            self.pitch_integral = clamp(self.pitch_integral + pitch_error * dt, -self.integral_limit, self.integral_limit)
        else:
            self.pitch_integral *= self.integral_decay
        
        if user_yaw_input or abs(self.filtered_gyro[2]) > 0.1:
            self.yaw_integral = clamp(self.yaw_integral + self.filtered_gyro[2] * dt, -self.integral_limit, self.integral_limit)
        else:
            self.yaw_integral *= self.integral_decay
        
        # PID calculations
        roll_input = (self.k_roll_p * roll_error + self.k_roll_d * self.filtered_gyro[0] + 0.3 * self.roll_integral + self.smooth_roll_cmd)
        pitch_input = (self.k_pitch_p * pitch_error + self.k_pitch_d * self.filtered_gyro[1] + 0.3 * self.pitch_integral + self.smooth_pitch_cmd)
        
        if user_yaw_input:
            yaw_input = self.smooth_yaw_cmd + self.k_yaw_d * self.filtered_gyro[2]
        else:
            yaw_input = -self.k_yaw_p * self.filtered_gyro[2] - 0.2 * self.yaw_integral
        
        # Clamp control inputs
        roll_input = clamp(roll_input, -12.0, 12.0)
        pitch_input = clamp(pitch_input, -12.0, 12.0)
        yaw_input = clamp(yaw_input, -6.0, 6.0)
        
        # Altitude control
        altitude_error = self.target_altitude - altitude + self.k_vertical_offset
        clamped_altitude_error = clamp(altitude_error, -1.0, 1.0)
        vertical_input = self.k_vertical_p * (clamped_altitude_error ** 3.0)
        
        # Motor mixing
        front_left_motor_cmd = self.k_vertical_thrust + vertical_input - roll_input + pitch_input - yaw_input
        front_right_motor_cmd = self.k_vertical_thrust + vertical_input + roll_input + pitch_input + yaw_input
        rear_left_motor_cmd = self.k_vertical_thrust + vertical_input - roll_input - pitch_input + yaw_input
        rear_right_motor_cmd = self.k_vertical_thrust + vertical_input + roll_input - pitch_input - yaw_input
        
        # Clamp motor commands
        motor_commands = [front_left_motor_cmd, front_right_motor_cmd, rear_left_motor_cmd, rear_right_motor_cmd]
        for i in range(4):
            motor_commands[i] = clamp(motor_commands[i], 0.0, 600.0)
        
        # Apply motor commands with correct rotation directions
        self.motors[0].setVelocity(motor_commands[0])
        self.motors[1].setVelocity(-motor_commands[1])
        self.motors[2].setVelocity(-motor_commands[2])
        self.motors[3].setVelocity(motor_commands[3])
        
        return motor_commands, user_inputs
        
    def run(self):
        step_counter = 0
        print("Starting drone controller...")
        
        while self.robot.step(self.timestep) != -1:
            try:
                sim_time = self.robot.getTime()
                dt = self.timestep / 1000.0
                
                # Sensor readings
                imu_values = self.imu.getRollPitchYaw()
                roll, pitch, yaw = imu_values
                gyro_values = self.gyro.getValues()
                gps_values = self.gps.getValues()
                altitude = gps_values[2]
                
                # Update motor control
                motor_result = self.update_motor_velocities(imu_values, gyro_values, altitude, dt)
                if motor_result[0] is None:  # END key pressed
                    break
                    
                motor_velocities, user_inputs = motor_result
                
                # Calculate metrics
                total_thrust = sum(motor_velocities)
                stability_index = clamp(1.0 - ((abs(self.filtered_roll) + abs(self.filtered_pitch)) * 0.5), 0.0, 1.0)
                
                # ML predictions
                ml_errors = self.ml_predictor.predict(self.filtered_gyro, motor_velocities, stability_index)
                
                # Send data every 10 steps to reduce overhead
                if step_counter % 10 == 0:
                    data = {
                        "simulation_time": sim_time,
                        "altitude": altitude,
                        "filtered_roll": self.filtered_roll,
                        "filtered_pitch": self.filtered_pitch,
                        "filtered_yaw": self.filtered_yaw,
                        "stability_index": stability_index,
                        "ml_roll_error": ml_errors[0],
                        "ml_pitch_error": ml_errors[1],
                        "ml_yaw_error": ml_errors[2],
                        "gyro_x": self.filtered_gyro[0],
                        "gyro_y": self.filtered_gyro[1],
                        "gyro_z": self.filtered_gyro[2],
                        "target_altitude": self.target_altitude,
                        "motor_velocities": motor_velocities,
                        "total_thrust": total_thrust,
                        "user_inputs": user_inputs
                    }
                    self.tcp_sender.send(data)
                    
                    if step_counter % 100 == 0:  # Debug info every 100 steps
                        ml_info = f" | ML: Roll={ml_errors[0]:.3f}, Pitch={ml_errors[1]:.3f}" if self.ml_predictor.model_loaded else ""
                        print(f"📊 Time: {sim_time:.1f}s | Alt: {altitude:.2f}m | Roll: {self.filtered_roll * 57.3:.1f}° | Pitch: {self.filtered_pitch * 57.3:.1f}°{ml_info}")
                
                step_counter += 1
                
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(0.1)
        
        # Stop all motors when ending
        for motor in self.motors:
            motor.setVelocity(0.0)
        print("🛑 Drone controller stopped")

if __name__ == "__main__":
    controller = DroneController()
    controller.run()