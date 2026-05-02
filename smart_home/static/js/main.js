// Smart Home Security - Complete Application Logic

let cameraStream = null;
let sensorPollingInterval = null;

// ==================== API HELPERS ====================
async function apiGet(url) {
    const headers = getAuthHeader();
    headers['Content-Type'] = 'application/json';
    const res = await fetch(url, { headers });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
}

async function apiPost(url, body) {
    const headers = getAuthHeader();
    headers['Content-Type'] = 'application/json';
    const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
}

async function apiPut(url, body) {
    const headers = getAuthHeader();
    headers['Content-Type'] = 'application/json';
    const res = await fetch(url, { method: 'PUT', headers, body: JSON.stringify(body) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
}

async function apiDelete(url) {
    const headers = getAuthHeader();
    const res = await fetch(url, { method: 'DELETE', headers });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
}

// ==================== NAV ====================
function updateNavForAuth() {
    const loggedIn = isAuthenticated();
    const loginBtn = document.getElementById('loginNavBtn');
    const logoutBtn = document.getElementById('logoutNavBtn');
    if (loginBtn) loginBtn.style.display = loggedIn ? 'none' : '';
    if (logoutBtn) logoutBtn.style.display = loggedIn ? '' : 'none';
}

// ==================== FORMATTERS ====================
function formatTime(ts) {
    if (!ts) return '--';
    try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

function formatEventType(type) {
    const map = {
        'face_detected': 'Face Detected', 'unauthorized_access': 'Unauthorized Access',
        'unknown_face': 'Unknown Face', 'system_alert': 'System Alert',
        'fire_detected': 'Fire Alert', 'smoke_detected': 'Smoke Alert',
        'intruder_detected': 'Intruder Alert', 'door_locked': 'Door Locked',
        'door_unlocked': 'Door Unlocked', 'sensor_reading': 'Sensor Reading',
        'face_registered': 'Face Registered', 'buzzer_on': 'Buzzer ON',
        'buzzer_off': 'Buzzer OFF', 'servo_moved': 'Servo Moved'
    };
    return map[type] || type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function isAlertType(type) {
    return ['fire_detected', 'smoke_detected', 'intruder_detected', 'unauthorized_access'].includes(type);
}

// ==================== SENSOR DISPLAY ====================
function updateSensorDisplay(data) {
    // Public dashboard sensors
    setSensorValue('flameValue', data.flame ? 'DETECTED!' : 'Normal', data.flame ? 'sensor-danger' : 'sensor-safe');
    setSensorValue('smokeValue', data.smoke ? `ALERT: ${data.smoke_level} ppm` : `${data.smoke_level || 0} ppm`, data.smoke ? 'sensor-danger' : 'sensor-safe');
    setSensorValue('laserValue', data.laser ? 'BROKEN - Intruder!' : 'Intact', data.laser ? 'sensor-danger' : 'sensor-safe');
    setSensorValue('ldrValue', `${data.ldr_value || 0} lux`, '');
    setSensorValue('doorStatus', data.door ? 'UNLOCKED' : 'LOCKED', data.door ? 'sensor-warning' : 'sensor-safe');
    setSensorValue('buzzerStatus', data.buzzer ? 'ALARM ON' : 'OFF', data.buzzer ? 'sensor-danger' : '');
    setSensorValue('ledStatus', data.led ? 'ON' : 'OFF', data.led ? 'sensor-safe' : '');

    // Sensor bars
    setBarWidth('flameBar', data.flame ? 100 : 0);
    setBarWidth('smokeBar', Math.min(100, (data.smoke_level || 0) / 10));
    setBarWidth('ldrBar', Math.min(100, (data.ldr_value || 0) / 10));

    // Alert classes on cards
    toggleCardAlert('flameCard', data.flame);
    toggleCardAlert('smokeCard', data.smoke);
    toggleCardAlert('laserCard', data.laser);

    // Admin sensors
    setSensorValue('adminFlame', data.flame ? 'DETECTED!' : 'Normal', data.flame ? 'sensor-danger' : 'sensor-safe');
    setSensorValue('adminSmoke', data.smoke ? `ALERT: ${data.smoke_level} ppm` : `${data.smoke_level || 0} ppm`, data.smoke ? 'sensor-danger' : 'sensor-safe');
    setSensorValue('adminLaser', data.laser ? 'BROKEN!' : 'Intact', data.laser ? 'sensor-danger' : 'sensor-safe');
    setSensorValue('adminLdr', `${data.ldr_value || 0} lux`, '');
    setSensorValue('adminDoor', data.door ? 'UNLOCKED' : 'LOCKED', data.door ? 'sensor-warning' : 'sensor-safe');
    setSensorValue('adminBuzzer', data.buzzer ? 'ALARM ON' : 'OFF', data.buzzer ? 'sensor-danger' : '');
}

function setSensorValue(id, text, className) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.className = 'sensor-value' + (className ? ' ' + className : '');
}

function setBarWidth(id, percent) {
    const el = document.getElementById(id);
    if (el) el.style.width = Math.max(0, Math.min(100, percent)) + '%';
}

function toggleCardAlert(id, isAlert) {
    const el = document.getElementById(id);
    if (!el) return;
    if (isAlert) el.classList.add('card-alert');
    else el.classList.remove('card-alert');
}

function updateServoDisplay(val) {
    const el = document.getElementById('servoStatus');
    if (el) el.textContent = val + '\u00B0';
}

// ==================== PAGE: DASHBOARD ====================
async function loadDashboard() {
    // Load events
    try {
        const events = await apiGet('/api/events?limit=8');
        const el = document.getElementById('eventsList');
        if (!events.length) {
            el.innerHTML = '<p class="empty-state">No security events recorded yet</p>';
        } else {
            el.innerHTML = events.map(e => `
                <div class="event-item ${isAlertType(e.event_type) ? 'alert' : ''}">
                    <div class="event-time">${formatTime(e.timestamp)}</div>
                    <div class="event-type">${formatEventType(e.event_type)}</div>
                    <div class="event-desc">${e.description || 'No details'}</div>
                </div>
            `).join('');
        }
    } catch (e) {
        const el = document.getElementById('eventsList');
        if (el) el.innerHTML = '<p class="empty-state">Unable to load events</p>';
    }

    // Load authorized faces
    try {
        const faces = await apiGet('/api/faces/authorized');
        const fg = document.getElementById('facesGrid');
        const fc = document.getElementById('faceCount');
        if (fc) fc.textContent = faces.length;
        if (!faces.length) {
            if (fg) fg.innerHTML = '<p class="empty-state">No authorized faces registered</p>';
        } else {
            if (fg) fg.innerHTML = faces.map(f => `
                <div class="face-card">
                    <div class="face-avatar">&#128100;</div>
                    <div class="face-name">${f.name}</div>
                    <div class="face-status authorized">Authorized</div>
                </div>
            `).join('');
        }
    } catch (e) {
        const fg = document.getElementById('facesGrid');
        if (fg) fg.innerHTML = '<p class="empty-state">Unable to load faces</p>';
    }

    // Load event stats
    try {
        const stats = await apiGet('/api/events/stats');
        const te = document.getElementById('todayEvents');
        const ac = document.getElementById('alertCount');
        if (te) te.textContent = stats.todayEvents || 0;
        if (ac) ac.textContent = stats.alertCount || 0;
    } catch (e) { /* ignore */ }

    // Load sensor data
    try {
        const sensors = await apiGet('/api/sensors/latest');
        updateSensorDisplay(sensors);
    } catch (e) { /* sensors not available yet */ }

    const lu = document.getElementById('lastUpdated');
    if (lu) lu.textContent = 'Last updated: ' + new Date().toLocaleTimeString();

    // Start sensor polling
    startSensorPolling();
}

function startSensorPolling() {
    if (sensorPollingInterval) clearInterval(sensorPollingInterval);
    sensorPollingInterval = setInterval(async () => {
        try {
            const sensors = await apiGet('/api/sensors/latest');
            updateSensorDisplay(sensors);
            const lu = document.getElementById('lastUpdated');
            if (lu) lu.textContent = 'Last updated: ' + new Date().toLocaleTimeString();
            // Show alarm banner on camera page if buzzer/LED active
            const alarmBanner = document.getElementById('alarmBanner');
            if (alarmBanner) {
                alarmBanner.style.display = (sensors.buzzer || sensors.led) ? 'block' : 'none';
            }
        } catch (e) { /* ignore polling errors */ }
    }, 3000);
}

// ==================== PAGE: CAMERA ====================
async function startCamera() {
    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: 640, height: 480 }
        });
        document.getElementById('videoFeed').srcObject = cameraStream;
        document.getElementById('startCamBtn').disabled = true;
        document.getElementById('stopCamBtn').disabled = false;
        document.getElementById('captureBtn').disabled = false;
        document.getElementById('camStatusDot').className = 'status-dot online';
        document.getElementById('camStatusText').textContent = 'Camera Online';
    } catch (e) {
        alert('Camera access denied. Please allow camera permissions.');
    }
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(t => t.stop());
        cameraStream = null;
    }
    document.getElementById('videoFeed').srcObject = null;
    document.getElementById('startCamBtn').disabled = false;
    document.getElementById('stopCamBtn').disabled = true;
    document.getElementById('captureBtn').disabled = true;
    document.getElementById('camStatusDot').className = 'status-dot offline';
    document.getElementById('camStatusText').textContent = 'Camera Offline';
}

