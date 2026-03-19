import os
import json
import random 
import streamlit as st
import google.generativeai as genai
import tempfile
import io
import pypdfium2 as pdfium
import base64
from docx import Document
import pandas as pd
import plotly.express as px
import streamlit.components.v1 as components
from PIL import Image, ImageOps

# ==========================================
# 🛑 核心配置與 API 初始化
# ==========================================
st.set_page_config(page_title="機車專利 AI 戰情室", layout="wide")

api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# 🌟 初始化系統所有 Session State
if 'ip_report_content' not in st.session_state: st.session_state.ip_report_content = ""
if 'rd_card_data' not in st.session_state: st.session_state.rd_card_data = None
if 'claim_data_t2' not in st.session_state: st.session_state.claim_data_t2 = None
if 'pdf_bytes_main' not in st.session_state: st.session_state.pdf_bytes_main = None
if 'scanned_pages' not in st.session_state: st.session_state.scanned_pages = {}
if 'ai_analysis_result' not in st.session_state: st.session_state.ai_analysis_result = None
if 'rd_database' not in st.session_state: st.session_state.rd_database = [] 
if 'comp_database' not in st.session_state: st.session_state.comp_database = [] 
if 'active_patent_num' not in st.session_state: st.session_state.active_patent_num = ""

SAVE_DIR = "saved_reports"
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)

# ==========================================
# 🛑 工具函式庫
# ==========================================
def crop_white_margins(img):
    if img.mode != 'RGB':
        img = img.convert('RGB')
    inv = ImageOps.invert(img)
    bbox = inv.getbbox()
    if bbox:
        padded_bbox = (max(0, bbox[0]-20), max(0, bbox[1]-20), min(img.width, bbox[2]+20), min(img.height, bbox[3]+20))
        return img.crop(padded_bbox)
    return img

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

def create_word_doc(text):
    doc = Document()
    doc.add_heading('專利戰略深度分析報告 (IP 嚴謹版)', 0)
    for para in text.split('\n'):
        if para.strip():
            doc.add_paragraph(para.strip())
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

if not check_password():
    st.stop()

# ==========================================
# 🚧 全局核心上傳與分析區
# ==========================================
st.title("🏍️ 機車專利 AI 戰略分析系統")
st.markdown("---")

