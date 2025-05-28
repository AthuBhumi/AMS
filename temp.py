from flask import Flask, render_template, redirect, request, session, url_for, send_file, flash, jsonify
import face_recognition
import cv2
import os
import pickle
from datetime import datetime, timedelta, date, time
import numpy as np
import csv
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import base64
from PIL import Image
from pytz import timezone
from dotenv import load_dotenv
import json
from google.oauth2.service_account import Credentials
import shutil

load_dotenv()

credential_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
app = Flask(__name__)
app.secret_key = 'secret'  # Required for sessions

ENCODINGS_FILE = 'face_encodings (1).pkl'
IMAGES_DIR = 'images'
TEMP_CHECKIN_IMAGES_DIR = 'temp_checkin_images'

# Create temporary check-in images directory if it doesn't exist
if not os.path.exists(TEMP_CHECKIN_IMAGES_DIR):
    os.makedirs(TEMP_CHECKIN_IMAGES_DIR)

# Google Sheets setup
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credential_dict = json.loads(credential_json)
CREDS = Credentials.from_service_account_info(credential_dict, scopes=SCOPE)
CLIENT = gspread.authorize(CREDS)
ALL_SHEET = CLIENT.open("Nitesh_Bhaiya").sheet1
CALENDAR_SHEET = CLIENT.open("Nitesh_Bhaiya").worksheet("Calendar")
LEAVE_SHEET = CLIENT.open("Nitesh_Bhaiya").worksheet("LeaveBalance")
CLIENT_VISITS_SHEET = None  # Will initialize later

# Initialize ClientVisits worksheet if it doesn't exist
# Initialize ClientVisits worksheet if it doesn't exist
def init_client_visits_sheet():
    global CLIENT_VISITS_SHEET
    try:
        CLIENT_VISITS_SHEET = CLIENT.open("Nitesh_Bhaiya").worksheet("ClientVisits")
        # Ensure headers exist
        headers = CLIENT_VISITS_SHEET.row_values(1)
        expected_headers = ["Employee Name", "Date", "Client", "Purpose", "Status"]
        if not headers or headers != expected_headers:
            print("ClientVisits worksheet headers missing or incorrect. Setting up headers.")
            CLIENT_VISITS_SHEET.clear()
            CLIENT_VISITS_SHEET.append_row(expected_headers)
    except gspread.exceptions.WorksheetNotFound:
        print("ClientVisits worksheet not found. Creating new worksheet.")
        CLIENT_VISITS_SHEET = CLIENT.open("Nitesh_Bhaiya").add_worksheet(title="ClientVisits", rows="100", cols="5")
        CLIENT_VISITS_SHEET.append_row(["Employee Name", "Date", "Client", "Purpose", "Status"])
    except Exception as e:
        print(f"Critical error initializing ClientVisits sheet: {e}")
        raise

init_client_visits_sheet()

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
    return None, None

def is_working_day(date_str):
    try:
        records = CALENDAR_SHEET.get_all_values()[1:]  # Skip header
        for row in records:
            if row[0] == date_str:
                return row[2].lower() == 'yes'
        return True  # Default to working day if not found
    except Exception as e:
        print(f"Error checking working day: {e}")
        return True

def has_approved_client_visit(employee_name, date_str):
    try:
        records = CLIENT_VISITS_SHEET.get_all_records()
        print(f"Checking for approved client visit - Employee: {employee_name}, Date: {date_str}")
        print(f"ClientVisits records: {records}")
        for record in records:
            print(f"Comparing - Record Employee: {record['Employee Name']}, Record Date: {record['Date']}, Record Status: {record['Status']}")
            if (record['Employee Name'].lower() == employee_name.lower() and 
                record['Date'] == date_str and 
                record['Status'] == 'Approved'):
                print(f"Approved client visit found for {employee_name} on {date_str}")
                return True
        print(f"No approved client visit found for {employee_name} on {date_str}")
        return False
    except Exception as e:
        print(f"Error checking client visit: {e}")
        return False