async function captureAndDetect() {
    const video = document.getElementById('videoFeed');
    const canvas = document.getElementById('captureCanvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const imageData = canvas.toDataURL('image/jpeg', 0.8);

    const rp = document.getElementById('detectionResult');
    rp.innerHTML = '<div style="text-align:center;padding:1rem;"><div class="loading-spinner"></div><p>Analyzing face...</p></div>';

    try {
        const result = await apiPost('/api/camera/detect', { image_data: imageData });
        const auth = result.authorized;
        let alarmHtml = '';
        if (!auth) {
            alarmHtml = '<div style="margin-top:0.8rem;padding:0.6rem;background:rgba(231,76,60,0.15);border:1px solid rgba(231,76,60,0.3);border-radius:6px;font-size:0.85rem;">'
                + '<p style="color:#e74c3c;font-weight:600;margin-bottom:0.3rem;">&#128276; Alarm Activated!</p>'
                + '<p style="color:rgba(255,255,255,0.7)">Buzzer and LED turned ON. Email alerts sent to all registered users.</p>'
                + '</div>';
        }
        rp.innerHTML = `
            <div class="detection-result ${auth ? 'authorized' : 'unauthorized'}">
                <div class="detection-icon">${auth ? '&#9989;' : '&#9888;&#65039;'}</div>
                <div class="detection-info">
                    <h3>${auth ? 'Authorized Person' : 'Unknown Person Detected'}</h3>
                    <p>${result.message}</p>
                    <p class="detection-time">${new Date().toLocaleString()}</p>
                    ${alarmHtml}
                </div>
            </div>`;

        // Show face box overlay
        const fb = document.getElementById('faceBox');
        const fl = document.getElementById('faceLabel');
        if (fb && fl) {
            fb.style.display = 'block';
            fl.textContent = auth ? 'Authorized' : 'Unknown';
            fl.className = 'face-label ' + (auth ? 'auth' : 'unauth');
            fb.style.borderColor = auth ? '#27ae60' : '#e74c3c';
            setTimeout(() => { fb.style.display = 'none'; }, 4000);
        }

        addToDetectionHistory(auth, result.message);
    } catch (e) {
        rp.innerHTML = `<div class="detection-result unauthorized"><p>Detection failed: ${e.message}</p></div>`;
    }
}

async function registerFaceFromCamera() {
    const video = document.getElementById('videoFeed');
    if (!cameraStream) { alert('Start the camera first!'); return; }
    const name = document.getElementById('newFaceName').value.trim();
    if (!name) { alert('Please enter a name!'); return; }

    const canvas = document.getElementById('captureCanvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    canvas.getContext('2d').drawImage(video, 0, 0);
    const imageData = canvas.toDataURL('image/jpeg', 0.8);
    const isAuth = document.getElementById('newFaceAuth').value === 'true';

    try {
        const result = await apiPost('/api/camera/register-face', {
            image_data: imageData, name: name, is_authorized: isAuth
        });
        alert(`Face registered for ${name}!`);
        document.getElementById('newFaceName').value = '';
    } catch (e) {
        alert('Face registration failed: ' + e.message);
    }
}

function addToDetectionHistory(authorized, message) {
    const hd = document.getElementById('detectionHistory');
    if (!hd) return;
    const entry = document.createElement('div');
    entry.className = `event-item ${authorized ? '' : 'alert'}`;
    entry.innerHTML = `
        <div class="event-time">${new Date().toLocaleTimeString()}</div>
        <div class="event-type">${authorized ? '&#9989; Authorized' : '&#9888;&#65039; Unknown'}</div>
        <div class="event-desc">${message}</div>`;
    const empty = hd.querySelector('.empty-state');
    if (empty) empty.remove();
    hd.insertBefore(entry, hd.firstChild);
}

// ==================== PAGE: ADMIN ====================
async function loadAdminDashboard() {
    // Load stats
    try {
        const stats = await apiGet('/api/admin/stats');
        const ids = {
            'statUsers': 'totalUsers', 'statFaces': 'authorizedFaces',
            'statTodayEvents': 'todayEvents', 'statAlerts': 'alertCount'
        };
        for (const [elId, key] of Object.entries(ids)) {
            const el = document.getElementById(elId);
            if (el) el.textContent = stats[key] ?? '--';
        }
    } catch (e) { console.error('Stats error:', e); }

    // Load sensors for admin
    try {
        const sensors = await apiGet('/api/sensors/latest');
        updateSensorDisplay(sensors);
    } catch (e) { /* ignore */ }

    // Start sensor polling
    startSensorPolling();

    // Setup tabs
    setupAdminTabs();

    // Load initial tab data
    loadAdminUsers();
    setupAdminForms();
}

function setupAdminTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            this.classList.add('active');
            document.getElementById('tab-' + this.dataset.tab).classList.add('active');
            if (this.dataset.tab === 'users') loadAdminUsers();
            if (this.dataset.tab === 'faces') loadAdminFaces();
            if (this.dataset.tab === 'events') loadAdminEvents();
            if (this.dataset.tab === 'notifications') loadNotifyUsers();
        });
    });
}

