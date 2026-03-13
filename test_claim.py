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
st.markdown("實務級三視窗連動：無死角對齊「專利圖面、請求項、說明書全文本對應 (含段落編號)」。")
st.markdown("---")

uploaded_pdf = st.file_uploader("📥 請上傳一份專利 PDF 檔", type=["pdf"])

if st.button("🤖 啟動精細拆解 (建立連動字典)", use_container_width=True):
    if uploaded_pdf is None:
        st.warning("⚠️ 請先上傳 PDF 檔案！")
    else:
        with st.spinner("大腦正在地毯式搜索說明書，並精準抓取段落編號... (需時較長，請稍候)"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_pdf.getvalue())
                    tmp_file_path = tmp_file.name

                gemini_file = genai.upload_file(tmp_file_path)

                # 🌟 升級版 Prompt：強制保留【xxxx】段落編號
                prompt = '''
                你現在是一位極度嚴謹的專利訴訟律師。請閱讀這份機車專利，建立核心元件的「文義解釋對照表」。
                請找出獨立項中最核心的 5 到 8 個實體元件。

                【任務要求】：
                對於每一個元件，你必須在說明書中進行「地毯式搜索」。
                把說明書中「所有」提到該元件的段落（包含它的位置、連接關係、材質、作動方式、目的）全部摘錄出來。
                【🔴 極度重要】：摘錄時，必須完整保留說明書原文前方的「段落編號」（例如：【0037】或 [0037] 等格式）。
                絕對不要只給一段，也不要自己總結，請給我原汁原味的說明書原文與段落編號。

                【🔴 絕對指令：輸出純 JSON 格式】
                嚴格符合以下結構：
                {
                  "claim_1": [
                    "請將請求項1的內容，以陣列形式，一句一行乾淨地列出",
                    "一水泵本體(10)；"
                  ],
                  "components": [
                    {
                      "id": "40",
                      "name": "後搖臂",
                      "spec_texts": [
                        "【0037】後搖臂40設置在車輪組20的後車輪22與動力單元30的引擎31之間...",
                        "【0042】左搖臂41的兩端分別設為一左前連接部411與一左後連接部412..."
                      ]
                    }
                  ]
                }
                '''
                
                response = model.generate_content([gemini_file, prompt])
                
                clean_text = response.text.replace('```json', '').replace('```', '').strip()
                clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                st.session_state.claim_data = json.loads(clean_text)
                
                st.success("✅ 建構完成！請在下方操作三視窗連動。")

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
        comp_options = {f"[{c['id']}] {c['name']}": c for c in components}
        selected_comp_label = st.selectbox("🎯 選擇要追蹤的比對目標【核心元件】：", list(comp_options.keys()))
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
                
                spec_texts = active_comp.get('spec_texts', [])
                if not spec_texts:
                    st.warning("說明書中未找到針對此元件的進一步描述。")
                else:
                    for text in spec_texts:
                        # 🌟 將說明書段落中的元件名稱高亮，並直接顯示 AI 抓出的完整段落 (含段落編號)
                        highlighted_text = text.replace(active_comp['name'], f"<mark style='background-color: #cce5ff; color: #004085; font-weight: bold; padding: 2px 4px; border-radius: 3px;'>{active_comp['name']}</mark>")
                        
                        # 讓含有 【xxxx】 的段落開頭更明顯
                        st.markdown(f"<div style='background-color: #f8f9fa; padding: 12px; border-left: 5px solid #007bff; margin-bottom: 15px; line-height: 1.6;'>{highlighted_text}</div>", unsafe_allow_html=True)