def update_leave_balance(name, month, leaves_used=0, hours_worked=0):
    try:
        headers = LEAVE_SHEET.row_values(1) or ['Employee_ID', 'Name', 'Month', 'Leaves_Available', 'Leaves_Used', 'Leaves_Carried_Forward', 'Compensatory_Days']
        if 'Compensatory_Days' not in headers:
            headers.append('Compensatory_Days')
            LEAVE_SHEET.update('A1', [headers], value_input_option='RAW')
        
        records = LEAVE_SHEET.get_all_values()[1:] or []
        employee_id = len(records) + 1
        current_record = None
        prev_month = (datetime.strptime(month, '%b-%Y') - timedelta(days=1)).strftime('%b-%Y')

        prev_leaves = 0
        prev_comp_days = 0
        for row in records:
            if row[1] == name and row[2] == prev_month:
                prev_leaves = float(row[5] or 0)
                prev_comp_days = float(row[6] or 0) if len(row) > 6 else 0
                break

        leaves_available = 2 + prev_leaves

        if current_record := next((row for row in records if row[1] == name and row[2] == month), None):
            old_leaves_used = float(current_record[4])
            new_leaves_used = old_leaves_used + leaves_used
            excess_leaves = max(0, new_leaves_used - 2)
            compensatory_days = prev_comp_days + excess_leaves
            if hours_worked >= 8.75:  # Overtime
                compensatory_days += 1
            elif hours_worked >= 8:
                compensatory_days = max(0, compensatory_days - 1)

            current_record[3] = str(leaves_available)
            current_record[4] = str(new_leaves_used)
            current_record[5] = str(leaves_available - new_leaves_used)
            current_record[6] = str(compensatory_days) if len(current_record) > 6 else str(compensatory_days)
            print(f"Updating leave balance for {name} in {month}: Leaves Available = {leaves_available}, Leaves Used = {new_leaves_used}, Carried Forward = {leaves_available - new_leaves_used}, Compensatory Days = {compensatory_days}")
            LEAVE_SHEET.update(f'A{records.index(current_record) + 2}', [current_record], value_input_option='RAW')
        else:
            new_leaves_used = leaves_used
            excess_leaves = max(0, new_leaves_used - 2)
            compensatory_days = prev_comp_days + excess_leaves
            if hours_worked >= 8.75:  # Overtime
                compensatory_days += 1
            elif hours_worked >= 8:
                compensatory_days = max(0, compensatory_days - 1)

            new_record = [
                str(employee_id),
                name,
                month,
                str(leaves_available),
                str(new_leaves_used),
                str(leaves_available - new_leaves_used),
                str(compensatory_days)
            ]
            print(f"Creating new leave balance for {name} in {month}: Leaves Available = {leaves_available}, Leaves Used = {new_leaves_used}, Carried Forward = {leaves_available - new_leaves_used}, Compensatory Days = {compensatory_days}")
            LEAVE_SHEET.append_row(new_record, value_input_option='RAW')
    except Exception as e:
        print(f"Error updating leave balance: {e}")

def read_attendance_from_sheet():
    try:
        sheet_data = ALL_SHEET.get_all_values()
        if not sheet_data or sheet_data[0] == ['Name']:
            return []
        headers = sheet_data[0]
        attendance = []
        for row in sheet_data[1:]:
            name = row[0]
            for i in range(1, len(headers), 4):
                if i + 3 >= len(headers):
                    break
                date = headers[i].replace(' Attendance', '')
                time_range = row[i] if i < len(row) else ''
                hours = row[i + 1] if i + 1 < len(row) else ''
                checkin_image = row[i + 2] if i + 2 < len(row) else ''
                day_status = row[i + 3] if i + 3 < len(row) else ''
                if time_range:
                    in_time, out_time = parse_time_range(time_range)
                    status = 'Present' if in_time else 'Absent'
                    attendance.append([name, date, in_time, out_time, status, hours, checkin_image, day_status])
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
                headers.append(f"{date} Image")
                headers.append(f"{date} Day Status")

        existing_dates = {header.replace(' Attendance', '') for header in headers if header.endswith(' Attendance')}
        for date in set(r[1] for r in attendance):
            if date not in existing_dates:
                headers.append(f"{date} Attendance")
                headers.append(f"{date} Hours")
                headers.append(f"{date} Image")
                headers.append(f"{date} Day Status")

        if f"{today} Attendance" not in headers:
            headers.append(f"{today} Attendance")
            headers.append(f"{today} Hours")
            headers.append(f"{today} Image")
            headers.append(f"{today} Day Status")

        all_names = list(load_encodings().keys())
        updated_data = []
        for name in all_names:
            row = [name]
            for i in range(1, len(headers), 4):
                date = headers[i].replace(' Attendance', '')
                time_range = ''
                hours = ''
                checkin_image = ''
                day_status = ''
                for record in attendance:
                    if record[0] == name and record[1] == date:
                        in_time = record[2] if record[2] else ''
                        out_time = record[3] if record[3] else ''
                        checkin_image = record[6] if len(record) > 6 else ''
                        day_status = record[7] if len(record) > 7 else ''
                        if in_time and out_time:
                            time_range = f"{in_time} - {out_time}"
                            hours = calculate_hours(in_time, out_time)
                        elif in_time:
                            time_range = in_time
                row.append(time_range)
                row.append(hours)
                row.append(checkin_image)
                row.append(day_status)
            updated_data.append(row)

        ALL_SHEET.update('A1', [headers], value_input_option='RAW')
        if updated_data:
            ALL_SHEET.update('A2', updated_data, value_input_option='RAW')
    except Exception as e:
        print(f"Error in update_sheet: {e}")
        raise

