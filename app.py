from flask import Flask, render_template, redirect, request, session, url_for, send_file, flash, jsonify
import face_recognition
import cv2
import os
import pickle
from datetime import datetime, timedelta, date
import numpy as np
import csv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import base64
from PIL import Image
from dotenv import load_dotenv
import json
from google.oauth2.service_account import Credentials

load_dotenv()


credential_json = os.getenv("GOOGLE_CREDENTIALS_JSON")


app = Flask(__name__)
app.secret_key = 'secret'  # Required for sessions

ENCODINGS_FILE = 'face_encodings.pkl'
IMAGES_DIR = 'images'

# Google Sheets setup
# SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# CREDS = ServiceAccountCredentials.from_json_keyfile_name('attendance-sheets-credentials.json', SCOPE)
# CLIENT = gspread.authorize(CREDS)

# Google Sheets setup
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# CREDS = ServiceAccountCredentials.from_json_keyfile_name('attendance-sheets-credentials.json', SCOPE)
if not credential_json:
    raise ValueError("GOOGLE_CREDENTIALS environment variable is not set or empty")


credential_dict=json.loads(credential_json)
    
CREDS = Credentials.from_service_account_info(credential_dict , scopes = SCOPE)
CLIENT = gspread.authorize(CREDS)

ALL_SHEET = CLIENT.open("Attendance_All").sheet1

import subprocess
import platform
import sys
from dotenv import load_dotenv
import os
import requests

load_dotenv()  # Ensure your .env file is loaded

# Get allowed SSID from environment or fallback default
ALLOWED_SSID = "106.211.122.30"

# def get_connected_ssid():
#     system = platform.system()
#     print(system)
#     try:
#         if system == "Windows":
#             output = subprocess.check_output("netsh wlan show interfaces", shell=True).decode()
#             print(output)
#             for line in output.split("\n"):
#                 if "SSID" in line and "BSSID" not in line:
#                     return line.split(":")[1].strip()

#         elif system == "Darwin":  # macOS
#             airport_cmd = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
#             output = subprocess.check_output([airport_cmd, "-I"]).decode()
#             for line in output.split("\n"):
#                 if " SSID" in line:
#                     return line.split(":")[1].strip()

#         elif system == "Linux":
#             output = subprocess.check_output(["iwconfig"]).decode()
#             print(output)
#             for line in output.split("\n"):
#                 if line.startswith("yes:"):
#                     return line.split(":")[1]
#     except Exception as e:
#         print(f"[ERROR] Could not get Wi-Fi SSID: {e}")
#         return None

#     return None



def get_public_ip():
    try:
        response = requests.get('https://api.ipify.org?format=json')
        ip = response.json().get('ip')
        return ip
    except Exception as e:
        return f"Error fetching IP: {str(e)}"


# @app.before_request
# def check_wifi():
#     ssid = get_public_ip();
#     client_ip = request.headers.get('X-Forwarded-For')
    
#     if client_ip:
#         # The 'X-Forwarded-For' can contain multiple IPs if there are multiple proxies, 
#         # so we take the first one (which is usually the original client's IP).
#         client_ip = client_ip.split(',')[0]
#     else:
#         # If the header is not available, fall back to request.remote_addr
#         client_ip = request.remote_addr

#     print(f"Client IP: {client_ip}")
#     # return None
   

#     if client_ip != ALLOWED_SSID:
#         return "<h3>Access Denied: Connect to the authorized Wi-Fi network to access this site.</h3>", 403

def load_encodings():
    if os.path.exists(ENCODINGS_FILE):
        with open(ENCODINGS_FILE, 'rb') as f:
            encodings = pickle.load(f)
        print(f"Loaded encodings for {len(encodings)} users: {list(encodings.keys())}")
        return encodings
    print("No encodings file found, starting fresh.")
    return {}

def save_encodings(data):
    with open(ENCODINGS_FILE, 'wb') as f:
        pickle.dump(data, f)
    print(f"Saved encodings for {len(data)} users: {list(data.keys())}")

def read_attendance_from_sheet():
    try:
        sheet_data = ALL_SHEET.get_all_values()
        if not sheet_data or sheet_data[0] == ['Name']:
            return []
        headers = sheet_data[0]
        attendance = []
        for row in sheet_data[1:]:
            name = row[0]
            for i in range(1, len(headers), 2):
                if i + 1 >= len(headers):
                    break
                date = headers[i].replace(' Attendance', '')
                time_range = row[i] if i < len(row) else ''
                hours = row[i + 1] if i + 1 < len(row) else ''
                if time_range:
                    in_time, out_time = parse_time_range(time_range)
                    status = 'Present' if in_time else 'Absent'
                    attendance.append([name, date, in_time, out_time, status, hours])
        return attendance
    except Exception as e:
        print(f"Error in read_attendance_from_sheet: {e}")
        return []

