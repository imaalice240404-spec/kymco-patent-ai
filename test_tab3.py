import os
import json
import random
import streamlit as st
import google.generativeai as genai
import pandas as pd

# 👇 建立 API 鑰匙池
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# 🌟 初始化：統一專利資料庫 (State Machine)
# 包含欄位: patent_num, title, abstract, claim, status(PENDING/COMPLETED/FAILED), legal_status, category, mechanism, effect, solution
if 'master_db' not in st.session_state:
    st.session_state.master_db = pd.DataFrame(columns=[
        '專利號', '專利名稱', '摘要', '請求項', '狀態', '法律狀態', 
        '大分類', '特殊機構', '達成功效', '核心解法'
    ])

st.set_page_config(page_title="專利大數據戰略中心", layout="wide")

# --- 簡易密碼門禁 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔒 系統登入")
        pwd = st.text_input("請輸入授權密碼", type="password")
        if pwd == st.secrets.get("APP_PASSWORD", "1234"): # 預設1234方便測試
            st.session_state["password_correct"] = True
            st.rerun()
        elif pwd:
            st.error("密碼錯誤，請重新輸入！")
        return False
    return True

if not check_password():
    st.stop()
# --- 門禁結束 ---

st.title("🏍️ 專利大數據與檢索分析平台")
st.markdown("整合 Autoresearch 自動探勘管線與漏斗式宏觀檢索。")

# 🌟 建立兩大核心模組的 Tab
tab_ingest, tab_dashboard = st.tabs(["📥 模組一：自動探勘與資料匯入 (Autoresearch)", "📊 模組二：宏觀檢索與研發知識庫 (Dashboard)"])

# ==========================================
# 模組一：自動探勘與資料匯入 (Autoresearch Pipeline)
# ==========================================
with tab_ingest:
    st.header("1. 資料匯入與去重檢查 (Ingestion & Deduplication)")
    
    col_upload, col_settings = st.columns([2, 1])
    with col_upload:
        uploaded_excel = st.file_uploader("上傳 TWPAT 匯出的專利清單", type=["xlsx", "xls", "csv"])
    with col_settings:
        batch_legal_status = st.selectbox("此批專利的預設法律狀態", ["已失效 (RD開源用)", "存續中 (智權防禦用)"])

    if uploaded_excel:
        if st.button("🔄 執行資料比對與匯入", type="primary"):
            df = pd.read_csv(uploaded_excel) if uploaded_excel.name.endswith('.csv') else pd.read_excel(uploaded_excel)
            
            # 尋找關鍵欄位
            title_col = next((col for col in df.columns if '專利名稱' in col or '標題' in col), None)
            abstract_col = next((col for col in df.columns if '摘要' in col), None)
            patent_num_col = next((col for col in df.columns if '號' in col and ('公開' in col or '公告' in col or '申請' in col)), None)
            claim_col = next((col for col in df.columns if '申請專利範圍' in col or '請求項' in col), None)

            if patent_num_col:
                new_records = 0
                skip_records = 0
                
                # 將新資料轉換為系統標準格式
                for _, row in df.iterrows():
                    p_num = str(row[patent_num_col])
                    # 💡 核心邏輯：去重檢查 (避免重複分析)
                    if p_num in st.session_state.master_db['專利號'].values:
                        skip_records += 1
                        continue
                    
                    new_row = {
                        '專利號': p_num,
                        '專利名稱': str(row[title_col]) if title_col else "無",
                        '摘要': str(row[abstract_col]).replace('\n', '')[:250] if abstract_col else "無",
                        '請求項': str(row[claim_col]).replace('\n', '')[:300] if claim_col else "無",
                        '狀態': 'PENDING', # 預設等待 AI 處理
                        '法律狀態': batch_legal_status,
                        '大分類': '', '特殊機構': '', '達成功效': '', '核心解法': ''
                    }
                    st.session_state.master_db = pd.concat([st.session_state.master_db, pd.DataFrame([new_row])], ignore_index=True)
                    new_records += 1
                
                st.success(f"✅ 匯入完成！新增 {new_records} 筆 PENDING 資料，跳過 {skip_records} 筆已存在資料。")

    st.markdown("---")
    st.header("2. AI 批次特徵萃取 (Batch Processing)")
    
    # 計算目前等待處理的數量
    pending_df = st.session_state.master_db[st.session_state.master_db['狀態'] == 'PENDING']
    st.info(f"⏳ 目前有 **{len(pending_df)}** 筆專利等待 AI 萃取特徵。")

    if len(pending_df) > 0:
        batch_size = st.slider("選擇本次 AI 處理的批次量", min_value=1, max_value=20, value=min(10, len(pending_df)))
        
        if st.button("🤖 啟動 Autoresearch 分析", type="primary"):
            process_df = pending_df.head(batch_size)
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, (idx, row) in enumerate(process_df.iterrows()):
                status_text.text(f"正在分析 ({i+1}/{batch_size}): {row['專利號']}")
                
                prompt = f"""
                你是一位機車廠的資深研發顧問。請閱讀以下專利，並提取結構化資訊。
                【專利號】：{row['專利號']}
                【名稱】：{row['專利名稱']}
                【摘要】：{row['摘要']}
                【請求項】：{row['請求項']}

                請嚴格輸出 JSON 格式 (不要有 markdown 標記)，格式如下：
                {{
                  "大分類": "從 [引擎與動力系統, 傳動系統, 煞車系統, 車架與懸吊系統, 電系與儀表控制, 外觀件與其他] 中選1",
                  "特殊機構": "15字內，核心物理設計",
                  "達成功效": "20字內，解決了什麼痛點",
                  "核心解法": "用白話文簡述運作原理，給工程師參考"
                }}
                """
                
                try:
                    response = model.generate_content(prompt)
                    clean_text = response.text.replace('```json', '').replace('```', '').strip()
                    clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                    result = json.loads(clean_text)
                    
                    # 更新資料庫狀態
                    st.session_state.master_db.at[idx, '大分類'] = result.get('大分類', '其他')
                    st.session_state.master_db.at[idx, '特殊機構'] = result.get('特殊機構', '')
                    st.session_state.master_db.at[idx, '達成功效'] = result.get('達成功效', '')
                    st.session_state.master_db.at[idx, '核心解法'] = result.get('核心解法', '')
                    st.session_state.master_db.at[idx, '狀態'] = 'COMPLETED'
                    
                except Exception as e:
                    st.session_state.master_db.at[idx, '狀態'] = 'FAILED'
                    st.error(f"專利 {row['專利號']} 分析失敗: {e}")
                
                progress_bar.progress((i + 1) / batch_size)
            
            status_text.text("✅ 本批次處理完成！請前往「宏觀檢索」分頁查看。")
            st.rerun()

