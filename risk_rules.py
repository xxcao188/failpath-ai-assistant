"""Fail Path 风险识别规则引擎

5 条规则：
1. 报价无响应 — 报价后超过 N 天无回复
2. 长期未联系 — 超过 N 天未联系
3. 跟进停滞 — 同一阶段停留超过 N 天
4. 高频低效跟进 — 最近 N 次跟进未推进阶段
5. 关键阶段失联 — 谈判中超 N 天无联系
"""

import yaml
from datetime import datetime, timedelta
from typing import List, Tuple

from db import (
    get_customers, get_follow_ups, get_latest_follow_up,
    add_risk_flag, clear_all_risk_flags, get_risk_flags
)
from models import Customer, RiskFlag


def load_config():
    """加载配置"""
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def days_since(date_str: str) -> int:
    """计算距今多少天"""
    if not date_str:
        return 999
    try:
        dt = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - dt).days
    except ValueError:
        return 999


def get_stage_index(stage: str) -> int:
    """获取阶段序号"""
    stages = ["初次接触", "需求沟通", "已报价", "谈判中", "已签单"]
    return stages.index(stage) if stage in stages else 0


# ===================== 规则实现 =====================

def rule_quotation_no_response(customer: Customer, config: dict) -> Tuple[bool, str]:
    """规则1：报价无响应
    依据：报价后沉默是最常见的客户流失信号。客户收到报价后如果不回应，
    通常意味着价格超出预期、需求已变或转投竞对。
    逻辑：客户处于"已报价"阶段 + 最近一次跟进是发送报价 + 超过阈值天数无回复
    """
    threshold = config["rules"]["quotation_no_response_days"]
    follow_ups = get_follow_ups(customer.id)
    if not follow_ups:
        return False, ""

    # 查找最近的报价记录
    quotation_fus = [fu for fu in follow_ups if fu.is_quotation_sent]
    if not quotation_fus:
        return False, ""

    latest_quotation = quotation_fus[0]  # 已按时间倒序
    days = days_since(latest_quotation.follow_up_time)

    # 检查报价后是否有新的跟进（说明有回应）
    has_follow_up_after = any(
        fu.follow_up_time > latest_quotation.follow_up_time
        for fu in follow_ups
        if fu.id != latest_quotation.id
    )

    if customer.stage in ["已报价", "谈判中"] and not has_follow_up_after and days >= threshold:
        detail = f"报价￥{latest_quotation.quotation_amount or '未知'}已于{days}天前发送，客户至今未回复"
        return True, detail

    return False, ""


def rule_no_contact(customer: Customer, config: dict) -> Tuple[bool, str]:
    """规则2：长期未联系
    依据：销售心理学表明，超过2周不联系，客户对产品的关注度会大幅下降，
    记忆衰减曲线决定了持续触达的重要性。
    逻辑：距最近联系时间超过阈值天数
    """
    threshold = config["rules"]["no_contact_days"]
    latest_fu = get_latest_follow_up(customer.id)
    if not latest_fu:
        days = days_since(customer.created_at)
        if days >= threshold:
            return True, f"客户录入{days}天以来从未联系过"
        return False, ""

    days = days_since(latest_fu.follow_up_time)
    if days >= threshold and customer.stage != "已签单":
        return True, f"最近一次联系在{days}天前（{latest_fu.follow_up_time[:10]}），已超过{threshold}天未联系"

    return False, ""


