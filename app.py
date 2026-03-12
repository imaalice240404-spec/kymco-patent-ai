import os
import json
import random 
import streamlit as st
import google.generativeai as genai
import tempfile
import io
import pypdfium2 as pdfium
from docx import Document
import pandas as pd
import plotly.express as px

# 👇 建立 API 鑰匙池
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

if 'report_content' not in st.session_state:
    st.session_state.report_content = ""
if 'ai_analysis_result' not in st.session_state:
    st.session_state.ai_analysis_result = None

st.set_page_config(page_title="機車專利大數據戰情室", layout="wide")

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

st.title("🏍️ 機車專利 AI 戰略分析系統 (旗艦全景版)")
st.markdown("---")

# 🌟 建立頂層雙模式切換
main_tab1, main_tab2 = st.tabs(["📄 戰術：單篇專利深度解剖 (PDF)", "🗺️ 戰略：宏觀大數據雷達 (Excel)"])

# ==========================================
# 模式一：單篇專利深度解剖 (PDF)
# ==========================================
with main_tab1:
    st.markdown("支援 Google Patents 快速連線、十秒專利卡生成，並可一鍵匯出 Word 戰略報告。")
    col_input1, col_input2 = st.columns([1, 2])
    with col_input1:
        st.subheader("1️⃣ 案件資訊與法態")
        applicant = st.text_input("申請人 (對手公司)", placeholder="例如：光陽工業", key="pdf_applicant")
        patent_num = st.text_input("專利號 (輸入以啟用傳送門)", placeholder="例如：I856744", key="pdf_num")
        if patent_num:
            clean_num = ''.join(e for e in patent_num if e.isalnum())
            google_patents_url = f"https://patents.google.com/patent/TW{clean_num}B"
            st.markdown(f"👉 [點我秒開 Google Patents 查看 **{patent_num}**]({google_patents_url})")
        status = st.selectbox("目前案件狀態", ["請選擇...", "公開", "公告/核准", "核駁", "撤回", "消滅"], key="pdf_status")

    with col_input2:
        st.subheader("2️⃣ 上傳專利 PDF")
        uploaded_pdf = st.file_uploader("請拖曳或選擇專利 PDF 檔", type=["pdf"], key="pdf_upload")

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
        elif uploaded_pdf is None:
            st.warning("⚠️ 請上傳一份專利 PDF 檔案！")
        elif not patent_num:
            st.warning("⚠️ 請輸入「專利號」，系統才能為您建立專屬記憶檔案！")
        else:
            safe_applicant = "".join(c for c in applicant if c.isalnum() or c in (' ', '-', '_')).strip()
            folder_name = safe_applicant if safe_applicant else "未分類"
            applicant_dir = os.path.join(SAVE_DIR, folder_name)
            if not os.path.exists(applicant_dir):
                os.makedirs(applicant_dir)

            clean_num = ''.join(e for e in patent_num if e.isalnum())
            file_path = os.path.join(applicant_dir, f"{clean_num}.json")

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
                            tmp_file.write(uploaded_pdf.getvalue())
                            tmp_file_path = tmp_file.name

                        gemini_file = genai.upload_file(tmp_file_path)

                        prompt = f'''
                        【⚠️ 語氣與術語強制校準】：你現在是一位資深機車專利代理人與研發主管。請使用機車研發黑話。
                        我已經提供了一份機車相關的專利 PDF 檔案，請仔細閱讀全文。
                        【補充資訊】申請人：{applicant} / 目前法律狀態：{status}

                        【📝 輸出格式要求】請嚴格依序輸出以下兩個大區塊，並「完全模仿」以下指定的標題與排版格式，不要自創格式：

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
                        【一、 🚦 FTO 風險判定】
                        (直接判定 🔴 紅燈：具威脅 / 🟡 黃燈：需注意 / 🟢 綠燈：已失效。並簡述證書號與威脅程度)

                        【二、 📸 技術核心快照】
                        1. **發明目的：** (說明旨在解決什麼弊病)
                        2. **核心技術：** (說明具體結構設計)
                        3. **宣稱功效：** (說明提升了什麼效果)

                        【三、 🏢 研發部門精準派發】
                        [填入建議部門名稱]。 (說明分發理由)

                        【四、 🛑 先前技術與妥協分析 (防禦地雷)】
                        **本案欲解決之舊設計缺點：** (描述習用技術的缺點)
                        **為避開前案，獨立項被迫增加的特定空間配置限制（破口分析）：**
                        (列出獨立項增加的限制特徵)

                        【五、 🧩 獨立項全要件拆解 (Claim Chart)】
                        **最廣獨立項（請求項1）拆解：**
                        (請將請求項1的內容，以 1. 2. 3. 逐行乾淨條列拆解，絕對不要在每行加註解！)
                        (在拆解完的最後一行，加上以下總結：)
                        **破口（限縮最嚴格之特徵）：** (精準點出最容易被迴避的限制條件)

                        【六、 🪤 附屬項隱藏地雷探測】
                        (以 1. 2. 3. 數字條列出具備「具體結構形狀、相對位置、或工程參數限制」的附屬項，並說明其限制條件)

                        【七、 👁️ 侵權可偵測性評估】
                        (判定：極易偵測 / 需破壞性拆解，並給出具體理由)

                        【八、 🕵️‍♂️ 實證功效檢驗 (打假雷達)】
                        (說明是否有實體測試數據，或僅為定性描述)

                        【九、 🛡️ 高階迴避設計建議 (防範均等論)】
                        (基於第五點的破口，提出具體的迴避方向與作法)

                        【十、 🧬 技術演進與機構整併雷達】
                        (分析屬於機構整併或架構重組，並說明解決了什麼歷史困境)

                        【十一、 🏷️ 元件符號圖面提取字典】
                        (以垂直條列式列出，絕對不要加英文)
                        * 1: 引擎
                        * 3: 汽缸頭組
                        '''
                        
                        response = model.generate_content([gemini_file, prompt])
                        st.session_state.report_content = response.text

                        with open(file_path, "w", encoding="utf-8") as f:
                            json.dump({"content": st.session_state.report_content}, f, ensure_ascii=False)
                        st.success("✅ 分析完成，並已自動將報告存入系統記憶庫！")

                        os.remove(tmp_file_path)
                        genai.delete_file(gemini_file.name)
                    except Exception as e:
                        st.error(f"分析失敗：{e}")

    if st.session_state.report_content:
        st.markdown("---")
        col_pdf, col_report = st.columns([1.2, 1])
        
        with col_pdf:
            st.subheader("📄 專利原件 (純淨影像版)")
            if uploaded_pdf:
                with st.container(height=800):
                    with st.spinner("正在加載高畫質圖檔..."):
                        pdf_doc = pdfium.PdfDocument(uploaded_pdf.getvalue())
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


