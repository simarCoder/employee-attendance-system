# 👨‍💼 Employee Attendance & Payroll System

A local web-based backend system for managing employee records, attendance tracking, and automated salary calculation.

This project focuses on backend logic, data handling, and real-world workflow simulation.

---

## 🚀 Features

- Employee management (add, update, delete records)  
- Attendance tracking system  
- Automated salary calculation based on attendance  
- Multi-user login system  
- Document storage for employee records  
- Data encryption for sensitive fields  

---

## 🛠️ Tech Stack

- **Backend:** Python (Flask)  
- **Database:** SQLite3  
- **Frontend:** HTML, CSS, JavaScript  
- **Security:** Cryptography (Fernet encryption)  

---

## ⚙️ System Architecture

- Modular backend structure (`services`, `utils`, `database`)  
- Separation of business logic from routes  
- Database-driven workflow  
- File handling for document uploads  
- Local server-based execution  

---

## 🔐 Authentication (Current State)

- Passwords are encrypted before storage  
- Login system validates encrypted credentials  
- Session handling is basic and will be improved  

---

## 📦 Installation

```bash
git clone https://github.com/simarCoder/employee-attendance-system
cd employee-attendance-system
pip install -r requirements.txt
python app.py
```

---
 
## 🎯 Purpose

This project simulates a real-world employee management system used in small organizations to handle attendance, payroll, and employee data efficiently.

---

## ⚠️ Note
This is a local system (not deployed on cloud)
Designed for learning and demonstration purposes
Authentication system can be further improved using Flask sessions

---

## 👨‍💻 Author

Simar
GitHub: https://github.com/simarCoder