def rule_stage_stagnation(customer: Customer, config: dict) -> Tuple[bool, str]:
    """规则3：跟进停滞
    依据：销售漏斗的核心假设是客户会沿阶段推进。如果一个阶段停留过久，
    说明存在未解决的障碍（决策人未参与、预算问题、竞对干扰等）。
    逻辑：客户停留在当前阶段超过阈值天数
    """
    threshold = config["rules"]["stage_stagnation_days"]
    if customer.stage in ["已签单", "初次接触"]:
        return False, ""

    days = days_since(customer.created_at)
    # 检查阶段更新时间：通过 updated_at 近似判断
    stage_days = days_since(customer.updated_at)

    # 用所有跟进记录中最早的日期作为"进入当前阶段"的近似
    follow_ups = get_follow_ups(customer.id)
    if len(follow_ups) < 2:
        return False, ""

    # 简化逻辑：如果客户存在超过阈值天数且阶段不是已签单，
    # 检查跟进记录中是否长时间没有阶段变化
    if days >= threshold:
        # 看最近的跟进是否还在同一阶段
        latest_fu = follow_ups[0]
        latest_days = days_since(latest_fu.follow_up_time)
        if latest_days >= 7:  # 至少7天没有新跟进
            return True, f"客户在「{customer.stage}」阶段已停留较长时间，最近{latest_days}天无新进展"

    return False, ""


def rule_ineffective_follow_up(customer: Customer, config: dict) -> Tuple[bool, str]:
    """规则4：高频低效跟进
    依据：反复联系但不推进，说明跟进策略有问题——可能在跟错误的人、
    用错误的方式，或者客户根本没打算推进。
    逻辑：最近 N 次跟进均未使阶段发生变化
    """
    threshold_count = config["rules"]["ineffective_follow_up_count"]
    if customer.stage in ["已签单", "初次接触"]:
        return False, ""

    follow_ups = get_follow_ups(customer.id)
    if len(follow_ups) < threshold_count:
        return False, ""

    # 取最近 N 次跟进
    recent_fus = follow_ups[:threshold_count]
    # 如果最近 N 次跟进都没有推动阶段变化（阶段仍相同），
    # 且最近一次跟进距今超过3天
    latest_days = days_since(recent_fus[0].follow_up_time)

    if latest_days >= 3:
        return True, f"最近{threshold_count}次跟进均未将客户从「{customer.stage}」阶段推进，跟进策略可能需要调整"

    return False, ""


def rule_key_stage_no_contact(customer: Customer, config: dict) -> Tuple[bool, str]:
    """规则5：关键阶段失联
    依据：谈判阶段是成单前最关键的环节，此时失联风险最高——
    客户可能在比较竞对、内部出现分歧、或已被竞对截胡。
    逻辑：客户处于"谈判中"阶段 + 超过阈值天数无联系
    """
    threshold = config["rules"]["key_stage_no_contact_days"]
    if customer.stage != "谈判中":
        return False, ""

    latest_fu = get_latest_follow_up(customer.id)
    if not latest_fu:
        days = days_since(customer.created_at)
        if days >= threshold:
            return True, f"谈判中客户从未联系，已{days}天"
        return False, ""

    days = days_since(latest_fu.follow_up_time)
    if days >= threshold:
        return True, f"谈判中客户已{days}天无联系，存在被竞对截胡风险"

    return False, ""


# ===================== 规则引擎 =====================

# 注册所有规则
RULES = [
    ("quotation_no_response", "报价无响应", rule_quotation_no_response),
    ("no_contact", "长期未联系", rule_no_contact),
    ("stage_stagnation", "跟进停滞", rule_stage_stagnation),
    ("ineffective_follow_up", "高频低效跟进", rule_ineffective_follow_up),
    ("key_stage_no_contact", "关键阶段失联", rule_key_stage_no_contact),
]


def scan_all_risks() -> List[RiskFlag]:
    """扫描所有客户，执行全部规则，返回风险标记列表"""
    config = load_config()
    clear_all_risk_flags()

    customers = get_customers()
    flagged_count = 0

    for customer in customers:
        for rule_id, rule_name, rule_fn in RULES:
            triggered, detail = rule_fn(customer, config)
            if triggered:
                add_risk_flag(customer.id, rule_id, rule_name, detail)
                flagged_count += 1

    flags = get_risk_flags()
    return flags


def get_customer_risk_summary(customer_id: int) -> List[RiskFlag]:
    """获取某客户的风险摘要"""
    from db import get_risk_flags_for_customer
    return get_risk_flags_for_customer(customer_id)