def get_checkin_image_base64(name, date_str):
    image_path = os.path.join(TEMP_CHECKIN_IMAGES_DIR, f"{name}_{date_str.replace('/', '-')}.jpg")
    if os.path.exists(image_path):
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/jpeg;base64,{encoded_string}"
    return None

def log_attendance(name, action, image_data=None):
    now = datetime.now()
    date_str = now.strftime('%d/%m/%Y')
    time_str = now.strftime('%H:%M:%S')
    month = now.strftime('%b-%Y')

    if not is_working_day(date_str):
        return False, "Today is a holiday. Attendance cannot be logged."

    attendance = read_attendance_from_sheet()
    today_records = [r for r in attendance if r[0] == name and r[1] == date_str]

    image_path = None
    if image_data and action == 'checkin':
        try:
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            person_dir = os.path.join(IMAGES_DIR, name)
            if not os.path.exists(person_dir):
                os.makedirs(person_dir)
            image_path = os.path.join(person_dir, f'{name}checkin{date_str.replace("/", "-")}.jpg')
            image.save(image_path)
            image_path = f'/images/{name}/{name}checkin{date_str.replace("/", "-")}.jpg'
        except Exception as e:
            print(f"Error saving check-in image: {e}")
            image_path = None

    if not today_records:
        if action == 'checkin':
            checkin_dt = datetime.strptime(time_str, '%H:%M:%S')
            time_10_00 = datetime.combine(datetime.today(), time(10, 0))
            time_10_30 = datetime.combine(datetime.today(), time(10, 30))
            time_11_00 = datetime.combine(datetime.today(), time(11, 0))
            time_12_00 = datetime.combine(datetime.today(), time(12, 0))
            day_status = 'Full Day'
            if time_10_30 <= checkin_dt <= time_11_00:
                day_status = 'Full Day'
            elif checkin_dt > time_11_00:
                day_status = 'Half Day'
            if checkin_dt <= time_12_00 and has_approved_client_visit(name, date_str):
                attendance.append([name, date_str, time_str, '', 'Present', '', image_path or '', day_status])
                update_sheet(attendance)
                update_leave_balance(name, month)
                return True, "Checked in successfully (Approved client visit)"
            elif checkin_dt > time_12_00:
                attendance.append([name, date_str, time_str, '', 'Present', '', image_path or '', day_status])
                update_sheet(attendance)
                update_leave_balance(name, month)
                return True, "Checked in successfully"
            else:
                return False, "Check-in not allowed before 12:00 PM unless approved client visit"
    else:
        last_record = today_records[-1]
        checkin_time = datetime.strptime(last_record[2], '%H:%M:%S') if last_record[2] else None
        checkout_time = datetime.strptime(last_record[3], '%H:%M:%S') if last_record[3] else None

        if action == 'checkout' and checkin_time and not checkout_time:
            time_since_checkin = now - datetime.combine(date.today(), checkin_time.time())
            hours_worked = time_since_checkin.total_seconds() / 3600
            day_status = 'Overtime' if hours_worked >= 8.75 else ('Full Day' if checkin_time.time() <= time(11, 0) else 'Half Day')
            if time_since_checkin >= timedelta(hours=7):
                last_record[3] = time_str
                last_record[4] = 'Present'
                hours = float(calculate_hours(last_record[2], last_record[3]))
                last_record[5] = str(hours)
                last_record[7] = day_status
                update_sheet(attendance)
                update_leave_balance(name, month, hours_worked=hours)
                return True, f"Checked out successfully. Hours: {hours:.2f}. Status: {day_status}"
            return False, "Cannot check out yet. Must work at least 7 hours."
        elif action == 'checkin' and not checkout_time:
            if not checkin_time:
                checkin_dt = datetime.strptime(time_str, '%H:%M:%S')
                time_10_00 = datetime.combine(datetime.today(), time(10, 0))
                time_10_30 = datetime.combine(datetime.today(), time(10, 30))
                time_11_00 = datetime.combine(datetime.today(), time(11, 0))
                time_12_00 = datetime.combine(datetime.today(), time(12, 0))
                day_status = 'Full Day'
                if time_10_30 <= checkin_dt <= time_11_00:
                    day_status = 'Full Day'
                elif checkin_dt > time_11_00:
                    day_status = 'Half Day'
                if checkin_dt <= time_12_00 and has_approved_client_visit(name, date_str):
                    last_record[2] = time_str
                    last_record[4] = 'Present'
                    last_record[6] = image_path or ''
                    last_record[7] = day_status
                    update_sheet(attendance)
                    update_leave_balance(name, month)
                    return True, "Checked in successfully (Approved client visit)"
                elif checkin_dt > time_12_00:
                    last_record[2] = time_str
                    last_record[4] = 'Present'
                    last_record[6] = image_path or ''
                    last_record[7] = day_status
                    update_sheet(attendance)
                    update_leave_balance(name, month)
                    return True, "Checked in successfully"
                else:
                    return False, "Check-in not allowed before 12:00 PM unless approved client visit"
    return False, "Invalid attendance state"

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == 'admin' and password == 'admin123':
            session['user'] = 'admin'
            session['user_name'] = 'admin'
            return redirect('/admin_panel')
        elif username == 'user' and password == 'user123':
            session['user'] = 'user'
            session['user_name'] = 'user'
            session.permanent = True
            print(f"User login successful. Session: {session}")
            return redirect('/user_panel')
        else:
            known_faces = load_encodings()
            if username in known_faces and password == 'user123':
                session['user'] = 'user'
                session['user_name'] = username  # Store the actual registered name
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
    month = datetime.now().strftime('%b-%Y')
    initial_data = {name: {'checkin': '', 'checkout': '', 'status': 'Absent', 'allow_checkout': False, 'hours': '', 'checkin_image': '', 'day_status': 'Working Day'} for name in names}
    
    # Fetch client visit data
    client_visit_data = []
    try:
        client_visit_records = CLIENT_VISITS_SHEET.get_all_records()
        if not client_visit_records:
            print("No client visit records found in the sheet.")
        else:
            for record in client_visit_records:
                # Ensure all expected keys exist in the record
                if all(key in record for key in ['Employee Name', 'Date', 'Client', 'Purpose', 'Status']):
                    client_visit_data.append({
                        'employee_name': record['Employee Name'],
                        'date': record['Date'],
                        'client': record['Client'],
                        'purpose': record['Purpose'],
                        'status': record['Status']
                    })
                else:
                    print(f"Skipping malformed client visit record: {record}")
    except Exception as e:
        print(f"Error fetching client visits: {e}")
        flash(f'Error fetching client visit data: {str(e)}', 'error')

    # Handle client visit actions
    if request.method == 'POST' and 'client_visit_action' in request.form:
        employee_name = request.form['employee_name']
        date = request.form['date']
        action = request.form['client_visit_action']
        try:
            records = CLIENT_VISITS_SHEET.get_all_values()
            for i, row in enumerate(records[1:], start=2):
                if row[0] == employee_name and row[1] == date:
                    CLIENT_VISITS_SHEET.update_cell(i, 5, action)
                    flash(f'Client visit request {action.lower()}', 'success')
                    break
        except Exception as e:
            print(f"Error updating client visit: {e}")
            flash('Error updating client visit status', 'error')
        return redirect(url_for('admin_panel'))

    # Rest of the admin_panel route remains unchanged...
    todays_attendance = [r for r in attendance if r[1] == today]
    for record in todays_attendance:
        name, date, checkin, checkout, status, hours, checkin_image, day_status = record if len(record) > 7 else record + [''] * (8 - len(record))
        checkin_formatted = checkin.split(':')[0] + ':' + checkin.split(':')[1] if checkin else ''
        checkout_formatted = checkout.split(':')[0] + ':' + checkout.split(':')[1] if checkout else ''
        initial_data[name] = {
            'checkin': checkin_formatted,
            'checkout': checkout_formatted,
            'status': status,
            'allow_checkout': bool(checkin and not checkout),
            'hours': hours,
            'checkin_image': checkin_image or get_checkin_image_base64(name, today),
            'day_status': day_status or ('Working Day' if is_working_day(today) else 'Holiday')
        }

    leave_balances = LEAVE_SHEET.get_all_values()[1:] or []
    leave_data = {row[1]: {
        'leaves_available': row[3],
        'leaves_used': row[4],
        'leaves_carried_forward': row[5],
        'compensatory_days': row[6] if len(row) > 6 else '0'
    } for row in leave_balances if row[2] == month}
    print(f"Leave data for {month}: {leave_data}")

    if request.method == 'POST' and 'force_checkout' in request.form:
        name = request.form['force_checkout']
        now = datetime.now().strftime('%H:%M:%S')
        for record in todays_attendance:
            if record[0] == name and not record[3]:
                record[3] = now
                record[4] = 'Present'
                hours = float(calculate_hours(record[2], now))
                day_status = 'Overtime' if hours >= 8.75 else ('Full Day' if datetime.strptime(record[2], '%H:%M:%S').time() <= time(11, 0) else 'Half Day')
                record[5] = str(hours)
                record[7] = day_status
                update_leave_balance(name, month, hours_worked=hours)
        try:
            update_sheet(attendance)
            image_path = os.path.join(TEMP_CHECKIN_IMAGES_DIR, f"{name}_{today.replace('/', '-')}.jpg")
            if os.path.exists(image_path):
                os.remove(image_path)
                print(f"Deleted check-in image: {image_path}")
            flash("Checkout forced successfully.", "success")
        except Exception as e:
            print(f"Error forcing checkout: {e}")
            flash("Network error: Could not update attendance. Please try again.", "error")
        return redirect('/admin_panel')

    return render_template(
        'admin_panel.html',
        today=today,
        names=names,
        initial_data=initial_data,
        leave_data=leave_data,
        month=month,
        datetime=datetime,
        client_visit_data=client_visit_data
    )
