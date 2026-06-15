"""数据模型定义"""

from dataclasses import dataclass

@dataclass
class Customer:
    id: int
    owner_id: int
    name: str
    company: str = ""
    contact_info: str = ""
    stage: str = "初次接触"
    created_at: str = ""
    updated_at: str = ""

@dataclass
class FollowUp:
    id: int
    customer_id: int
    action_type: str = "电话"
    content: str = ""
    follow_up_time: str = ""
    is_quotation_sent: int = 0
    quotation_amount: float = None

@dataclass
class RiskFlag:
    id: int
    customer_id: int
    rule_id: str
    rule_name: str
    detail: str = ""
    flagged_at: str = ""
    status: str = "active"

@dataclass
class DailyReport:
    id: int
    report_date: str
    content_md: str = ""
    file_path: str = ""
    created_at: str = ""

@dataclass
class User:
    id: int
    username: str
    password: str
    fullname: str = ""
    role: str = "sales"          # 'sales' 或 'manager'
    created_at: str = ""

@dataclass
class Reminder:
    id: int
    from_user_id: int
    to_user_id: int
    customer_id: int = None
    message: str = ""
    created_at: str = ""
    is_read: int = 0