async function loadAdminUsers() {
    try {
        const users = await apiGet('/api/users');
        const tb = document.getElementById('usersBody');
        if (!users.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-state">No users</td></tr>'; return; }
        tb.innerHTML = users.map(u => `<tr>
            <td>${u.username}</td><td>${u.email || '--'}</td>
            <td><span class="badge ${u.role === 'admin' ? 'badge-admin' : 'badge-public'}">${u.role}</span></td>
            <td>${formatTime(u.created_at)}</td>
            <td class="action-cell">
                <button class="btn-sm btn-edit" onclick="editUser('${u._id}','${u.username}','${u.email || ''}','${u.role}')">Edit</button>
                <button class="btn-sm btn-delete" onclick="deleteUser('${u._id}','${u.username}')">Del</button>
            </td></tr>`).join('');
    } catch (e) { console.error(e); }
}

async function loadAdminFaces() {
    try {
        const faces = await apiGet('/api/faces');
        const tb = document.getElementById('facesBody');
        if (!faces.length) { tb.innerHTML = '<tr><td colspan="4" class="empty-state">No faces registered</td></tr>'; return; }
        tb.innerHTML = faces.map(f => `<tr>
            <td>${f.name}</td>
            <td><span class="badge ${f.is_authorized ? 'badge-admin' : 'badge-danger'}">${f.is_authorized ? 'Authorized' : 'Not Auth'}</span></td>
            <td>${formatTime(f.created_at)}</td>
            <td class="action-cell">
                <button class="btn-sm btn-edit" onclick="toggleFaceAuth('${f._id}',${!f.is_authorized})">${f.is_authorized ? 'Revoke' : 'Auth'}</button>
                <button class="btn-sm btn-delete" onclick="deleteFace('${f._id}','${f.name}')">Del</button>
            </td></tr>`).join('');
    } catch (e) { console.error(e); }
}

async function loadAdminEvents() {
    try {
        const events = await apiGet('/api/events?limit=30');
        const tb = document.getElementById('eventsBody');
        const ec = document.getElementById('eventsCount');
        if (ec) ec.textContent = events.length + ' events';
        if (!events.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-state">No events</td></tr>'; return; }
        tb.innerHTML = events.map(e => `<tr class="${isAlertType(e.event_type) ? 'row-alert' : ''}">
            <td>${formatTime(e.timestamp)}</td>
            <td><span class="badge ${isAlertType(e.event_type) ? 'badge-danger' : 'badge-public'}">${formatEventType(e.event_type)}</span></td>
            <td>${e.description || '--'}</td>
            <td><span class="badge ${e.processed ? 'badge-admin' : 'badge-public'}">${e.processed ? 'Done' : 'Pending'}</span></td>
            <td class="action-cell"><button class="btn-sm btn-delete" onclick="deleteEvent('${e._id}')">Del</button></td></tr>`).join('');
    } catch (e) { console.error(e); }
}

async function loadNotifyUsers() {
    try {
        const users = await apiGet('/api/users');
        const sel = document.getElementById('notifyUser');
        if (sel) sel.innerHTML = users.map(u => `<option value="${u._id}">${u.username} (${u.email || 'no email'})</option>`).join('');
    } catch (e) { console.error(e); }
}

// ==================== ADMIN FORMS ====================
function setupAdminForms() {
    // Add User
    const auf = document.getElementById('addUserForm');
    if (auf) auf.addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            await apiPost('/api/register', {
                username: document.getElementById('newUsername').value,
                email: document.getElementById('newEmail').value,
                password: document.getElementById('newPassword').value,
                confirmPassword: document.getElementById('newPassword').value,
                role: document.getElementById('newRole').value
            });
            closeModal('addUserModal');
            loadAdminUsers();
            auf.reset();
        } catch (err) { alert(err.message); }
    });

    // Edit User
    const euf = document.getElementById('editUserForm');
    if (euf) euf.addEventListener('submit', async (e) => {
        e.preventDefault();
        const d = {
            username: document.getElementById('editUsername').value,
            email: document.getElementById('editEmail').value,
            role: document.getElementById('editRole').value
        };
        const pw = document.getElementById('editPassword').value;
        if (pw) d.password = pw;
        try {
            await apiPut('/api/users/' + document.getElementById('editUserId').value, d);
            closeModal('editUserModal');
            loadAdminUsers();
        } catch (err) { alert(err.message); }
    });

    // Add Face
    const aff = document.getElementById('addFaceForm');
    if (aff) aff.addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            await apiPost('/api/faces', {
                name: document.getElementById('faceName').value,
                is_authorized: document.getElementById('faceAuth').value === 'true'
            });
            closeModal('addFaceModal');
            loadAdminFaces();
            aff.reset();
        } catch (err) { alert(err.message); }
    });
}

