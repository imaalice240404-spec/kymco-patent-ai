import streamlit as st
import google.generativeai as genai
import os
import tempfile
import base64
import json
import io
import pypdfium2 as pdfium
from PIL import Image, ImageDraw
from docx import Document

# 👇 從 Streamlit 本機或雲端的保險箱中讀取 API Key
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
genai.configure(api_key=GOOGLE_API_KEY)
# 升級使用最新的 Gemini 模型以提升視覺辨識力
model = genai.GenerativeModel('gemini-2.5-flash')

if 'report_content' not in st.session_state:
    st.session_state.report_content = ""

st.set_page_config(page_title="機車專利 PDF 戰情室", layout="wide")

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
                【一、 🚦 FTO 風險判定】(推論)：判定『🟢 綠燈：已失效』或『🔴 紅燈：具威脅』。
                【二、 📸 技術核心快照】(嚴格)：1.發明目的 2.核心技術 3.宣稱功效。
                【三、 🏢 研發部門精準派發】(推論)：挑選接收部門並附理由。
                【四、 🛑 先前技術與妥協分析 (防禦地雷)】(推論)：獨立項被迫增加了什麼限制？
                【五、 🧩 獨立項全要件拆解 (Claim Chart)】(嚴格)：一字不漏拆解原請求項文字，並指出「破口」。
                【六、 🪤 附屬項隱藏地雷探測】(嚴格)：挑出具「實質工程參數限制」的附屬項。
                【七、 👁️ 侵權可偵測性評估】(推論)：極易偵測 / 需破壞性拆解。
                【八、 🕵️‍♂️ 實證功效檢驗 (打假雷達)】(推論)：是否有實體數據？
                【九、 🛡️ 高階迴避設計建議 (防範均等論)】(推論)：基於物理原理提出迴避方案。
                【十、 🧬 技術演進與機構整併雷達】(推論)：是否將以往獨立的兩個元件整併？
                【十一、 🏷️ 元件符號圖面提取字典】(嚴格)：提取核心元件及其數字編號。
                '''
                
                response = model.generate_content([gemini_file, prompt])
                st.session_state.report_content = response.text

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
                with st.spinner("正在將 PDF 轉換為超清晰圖片..."):
                    # 🌟 降維打擊：將 PDF 轉成圖片直接貼上，無畏任何瀏覽器封鎖！
                    pdf_doc = pdfium.PdfDocument(uploaded_file.getvalue())
                    for i in range(len(pdf_doc)):
                        page = pdf_doc[i]
                        # scale=1.5 提供良好的閱讀畫質且不會拖垮系統
                        img = page.render(scale=1.5).to_pil()
                        st.image(img, caption=f"第 {i+1} 頁", use_container_width=True)
                    pdf_doc.close()

    with col_report:
        st.subheader("🧠 深度戰略分析報告")
        word_file = create_word_doc(st.session_state.report_content)
        st.download_button(
            label="📥 一鍵下載分析報告 (Word 格式)",
            data=word_file, file_name=f"Patent_Report.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )
        report_container = st.container(height=800)
        with report_container:
            st.markdown(st.session_state.report_content)

# ==========================================
# 鷹眼掃描區塊 (狙擊手升級版)
# ==========================================
    st.markdown("---")
    st.subheader("🎯 鷹眼自動標註 (指定狙擊模式)")

    # 🌟 新增：讓您可以手動輸入要尋找的「特定元件」
    col_config_1, col_config_2, col_config_3 = st.columns([1, 1.5, 1])
    with col_config_1:
        target_page_num = st.number_input("📄 選擇代表圖頁碼", min_value=1, value=2)
    with col_config_2:
        target_component = st.text_input("🎯 輸入想狙擊的元件 (例如)", value="水泵 或 水泵組件")
    with col_config_3:
        st.write("") 
        scan_btn = st.button("👁️ 啟動鷹眼狙擊", use_container_width=True)

    if scan_btn and uploaded_file is not None:
        with st.spinner(f"正在鎖定 第 {target_page_num} 頁的「{target_component}」..."):
            try:
                pdf = pdfium.PdfDocument(uploaded_file.getvalue())
                if target_page_num > len(pdf):
                    st.error(f"頁數錯誤！此 PDF 只有 {len(pdf)} 頁。")
                    pdf.close()
                else:
                    page = pdf[target_page_num - 1] 
                    bitmap = page.render(scale=3.0) 
                    pil_image = bitmap.to_pil()
                    pdf.close()

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as img_tmp:
                        pil_image.save(img_tmp.name, format="JPEG")
                        img_path = img_tmp.name

                    vision_file = genai.upload_file(img_path)
                    
                    # 🌟 狙擊專用 Prompt：強迫 AI 只看您指定的元件，並盡量框選標號
                    vision_prompt = f"""
                    你是一個精準的專利圖面定位 AI。
                    使用者的目標是尋找：「{target_component}」。
                    請在這張圖面中，找出與「{target_component}」最相關的 1 到 2 個局部特徵或數字標號。
                    請以 JSON 格式回傳，格式如下：
                    [
                      {{"name": "特徵或標號說明", "box": [ymin, xmin, ymax, xmax]}}
                    ]
                    注意：
                    1. box 座標為 0 到 1000 的整數百分比。
                    2. 請盡量「縮小範圍」，精準框選該元件本身或其數字標號的所在位置，絕對不要框選整個引擎或大面積不相關的區域。
                    """
                    vision_response = model.generate_content([vision_file, vision_prompt])
                    
                    response_text = vision_response.text.replace('```json', '').replace('```', '').strip()
                    bounding_boxes = json.loads(response_text)

                    draw = ImageDraw.Draw(pil_image)
                    img_width, img_height = pil_image.size
                    
                    for i, item in enumerate(bounding_boxes):
                        ymin, xmin, ymax, xmax = item["box"]
                        abs_xmin = int((xmin / 1000) * img_width)
                        abs_ymin = int((ymin / 1000) * img_height)
                        abs_xmax = int((xmax / 1000) * img_width)
                        abs_ymax = int((ymax / 1000) * img_height)
                        
                        # 改用半透明或細一點的框，讓視覺焦點更精確
                        draw.rectangle([abs_xmin, abs_ymin, abs_xmax, abs_ymax], outline="#00FF00", width=6)
                        draw.rectangle([abs_xmin, abs_ymin-35, abs_xmin+40, abs_ymin], fill="#00FF00")
                        draw.text((abs_xmin+10, abs_ymin-25), f"Target {i+1}", fill="black")
                    
                    col_img, col_list = st.columns([2, 1])
                    with col_img:
                        st.image(pil_image, caption=f"鷹眼狙擊目標：{target_component}", use_container_width=True)
                    
                    with col_list:
                        st.success(f"✅ 狙擊完成！尋找目標：{target_component}")
                        for i, item in enumerate(bounding_boxes):
                            st.markdown(f"**🎯 命中點 {i+1}：** {item['name']}")

                    os.remove(img_path)
                    genai.delete_file(vision_file.name)

            except Exception as e:
                st.error("AI 尋找特定特徵時發生偏移，請嘗試更換目標名稱（例如加上數字標號），並再試一次！")