# from flask import Flask, render_template, redirect, request, session, url_for, send_file
# import face_recognition
# import cv2
# import os
# import pickle
# from datetime import datetime, timedelta
# import numpy as np
# import csv
# import time

# app = Flask(__name__)
# app.secret_key = 'secret'  # Required for sessions

# ENCODINGS_FILE = 'face_encodings.pkl'
# ATTENDANCE_FILE = 'attendance.csv'
# HISTORY_FILE = 'attendance_history.csv'

# def load_encodings():
#     if os.path.exists(ENCODINGS_FILE):
#         with open(ENCODINGS_FILE, 'rb') as f:
#             encodings = pickle.load(f)
#         print(f"Loaded encodings for {len(encodings)} users: {list(encodings.keys())}")
#         return encodings
#     print("No encodings file found, starting fresh.")
#     return {}

# def save_encodings(data):
#     with open(ENCODINGS_FILE, 'wb') as f:
#         pickle.dump(data, f)
#     print(f"Saved encodings for {len(data)} users: {list(data.keys())}")

# def read_attendance():
#     if not os.path.exists(ATTENDANCE_FILE):
#         return []
#     with open(ATTENDANCE_FILE, 'r') as f:
#         lines = f.readlines()
#     return [line.strip().split(',') for line in lines]

# def read_history():
#     if not os.path.exists(HISTORY_FILE):
#         return []
#     with open(HISTORY_FILE, 'r') as f:
#         lines = f.readlines()
#     return [line.strip().split(',') for line in lines]

# def write_attendance(records):
#     with open(ATTENDANCE_FILE, 'w') as f:
#         for r in records:
#             f.write(','.join(r) + '\n')

# def write_history(records):
#     with open(HISTORY_FILE, 'w') as f:
#         for r in records:
#             f.write(','.join(r) + '\n')

# def archive_old_records():
#     now = datetime.now()
#     attendance = read_attendance()
#     history = read_history()
#     new_attendance = []

#     for record in attendance:
#         if len(record) >= 4 and record[3]:  # Check if check-out exists
#             checkout_time = datetime.strptime(record[3], '%H:%M:%S')
#             record_date = datetime.strptime(record[1], '%Y-%m-%d')
#             full_time = datetime.combine(record_date.date(), checkout_time.time())
#             if (now - full_time).total_seconds() >= 12 * 3600:  # 12 hours in seconds
#                 history.append(record)
#             else:
#                 new_attendance.append(record)
#         else:
#             new_attendance.append(record)

#     write_attendance(new_attendance)
#     write_history(history)

# def log_attendance(name, action):
#     archive_old_records()
#     now = datetime.now()
#     date_str = now.strftime('%Y-%m-%d')
#     time_str = now.strftime('%H:%M:%S')

#     records = read_attendance()
#     today_records = [r for r in records if r[0] == name and r[1] == date_str]

#     if not today_records:
#         if action == 'checkin':
#             records.append([name, date_str, time_str, '', 'Present'])
#             write_attendance(records)
#             return True
#     else:
#         last_record = today_records[-1]
#         checkin_time = datetime.strptime(last_record[2], '%H:%M:%S') if last_record[2] else None
#         checkout_time = datetime.strptime(last_record[3], '%H:%M:%S') if last_record[3] else None

#         if action == 'checkout' and checkin_time and not checkout_time and (now - checkin_time) >= timedelta(minutes=1):
#             last_record[3] = time_str
#             last_record[4] = 'Present'
#             write_attendance(records)
#             return True
#         elif action == 'checkin' and not checkout_time:  # Only allow check-in if no check-out exists
#             if not checkin_time:  # Only allow initial check-in
#                 last_record[2] = time_str
#                 last_record[4] = 'Present'
#                 write_attendance(records)
#                 return True
#     return False

# # -------------------------
# # LOGIN PAGE (Home Page)
# # -------------------------
# @app.route('/', methods=['GET', 'POST'])
# def login():
#     if request.method == 'POST':
#         username = request.form['username']
#         password = request.form['password']

#         if username == 'admin' and password == 'admin123':
#             session['user'] = 'admin'
#             return redirect('/admin_panel')
#         elif username == 'user' and password == 'user123':
#             session['user'] = 'user'
#             return redirect('/user_panel')
#         else:
#             return 'Invalid username or password. Try again.'

#     return render_template('login.html')

# # -------------------------
# # ADMIN PANEL
# # -------------------------
# @app.route('/admin_panel', methods=['GET'])
# def admin_panel():
#     if session.get('user') != 'admin':
#         return redirect('/')
    