// ==================== ADMIN ACTIONS ====================
function editUser(id, username, email, role) {
    document.getElementById('editUserId').value = id;
    document.getElementById('editUsername').value = username;
    document.getElementById('editEmail').value = email;
    document.getElementById('editRole').value = role;
    document.getElementById('editPassword').value = '';
    openModal('editUserModal');
}

async function deleteUser(id, name) {
    if (!confirm('Delete user "' + name + '"?')) return;
    try { await apiDelete('/api/users/' + id); loadAdminUsers(); }
    catch (e) { alert(e.message); }
}

async function toggleFaceAuth(id, v) {
    try { await apiPut('/api/faces/' + id, { is_authorized: v }); loadAdminFaces(); }
    catch (e) { alert(e.message); }
}

async function deleteFace(id, name) {
    if (!confirm('Delete face "' + name + '"?')) return;
    try { await apiDelete('/api/faces/' + id); loadAdminFaces(); }
    catch (e) { alert(e.message); }
}

async function deleteEvent(id) {
    if (!confirm('Delete this event?')) return;
    try { await apiDelete('/api/events/' + id); loadAdminEvents(); }
    catch (e) { alert(e.message); }
}

async function sendNotification() {
    const md = document.getElementById('notifyMessage');
    try {
        await apiPost('/api/notifications/send', {
            user_id: document.getElementById('notifyUser').value,
            subject: document.getElementById('notifySubject').value,
            message: document.getElementById('notifyMsg').value
        });
        md.textContent = 'Notification sent successfully!';
        md.className = 'login-message success';
        md.style.display = 'block';
        document.getElementById('notifyMsg').value = '';
    } catch (err) {
        md.textContent = err.message;
        md.className = 'login-message error';
        md.style.display = 'block';
    }
    setTimeout(() => md.style.display = 'none', 3000);
}

