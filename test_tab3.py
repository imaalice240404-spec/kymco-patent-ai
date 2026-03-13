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

st.title("🧪 Tab 3 研發專屬彈藥庫 (獨立測試版)")
st.markdown("這裡絕對安全，不會影響到您原本的 `app.py`！")
st.markdown("---")

uploaded_excel = st.file_uploader("📥 請上傳 TWPAT 匯出的 Excel (需含『摘要』與『申請專利範圍』)", type=["xlsx", "xls", "csv"], key="rd_excel")

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
        status_col = next((col for col in df.columns if '狀態' in col or '法態' in col or '專利權' in col), None)

        st.markdown("---")
        st.markdown("#### 第一階段：AI 彈藥庫自動標籤化")
        
        if abstract_col and title_col and patent_num_col:
            col_slider, col_btn = st.columns([2, 1])
            with col_slider:
                analyze_count = st.slider("選擇要批次建檔的專利數量 (建議先選 3-5 篇測試)", min_value=1, max_value=min(len(df), 20), value=min(len(df), 3))
            
            with col_btn:
                st.write("") 
                if st.button("🤖 啟動 AI 萃取與標籤化", use_container_width=True):
                    with st.spinner("大腦正在閱讀專利，並強制貼上產品與技術標籤..."):
                        try:
                            sample_df = df.head(analyze_count)
                            prompt_data = ""
                            for idx, row in sample_df.iterrows():
                                p_num = str(row[patent_num_col])
                                title = str(row[title_col])
                                status = str(row[status_col]) if status_col else "未知"
                                abs_text = str(row[abstract_col]).replace('\n', '')[:250] 
                                claim_text = str(row[claim_col]).replace('\n', '')[:300] if claim_col else "無"
                                
                                prompt_data += f"[{p_num}] 名稱：{title} | 法態：{status} | 摘要：{abs_text} | 請求項：{claim_text}\n"

                            prompt = f"""
                            你是一位專利技術轉譯專家，負責將專利資料庫轉化為研發工程師(RD)可以快速檢索的「解題靈感庫」。
                            請閱讀以下專利，並為每一篇提取出三個關鍵維度的標籤，以及一段 RD 友善的核心解法。

                            【🔴 強制收斂字典】為了方便下拉選單檢索，請盡量使用以下標準詞彙（若無相符可自創，但以簡潔為原則）：
                            * **對應產品**：電動機車、燃油速克達、重型機車、電池模組、馬達控制器、車架懸吊、引擎本體。
                            * **技術手段**：水冷散熱、氣冷結構、連桿機構、齒輪傳動、感測器配置、鎖固件改良、流體通道、避震結構。

                            請嚴格輸出 JSON 格式 (不要有 markdown 標記)，格式如下：
                            {{
                              "database": [
                                {{
                                  "專利號": "XXX",
                                  "專利名稱": "XXX",
                                  "法態": "XXX",
                                  "對應產品": "電動機車", 
                                  "技術手段": "水冷散熱",
                                  "解決痛點": "高速運轉時馬達過熱導致效率下降",
                                  "核心解法": "透過在馬達外殼設置螺旋狀冷卻水道，增加散熱面積..."
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
                            st.session_state.rd_database = result_json.get("database", [])
                            st.success("✅ 建檔完成！請使用下方濾網尋找研發靈感。")
                            
                        except Exception as e:
                            st.error(f"分析失敗，錯誤：{e}")

        # ==========================================
        # RD 專屬檢索介面
        # ==========================================
        if st.session_state.rd_database:
            st.markdown("---")
            st.markdown("#### 🔍 第二階段：RD 專屬檢索面板")
            
            all_products = list(set([item.get("對應產品", "未知") for item in st.session_state.rd_database]))
            all_techs = list(set([item.get("技術手段", "未知") for item in st.session_state.rd_database]))

            col_f1, col_f2 = st.columns(2)
            with col_f1:
                filter_product = st.multiselect("🏷️ 篩選『對應產品』", all_products, placeholder="選擇產品...")
            with col_f2:
                filter_tech = st.multiselect("⚙️ 篩選『技術手段』", all_techs, placeholder="選擇技術...")

            st.markdown("##### 📚 檢索結果 (解題靈感卡)")
            
            filtered_db = st.session_state.rd_database
            if filter_product:
                filtered_db = [item for item in filtered_db if item.get("對應產品") in filter_product]
            if filter_tech:
                filtered_db = [item for item in filtered_db if item.get("技術手段") in filter_tech]

            if not filtered_db:
                st.warning("沒有符合條件的專利，請放寬篩選條件。")
            else:
                for p in filtered_db:
                    with st.container(border=True):
                        status_text = p.get('法態', '')
                        is_open_source = any(keyword in status_text for keyword in ["消滅", "撤回", "放棄", "屆滿"])
                        badge = "🟢 **【可合法參考：已失效/開源】**" if is_open_source else "🔴 **【注意侵權：專利有效】**"
                        
                        st.markdown(f"**[{p.get('專利號')}] {p.get('專利名稱')}**")
                        st.markdown(f"{badge} | 法態紀錄：{status_text}")
                        
                        col_tag1, col_tag2, col_tag3 = st.columns(3)
                        col_tag1.info(f"🏍️ **產品**：{p.get('對應產品')}")
                        col_tag2.warning(f"🔧 **技術**：{p.get('技術手段')}")
                        col_tag3.error(f"🔥 **痛點**：{p.get('解決痛點')}")
                        
                        st.markdown(f"**💡 核心解法 (RD 參考設計)：**\n> {p.get('核心解法')}")

    except Exception as e:
        st.error(f"檔案讀取失敗，錯誤訊息：{e}")
