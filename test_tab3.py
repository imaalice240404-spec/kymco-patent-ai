import os
import json
import random
import time
import datetime
import streamlit as st
import google.generativeai as genai
import pandas as pd
import numpy as np
import re

# ==========================================
# 👇 1. 建立 API 鑰匙池與初始化設定
# ==========================================
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# 🌟 初始化：統一專利資料庫
if 'master_db' not in st.session_state:
    st.session_state.master_db = pd.DataFrame(columns=[
        '申請號', '證書號', '公開公告日', '專利權人', 
        '專利名稱', '摘要', '請求項', '案件狀態',
        '狀態', '五大類', '次系統', '特殊機構', '達成功效', '核心解法'
    ])

# 🌟 初始化：購物車勾選狀態
if 'selected_patents_set' not in st.session_state:
    st.session_state.selected_patents_set = set()

st.set_page_config(page_title="機車專利大數據戰略中心", layout="wide")

# ==========================================
# 🛠️ 輔助函數：資料清洗
# ==========================================
def safe_str(val):
    if pd.isna(val): return ""
    return str(val).strip()

def clean_assignee(name):
    """將冗長的專利權人名稱收斂 (去除股份公司與地址)"""
    name = safe_str(name)
    if not name: return "未知"
    name = re.split(r'股份有限公司|有限公司|公司', name)[0].strip()
    name = name.split(' ')[0].strip() 
    return name if name else "未知"

# ==========================================
# 🛠️ 開發者工具箱 (側邊欄) - 救援卡頓與監控錯誤
# ==========================================
with st.sidebar:
    st.markdown("### 🛠️ 系統狀態與除錯")
    total_records = len(st.session_state.master_db)
    st.info(f"🗄️ 總資料筆數: {total_records}")
    
    if total_records > 0:
        pending_count = len(st.session_state.master_db[st.session_state.master_db['狀態'] == 'PENDING'])
        completed_count = len(st.session_state.master_db[st.session_state.master_db['狀態'] == 'COMPLETED'])
        failed_count = len(st.session_state.master_db[st.session_state.master_db['狀態'] == 'FAILED'])
        
        st.write(f"⏳ 等待分析 (PENDING): {pending_count}")
        st.write(f"✅ 分析完成 (COMPLETED): {completed_count}")
        st.write(f"❌ 分析失敗 (FAILED): {failed_count}") # 🌟 抓出死掉的資料
        
    st.markdown("---")
    if st.button("🗑️ 清空並重置資料庫 (遇到問題按這個)", use_container_width=True):
        st.session_state.master_db = pd.DataFrame(columns=st.session_state.master_db.columns)
        st.session_state.selected_patents_set = set()
        st.rerun()

st.title("🏍️ 機車專利大數據戰略中心")

tab_ingest, tab_dashboard, tab_agent = st.tabs([
    "📥 模組一：自動探勘與資料匯入", 
    "📊 模組二：研發知識庫與任務分發", 
    "🕵️ 模組三：無效化特務 (Agentic Search)"
])

