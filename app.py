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

# 初始化所有 Session State
if 'report_content' not in st.session_state:
    st.session_state.report_content = ""
if 'ai_analysis_result' not in st.session_state:
    st.session_state.ai_analysis_result = None
if 'rd_database' not in st.session_state:
    st.session_state.rd_database = [] # Tab 3: 失效研發庫
if 'comp_database' not in st.session_state:
    st.session_state.comp_database = [] # 🌟 Tab 2: 競爭前案庫

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

# 🌟 建立頂層三模式切換
main_tab1, main_tab2, main_tab3 = st.tabs([
    "📄 戰術：單篇深度解剖 (PDF)", 
    "🗺️ 戰略：宏觀與前案篩選 (Excel)", 
    "💡 賦能：研發專屬彈藥庫 (Excel)"
])

# ==========================================
# 模式一：單篇專利深度解剖 (PDF)
# ==========================================
with main_tab1:
    st.markdown("支援 Google Patents 快速連線、自動辨識發明/新型專利，並產出精準戰略報告。")
    col_input1, col_input2 = st.columns([1, 2])
    with col_input1:
        st.subheader("1️⃣ 案件資訊與法態")
        applicant = st.text_input("申請人 (對手公司)", placeholder="例如：光陽工業", key="pdf_applicant")
        patent_num = st.text_input("專利號 (從 Tab 2 篩選後貼上)", placeholder="例如：I856744 或 M654321", key="pdf_num")
        if patent_num:
            clean_num = ''.join(e for e in patent_num if e.isalnum())
            google_patents_url = f"https://patents.google.com/patent/TW{clean_num}B" if clean_num.upper().startswith('I') else f"https://patents.google.com/patent/TW{clean_num}U"
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
                with st.spinner("大腦正在深挖技術與地雷，請稍候約 20 秒..."):
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                            tmp_file.write(uploaded_pdf.getvalue())
                            tmp_file_path = tmp_file.name

                        gemini_file = genai.upload_file(tmp_file_path)

                        is_utility_model = clean_num.upper().startswith('M')
                        
                        if is_utility_model:
                            claim_analysis_prompt = '''
                            【五、 🧱 具體結構特徵拆解 (Structural Features)】：
                            新型專利保護的是具體形狀與構造。請拆解其最核心的「物理結構、形狀與組裝關係」，不要探討抽象概念。
                            【六、 🪤 迴避設計難度評估】：
                            評估要替換掉這個特定結構的難度。這個機構設計是達成該功效的「唯一最佳解」嗎？RD 是否容易用其他常見的連桿/卡榫/螺絲配置來繞開？
                            '''
                        else:
                            claim_analysis_prompt = '''
                            【五、 🧩 獨立項全要件拆解 (Claim Chart)】：
                            最廣獨立項（請求項1）拆解，請以 1. 2. 3. 逐行乾淨條列拆解。
                            在最後一行加上「破口（限縮最嚴格之特徵）：精準點出最容易被迴避的限制條件」。
                            【六、 🪤 附屬項隱藏地雷探測】：
                            以數字條列出具備「具體結構形狀、相對位置、或工程參數限制」的附屬項。
                            '''

                        prompt = f'''
                        【⚠️ 語氣與術語強制校準】：你現在是一位資深機車專利代理人與研發主管。請使用機車研發黑話。
                        我已經提供了一份機車相關的專利 PDF 檔案，請仔細閱讀全文。
                        【補充資訊】申請人：{applicant} / 目前法律狀態：{status} / 專利類型：{"新型專利(Utility Model)" if is_utility_model else "發明專利(Invention)"}

                        【📝 輸出格式要求】請嚴格依序輸出以下兩個大區塊，並「完全模仿」以下指定的標題與排版格式：

                        ====================
                        區塊一：【🚀 RD 專屬十秒專利卡 (Patent Card)】
                        * **📝 Title (技術命名)**：(用一句話總結這項技術)
                        * **🔥 Problem (解決痛點)**：(原本的設計有什麼缺點)
                        * **💡 Solution (核心解法)**：(本專利用了什麼特殊結構解決)
                        * **🏷️ Key Elements (關鍵字標籤)**：(請提取 3~5 個核心元件的中文關鍵字)
                        * **🎯 Application (應用場景)**：(例如：速克達、重機、電動機車)
                        * **⚔️ 侵權風險視覺化 (自家技術對比清單)**：請列成 3 項 Checklist (使用 ✔ 符號)。

                        ====================
                        區塊二：【📜 智權與法務深度戰略分析】
                        【一、 🚦 FTO 風險判定】
                        (直接判定 🔴 紅燈：具威脅 / 🟡 黃燈：需注意 / 🟢 綠燈：已失效。並簡述威脅程度)

                        【二、 📸 技術核心快照】
                        1. **發明目的：** (說明旨在解決什麼弊病)
                        2. **核心技術：** (說明具體結構設計)
                        3. **宣稱功效：** (說明提升了什麼效果)

                        【三、 🏢 研發部門精準派發】
                        [填入建議部門名稱]。 (說明分發理由)

                        【四、 🛑 先前技術與妥協分析 (防禦地雷)】
                        **本案欲解決之舊設計缺點：** (描述習用技術的缺點)
                        
                        {claim_analysis_prompt}

                        【七、 👁️ 侵權可偵測性評估】
                        (判定：極易偵測 / 需破壞性拆解，並給出具體理由)

                        【八、 🕵️‍♂️ 實證功效檢驗 (打假雷達)】
                        (說明是否有實體測試數據，或僅為定性描述)

                        【九、 🛡️ 高階迴避設計建議 (防範均等論)】
                        (提出具體的迴避方向與作法)

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
# 模式二：宏觀專利大數據雷達 (Excel) + 競爭前案快篩
# ==========================================
with main_tab2:
    st.markdown("雙軌解析摘要與請求項，產出技術功效矩陣，並建立**對手競爭前案快篩庫**。")
    uploaded_excel = st.file_uploader("請上傳從 TWPAT 匯出的 Excel (有效專利/競爭對手)", type=["xlsx", "xls", "csv"], key="excel_upload_tab2")

    if uploaded_excel:
        try:
            if uploaded_excel.name.endswith('.csv'):
                df = pd.read_csv(uploaded_excel)
            else:
                df = pd.read_excel(uploaded_excel)
                
            st.success(f"✅ 成功載入資料！共計 {len(df)} 筆專利。")
            
            # 🌟 新增 sub_tab7: 競爭前案快篩庫
            sub_tab1, sub_tab2, sub_tab3, sub_tab4, sub_tab5, sub_tab6, sub_tab7 = st.tabs([
                "🏢 競爭者佈局", "📈 演進趨勢", "🎯 IPC 熱區", "🧠 AI 技術功效矩陣", "👑 核心地雷探勘", "🛍️ 產品防護牆", "🗄️ 競爭前案快篩庫"
            ])
            
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

            # --------------------------
            # AI 核心分析區塊 (矩陣 + 產品對應)
            # --------------------------
            with sub_tab4:
                st.markdown("### 🧠 AI 自動生成：技術功效矩陣")
                if abstract_col and title_col and patent_num_col:
                    analyze_count = st.slider("選擇要投入 AI 分析的專利數量", min_value=1, max_value=min(len(df), 30), value=min(len(df), 15), key="slider_tab2")
                    if st.button("🚀 啟動雙軌解析 (矩陣 + 產品防護網)", use_container_width=True):
                        with st.spinner("大腦正在交叉比對摘要與請求項，建立矩陣與產品關聯..."):
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
                                你必須將所有的專利，強制歸類到以下我定義好的「標準維度」中：
                                ▶️ 達成功效(X軸)：["提升散熱與冷卻", "提升燃燒與動力效率", "結構緊湊與輕量化", "降低震動與噪音", "改善潤滑與耐用度", "降低製造成本"]
                                ▶️ 技術手段(Y軸)：["汽缸本體與散熱片結構", "活塞與曲軸連桿機構", "氣門與進排氣佈局", "機油道與水套冷卻配置", "燃油噴射與點火控制", "引擎外殼與鎖固元件", "煞車與懸吊系統", "電控與儀表"]
                                ▶️ 對應產品線：["燃油速克達", "電動機車", "重型機車/檔車", "跨車系通用元件"]

                                請嚴格輸出 JSON 格式 (不要有 markdown 標記)，格式如下：
                                {{
                                  "matrix": [
                                    {{"專利號": "XXX", "技術手段": "上方的選項之一", "達成功效": "上方的選項之一", "對應產品線": "上方的選項之一"}}
                                  ],
                                  "top_patents": [
                                    {{"專利號": "XXX", "專利名稱": "XXX", "威脅度": "🔴極高 / 🟡中等", "入選理由": "此專利..."}}
                                  ]
                                }}
                                以下是專利資料：
                                {prompt_data}
                                """
                                
                                response = model.generate_content(prompt)
                                clean_text = response.text.replace('```json', '').replace('```', '').strip()
                                clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                                st.session_state.ai_analysis_result = json.loads(clean_text)
                                st.success("✅ 深度解析完成！請查看各分頁的圖表分析！")
                            except Exception as e:
                                st.error(f"分析失敗，錯誤：{e}")

                if st.session_state.ai_analysis_result:
                    matrix_df = pd.DataFrame(st.session_state.ai_analysis_result["matrix"])
                    fig4 = px.density_heatmap(
                        matrix_df, y='技術手段', x='達成功效', text_auto=True, color_continuous_scale='Reds',
                        title="技術功效矩陣圖 (數字代表專利篇數)"
                    )
                    st.plotly_chart(fig4, use_container_width=True)

            with sub_tab5:
                st.markdown("### 👑 核心高價值專利探勘 (Killer Patents)")
                if st.session_state.ai_analysis_result:
                    top_patents = st.session_state.ai_analysis_result.get("top_patents", [])
                    for p in top_patents:
                        with st.container(border=True):
                            threat_color = "red" if "高" in p.get("威脅度", "") else "orange"
                            st.markdown(f"#### 🎯 [{p.get('專利號')}] {p.get('專利名稱')}")
                            st.markdown(f"**威脅度：** <span style='color:{threat_color}; font-weight:bold;'>{p.get('威脅度')}</span>", unsafe_allow_html=True)
                            st.markdown(f"**🕵️‍♂️ 深度洞察：** {p.get('入選理由')}")
                else:
                    st.write("請先至「AI 技術功效矩陣」頁籤啟動解析。")

            with sub_tab6:
                st.markdown("### 🛍️ 產品防護牆 (Product vs Patent Mapping)")
                if st.session_state.ai_analysis_result:
                    mapping_df = pd.DataFrame(st.session_state.ai_analysis_result["matrix"])
                    mapping_counts = mapping_df.groupby(['對應產品線', '技術手段']).size().reset_index(name='專利數')
                    fig_tree = px.treemap(
                        mapping_counts, path=[px.Constant("全車系專利總覽"), '對應產品線', '技術手段'], 
                        values='專利數', color='專利數', color_continuous_scale='Teal'
                    )
                    fig_tree.update_traces(textinfo="label+value")
                    st.plotly_chart(fig_tree, use_container_width=True)
                else:
                    st.write("請先至「AI 技術功效矩陣」頁籤啟動解析。")

            # 🌟 全新子頁籤：競爭前案快篩庫 (The Funnel)
            with sub_tab7:
                st.markdown("### 🗄️ 競爭前案快篩庫 (Triage Database)")
                st.markdown("透過低耗能的 AI 批次掃描，替對手專利自動貼標。找尋潛在威脅後，**複製專利號至 Tab 1 進行 FTO 深度拆解**。")
                
                col_comp_stat, col_comp_clear = st.columns([4, 1])
                with col_comp_stat:
                    st.info(f"🗄️ 目前已快篩累積： **{len(st.session_state.comp_database)}** 筆競爭前案。")
                with col_comp_clear:
                    if st.button("🗑️ 清空快篩庫", use_container_width=True, key="clear_comp_btn"):
                        st.session_state.comp_database = []
                        st.rerun()

                if abstract_col and title_col and patent_num_col and applicant_col:
                    col_slider2, col_btn2 = st.columns([2, 1])
                    with col_slider2:
                        batch_range_comp = st.slider("選擇批次快篩區間 (列號)", min_value=1, max_value=len(df), value=(1, min(15, len(df))), key="comp_batch_slider")
                    with col_btn2:
                        st.write("") 
                        if st.button("🤖 啟動對手前案快篩", use_container_width=True, key="start_comp_btn"):
                            with st.spinner(f"正在掃描第 {batch_range_comp[0]} 到 {batch_range_comp[1]} 筆對手專利..."):
                                try:
                                    start_idx = batch_range_comp[0] - 1
                                    end_idx = batch_range_comp[1]
                                    sample_df_comp = df.iloc[start_idx:end_idx]
                                    
                                    prompt_data_comp = ""
                                    for idx, row in sample_df_comp.iterrows():
                                        p_num = str(row[patent_num_col])
                                        title = str(row[title_col])
                                        company = str(row[applicant_col]) # 🌟 直接從 Excel 抓公司名稱
                                        abs_text = str(row[abstract_col]).replace('\n', '')[:250] 
                                        
                                        prompt_data_comp += f"[{p_num}] 公司：{company} | 名稱：{title} | 摘要：{abs_text}\n"

                                    prompt_comp = f"""
                                    你是一位競爭情報分析師。請快速掃描以下機車專利，為每篇提取系統大分類與核心特徵。
                                    
                                    【🔴 絕對指令】
                                    大分類只能從以下挑選：["引擎與動力", "傳動", "煞車", "車架懸吊", "電控儀表", "外觀其他"]
                                    
                                    輸出 JSON：
                                    {{
                                      "database": [
                                        {{
                                          "專利號": "XXX",
                                          "專利名稱": "XXX",
                                          "申請人": "直接填入我提供的公司名稱",
                                          "大分類": "選項之一",
                                          "核心特徵": "用 15 字以內簡述這篇專利保護了什麼具體結構"
                                        }}
                                      ]
                                    }}
                                    資料：
                                    {prompt_data_comp}
                                    """
                                    
                                    response_comp = model.generate_content(prompt_comp)
                                    clean_text_comp = response_comp.text.replace('```json', '').replace('```', '').strip()
                                    clean_text_comp = clean_text_comp[clean_text_comp.find('{'):clean_text_comp.rfind('}')+1]
                                    
                                    result_json_comp = json.loads(clean_text_comp)
                                    new_data_comp = result_json_comp.get("database", [])
                                    
                                    existing_pnums_comp = [p['專利號'] for p in st.session_state.comp_database]
                                    for item in new_data_comp:
                                        if item['專利號'] not in existing_pnums_comp:
                                            st.session_state.comp_database.append(item)
                                            
                                    st.success(f"✅ 成功將 {len(new_data_comp)} 筆前案匯入快篩庫！")
                                except Exception as e:
                                    st.error(f"快篩失敗，錯誤：{e}")

                if st.session_state.comp_database:
                    st.markdown("---")
                    st.markdown("#### 🎯 競爭前案檢索面板")
                    
                    # 動態抓取已建立資料庫中的公司名單
                    all_companies = list(set([item.get("申請人", "未知") for item in st.session_state.comp_database]))
                    all_comp_categories = ["引擎與動力", "傳動", "煞車", "車架懸吊", "電控儀表", "外觀其他"]

                    col_c1, col_c2, col_c3 = st.columns(3)
                    with col_c1:
                        filter_company = st.multiselect("🏢 篩選『對手公司』", all_companies, placeholder="例如：三陽工業")
                    with col_c2:
                        filter_sys = st.multiselect("🏷️ 篩選『系統分類』", all_comp_categories, placeholder="例如：引擎與動力")
                    with col_c3:
                        search_comp = st.text_input("🔍 關鍵字搜尋特徵", placeholder="例如：冷卻、水泵...")

                    filtered_comp_db = st.session_state.comp_database
                    if filter_company:
                        filtered_comp_db = [item for item in filtered_comp_db if item.get("申請人") in filter_company]
                    if filter_sys:
                        filtered_comp_db = [item for item in filtered_comp_db if item.get("大分類") in filter_sys]
                    if search_comp:
                        filtered_comp_db = [item for item in filtered_comp_db if search_comp in item.get("核心特徵", "") or search_comp in item.get("專利名稱", "")]

                    if not filtered_comp_db:
                        st.warning("沒有符合條件的專利。")
                    else:
                        for p in filtered_comp_db:
                            with st.container(border=True):
                                st.markdown(f"**[{p.get('專利號')}] {p.get('專利名稱')}**")
                                c1, c2, c3 = st.columns([1, 1, 2])
                                c1.info(f"🏢 **申請人**：{p.get('申請人')}")
                                c2.warning(f"📂 **系統**：{p.get('大分類')}")
                                c3.error(f"⚙️ **特徵**：{p.get('核心特徵')}")
                                st.markdown(f"👉 **下一步：** 複製專利號 `{p.get('專利號')}`，前往 **[Tab 1]** 執行 PDF 深度 FTO 拆解！")

        except Exception as e:
            st.error(f"檔案讀取失敗，錯誤訊息：{e}")

# ==========================================
# 模式三：研發專屬彈藥庫 (Excel)
# ==========================================
with main_tab3:
    st.markdown("### 🛠️ 研發解題靈感與開源技術庫")
    st.markdown("將已失效的專利轉化為 RD 靈感庫，透過大系統分類聚攏資料，並支援分批寫入資料庫。")
    
    uploaded_rd_excel = st.file_uploader("📥 請上傳 TWPAT 匯出的 Excel (已篩選為失效專利)", type=["xlsx", "xls", "csv"], key="rd_excel_upload")

    if uploaded_rd_excel:
        try:
            if uploaded_rd_excel.name.endswith('.csv'):
                df_rd = pd.read_csv(uploaded_rd_excel)
            else:
                df_rd = pd.read_excel(uploaded_rd_excel)
                
            st.success(f"✅ 成功載入資料！共計 {len(df_rd)} 筆專利。")
            
            title_col_rd = next((col for col in df_rd.columns if '專利名稱' in col or '標題' in col), None)
            abstract_col_rd = next((col for col in df_rd.columns if '摘要' in col), None)
            patent_num_col_rd = next((col for col in df_rd.columns if '號' in col and ('公開' in col or '公告' in col or '申請' in col)), None)
            claim_col_rd = next((col for col in df_rd.columns if '申請專利範圍' in col or '請求項' in col), None)

            st.markdown("---")
            
            col_db_stat, col_db_clear = st.columns([4, 1])
            with col_db_stat:
                st.info(f"🗄️ 目前系統彈藥庫已累積： **{len(st.session_state.rd_database)}** 筆開源技術。")
            with col_db_clear:
                if st.button("🗑️ 清空資料庫", use_container_width=True, key="clear_db_btn"):
                    st.session_state.rd_database = []
                    st.rerun()

            st.markdown("#### 第一階段：分批萃取與標籤化 (Batch Processing)")
            
            if abstract_col_rd and title_col_rd and patent_num_col_rd:
                col_slider, col_btn = st.columns([2, 1])
                with col_slider:
                    batch_range = st.slider("選擇本次要交給 AI 處理的資料區間 (列號)", 
                                            min_value=1, max_value=len(df_rd), 
                                            value=(1, min(15, len(df_rd))), key="rd_batch_slider")
                
                with col_btn:
                    st.write("") 
                    if st.button("🤖 開始批次寫入彈藥庫", use_container_width=True, key="start_batch_btn"):
                        with st.spinner(f"大腦正在解讀第 {batch_range[0]} 到 {batch_range[1]} 筆專利..."):
                            try:
                                start_idx = batch_range[0] - 1
                                end_idx = batch_range[1]
                                sample_df_rd = df_rd.iloc[start_idx:end_idx]
                                
                                prompt_data_rd = ""
                                for idx, row in sample_df_rd.iterrows():
                                    p_num = str(row[patent_num_col_rd])
                                    title = str(row[title_col_rd])
                                    abs_text = str(row[abstract_col_rd]).replace('\n', '')[:250] 
                                    claim_text = str(row[claim_col_rd]).replace('\n', '')[:300] if claim_col_rd else "無"
                                    
                                    prompt_data_rd += f"[{p_num}] 名稱：{title} | 摘要：{abs_text} | 請求項：{claim_text}\n"

                                prompt_rd = f"""
                                你是一位機車廠的資深研發顧問。請閱讀以下專利，為每一篇提取三個維度的資訊，以建立研發知識庫。

                                【🔴 絕對指令 1：系統大分類】(只能從這 6 個選項中挑選 1 個)
                                請根據「專利名稱」與「請求項」，判斷該專利屬於哪一個系統：
                                ["引擎與動力系統", "傳動系統", "煞車系統", "車架與懸吊系統", "電系與儀表控制", "外觀件與其他"]

                                【🔴 絕對指令 2：特殊機構與達成功效】
                                * **特殊機構**：從摘要與請求項中提取這項專利的核心物理設計或結構。字數限 15 字內。
                                * **達成功效**：這個特殊機構具體解決了什麼痛點？或達成了什麼效果？字數限 20 字內。

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
                                {prompt_data_rd}
                                """
                                
                                response_rd = model.generate_content(prompt_rd)
                                clean_text_rd = response_rd.text.replace('```json', '').replace('```', '').strip()
                                clean_text_rd = clean_text_rd[clean_text_rd.find('{'):clean_text_rd.rfind('}')+1]
                                
                                result_json_rd = json.loads(clean_text_rd)
                                new_data_rd = result_json_rd.get("database", [])
                                
                                existing_pnums = [p['專利號'] for p in st.session_state.rd_database]
                                for item in new_data_rd:
                                    if item['專利號'] not in existing_pnums:
                                        st.session_state.rd_database.append(item)
                                        
                                st.success(f"✅ 成功將 {len(new_data_rd)} 筆資料匯入彈藥庫！")
                            except Exception as e:
                                st.error(f"分析失敗，錯誤：{e}")

            if st.session_state.rd_database:
                st.markdown("---")
                st.markdown("#### 🔍 第二階段：RD 專屬檢索面板")
                all_categories = ["引擎與動力系統", "傳動系統", "煞車系統", "車架與懸吊系統", "電系與儀表控制", "外觀件與其他"]
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    filter_cat = st.multiselect("🏷️ 選擇『研發系統大分類』", all_categories, placeholder="例如：尋找『煞車系統』相關機構", key="filter_cat")
                with col_f2:
                    search_query = st.text_input("🎯 關鍵字搜尋 (找痛點或機構)", placeholder="例如：散熱、連動、減震...", key="search_query")

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
