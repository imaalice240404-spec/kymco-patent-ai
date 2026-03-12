import streamlit as st
import google.generativeai as genai
import tempfile
import os
import base64
import io
from docx import Document

from streamlit_pdf_viewer import pdf_viewer  # 🌟 新增：專屬 PDF 閱讀器
# 👇 從 Streamlit 本機或雲端的保險箱中讀取 API Key
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

if 'report_content' not in st.session_state:
    st.session_state.report_content = ""

# 網頁設定，必須緊貼最左邊
st.set_page_config(page_title="機車專利 PDF 戰情室", layout="wide")

# --- 簡易密碼門禁 (緊貼最左邊) ---
def check_password():
    """要求使用者輸入密碼，正確才顯示網頁內容。"""
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
    st.stop() # 密碼錯誤就停止執行後面的程式碼
# --- 門禁結束 ---


st.title("🏍️ 機車專利 AI 戰略分析系統 (RD 視覺化旗艦版)")
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
    else:
        with st.spinner("大腦正在深挖先前技術與獨立項地雷，請稍候約 20 秒..."):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_file_path = tmp_file.name

                gemini_file = genai.upload_file(tmp_file_path)

                # 🌟 雙大腦混合版 + RD 專屬 Patent Card 終極 Prompt
                prompt = f'''
                【⚠️ 語氣與術語強制校準】：你現在是一位資深機車專利代理人與研發主管。請使用機車研發黑話（如：搖臂、動力單元、導流罩）。

                我已經提供了一份機車相關的專利 PDF 檔案，請仔細閱讀全文。
                【補充資訊】申請人：{applicant} / 目前法律狀態：{status}

                【🧠 雙大腦運作模式切換 (Hybrid Analysis Mode)】
                🛡️ 模式一：嚴格法理對照 (Zero-Hallucination) -> 適用於解析權利範圍，必須死忠原文。
                🕵️‍♂️ 模式二：通常知識者推論 (PHOSITA) -> 適用於評價功效與迴避設計，請大膽提出工程質疑。

                【📝 輸出格式要求】
                請嚴格依序輸出以下兩個大區塊：

                ====================
                區塊一：【🚀 RD 專屬十秒專利卡 (Patent Card)】
                (請以簡潔、條列式輸出，讓工程師 10 秒看懂)
                * **📝 Title (技術命名)**：(用一句話總結這項技術)
                * **🔥 Problem (解決痛點)**：(原本的設計有什麼缺點)
                * **💡 Solution (核心解法)**：(本專利用了什麼特殊結構解決)
                * **🏷️ Key Elements (關鍵字標籤)**：(請提取 3~5 個核心元件的中文關鍵字，加上 Hashtag，例如：#水套冷卻 #連桿機構)
                * **🎯 Application (應用場景)**：(例如：速克達、電動機車、重機)
                * **⚔️ 侵權風險視覺化 (自家技術對比清單)**：
                  請將該專利獨立項的「絕對必要特徵」列成 3 項 Checklist (使用 ✔ 符號)。

                ====================
                區塊二：【📜 智權與法務深度戰略分析】
                (請接續輸出 11 大戰略區塊)
                【一、 🚦 FTO 風險判定】(推論)：判定『🟢 綠燈：已失效』或『🔴 紅燈：具威脅』或『⚪ 白燈：狀態未明』。
                【二、 📸 技術核心快照】(嚴格)：1.發明目的 2.核心技術 3.宣稱功效。
                【三、 🏢 研發部門精準派發】(推論)：挑選接收部門並附理由。
                【四、 🛑 先前技術與妥協分析 (防禦地雷)】(推論)：本案欲解決何種舊設計缺點？獨立項被迫增加了什麼限制？
                【五、 🧩 獨立項全要件拆解 (Claim Chart)】(嚴格)：一字不漏拆解原請求項文字，並指出「破口」。
                【六、 🪤 附屬項隱藏地雷探測】(嚴格)：挑出具「實質工程參數限制」的附屬項。
                【七、 👁️ 侵權可偵測性評估】(推論)：極易偵測 / 需破壞性拆解 / 極難舉證，簡述理由。
                【八、 🕵️‍♂️ 實證功效檢驗 (打假雷達)】(推論)：是否有實體數據？若無，請依物理常識質疑其誇大之處。
                【九、 🛡️ 高階迴避設計建議 (防範均等論)】(推論)：基於物理原理提出迴避方案。
                【十、 🧬 技術演進與機構整併雷達】(推論)：是否將以往獨立的兩個元件整併？屬於漸進還是架構重組？
                【十一、 🏷️ 元件符號圖面提取字典】(嚴格)：提取核心元件及其數字編號 (JSON 格式)。
                '''
                
                response = model.generate_content([gemini_file, prompt])
                st.session_state.report_content = response.text

                os.remove(tmp_file_path)
                genai.delete_file(gemini_file.name)
            except Exception as e:
                st.error(f"分析失敗，請檢查網路連線或 API 狀態：{e}")

if st.session_state.report_content:
    # 🌟 修改 1：把原本的 [1, 1] 改成 [1.2, 1]，給左邊多一點空間
    col_pdf, col_report = st.columns([1.2, 1])
    
    with col_pdf:
        st.subheader("📄 專利原件 (左側獨立滾動)")
        if uploaded_file:
            with st.container(height=800):
                # 🌟 修改 2：把原本的 width=700 縮小成 550
                pdf_viewer(input=uploaded_file.getvalue(), width=550)
                
    with col_report:
        st.subheader("🧠 深度戰略分析報告")
        # ... (後面的下載按鈕與 markdown 都不變) ...
        
        word_file = create_word_doc(st.session_state.report_content)
        st.download_button(
            label="📥 一鍵下載分析報告 (Word 格式)",
            data=word_file,
            file_name=f"Patent_Strategy_Report_{patent_num if patent_num else 'Result'}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )
        
        report_container = st.container(height=800)
        with report_container:
            st.markdown(st.session_state.report_content)