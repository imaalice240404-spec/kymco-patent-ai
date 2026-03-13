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

st.title("⚖️ 請求項文義解析 (Claim Construction) 工作站")
st.markdown("實務級三視窗連動：無死角對齊「圖面、請求項、說明書」，**完整收錄全專利所有元件**。")
st.markdown("---")

uploaded_pdf = st.file_uploader("📥 請上傳一份專利 PDF 檔", type=["pdf"])

if st.button("🤖 啟動精細拆解 (建立全文本與全元件字典)", use_container_width=True):
    if uploaded_pdf is None:
        st.warning("⚠️ 請先上傳 PDF 檔案！")
    else:
        with st.spinner("大腦正在建立全本專利的「符號字典」與「說明書全文本」... (約需 20 秒)"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_pdf.getvalue())
                    tmp_file_path = tmp_file.name

                gemini_file = genai.upload_file(tmp_file_path)

                # 🌟 終極 Prompt：不准 AI 亂猜，強制建立 100% 完整的資料庫
                prompt = '''
                你現在是一個精準的專利資料庫解析系統。請閱讀這份專利，並將內容轉化為結構化的 JSON 格式。

                【任務 1：完整元件符號字典 (絕對不能漏)】
                請去尋找專利說明書最後面的「符號簡單說明」、「主要元件符號說明」或文中的對應段落。
                將裡面提及的【每一個】元件符號跟名稱提取出來。即使是小螺絲、墊片也必須列出。

                【任務 2：請求項 1 拆解】
                將請求項 1 逐句拆解為陣列。

                【任務 3：實施方式全文本提取】
                請將專利中「發明說明 / 實施方式 / 具體實施例」的所有段落完整提取出來。
                必須保留原本的【00xx】段落編號。如果該專利較舊沒有段落編號，請以自然段落區分。

                【🔴 絕對指令：輸出純 JSON 格式】
                嚴格符合以下結構：
                {
                  "claim_1": [
                    "一種機車，包含：",
                    "一車架10；"
                  ],
                  "components": [
                    {"id": "10", "name": "車架"},
                    {"id": "11", "name": "頭管"},
                    {"id": "40", "name": "後搖臂"}
                  ],
                  "spec_texts": [
                    "【0015】如圖1所示，車架10包含一頭管11...",
                    "【0016】該後搖臂40設置於..."
                  ]
                }
                '''
                
                response = model.generate_content([gemini_file, prompt])
                
                clean_text = response.text.replace('```json', '').replace('```', '').strip()
                clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                st.session_state.claim_data = json.loads(clean_text)
                
                st.success("✅ 全本字典建構完成！請使用下方下拉選單進行無死角查閱。")

                os.remove(tmp_file_path)
                genai.delete_file(gemini_file.name)
            except Exception as e:
                st.error(f"分析失敗，可能是 PDF 過大或格式問題：{e}")

# ==========================================
# 實務級三聯屏 (Triple-Pane Workspace)
# ==========================================
if st.session_state.claim_data:
    st.markdown("---")
    
    components = st.session_state.claim_data.get("components", [])
    if components:
        # 🌟 建立超完整的元件選擇器
        comp_options = {f"[{c['id']}] {c['name']}": c for c in components}
        
        col_select, col_empty = st.columns([1, 1])
        with col_select:
            selected_comp_label = st.selectbox(f"🎯 選擇要追蹤的比對目標 (已成功載入 {len(components)} 個元件)：", list(comp_options.keys()))
            active_comp = comp_options[selected_comp_label]
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        col_img, col_claim, col_spec = st.columns([1.2, 1, 1.2])
        
        with col_img:
            st.markdown("### 🖼️ 專利圖面檢視")
            if uploaded_pdf:
                pdf_doc = pdfium.PdfDocument(uploaded_pdf.getvalue())
                total_pages = len(pdf_doc)
                page_num = st.number_input(f"跳至頁碼 (共 {total_pages} 頁)", min_value=1, max_value=total_pages, value=min(2, total_pages))
                with st.container(height=650, border=True):
                    page = pdf_doc[page_num - 1]
                    img = page.render(scale=2.0).to_pil() 
                    st.image(img, use_container_width=True)
                pdf_doc.close()
        
        with col_claim:
            st.markdown("### 🧩 獨立項文義")
            with st.container(height=750, border=True):
                claims = st.session_state.claim_data.get("claim_1", [])
                for line in claims:
                    if active_comp['name'] in line:
                        highlighted_line = line.replace(active_comp['name'], f"<span style='background-color: #fff3cd; font-weight: bold; color: #856404; padding: 2px 4px; border-radius: 3px;'>{active_comp['name']}</span>")
                        st.markdown(f"<div style='padding: 8px; border-bottom: 1px dashed #eee;'>{highlighted_line}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='padding: 8px; border-bottom: 1px dashed #eee; color: #555;'>{line}</div>", unsafe_allow_html=True)

        with col_spec:
            st.markdown("### 📖 說明書具體限制原文")
            with st.container(height=750, border=True):
                st.info(f"📍 目標元件：**{active_comp['name']} ({active_comp['id']})**")
                
                # 🌟 Python 超高速瞬間篩選邏輯：只挑出含有該元件的段落
                spec_texts = st.session_state.claim_data.get('spec_texts', [])
                found_texts = [text for text in spec_texts if active_comp['name'] in text or active_comp['id'] in text]
                
                if not found_texts:
                    st.warning(f"在實施方式中，未找到針對「{active_comp['name']}」的進一步描述文字。")
                else:
                    for text in found_texts:
                        # 雙重高亮：把元件名稱跟編號都標記出來
                        highlighted_text = text.replace(active_comp['name'], f"<mark style='background-color: #cce5ff; color: #004085; font-weight: bold; padding: 2px 4px; border-radius: 3px;'>{active_comp['name']}</mark>")
                        st.markdown(f"<div style='background-color: #f8f9fa; padding: 12px; border-left: 5px solid #007bff; margin-bottom: 15px; line-height: 1.6;'>{highlighted_text}</div>", unsafe_allow_html=True)