# ==========================================
# 模組一：自動探勘與資料匯入 
# ==========================================
with tab_ingest:
    st.header("1. TWPAT 資料匯入")
    uploaded_excel = st.file_uploader("上傳 TWPAT 匯出的 Excel/CSV", type=["xlsx", "xls", "csv"])

    if uploaded_excel:
        if st.button("🔄 執行資料比對與匯入", type="primary"):
            df = pd.read_csv(uploaded_excel) if uploaded_excel.name.endswith('.csv') else pd.read_excel(uploaded_excel)
            
            col_map = {
                'title': next((c for c in df.columns if '名稱' in c or '標題' in c), None),
                'abs': next((c for c in df.columns if '摘要' in c), None),
                'claim': next((c for c in df.columns if '範圍' in c or '請求' in c), None),
                'app_num': next((c for c in df.columns if '申請號' in c), None),
                'cert_num': next((c for c in df.columns if '證書' in c or '公告號' in c or '公開號' in c), None),
                'date': next((c for c in df.columns if '日' in c and ('公開' in c or '公告' in c)), None),
                'assignee': next((c for c in df.columns if '權人' in c or '申請人' in c), None),
                'status': next((c for c in df.columns if '狀態' in c), None)
            }

            new_records = 0
            skip_records = 0
            
            for _, row in df.iterrows():
                app_val = safe_str(row[col_map['app_num']]) if col_map['app_num'] else ""
                cert_val = safe_str(row[col_map['cert_num']]) if col_map['cert_num'] else ""
                p_id = app_val if app_val else cert_val
                
                if not p_id or p_id == "nan": continue 
                    
                if p_id in st.session_state.master_db['申請號'].values or p_id in st.session_state.master_db['證書號'].values:
                    skip_records += 1
                    continue
                
                raw_assignee = safe_str(row[col_map['assignee']]) if col_map['assignee'] else ""
                clean_name = clean_assignee(raw_assignee)
                
                new_row = {
                    '申請號': app_val,
                    '證書號': cert_val,
                    '公開公告日': safe_str(row[col_map['date']]) if col_map['date'] else "未知",
                    '專利權人': clean_name,
                    '專利名稱': safe_str(row[col_map['title']]) if col_map['title'] else "無名稱",
                    '摘要': safe_str(row[col_map['abs']]).replace('\n', '')[:250] if col_map['abs'] else "無摘要",
                    '請求項': safe_str(row[col_map['claim']]).replace('\n', '')[:300] if col_map['claim'] else "無請求項",
                    '案件狀態': safe_str(row[col_map['status']]) if col_map['status'] else "未知",
                    '狀態': 'PENDING',
                    '五大類': '', '次系統': '', '特殊機構': '', '達成功效': '', '核心解法': ''
                }
                st.session_state.master_db = pd.concat([st.session_state.master_db, pd.DataFrame([new_row])], ignore_index=True)
                new_records += 1
            
            st.success(f"✅ 匯入完成！成功提取 {new_records} 筆新資料，跳過 {skip_records} 筆重複資料。")

    st.markdown("---")
    st.header("2. AI 批次特徵萃取 (具備防擋煞車系統)")
    
    pending_df = st.session_state.master_db[st.session_state.master_db['狀態'] == 'PENDING']
    
    if len(pending_df) > 0:
        st.info(f"⏳ 目前有 **{len(pending_df)}** 筆專利等待 AI 萃取特徵。")
        batch_size = st.slider("選擇本次交給 AI 處理的筆數 (建議每次 10-20 筆)", 1, min(50, len(pending_df)), min(5, len(pending_df)))
        
        if st.button(f"🤖 啟動高階探勘管線 (處理 {batch_size} 筆)", type="primary"):
            process_df = pending_df.head(batch_size)
            progress_bar = st.progress(0)
            status_text = st.empty()
            error_log = st.empty() # 🌟 用來顯示真實錯誤原因的區塊

            for i, (idx, row) in enumerate(process_df.iterrows()):
                status_text.text(f"正在分析 ({i+1}/{batch_size}): {row['專利名稱']} ...")
                prompt = f"""
                你是一位機車廠的資深研發總監。請閱讀以下專利，並進行嚴格的技術拆解。
                【名稱】：{row['專利名稱']}
                【摘要】：{row['摘要']}
                【請求項】：{row['請求項']}

                請嚴格輸出 JSON 格式：
                {{
                  "五大類": "從 [動力引擎, 車體, 懸吊, 電裝, 機電] 中選一",
                  "次系統": "若為動力引擎，選 [呼吸與進氣系統, 引擎本體與燃燒核心, 冷卻與排熱系統, 傳動與排氣]。其餘自訂精煉 5-8 字",
                  "特殊機構": "15字內核心物理設計",
                  "達成功效": "20字內解決痛點",
                  "核心解法": "用工程師白話文簡述運作原理"
                }}
                """
                try:
                    response = model.generate_content(prompt)
                    clean_text = response.text.replace('```json', '').replace('```', '').strip()
                    clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                    result = json.loads(clean_text)
                    
                    st.session_state.master_db.at[idx, '五大類'] = result.get('五大類', '未分類')
                    st.session_state.master_db.at[idx, '次系統'] = result.get('次系統', '未分類')
                    st.session_state.master_db.at[idx, '特殊機構'] = result.get('特殊機構', '')
                    st.session_state.master_db.at[idx, '達成功效'] = result.get('達成功效', '')
                    st.session_state.master_db.at[idx, '核心解法'] = result.get('核心解法', '')
                    st.session_state.master_db.at[idx, '狀態'] = 'COMPLETED'
                    
                except Exception as e:
                    st.session_state.master_db.at[idx, '狀態'] = 'FAILED'
                    # 🌟 抓出靜默失敗的真兇並印在畫面上
                    error_log.error(f"❌ [{row['專利名稱']}] 分析失敗: {e}")
                
                progress_bar.progress((i + 1) / batch_size)
                # 🌟 絕對關鍵的煞車系統：強迫程式休息，防止 Google API 封鎖
                time.sleep(2) 
            
            st.success("✅ 本批次分析執行完畢！請檢查左側面板的成功/失敗數量。")

