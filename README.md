# IT Helpdesk Ticket Management System

A Flask + SQLite portfolio project that simulates a basic IT service desk workflow.

## Features

- User registration and login with hashed passwords
- Role-based access: requester, support agent and admin
- Create tickets with category and priority
- Ticket dashboard with status counts, search and filters
- Assign tickets to support agents
- Update ticket status and priority
- Add comments and troubleshooting updates
- Admin page to create agent/requester accounts

## Requirements

- Python 3.10 or newer
- pip
- VS Code (recommended)

## Setup on Windows

Open this folder in VS Code. Open Terminal > New Terminal and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If PowerShell blocks activation, use Command Prompt:

```bat
.venv\Scripts\activate.bat
```

## Initialize the database and create an admin

PowerShell:

```powershell
$env:ADMIN_EMAIL="admin@helpdesk.local"
$env:ADMIN_PASSWORD="ChangeMe123!"
flask --app app seed-admin
```

The database and tables are created automatically by the command.

Start the application:

```powershell
flask --app app run --debug
```

Open http://127.0.0.1:5000 in your browser.

Admin login:
- Email: `admin@helpdesk.local`
- Password: `ChangeMe123!` (if you used the commands above)

Change the temporary password and use a unique secret before any public deployment.

## Suggested demo flow

1. Sign in as admin.
2. Open **Users** and create a support agent account.
3. Register a separate requester account.
4. Sign in as requester and create a ticket, for example: "Laptop cannot connect to office Wi-Fi".
5. Sign in as admin or agent, open the ticket, assign it and change its status to **In Progress**.
6. Add a troubleshooting comment.
7. Change the status to **Resolved** and verify the requester can see the update.

## Database tables

- `users`: account details and role
- `tickets`: issue details, priority, status, requester and assigned agent
- `comments`: ticket conversation and troubleshooting notes

## Project structure

```text
it_helpdesk_ticket_management_system/
├── app.py
├── requirements.txt
├── README.md
├── .gitignore
├── .env.example
├── helpdesk.db                 # created automatically; not committed
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   ├── new_ticket.html
│   ├── ticket_detail.html
│   ├── users.html
│   └── error.html
└── static/
    └── style.css
```

## Important security note

This is a learning/portfolio application, not a production-ready service desk. Before public production use, add CSRF protection, rate limiting, secure environment-based secrets, HTTPS, audit logging, stronger account lifecycle controls and automated tests. The built-in Flask development server is for local development only.
