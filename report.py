"""日报生成模块 - 支持用户隔离（销售员/主管），高效查询"""

import os
from datetime import datetime
from typing import List, Dict, Optional
from fpdf import FPDF

from db import get_conn, get_customer
from advisor import generate_advice

# ===================== 中文 PDF 支持 =====================
def get_chinese_font_path():
    possible_paths = [
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arialuni.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallback.ttf",
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return None

class ChinesePDF(FPDF):
    def __init__(self):
        super().__init__()
        font_path = get_chinese_font_path()
        if font_path:
            try:
                self.add_font('chinese', '', font_path, uni=True)
                self.set_font('chinese', '', 10)
            except RuntimeError:
                self.set_font('helvetica', '', 10)
        else:
            self.set_font('helvetica', '', 10)

    def header(self):
        if 'chinese' in self.fonts:
            self.set_font('chinese', 'B', 16)
        else:
            self.set_font('helvetica', 'B', 16)
        self.cell(0, 10, 'Sales Daily Report', ln=True, align='C')
        if 'chinese' in self.fonts:
            self.set_font('chinese', '', 10)
        else:
            self.set_font('helvetica', '', 10)
        self.cell(0, 6, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', ln=True, align='C')
        self.ln(8)

    def footer(self):
        self.set_y(-15)
        if 'chinese' in self.fonts:
            self.set_font('chinese', 'I', 8)
        else:
            self.set_font('helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', align='C')

# ===================== TXT 日报 =====================
def generate_txt_report(report_data: List[Dict], output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    lines = []
    lines.append("=" * 60)
    lines.append(f"销售跟进日报 - {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    lines.append("")
    if not report_data:
        lines.append("今日无风险客户，恭喜！")
    else:
        for idx, item in enumerate(report_data, 1):
            lines.append(f"【{idx}】{item['name']}（{item.get('company', '')}）- {item['stage']}")
            lines.append(f"风险类型：{', '.join(item['risks'])}")
            lines.append(f"跟进建议：{item['advice']}")
            lines.append("-" * 40)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path

# ===================== PDF 日报 =====================
def generate_pdf_report(report_data: List[Dict], output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf = ChinesePDF()
    pdf.add_page()
    col_widths = [50, 35, 45, 60]
    row_height = 8
    pdf.set_fill_color(200, 220, 255)
    if 'chinese' in pdf.fonts:
        pdf.set_font('chinese', 'B', 10)
    else:
        pdf.set_font('helvetica', 'B', 10)
    headers = ['Customer', 'Stage', 'Risk Types', 'AI Suggestion']
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], row_height, header, border=1, align='C', fill=True)
    pdf.ln(row_height)
    if 'chinese' in pdf.fonts:
        pdf.set_font('chinese', '', 9)
    else:
        pdf.set_font('helvetica', '', 9)
    for item in report_data:
        name_company = f"{item['name']}\n{item.get('company', '')}"
        stage = item['stage']
        risks = ', '.join(item['risks']) if item['risks'] else 'none'
        advice = item['advice'].replace('\n', ' ')
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        pdf.multi_cell(col_widths[0], row_height, name_company, border=1, align='L')
        x_next, y_next = pdf.get_x(), pdf.get_y()
        pdf.set_xy(x_start + col_widths[0], y_start)
        pdf.multi_cell(col_widths[1], row_height, stage, border=1, align='L')
        pdf.set_xy(x_start + col_widths[0] + col_widths[1], y_start)
        pdf.multi_cell(col_widths[2], row_height, risks, border=1, align='L')
        pdf.set_xy(x_start + col_widths[0] + col_widths[1] + col_widths[2], y_start)
        pdf.multi_cell(col_widths[3], row_height, advice, border=1, align='L')
        pdf.set_y(max(y_next, pdf.get_y()))
        pdf.ln(0)
    pdf.output(output_path)
    return output_path

# ===================== Markdown 日报 =====================
def generate_markdown_report(report_data: List[Dict], output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    lines = [f"# 销售跟进日报 - {datetime.now().strftime('%Y-%m-%d')}\n"]
    lines.append(f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    if not report_data:
        lines.append("✅ 今日无风险客户，恭喜！")
    else:
        for idx, item in enumerate(report_data, 1):
            lines.append(f"## {idx}. {item['name']}（{item.get('company', '')}）- {item['stage']}")
            lines.append(f"- **风险类型**：{', '.join(item['risks'])}")
            lines.append(f"- **跟进建议**：{item['advice']}\n")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return output_path

# ===================== 主函数（支持用户隔离，高效查询）=====================
def generate_daily_report(user_id: int = None, user_role: str = "sales",
                          output_dir: str = "output",
                          formats: List[str] = ["txt", "md"]) -> Dict[str, str]:
    """
    生成日报 - 根据用户角色自动过滤客户
    :param user_id: 当前用户ID（销售员必传，主管可为None但会忽略）
    :param user_role: 用户角色 'sales' 或 'manager'
    """
    # 一次性获取所有活跃风险标记及对应客户信息（JOIN）
    conn = get_conn()
    if user_role == "manager":
        # 主管：所有客户的风险
        rows = conn.execute("""
            SELECT r.customer_id, r.rule_name, r.detail, c.name, c.company, c.stage, c.owner_id
            FROM risk_flags r
            JOIN customers c ON r.customer_id = c.id
            WHERE r.status = 'active'
        """).fetchall()
    else:
        # 销售员：只属于自己客户的风险
        rows = conn.execute("""
            SELECT r.customer_id, r.rule_name, r.detail, c.name, c.company, c.stage, c.owner_id
            FROM risk_flags r
            JOIN customers c ON r.customer_id = c.id
            WHERE r.status = 'active' AND c.owner_id = ?
        """, (user_id,)).fetchall()
    conn.close()

    # 按客户聚合风险
    risk_map = {}
    for row in rows:
        cid = row['customer_id']
        if cid not in risk_map:
            risk_map[cid] = {
                'name': row['name'],
                'company': row['company'],
                'stage': row['stage'],
                'owner_id': row['owner_id'],
                'risks': []
            }
        risk_map[cid]['risks'].append(row['rule_name'])
    
    # 构建报告数据，并生成 AI 建议
    report_data = []
    for cid, data in risk_map.items():
        advice = generate_advice(cid)
        report_data.append({
            'name': data['name'],
            'company': data['company'],
            'stage': data['stage'],
            'risks': list(set(data['risks'])),  # 去重
            'advice': advice
        })
    
    # 生成文件
    date_str = datetime.now().strftime("%Y%m%d")
    output_paths = {}
    if "txt" in formats:
        txt_path = os.path.join(output_dir, f"daily_report_{date_str}.txt")
        generate_txt_report(report_data, txt_path)
        output_paths["txt"] = txt_path
    if "pdf" in formats:
        pdf_path = os.path.join(output_dir, f"daily_report_{date_str}.pdf")
        generate_pdf_report(report_data, pdf_path)
        output_paths["pdf"] = pdf_path
    if "md" in formats:
        md_path = os.path.join(output_dir, f"daily_report_{date_str}.md")
        generate_markdown_report(report_data, md_path)
        output_paths["md"] = md_path
    return output_paths

if __name__ == "__main__":
    # 测试：销售员视角
    result = generate_daily_report(user_id=1, user_role="sales")
    print("销售员日报生成:", result)