# ==========================================
# 模式二：宏觀專利大數據雷達 (Excel)
# ==========================================
with main_tab2:
    st.markdown("雙軌解析「摘要與請求項」，透過強制收斂字典產出高商業價值的技術功效矩陣，並自動探勘核心專利。")
    uploaded_excel = st.file_uploader("請上傳從 TWPAT 匯出的 Excel (請確保包含『摘要』與『申請專利範圍』)", type=["xlsx", "xls", "csv"], key="excel_upload")

    if uploaded_excel:
        try:
            if uploaded_excel.name.endswith('.csv'):
                df = pd.read_csv(uploaded_excel)
            else:
                df = pd.read_excel(uploaded_excel)
                
            st.success(f"✅ 成功載入資料！共計 {len(df)} 筆專利。")
            
            sub_tab1, sub_tab2, sub_tab3, sub_tab4, sub_tab5 = st.tabs(["🏢 競爭者佈局", "📈 演進趨勢", "🎯 IPC 熱區", "🧠 AI 技術功效矩陣", "👑 核心高價值專利"])
            
            # 尋找關鍵欄位
            applicant_col = next((col for col in df.columns if '申請人' in col), None)
            date_col = next((col for col in df.columns if '申請日' in col or '公開日' in col or '公告日' in col), None)
            ipc_col = next((col for col in df.columns if 'IPC' in col.upper()), None)
            title_col = next((col for col in df.columns if '專利名稱' in col or '標題' in col), None)
            abstract_col = next((col for col in df.columns if '摘要' in col), None)
            patent_num_col = next((col for col in df.columns if '號' in col and ('公開' in col or '公告' in col or '申請' in col)), None)
            claim_col = next((col for col in df.columns if '申請專利範圍' in col or '請求項' in col), None)

            with sub_tab1:
                if applicant_col:
                    top_applicants = df[applicant_col].value_counts().reset_index().head(10)
                    top_applicants.columns = ['公司名稱', '專利數量']
                    fig = px.bar(top_applicants, x='專利數量', y='公司名稱', orientation='h', color='專利數量', color_continuous_scale='Blues')
                    fig.update_layout(yaxis={'categoryorder':'total ascending'})
                    st.plotly_chart(fig, use_container_width=True)

            with sub_tab2:
                if date_col:
                    df['年份'] = df[date_col].astype(str).str[:4]
                    yearly_trend = df['年份'].value_counts().reset_index().sort_values('年份')
                    yearly_trend.columns = ['年份', '專利數量']
                    yearly_trend = yearly_trend[yearly_trend['年份'].str.isnumeric()]
                    fig2 = px.line(yearly_trend, x='年份', y='專利數量', markers=True, line_shape='spline', color_discrete_sequence=['#ff7f0e'])
                    st.plotly_chart(fig2, use_container_width=True)

            with sub_tab3:
                if ipc_col:
                    def get_main_group(ipc_str):
                        if pd.isna(ipc_str): return "未知"
                        return str(ipc_str).split(';')[0].split('|')[0].split('(')[0].strip()

                    df['IPC_四階'] = df[ipc_col].apply(get_main_group)
                    ipc_dist = df['IPC_四階'].value_counts().reset_index().head(15)
                    ipc_dist.columns = ['IPC四階分類', '數量']
                    fig3 = px.pie(ipc_dist, values='數量', names='IPC四階分類', hole=0.4)
                    fig3.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig3, use_container_width=True)

            with sub_tab4:
                st.markdown("### 🧠 AI 自動生成：技術功效矩陣")
                
                if abstract_col and title_col and patent_num_col:
                    if not claim_col:
                        st.warning("⚠️ 您的 Excel 中未包含『申請專利範圍』欄位。AI 將僅依賴『摘要』進行分析，精準度會受限！建議重新從 TWPAT 匯出。")
                    
                    analyze_count = st.slider("選擇要投入 AI 矩陣分析的專利數量", min_value=1, max_value=min(len(df), 30), value=min(len(df), 15))
                    
                    if st.button("🚀 啟動雙軌解析 (矩陣 + 核心探勘)", use_container_width=True):
                        with st.spinner("大腦正在交叉比對摘要與請求項，並執行強制收斂分類..."):
                            try:
                                sample_df = df.head(analyze_count)
                                prompt_data = ""
                                for idx, row in sample_df.iterrows():
                                    p_num = str(row[patent_num_col])
                                    title = str(row[title_col])
                                    abs_text = str(row[abstract_col]).replace('\n', '')[:300] 
                                    claim_text = str(row[claim_col]).replace('\n', '')[:500] if claim_col else "無"
                                    
                                    prompt_data += f"[{p_num}] {title} | 摘要：{abs_text} | 請求項：{claim_text}\n"

                                prompt = f"""
                                你是一位世界頂尖的專利佈局與侵權分析師。請交叉閱讀以下 {analyze_count} 篇機車領域專利的摘要與請求項。
                                
                                【🔴 絕對指令：強制收斂分類】
                                為了繪製有意義的技術功效矩陣，你【嚴格禁止】為每一篇專利發明獨特的詞彙。
                                你必須將所有的專利，強制歸類到以下我定義好的「標準維度」中。如果沒有完全符合的，請選擇最接近的概念。

                                ▶️ 允許使用的「達成功效」(X軸) 只能從以下 6 個選項中挑選：
                                ["提升散熱與冷卻", "提升燃燒與動力效率", "結構緊湊與輕量化", "降低震動與噪音", "改善潤滑與耐用度", "降低製造成本"]

                                ▶️ 允許使用的「技術手段」(Y軸) 只能從以下 6 個選項中挑選：
                                ["汽缸本體與散熱片結構", "活塞與曲軸連桿機構", "氣門與進排氣佈局", "機油道與水套冷卻配置", "燃油噴射與點火控制", "引擎外殼與鎖固元件"]

                                請嚴格輸出一個包含兩個 Key 的 JSON 物件 (不要有 markdown 標記)，格式如下：
                                {{
                                  "matrix": [
                                    {{"專利號": "XXX", "技術手段": "這裡只能填入上述的6個選項之一", "達成功效": "這裡只能填入上述的6個選項之一"}}
                                  ],
                                  "top_patents": [
                                    {{"專利號": "XXX", "專利名稱": "XXX", "威脅度": "🔴極高 / 🟡中等", "入選理由": "此專利..."}}
                                  ]
                                }}

                                任務 1 (matrix)：為每一篇專利選擇最符合的標準手段與功效。
                                任務 2 (top_patents)：挑選出「最具威脅性或最具特別意義」的 1~3 篇核心專利，給予威脅度評級與入選理由。

                                以下是專利資料：
                                {prompt_data}
                                """
                                
                                response = model.generate_content(prompt)
                                
                                # 增強 JSON 解析防呆
                                clean_text = response.text.replace('```json', '').replace('```', '').strip()
                                clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                                st.session_state.ai_analysis_result = json.loads(clean_text)
                                st.success("✅ 深度解析完成！請查看下方矩陣，並前往『👑 核心高價值專利』頁籤查看重點威脅！")
                                
                            except Exception as e:
                                st.error(f"分析失敗，可能是資料格式過於複雜或API額度已滿。錯誤：{e}")

                if st.session_state.ai_analysis_result:
                    matrix_df = pd.DataFrame(st.session_state.ai_analysis_result["matrix"])
                    fig4 = px.density_heatmap(
                        matrix_df, y='技術手段', x='達成功效', text_auto=True, color_continuous_scale='Reds',
                        title="技術功效矩陣圖 (數字代表專利篇數)"
                    )
                    fig4.update_layout(xaxis_title="達成功效", yaxis_title="技術手段")
                    st.plotly_chart(fig4, use_container_width=True)

            with sub_tab5:
                st.markdown("### 👑 核心高價值專利探勘 (Killer Patents)")
                st.info("💡 AI 已從上述專利池中，為您篩選出最具威脅性與特別意義的核心專利。")
                
                if st.session_state.ai_analysis_result:
                    top_patents = st.session_state.ai_analysis_result.get("top_patents", [])
                    if not top_patents:
                        st.write("這批專利中，AI 未偵測到具備高度威脅性的異常專利。")
                    else:
                        for p in top_patents:
                            with st.container():
                                threat_color = "red" if "高" in p.get("威脅度", "") else "orange"
                                st.markdown(f"#### 🎯 [{p.get('專利號')}] {p.get('專利名稱')}")
                                st.markdown(f"**威脅度評級：** <span style='color:{threat_color}; font-weight:bold;'>{p.get('威脅度')}</span>", unsafe_allow_html=True)
                                st.markdown(f"**🕵️‍♂️ AI 深度洞察：** {p.get('入選理由')}")
                                st.markdown("---")
                else:
                    st.write("請先至「AI 技術功效矩陣」頁籤啟動解析。")

        except Exception as e:
            st.error(f"檔案讀取失敗，錯誤訊息：{e}")