def parse_time_range(time_range):
    if '-' in time_range:
        in_time, out_time = time_range.split(' - ')
        return in_time, out_time
    return time_range, ''

def calculate_hours(in_time, out_time):
    if not in_time or not out_time:
        return ''
    try:
        in_time_dt = datetime.strptime(in_time, '%H:%M:%S')
        out_time_dt = datetime.strptime(out_time, '%H:%M:%S')
        time_diff = out_time_dt - in_time_dt
        if time_diff.total_seconds() < 0:
            time_diff += timedelta(days=1)
        hours = time_diff.total_seconds() / 3600
        return f"{hours:.2f}"
    except ValueError:
        return ''

def update_sheet(attendance):
    try:
        today = datetime.now().strftime('%d/%m/%Y')
        headers = ALL_SHEET.row_values(1)
        if not headers or headers == ['Name']:
            headers = ['Name']
        else:
            existing_dates = set()
            for header in headers[1:]:
                if header.endswith(' Attendance'):
                    existing_dates.add(header.replace(' Attendance', ''))
            headers = ['Name']
            for date in sorted(existing_dates):
                headers.append(f"{date} Attendance")
                headers.append(f"{date} Hours")

        existing_dates = {header.replace(' Attendance', '') for header in headers if header.endswith(' Attendance')}
        for date in set(r[1] for r in attendance):
            if date not in existing_dates:
                headers.append(f"{date} Attendance")
                headers.append(f"{date} Hours")

        if f"{today} Attendance" not in headers:
            headers.append(f"{today} Attendance")
            headers.append(f"{today} Hours")

        all_names = list(load_encodings().keys())
        updated_data = []
        for name in all_names:
            row = [name]
            for i in range(1, len(headers), 2):
                date = headers[i].replace(' Attendance', '')
                time_range = ''
                hours = ''
                for record in attendance:
                    if record[0] == name and record[1] == date:
                        in_time = record[2] if record[2] else ''
                        out_time = record[3] if record[3] else ''
                        if in_time and out_time:
                            time_range = f"{in_time} - {out_time}"
                            hours = calculate_hours(in_time, out_time)
                        elif in_time:
                            time_range = in_time
                row.append(time_range)
                row.append(hours)
            updated_data.append(row)

        ALL_SHEET.update('A1', [headers], value_input_option='RAW')
        if updated_data:
            ALL_SHEET.update('A2', updated_data, value_input_option='RAW')
    except Exception as e:
        print(f"Error in update_sheet: {e}")
        raise

def log_attendance(name, action):
    now = datetime.now()
    date_str = now.strftime('%d/%m/%Y')
    time_str = now.strftime('%H:%M:%S')

    attendance = read_attendance_from_sheet()
    today_records = [r for r in attendance if r[0] == name and r[1] == date_str]

    if not today_records:
        if action == 'checkin':
            attendance.append([name, date_str, time_str, '', 'Present', ''])
            update_sheet(attendance)
            return True
    else:
        last_record = today_records[-1]
        checkin_time = datetime.strptime(last_record[2], '%H:%M:%S') if last_record[2] else None
        checkout_time = datetime.strptime(last_record[3], '%H:%M:%S') if last_record[3] else None

        if action == 'checkout' and checkin_time and not checkout_time:
            time_since_checkin = now - datetime.combine(date.today(), checkin_time.time())
            if time_since_checkin >= timedelta(hours=7):
                last_record[3] = time_str
                last_record[4] = 'Present'
                update_sheet(attendance)
                return True
            return False
        elif action == 'checkin' and not checkout_time:
            if not checkin_time:
                last_record[2] = time_str
                last_record[4] = 'Present'
                update_sheet(attendance)
                return True
    return False

