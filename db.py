"""SQLite 数据库操作 - 支持多用户、角色、跟进记录、提醒消息"""

import os
import sqlite3
from datetime import datetime
from typing import List, Optional
from models import Customer, FollowUp, RiskFlag, DailyReport, User, Reminder

DB_PATH = "data/failpath.db"

def get_db_path():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH

def get_conn():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    """初始化数据库表（包括用户、客户、跟进记录、风险标记、日报、提醒消息）"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            fullname TEXT DEFAULT '',
            role TEXT DEFAULT 'sales',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            company TEXT DEFAULT '',
            contact_info TEXT DEFAULT '',
            stage TEXT DEFAULT '初次接触',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS follow_ups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            action_type TEXT DEFAULT '电话',
            content TEXT DEFAULT '',
            follow_up_time TEXT DEFAULT (datetime('now', 'localtime')),
            is_quotation_sent INTEGER DEFAULT 0,
            quotation_amount REAL DEFAULT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS risk_flags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            rule_id TEXT NOT NULL,
            rule_name TEXT NOT NULL,
            detail TEXT DEFAULT '',
            flagged_at TEXT DEFAULT (datetime('now', 'localtime')),
            status TEXT DEFAULT 'active',
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS daily_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_date TEXT NOT NULL,
            content_md TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );

        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER NOT NULL,
            to_user_id INTEGER NOT NULL,
            customer_id INTEGER,
            message TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            is_read INTEGER DEFAULT 0,
            FOREIGN KEY (from_user_id) REFERENCES users(id),
            FOREIGN KEY (to_user_id) REFERENCES users(id),
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
        );
    """)
    conn.commit()
    conn.close()

# ===================== 用户 CRUD =====================
def add_user(username: str, password: str, fullname: str = "", role: str = "sales") -> int:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO users (username, password, fullname, role) VALUES (?, ?, ?, ?)",
        (username, password, fullname, role)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id

def get_user_by_username(username: str) -> Optional[User]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return User(**dict(row)) if row else None

def get_user_by_id(user_id: int) -> Optional[User]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return User(**dict(row)) if row else None

def get_all_users():
    conn = get_conn()
    rows = conn.execute("SELECT id, username, fullname, role FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ===================== 客户 CRUD =====================
def add_customer(owner_id: int, name: str, company: str = "", contact_info: str = "", stage: str = "初次接触") -> int:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO customers (owner_id, name, company, contact_info, stage) VALUES (?, ?, ?, ?, ?)",
        (owner_id, name, company, contact_info, stage)
    )
    conn.commit()
    customer_id = cursor.lastrowid
    conn.close()
    return customer_id

def get_customers(owner_id: Optional[int] = None) -> List[Customer]:
    conn = get_conn()
    if owner_id is not None:
        rows = conn.execute("SELECT * FROM customers WHERE owner_id = ? ORDER BY updated_at DESC", (owner_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM customers ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [Customer(**dict(r)) for r in rows]

def get_all_customers_with_owner():
    """主管专用：获取所有客户及其归属销售员信息"""
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, u.username as owner_username, u.fullname as owner_fullname
        FROM customers c
        JOIN users u ON c.owner_id = u.id
        ORDER BY c.updated_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_customer(customer_id: int) -> Optional[Customer]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    conn.close()
    return Customer(**dict(row)) if row else None

def update_customer(customer_id: int, **kwargs) -> bool:
    if not kwargs:
        return False
    kwargs["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [customer_id]
    conn = get_conn()
    conn.execute(f"UPDATE customers SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    return True

def delete_customer(customer_id: int) -> bool:
    conn = get_conn()
    conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    conn.commit()
    conn.close()
    return True

# ===================== 跟进记录 CRUD =====================
def add_follow_up(customer_id: int, action_type: str, content: str,
                  follow_up_time: str = None, is_quotation_sent: bool = False,
                  quotation_amount: float = None) -> int:
    if follow_up_time is None:
        follow_up_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO follow_ups (customer_id, action_type, content, follow_up_time, is_quotation_sent, quotation_amount) VALUES (?, ?, ?, ?, ?, ?)",
        (customer_id, action_type, content, follow_up_time, int(is_quotation_sent), quotation_amount)
    )
    conn.execute(
        "UPDATE customers SET updated_at = datetime('now', 'localtime') WHERE id = ?",
        (customer_id,)
    )
    conn.commit()
    fu_id = cursor.lastrowid
    conn.close()
    return fu_id

def get_follow_ups(customer_id: int) -> List[FollowUp]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM follow_ups WHERE customer_id = ? ORDER BY follow_up_time DESC",
        (customer_id,)
    ).fetchall()
    conn.close()
    return [FollowUp(**dict(r)) for r in rows]

def get_all_follow_ups() -> List[FollowUp]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM follow_ups ORDER BY follow_up_time DESC").fetchall()
    conn.close()
    return [FollowUp(**dict(r)) for r in rows]

def get_latest_follow_up(customer_id: int) -> Optional[FollowUp]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM follow_ups WHERE customer_id = ? ORDER BY follow_up_time DESC LIMIT 1",
        (customer_id,)
    ).fetchone()
    conn.close()
    return FollowUp(**dict(row)) if row else None

def update_follow_up(follow_up_id: int, **kwargs) -> bool:
    if not kwargs:
        return False
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [follow_up_id]
    conn = get_conn()
    conn.execute(f"UPDATE follow_ups SET {sets} WHERE id = ?", vals)
    conn.commit()
    conn.close()
    return True

def delete_follow_up(follow_up_id: int) -> bool:
    conn = get_conn()
    conn.execute("DELETE FROM follow_ups WHERE id = ?", (follow_up_id,))
    conn.commit()
    conn.close()
    return True

# ===================== 风险标记 CRUD =====================
def add_risk_flag(customer_id: int, rule_id: str, rule_name: str, detail: str) -> int:
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM risk_flags WHERE customer_id = ? AND rule_id = ? AND status = 'active'",
        (customer_id, rule_id)
    ).fetchone()
    if existing:
        conn.close()
        return existing["id"]
    cursor = conn.execute(
        "INSERT INTO risk_flags (customer_id, rule_id, rule_name, detail) VALUES (?, ?, ?, ?)",
        (customer_id, rule_id, rule_name, detail)
    )
    conn.commit()
    flag_id = cursor.lastrowid
    conn.close()
    return flag_id