#     archive_old_records()
#     encodings = load_encodings()
#     names = list(encodings.keys())
#     attendance = read_attendance()
#     history = read_history()
#     today = datetime.now().strftime('%Y-%m-%d')
#     initial_data = {name: {'checkin': '', 'checkout': '', 'status': 'Absent', 'allow_checkout': True} for name in names}
    
#     # Filter attendance for today's date only
#     todays_attendance = [r for r in attendance if r[1] == today]
    
#     for name, date, checkin, checkout, status in attendance:
#         if date == today:
#             initial_data[name] = {
#                 'checkin': checkin,
#                 'checkout': checkout,
#                 'status': status,
#                 'allow_checkout': bool(checkin and not checkout)
#             }

#     # Prepare filter options for 2025
#     years = ["2025"]
#     months = list(range(1, 13))  # Months 1-12

#     # Get filter parameters from request
#     selected_year = request.args.get('year', '')
#     selected_month = request.args.get('month', '')
#     selected_date = request.args.get('date', '')

#     # Filter history based on selections
#     filtered_history = history
#     if selected_year:
#         filtered_history = [r for r in filtered_history if r[1].startswith(selected_year)]
#     if selected_month:
#         filtered_history = [r for r in filtered_history if r[1][5:7] == selected_month.zfill(2)]
#     if selected_date:
#         filtered_history = [r for r in filtered_history if r[1] == selected_date]

#     return render_template('admin_panel.html', 
#                           names=names, 
#                           attendance=todays_attendance,  
#                           initial_data=initial_data, 
#                           history=history,
#                           years=years,
#                           months=months,
#                           selected_year=selected_year,
#                           selected_month=selected_month,
#                           selected_date=selected_date,
#                           filtered_history=filtered_history)

# # -------------------------
# # ADD USER
# # -------------------------
# @app.route('/add_user', methods=['GET', 'POST'])
# def add_user():
#     if session.get('user') != 'admin':
#         return redirect('/')

#     if request.method == 'POST':
#         name = request.form['name']
#         encodings = load_encodings()
#         if name in encodings:
#             return "User already registered. Try a different name."

#         cap = cv2.VideoCapture(0)
#         face_encodings = []
#         for _ in range(5):  # Capture 5 frames for robustness
#             ret, frame = cap.read()
#             if ret and frame is not None:
#                 face_locations = face_recognition.face_locations(frame)
#                 if face_locations:
#                     encoding = face_recognition.face_encodings(frame, face_locations)[0]
#                     face_encodings.append(encoding)
#                     time.sleep(1)  # Delay to allow different poses
#             else:
#                 break
#         cap.release()
#         cv2.destroyAllWindows()

#         if face_encodings:
#             if len(face_encodings) < 3:  # Ensure at least 3 successful captures
#                 return "Insufficient face captures. Please try again with better conditions."
#             final_encoding = np.mean(face_encodings, axis=0)
#             encodings[name] = final_encoding
#             save_encodings(encodings)
#             return f"User {name} added successfully. Redirecting..."  # Feedback
#         return 'Face not detected. Try again with better lighting or angle.'

#     return '''
#         <form method="post">
#             <label>Enter Name:</label>
#             <input type="text" name="name" required>
#             <button type="submit">Capture & Register</button>
#         </form>
#     '''

# # -------------------------
# # USER PANEL (Attendance)
# # -------------------------
# @app.route('/user_panel')
# def user_panel():
#     if session.get('user') == 'admin' or session.get('user') is None:
#         return redirect('/')

#     archive_old_records()
#     known_faces = load_encodings()
#     cap = cv2.VideoCapture(0)
#     ret, frame = cap.read()
#     cap.release()

#     if ret and frame is not None:
#         face_locations = face_recognition.face_locations(frame)
#         if face_locations:
#             face_encodings = face_recognition.face_encodings(frame, face_locations)
#             for face_encoding in face_encodings:
#                 print(f"Comparing with known faces: {list(known_faces.keys())}")
#                 for name, known_encoding in known_faces.items():
#                     matches = face_recognition.compare_faces([known_encoding], face_encoding, tolerance=0.6)
#                     distances = face_recognition.face_distance([known_encoding], face_encoding)
#                     print(f"Distance for {name}: {distances[0]}")
#                     if np.any(matches):
#                         print(f"Match found for {name}")
#                         attendance = read_attendance()
#                         today = datetime.now().strftime('%Y-%m-%d')
#                         today_records = [r for r in attendance if r[0] == name and r[1] == today]
#                         now = datetime.now()

