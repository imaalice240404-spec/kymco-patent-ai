import os
import json
import random 
import streamlit as st
import google.generativeai as genai
import tempfile
import pypdfium2 as pdfium

# 👇 建立 API 鑰匙池
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

st.set_page_config(page_title="Claim Construction 沙盒", layout="wide")

# 初始化 Session State
if 'claim_data' not in st.session_state:
    st.session_state.claim_data = None

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

st.title("⚖️ 請求項精細建構 (Claim Construction) 工作站")
st.markdown("實務級三視窗連動：點擊核心元件，瞬間對齊「圖面、請求項、說明書具體限制」。")
st.markdown("---")

uploaded_pdf = st.file_uploader("📥 請上傳一份專利 PDF 檔", type=["pdf"])

if st.button("🤖 啟動精細拆解 (生成 JSON 連動字典)", use_container_width=True):
    if uploaded_pdf is None:
        st.warning("⚠️ 請先上傳 PDF 檔案！")
    else:
        with st.spinner("大腦正在掃描說明書，尋找每一個元件的具體限制條件... (約需 20 秒)"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_pdf.getvalue())
                    tmp_file_path = tmp_file.name

                gemini_file = genai.upload_file(tmp_file_path)

                # 🌟 極度嚴格的 JSON 提取 Prompt
                prompt = '''
                你現在是一位資深專利訴訟律師。請閱讀這份機車專利，並提取核心元件的「說明書解釋」。
                請找出獨立項中最重要的 4 到 6 個核心實體元件，並去說明書中找出「具體解釋該元件形狀、位置、材質或作動方式」的段落。

                【🔴 絕對指令：輸出純 JSON 格式，不要 Markdown 標記】
                必須嚴格符合以下結構：
                {
                  "claim_1": [
                    "請將請求項1的內容，以陣列形式，一句一行乾淨地列出",
                    "例如：一種機車水泵結構，包含：",
                    "一水泵本體(10)；",
                    "一葉輪(20)..."
                  ],
                  "components": [
                    {
                      "id": "10",
                      "name": "水泵本體",
                      "spec_text": "請從說明書中摘錄出具體限制這個元件的段落。例如：『該水泵本體10較佳為採用鋁合金壓鑄成型，其內部具有一容置空間...』",
                      "strategic_note": "律師備註：這段說明書對該元件加了什麼隱藏限制？(10字以內)"
                    }
                  ]
                }
                '''
                
                response = model.generate_content([gemini_file, prompt])
                
                # 清洗並解析 JSON
                clean_text = response.text.replace('```json', '').replace('```', '').strip()
                clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                st.session_state.claim_data = json.loads(clean_text)
                
                st.success("✅ 建構完成！請在下方操作三視窗連動。")

                os.remove(tmp_file_path)
                genai.delete_file(gemini_file.name)
            except Exception as e:
                st.error(f"分析失敗：{e}")

# ==========================================
# 實務級三聯屏 (Triple-Pane Workspace)
# ==========================================
if st.session_state.claim_data:
    st.markdown("---")
    
    # 🌟 建立互動選擇器
    components = st.session_state.claim_data.get("components", [])
    if components:
        # 讓使用者選擇要檢視的元件
        comp_options = {f"[{c['id']}] {c['name']}": c for c in components}
        selected_comp_label = st.selectbox("🎯 選擇要比對的【核心元件】：", list(comp_options.keys()))
        active_comp = comp_options[selected_comp_label]
        
        st.markdown("<br>", unsafe_allow_html=True) # 排版空行
        
        # 🌟 三欄位切割：左(圖面) / 中(請求項) / 右(說明書)
        col_img, col_claim, col_spec = st.columns([1.2, 1, 1.2])
        
        # 👈 左區：圖面檢視
        with col_img:
            st.markdown("### 🖼️ 專利圖面檢視")
            with st.container(height=600):
                if uploaded_pdf:
                    pdf_doc = pdfium.PdfDocument(uploaded_pdf.getvalue())
                    # 預設顯示前 5 頁，實務上圖面通常在前面
                    pages_to_render = min(5, len(pdf_doc)) 
                    for i in range(pages_to_render):
                        page = pdf_doc[i]
                        img = page.render(scale=1.0).to_pil()
                        st.image(img, caption=f"第 {i+1} 頁", use_container_width=True)
                    pdf_doc.close()
        
        # 🎯 中區：請求項拆解與高亮
        with col_claim:
            st.markdown("### 🧩 獨立項文義")
            with st.container(height=600, border=True):
                claims = st.session_state.claim_data.get("claim_1", [])
                for line in claims:
                    # 如果該行包含選中的元件名稱，就用黃色高亮標示
                    if active_comp['name'] in line or active_comp['id'] in line:
                        st.markdown(f"<div style='background-color: #fff3cd; padding: 5px; border-radius: 5px; font-weight: bold;'>{line}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='padding: 5px;'>{line}</div>", unsafe_allow_html=True)

        # 📖 右區：說明書限制解釋
        with col_spec:
            st.markdown("### 📖 說明書具體限制")
            with st.container(height=600, border=True):
                st.info(f"**目標元件：** {active_comp['name']} ({active_comp['id']})")
                
                st.markdown("##### 📌 說明書原文對應：")
                # 將說明書文字中的元件名稱高亮
                spec_text = active_comp['spec_text'].replace(active_comp['name'], f"<mark style='background-color: #cce5ff;'>{active_comp['name']}</mark>")
                st.markdown(f"> {spec_text}", unsafe_allow_html=True)
                
                st.markdown("---")
                st.markdown("##### 💡 研發討論/迴避重點：")
                st.error(f"{active_comp['strategic_note']}")