// ==================== HARDWARE CONTROLS ====================
async function controlDoor(action) {
    try {
        const result = await apiPost('/api/hardware/door', { action });
        const el = document.getElementById('doorStatus');
        if (el) { el.textContent = action === 'unlock' ? 'UNLOCKED' : 'LOCKED'; el.className = 'sensor-value ' + (action === 'unlock' ? 'sensor-warning' : 'sensor-safe'); }
        showToast(result.message);
    } catch (e) { showToast('Error: ' + e.message, true); }
}

async function controlBuzzer(action) {
    try {
        await apiPost('/api/hardware/buzzer', { action });
        const el = document.getElementById('buzzerStatus');
        if (el) { el.textContent = action === 'on' ? 'ALARM ON' : 'OFF'; el.className = 'sensor-value ' + (action === 'on' ? 'sensor-danger' : ''); }
        showToast('Buzzer ' + action);
    } catch (e) { showToast('Error: ' + e.message, true); }
}

async function controlLED(action) {
    try {
        await apiPost('/api/hardware/led', { action });
        const el = document.getElementById('ledStatus');
        if (el) { el.textContent = action === 'on' ? 'ON' : 'OFF'; el.className = 'sensor-value ' + (action === 'on' ? 'sensor-safe' : ''); }
        showToast('LED ' + action);
    } catch (e) { showToast('Error: ' + e.message, true); }
}