#                         if not today_records:
#                             if log_attendance(name, 'checkin'):
#                                 return render_template('user_panel.html', name=name, action='checked in', known_faces=known_faces)
#                             return "Error logging check-in"
#                         else:
#                             last_record = today_records[-1]
#                             checkin_time = datetime.strptime(last_record[2], '%H:%M:%S') if last_record[2] else None
#                             checkout_time = datetime.strptime(last_record[3], '%H:%M:%S') if last_record[3] else None

#                             if checkout_time:
#                                 return render_template('user_panel.html', name=name, action='Attendance complete. No further check-in allowed today.', known_faces=known_faces)
#                             elif checkin_time and not checkout_time:
#                                 time_since_checkin = now - checkin_time
#                                 if time_since_checkin < timedelta(minutes=1):
#                                     remaining = timedelta(minutes=1) - time_since_checkin
#                                     return render_template('user_panel.html', name=name, action=f"Please wait {remaining.seconds // 60} minute(s) and {remaining.seconds % 60} second(s) to check out.", known_faces=known_faces)
#                                 if log_attendance(name, 'checkout'):
#                                     return render_template('user_panel.html', name=name, action='checked out', known_faces=known_faces)
#                             else:
#                                 return render_template('user_panel.html', name=name, action='Invalid attendance state.', known_faces=known_faces)

#         return render_template('user_panel.html', known_faces=known_faces)
#     return render_template('user_panel.html', known_faces=known_faces)

# # -------------------------
# # DELETE USER
# # -------------------------
# @app.route('/delete_user', methods=['GET'])
# def delete_user():
#     if session.get('user') != 'admin':
#         return redirect('/')

#     name = request.args.get('name', '')
#     if not name:
#         return "No user specified for deletion."

#     encodings = load_encodings()
#     if name in encodings:
#         del encodings[name]
#         save_encodings(encodings)
#         # Remove attendance records for the deleted user
#         attendance = read_attendance()
#         updated_attendance = [r for r in attendance if r[0] != name]
#         write_attendance(updated_attendance)
#         # Remove history records for the deleted user
#         history = read_history()
#         updated_history = [r for r in history if r[0] != name]
#         write_history(updated_history)
#         return redirect('/admin_panel')
#     return f"User {name} not found."

# # -------------------------
# # LOGOUT
# # -------------------------
# @app.route('/logout')
# def logout():
#     session.pop('user', None)
#     return redirect('/')

# # -------------------------
# # MARK ATTENDANCE
# # -------------------------
# @app.route('/mark_attendance', methods=['POST'])
# def mark_attendance():
#     archive_old_records()
#     name = request.form['mark_user']
#     status = request.form[f'status_{name}']
#     date_str = datetime.now().strftime('%Y-%m-%d')
#     checkin = request.form.get(f'checkin_{name}', '').strip()
#     checkout = request.form.get(f'checkout_{name}', '').strip()

#     records = read_attendance()
#     today_records = [r for r in records if r[0] == name and r[1] == date_str]
#     updated = False

#     if today_records:
#         last_record = today_records[-1]
#         if checkin and not last_record[2]:
#             last_record[2] = checkin + ':00'  # Append ':00' for form input
#             updated = True
#         elif checkout and last_record[2] and not last_record[3]:
#             last_record[3] = checkout + ':00'  # Append ':00' for form input
#             updated = True
#         last_record[4] = status
#     else:
#         records.append([name, date_str, checkin + ':00' if checkin else '', checkout + ':00' if checkout else '', status])

#     if updated or not today_records:
#         write_attendance(records)

#     return redirect('/admin_panel')

# # -------------------------
# # DOWNLOAD ATTENDANCE
# # -------------------------
# @app.route('/download_attendance')
# def download_attendance():
#     if session.get('user') != 'admin':
#         return redirect('/')
    
#     return send_file(
#         ATTENDANCE_FILE,
#         as_attachment=True,
#         download_name='attendance_records.csv',
#         mimetype='text/csv'
#     )

# # -------------------------
# # DELETE HISTORY
# # -------------------------
# @app.route('/delete_history', methods=['POST'])
# def delete_history():
#     if session.get('user') != 'admin':
#         return redirect('/')
    
#     date_to_delete = request.form.get('delete_date')
#     if date_to_delete:
#         history = read_history()
#         updated_history = [r for r in history if r[1] != date_to_delete]
#         write_history(updated_history)
    
#     return redirect('/admin_panel')

# if __name__ == '__main__':
#     app.run(debug=True)