with st.container(border=True):
    st.subheader("📥 第一步：設定案件資訊並上傳 PDF (單篇深度分析用)")
    col_input1, col_input2, col_input3 = st.columns([1.5, 2, 1])

    with col_input1:
        applicant_main = st.text_input("申請人 (對手公司)", placeholder="例如：光陽工業", key="main_app")
        patent_num_main = st.text_input("專利號", placeholder="例如：I856744", key="main_num")
        st.session_state.active_patent_num = patent_num_main
        if patent_num_main:
            clean_num_m = ''.join(e for e in patent_num_main if e.isalnum())
            google_patents_url = f"https://patents.google.com/patent/TW{clean_num_m}B" if clean_num_m.upper().startswith('I') else f"https://patents.google.com/patent/TW{clean_num_m}U"
            st.markdown(f"👉 [Google Patents 傳送門 **{patent_num_main}**]({google_patents_url})")

    with col_input2:
        status_main = st.selectbox("目前案件狀態", ["請選擇...", "公開", "公告/核准", "核駁", "撤回", "消滅"], key="main_status")
        uploaded_pdf_main = st.file_uploader("上傳專利 PDF 檔", type=["pdf"], key="main_upload")

    with col_input3:
        st.write("")
        st.write("")
        if st.button("🚀 啟動全局 AI 深度解剖", use_container_width=True, type="primary"):
            if status_main == "請選擇..." or uploaded_pdf_main is None or not patent_num_main:
                st.warning("⚠️ 請確認：1.輸入專利號 2.選擇狀態 3.上傳 PDF")
            else:
                pdf_bytes = uploaded_pdf_main.getvalue()
                st.session_state.pdf_bytes_main = pdf_bytes
                st.session_state.scanned_pages = {} 

                safe_app = "".join(c for c in applicant_main if c.isalnum() or c in (' ', '-', '_')).strip()
                folder_name = safe_app if safe_app else "未分類"
                applicant_dir = os.path.join(SAVE_DIR, folder_name)
                if not os.path.exists(applicant_dir): os.makedirs(applicant_dir)

                clean_num = ''.join(e for e in patent_num_main if e.isalnum())
                file_path = os.path.join(applicant_dir, f"{clean_num}_master.json")

                if os.path.exists(file_path):
                    with st.spinner("載入歷史分析數據..."):
                        with open(file_path, "r", encoding="utf-8") as f:
                            saved_data = json.load(f)
                            st.session_state.ip_report_content = saved_data.get("ip_report", "")
                            st.session_state.rd_card_data = saved_data.get("rd_card", None)
                            st.session_state.claim_data_t2 = saved_data.get("vis_data", None)
                        st.success("⚡ 歷史紀錄載入完成！請切換下方頁籤查看。")
                else:
                    with st.spinner("大腦正在進行全局地毯式搜索，約需 30 秒..."):
                        try:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                                tmp_file.write(pdf_bytes)
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

                            prompt_master = f'''
                            【⚠️ 語氣與術語強制校準】：你現在是一位資深機車專利代理人與研發主管。請使用機車研發黑話。
                            我已經提供了一份機車相關的專利 PDF 檔案，請仔細閱讀全文。
                            【補充資訊】申請人：{applicant_main} / 目前法律狀態：{status_main} / 專利類型：{"新型專利" if is_utility_model else "發明專利"}

                            【🔴 輸出格式嚴格要求：純 JSON 格式】
                            {{
                              "rd_card": {{
                                "title": "用一句話總結這項技術",
                                "problem": "原本的設計有什麼缺點",
                                "solution": "本專利用了什麼特殊結構解決",
                                "application": "速克達/重機",
                                "risk_check": ["破口限制特徵1", "破口限制特徵2", "破口限制特徵3"],
                                "design_avoid_rd": ["具體機構迴避方向1", "具體機構迴避方向2"]
                              }},
                              "vis_data": {{
                                "claims": ["1. 請求項逐句", "第二句..."],
                                "components": [ {{"id": "10", "name": "車架"}} ],
                                "spec_texts": ["【00xx】實施方式段落1", "【00xx】實施方式段落2"]
                              }},
                              "ip_report": "【一、 🚦 FTO 風險判定】\\n(🔴/🟡/🟢 判定與簡述)\\n\\n【二、 📸 技術核心快照】\\n1. 發明目的\\n2. 核心技術\\n3. 宣稱功效\\n\\n【三、 🏢 研發部門精準派發】\\n\\n【四、 🛑 先前技術與妥協分析 (防禦地雷)】\\n\\n{claim_analysis_prompt}\\n\\n【七、 👁️ 侵權可偵測性評估】\\n\\n【八、 🕵️‍♂️ 實證功效檢驗 (打假雷達)】\\n\\n【九、 🛡️ 高階迴避設計建議 (防範均等論)】\\n\\n【十、 🧬 技術演進與機構整併雷達】\\n\\n【十一、 🏷️ 元件符號圖面提取字典】"
                            }}
                            備註：vis_data 中的 components 必須去尋找專利最後面的「符號簡單說明」，將所有元件提取出來。
                            '''
                            
                            response = model.generate_content([gemini_file, prompt_master])
                            clean_text = response.text.replace('```json', '').replace('```', '').strip()
                            clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                            master_json = json.loads(clean_text)

                            st.session_state.rd_card_data = master_json.get("rd_card")
                            st.session_state.ip_report_content = master_json.get("ip_report")
                            st.session_state.claim_data_t2 = master_json.get("vis_data")
                            
                            with open(file_path, "w", encoding="utf-8") as f:
                                json.dump({"ip_report": st.session_state.ip_report_content, "rd_card": st.session_state.rd_card_data, "vis_data": st.session_state.claim_data_t2}, f, ensure_ascii=False)
                            st.success("✅ 全局分析完成！請切換下方頁籤查看。")
                            os.remove(tmp_file_path)
                            genai.delete_file(gemini_file.name)
                        except Exception as e:
                            st.error(f"分析失敗：{e}")

st.markdown("<br>", unsafe_allow_html=True)

# 🌟 建立頂層四模式切換
main_tab1, main_tab2, main_tab3, main_tab4 = st.tabs([
    "🧑‍💻 Tab 1 研發：迴避設計大屏 (RD)", 
    "⚖️ Tab 2 智權：法務審查中心 (IP)", 
    "🗺️ Tab 3 戰略：宏觀大數據與快篩 (Excel)", 
    "💡 Tab 4 賦能：研發開源技術庫 (Excel)"
])