async function controlServo() {
    const angle = document.getElementById('servoSlider').value;
    try {
        await apiPost('/api/hardware/servo', { angle: parseInt(angle) });
        showToast('Servo set to ' + angle + '\u00B0');
    } catch (e) { showToast('Error: ' + e.message, true); }
}

// ==================== TOAST NOTIFICATION ====================
function showToast(message, isError) {
    let toast = document.getElementById('appToast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'appToast';
        document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = 'toast' + (isError ? ' toast-error' : '');
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 3000);
}

// ==================== MODALS ====================
function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }
document.addEventListener('click', function (e) {
    if (e.target.classList.contains('modal-overlay') && e.target.classList.contains('active'))
        e.target.classList.remove('active');
});

// ==================== AUTH FORMS ====================
function initLoginForm() {
    const form = document.getElementById('loginForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('loginBtn');
        const msg = document.getElementById('loginMessage');
        btn.textContent = 'Logging in...'; btn.disabled = true;
        const result = await login(
            document.getElementById('username').value,
            document.getElementById('password').value,
            document.querySelector('input[name="role"]:checked').value
        );
        btn.textContent = 'Login'; btn.disabled = false;
        if (result.success) {
            window.location.href = result.role === 'admin' ? 'admin.html' : 'index.html';
        } else {
            msg.textContent = result.error; msg.className = 'login-message error'; msg.style.display = 'block';
        }
    });
}

function initRegisterForm() {
    const form = document.getElementById('registerForm');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('registerBtn');
        const msg = document.getElementById('registerMessage');
        btn.textContent = 'Creating...'; btn.disabled = true;
        try {
            await apiPost('/api/register', {
                username: document.getElementById('username').value,
                email: document.getElementById('email').value,
                password: document.getElementById('password').value,
                confirmPassword: document.getElementById('confirmPassword').value,
                role: document.querySelector('input[name="role"]:checked').value
            });
            msg.textContent = 'Registration successful! Redirecting to login...';
            msg.className = 'login-message success'; msg.style.display = 'block';
            setTimeout(() => window.location.href = 'login.html', 2000);
        } catch (err) {
            msg.textContent = err.message; msg.className = 'login-message error'; msg.style.display = 'block';
            btn.textContent = 'Create Account'; btn.disabled = false;
        }
    });
}

// ==================== INIT ====================
function initApp() {
    updateNavForAuth();
    const page = window.location.pathname.split('/').pop() || 'index.html';

    if (page === 'index.html' || page === '') loadDashboard();
    else if (page === 'admin.html') {
        if (!isAuthenticated() || getUserRole() !== 'admin') { window.location.href = 'login.html'; return; }
        loadAdminDashboard();
    }
    else if (page === 'login.html') initLoginForm();
    else if (page === 'register.html') initRegisterForm();
    else if (page === 'camera.html') {
        if (!isAuthenticated()) { window.location.href = 'login.html'; return; }
        // Camera page uses onclick handlers from HTML
        startSensorPolling();
    }
}

document.addEventListener('DOMContentLoaded', initApp);