@app.route('/add_user', methods=['GET', 'POST'])
def add_user():
    if session.get('user') != 'admin':
        return redirect('/')

    if request.method == 'POST':
        try:
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
                        image_data = image_data.split(',')[1]
                    image_bytes = base64.b64decode(image_data)
                    image = Image.open(io.BytesIO(image_bytes))
                    frame = np.array(image)

                    if frame.shape[-1] == 4:
                        frame = frame[:, :, :3]
                    rgb_frame = frame

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
                    update_leave_balance(name, datetime.now().strftime('%b-%Y'))
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
    # if session.get('user') == 'admin' or session.get('user') is None:
    #     return redirect('/')
    print(f"Accessing user_panel. Session: {session}")
    if session.get('user') == 'admin':
        print("Redirecting: User is logged in as admin.")
        return redirect('/')
    if session.get('user') is None:
        print("Redirecting: No user in session.")
        return redirect('/')

    name = session.get('user_name', 'user')  # Always 'user'
    action = "Welcome, please check in or out"
    print(f"User panel accessed. Name: {name}, Session: {session}")
    known_faces = load_encodings()
    action = "Welcome, please start recognition"
    name = session.get('user_name', 'Unknown')

    # Handle client visit request
    if request.method == 'POST' and 'client_visit' in request.form:
        employee_name = request.form['employee_name']
        date = request.form['date']  # Comes in YYYY-MM-DD format (e.g., "2025-05-26")
        # Convert date to DD/MM/YYYY format
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d/%m/%Y')  # e.g., "26/05/2025"
        except ValueError:
            flash('Invalid date format. Please use YYYY-MM-DD.', 'error')
            return redirect(url_for('user_panel'))
        client = request.form['client']
        purpose = request.form['purpose']
        try:
            CLIENT_VISITS_SHEET.append_row([employee_name, formatted_date, client, purpose, 'Pending'])
            flash('Client visit request submitted successfully', 'success')
        except Exception as e:
            print(f"Error saving client visit: {e}")
            flash('Error submitting client visit request', 'error')
        return redirect(url_for('user_panel'))

    # Rest of the user_panel route remains unchanged...
    if request.method == 'POST':
        try:
            if not request.is_json:
                return jsonify({'action': 'Invalid request. Image data required.', 'name': name}), 400

            data = request.get_json()
            if 'image' not in data:
                return jsonify({'action': 'No image provided.', 'name': name}), 400

            image_data = data['image']
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            image_bytes = base64.b64decode(image_data)
            image = Image.open(io.BytesIO(image_bytes))
            frame = np.array(image)

            if frame.shape[-1] == 4:
                frame = frame[:, :, :3]
            rgb_frame = frame

            face_locations = face_recognition.face_locations(rgb_frame)
            if face_locations:
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                for face_encoding in face_encodings:
                    match_result = find_best_match(face_encoding, known_faces, tolerance=0.5, strict_threshold=0.45)
                    if match_result:
                        matched_name, best_distance = match_result
                        print(f"Recognized: {matched_name} with distance {best_distance}")
                        print(f'{matched_name} {name}')
                        if matched_name != name:
                            return jsonify({'action': 'Face does not match your profile.', 'name': name})
                        attendance = read_attendance_from_sheet()
                        today = datetime.now().strftime('%d/%m/%Y')
                        today_records = [r for r in attendance if r[0] == name and r[1] == today]
                        now = datetime.now()

                        if not is_working_day(today):
                            action = "Today is a holiday. Attendance cannot be logged."
                        elif not today_records:
                            success, message = log_attendance(name, 'checkin', image_data)
                            action = message
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
                                else:
                                    success, message = log_attendance(name, 'checkout')
                                    action = message
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
            leave_data = LEAVE_SHEET.get_all_values()[1:] or []
            updated_leave_data = [row for row in leave_data if row[1] != name]
            LEAVE_SHEET.clear()
            LEAVE_SHEET.update('A1', ['Employee_ID', 'Name', 'Month', 'Leaves_Available', 'Leaves_Used', 'Leaves_Carried_Forward', 'Compensatory_Days'], value_input_option='RAW')
            if updated_leave_data:
                LEAVE_SHEET.update('A2', updated_leave_data, value_input_option='RAW')
            person_dir = os.path.join(IMAGES_DIR, name)
            if os.path.exists(person_dir):
                shutil.rmtree(person_dir)
            for image_file in os.listdir(TEMP_CHECKIN_IMAGES_DIR):
                if image_file.startswith(f"{name}_"):
                    os.remove(os.path.join(TEMP_CHECKIN_IMAGES_DIR, image_file))
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

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():

    name = request.form['mark_user']
    status = request.form[f'status_{name}']
    india = timezone('Asia/Kolkata')
    now = datetime.now(india)

    # Add 5 hours and 30 minutes
    added_time = now + timedelta(hours=5, minutes=30)

    date_str = added_time.strftime('%d/%m/%Y')
    month = added_time.strftime('%b-%Y')

    noon_naive = datetime.combine(added_time.date(), time(12, 0))
    noon = india.localize(noon_naive)


    # Block admin attendance marking before 12:00 PM unless approved client visit
    if now < noon and not has_approved_client_visit(name, date_str):
        flash("Admin attendance marking is disabled before 12:00 PM unless approved client visit.", "error")
        return redirect('/admin_panel')

    # Validate that check-in time entered is after 12:00 PM unless approved client visit
    checkin = request.form.get(f'checkin_{name}', '').strip()
    print(f"has_approved_client_visit({name}, {date_str}) returned: {has_approved_client_visit(name, date_str)}")
    if checkin and not has_approved_client_visit(name, date_str):
        try:
            checkin_dt = datetime.strptime(checkin + ':00', '%H:%M:%S')
            checkin_dt = india.localize(checkin_dt.replace(year=now.year, month=now.month, day=now.day))
            if checkin_dt.time() < time(12, 0):
                flash("Check-in time must be after 12:00 PM when marked by admin unless approved client visit.", "error")
                return redirect('/admin_panel')
        except ValueError:
            flash("Invalid check-in time format. Use HH:MM.", "error")
            return redirect('/admin_panel')

    checkout = request.form.get(f'checkout_{name}', '').strip()

    if not is_working_day(date_str):
        flash("Today is a holiday. Attendance cannot be logged.", "error")
        return redirect('/admin_panel')

    attendance = read_attendance_from_sheet()
    today_records = [r for r in attendance if r[0] == name and r[1] == date_str]
    updated = False

    if status == 'Absent':
        update_leave_balance(name, month, leaves_used=1)

    day_status = 'Full Day'  # Default
    if checkin:
        try:
            checkin_dt = datetime.strptime(checkin + ':00', '%H:%M:%S')
            checkin_dt = india.localize(checkin_dt.replace(year=now.year, month=now.month, day=now.day))
            if checkin_dt.time() > time(11, 0):
                day_status = 'Half Day'
        except ValueError:
            flash("Invalid check-in time format. Use HH:MM.", "error")
            return redirect('/admin_panel')

    if today_records:
        last_record = today_records[-1]
        if checkin and not last_record[2]:
            last_record[2] = checkin + ':00' if checkin else ''
            last_record[4] = 'Present'
            last_record[7] = day_status
            updated = True
        elif checkout and last_record[2] and not last_record[3]:
            try:
                checkin_time = datetime.strptime(last_record[2], '%H:%M:%S')
                checkin_time = india.localize(checkin_time.replace(year=now.year, month=now.month, day=now.day))
                checkout_dt = datetime.strptime(checkout + ':00', '%H:%M:%S')
                checkout_dt = india.localize(checkout_dt.replace(year=now.year, month=now.month, day=now.day))
                time_since_checkin = checkout_dt - checkin_time
                hours = time_since_checkin.total_seconds() / 3600
                if hours < 0:
                    hours += 24  # Handle overnight shifts
                day_status = 'Overtime' if hours >= 8.75 else ('Full Day' if checkin_time.time() <= time(11, 0) else 'Half Day')
                if time_since_checkin >= timedelta(hours=7) or session.get('user') == 'admin':
                    last_record[3] = checkout + ':00' if checkout else ''
                    last_record[4] = 'Present'
                    last_record[5] = str(hours)
                    last_record[7] = day_status
                    update_leave_balance(name, month, hours_worked=hours)
                    updated = True
                else:
                    flash("Checkout not allowed yet. Wait 7 hours or contact admin.", "error")
                    return redirect('/admin_panel')
            except ValueError:
                flash("Invalid check-out time format. Use HH:MM.", "error")
                return redirect('/admin_panel')
    else:
        hours = float(calculate_hours(checkin + ':00', checkout + ':00')) if checkin and checkout else 0
        if checkout:
            try:
                checkin_time = datetime.strptime(checkin + ':00', '%H:%M:%S')
                checkin_time = india.localize(checkin_time.replace(year=now.year, month=now.month, day=now.day))
                day_status = 'Overtime' if hours >= 8.75 else ('Full Day' if checkin_time.time() <= time(11, 0) else 'Half Day')
            except ValueError:
                flash("Invalid check-in time format. Use HH:MM.", "error")
                return redirect('/admin_panel')
        attendance.append([name, date_str, checkin + ':00' if checkin else '', checkout + ':00' if checkout else '', 'Present' if checkin else 'Absent', str(hours), '', day_status])
        update_leave_balance(name, month, hours_worked=hours)
        updated = True

    if updated or not today_records:
        try:
            update_sheet(attendance)
            flash("Attendance updated successfully.", "success")
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
    writer.writerow(['Name', 'Date', 'Time Range', 'Status', 'Hours', 'Check-in Image', 'Day Status'])
    for record in attendance:
        name, date, in_time, out_time, status, hours, checkin_image, day_status = record if len(record) > 7 else record + [''] * (8 - len(record))
        time_range = f"{in_time} - {out_time}" if in_time and out_time else (in_time or out_time)
        writer.writerow([name, date, time_range, status, hours, checkin_image, day_status])
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
                image_col_idx = col_idx + 2
                day_status_col_idx = col_idx + 3 if col_idx + 3 < len(headers) else None
                all_data = ALL_SHEET.get_all_values()[1:] or []
                for row in all_data:
                    name = row[0]
                    time_range = row[col_idx - 1] if col_idx <= len(row) else ''
                    hours = row[hours_col_idx - 1] if hours_col_idx <= len(row) else ''
                    checkin_image = row[image_col_idx - 1] if image_col_idx <= len(row) else ''
                    day_status = row[day_status_col_idx - 1] if day_status_col_idx and day_status_col_idx <= len(row) else ''
                    if time_range:
                        in_time, out_time = parse_time_range(time_range)
                        status = 'Present' if in_time else 'Absent'
                        time_display = f"{in_time} - {out_time}" if in_time and out_time else (in_time or out_time or 'N/A')
                        attendance_records.append({
                            'name': name,
                            'status': status,
                            'time': time_display,
                            'hours': hours,
                            'checkin_image': checkin_image,
                            'day_status': day_status
                        })

    return render_template('history.html', selected_date=selected_date, attendance_records=attendance_records)

