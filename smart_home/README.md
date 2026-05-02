# Smart Home Security System

A comprehensive smart home security system with face recognition, role-based access control (admin/public), and real-time monitoring.

## Features

- **Role-Based Access Control**: Admin and public user roles with different permissions
- **Face Recognition**: Hybrid approach using webcam capture and server-side processing
- **Real-time Monitoring**: Security event detection and logging
- **Email Notifications**: SMTP-based email alerts for security events
- **Responsive Web Interface**: Modern, animated UI for both admin and public dashboards
- **MongoDB Atlas Integration**: Cloud-hosted database for scalability

## Technology Stack

- **Frontend**: HTML, CSS, JavaScript (Vanilla JS)
- **Backend**: Python (Flask)
- **Database**: MongoDB Atlas
- **Authentication**: JWT tokens
- **Face Recognition**: face-recognition library
- **Deployment**: Local development → cloud deployment

## Installation

1. Clone the repository
2. Install Python dependencies: `pip install -r requirements.txt`
3. Set up MongoDB Atlas cluster and update `.env` file with connection string
4. Create MongoDB collections and indexes
5. Run the application: `python app.py`

## Getting Started

### Prerequisites
- Python 3.8+
- MongoDB Atlas account
- SMTP email service (Gmail, Outlook, etc.)

### Setup Instructions

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   - Copy `.env.example` to `.env` and update with your credentials
   - Set MongoDB Atlas connection string
   - Configure SMTP settings

3. **Run the application**:
   ```bash
   python app.py
   ```

4. **Access the application**:
   - Public Dashboard: `http://localhost:5000`
   - Admin Dashboard: `http://localhost:5000/admin.html`
   - Login: `http://localhost:5000/login.html`

## Default Credentials

- **Admin**: username: `admin`, password: `admin123`
- **Public User**: username: `user`, password: `user123`

## Security Considerations

- Passwords are hashed with bcrypt
- JWT tokens are signed and verified
- Input validation and sanitization
- Rate limiting on authentication endpoints
- HTTPS enforcement in production

## Development Roadmap

- [x] Phase 1: Foundation (Project structure, authentication, basic frontend)
- [ ] Phase 2: Core Security (Webcam integration, face recognition, security events)
- [ ] Phase 3: Admin Interface (Full CRUD, user management, configuration)
- [ ] Phase 4: Testing & Deployment (Comprehensive testing, security audit, deployment)

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting pull requests.

## License

MIT License