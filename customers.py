"""为两个销售员分别生成 10 个客户（共 20 个），带跟进记录"""

from db import init_db, add_user, get_user_by_username, add_customer, add_follow_up
from datetime import datetime, timedelta
import random

def ensure_user(username, password, fullname):
    user = get_user_by_username(username)
    if not user:
        user_id = add_user(username, password, fullname)
        print(f"✅ 创建用户: {username} ({fullname})")
    else:
        user_id = user.id
        print(f"✅ 用户已存在: {username} ({fullname})")
    return user_id

def random_stage():
    """随机分配阶段，让风险规则更容易触发"""
    stages = ["初次接触", "需求沟通", "已报价", "谈判中", "已签单"]
    weights = [0.1, 0.2, 0.4, 0.25, 0.05]  # 大部分在报价/谈判阶段
    return random.choices(stages, weights=weights)[0]

def random_days_ago():
    """随机返回最近联系天数（1~25天），用于触发风险"""
    return random.randint(1, 25)

def random_quotation():
    """随机决定是否发送报价，并返回金额"""
    sent = random.choice([True, False])
    amount = random.randint(5000, 50000) if sent else None
    return sent, amount

def main():
    init_db()
    print("数据库初始化完成")

    sales1_id = ensure_user("sales1", "123", "张销售")
    sales2_id = ensure_user("sales2", "123", "李销售")

    # 定义客户基础名（姓氏+序号，方便区分）
    first_names_1 = ["张明", "王强", "李伟", "刘洋", "陈晨", "赵磊", "周涛", "吴迪", "郑爽", "林晨"]
    first_names_2 = ["李芳", "孙梅", "周丽", "吴静", "郑娟", "王霞", "陈敏", "刘娟", "赵燕", "林娜"]
    companies = ["云创科技", "智联网络", "创新软件", "先锋科技", "未来智能",
                 "海达集团", "华威电子", "新锐传媒", "安达物流", "博雅咨询"]

    def add_customers_for(owner_id, name_list, company_list):
        for idx, name in enumerate(name_list):
            # 循环使用公司列表，确保每个客户有不同公司
            company = company_list[idx % len(company_list)]
            stage = random_stage()
            days = random_days_ago()
            sent, amount = random_quotation()
            action = "发送报价单" if sent else ("电话沟通" if random.random() > 0.5 else "邮件跟进")

            # 添加客户
            cid = add_customer(
                owner_id=owner_id,
                name=name,
                company=company,
                contact_info=f"{name}@{company.replace(' ', '')}.com",
                stage=stage
            )
            # 跟进时间
            follow_time = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            # 跟进记录
            add_follow_up(
                customer_id=cid,
                action_type="邮件" if sent else "电话",
                content=action,
                follow_up_time=follow_time,
                is_quotation_sent=sent,
                quotation_amount=amount
            )
            print(f"   → 添加: {name} ({company}) | 阶段:{stage} | 距今{days}天 | 报价:{amount if sent else '无'}")
        print(f"完成 {len(name_list)} 个客户")

    print("\n为销售1 (sales1) 添加 10 个客户:")
    add_customers_for(sales1_id, first_names_1, companies)

    print("\n为销售2 (sales2) 添加 10 个客户:")
    add_customers_for(sales2_id, first_names_2, companies)

    print("\n✅ 完成！共 20 个客户（每个销售 10 个）")

if __name__ == "__main__":
    main()