import os
import json
import random # 🌟 需要這個來隨機抽鑰匙
import streamlit as st
import google.generativeai as genai
import tempfile
import io
import pypdfium2 as pdfium
from docx import Document

# 👇 建立 API 鑰匙池
api_keys = [
    st.secrets["GOOGLE_API_KEY_1"],
    st.secrets["GOOGLE_API_KEY_2"]
    # 如果未來有第三把，可以直接加 GOOGLE_API_KEY_3...
]

# 🌟 隨機抽一把鑰匙來開門 (分散扣打)
selected_key = random.choice(api_keys)
genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

if 'report_content' not in st.session_state:
    st.session_state.report_content = ""

st.set_page_config(page_title="機車專利 PDF 戰情室", layout="wide")

# 🌟 建立存放歷史報告的總資料夾
SAVE_DIR = "saved_reports"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# --- 簡易密碼門禁 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔒 專利戰情室 - 系統登入")
        pwd = st.text_input("請輸入授權密碼", type="password")
        if pwd == st.secrets["APP_PASSWORD"]: 
            st.session_state["password_correct"] = True
            st.rerun()
        elif pwd:
            st.error("密碼錯誤，請重新輸入！")
        return False
    return True

if not check_password():
    st.stop()
# --- 門禁結束 ---

st.title("🏍️ 機車專利分析系統 ")
st.markdown("支援 Google Patents 快速連線、十秒專利卡 (Patent Card) 生成，並可一鍵匯出 Word 戰略報告。")
st.markdown("---")

col_input1, col_input2 = st.columns([1, 2])
with col_input1:
    st.subheader("1️⃣ 案件資訊與法態")
    applicant = st.text_input("申請人 (對手公司)", placeholder="例如：光陽工業")
    patent_num = st.text_input("專利號 (輸入以啟用傳送門)", placeholder="例如：I856744")
    if patent_num:
        clean_num = ''.join(e for e in patent_num if e.isalnum())
        google_patents_url = f"https://patents.google.com/patent/TW{clean_num}B"
        st.markdown(f"👉 [點我秒開 Google Patents 查看 **{patent_num}**]({google_patents_url})")
    status = st.selectbox("目前案件狀態", ["請選擇...", "公開", "公告/核准", "核駁", "撤回", "消滅"])

with col_input2:
    st.subheader("2️⃣ 上傳專利 PDF")
    uploaded_file = st.file_uploader("請拖曳或選擇專利 PDF 檔", type=["pdf"])

st.markdown("---")

def create_word_doc(text):
    doc = Document()
    doc.add_heading('專利戰略深度分析報告', 0)
    for para in text.split('\n'):
        if para.strip():
            doc.add_paragraph(para.strip())
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