# ==========================================
# 模組二：研發知識庫與任務分發 (R&D 工作流完美版)
# ==========================================
with tab_dashboard:
    completed_df = st.session_state.master_db[st.session_state.master_db['狀態'] == 'COMPLETED']
    
    if completed_df.empty:
        st.warning("⚠️ 目前資料庫中沒有「已完成分析」的專利。請先至【模組一】啟動 AI 探勘管線！")
    else:
        st.header("🔍 研發技術情報檢索 (R&D Filter Hub)")
        
        # ---------------------------------------------------------
        # 1. 檢索過濾器 (Filter Hub)
        # ---------------------------------------------------------
        with st.container(border=True):
            col_f1, col_f2, col_f3 = st.columns(3)
            with col_f1:
                filter_main = st.selectbox("📂 1. 大系統", ["全部"] + list(completed_df['五大類'].unique()))
            with col_f2:
                sub_options = ["全部"]
                if filter_main != "全部":
                    sub_options += list(completed_df[completed_df['五大類'] == filter_main]['次系統'].unique())
                filter_sub = st.selectbox("⚙️ 2. 次系統", sub_options)
            with col_f3:
                search_query = st.text_input("🔑 3. 關鍵字 (找痛點/機構)")

            col_f4, col_f5 = st.columns([1, 1])
            with col_f4:
                companies = [c for c in completed_df['專利權人'].unique() if c and c != "未知"]
                filter_company = st.multiselect("🏢 4. 競爭對手", companies, placeholder="可複選，例如：三陽工業")
            with col_f5:
                temp_dates = pd.to_datetime(completed_df['公開公告日'], errors='coerce')
                min_val = temp_dates.min().date() if not pd.isna(temp_dates.min()) else datetime.date(2000, 1, 1)
                max_val = temp_dates.max().date() if not pd.isna(temp_dates.max()) else datetime.date.today()
                filter_date = st.date_input("📅 5. 公開/公告日區間", value=(min_val, max_val), min_value=min_val, max_value=max_val)

        # 執行過濾邏輯
        filtered_df = completed_df.copy()
        if filter_main != "全部": filtered_df = filtered_df[filtered_df['五大類'] == filter_main]
        if filter_sub != "全部": filtered_df = filtered_df[filtered_df['次系統'] == filter_sub]
        if filter_company:
            mask = filtered_df['專利權人'].apply(lambda x: any(c in str(x) for c in filter_company))
            filtered_df = filtered_df[mask]
        if len(filter_date) == 2:
            start_date, end_date = filter_date
            valid_date_mask = pd.to_datetime(filtered_df['公開公告日'], errors='coerce').dt.date.between(start_date, end_date)
            filtered_df = filtered_df[valid_date_mask | (filtered_df['公開公告日'] == "未知")]
        if search_query:
            mask = filtered_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            filtered_df = filtered_df[mask]

        st.info(f"✨ 檢索完成：共篩選出 **{len(filtered_df)}** 筆專利。")

        # ---------------------------------------------------------
        # 2. 宏觀與組合分析指令區 (Action Bar 置頂)
        # ---------------------------------------------------------
        # 動態計算目前有被「打勾」的專利數量
        selected_ids = [k.split("chk_")[1] for k, v in st.session_state.items() if k.startswith("chk_") and v]
        
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            # 傳統分析：直接針對上方過濾出來的 N 筆資料進行地圖繪製
            if st.button(f"📊 傳統專利分析 (針對目前篩選的 {len(filtered_df)} 筆)", use_container_width=True, type="primary"):
                st.session_state.target_macro_pool = filtered_df
                st.toast("✅ 啟動宏觀專利地圖引擎...")
                # 這裡未來接你的傳統分析代碼
                
        with col_act2:
            # 組合分析：針對下方被打勾的資料
            if st.button(f"⚔️ 組合核駁分析 (針對下方已勾選的 {len(selected_ids)} 筆)", use_container_width=True, type="secondary"):
                if len(selected_ids) < 2:
                    st.error("⚠️ 組合核駁至少需要在下方卡片勾選 2 篇專利！")
                else:
                    selected_patents_df = completed_df[completed_df['證書號'].isin(selected_ids) | completed_df['申請號'].isin(selected_ids)]
                    st.session_state.target_combo_pool = selected_patents_df
                    st.toast("✅ 啟動 AI 組合特務...")
                    # 這裡未來接你的組合分析代碼

        st.markdown("---")

        # ---------------------------------------------------------
        # 3. 專利情報卡片渲染 (內含單篇分析按鈕)
        # ---------------------------------------------------------
        for _, p in filtered_df.iterrows():
            disp_id = p['證書號'] if p['證書號'] else p['申請號']
            
            with st.container(border=True):
                col_chk, col_content = st.columns([0.5, 9.5])
                
                with col_chk:
                    st.write("") 
                    # 勾選框的狀態會自動被 Streamlit 記住在 session_state["chk_專利號"] 裡面
                    st.checkbox("選取", key=f"chk_{disp_id}", label_visibility="collapsed")
                
                with col_content:
                    status_color = "🟢" if "消滅" in p['案件狀態'] or "撤回" in p['案件狀態'] else "🟠"
                    st.markdown(f"#### {status_color} [{disp_id}] {p['專利名稱']}")
                    st.caption(f"**🏢 權利人:** {p['專利權人']} ｜ **📅 日期:** {p['公開公告日']} ｜ **⚖️ 狀態:** {p['案件狀態']}")
                    
                    st.markdown("---")
                    col_t1, col_t2, col_t3 = st.columns([1.5, 1.5, 2])
                    with col_t1:
                        st.markdown(f"**📂 分類：**\n{p['五大類']} ➡️ {p['次系統']}")
                    with col_t2:
                        st.markdown(f"**⚙️ 特殊機構：**\n{p['特殊機構']}")
                    with col_t3:
                        st.markdown(f"**🎯 達成功效：**\n{p['達成功效']}")
                    
                    st.markdown(f"**💡 核心解法：**\n> {p['核心解法']}")
                    
                    # 🌟 單篇分析按鈕直接嵌在卡片底部
                    if st.button("📄 進入單篇深度拆解", key=f"btn_single_{disp_id}"):
                        st.session_state.target_single_patent = p.to_dict()
                        st.toast(f"✅ 已載入 [{disp_id}]！準備呼叫單篇分析引擎...")
                        # 這裡未來接你的單篇分析代碼
# ==========================================
# 模組三：無效化特務 (Agentic Search)
# ==========================================
with tab_agent:
    st.header("🕵️ 自主前案檢索與無效化特務")
    st.write("（介面保留區：未來可在此整合自動檢索的 AI Agent 邏輯）")
