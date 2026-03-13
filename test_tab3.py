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

# 🌟 初始化：RD 資料庫 (用來不斷累積資料)
if 'rd_database' not in st.session_state:
    st.session_state.rd_database = []

st.set_page_config(page_title="Tab 3 沙盒測試區", layout="wide")

# --- 簡易密碼門禁 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔒 測試區 - 系統登入")
        pwd = st.text_input("請輸入授權密碼", type="password")
        if pwd == st.secrets.get("APP_PASSWORD", ""): 
            st.session_state["password_correct"] = True
            st.rerun()
        elif pwd:
            st.error("密碼錯誤，請重新輸入！")
        return False
    return True

if not check_password():
    st.stop()
# --- 門禁結束 ---

st.title("🧪 Tab 3 研發專屬彈藥庫 (無限累積與強制收斂版)")
st.markdown("將已失效的專利轉化為 RD 靈感庫，透過大系統分類聚攏資料，並支援分批寫入資料庫。")
st.markdown("---")

uploaded_excel = st.file_uploader("📥 請上傳 TWPAT 匯出的 Excel (已篩選為失效專利)", type=["xlsx", "xls", "csv"], key="rd_excel")

if uploaded_excel:
    try:
        if uploaded_excel.name.endswith('.csv'):
            df = pd.read_csv(uploaded_excel)
        else:
            df = pd.read_excel(uploaded_excel)
            
        st.success(f"✅ 成功載入資料！共計 {len(df)} 筆專利。")
        
        # 尋找關鍵欄位
        title_col = next((col for col in df.columns if '專利名稱' in col or '標題' in col), None)
        abstract_col = next((col for col in df.columns if '摘要' in col), None)
        patent_num_col = next((col for col in df.columns if '號' in col and ('公開' in col or '公告' in col or '申請' in col)), None)
        claim_col = next((col for col in df.columns if '申請專利範圍' in col or '請求項' in col), None)

        st.markdown("---")
        
        # 顯示目前資料庫狀態
        col_db_stat, col_db_clear = st.columns([4, 1])
        with col_db_stat:
            st.info(f"🗄️ 目前系統彈藥庫已累積： **{len(st.session_state.rd_database)}** 筆開源技術。")
        with col_db_clear:
            if st.button("🗑️ 清空資料庫", use_container_width=True):
                st.session_state.rd_database = []
                st.rerun()

        st.markdown("#### 第一階段：分批萃取與標籤化 (Batch Processing)")
        st.write("為了維持 AI 準確度與避免超載，請每次選擇大約 15~20 筆的範圍進行建檔。建檔完畢後，資料會自動加入上方的彈藥庫中。")
        
        if abstract_col and title_col and patent_num_col:
            col_slider, col_btn = st.columns([2, 1])
            with col_slider:
                # 🌟 雙向拉桿，讓您可以選擇 1~20, 然後 21~40
                batch_range = st.slider("選擇本次要交給 AI 處理的資料區間 (列號)", 
                                        min_value=1, max_value=len(df), 
                                        value=(1, min(15, len(df))))
            
            with col_btn:
                st.write("") 
                if st.button("🤖 開始批次寫入彈藥庫", use_container_width=True):
                    with st.spinner(f"大腦正在解讀第 {batch_range[0]} 到 {batch_range[1]} 筆專利..."):
                        try:
                            # 依照拉桿範圍擷取資料
                            start_idx = batch_range[0] - 1
                            end_idx = batch_range[1]
                            sample_df = df.iloc[start_idx:end_idx]
                            
                            prompt_data = ""
                            for idx, row in sample_df.iterrows():
                                p_num = str(row[patent_num_col])
                                title = str(row[title_col])
                                abs_text = str(row[abstract_col]).replace('\n', '')[:250] 
                                claim_text = str(row[claim_col]).replace('\n', '')[:300] if claim_col else "無"
                                
                                prompt_data += f"[{p_num}] 名稱：{title} | 摘要：{abs_text} | 請求項：{claim_text}\n"

                            # 🌟 強制收斂的大分類字典
                            prompt = f"""
                            你是一位機車廠的資深研發顧問。請閱讀以下專利，為每一篇提取三個維度的資訊，以建立研發知識庫。

                            【🔴 絕對指令 1：系統大分類】(只能從這 6 個選項中挑選 1 個)
                            請根據「專利名稱」與「請求項」，判斷該專利屬於哪一個系統：
                            ["引擎與動力系統", "傳動系統", "煞車系統", "車架與懸吊系統", "電系與儀表控制", "外觀件與其他"]

                            【🔴 絕對指令 2：特殊機構與達成功效】
                            * **特殊機構**：從摘要與請求項中提取這項專利的核心物理設計或結構（例如：連動鋼索、螺旋水套、雙活塞卡鉗）。字數限 15 字內。
                            * **達成功效**：這個特殊機構具體解決了什麼痛點？或達成了什麼效果？（例如：避免煞車力分配不均、提升引擎散熱）。字數限 20 字內。

                            請嚴格輸出 JSON 格式 (不要有 markdown 標記)，格式如下：
                            {{
                              "database": [
                                {{
                                  "專利號": "XXX",
                                  "專利名稱": "XXX",
                                  "大分類": "這裡只能填上方規定的6個選項之一", 
                                  "特殊機構": "XXX",
                                  "達成功效": "XXX",
                                  "核心解法": "用白話文簡述這項設計的運作原理，給RD當作參考。"
                                }}
                              ]
                            }}

                            以下是專利資料：
                            {prompt_data}
                            """
                            
                            response = model.generate_content(prompt)
                            clean_text = response.text.replace('```json', '').replace('```', '').strip()
                            clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                            
                            result_json = json.loads(clean_text)
                            new_data = result_json.get("database", [])
                            
                            # 🌟 將新分析出來的資料「疊加」進去資料庫，並排除重複的專利號
                            existing_pnums = [p['專利號'] for p in st.session_state.rd_database]
                            for item in new_data:
                                if item['專利號'] not in existing_pnums:
                                    st.session_state.rd_database.append(item)
                                    
                            st.success(f"✅ 成功將 {len(new_data)} 筆資料匯入彈藥庫！")
                            
                        except Exception as e:
                            st.error(f"分析失敗，錯誤：{e}")

        # ==========================================
        # RD 專屬檢索介面
        # ==========================================
        if st.session_state.rd_database:
            st.markdown("---")
            st.markdown("#### 🔍 第二階段：RD 專屬檢索面板")
            
            # 使用固定的大分類選項
            all_categories = ["引擎與動力系統", "傳動系統", "煞車系統", "車架與懸吊系統", "電系與儀表控制", "外觀件與其他"]

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                filter_cat = st.multiselect("🏷️ 選擇『研發系統大分類』", all_categories, placeholder="例如：尋找『煞車系統』相關機構")
            with col_f2:
                # 讓使用者可以輸入關鍵字去搜尋「達成功效」
                search_query = st.text_input("🎯 關鍵字搜尋 (找痛點或機構)", placeholder="例如：散熱、連動、減震...")

            st.markdown("##### 📚 檢索結果 (解題靈感卡)")
            
            filtered_db = st.session_state.rd_database
            if filter_cat:
                filtered_db = [item for item in filtered_db if item.get("大分類") in filter_cat]
            if search_query:
                filtered_db = [item for item in filtered_db if search_query in item.get("特殊機構", "") or search_query in item.get("達成功效", "") or search_query in item.get("核心解法", "")]

            if not filtered_db:
                st.warning("沒有符合條件的專利，請放寬篩選條件。")
            else:
                for p in filtered_db:
                    with st.container(border=True):
                        # 🌟 強制標示為開源綠燈
                        badge = "🟢 **【開源技術庫：免授權直接參考】**"
                        
                        st.markdown(f"**[{p.get('專利號')}] {p.get('專利名稱')}**")
                        st.markdown(f"{badge}")
                        
                        col_tag1, col_tag2, col_tag3 = st.columns(3)
                        col_tag1.info(f"📂 **系統分類**：{p.get('大分類')}")
                        col_tag2.warning(f"⚙️ **特殊機構**：{p.get('特殊機構')}")
                        col_tag3.error(f"🎯 **達成功效**：{p.get('達成功效')}")
                        
                        st.markdown(f"**💡 核心解法 (RD 參考設計)：**\n> {p.get('核心解法')}")

    except Exception as e:
        st.error(f"檔案讀取失敗，錯誤訊息：{e}")