if st.button("🚀 啟動 PDF 視覺化深度解剖", use_container_width=True):
    if status == "請選擇...":
        st.warning("⚠️ 請選擇目前的案件狀態！")
    elif uploaded_file is None:
        st.warning("⚠️ 請上傳一份專利 PDF 檔案！")
    elif not patent_num:
        st.warning("⚠️ 請輸入「專利號」，系統才能為您建立專屬記憶檔案！")
    else:
        # 🌟 1. 整理申請人名稱，作為分類資料夾名稱
        safe_applicant = "".join(c for c in applicant if c.isalnum() or c in (' ', '-', '_')).strip()
        folder_name = safe_applicant if safe_applicant else "未分類"
        
        # 🌟 2. 建立對手專屬的資料夾 (例如: saved_reports/光陽工業)
        applicant_dir = os.path.join(SAVE_DIR, folder_name)
        if not os.path.exists(applicant_dir):
            os.makedirs(applicant_dir)

        # 🌟 3. 整理專利號，作為存檔的檔名
        clean_num = ''.join(e for e in patent_num if e.isalnum())
        file_path = os.path.join(applicant_dir, f"{clean_num}.json")

        # 🌟 攔截點：檢查是否已經分析過？
        if os.path.exists(file_path):
            with st.spinner(f"正在從【{folder_name}】的記憶庫中讀取歷史大腦記憶..."):
                with open(file_path, "r", encoding="utf-8") as f:
                    saved_data = json.load(f)
                    st.session_state.report_content = saved_data.get("content", "")
                st.success(f"⚡ 找到 {patent_num} 的歷史紀錄！已為您從【{folder_name}】分類中秒速載入，完全不消耗 API 額度。")
        else:
            with st.spinner("大腦正在深挖先前技術與獨立項地雷，請稍候約 20 秒..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_file_path = tmp_file.name

                    gemini_file = genai.upload_file(tmp_file_path)

                    prompt = f'''
                    【⚠️ 語氣與術語強制校準】：你現在是一位資深機車專利代理人與研發主管。請使用機車研發黑話。
                    我已經提供了一份機車相關的專利 PDF 檔案，請仔細閱讀全文。
                    【補充資訊】申請人：{applicant} / 目前法律狀態：{status}

                    【📝 輸出格式要求】請嚴格依序輸出以下兩個大區塊：
                    ====================
                    區塊一：【🚀 RD 專屬十秒專利卡 (Patent Card)】
                    * **📝 Title (技術命名)**：(用一句話總結這項技術)
                    * **🔥 Problem (解決痛點)**：(原本的設計有什麼缺點)
                    * **💡 Solution (核心解法)**：(本專利用了什麼特殊結構解決)
                    * **🏷️ Key Elements (關鍵字標籤)**：(請提取 3~5 個核心元件的中文關鍵字)
                    * **🎯 Application (應用場景)**：(例如：速克達、重機)
                    * **⚔️ 侵權風險視覺化 (自家技術對比清單)**：請列成 3 項 Checklist (使用 ✔ 符號)。

                    ====================
                    區塊二：【📜 智權與法務深度戰略分析】
                    【一、 🚦 FTO 風險判定】：判定『🟢 綠燈：已失效』或『🔴 紅燈：具威脅』。
                    【二、 📸 技術核心快照】：1.發明目的 2.核心技術 3.宣稱功效。
                    【三、 🏢 研發部門精準派發】：挑選接收部門並附理由。
                    【四、 🛑 先前技術與妥協分析 】：獨立項被迫增加了什麼限制？
                    【五、 🧩 獨立項全要件拆解 (Claim Chart)】：請將獨立項依要件原汁原味分段列出（絕對不需在每行加註解）。列出完畢後，統一在該區塊底部新增一個「🎯 侵權破口總結」，精準點出該獨立項中最容易被對手迴避的 1~2 個多餘限制即可。
                    【六、 🪤 附屬項隱藏地雷探測】：請「逐一檢視」所有附屬項，全面挑出所有具有「具體結構形狀、相對位置、或工程參數限制」的附屬項（寧可多抓，絕對不要遺漏），並條列簡述其限制條件。
                    【七、 👁️ 侵權可偵測性評估】：極易偵測 / 需破壞性拆解。
                    【八、 🕵️‍♂️ 實證功效檢驗 】：是否有實體數據？
                    【九、 🛡️ 高階迴避設計建議 (防範均等論)】：基於物理原理提出迴避方案。
                    【十、 🧬 技術演進與機構整併雷達】：是否將以往獨立的兩個元件整併？
                    【十一、 🏷️ 元件符號圖面提取字典】：請務必以「垂直條列式（Bullet points）」列出所有元件符號，【絕對不要】加上英文翻譯。格式範例：
                    * 1: 引擎
                    * 3: 汽缸頭組
                    '''
                    
                    response = model.generate_content([gemini_file, prompt])
                    st.session_state.report_content = response.text

                    # 🌟 將成功產出的結果存檔進 JSON
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump({"content": st.session_state.report_content}, f, ensure_ascii=False)
                    st.success("✅ 分析完成，並已自動將報告存入系統記憶庫！")

                    os.remove(tmp_file_path)
                    genai.delete_file(gemini_file.name)
                except Exception as e:
                    st.error(f"分析失敗：{e}")

# ==========================================
# 顯示報告與純淨版影像 PDF 區塊
# ==========================================
if st.session_state.report_content:
    col_pdf, col_report = st.columns([1.2, 1])
    
    with col_pdf:
        st.subheader("📄 專利原件 (純淨影像版 - 絕對防封鎖)")
        if uploaded_file:
            with st.container(height=800):
                with st.spinner("正在加載高畫質圖檔..."):
                    pdf_doc = pdfium.PdfDocument(uploaded_file.getvalue())
                    for i in range(len(pdf_doc)):
                        page = pdf_doc[i]
                        img = page.render(scale=1.5).to_pil()
                        st.image(img, caption=f"第 {i+1} 頁", use_container_width=True)
                    pdf_doc.close()

    with col_report:
        st.subheader("🧠 深度戰略分析報告")
        word_file = create_word_doc(st.session_state.report_content)
        st.download_button(
            label="📥 一鍵下載分析報告 (Word 格式)",
            data=word_file, file_name=f"Patent_Report_{patent_num if patent_num else 'Result'}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )
        report_container = st.container(height=800)
        with report_container:
            st.markdown(st.session_state.report_content)