# ==========================================
# 🧑‍💻 Tab 1：研發迴避設計大屏 (理想排版實作)
# ==========================================
with main_tab1:
    if not st.session_state.rd_card_data or not st.session_state.pdf_bytes_main:
        st.info("請先於上方上傳 PDF 並啟動分析。")
    else:
        rd_data = st.session_state.rd_card_data
        
        # 🌟 上半部：三卡並列 (完美還原附圖邏輯)
        col_c1, col_c2, col_c3 = st.columns(3)
        
        # 【卡片 1：研發戰略看板】
        with col_c1:
            with st.container(border=True, height=420):
                st.markdown(f"#### 🎯 研發戰略看板")
                st.markdown(f"**{rd_data.get('title', '未知技術')}**")
                
                # 修復之前的錯誤寫法，改用乾淨的 HTML 標籤
                f_color = "red" if "🔴" in st.session_state.ip_report_content else "orange" if "🟡" in st.session_state.ip_report_content else "green"
                f_text = "🔴 具備威脅" if f_color == "red" else "🟡 需注意" if f_color == "orange" else "🟢 低風險"
                st.markdown(f"**🚦 FTO 燈號：** <span style='color:{f_color}; font-weight:bold; font-size:18px;'>{f_text}</span>", unsafe_allow_html=True)
                st.markdown("---")
                st.markdown(f"**🔥 解決痛點：** {rd_data.get('problem', '')}")
                st.markdown(f"**💡 核心解法：** {rd_data.get('solution', '')}")
                st.markdown(f"**🎯 應用場景：** {rd_data.get('application', '')}")

        # 【卡片 2：自家技術 CheckBox】
        with col_c2:
            with st.container(border=True, height=420):
                st.markdown("#### ⚔️ 自家技術 CheckBox 檢核")
                st.caption("請確認我司目前設計是否具備以下「權利要求獨立項特徵」：")
                risk_list = rd_data.get('risk_check', [])
                checked_count = 0
                for i, risk in enumerate(risk_list):
                    if st.checkbox(f"{risk}", key=f"risk_c_{i}"): 
                        checked_count += 1
                
                st.markdown("<br>", unsafe_allow_html=True)
                if len(risk_list) > 0:
                    if checked_count == len(risk_list): 
                        st.markdown("<div style='padding:10px; background-color:#ffebee; color:#c62828; border-radius:5px;'><b>⚠️ 警告：特徵全中，高度侵權風險！</b></div>", unsafe_allow_html=True)
                    elif checked_count > 0: 
                        st.markdown(f"<div style='padding:10px; background-color:#fff8e1; color:#f57f17; border-radius:5px;'><b>注意：命中 {checked_count}/{len(risk_list)} 個特徵，具均等論風險。</b></div>", unsafe_allow_html=True)
                    else: 
                        st.markdown("<div style='padding:10px; background-color:#e8f5e9; color:#2e7d32; border-radius:5px;'><b>🎉 全數未命中，文義迴避成功。</b></div>", unsafe_allow_html=True)

        # 【卡片 3：迴避設計建議方向】
        with col_c3:
            with st.container(border=True, height=420):
                st.markdown("#### 🛡️ 迴避設計建議方向")
                st.caption("針對前述之限制特徵，建議研發之修改方向：")
                for avoid in rd_data.get('design_avoid_rd', []):
                    st.markdown(f"✅ {avoid}")

        st.markdown("---")
        
        # 🌟 下半部：終極滿版雙向連動大屏
        pdf_doc_v = pdfium.PdfDocument(st.session_state.pdf_bytes_main)
        total_pages_v = len(pdf_doc_v)

        col_page, col_btn, _ = st.columns([1, 1, 3])
        with col_page:
            target_page = st.number_input(f"📄 跳至專利圖紙頁碼 (共 {total_pages_v} 頁)", min_value=1, max_value=total_pages_v, value=min(2, total_pages_v), key="vis_page_rd")
        
        page = pdf_doc_v[target_page - 1]
        raw_pil_img = page.render(scale=2.0).to_pil()
        cropped_img = crop_white_margins(raw_pil_img) 
        
        img_byte_arr = io.BytesIO()
        cropped_img.save(img_byte_arr, format='JPEG')
        encoded_img = base64.b64encode(img_byte_arr.getvalue()).decode()
        img_uri = f"data:image/jpeg;base64,{encoded_img}"

        is_scanned = str(target_page) in st.session_state.scanned_pages
        with col_btn:
            st.write("")
            if not is_scanned:
                if st.button(f"🔍 啟動圖片標號鎖定", use_container_width=True, key="btn_scan_rd"):
                    with st.spinner("Gemini Vision 正在鎖定座標..."):
                        try:
                            comp_dict_list = st.session_state.claim_data_t2.get("components", [])
                            known_comps_str = json.dumps(comp_dict_list, ensure_ascii=False)
                            prompt_vision = f'''這是一張專利圖。元件表：{known_comps_str}。找出圖片上所有標號的 相對座標(0.0~1.0)。輸出 JSON：{{ "hotspots": [ {{"number": "31", "name": "汽缸頭", "x_rel": 0.45, "y_rel": 0.55}} ] }}'''
                            response_vis = model.generate_content([cropped_img, prompt_vision])
                            clean_text_vis = response_vis.text.replace('```json', '').replace('```', '').strip()
                            clean_text_vis = clean_text_vis[clean_text_vis.find('{'):clean_text_vis.rfind('}')+1]
                            ai_visual_data = json.loads(clean_text_vis).get("hotspots", [])
                            st.session_state.scanned_pages[str(target_page)] = ai_visual_data
                            st.rerun()
                        except: st.error("視覺解析失敗。")
            else:
                st.success("⚡ 座標已鎖定！請體驗下方雙向連動。")

        # 滿版 HTML 渲染
        if is_scanned:
            ai_visual_data = st.session_state.scanned_pages[str(target_page)]
            comp_dict_list = st.session_state.claim_data_t2.get("components", [])
            claim_lines = st.session_state.claim_data_t2.get("claims", [])
            claim_text_full = "<br><br>".join(claim_lines)
            
            for comp in comp_dict_list:
                c_num = comp.get("id", "")
                c_name = comp.get("name", "")
                replacement = f'<span class="comp-text comp-{c_num}" onmouseover="hoverText(\'{c_num}\')" onmouseout="leaveText(\'{c_num}\')">{c_name} ({c_num})</span>'
                claim_text_full = claim_text_full.replace(f"{c_name} ({c_num})", replacement).replace(c_name, replacement)

            hotspots_html = ""
            for spot in ai_visual_data:
                if spot['name'] != "未知":
                    hotspots_html += f"""
                    <div class="hotspot hotspot-marker-{spot['number']}" id="hotspot-{spot['number']}"
                         style="left: {spot['x_rel']*100}%; top: {spot['y_rel']*100}%;"
                         onmouseover="hoverImage('{spot['number']}', '{spot['name']}')" 
                         onmouseout="leaveImage('{spot['number']}')">
                    </div>
                    """

            html_skeleton = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
                body {{ margin: 0; font-family: sans-serif; background: #fff; }}
                .main-container {{ display: flex; height: 800px; width: 100%; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; }}
                .img-section {{ flex: 6; position: relative; overflow: auto; background: #f8f9fa; border-right: 2px solid #ddd; display: flex; justify-content: center; align-items: flex-start; padding: 10px; }}
                .img-wrapper {{ position: relative; display: inline-block; }}
                .patent-img {{ max-width: 100%; height: auto; display: block; }}
                .hotspot {{ position: absolute; width: 35px; height: 35px; transform: translate(-50%, -50%); border-radius: 50%; cursor: pointer; transition: 0.2s; border: 2px solid transparent; z-index: 10; }}
                .hotspot:hover {{ background: rgba(255, 0, 0, 0.3); border: 2px solid red; box-shadow: 0 0 10px rgba(255,0,0,0.5); z-index: 50; }}
                .hotspot-active {{ background: rgba(255, 255, 0, 0.6) !important; border: 3px solid red !important; box-shadow: 0 0 20px red !important; transform: translate(-50%, -50%) scale(1.3); z-index: 50; }}
                #tooltip {{ display: none; position: absolute; background: rgba(0, 0, 0, 0.8); color: white; padding: 6px 12px; border-radius: 4px; font-size: 14px; z-index: 100; pointer-events: none; white-space: nowrap; }}
                .text-section {{ flex: 4; padding: 20px; overflow-y: auto; font-size: 16px; line-height: 1.8; color: #333; }}
                .comp-text {{ color: #0284c7; font-weight: bold; cursor: pointer; border-bottom: 1px dashed #0284c7; padding: 0 2px; transition: 0.2s; }}
                .highlight-active {{ background-color: #fef08a; color: #b91c1c; border-bottom: none; border-radius: 3px; padding: 2px 4px; }}
            </style>
            </head>
            <body>
            <div class="main-container">
                <div class="img-section" id="img-container">
                    <div class="img-wrapper">
                        <img src="{img_uri}" class="patent-img">
                        {hotspots_html}
                    </div>
                    <div id="tooltip"></div>
                </div>
                <div class="text-section">
                    <div style="font-size:18px; font-weight:bold; color:#1e3a8a; border-bottom:2px solid #eee; padding-bottom:8px; margin-bottom:15px; position:sticky; top:0; background:white; z-index:10;">
                        📜 獨立項文義對應 (雙向連動)
                    </div>
                    {claim_text_full}
                </div>
            </div>
            <script>
                const tooltip = document.getElementById('tooltip');
                function hoverImage(num, name) {{
                    document.onmousemove = e => {{ tooltip.style.left = (e.pageX + 15) + 'px'; tooltip.style.top = (e.pageY + 15) + 'px'; }};
                    tooltip.innerHTML = "標號 <b>" + num + "</b> : " + name; tooltip.style.display = 'block';
                    document.querySelectorAll('.comp-' + num).forEach((el, i) => {{ el.classList.add('highlight-active'); if(i===0) el.scrollIntoView({{behavior:'smooth', block:'center'}}); }});
                }}
                function leaveImage(num) {{
                    document.onmousemove = null; tooltip.style.display = 'none';
                    document.querySelectorAll('.comp-' + num).forEach(el => el.classList.remove('highlight-active'));
                }}
                function hoverText(num) {{
                    document.querySelectorAll('.comp-' + num).forEach(el => el.classList.add('highlight-active'));
                    const hs = document.getElementById('hotspot-' + num);
                    if(hs) {{ hs.classList.add('hotspot-active'); hs.scrollIntoView({{behavior:'smooth', block:'center'}}); }}
                }}
                function leaveText(num) {{
                    document.querySelectorAll('.comp-' + num).forEach(el => el.classList.remove('highlight-active'));
                    const hs = document.getElementById('hotspot-' + num);
                    if(hs) hs.classList.remove('hotspot-active');
                }}
            </script>
            </body>
            </html>
            """
            components.html(html_skeleton, height=820, scrolling=False)
        else:
            st.image(cropped_img, use_container_width=True)

# ==========================================
# ⚖️ Tab 2：智權法務審查中心 (IP)
# ==========================================
with main_tab2:
    if not st.session_state.ip_report_content or not st.session_state.claim_data_t2:
        st.info("請先於上方上傳 PDF 並啟動分析。")
    else:
        st.markdown("## 🏛️ 智權法務審查工作站")
        ip_tab_report, ip_tab_claim = st.tabs(["📄 智權戰略深度報告 (含破口與地雷)", "⚖️ 請求項文義比對 (三視窗)"])
        
        with ip_tab_report:
            col_r1, col_r2 = st.columns([3, 1])
            with col_r1: st.markdown("以下為嚴格遵守指令生成的 11 項實務拆解報告：")
            with col_r2:
                st.download_button(
                    label="📥 下載 Word 報告",
                    data=create_word_doc(st.session_state.ip_report_content),
                    file_name=f"IP_Report_{st.session_state.active_patent_num}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True
                )
            with st.container(height=650, border=True):
                st.markdown(st.session_state.ip_report_content)
        
        with ip_tab_claim:
            components_list = st.session_state.claim_data_t2.get("components", [])
            if components_list:
                comp_options = {f"[{c.get('id','')}] {c.get('name','')}": c for c in components_list}
                col_sel, _ = st.columns([1, 1])
                with col_sel:
                    selected_comp = st.selectbox(f"🎯 選擇比對目標元件 (共 {len(components_list)} 個)：", list(comp_options.keys()), key="ip_comp_sel")
                    active_c = comp_options[selected_comp]
                
                st.markdown("<br>", unsafe_allow_html=True)
                col_i1, col_i2, col_i3 = st.columns([1.2, 1, 1.2])
                
                with col_i1:
                    st.markdown("### 🖼️ 專利圖面")
                    pdf_doc_ip = pdfium.PdfDocument(st.session_state.pdf_bytes_main)
                    pg_ip = st.number_input("頁碼", min_value=1, max_value=len(pdf_doc_ip), value=min(2, len(pdf_doc_ip)), key="ip_pg")
                    with st.container(height=600, border=True):
                        st.image(pdf_doc_ip[pg_ip - 1].render(scale=2.0).to_pil(), use_container_width=True)
                
                with col_i2:
                    st.markdown("### 🧩 獨立項文義")
                    with st.container(height=600, border=True):
                        for line in st.session_state.claim_data_t2.get("claims", []):
                            if active_c['name'] in line:
                                hl_line = line.replace(active_c['name'], f"<span style='background-color:#fff3cd; font-weight:bold; color:#856404; padding:2px 4px; border-radius:3px;'>{active_c['name']}</span>")
                                st.markdown(f"<div style='padding: 8px; border-bottom: 1px dashed #eee;'>{hl_line}</div>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"<div style='padding: 8px; border-bottom: 1px dashed #eee; color: #555;'>{line}</div>", unsafe_allow_html=True)

                with col_i3:
                    st.markdown("### 📖 說明書具體限制")
                    with st.container(height=600, border=True):
                        st.info(f"📍 目標：**{active_c['name']} ({active_c.get('id','')})**")
                        found_texts = [t for t in st.session_state.claim_data_t2.get('spec_texts', []) if active_c['name'] in t or active_c.get('id','') in t]
                        if not found_texts: st.warning("未找到說明。")
                        else:
                            for t in found_texts:
                                hl_t = t.replace(active_c['name'], f"<mark style='background-color:#cce5ff; color:#004085; font-weight:bold; padding:2px; border-radius:3px;'>{active_c['name']}</mark>")
                                st.markdown(f"<div style='background: #f8f9fa; padding: 10px; border-left: 4px solid #007bff; margin-bottom: 10px;'>{hl_t}</div>", unsafe_allow_html=True)

# ==========================================
# 🗺️ Tab 3：宏觀專利大數據與競爭快篩
# ==========================================
with main_tab3:
    st.markdown("雙軌解析摘要與請求項，產出技術功效矩陣，並建立**對手競爭前案快篩庫**。")
    uploaded_excel_t3 = st.file_uploader("請上傳從 TWPAT 匯出的 Excel (有效專利/競爭對手)", type=["xlsx", "xls", "csv"], key="excel_up_t3")

    if uploaded_excel_t3:
        try:
            df = pd.read_csv(uploaded_excel_t3) if uploaded_excel_t3.name.endswith('.csv') else pd.read_excel(uploaded_excel_t3)
            st.success(f"✅ 成功載入資料！共計 {len(df)} 筆專利。")
            
            sub_t1, sub_t2, sub_t3, sub_t4, sub_t5, sub_t6 = st.tabs(["🏢 競爭者佈局", "📈 演進趨勢", "🎯 IPC 熱區", "🧠 AI 技術功效矩陣", "🗄️ 競爭前案快篩庫", "👑 核心地雷探勘"])
            
            app_col = next((col for col in df.columns if '申請人' in col or '權人' in col), None)
            date_col = next((col for col in df.columns if '申請日' in col or '公開日' in col or '公告日' in col), None)
            ipc_col = next((col for col in df.columns if 'IPC' in col.upper()), None)
            title_col = next((col for col in df.columns if '專利名稱' in col or '標題' in col), None)
            abs_col = next((col for col in df.columns if '摘要' in col), None)
            num_col = next((col for col in df.columns if '號' in col and ('公開' in col or '公告' in col or '申請' in col)), None)
            claim_col = next((col for col in df.columns if '申請專利範圍' in col or '請求項' in col), None)

            with sub_t1:
                if app_col:
                    top_app = df[app_col].value_counts().reset_index().head(10)
                    top_app.columns = ['公司名稱', '專利數量']
                    st.plotly_chart(px.bar(top_app, x='專利數量', y='公司名稱', orientation='h', color='專利數量', color_continuous_scale='Blues').update_layout(yaxis={'categoryorder':'total ascending'}), use_container_width=True)

            with sub_t2:
                if date_col:
                    df['年份'] = df[date_col].astype(str).str[:4]
                    yt = df['年份'].value_counts().reset_index().sort_values('年份')
                    yt.columns = ['年份', '專利數量']
                    st.plotly_chart(px.line(yt[yt['年份'].str.isnumeric()], x='年份', y='專利數量', markers=True, line_shape='spline', color_discrete_sequence=['#ff7f0e']), use_container_width=True)

            with sub_t3:
                if ipc_col:
                    df['IPC_四階'] = df[ipc_col].apply(lambda x: str(x).split(';')[0].split('|')[0].split('(')[0].strip() if not pd.isna(x) else "未知")
                    ipc_d = df['IPC_四階'].value_counts().reset_index().head(15)
                    ipc_d.columns = ['IPC四階', '數量']
                    fig3 = px.pie(ipc_d, values='數量', names='IPC四階', hole=0.4)
                    fig3.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig3, use_container_width=True)

            with sub_t4:
                st.markdown("### 🧠 AI 自動生成：技術功效矩陣")
                if abs_col and title_col and num_col:
                    analyze_count = st.slider("選擇要投入 AI 矩陣分析的專利數量", 1, min(len(df), 30), min(len(df), 15), key="slider_t3")
                    if st.button("🚀 啟動雙軌解析", use_container_width=True, key="btn_mat_t3"):
                        with st.spinner("交叉比對摘要與請求項..."):
                            try:
                                sample_df = df.head(analyze_count)
                                p_data = "".join([f"[{str(row[num_col])}] {str(row[title_col])} | 摘要：{str(row[abs_col])[:300]} | 請求項：{str(row[claim_col])[:500] if claim_col else '無'}\n" for _, row in sample_df.iterrows()])
                                prompt = f'''輸出JSON。矩陣維度X:["提升散熱與冷卻", "提升燃燒與動力效率", "結構緊湊與輕量化", "降低震動與噪音", "改善潤滑與耐用度", "降低製造成本"]。維度Y:["汽缸本體與散熱片", "活塞曲軸", "氣門進排氣", "機油道水套", "燃油噴射點火", "引擎外殼", "煞車懸吊", "電控儀表"]。\n{{ "matrix": [{{"專利號": "XXX", "技術手段": "選項", "達成功效": "選項"}}], "top_patents": [{{"專利號": "XXX", "專利名稱": "XXX", "威脅度": "🔴極高/🟡中等", "入選理由": "..."}}] }}\n資料：{p_data}'''
                                res = model.generate_content(prompt)
                                cln = res.text.replace('```json','').replace('```','').strip()
                                st.session_state.ai_analysis_result = json.loads(cln[cln.find('{'):cln.rfind('}')+1])
                                st.success("✅ 解析完成！")
                            except: st.error("分析失敗")

                if st.session_state.ai_analysis_result:
                    st.plotly_chart(px.density_heatmap(pd.DataFrame(st.session_state.ai_analysis_result["matrix"]), y='技術手段', x='達成功效', text_auto=True, color_continuous_scale='Reds'), use_container_width=True)

            with sub_t5:
                st.markdown("### 🗄️ 競爭前案快篩庫 (Triage Database)")
                c_stat, c_clr = st.columns([4, 1])
                c_stat.info(f"🗄️ 目前累積： **{len(st.session_state.comp_database)}** 筆")
                if c_clr.button("🗑️ 清空", use_container_width=True, key="clr_comp_t3"): st.session_state.comp_database = []; st.rerun()

                if abs_col and title_col and num_col and app_col:
                    cs2, cb2 = st.columns([2, 1])
                    b_range = cs2.slider("批次快篩區間", 1, len(df), (1, min(15, len(df))), key="sl_c_t3")
                    if cb2.button("🤖 啟動快篩", use_container_width=True, key="btn_c_t3"):
                        with st.spinner("掃描對手專利..."):
                            try:
                                s_df = df.iloc[b_range[0]-1 : b_range[1]]
                                p_data_c = "".join([f"[{str(r[num_col])}] 公司：{str(r[app_col])} | {str(r[title_col])} | 摘要：{str(r[abs_col])[:250]}\n" for _, r in s_df.iterrows()])
                                prompt_c = f'''輸出JSON。分類:["引擎與動力", "傳動", "煞車", "車架懸吊", "電控儀表", "外觀其他"]。\n{{ "database": [{{"專利號": "XXX", "專利名稱": "XXX", "申請人": "XXX", "大分類": "選項", "特殊機構": "15字", "達成功效": "20字"}}] }}\n資料：{p_data_c}'''
                                res_c = model.generate_content(prompt_c)
                                cln_c = res_c.text.replace('```json','').replace('```','').strip()
                                new_db = json.loads(cln_c[cln_c.find('{'):cln_c.rfind('}')+1]).get("database", [])
                                ex_p = [p['專利號'] for p in st.session_state.comp_database]
                                for item in new_db:
                                    if item['專利號'] not in ex_p: st.session_state.comp_database.append(item)
                                st.success(f"匯入 {len(new_db)} 筆！")
                            except: st.error("失敗")

                if st.session_state.comp_database:
                    st.markdown("---")
                    c1, c2, c3 = st.columns(3)
                    f_com = c1.multiselect("🏢 篩選『對手公司』", list(set([i.get("申請人", "未知") for i in st.session_state.comp_database])), key="fc_t3")
                    f_sys = c2.multiselect("📂 篩選『系統分類』", ["引擎與動力", "傳動", "煞車", "車架懸吊", "電控儀表", "外觀其他"], key="fs_t3")
                    s_q = c3.text_input("🔍 關鍵字", key="sq_t3")

                    db_f = st.session_state.comp_database
                    if f_com: db_f = [i for i in db_f if i.get("申請人") in f_com]
                    if f_sys: db_f = [i for i in db_f if i.get("大分類") in f_sys]
                    if s_q: db_f = [i for i in db_f if s_q in str(i)]

                    for p in db_f:
                        with st.container(border=True):
                            st.markdown(f"**[{p.get('專利號')}] {p.get('專利名稱')}**")
                            sc1, sc2 = st.columns(2)
                            sc1.info(f"🏢 {p.get('申請人')}")
                            sc2.warning(f"📂 {p.get('大分類')}")
                            sc3, sc4 = st.columns(2)
                            sc3.error(f"⚙️ {p.get('特殊機構')}")
                            sc4.success(f"🎯 {p.get('達成功效')}")
                            st.markdown(f"👉 複製 `{p.get('專利號')}` 去 Tab 1/2 分析！")

            with sub_t6:
                st.markdown("### 👑 核心地雷探勘 (Killer Patents)")
                if st.session_state.ai_analysis_result:
                    for p in st.session_state.ai_analysis_result.get("top_patents", []):
                        with st.container(border=True):
                            c = "red" if "高" in p.get("威脅度", "") else "orange"
                            st.markdown(f"#### 🎯 [{p.get('專利號')}] {p.get('專利名稱')}")
                            st.markdown(f"**威脅度：** <span style='color:{c};font-weight:bold;'>{p.get('威脅度')}</span><br>**洞察：** {p.get('入選理由')}", unsafe_allow_html=True)

# ==========================================
# 💡 Tab 4：研發專屬彈藥庫 (Excel)
# ==========================================
with main_tab4:
    st.markdown("### 🛠️ 研發解題靈感與開源技術庫")
    up_rd = st.file_uploader("上傳 Excel (已篩選為失效專利)", type=["xlsx", "xls", "csv"], key="up_rd_t4")

    if up_rd:
        try:
            df_r = pd.read_csv(up_rd) if up_rd.name.endswith('.csv') else pd.read_excel(up_rd)
            st.success(f"✅ 載入 {len(df_r)} 筆。")
            t_col = next((c for c in df_r.columns if '標題' in c or '名稱' in c), None)
            a_col = next((c for c in df_r.columns if '摘要' in c), None)
            n_col = next((c for c in df_r.columns if '號' in c), None)
            c_col = next((c for c in df_r.columns if '請求項' in c or '範圍' in c), None)

            st.markdown("---")
            rs1, rs2 = st.columns([4, 1])
            rs1.info(f"🗄️ 彈藥庫累積： **{len(st.session_state.rd_database)}** 筆")
            if rs2.button("🗑️ 清空", use_container_width=True, key="c_rd_t4"): st.session_state.rd_database = []; st.rerun()

            if a_col and t_col and n_col:
                r_s, r_b = st.columns([2, 1])
                br_rd = r_s.slider("批次處理區間", 1, len(df_r), (1, min(15, len(df_r))), key="sl_rd_t4")
                if r_b.button("🤖 寫入彈藥庫", use_container_width=True, key="btn_rd_t4"):
                    with st.spinner("解讀專利中..."):
                        try:
                            s_df_r = df_r.iloc[br_rd[0]-1 : br_rd[1]]
                            pr_data = "".join([f"[{str(r[n_col])}] {str(r[t_col])} | 摘要：{str(r[a_col])[:250]}\n" for _, r in s_df_r.iterrows()])
                            pr_rd = f'''輸出JSON。分類:["引擎與動力系統", "傳動系統", "煞車系統", "車架與懸吊系統", "電系與儀表控制", "外觀件與其他"]。\n{{ "database": [{{"專利號": "XXX", "專利名稱": "XXX", "大分類": "選項", "特殊機構": "15字", "達成功效": "20字", "核心解法": "白話文原理"}}] }}\n資料：{pr_data}'''
                            res_rd = model.generate_content(pr_rd)
                            cln_rd = res_rd.text.replace('```json','').replace('```','').strip()
                            new_rdb = json.loads(cln_rd[cln_rd.find('{'):cln_rd.rfind('}')+1]).get("database", [])
                            ex_rp = [p['專利號'] for p in st.session_state.rd_database]
                            for item in new_rdb:
                                if item['專利號'] not in ex_rp: st.session_state.rd_database.append(item)
                            st.success(f"寫入 {len(new_rdb)} 筆！")
                        except: st.error("失敗")

            if st.session_state.rd_database:
                st.markdown("---")
                rc1, rc2 = st.columns(2)
                f_rcat = rc1.multiselect("🏷️ 『大分類』", ["引擎與動力系統", "傳動系統", "煞車系統", "車架與懸吊系統", "電系與儀表控制", "外觀件與其他"], key="f_rc_t4")
                s_rq = rc2.text_input("🎯 關鍵字搜尋", key="sq_r_t4")

                db_r = st.session_state.rd_database
                if f_rcat: db_r = [i for i in db_r if i.get("大分類") in f_rcat]
                if s_rq: db_r = [i for i in db_r if s_rq in str(i)]

                for p in db_r:
                    with st.container(border=True):
                        st.markdown(f"**[{p.get('專利號')}] {p.get('專利名稱')}**")
                        st.markdown("🟢 **【開源技術庫：免授權直接參考】**")
                        t1, t2, t3 = st.columns(3)
                        t1.info(f"📂 {p.get('大分類')}")
                        t2.warning(f"⚙️ {p.get('特殊機構')}")
                        t3.error(f"🎯 {p.get('達成功效')}")
                        st.markdown(f"> **💡 核心解法：** {p.get('核心解法')}")
        except: st.error("檔案讀取失敗")