def find_best_match(face_encoding, known_faces, tolerance=0.5, strict_threshold=0.45):
    matches = []
    for current_name, known_encodings in known_faces.items():
        distances = face_recognition.face_distance(known_encodings, face_encoding)
        for i, distance in enumerate(distances):
            if distance < tolerance:
                matches.append((current_name, distance))
    
    if matches:
        best_match = min(matches, key=lambda x: x[1])
        name, distance = best_match
        if distance < strict_threshold:
            print(f"Found match: {name} with distance {distance}")
            return name, distance
        else:
            print(f"Best match {name} rejected: distance {distance} >= {strict_threshold}")
    
    print("No valid match found for face.")
    return None

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == 'admin' and password == 'admin123':
            session['user'] = 'admin'
            return redirect('/admin_panel')
        elif username == 'user' and password == 'user123':
            session['user'] = 'user'
            return redirect('/user_panel')
        else:
            flash("Invalid username or password.")
            return redirect('/')

    return render_template('login.html')

@app.route('/admin_panel', methods=['GET', 'POST'])
def admin_panel():
    if session.get('user') != 'admin':
        return redirect('/')
    
    encodings = load_encodings()
    names = list(encodings.keys())
    attendance = read_attendance_from_sheet()
    today = datetime.now().strftime('%d/%m/%Y')
    initial_data = {name: {'checkin': '', 'checkout': '', 'status': 'Absent', 'allow_checkout': False, 'hours': ''} for name in names}
    
    todays_attendance = [r for r in attendance if r[1] == today]
    for name, date, checkin, checkout, status, hours in todays_attendance:
        checkin_formatted = checkin.split(':')[0] + ':' + checkin.split(':')[1] if checkin else ''
        checkout_formatted = checkout.split(':')[0] + ':' + checkout.split(':')[1] if checkout else ''
        initial_data[name] = {
            'checkin': checkin_formatted,
            'checkout': checkout_formatted,
            'status': status,
            'allow_checkout': bool(checkin and not checkout),
            'hours': hours
        }

    if request.method == 'POST' and 'force_checkout' in request.form:
        name = request.form['force_checkout']
        ist_now = datetime.now() + timedelta(hours=5, minutes=30)
        now = ist_now.strftime('%H:%M:%S')
        for record in todays_attendance:
            if record[0] == name and not record[3]:
                record[3] = now
                record[4] = 'Present'
        try:
            update_sheet(attendance)
            flash("Checkout forced successfully.", "success")
        except Exception as e:
            print(f"Error forcing checkout: {e}")
            flash("Network error: Could not update attendance. Please try again.", "error")
        return redirect('/admin_panel')

    return render_template('admin_panel.html', 
                          names=names, 
                          attendance=todays_attendance,  
                          initial_data=initial_data,
                          today=today)

@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if session.get('user') != 'admin':
        return redirect('/')

    if request.method == 'POST':
        try:
            # Check if JSON payload is provided
            if not request.is_json:
                return jsonify({'error': 'Invalid request. JSON data required.'}), 400

            data = request.get_json()
            name = data.get('name')
            images = data.get('images', [])

            if not name or not name.strip():
                return jsonify({'error': 'Name is required.'}), 400
            if not images:
                return jsonify({'error': 'No images provided.'}), 400

            encodings = load_encodings()
            if name in encodings:
                return jsonify({'error': 'User already registered. Try a different name.'}), 400

            person_dir = os.path.join(IMAGES_DIR, name)
            if not os.path.exists(person_dir):
                try:
                    os.makedirs(person_dir)
                    print(f"Created directory: {person_dir}")
                except Exception as e:
                    print(f"Error creating directory {person_dir}: {e}")
                    return jsonify({'error': f'Error creating directory for {name}: {str(e)}'}), 500

            known_face_encodings = []
            image_count = 0

            for image_data in images:
                try:
                    if ',' in image_data:
                        image_data = image_data.split(',')[1]  # Remove data:image/jpeg;base64, prefix
                    image_bytes = base64.b64decode(image_data)
                    image = Image.open(io.BytesIO(image_bytes))
                    frame = np.array(image)

                    # Ensure frame is in RGB format
                    if frame.shape[-1] == 4:  # Handle RGBA
                        frame = frame[:, :, :3]
                    rgb_frame = frame  # PIL loads as RGB

                    face_locations = face_recognition.face_locations(rgb_frame)
                    print(f"Image {image_count + 1}: Detected {len(face_locations)} faces")

                    if len(face_locations) == 0:
                        print(f"Image {image_count + 1}: No faces detected")
                        continue
                    if len(face_locations) > 1:
                        print(f"Image {image_count + 1}: Multiple faces detected, skipping")
                        continue

                    face_encoding = face_recognition.face_encodings(rgb_frame, face_locations)[0]
                    if face_encoding.shape != (128,):
                        print(f"Image {image_count + 1}: Invalid encoding shape: {face_encoding.shape}")
                        continue

                    known_face_encodings.append(face_encoding)
                    image_count += 1
                    image_path = os.path.join(person_dir, f'{name}_{image_count}.jpg')
                    try:
                        Image.fromarray(frame).save(image_path)
                        print(f"Saved image {image_count}: {image_path}")
                    except Exception as e:
                        print(f"Error saving image {image_path}: {e}")
                        continue

                except Exception as e:
                    print(f"Error processing image {image_count + 1}: {e}")
                    continue

            print(f"Capture complete. Total images: {image_count}, Total encodings: {len(known_face_encodings)}")

            if known_face_encodings:
                if len(known_face_encodings) < 5:
                    return jsonify({'error': 'Insufficient face captures (less than 5). Try again with better lighting or more angles.'}), 400
                encodings[name] = known_face_encodings
                try:
                    save_encodings(encodings)
                    headers = ALL_SHEET.row_values(1) or ['Name']
                    all_data = ALL_SHEET.get_all_values()[1:] or []
                    all_data.append([name] + [''] * (len(headers) - 1))
                    ALL_SHEET.clear()
                    ALL_SHEET.update('A1', [headers], value_input_option='RAW')
                    if all_data:
                        ALL_SHEET.update('A2', all_data, value_input_option='RAW')
                    return jsonify({'success': f'User {name} registered successfully'}), 200
                except Exception as e:
                    print(f"Error saving encodings or updating sheet: {e}")
                    return jsonify({'error': f'Network error: Could not save user data. Please try again.'}), 500
            else:
                return jsonify({'error': 'No valid faces detected. Try again with better lighting, closer to the camera, or different angles.'}), 400

        except Exception as e:
            print(f"Error in add_user: {e}")
            return jsonify({'error': f'Error processing request: {str(e)}'}), 500

    return render_template('add_user.html', error=None)

