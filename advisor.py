"""AI 跟进建议生成器"""

import yaml
from typing import List, Optional
from openai import OpenAI

from db import get_customer, get_follow_ups, get_risk_flags_for_customer
from models import RiskFlag


def load_config():
    """加载配置"""
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_client() -> OpenAI:
    """获取 API 客户端"""
    config = load_config()
    return OpenAI(
        api_key=config["api"]["api_key"],
        base_url=config["api"]["base_url"]
    )


def build_prompt(customer_id: int, risk_flags: List[RiskFlag]) -> str:
    """构建生成跟进建议的 Prompt"""
    customer = get_customer(customer_id)
    follow_ups = get_follow_ups(customer_id)

    # 跟进历史摘要（最近5条）
    fu_lines = []
    for fu in follow_ups[:5]:
        amount_str = f"，报价￥{fu.quotation_amount}" if fu.is_quotation_sent and fu.quotation_amount else ""
        fu_lines.append(f"  - {fu.follow_up_time[:10]} | {fu.action_type} | {fu.content}{amount_str}")
    fu_history = "\n".join(fu_lines) if fu_lines else "  暂无跟进记录"

    # 风险信息
    risk_lines = []
    for flag in risk_flags:
        risk_lines.append(f"  ⚠️ {flag.rule_name}：{flag.detail}")
    risk_info = "\n".join(risk_lines)

    prompt = f"""你是一位资深销售教练。请根据以下客户信息，生成2-3条具体、可操作的下一步跟进建议。

## 客户信息
- 客户姓名：{customer.name}
- 公司：{customer.company}
- 当前阶段：{customer.stage}
- 联系方式：{customer.contact_info}

## 识别到的风险信号
{risk_info}

## 最近跟进记录
{fu_history}

## 要求
1. 每条建议必须包含**具体动作**（如：今日致电、发送邮件、约线上会议、上门拜访等）
2. 每条建议必须包含**具体话术方向或沟通要点**，不能是泛泛的"保持跟进"
3. 建议要针对识别到的风险类型，帮助销售突破当前困境
4. 语气专业、简洁，适合销售直接参考执行

请直接输出建议，每条一行，用编号标记。"""

    return prompt

def format_advice(advice_text: str) -> str:
    """格式化建议文本：去除首尾空白，合并连续空行，使每条建议之间只空一行"""
    if not advice_text:
        return advice_text
    lines = advice_text.strip().split('\n')
    result_lines = []
    prev_empty = False
    for line in lines:
        line = line.strip()
        if line:
            result_lines.append(line)
            prev_empty = False
        else:
            if not prev_empty:
                result_lines.append('')  # 保留一个空行作为分隔
                prev_empty = True
    # 如果末尾有空行，去掉
    while result_lines and result_lines[-1] == '':
        result_lines.pop()
    return '\n'.join(result_lines)

def generate_advice(customer_id: int) -> Optional[str]:
    """为指定客户生成跟进建议（自动格式化，统一空行）"""
    risk_flags = get_risk_flags_for_customer(customer_id)
    if not risk_flags:
        return "该客户当前无风险标记，无需生成建议。"

    prompt = build_prompt(customer_id, risk_flags)

    try:
        config = load_config()
        client = get_client()
        response = client.chat.completions.create(
            model=config["api"]["model"],
            messages=[
                {"role": "system", "content": "你是资深销售教练，擅长分析客户跟进风险并给出具体可操作的建议。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        raw_advice = response.choices[0].message.content.strip()
        return format_advice(raw_advice)
    except Exception as e:
        error_msg = f"⚠️ AI 建议生成失败：{str(e)}\n请检查 config.yaml 中的 API Key 是否正确配置。"
        # 错误信息也做简单格式化（但一般不会有空行问题）
        return format_advice(error_msg)


def batch_generate_advice(risk_customer_ids: List[int] = None) -> dict:
    """批量生成建议，返回 {customer_id: advice} 字典"""
    if risk_customer_ids is None:
        from db import get_risk_flags
        flags = get_risk_flags()
        risk_customer_ids = list(set(f.customer_id for f in flags))

    results = {}
    for cid in risk_customer_ids:
        results[cid] = generate_advice(cid)

    return results