@app.route('/calendar', methods=['GET', 'POST'])
def calendar():
    if session.get('user') != 'admin':
        return redirect('/')
    
    month = request.args.get('month', datetime.now().strftime('%b-%Y'))
    today = datetime.now().strftime('%Y-%m-%d')
    days = []
    try:
        records = CALENDAR_SHEET.get_all_values()[1:] or []
        for row in records:
            if datetime.strptime(row[0], '%d/%m/%Y').strftime('%b-%Y') == month:
                days.append({'date': row[0], 'day': row[1], 'is_working_day': row[2], 'holiday_reason': row[3]})
    except Exception as e:
        print(f"Error reading calendar: {e}")

    if request.method == 'POST':
        try:
            date_input = request.form['date']
            date_obj = datetime.strptime(date_input, '%Y-%m-%d')
            date = date_obj.strftime('%d/%m/%Y')
            
            is_working_day = request.form['is_working_day']
            holiday_reason = request.form.get('holiday_reason', '')
            records = CALENDAR_SHEET.get_all_values()[1:] or []
            updated = False
            for i, row in enumerate(records):
                if row[0] == date:
                    records[i] = [date, datetime.strptime(date, '%d/%m/%Y').strftime('%A'), is_working_day, holiday_reason]
                    updated = True
                    break
            if not updated:
                records.append([date, datetime.strptime(date, '%d/%m/%Y').strftime('%A'), is_working_day, holiday_reason])
            CALENDAR_SHEET.update('A2', records, value_input_option='RAW')
            flash("Calendar updated successfully.", "success")
        except Exception as e:
            print(f"Error updating calendar: {e}")
            flash("Network error: Could not update calendar. Please try again.", "error")
        return redirect(url_for('calendar', month=month))

    return render_template('calendar.html', days=days, month=month, today=today)