def get_risk_flags(status: str = "active") -> List[RiskFlag]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM risk_flags WHERE status = ? ORDER BY flagged_at DESC",
        (status,)
    ).fetchall()
    conn.close()
    return [RiskFlag(**dict(r)) for r in rows]

def get_risk_flags_for_customer(customer_id: int, status: str = "active") -> List[RiskFlag]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM risk_flags WHERE customer_id = ? AND status = ? ORDER BY flagged_at DESC",
        (customer_id, status)
    ).fetchall()
    conn.close()
    return [RiskFlag(**dict(r)) for r in rows]

def resolve_risk_flag(flag_id: int) -> bool:
    conn = get_conn()
    conn.execute("UPDATE risk_flags SET status = 'resolved' WHERE id = ?", (flag_id,))
    conn.commit()
    conn.close()
    return True

def clear_all_risk_flags():
    conn = get_conn()
    conn.execute("DELETE FROM risk_flags WHERE status = 'active'")
    conn.commit()
    conn.close()

# ===================== 日报 CRUD =====================
def save_report(report_date: str, content_md: str, file_path: str) -> int:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO daily_reports (report_date, content_md, file_path) VALUES (?, ?, ?)",
        (report_date, content_md, file_path)
    )
    conn.commit()
    report_id = cursor.lastrowid
    conn.close()
    return report_id

def get_reports() -> List[DailyReport]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM daily_reports ORDER BY report_date DESC").fetchall()
    conn.close()
    return [DailyReport(**dict(r)) for r in rows]

# ===================== 提醒消息 CRUD =====================
def add_reminder(from_user_id: int, to_user_id: int, message: str, customer_id: int = None) -> int:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO reminders (from_user_id, to_user_id, customer_id, message) VALUES (?, ?, ?, ?)",
        (from_user_id, to_user_id, customer_id, message)
    )
    conn.commit()
    rid = cursor.lastrowid
    conn.close()
    return rid

def get_reminders_for_user(to_user_id: int, unread_only: bool = True, limit: int = 20):
    """获取用户的提醒消息（按时间倒序）"""
    conn = get_conn()
    query = """
        SELECT r.*, u.fullname as from_name 
        FROM reminders r 
        JOIN users u ON r.from_user_id = u.id 
        WHERE r.to_user_id = ? 
    """
    params = [to_user_id]
    if unread_only:
        query += " AND r.is_read = 0"
    query += " ORDER BY r.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def mark_reminder_read(reminder_id: int):
    conn = get_conn()
    conn.execute("UPDATE reminders SET is_read = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def mark_all_reminders_read(to_user_id: int):
    conn = get_conn()
    conn.execute("UPDATE reminders SET is_read = 1 WHERE to_user_id = ? AND is_read = 0", (to_user_id,))
    conn.commit()
    conn.close()