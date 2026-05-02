// Smart Home Security - Authentication Module

const TOKEN_KEY = 'smart_home_jwt_token';
const USER_ROLE_KEY = 'smart_home_user_role';
const USERNAME_KEY = 'smart_home_username';

function getAuthToken() {
    return localStorage.getItem(TOKEN_KEY);
}

function setAuthToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
}

function removeAuthToken() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_ROLE_KEY);
    localStorage.removeItem(USERNAME_KEY);
}

function getUserRole() {
    return localStorage.getItem(USER_ROLE_KEY);
}

function setUserRole(role) {
    localStorage.setItem(USER_ROLE_KEY, role);
}

function getUsername() {
    return localStorage.getItem(USERNAME_KEY);
}

function isAuthenticated() {
    const token = getAuthToken();
    if (!token) return false;
    try {
        const payload = JSON.parse(atob(token.split('.')[1]));
        return payload.exp * 1000 > Date.now();
    } catch (e) {
        return false;
    }
}

function getAuthHeader() {
    const token = getAuthToken();
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function login(username, password, role) {
    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role })
        });
        const data = await response.json();
        if (!response.ok) {
            return { success: false, error: data.error || 'Login failed' };
        }
        if (data.token && data.role) {
            setAuthToken(data.token);
            setUserRole(data.role);
            localStorage.setItem(USERNAME_KEY, data.username || username);
            return { success: true, role: data.role };
        }
        return { success: false, error: 'Invalid response' };
    } catch (error) {
        return { success: false, error: error.message };
    }
}

function logout() {
    removeAuthToken();
    window.location.href = 'login.html';
}

// Auto-redirect on protected pages
document.addEventListener('DOMContentLoaded', function() {
    const page = window.location.pathname.split('/').pop() || 'index.html';
    if (page === 'admin.html' && !isAuthenticated()) {
        window.location.href = 'login.html';
    }
});
