"""Streamlit Web 界面 - 完整修复版（DOM 错误已解决）"""

import streamlit as st
import pandas as pd
from datetime import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import (
    init_db, add_customer, get_customers, get_customer,
    update_customer, delete_customer,
    add_follow_up, get_follow_ups, update_follow_up, delete_follow_up,
    get_user_by_username, add_user, get_all_customers_with_owner,
    get_risk_flags_for_customer, resolve_risk_flag,
    get_risk_flags, get_all_users, get_user_by_id,
    add_reminder, get_reminders_for_user, mark_reminder_read, mark_all_reminders_read
)
from risk_rules import scan_all_risks
from advisor import generate_advice
from report import generate_daily_report

# ==================== 辅助函数 ====================
def get_latest_quotation_amount(customer_id):
    """获取某个客户的最新报价金额（从跟进记录中取第一条有报价的）"""
    follow_ups = get_follow_ups(customer_id)
    for fu in follow_ups:
        if fu.is_quotation_sent and fu.quotation_amount:
            return fu.quotation_amount
    return None

def cleanup_temp_states():
    """清理所有临时编辑状态，避免 DOM 冲突导致前端错误"""
    temp_keys = [key for key in st.session_state.keys() 
                 if key.startswith("editing_fu_") or key.startswith("edit_form_") or key.startswith("add_fu_")]
    for key in temp_keys:
        del st.session_state[key]

# ==================== 常量定义 ====================
STAGES = ["初次接触", "需求沟通", "已报价", "谈判中", "已签单"]
ACTION_TYPES = ["电话", "邮件", "微信", "拜访", "其他"]

st.set_page_config(page_title="销售助手", layout="wide")

# 初始化数据库并创建默认用户
if 'db_initialized' not in st.session_state:
    init_db()
    if not get_user_by_username("sales1"):
        add_user("sales1", "123", "张销售", role="sales")
    if not get_user_by_username("sales2"):
        add_user("sales2", "123", "李销售", role="sales")
    if not get_user_by_username("manager"):
        add_user("manager", "123", "王主管", role="manager")
    st.session_state.db_initialized = True

def login():
    st.title("销售客户FailPath AI助手登录")
    with st.form("login_form"):
        username = st.text_input("用户名")
        password = st.text_input("密码", type="password")
        submitted = st.form_submit_button("登录")
        if submitted:
            user = get_user_by_username(username)
            if user and user.password == password:
                st.session_state.logged_in = True
                st.session_state.user_id = user.id
                st.session_state.username = user.fullname or user.username
                st.session_state.user_role = user.role
                cleanup_temp_states()
                st.rerun()
            else:
                st.error("用户名或密码错误")

def logout():
    for key in ["logged_in", "user_id", "username", "user_role"]:
        if key in st.session_state:
            del st.session_state[key]
    cleanup_temp_states()
    st.rerun()

if not st.session_state.get("logged_in", False):
    login()
    st.stop()

# ==================== 侧边栏统计信息 ====================
st.sidebar.title(f"欢迎，{st.session_state.username}")
st.sidebar.markdown(f"**角色**：{'主管' if st.session_state.user_role == 'manager' else '销售员'}")

if st.session_state.user_role == "manager":
    all_cust = get_customers()
    total_customers = len(all_cust)
    risk_flags = get_risk_flags(status="active")
    risk_customer_ids = set(f.customer_id for f in risk_flags)
    total_risk_customers = len(risk_customer_ids)
else:
    my_cust = get_customers(owner_id=st.session_state.user_id)
    total_customers = len(my_cust)
    risk_customer_ids = set()
    for c in my_cust:
        flags = get_risk_flags_for_customer(c.id, status="active")
        if flags:
            risk_customer_ids.add(c.id)
    total_risk_customers = len(risk_customer_ids)

st.sidebar.metric("📋 客户总数", total_customers)
st.sidebar.metric("⚠️ 风险客户数", total_risk_customers)

# 销售员未读督促消息
if st.session_state.user_role != "manager":
    unread_msgs = get_reminders_for_user(st.session_state.user_id, unread_only=True, limit=10)
    if unread_msgs:
        with st.sidebar.expander(f"📬 未读督促 ({len(unread_msgs)})", expanded=False):
            for msg in unread_msgs:
                st.markdown(f"**{msg['from_name']}** 提醒：{msg['message']}")
                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button("✓ 标记已读", key=f"read_{msg['id']}"):
                        mark_reminder_read(msg['id'])
                        cleanup_temp_states()
                        st.rerun()
                with col2:
                    st.caption(msg['created_at'][:16])
                st.divider()
            if st.button("全部标为已读", key="mark_all_read"):
                mark_all_reminders_read(st.session_state.user_id)
                cleanup_temp_states()
                st.rerun()
    else:
        st.sidebar.success("📭 暂无未读督促")