@app.route('/leave_balance', methods=['GET', 'POST'])
def leave_balance():
    if session.get('user') != 'admin':
        return redirect('/')
    
    month = request.args.get('month', datetime.now().strftime('%b-%Y'))
    leave_balances = LEAVE_SHEET.get_all_values()[1:] or []
    leave_data = [row for row in leave_balances if row[2] == month]

    if request.method == 'POST':
        try:
            name = request.form['name']
            leaves_available = float(request.form['leaves_available'])
            leaves_used = float(request.form['leaves_used'])
            compensatory_days = float(request.form.get('compensatory_days', 0))
            records = LEAVE_SHEET.get_all_values()[1:] or []
            updated = False
            for i, row in enumerate(records):
                if row[1] == name and row[2] == month:
                    records[i][3] = str(leaves_available)
                    records[i][4] = str(leaves_used)
                    records[i][5] = str(leaves_available - leaves_used)
                    records[i][6] = str(compensatory_days) if len(records[i]) > 6 else str(compensatory_days)
                    updated = True
                    break
            if not updated:
                employee_id = len(records) + 1
                records.append([str(employee_id), name, month, str(leaves_available), str(leaves_used), str(leaves_available - leaves_used), str(compensatory_days)])
            LEAVE_SHEET.update('A2', records, value_input_option='RAW')
            flash("Leave balance updated successfully.", "success")
        except Exception as e:
            print(f"Error updating leave balance: {e}")
            flash("Network error: Could not update leave balance. Please try again.", "error")
        return redirect(url_for('leave_balance', month=month))

    return render_template('leave_balance.html', leave_data=leave_data, month=month)

def update_client_visits_dates():
    try:
        records = CLIENT_VISITS_SHEET.get_all_values()
        headers = records[0]
        updated_records = [headers]
        for row in records[1:]:
            date_str = row[1]  # Date column
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d/%m/%Y')
                row[1] = formatted_date
            except ValueError:
                pass  # Date is already in DD/MM/YYYY format or invalid
            updated_records.append(row)
        CLIENT_VISITS_SHEET.update('A1', updated_records, value_input_option='RAW')
        print("Updated date formats in ClientVisits sheet.")
    except Exception as e:
        print(f"Error updating ClientVisits dates: {e}")

# Run this once to update existing records
update_client_visits_dates()

if __name__ == '__main__':
    app.run(debug=True)