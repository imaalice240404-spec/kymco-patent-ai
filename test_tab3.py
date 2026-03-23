import os
import json
import random
import time
import datetime
import streamlit as st
import google.generativeai as genai
import pandas as pd
import numpy as np

# 👇 1. 建立 API 鑰匙池與初始化設定
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

st.set_page_config(page_title="機車專利大數據戰略中心", layout="wide")

# 安全讀取字串的輔助函數
def safe_str(val):
    if pd.isna(val): return ""
    return str(val).strip()

# ==========================================
# 🛠️ 開發者工具箱 (側邊欄) - 救援卡頓的神器
# ==========================================
with st.sidebar:
    st.markdown("### 🛠️ 系統狀態與除錯")
    total_records = len(st.session_state.master_db)
    st.info(f"🗄️ 總資料筆數: {total_records}")
    
    if total_records > 0:
        pending_count = len(st.session_state.master_db[st.session_state.master_db['狀態'] == 'PENDING'])
        completed_count = len(st.session_state.master_db[st.session_state.master_db['狀態'] == 'COMPLETED'])
        st.write(f"⏳ 等待分析 (PENDING): {pending_count}")
        st.write(f"✅ 分析完成 (COMPLETED): {completed_count}")
        
    st.markdown("---")
    if st.button("🗑️ 清空並重置資料庫 (遇到 Bug 按這個)", use_container_width=True):
        st.session_state.master_db = pd.DataFrame(columns=st.session_state.master_db.columns)
        st.rerun()

st.title("🏍️ 機車專利大數據戰略中心")

