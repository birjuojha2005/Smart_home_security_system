from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from pymongo import MongoClient
from bson import ObjectId
import bcrypt
import jwt
import datetime
import os
import smtplib
import base64
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from dotenv import load_dotenv
from datetime import timezone

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static', static_url_path='/static')
CORS(app)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'dev-secret-change-in-production')
app.config['MONGODB_URI'] = os.environ.get('MONGODB_URI')
app.config['MONGODB_DB_NAME'] = os.environ.get('MONGODB_DB_NAME', 'smart_home')
app.config['SMTP_SERVER'] = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
app.config['SMTP_PORT'] = int(os.environ.get('SMTP_PORT', 587))
app.config['SMTP_USERNAME'] = os.environ.get('SMTP_USERNAME', '')
app.config['SMTP_PASSWORD'] = os.environ.get('SMTP_PASSWORD', '')
app.config['SMTP_FROM'] = os.environ.get('SMTP_FROM', 'smarthome@security.com')

if not app.config['MONGODB_URI']:
    print("ERROR: MONGODB_URI not set in .env"); exit(1)

# MongoDB connection
try:
    client = MongoClient(app.config['MONGODB_URI'])
    client.admin.command('ping')
    print("Connected to MongoDB Atlas successfully")
    db = client[app.config['MONGODB_DB_NAME']]
except Exception as e:
    print(f"MongoDB connection failed: {e}"); exit(1)

# Collections
users_col = db['users']
events_col = db['security_events']
faces_col = db['faces']
notifications_col = db['notifications']
sensors_col = db['sensor_data']