# ==========================================
# 模組二：宏觀檢索與研發知識庫 (Dashboard View)
# ==========================================
with tab_dashboard:
    completed_df = st.session_state.master_db[st.session_state.master_db['狀態'] == 'COMPLETED']
    
    if completed_df.empty:
        st.warning("目前沒有已完成分析的專利，請先至「自動探勘」分頁進行處理。")
    else:
        st.header("🔍 宏觀檢索與漏斗過濾")
        
        # 建立篩選器 (Filter Funnel)
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_legal = st.multiselect("⚖️ 法律狀態視角", completed_df['法律狀態'].unique(), default=completed_df['法律狀態'].unique())
        with col_f2:
            filter_cat = st.multiselect("🏷️ 系統大分類", completed_df['大分類'].unique())
        with col_f3:
            search_query = st.text_input("🎯 關鍵字 (找痛點/機構/解法)")

        # 套用篩選條件
        filtered_df = completed_df.copy()
        if filter_legal:
            filtered_df = filtered_df[filtered_df['法律狀態'].isin(filter_legal)]
        if filter_cat:
            filtered_df = filtered_df[filtered_df['大分類'].isin(filter_cat)]
        if search_query:
            # 在多個欄位中搜尋關鍵字
            mask = filtered_df[['專利名稱', '特殊機構', '達成功效', '核心解法']].apply(
                lambda x: x.str.contains(search_query, na=False, case=False)
            ).any(axis=1)
            filtered_df = filtered_df[mask]

        st.info(f"篩選結果：共 **{len(filtered_df)}** 筆專利符合條件。")
        
        # 視覺化展示 (卡片設計)
        for _, p in filtered_df.iterrows():
            with st.container(border=True):
                # 依據法律狀態給予不同的視覺提示
                if p['法律狀態'] == '已失效 (RD開源用)':
                    badge = "🟢 **【開源技術庫：免授權直接參考】**"
                else:
                    badge = "🔴 **【高威脅前案：注意侵權風險】**"
                    
                st.markdown(f"**[{p['專利號']}] {p['專利名稱']}**")
                st.markdown(f"{badge}")
                
                col_tag1, col_tag2, col_tag3 = st.columns(3)
                col_tag1.info(f"📂 **系統分類**：{p['大分類']}")
                col_tag2.warning(f"⚙️ **特殊機構**：{p['特殊機構']}")
                col_tag3.error(f"🎯 **達成功效**：{p['達成功效']}")
                
                st.markdown(f"**💡 核心解法：**\n> {p['核心解法']}")
                
                # 預留進入單篇深度分析的按鈕空間
                if st.button("進入單篇深度拆解 (Tab 1/2)", key=p['專利號']):
                    st.toast(f"未來這裡會跳轉至 {p['專利號']} 的 3D圖面/文義比對 頁面！")