# 建立三大核心模組的 Tab
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
            
            # 智能映射 TWPAT 欄位
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
                
                if not p_id or p_id == "nan":
                    continue 
                    
                # 檢查是否已存在
                if p_id in st.session_state.master_db['申請號'].values or p_id in st.session_state.master_db['證書號'].values:
                    skip_records += 1
                    continue
                
                new_row = {
                    '申請號': app_val,
                    '證書號': cert_val,
                    '公開公告日': safe_str(row[col_map['date']]) if col_map['date'] else "未知",
                    '專利權人': safe_str(row[col_map['assignee']]) if col_map['assignee'] else "未知",
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
    st.header("2. AI 批次特徵萃取 (嚴謹樹狀分類)")
    
    pending_df = st.session_state.master_db[st.session_state.master_db['狀態'] == 'PENDING']
    
    if len(pending_df) > 0:
        st.info(f"⏳ 目前有 **{len(pending_df)}** 筆專利等待 AI 萃取特徵。下方為前 5 筆預覽：")
        st.dataframe(pending_df[['申請號', '專利名稱', '專利權人', '狀態']].head(5))
        
        batch_size = st.slider("選擇本次交給 AI 處理的筆數 (避免 API Timeout)", 1, min(50, len(pending_df)), min(10, len(pending_df)))
        
        if st.button(f"🤖 啟動高階探勘管線 (處理 {batch_size} 筆)", type="primary"):
            process_df = pending_df.head(batch_size)
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, (idx, row) in enumerate(process_df.iterrows()):
                status_text.text(f"正在分析 ({i+1}/{batch_size}): {row['專利名稱']}")
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
                
                progress_bar.progress((i + 1) / batch_size)
            
            st.success("✅ 本批次分析完成！請切換至【模組二】查看結果。")
            time.sleep(1)
            st.rerun()
    else:
        st.write("✅ 目前沒有需要分析的資料。請上傳 Excel 匯入新專利。")

# ==========================================
# 模組二：研發知識庫與任務分發 (檢索 + 購物車)
# ==========================================
with tab_dashboard:
    completed_df = st.session_state.master_db[st.session_state.master_db['狀態'] == 'COMPLETED']
    
    if completed_df.empty:
        st.warning("⚠️ 目前資料庫中沒有「已完成分析」的專利。請先至【模組一】啟動 AI 探勘管線！")
    else:
        st.header("🔍 研發技術情報檢索 (R&D Filter Hub)")
        st.markdown("媲美 TWPAT 但更純粹的過濾系統，勾選目標後即可發送至各大分析引擎。")
        
        # --- 1. 檢索設定區 ---
        with st.container(border=True):
            st.markdown("#### 🎯 核心檢索條件")
            
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
                filter_company = st.multiselect("🏢 4. 競爭對手 (專利權人)", companies, placeholder="可複選，例如：光陽, 三陽, HONDA")
            
            with col_f5:
                # 日期安全處理
                temp_dates = pd.to_datetime(completed_df['公開公告日'], errors='coerce')
                min_val = temp_dates.min().date() if not pd.isna(temp_dates.min()) else datetime.date(2000, 1, 1)
                max_val = temp_dates.max().date() if not pd.isna(temp_dates.max()) else datetime.date.today()
                
                filter_date = st.date_input("📅 5. 公開/公告日區間", 
                                          value=(min_val, max_val),
                                          min_value=min_val, 
                                          max_value=max_val)

        # --- 2. 執行過濾邏輯 ---
        filtered_df = completed_df.copy()
        
        if filter_main != "全部":
            filtered_df = filtered_df[filtered_df['五大類'] == filter_main]
        if filter_sub != "全部":
            filtered_df = filtered_df[filtered_df['次系統'] == filter_sub]
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

        st.info(f"✨ 檢索完成：共篩選出 **{len(filtered_df)}** 筆目標專利。")

        # --- 3. 專利購物車 ( Interactive Data Editor ) ---
        if not filtered_df.empty:
            st.markdown("### 🛒 勾選目標進入進階分析")
            
            display_cols = ['證書號', '專利名稱', '專利權人', '公開公告日', '五大類', '次系統']
            display_df = filtered_df[display_cols].copy()
            display_df.insert(0, "☑️ 選取", False)

            edited_df = st.data_editor(
                display_df,
                column_config={
                    "☑️ 選取": st.column_config.CheckboxColumn("勾選", default=False),
                    "證書號": st.column_config.TextColumn("專利號", width="medium"),
                    "專利名稱": st.column_config.TextColumn("專利名稱", width="large"),
                },
                disabled=display_cols, 
                hide_index=True,
                use_container_width=True,
                height=min(400, (len(display_df) + 1) * 35 + 3) 
            )

            # --- 4. 行動指令列 ( Action Bar ) ---
            selected_ids = edited_df[edited_df["☑️ 選取"] == True]['證書號'].tolist()
            selected_patents = filtered_df[filtered_df['證書號'].isin(selected_ids)]

            st.markdown("---")
            if selected_patents.empty:
                st.warning("👆 請從上方列表勾選至少一篇專利，以啟動進階分析引擎。")
            else:
                st.success(f"🎯 鎖定目標：已選取 **{len(selected_patents)}** 篇專利！請指派分析任務：")
                
                col_btn1, col_btn2, col_btn3 = st.columns(3)
                
                with col_btn1:
                    if st.button("📄 1. 進入單篇深度拆解", use_container_width=True):
                        if len(selected_patents) > 1:
                            st.error("⚠️ 單篇拆解建議一次勾選 1 篇喔！請取消多餘的勾選。")
                        else:
                            st.session_state.target_single_patent = selected_patents.iloc[0].to_dict()
                            st.balloons()
                            st.toast("✅ 已載入單篇資料！準備呼叫單篇分析引擎...")
                            
                with col_btn2:
                    if st.button("📊 2. 傳統專利分析 (儀表板)", use_container_width=True):
                        if len(selected_patents) < 2:
                            st.warning("⚠️ 建議勾選多篇專利以生成統計圖表！")
                        else:
                            st.session_state.target_macro_pool = selected_patents
                            st.toast(f"✅ 已載入 {len(selected_patents)} 篇資料！準備呼叫地圖引擎...")
                        
                with col_btn3:
                    if st.button("⚔️ 3. 組合核駁分析 (AI特務)", use_container_width=True):
                        if len(selected_patents) < 2:
                            st.error("⚠️ 組合核駁至少需要勾選 2 篇專利（引證一 + 引證二）！")
                        else:
                            st.session_state.target_combo_pool = selected_patents
                            st.toast("✅ 已載入引證組合！啟動 Agent...")

# ==========================================
# 模組三：無效化特務 (Agentic Search)
# ==========================================
with tab_agent:
    st.header("🕵️ 自主前案檢索與無效化特務")
    st.write("（介面保留區：未來可在此整合自動檢索的 AI Agent 邏輯）")