@app.route('/user_panel', methods=['GET', 'POST'])
def user_panel():
    client_ip = request.headers.get('X-Forwarded-For')
    
    if client_ip:
        # The 'X-Forwarded-For' can contain multiple IPs if there are multiple proxies, 
        # so we take the first one (which is usually the original client's IP).
        client_ip = client_ip.split(',')[0]
    else:
        # If the header is not available, fall back to request.remote_addr
        client_ip = request.remote_addr

    print(f"Client IP: {client_ip}")

    if client_ip != ALLOWED_SSID:
        return "<h3>Access Denied: Connect to the authorized Wi-Fi network to access this site.</h3>", 403

    
    if session.get('user') == 'admin' or session.get('user') is None:
        return redirect('/')

    known_faces = load_encodings()
    action = "Welcome, please start recognition"
    name = "Unknown"

    if request.method == 'POST':
        try:
            # Check if JSON payload is provided
            if not request.is_json:
                return jsonify({'action': 'Invalid request. Image data required.', 'name': name}), 400

            data = request.get_json()
            if 'image' not in data:
                return jsonify({'action': 'No image provided.', 'name': name}), 400

            # Decode base64 image
            image_data = data['image']
            if ',' in image_data:
                image_data = image_data.split(',')[1]  # Remove data:image/jpeg;base64, prefix
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            frame = np.array(image)

            # Ensure frame is in RGB format
            if frame.shape[-1] == 4:  # Handle RGBA
                frame = frame[:, :, :3]
            rgb_frame = frame  # PIL loads as RGB, no need to convert

            face_locations = face_recognition.face_locations(rgb_frame)
            if face_locations:
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                for face_encoding in face_encodings:
                    match_result = find_best_match(face_encoding, known_faces, tolerance=0.5, strict_threshold=0.45)
                    if match_result:
                        name, best_distance = match_result
                        print(f"Recognized: {name} with distance {best_distance}")
                        attendance = read_attendance_from_sheet()
                        ist_now = datetime.now() + timedelta(hours=5, minutes=30)
                        today = ist_now.strftime('%d/%m/%Y')
                        today_records = [r for r in attendance if r[0] == name and r[1] == today]
                        now = datetime.now() + timedelta(hours=5, minutes=30)

                        if not today_records:
                            noon = datetime.combine(ist_now.date(), datetime.strptime("12:00:00", "%H:%M:%S").time())
                            if now > noon:
                                action = "Check-in not allowed after 12:00 PM. Please contact the admin."
                            elif log_attendance(name, 'checkin'):
                                action = 'Checked in successfully'
                        else:
                            last_record = today_records[-1]
                            checkin_time = datetime.strptime(last_record[2], '%H:%M:%S') if last_record[2] else None
                            checkout_time = datetime.strptime(last_record[3], '%H:%M:%S') if last_record[3] else None

                            if checkout_time:
                                action = 'Attendance complete for today'
                            elif checkin_time and not checkout_time:
                                time_since_checkin = now - datetime.combine(date.today(), checkin_time.time())
                                if time_since_checkin < timedelta(hours=7):
                                    remaining = timedelta(hours=7) - time_since_checkin
                                    hours, remainder = divmod(remaining.total_seconds(), 3600)
                                    minutes, seconds = divmod(remainder, 60)
                                    action = f'Cannot check out yet, wait {int(hours)}h {int(minutes)}m {int(seconds)}s'
                                elif log_attendance(name, 'checkout'):
                                    action = 'Checked out successfully'
                            else:
                                action = 'Invalid attendance state'
                    else:
                        name = "Unknown"
                        action = "Unknown user. Please register or contact the admin."
            else:
                action = "No face detected. Ensure your face is visible and try again."

            return jsonify({'action': action, 'name': name})

        except Exception as e:
            print(f"Error in user_panel: {e}")
            return jsonify({'action': f"Error processing image: {str(e)}", 'name': name}), 500

    return render_template('user_panel.html', name=name, action=action, known_faces=known_faces)