if st.sidebar.button("退出登录"):
    logout()

# 导航菜单
page = st.sidebar.radio("功能", ["客户管理", "风险看板", "每日日报"])

# ==================== 客户管理页面 ====================
if page == "客户管理":
    cleanup_temp_states()
    st.title("📋 客户管理")
    if st.session_state.user_role == "manager":
        st.caption("主管视角：只读查看所有客户的跟进记录")
        customers_data = get_all_customers_with_owner()
        if not customers_data:
            st.info("暂无客户数据")
        else:
            for cust in customers_data:
                with st.expander(f"**{cust['name']}** — {cust['company']} | {cust['stage']} | 负责销售：{cust['owner_fullname']}({cust['owner_username']})"):
                    st.write(f"联系方式：{cust['contact_info'] or '未填写'}")
                    st.write(f"创建时间：{cust['created_at'][:10] if cust['created_at'] else '-'}")
                    st.write(f"最后更新：{cust['updated_at'][:10] if cust['updated_at'] else '-'}")
                    latest_quotation = get_latest_quotation_amount(cust['id'])
                    if latest_quotation:
                        st.write(f"💰 最新报价：￥{latest_quotation:,.0f}")
                    
                    if st.button(f"📢 督促 {cust['owner_fullname']}", key=f"remind_{cust['id']}"):
                        msg = f"请重点关注客户 {cust['name']}（{cust['company']}）的跟进进度。"
                        add_reminder(
                            from_user_id=st.session_state.user_id,
                            to_user_id=cust['owner_id'],
                            message=msg,
                            customer_id=cust['id']
                        )
                        st.toast(f"已发送督促信息给 {cust['owner_fullname']}", icon="📨")
                        st.rerun()
                    
                    st.divider()
                    st.write("**跟进记录**")
                    follow_ups = get_follow_ups(cust['id'])
                    if follow_ups:
                        for fu in follow_ups:
                            st.write(f"- **{fu.action_type}** {fu.follow_up_time[:16]} : {fu.content}")
                            if fu.is_quotation_sent and fu.quotation_amount:
                                st.write(f"  💰 报价金额：￥{fu.quotation_amount:,.0f}")
                            elif fu.is_quotation_sent:
                                st.write(f"  💰 报价金额：未填写")
                    else:
                        st.write("暂无跟进记录")
    else:
        # 销售员视角（可编辑）
        st.caption("销售视角：管理自己的客户，可编辑信息及跟进记录")
        
        # 新增客户表单
        with st.expander("➕ 新增客户", expanded=False):
            with st.form("add_customer_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_name = st.text_input("客户姓名 *")
                    new_company = st.text_input("公司名称")
                with col2:
                    new_contact = st.text_input("联系方式")
                    new_stage = st.selectbox("当前阶段", STAGES)
                
                show_quotation = new_stage in ["已报价", "谈判中"]
                if show_quotation:
                    initial_quotation = st.number_input("💰 报价金额（元）", min_value=0.0, step=1000.0, value=0.0, help="首次报价金额，将自动生成一条报价跟进记录")
                else:
                    initial_quotation = None
                
                submitted = st.form_submit_button("添加客户")
                if submitted:
                    if not new_name.strip():
                        st.error("请输入客户姓名")
                    else:
                        cid = add_customer(
                            owner_id=st.session_state.user_id,
                            name=new_name.strip(),
                            company=new_company.strip(),
                            contact_info=new_contact.strip(),
                            stage=new_stage
                        )
                        if show_quotation and initial_quotation and initial_quotation > 0:
                            add_follow_up(
                                customer_id=cid,
                                action_type="邮件",
                                content=f"首次报价：￥{initial_quotation:,.0f}",
                                is_quotation_sent=True,
                                quotation_amount=initial_quotation
                            )
                            st.success(f"✅ 客户「{new_name}」已添加，并自动记录报价￥{initial_quotation:,.0f}")
                        else:
                            st.success(f"✅ 客户「{new_name}」已添加")
                        cleanup_temp_states()
                        st.rerun()
        
        customers = get_customers(owner_id=st.session_state.user_id)
        if not customers:
            st.info("暂无客户数据")
        else:
            for cust in customers:
                flags = get_risk_flags_for_customer(cust.id)
                risk_badge = f" 🔴 {len(flags)}个风险" if flags else ""
                with st.expander(f"**{cust.name}** — {cust.company} | {cust.stage}{risk_badge}"):
                    latest_quotation = get_latest_quotation_amount(cust.id)
                    if latest_quotation:
                        st.write(f"💰 最新报价：￥{latest_quotation:,.0f}")
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        new_name = st.text_input("客户姓名", value=cust.name, key=f"name_{cust.id}")
                    with col2:
                        new_company = st.text_input("公司名称", value=cust.company, key=f"company_{cust.id}")
                    with col3:
                        new_contact = st.text_input("联系方式", value=cust.contact_info, key=f"contact_{cust.id}")
                    new_stage = st.selectbox("当前阶段", STAGES, index=STAGES.index(cust.stage), key=f"stage_{cust.id}")
                    
                    col_save, col_del = st.columns(2)
                    with col_save:
                        if st.button("💾 保存修改", key=f"save_{cust.id}"):
                            update_customer(cust.id, name=new_name.strip(), company=new_company.strip(), contact_info=new_contact.strip(), stage=new_stage)
                            st.success("已保存")
                            cleanup_temp_states()
                            st.rerun()
                    with col_del:
                        if st.button("🗑️ 删除客户", key=f"del_{cust.id}"):
                            delete_customer(cust.id)
                            st.success("客户已删除")
                            cleanup_temp_states()
                            st.rerun()
                    
                    st.divider()
                    st.write("**跟进记录**")
                    follow_ups = get_follow_ups(cust.id)
                    if follow_ups:
                        for fu in follow_ups:
                            with st.container():
                                col_f1, col_f2, col_f3 = st.columns([4,1,1])
                                with col_f1:
                                    st.write(f"**{fu.action_type}** - {fu.follow_up_time[:16]}")
                                    st.write(f"内容: {fu.content}")
                                    if fu.is_quotation_sent:
                                        if fu.quotation_amount:
                                            st.write(f"💰 报价: ￥{fu.quotation_amount:,.0f}")
                                        else:
                                            st.write(f"💰 报价: 未填写金额")
                                with col_f2:
                                    if st.button("编辑", key=f"edit_fu_{fu.id}"):
                                        st.session_state[f"editing_fu_{fu.id}"] = True
                                with col_f3:
                                    if st.button("删除", key=f"del_fu_{fu.id}"):
                                        delete_follow_up(fu.id)
                                        cleanup_temp_states()
                                        st.rerun()
                                
                                if st.session_state.get(f"editing_fu_{fu.id}"):
                                    with st.form(key=f"edit_form_{fu.id}"):
                                        new_action = st.selectbox("动作类型", ACTION_TYPES, index=ACTION_TYPES.index(fu.action_type) if fu.action_type in ACTION_TYPES else 0)
                                        new_content = st.text_area("内容", value=fu.content)
                                        new_time = st.text_input("时间 (YYYY-MM-DD HH:MM:SS)", value=fu.follow_up_time)
                                        is_quotation = st.checkbox("发送报价", value=bool(fu.is_quotation_sent))
                                        new_amount = None
                                        if is_quotation:
                                            new_amount = st.number_input("报价金额", min_value=0.0, step=1000.0, value=fu.quotation_amount or 0.0)
                                        if st.form_submit_button("保存"):
                                            update_data = {
                                                "action_type": new_action,
                                                "content": new_content,
                                                "follow_up_time": new_time,
                                                "is_quotation_sent": int(is_quotation)
                                            }
                                            if is_quotation and new_amount is not None:
                                                update_data["quotation_amount"] = new_amount
                                            elif not is_quotation:
                                                update_data["quotation_amount"] = None
                                            update_follow_up(fu.id, **update_data)
                                            del st.session_state[f"editing_fu_{fu.id}"]
                                            cleanup_temp_states()
                                            st.rerun()
                                        if st.form_submit_button("取消"):
                                            del st.session_state[f"editing_fu_{fu.id}"]
                                            cleanup_temp_states()
                                            st.rerun()
                                st.divider()
                    else:
                        st.write("暂无跟进记录")
                    
                    with st.form(key=f"add_fu_{cust.id}"):
                        col_a1, col_a2 = st.columns(2)
                        with col_a1:
                            fu_action = st.selectbox("动作类型", ACTION_TYPES, key=f"act_{cust.id}")
                        with col_a2:
                            fu_time = st.text_input("跟进时间 (留空为现在)", value="", key=f"time_{cust.id}")
                        fu_content = st.text_area("跟进内容", key=f"cont_{cust.id}")
                        col_q1, col_q2 = st.columns(2)
                        with col_q1:
                            is_quotation = st.checkbox("发送报价", key=f"quot_{cust.id}")
                        with col_q2:
                            quotation_amt = None
                            if is_quotation:
                                quotation_amt = st.number_input("报价金额", min_value=0.0, step=1000.0, value=0.0, key=f"amt_{cust.id}")
                        if st.form_submit_button("添加跟进"):
                            if not fu_content.strip():
                                st.error("请输入跟进内容")
                            else:
                                add_follow_up(
                                    customer_id=cust.id,
                                    action_type=fu_action,
                                    content=fu_content.strip(),
                                    follow_up_time=fu_time if fu_time else None,
                                    is_quotation_sent=is_quotation,
                                    quotation_amount=quotation_amt if is_quotation and quotation_amt else None
                                )
                                st.success("跟进记录已添加")
                                cleanup_temp_states()
                                st.rerun()

elif page == "风险看板":
    st.title("⚠️ 风险看板")
    
    # 清理临时编辑状态
    for key in list(st.session_state.keys()):
        if key.startswith("editing_fu_") or key.startswith("edit_form_") or key.startswith("add_fu_"):
            del st.session_state[key]
    
    # 扫描按钮
    if st.button("🔄 重新扫描风险", key="scan_risk_btn"):
        with st.spinner("正在扫描所有客户的风险..."):
            scan_all_risks()  # 全局扫描，写入数据库
        st.success("✅ 风险扫描完成")
        # 强制刷新页面，以便重新读取数据库
        st.rerun()
    
    # 根据角色获取客户列表（关键过滤）
    if st.session_state.user_role == "manager":
        customers = get_customers()  # 主管看所有
    else:
        customers = get_customers(owner_id=st.session_state.user_id)  # 销售只看自己的
    
    # 构建风险客户列表，并统计当前用户的风险总数
    risk_items = []
    total_risk_count = 0
    for cust in customers:
        flags = get_risk_flags_for_customer(cust.id, status="active")
        if flags:
            risk_items.append((cust, flags))
            total_risk_count += len(flags)
    
    # 显示当前用户的风险统计
    st.metric("📊 您的客户风险标记总数", total_risk_count)
    
    if not risk_items:
        st.info("🎉 暂无风险客户，所有跟进状态正常！")
    else:
        st.write(f"当前共有 **{len(risk_items)}** 个风险客户")
        for cust, flags in risk_items:
            risk_num = len(flags)
            with st.expander(f"🔴 **{cust.name}**（{cust.company}）- {cust.stage}  [风险数: {risk_num}]"):
                for f in flags:
                    st.warning(f"⚠️ **{f.rule_name}**：{f.detail}")
                
                # AI 建议按钮
                if st.button(f"🤖 生成 AI 建议", key=f"advice_{cust.id}"):
                    with st.spinner("AI 思考中..."):
                        advice = generate_advice(cust.id)
                    st.success("建议如下：")
                    st.markdown(advice)
                
                # 主管与销售的不同操作
                if st.session_state.user_role == "manager":
                    owner = get_user_by_id(cust.owner_id)
                    owner_name = owner.fullname if owner else f"销售ID{cust.owner_id}"
                    if st.button(f"📢 督促 {owner_name}", key=f"remind_{cust.id}"):
                        msg = f"请关注客户 {cust.name} 的风险并采取行动。"
                        add_reminder(st.session_state.user_id, cust.owner_id, msg, cust.id)
                        st.toast(f"已发送督促给 {owner_name}", icon="📨")
                else:
                    if st.button(f"✅ 标记已处理", key=f"resolve_{cust.id}"):
                        for f in flags:
                            resolve_risk_flag(f.id)
                        st.success("已标记为已处理")
                        st.rerun()
# ==================== 每日日报页面 ====================
elif page == "每日日报":
    cleanup_temp_states()
    st.title("📊 每日日报")
    if st.button("生成今日日报"):
        with st.spinner("生成中..."):
            scan_all_risks()
            result_paths = generate_daily_report(
                user_id=st.session_state.user_id,
                user_role=st.session_state.user_role,
                formats=["txt", "md"]
            )
        st.success("日报已生成")
        if "txt" in result_paths:
            with open(result_paths["txt"], "rb") as f:
                st.download_button("下载 TXT 日报", data=f, file_name=os.path.basename(result_paths["txt"]))
        if "md" in result_paths:
            with open(result_paths["md"], "rb") as f:
                st.download_button("下载 Markdown 日报", data=f, file_name=os.path.basename(result_paths["md"]))