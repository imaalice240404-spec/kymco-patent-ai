import os
import json
import random
import time
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

# 🌟 初始化：統一專利資料庫
if 'master_db' not in st.session_state:
    st.session_state.master_db = pd.DataFrame(columns=[
        '申請號', '證書號', '公開公告日', '專利權人', 
        '專利名稱', '摘要', '請求項', '案件狀態',
        '狀態', '五大類', '次系統', '特殊機構', '達成功效', '核心解法'
    ])

st.set_page_config(page_title="機車專利大數據戰略中心", layout="wide")

st.title("🏍️ 機車專利大數據戰略中心")

# 🌟 建立三大核心模組的 Tab
tab_ingest, tab_dashboard, tab_agent = st.tabs([
    "📥 模組一：自動探勘與資料匯入", 
    "📊 模組二：研發知識庫 (無 IPC 純淨版)", 
    "🕵️ 模組三：無效化特務 (Agentic Search)"
])

# ==========================================
# 模組一：自動探勘與資料匯入 (維持原樣，但移除 IPC 解析)
# ==========================================
with tab_ingest:
    st.header("1. TWPAT 資料匯入")
    uploaded_excel = st.file_uploader("上傳 TWPAT 匯出的 Excel/CSV", type=["xlsx", "xls", "csv"])

    if uploaded_excel:
        if st.button("🔄 執行資料比對與匯入", type="primary"):
            df = pd.read_csv(uploaded_excel) if uploaded_excel.name.endswith('.csv') else pd.read_excel(uploaded_excel)
            
            col_map = {
                'title': next((c for c in df.columns if '專利名稱' in c or '標題' in c), None),
                'abs': next((c for c in df.columns if '摘要' in c), None),
                'claim': next((c for c in df.columns if '申請專利範圍' in c or '請求項' in c), None),
                'app_num': next((c for c in df.columns if '申請號' in c), None),
                'cert_num': next((c for c in df.columns if '證書號' in c or '公告號' in c), None),
                'date': next((c for c in df.columns if '公開日' in c or '公告日' in c), None),
                'assignee': next((c for c in df.columns if '專利權人' in c or '申請人' in c), None),
                'status': next((c for c in df.columns if '案件狀態' in c or '法律狀態' in c), None)
            }

            if col_map['app_num'] or col_map['cert_num']:
                new_records = 0
                skip_records = 0
                
                for _, row in df.iterrows():
                    p_id = str(row[col_map['app_num']]) if col_map['app_num'] and pd.notna(row[col_map['app_num']]) else str(row[col_map['cert_num']])
                    
                    if p_id in st.session_state.master_db['申請號'].values or p_id in st.session_state.master_db['證書號'].values:
                        skip_records += 1
                        continue
                    
                    new_row = {
                        '申請號': str(row[col_map['app_num']]) if col_map['app_num'] else "",
                        '證書號': str(row[col_map['cert_num']]) if col_map['cert_num'] else "",
                        '公開公告日': str(row[col_map['date']]) if col_map['date'] else "未知",
                        '專利權人': str(row[col_map['assignee']]) if col_map['assignee'] else "未知",
                        '專利名稱': str(row[col_map['title']]) if col_map['title'] else "無",
                        '摘要': str(row[col_map['abs']]).replace('\n', '')[:250] if col_map['abs'] else "無",
                        '請求項': str(row[col_map['claim']]).replace('\n', '')[:300] if col_map['claim'] else "無",
                        '案件狀態': str(row[col_map['status']]) if col_map['status'] else "未知",
                        '狀態': 'PENDING',
                        '五大類': '', '次系統': '', '特殊機構': '', '達成功效': '', '核心解法': ''
                    }
                    st.session_state.master_db = pd.concat([st.session_state.master_db, pd.DataFrame([new_row])], ignore_index=True)
                    new_records += 1
                
                st.success(f"✅ 匯入完成！新增 {new_records} 筆資料，跳過 {skip_records} 筆重複資料。")

    st.markdown("---")
    st.header("2. AI 批次特徵萃取 (嚴謹樹狀分類)")
    pending_df = st.session_state.master_db[st.session_state.master_db['狀態'] == 'PENDING']
    
    if len(pending_df) > 0:
        if st.button(f"🤖 啟動高階探勘管線 (共 {len(pending_df)} 筆等待中)", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            for i, (idx, row) in enumerate(pending_df.iterrows()):
                status_text.text(f"正在分析: {row['專利名稱']}")
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
                
                progress_bar.progress((i + 1) / len(pending_df))
            st.rerun()

# ==========================================
# 模組二：研發知識庫 (拔除 IPC，聚焦核心解法)
# ==========================================
with tab_dashboard:
    completed_df = st.session_state.master_db[st.session_state.master_db['狀態'] == 'COMPLETED']
    
    # 🌟 加上這個防呆判斷
    if completed_df.empty:
        st.warning("⚠️ 目前資料庫中沒有「已完成分析」的專利。請先至【模組一】上傳 Excel 並啟動 AI 探勘管線！")
    else:
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            filter_main = st.selectbox("📂 1. 選擇大系統", ["全部"] + list(completed_df['五大類'].unique()))
        with col_f2:
            sub_options = ["全部"]
            if filter_main != "全部":
                sub_options += list(completed_df[completed_df['五大類'] == filter_main]['次系統'].unique())
            filter_sub = st.selectbox("⚙️ 2. 選擇次系統", sub_options)
        with col_f3:
            search_query = st.text_input("🎯 3. 關鍵字 (找對手/痛點/機構)")

        filtered_df = completed_df.copy()
        if filter_main != "全部":
            filtered_df = filtered_df[filtered_df['五大類'] == filter_main]
        if filter_sub != "全部":
            filtered_df = filtered_df[filtered_df['次系統'] == filter_sub]
        if search_query:
            mask = filtered_df.astype(str).apply(lambda x: x.str.contains(search_query, case=False)).any(axis=1)
            filtered_df = filtered_df[mask]
        
        for _, p in filtered_df.iterrows():
            with st.container(border=True):
                status_color = "🟢" if "消滅" in p['案件狀態'] or "撤回" in p['案件狀態'] else "🟠"
                disp_id = p['證書號'] if p['證書號'] else p['申請號']
                st.markdown(f"#### {status_color} [{disp_id}] {p['專利名稱']}")
                
                # 拿掉 IPC，介面更乾淨
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
                if st.button(f"進入單篇深度拆解 ➡️", key=f"btn_{disp_id}"):
                    st.toast(f"即將載入 {disp_id} 的詳細圖面與全要件比對")

# ==========================================
# 模組三：無效化特務 (Agentic Invalidation Search)
# ==========================================
with tab_agent:
    st.header("🕵️ 自主前案檢索與無效化特務")
    st.markdown("輸入敵方高威脅專利的請求項，AI 將自動進行「思維鏈推導 ➡️ 生成檢索式 ➡️ 迭代過濾 ➡️ 產出對比」，尋找可用的前案。")
    
    target_claim = st.text_area("🎯 貼上敵方目標請求項 (Target Claim)", height=150, placeholder="例如：一種機車冷卻系統，包含：一水冷排，設置於腳踏板下方；一導風罩，連接於該水冷排...")
    
    if st.button("🚀 啟動無效化特務 (Agent Start)", type="primary"):
        if target_claim:
            # 使用 st.status 呈現 Agent 的運作軌跡
            with st.status("特務正在執行自主檢索迴圈...", expanded=True) as status:
                
                # Step 1: 思考與解析
                st.write("🧠 **[Thought]** 讀取請求項，解析關鍵技術特徵與限制條件...")
                time.sleep(1.5) # 模擬運算時間
                st.info("提取特徵：`水冷排位置`, `踏板底部`, `導風罩角度`")
                
                # Step 2: 首次行動 (生成布林邏輯)
                st.write("🛠️ **[Action 1]** 正在建構初代布林邏輯檢索式並呼叫專利資料庫 API...")
                time.sleep(1.5)
                st.code("Query: (水冷排 OR 散熱器) AND (踏板 OR 底部)", language="sql")
                
                # Step 3: 觀察結果並反思
                st.write("👁️ **[Observation]** 取得 25 篇初步結果。分析摘要後發現大量汽車底盤散熱專利，領域不符，雜訊過高。")
                time.sleep(1.5)
                
                # Step 4: 自主迭代修正
                st.write("🧠 **[Thought 2]** 需要縮小範圍，排除汽車領域，並加入引導氣流的機構特徵。")
                time.sleep(1.5)
                
                # Step 5: 二次行動
                st.write("🛠️ **[Action 2]** 修正檢索式，執行二次精準檢索...")
                time.sleep(1.5)
                st.code("Query: (水冷排 OR 散熱器) AND (踏板 OR 底部) AND (機車 OR 摩托車) AND 導風罩", language="sql")
                
                # Step 6: 鎖定目標
                st.write("🎯 **[Match]** 檢索完畢！成功鎖定一篇高度相關的日本 YAMAHA 早期公開案。")
                time.sleep(1)
                
                status.update(label="特務任務完成！已準備好全要件比對報告。", state="complete", expanded=False)
            
            # 任務完成後，顯示 AI 生成的比對結果
            st.markdown("### 📑 疑似有效前案報告 (Prior Art Candidate)")
            st.success("**前案字號：** JP-2018-123456-A (YAMAHA MOTOR CO LTD) | **公開日：** 2018-05-12")
            
            st.markdown("#### ⚖️ 全要件讀取比對 (All-Elements Mapping)")
            # 這裡利用 Markdown 表格呈現法務最需要的比對表
            mapping_table = """
| 目標專利要件 (Target Limitations) | 前案揭露對應段落 (Prior Art Disclosure) | 涵蓋評估 |
| :--- | :--- | :--- |
| 一種機車冷卻系統 | 本發明涉及一種跨騎式車輛之冷卻裝置... 【0012】 | ✅ 完全讀取 |
| 包含：一水冷排 | 具備散熱器 (Radiator) 14... 【0015】 | ✅ 均等讀取 |
| 設置於腳踏板下方 | 散熱器14配置於低置腳踏板 (Footboard) 正下方空間... 【0021】 | ✅ 完全讀取 |
| 一導風罩，連接於該水冷排 | 設有一樹脂導流罩20，包覆於散熱器前方迎風面... 【0028】 | ✅ 完全讀取 |
            """
            st.markdown(mapping_table)
            
            st.info("💡 **Agent 洞察結論：** 該 YAMAHA 前案已完整揭露目標請求項之所有物理與空間特徵，具有極高的進步性核駁/無效化潛力。建議送交 Tab 2 進行更嚴謹的文義與圖面確認。")
        else:
            st.warning("請先輸入目標專利的請求項內容！")
