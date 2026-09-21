BarPOS Desktop

A desktop Point of Sale (POS) system designed for bars and small restaurants. Built with Python, Tkinter, and SQLite, BarPOS manages table accounts, products, inventory, payments, daily cash sessions, receipts, users, and sales reports from a touch-friendly interface.

Features

Point of Sale

Open and manage up to 10 customer/table accounts.

Add or remove products from active accounts.

Real-time subtotal, tax, and total calculations.

Automatic inventory updates when products are sold.

Touch-friendly product catalog and numeric controls.

Inventory Management

Create and edit products.

Manage product type, price, and stock.

Increase or decrease stock manually.

Low-stock and out-of-stock status indicators.

Users and Roles

Secure login system.

Two roles: admin and cajero.

Passwords stored using PBKDF2 hashing with an individual salt.

Administrator tools for creating users, resetting passwords, and deleting users.

Administrative restrictions for sensitive operations such as daily and cash closing.

Payments

Supported payment methods:

Cash (EFECTIVO)

Card (TARJETA)

SINPE Mobile (SINPE)

For cash payments, the system:

Captures the amount received.

Validates that the payment is sufficient.

Calculates change automatically.

Stores payment information for auditing and reporting.

Cash Register Management

Daily cash opening with an initial amount.

Only one cash session per business date.

Expected cash calculation based on opening balance and cash sales.

Physical cash count during closing.

Automatic difference calculation between expected and counted cash.

Optional closing notes.

Complete record of who opened and closed the register.

Receipts

Automatic receipt numbering.

TXT receipts suitable for thermal-printing workflows.

PDF receipts generated with ReportLab.

Payment method, amount received, and change are included in the final receipt.

Receipts can be opened and printed directly from the application.

Reports and CSV Export

The application can export daily operational data to CSV, including:

Inventory

Sales by product

Closed accounts

Daily closing summary

Receipt registry

Payments by method

Cash-session summary

Data Persistence

SQLite is used to persist:

Products

Users

Open accounts

Account items

Sales lines

Closed accounts

Daily closures

Receipts

Payments

Cash sessions

Open customer accounts are preserved between application restarts.

Tech Stack

Technology

Purpose

Python 3

Application logic

Tkinter / ttk

Desktop graphical interface

SQLite

Local relational database

ReportLab

PDF receipt generation

PBKDF2 / hashlib

Password hashing

PyInstaller

Windows executable packaging

CSV / JSON

Reporting and data serialization

Project Architecture

The application is separated into two main modules:

pos_core.py
├── Database schema and persistence
├── Product and inventory management
├── User authentication
├── Account and sales logic
├── Payment processing
├── Cash-session management
├── Receipt generation
└── CSV reporting

pos_gui.py
├── Login interface
├── Product catalog
├── Table/account management
├── Inventory interface
├── Payment dialogs
├── Cash opening/closing dialogs
├── User administration
└── Reports and receipt tools

Project Structure

BarPOS/
├── pos_core.py
├── pos_gui.py
├── POSBar.spec
├── CONTROL_CAJA_README.md
└── README.md

Files generated while using or building the application, such as build/, dist/, SQLite databases, receipts, reports, and __pycache__/, should normally not be committed to a public repository.

Installation

1. Clone the repository

git clone https://github.com/your-username/barpos-desktop.git
cd barpos-desktop

2. Create a virtual environment

Windows:

python -m venv .venv
.venv\Scripts\activate

macOS / Linux:

python3 -m venv .venv
source .venv/bin/activate

3. Install dependencies

pip install reportlab

Tkinter is included with most standard Python installations. On some Linux distributions it may need to be installed separately.

Running the Application

python pos_gui.py

The SQLite database is created automatically in the application directory if it does not already exist.

Initial Users

On a new database, the application creates two initial accounts:

User

Password

Role

admin

admin123

Administrator

cajero

cajero123

Cashier

Security note: Change these default passwords before using the system in a real environment.

Typical Workflow

Log in to the system.

Open the daily cash register and enter the initial cash amount.

Open a table/customer account.

Add products from the catalog.

Review the account total.

Charge the customer using cash, card, or SINPE.

Generate and optionally print the receipt.

Review daily reports and payment totals.

Close the cash register as an administrator.

Export CSV reports or perform the daily closing.

Business Rules

VAT is currently configured at 13%.

Monetary values are stored internally as integer cents to reduce floating-point rounding errors.

A payment cannot be processed unless a cash session is open.

A duplicated cash session cannot be opened for the same business date.

Cash payments must cover the complete account total.

The business day cannot be closed while customer accounts remain open.

Only administrators can perform restricted closing operations.

Building the Windows Executable

The repository includes a PyInstaller specification file.

Install PyInstaller:

pip install pyinstaller

Build the application:

pyinstaller POSBar.spec

The generated Windows application will be placed in the dist/ directory.

Generated Files

During normal operation, BarPOS may create:

pos_bar.sqlite
receipts/
└── YYYY-MM-DD/
    ├── recibo_....pdf
    └── recibo_....txt

docs/
└── YYYY-MM-DD/
    ├── inventario_....csv
    ├── ventas_por_producto_....csv
    ├── cuentas_cerradas_....csv
    ├── cierre_....csv
    ├── recibos_....csv
    ├── payments_....csv
    └── caja_....csv

Current Scope

BarPOS is a local desktop application intended as a practical POS solution and software-development project. The current implementation focuses on a single local SQLite database and a desktop environment rather than a distributed or cloud-based architecture.

Possible Improvements

Dashboard with sales charts and KPIs.

Configurable tax rates and business information.

Product categories and search improvements.

Discounts and promotions.

Automated database backups.

Historical cash-session dashboard.

Employee-specific sales reports.

Direct integration with supported thermal printers.

Multi-device synchronization.

Cloud database support.

Automated tests.

Author

Developed as a Python desktop software project focused on POS workflows, database persistence, inventory control, payment processing, reporting, and user-role management.