@app.route('/delete_user', methods=['GET'])
def delete_user():
    if session.get('user') != 'admin':
        return redirect('/')

    name = request.args.get('name', '')
    if not name:
        flash("No user specified for deletion.", "error")
        return redirect('/admin_panel')

    encodings = load_encodings()
    if name in encodings:
        try:
            del encodings[name]
            save_encodings(encodings)
            all_data = ALL_SHEET.get_all_values()[1:] or []
            updated_data = [row for row in all_data if row[0] != name]
            headers = ALL_SHEET.row_values(1) or ['Name']
            ALL_SHEET.clear()
            ALL_SHEET.update('A1', [headers], value_input_option='RAW')
            if updated_data:
                ALL_SHEET.update('A2', updated_data, value_input_option='RAW')
            person_dir = os.path.join(IMAGES_DIR, name)
            if os.path.exists(person_dir):
                import shutil
                shutil.rmtree(person_dir)
            print(f"Successfully deleted user: {name}")
            flash(f"User {name} deleted successfully", "success")
            return redirect('/admin_panel')
        except Exception as e:
            print(f"Error deleting user {name}: {e}")
            flash(f"Error deleting user {name}: {str(e)}", "error")
            return redirect('/admin_panel')
    print(f"User not found: {name}")
    flash(f"User {name} not found.", "error")
    return redirect('/admin_panel')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

# @app.route('/mark_attendance', methods=['POST'])
# def mark_attendance():
#     name = request.form['mark_user']
#     status = request.form[f'status_{name}']
#     ist_now = datetime.now() + timedelta(hours=5, minutes=30)
#     date_str = ist_now.strftime('%d/%m/%Y')

#     checkin = request.form.get(f'checkin_{name}', '').strip()
#     checkout = request.form.get(f'checkout_{name}', '').strip()

#     attendance = read_attendance_from_sheet()
#     today_records = [r for r in attendance if r[0] == name and r[1] == date_str]
#     updated = False

#     if today_records:
#         last_record = today_records[-1]
#         if checkin and not last_record[2]:
#             last_record[2] = checkin + ':00' if checkin else ''
#             last_record[4] = 'Present'
#             updated = True
#         elif checkout and last_record[2] and not last_record[3]:
#             checkin_time = datetime.strptime(last_record[2], '%H:%M:%S')
#             time_since_checkin = datetime.now() - datetime.combine(date.today(), checkin_time.time())
#             if time_since_checkin >= timedelta(hours=7) or session.get('user') == 'admin':
#                 last_record[3] = checkout + ':00' if checkout else ''
#                 last_record[4] = 'Present'
#                 updated = True
#             else:
#                 flash("Checkout not allowed yet. Wait 7 hours or contact admin.", "error")
#                 return redirect('/admin_panel')
#     else:
#         attendance.append([name, date_str, checkin + ':00' if checkin else '', checkout + ':00' if checkout else '', 'Present' if checkin else 'Absent', ''])

