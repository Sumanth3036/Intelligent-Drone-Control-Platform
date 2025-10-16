import serial
import requests
import time
import re

# Replace with your ThingSpeak Write API Key
THINGSPEAK_API_KEY = 'TS9K2POI0R8REDXJ'
THINGSPEAK_URL = 'https://api.thingspeak.com/update'

# COM port and baud rate
SERIAL_PORT = 'COM5'  # Change this to match your Arduino port
BAUD_RATE = 9600

def parse_serial_line(line):
    """Parse the serial line using regex for more robust extraction"""
    try:
        # Use regex to extract values more reliably
        pitch_match = re.search(r'Pitch:\s*([-+]?\d*\.?\d+)', line)
        roll_match = re.search(r'Roll:\s*([-+]?\d*\.?\d+)', line)
        throttle_l_match = re.search(r'Throttle L:\s*(\d+)', line)
        throttle_r_match = re.search(r'Throttle R:\s*(\d+)', line)
        current_match = re.search(r'Current:\s*([-+]?\d*\.?\d+)', line)
        
        if all([pitch_match, roll_match, throttle_l_match, throttle_r_match, current_match]):
            pitch = float(pitch_match.group(1))
            roll = float(roll_match.group(1))
            throttleL = int(throttle_l_match.group(1))
            throttleR = int(throttle_r_match.group(1))
            current = float(current_match.group(1))
            
            return pitch, roll, throttleL, throttleR, current
        else:
            return None
            
    except Exception as e:
        print(f"⚠️ Error parsing line: {e}")
        return None

# Open serial connection with error handling
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Wait for Arduino to reboot
    print(f"✅ Connected to {SERIAL_PORT} at {BAUD_RATE} baud")
except serial.SerialException as e:
    print(f"❌ Failed to connect to serial port: {e}")
    exit(1)

try:
    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            
            if line:  # Only process non-empty lines
                print("Raw Serial Line:", line)
                
                if "Pitch" in line and "Current" in line:
                    parsed_data = parse_serial_line(line)
                    
                    if parsed_data:
                        pitch, roll, throttleL, throttleR, current = parsed_data
                        print(f"📊 Parsed Data - Pitch: {pitch}, Roll: {roll}, L: {throttleL}, R: {throttleR}, Current: {current}")
                        
                        # Upload to ThingSpeak
                        payload = {
                            'api_key': THINGSPEAK_API_KEY,
                            'field1': pitch,
                            'field2': roll,
                            'field3': throttleL,
                            'field4': throttleR,
                            'field5': current
                        }
                        
                        try:
                            response = requests.post(THINGSPEAK_URL, data=payload, timeout=10)
                            if response.status_code == 200:
                                print("✅ ThingSpeak Upload Success:", response.status_code)
                            else:
                                print("⚠️ ThingSpeak Upload Warning:", response.status_code)
                        except requests.RequestException as e:
                            print(f"❌ ThingSpeak Upload Failed: {e}")
                        
                        time.sleep(15)  # Respect ThingSpeak free rate limit
                    else:
                        print("⚠️ Failed to parse data from line")
                        
        except UnicodeDecodeError as e:
            print(f"⚠️ Unicode decode error: {e}")
        except Exception as e:
            print(f"⚠️ Unexpected error in main loop: {e}")
            time.sleep(1)  # Small delay before retrying
            
except KeyboardInterrupt:
    print("\n🛑 Stopped by user")
except Exception as e:
    print(f"❌ Fatal error: {e}")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("🔌 Serial connection closed")