# ==================== SMTP EMAIL SERVICE ====================
def send_email_notification(to_email, subject, html_body):
    """Send email alert via SMTP"""
    if not app.config['SMTP_USERNAME'] or not app.config['SMTP_PASSWORD']:
        print("SMTP not configured - skipping email")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = app.config['SMTP_FROM']
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(html_body, 'html'))
        server = smtplib.SMTP(app.config['SMTP_SERVER'], app.config['SMTP_PORT'])
        server.starttls()
        server.login(app.config['SMTP_USERNAME'], app.config['SMTP_PASSWORD'])
        server.sendmail(app.config['SMTP_FROM'], to_email, msg.as_string())
        server.quit()
        print(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False

# ==================== JWT AUTH ====================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = users_col.find_one({'_id': ObjectId(data['user_id'])})
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user = users_col.find_one({'_id': ObjectId(data['user_id'])})
            if not current_user:
                return jsonify({'error': 'User not found'}), 401
            if current_user['role'] != 'admin':
                return jsonify({'error': 'Admin access required'}), 403
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        return f(current_user, *args, **kwargs)
    return decorated

def generate_token(user):
    payload = {
        'user_id': str(user['_id']),
        'username': user['username'],
        'role': user['role'],
        'exp': datetime.datetime.now(timezone.utc) + datetime.timedelta(hours=24),
        'iat': datetime.datetime.now(timezone.utc)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

# ==================== LIVE SENSOR STATE ====================
live_sensors = {
    'flame': False, 'smoke': False, 'smoke_level': 0,
    'laser': False, 'ldr': False, 'ldr_value': 0,
    'door': False, 'buzzer': False, 'led': False,
    'servo_angle': 0, 'keypad_input': '',
    'last_update': None
}

# ==================== PAGE ROUTES ====================
@app.route('/')
@app.route('/index.html')
def home():
    return render_template('index.html')

@app.route('/login.html')
def login_page():
    return render_template('login.html')

@app.route('/register.html')
def register_page():
    return render_template('register.html')

@app.route('/admin.html')
def admin_page():
    return render_template('admin.html')

@app.route('/camera.html')
def camera_page():
    return render_template('camera.html')

# ==================== AUTH API ====================
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username', '')
        password = data.get('password', '')
        role = data.get('role', 'public')
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        user = users_col.find_one({'username': username, 'role': role})
        if not user or not bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
            return jsonify({'error': 'Invalid credentials'}), 401
        users_col.update_one({'_id': user['_id']}, {'$set': {'last_login': datetime.datetime.now(timezone.utc)}})
        token = generate_token(user)
        return jsonify({'token': token, 'role': user['role'], 'username': user['username'], 'message': 'Login successful'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        confirm = data.get('confirmPassword', '')
        role = data.get('role', 'public')
        if not username or not email or not password or not confirm:
            return jsonify({'error': 'All fields are required'}), 400
        if password != confirm:
            return jsonify({'error': 'Passwords do not match'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        if users_col.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 400
        if users_col.find_one({'email': email}):
            return jsonify({'error': 'Email already exists'}), 400
        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        result = users_col.insert_one({
            'username': username, 'email': email, 'password_hash': pw_hash,
            'role': role, 'created_at': datetime.datetime.now(timezone.utc),
            'last_login': datetime.datetime.now(timezone.utc)
        })
        return jsonify({'message': 'Registration successful', 'user_id': str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== USER CRUD (Admin) ====================
@app.route('/api/users', methods=['GET'])
@admin_required
def get_users(current_user):
    users = list(users_col.find({}, {'password_hash': 0}))
    for u in users:
        u['_id'] = str(u['_id'])
        if 'created_at' in u: u['created_at'] = u['created_at'].isoformat()
    return jsonify(users), 200

@app.route('/api/users/<user_id>', methods=['PUT'])
@admin_required
def update_user(current_user, user_id):
    try:
        data = request.get_json()
        update = {}
        if 'username' in data: update['username'] = data['username']
        if 'email' in data: update['email'] = data['email']
        if 'role' in data: update['role'] = data['role']
        if 'password' in data and data['password']:
            update['password_hash'] = bcrypt.hashpw(data['password'].encode('utf-8'), bcrypt.gensalt())
        if not update:
            return jsonify({'error': 'No fields to update'}), 400
        users_col.update_one({'_id': ObjectId(user_id)}, {'$set': update})
        return jsonify({'message': 'User updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(current_user, user_id):
    try:
        if str(current_user['_id']) == user_id:
            return jsonify({'error': 'Cannot delete yourself'}), 400
        users_col.delete_one({'_id': ObjectId(user_id)})
        return jsonify({'message': 'User deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== EVENTS API ====================
@app.route('/api/events', methods=['GET'])
def get_events():
    try:
        limit = int(request.args.get('limit', 20))
        event_type = request.args.get('type', '')
        query = {}
        if event_type: query['event_type'] = event_type
        events = list(events_col.find(query).sort('timestamp', -1).limit(limit))
        for e in events:
            e['_id'] = str(e['_id'])
            if 'timestamp' in e: e['timestamp'] = e['timestamp'].isoformat()
        return jsonify(events), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events/<event_id>', methods=['DELETE'])
@admin_required
def delete_event(current_user, event_id):
    try:
        events_col.delete_one({'_id': ObjectId(event_id)})
        return jsonify({'message': 'Event deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/events/stats', methods=['GET'])
def get_event_stats():
    try:
        today_start = datetime.datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        total = events_col.count_documents({})
        today = events_col.count_documents({'timestamp': {'$gte': today_start}})
        alerts = events_col.count_documents({
            'event_type': {'$in': ['fire_detected', 'smoke_detected', 'intruder_detected', 'unauthorized_access']}
        })
        unread = notifications_col.count_documents({'status': 'pending'})
        return jsonify({'totalEvents': total, 'todayEvents': today, 'alertCount': alerts, 'unreadNotifications': unread}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== FACES API ====================
@app.route('/api/faces', methods=['GET'])
@admin_required
def get_faces(current_user):
    faces = list(faces_col.find({}))
    for f in faces:
        f['_id'] = str(f['_id'])
        if 'user_id' in f: f['user_id'] = str(f['user_id'])
        if 'created_at' in f: f['created_at'] = f['created_at'].isoformat()
    return jsonify(faces), 200

@app.route('/api/faces/authorized', methods=['GET'])
def get_authorized_faces():
    faces = list(faces_col.find({'is_authorized': True}))
    for f in faces:
        f['_id'] = str(f['_id'])
        if 'user_id' in f: f['user_id'] = str(f['user_id'])
    return jsonify(faces), 200

@app.route('/api/faces', methods=['POST'])
@admin_required
def add_face(current_user):
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        is_auth = data.get('is_authorized', True)
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        face = {
            'user_id': current_user['_id'],
            'name': name,
            'is_authorized': is_auth,
            'face_encoding': data.get('face_encoding', []),
            'created_at': datetime.datetime.now(timezone.utc)
        }
        result = faces_col.insert_one(face)
        events_col.insert_one({
            'event_type': 'face_registered', 'description': f'Face registered: {name}',
            'processed': True, 'notified': False, 'timestamp': datetime.datetime.now(timezone.utc)
        })
        return jsonify({'message': 'Face added', 'face_id': str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/faces/<face_id>', methods=['PUT'])
@admin_required
def update_face(current_user, face_id):
    try:
        data = request.get_json()
        update = {}
        if 'name' in data: update['name'] = data['name']
        if 'is_authorized' in data: update['is_authorized'] = data['is_authorized']
        if not update:
            return jsonify({'error': 'No fields to update'}), 400
        faces_col.update_one({'_id': ObjectId(face_id)}, {'$set': update})
        return jsonify({'message': 'Face updated'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/faces/<face_id>', methods=['DELETE'])
@admin_required
def delete_face(current_user, face_id):
    try:
        faces_col.delete_one({'_id': ObjectId(face_id)})
        return jsonify({'message': 'Face deleted'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ADMIN STATS ====================
@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def get_admin_stats(current_user):
    try:
        today_start = datetime.datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        total_users = users_col.count_documents({})
        auth_faces = faces_col.count_documents({'is_authorized': True})
        total_events = events_col.count_documents({})
        today_events = events_col.count_documents({'timestamp': {'$gte': today_start}})
        alert_count = events_col.count_documents({
            'event_type': {'$in': ['fire_detected', 'smoke_detected', 'intruder_detected', 'unauthorized_access']}
        })
        unread = notifications_col.count_documents({'status': 'pending'})
        return jsonify({
            'totalUsers': total_users, 'authorizedFaces': auth_faces,
            'totalEvents': total_events, 'todayEvents': today_events,
            'alertCount': alert_count, 'unreadNotifications': unread,
            'systemStatus': 'Online'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== NOTIFICATIONS API ====================
@app.route('/api/notifications/send', methods=['POST'])
@admin_required
def send_notification(current_user):
    try:
        data = request.get_json()
        user_id = data.get('user_id', '')
        subject = data.get('subject', 'Smart Home Alert')
        message = data.get('message', '')
        if not user_id or not message:
            return jsonify({'error': 'User and message required'}), 400
        target_user = users_col.find_one({'_id': ObjectId(user_id)})
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
        email_sent = False
        if target_user.get('email'):
            html = f"""<div style="font-family:Arial;max-width:600px;margin:0 auto;padding:20px;">
                <div style="background:linear-gradient(135deg,#1a1a2e,#16213e);padding:20px;border-radius:10px 10px 0 0;">
                    <h2 style="color:white;margin:0;">Smart Home Security</h2>
                </div>
                <div style="background:#f5f7fa;padding:20px;border-radius:0 0 10px 10px;">
                    <h3>{subject}</h3><p>{message}</p>
                    <hr><p style="color:#999;font-size:12px;">This is an automated alert from Smart Home Security System</p>
                </div></div>"""
            email_sent = send_email_notification(target_user['email'], subject, html)
        notifications_col.insert_one({
            'user_id': ObjectId(user_id), 'type': 'email',
            'subject': subject, 'message': message,
            'status': 'sent' if email_sent else 'pending',
            'sent_at': datetime.datetime.now(timezone.utc)
        })
        return jsonify({'message': 'Notification sent' if email_sent else 'Notification saved (email failed)'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/notifications', methods=['GET'])
@admin_required
def get_notifications(current_user):
    notifs = list(notifications_col.find({}).sort('sent_at', -1).limit(50))
    for n in notifs:
        n['_id'] = str(n['_id'])
        n['user_id'] = str(n['user_id'])
        if 'sent_at' in n: n['sent_at'] = n['sent_at'].isoformat()
    return jsonify(notifs), 200

# ==================== SENSOR / HARDWARE API ====================
@app.route('/api/sensors/update', methods=['POST'])
def update_sensors():
    """ESP32/Arduino posts sensor data here"""
    try:
        data = request.get_json()
        global live_sensors
        for key in live_sensors:
            if key in data and key != 'last_update':
                live_sensors[key] = data[key]
        live_sensors['last_update'] = datetime.datetime.now(timezone.utc).isoformat()

        # Store sensor reading
        sensors_col.insert_one({
            'data': {k: v for k, v in live_sensors.items() if k != 'last_update'},
            'timestamp': datetime.datetime.now(timezone.utc)
        })

        # Auto-alerts: Fire detected
        if data.get('flame'):
            events_col.insert_one({
                'event_type': 'fire_detected', 'description': 'Flame sensor triggered! Fire detected!',
                'confidence': 1.0, 'processed': True, 'notified': True,
                'timestamp': datetime.datetime.now(timezone.utc)
            })
            # Activate buzzer and LED
            live_sensors['buzzer'] = True
            live_sensors['led'] = True
            # Email ALL registered users
            for user in users_col.find({'email': {'$exists': True, '$ne': None, '$nin': ['', 'null']}}):
                if user.get('email'):
                    send_email_notification(user['email'], 'FIRE ALERT!',
                        '<h2 style="color:red;">FIRE DETECTED!</h2><p>Flame sensor has been triggered. Take immediate action!</p>')

        # Auto-alerts: Smoke detected
        if data.get('smoke'):
            level = data.get('smoke_level', 0)
            events_col.insert_one({
                'event_type': 'smoke_detected', 'description': f'Smoke detected! MQ-2 Level: {level} ppm',
                'confidence': 1.0, 'processed': True, 'notified': True,
                'timestamp': datetime.datetime.now(timezone.utc)
            })
            # Activate buzzer and LED
            live_sensors['buzzer'] = True
            live_sensors['led'] = True
            # Email ALL registered users
            for user in users_col.find({'email': {'$exists': True, '$ne': None, '$nin': ['', 'null']}}):
                if user.get('email'):
                    send_email_notification(user['email'], 'SMOKE ALERT!',
                        f'<h2 style="color:orange;">SMOKE DETECTED!</h2><p>MQ-2 sensor level: {level} ppm</p>')

        # Auto-alerts: Intruder (laser broken)
        if data.get('laser'):
            events_col.insert_one({
                'event_type': 'intruder_detected', 'description': 'Laser beam broken! Possible intruder detected!',
                'confidence': 0.9, 'processed': True, 'notified': True,
                'timestamp': datetime.datetime.now(timezone.utc)
            })
            # Activate buzzer and LED
            live_sensors['buzzer'] = True
            live_sensors['led'] = True
            # Email ALL registered users
            for user in users_col.find({'email': {'$exists': True, '$ne': None, '$nin': ['', 'null']}}):
                if user.get('email'):
                    send_email_notification(user['email'], 'INTRUDER ALERT!',
                        '<h2 style="color:red;">INTRUDER DETECTED!</h2><p>Laser security beam has been broken!</p>')

        return jsonify({'status': 'ok', 'sensors': live_sensors}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/sensors/latest', methods=['GET'])
def get_sensors():
    """Get latest sensor readings"""
    return jsonify(live_sensors), 200

@app.route('/api/sensors/history', methods=['GET'])
@admin_required
def get_sensor_history(current_user):
    """Get sensor data history"""
    limit = int(request.args.get('limit', 50))
    history = list(sensors_col.find({}).sort('timestamp', -1).limit(limit))
    for h in history:
        h['_id'] = str(h['_id'])
        if 'timestamp' in h: h['timestamp'] = h['timestamp'].isoformat()
    return jsonify(history), 200

# ==================== HARDWARE CONTROL API ====================
@app.route('/api/hardware/door', methods=['POST'])
@admin_required
def control_door(current_user):
    try:
        action = request.get_json().get('action', 'lock')
        live_sensors['door'] = action == 'unlock'
        events_col.insert_one({
            'event_type': 'door_unlocked' if action == 'unlock' else 'door_locked',
            'description': f'Door {action}ed by {current_user["username"]}',
            'processed': True, 'notified': False,
            'timestamp': datetime.datetime.now(timezone.utc)
        })
        return jsonify({'message': f'Door {action}ed successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/hardware/buzzer', methods=['POST'])
@admin_required
def control_buzzer(current_user):
    try:
        action = request.get_json().get('action', 'off')
        live_sensors['buzzer'] = action == 'on'
        events_col.insert_one({
            'event_type': 'buzzer_on' if action == 'on' else 'buzzer_off',
            'description': f'Buzzer turned {action} by {current_user["username"]}',
            'processed': True, 'notified': False,
            'timestamp': datetime.datetime.now(timezone.utc)
        })
        return jsonify({'message': f'Buzzer turned {action}'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/hardware/led', methods=['POST'])
@admin_required
def control_led(current_user):
    try:
        action = request.get_json().get('action', 'off')
        live_sensors['led'] = action == 'on'
        return jsonify({'message': f'LED turned {action}'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/hardware/servo', methods=['POST'])
@admin_required
def control_servo(current_user):
    try:
        angle = request.get_json().get('angle', 0)
        angle = max(0, min(180, int(angle)))
        live_sensors['servo_angle'] = angle
        events_col.insert_one({
            'event_type': 'servo_moved', 'description': f'Servo moved to {angle} degrees by {current_user["username"]}',
            'processed': True, 'notified': False,
            'timestamp': datetime.datetime.now(timezone.utc)
        })
        return jsonify({'message': f'Servo set to {angle} degrees'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== CAMERA / FACE RECOGNITION ====================
@app.route('/api/camera/detect', methods=['POST'])
@admin_required
def detect_face(current_user):
    """Receive webcam frame and detect/recognize faces"""
    try:
        data = request.get_json()
        image_data = data.get('image_data', '')

        if not image_data:
            return jsonify({'error': 'No image data'}), 400

        # Decode base64 image
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        # Default: treat as unauthorized since recognition is unavailable
        # This ensures safety - unknown faces are ALWAYS flagged as unauthorized
        is_authorized = False
        match_name = 'Unknown'

        try:
            import face_recognition
            import numpy as np
            from PIL import Image

            # Process image
            img_bytes = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(img_bytes))
            img = img.convert('RGB')
            img_array = np.array(img)

            # Find faces
            face_locations = face_recognition.face_locations(img_array)
            face_encodings = face_recognition.face_encodings(img_array, face_locations)

            if not face_locations:
                events_col.insert_one({
                    'event_type': 'face_detected', 'description': 'No face detected in frame',
                    'processed': True, 'notified': False,
                    'timestamp': datetime.datetime.now(timezone.utc)
                })
                return jsonify({'authorized': False, 'message': 'No face detected', 'faces': []}), 200

            # Compare with known faces
            known_faces = list(faces_col.find({'is_authorized': True, 'face_encoding': {'$ne': []}}))
            results = []

            for encoding in face_encodings:
                match_name = 'Unknown'
                is_authorized = False
                for known in known_faces:
                    if known.get('face_encoding') and len(known['face_encoding']) == 128:
                        known_encoding = np.array(known['face_encoding'])
                        match = face_recognition.compare_faces([known_encoding], encoding, tolerance=0.6)
                        if match[0]:
                            match_name = known['name']
                            is_authorized = True
                            break

                results.append({'name': match_name, 'authorized': is_authorized})

            overall_auth = any(r['authorized'] for r in results)

        except ImportError:
            # face_recognition not installed - cannot verify identity, treat as unauthorized
            print('Warning: face_recognition not installed, treating as unauthorized')
            results = [{'name': 'Unknown', 'authorized': False}]
            overall_auth = False

        except Exception as e:
            # face_recognition installed but broken - cannot verify identity, treat as unauthorized
            print(f'Warning: Face recognition failed ({e}), treating as unauthorized')
            results = [{'name': 'Unknown', 'authorized': False}]
            overall_auth = False

        # ---- Handle unauthorized detection ----
        if not overall_auth:
            # Log unauthorized access event
            events_col.insert_one({
                'event_type': 'unauthorized_access',
                'description': 'Unauthorized/Unknown person detected by camera!',
                'processed': True, 'notified': True,
                'timestamp': datetime.datetime.now(timezone.utc)
            })

            # Activate buzzer and LED on hardware
            live_sensors['buzzer'] = True
            live_sensors['led'] = True

            # Send email alerts to ALL registered users (admin + public)
            all_users = users_col.find({'email': {'$exists': True, '$ne': None, '$nin': ['', 'null']}})
            for user in all_users:
                if user.get('email'):
                    send_email_notification(user['email'],
                        'SECURITY ALERT: Unauthorized Person Detected!',
                        '<div style="font-family:Arial;max-width:600px;margin:0 auto;padding:20px">'
                        '<div style="background:linear-gradient(135deg,#c0392b,#e74c3c);padding:20px;border-radius:10px 10px 0 0">'
                        '<h2 style="color:white;margin:0">&#9888; SECURITY ALERT</h2></div>'
                        '<div style="background:#f5f7fa;padding:20px;border-radius:0 0 10px 10px">'
                        '<h3>Unauthorized Person Detected!</h3>'
                        '<p>An unknown or unauthorized person was detected by the security camera.</p>'
                        '<p><strong>Time:</strong> ' + datetime.datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') + '</p>'
                        '<p style="color:red;font-weight:bold">Buzzer and LED have been activated.</p>'
                        '<hr><p style="color:#999;font-size:12px">Smart Home Security System - Automated Alert</p></div></div>')

            return jsonify({
                'authorized': False,
                'message': 'Unauthorized person detected! Alarm activated. Alerts sent.',
                'faces': results
            }), 200

        else:
            # Authorized face detected
            events_col.insert_one({
                'event_type': 'face_detected',
                'description': f'Authorized face recognized: {", ".join(r["name"] for r in results if r["authorized"])}',
                'processed': True, 'notified': False,
                'timestamp': datetime.datetime.now(timezone.utc)
            })
            return jsonify({
                'authorized': True,
                'message': f'Authorized: {", ".join(r["name"] for r in results if r["authorized"])}',
                'faces': results
            }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/camera/register-face', methods=['POST'])
@admin_required
def register_face_from_camera(current_user):
    """Register a new face from webcam capture"""
    try:
        data = request.get_json()
        image_data = data.get('image_data', '')
        name = data.get('name', '').strip()
        is_authorized = data.get('is_authorized', True)

        if not name:
            return jsonify({'error': 'Name is required'}), 400

        face_encoding = []

        try:
            import face_recognition
            import numpy as np
            from PIL import Image

            if ',' in image_data:
                image_data = image_data.split(',')[1]
            img_bytes = base64.b64decode(image_data)
            img = Image.open(io.BytesIO(img_bytes))
            img = img.convert('RGB')
            img_array = np.array(img)

            encodings = face_recognition.face_encodings(img_array)
            if encodings:
                face_encoding = encodings[0].tolist()
            else:
                # No face found, but still register with empty encoding
                print('Warning: No face encoding found in image. Registering without encoding.')
        except ImportError:
            print('Warning: face_recognition library not installed. Registering without encoding.')
        except Exception as e:
            print(f'Warning: Face encoding failed ({e}). Registering without encoding.')

        result = faces_col.insert_one({
            'user_id': current_user['_id'],
            'name': name,
            'face_encoding': face_encoding,
            'is_authorized': is_authorized,
            'created_at': datetime.datetime.now(timezone.utc)
        })

        return jsonify({'message': f'Face registered for {name}', 'face_id': str(result.inserted_id)}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== KEYPAD API ====================
@app.route('/api/keypad', methods=['POST'])
def keypad_input():
    """Receive keypad input from Arduino"""
    try:
        data = request.get_json()
        code = data.get('code', '')
        live_sensors['keypad_input'] = code

        # Check if code matches (simple PIN check - can be expanded)
        # For now, code "1234" unlocks the door
        if code == '1234':
            live_sensors['door'] = True
            events_col.insert_one({
                'event_type': 'door_unlocked', 'description': f'Door unlocked via keypad (code: {"*" * len(code)})',
                'processed': True, 'notified': False,
                'timestamp': datetime.datetime.now(timezone.utc)
            })
            return jsonify({'status': 'unlocked', 'message': 'Correct code - door unlocked'}), 200
        else:
            events_col.insert_one({
                'event_type': 'unauthorized_access', 'description': f'Wrong keypad code entered',
                'processed': True, 'notified': False,
                'timestamp': datetime.datetime.now(timezone.utc)
            })
            # Activate buzzer and LED on wrong keypad code
            live_sensors['buzzer'] = True
            live_sensors['led'] = True
            # Email ALL registered users
            for user in users_col.find({'email': {'$exists': True, '$ne': None, '$nin': ['', 'null']}}):
                if user.get('email'):
                    send_email_notification(user['email'], 'WRONG KEYPAD CODE',
                        '<div style="font-family:Arial;max-width:600px;margin:0 auto;padding:20px">'
                        '<div style="background:linear-gradient(135deg,#e67e22,#d35400);padding:20px;border-radius:10px 10px 0 0">'
                        '<h2 style="color:white;margin:0">&#9888; KEYPAD ALERT</h2></div>'
                        '<div style="background:#f5f7fa;padding:20px;border-radius:0 0 10px 10px">'
                        '<h3>Wrong Keypad Code Entered!</h3>'
                        '<p>Someone entered an incorrect code on the keypad. Possible unauthorized access attempt.</p>'
                        '<p><strong>Time:</strong> ' + datetime.datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') + '</p>'
                        '<p style="color:red;font-weight:bold">Buzzer and LED have been activated.</p>'
                        '<hr><p style="color:#999;font-size:12px">Smart Home Security System - Automated Alert</p></div></div>')
            return jsonify({'status': 'denied', 'message': 'Wrong code'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# ==================== STARTUP ====================
if __name__ == '__main__':
    # Create default admin user
    if users_col.count_documents({}) == 0:
        admin_pw = bcrypt.hashpw('admin123'.encode('utf-8'), bcrypt.gensalt())
        users_col.insert_one({
            'username': 'admin', 'password_hash': admin_pw, 'role': 'admin',
            'email': 'admin@smarthome.com',
            'created_at': datetime.datetime.now(timezone.utc),
            'last_login': datetime.datetime.now(timezone.utc)
        })
        print('Created default admin: admin / admin123')

        public_pw = bcrypt.hashpw('user123'.encode('utf-8'), bcrypt.gensalt())
        users_col.insert_one({
            'username': 'user', 'password_hash': public_pw, 'role': 'public',
            'email': 'user@smarthome.com',
            'created_at': datetime.datetime.now(timezone.utc),
            'last_login': datetime.datetime.now(timezone.utc)
        })
        print('Created default user: user / user123')

    print("\n========================================")
    print("  Smart Home Security System Running")
    print("  http://localhost:5000")
    print("========================================\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