#     if updated or not today_records:
#         try:
#             update_sheet(attendance)
#         except Exception as e:
#             print(f"Error in mark_attendance: {e}")
#             flash("Network error: Could not update attendance. Please try again.", "error")
#             return redirect('/admin_panel')

#     return redirect('/admin_panel')

from datetime import datetime, date, timedelta

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    name = request.form['mark_user']
    status = request.form[f'status_{name}']

    # ✅ Convert UTC to IST manually by adding 5 hours 30 minutes
    ist_now = datetime.now() + timedelta(hours=5, minutes=30)
    date_str = ist_now.strftime('%d/%m/%Y')

    print(date_str)

    checkin = request.form.get(f'checkin_{name}', '').strip()
    checkout = request.form.get(f'checkout_{name}', '').strip()

    attendance = read_attendance_from_sheet()
    today_records = [r for r in attendance if r[0] == name and r[1] == date_str]
    updated = False

    if today_records:
        last_record = today_records[-1]
        if checkin and not last_record[2]:
            last_record[2] = checkin + ':00' if checkin else ''
            last_record[4] = 'Present'
            updated = True
        elif checkout and last_record[2] and not last_record[3]:
            checkin_time = datetime.strptime(last_record[2], '%H:%M:%S')
            checkin_datetime = datetime.combine(ist_now.date(), checkin_time.time())
            time_since_checkin = ist_now - checkin_datetime

            if time_since_checkin >= timedelta(hours=7) or session.get('user') == 'admin':
                last_record[3] = checkout + ':00' if checkout else ''
                last_record[4] = 'Present'
                updated = True
            else:
                flash("Checkout not allowed yet. Wait 7 hours or contact admin.", "error")
                return redirect('/admin_panel')
    else:
        attendance.append([
            name,
            date_str,
            checkin + ':00' if checkin else '',
            checkout + ':00' if checkout else '',
            'Present' if checkin else 'Absent',
            ''
        ])

    if updated or not today_records:
        try:
            update_sheet(attendance)
        except Exception as e:
            print(f"Error in mark_attendance: {e}")
            flash("Network error: Could not update attendance. Please try again.", "error")
            return redirect('/admin_panel')

    return redirect('/admin_panel')


@app.route('/download_attendance')
def download_attendance():
    if session.get('user') != 'admin':
        return redirect('/')
    
    attendance = read_attendance_from_sheet()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Date', 'Time Range', 'Status', 'Hours'])
    for record in attendance:
        name, date, in_time, out_time, status, hours = record
        time_range = f"{in_time} - {out_time}" if in_time and out_time else (in_time or out_time)
        writer.writerow([name, date, time_range, status, hours])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode()),
        as_attachment=True,
        download_name='attendance_records.csv',
        mimetype='text/csv'
    )

@app.route('/history', methods=['GET', 'POST'])
def history():
    if session.get('user') != 'admin':
        return redirect('/')
    
    selected_date = None
    attendance_records = []

    if request.method == 'POST':
        selected_date = request.form.get('date')
        if selected_date:
            formatted_date = datetime.strptime(selected_date, '%Y-%m-%d').strftime('%d/%m/%Y')
            headers = ALL_SHEET.row_values(1)
            if f"{formatted_date} Attendance" in headers:
                col_idx = headers.index(f"{formatted_date} Attendance") + 1
                hours_col_idx = col_idx + 1
                all_data = ALL_SHEET.get_all_values()[1:] or []
                for row in all_data:
                    name = row[0]
                    time_range = row[col_idx - 1] if col_idx <= len(row) else ''
                    hours = row[hours_col_idx - 1] if hours_col_idx <= len(row) else ''
                    if time_range:
                        in_time, out_time = parse_time_range(time_range)
                        status = 'Present' if in_time else 'Absent'
                        time_display = f"{in_time} - {out_time}" if in_time and out_time else (in_time or out_time or 'N/A')
                        attendance_records.append({
                            'name': name,
                            'status': status,
                            'time': time_display
                        })

    return render_template('history.html', selected_date=selected_date, attendance_records=attendance_records)

# if __name__ == '__main__':
#     current_ssid = get_connected_ssid()
#     if current_ssid == ALLOWED_SSID:
#         print(f"✅ Connected to '{current_ssid}'. Starting Flask app...")
#         app.run(debug=True)
#     else:
#         print(f"❌ Access denied. Not connected to allowed Wi-Fi: '{ALLOWED_SSID}'")
#         print(f"📶 Current SSID: '{current_ssid or 'Unknown'}'")
#         sys.exit(1)
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
