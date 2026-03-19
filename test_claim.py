import os
import json
import random 
import streamlit as st
import google.generativeai as genai
import tempfile
import pypdfium2 as pdfium
import base64  # 🌟 新增：處理圖片編碼
import streamlit.components.v1 as components  # 🌟 新增：渲染 HTML 元件

# 👇 建立 API 鑰匙池 (保持原樣)
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

st.set_page_config(page_title="Claim Construction 沙盒 V2", layout="wide")

if 'claim_data' not in st.session_state:
    st.session_state.claim_data = None

# --- 簡易密碼門禁 (保持原樣) ---
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
st.markdown("整合 Gemini AI 深度解析與**前端沉浸式圖文連動**技術。")
st.markdown("---")

uploaded_pdf = st.file_uploader("📥 第一步：請上傳一份專利 PDF 檔 (供 AI 解析用)", type=["pdf"])

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

                # 🌟 終極 Prompt (保持原樣)
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
                
                st.success("✅ 全本字典建構完成！請前往下方頁籤查看成果。")

                os.remove(tmp_file_path)
                genai.delete_file(gemini_file.name)
            except Exception as e:
                st.error(f"分析失敗，可能是 PDF 過大或格式問題：{e}")

# ==========================================
# 實務級展示區 (改為頁籤模式)
# ==========================================
if st.session_state.claim_data:
    st.markdown("---")
    
    # 🌟 建立功能切換頁籤
    tab_workspace, tab_immersive = st.tabs(["⚖️ 實務級三聯屏", "🎯 沉浸式圖文連動 (測試區)"])

    # --- 頁籤一：你原本的工作站內容 ---
    with tab_workspace:
        components_list = st.session_state.claim_data.get("components", [])
        if components_list:
            # 🌟 建立超完整的元件選擇器
            comp_options = {f"[{c['id']}] {c['name']}": c for c in components_list}
            
            col_select, col_empty = st.columns([1, 1])
            with col_select:
                selected_comp_label = st.selectbox(f"🎯 選擇要追蹤的比對目標 (已成功載入 {len(components_list)} 個元件)：", list(comp_options.keys()))
                active_comp = comp_options[selected_comp_label]
            
            st.markdown("<br>", unsafe_allow_html=True)
            col_img, col_claim, col_spec = st.columns([1.2, 1, 1.2])
            
            with col_img:
                st.markdown("### 🖼️ 專利圖面檢視")
                if uploaded_pdf:
                    pdf_doc = pdfium.PdfDocument(uploaded_pdf.getvalue())
                    total_pages = len(pdf_doc)
                    page_num = st.number_input(f"跳至頁碼 (共 {total_pages} 頁)", min_value=1, max_value=total_pages, value=min(2, total_pages), key="workspace_page")
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
                    
                    spec_texts = st.session_state.claim_data.get('spec_texts', [])
                    found_texts = [text for text in spec_texts if active_comp['name'] in text or active_comp['id'] in text]
                    
                    if not found_texts:
                        st.warning(f"在實施方式中，未找到針對「{active_comp['name']}」的進一步描述文字。")
                    else:
                        for text in found_texts:
                            highlighted_text = text.replace(active_comp['name'], f"<mark style='background-color: #cce5ff; color: #004085; font-weight: bold; padding: 2px 4px; border-radius: 3px;'>{active_comp['name']}</mark>")
                            st.markdown(f"<div style='background-color: #f8f9fa; padding: 12px; border-left: 5px solid #007bff; margin-bottom: 15px; line-height: 1.6;'>{highlighted_text}</div>", unsafe_allow_html=True)

    # --- 頁籤二：🌟 新增的沉浸式連動測試區 ---
    with tab_immersive:
        st.markdown("### 🎯 沉浸式圖文連動解析 (Proof of Concept)")
        st.markdown("請上傳一張專利圖式的 **圖片檔 (PNG/JPG)**，然後點擊生成，體驗「圖上Hover，文中高亮」的效果。")

        col_v1, col_v2 = st.columns([2, 1])
        with col_v1:
            # 測試用：手動上傳單張圖片
            uploaded_img_t5 = st.file_uploader("🖼️ 第二步：上傳對應的專利圖紙圖片 (PNG/JPG)", type=["png", "jpg", "jpeg"], key="vis_upload_t5")
        
        with col_v2:
            st.write("") # 調整位置用
            st.write("")
            run_vis = st.button("🌟 生成沉浸式互動視窗", use_container_width=True, key="btn_run_t5")

        if run_vis and uploaded_img_t5:
            with st.spinner("正在封裝前端互動模組..."):
                # 1. 處理圖片編碼
                img_bytes = uploaded_img_t5.getvalue()
                encoded_img = base64.b64encode(img_bytes).decode()
                img_uri = f"data:image/jpeg;base64,{encoded_img}"

                # 2. 獲取請求項文字與元件字典
                claim_lines = st.session_state.claim_data.get("claim_1", [])
                claim_text_full = "<br><br>".join(claim_lines)
                comp_dict_list = st.session_state.claim_data.get("components", [])
                
                # 3. 預處理右側文字：包裝上 <span> 標籤
                for comp in comp_dict_list:
                    comp_num = comp["id"]
                    comp_name = comp["name"]
                    # ⚠️ 關鍵：這裡只處理有編號的元件，且避免重複處理
                    # 使用 CSS class 標記數字編號，例如 class='comp-text comp-32'
                    replacement = f'<span class="comp-text comp-{comp_num}">{comp_name} ({comp_num})</span>'
                    claim_text_full = claim_text_full.replace(comp_name, replacement)
                
                # 4. 🌟 MOCK DATA：測試用座標 (實務上這裡會是 Gemini Vision 回傳的 JSON)
                # 我設定了三個座標點 (百分比)，你可以修改這些數字來測試不同位置
                mock_visual_data = [
                    {"number": "32", "name": "汽缸蓋", "x_rel": 0.45, "y_rel": 0.15}, # 紅圈處
                    {"number": "31", "name": "汽缸頭", "x_rel": 0.45, "y_rel": 0.55},
                    {"number": "313", "name": "安裝孔", "x_rel": 0.90, "y_rel": 0.40}
                ]

                # 5. 生成 HTML 熱區 (Hotspots)
                hotspots_html = ""
                for spot in mock_visual_data:
                    hotspots_html += f"""
                    <div class="hotspot" 
                         style="left: {spot['x_rel']*100}%; top: {spot['y_rel']*100}%;"
                         onmouseover="highlight('{spot['number']}', '{spot['name']}')" 
                         onmouseout="removeHighlight('{spot['number']}')">
                    </div>
                    """

                # 6. 終極 HTML/CSS/JS 封裝
                html_skeleton = f"""
                <!DOCTYPE html>
                <html>
                <head>
                <style>
                    body {{ margin: 0; font-family: sans-serif; background: #f0f2f6; }}
                    .main-container {{ display: flex; height: 850px; width: 100%; border-radius: 8px; overflow: hidden; background: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                    
                    /* 左側大圖區 */
                    .img-section {{ flex: 6; position: relative; overflow: auto; background: #e0e0e0; border-right: 2px solid #ddd; display: flex; justify-content: center; align-items: flex-start; padding: 10px; }}
                    .img-wrapper {{ position: relative; display: inline-block; }}
                    .patent-img {{ max-width: 100%; height: auto; }}
                    
                    /* 透明熱區 */
                    .hotspot {{ position: absolute; width: 45px; height: 45px; transform: translate(-50%, -50%); border-radius: 50%; cursor: pointer; transition: 0.2s; }}
                    .hotspot:hover {{ background: rgba(255, 0, 0, 0.3); border: 2px solid red; box-shadow: 0 0 10px rgba(255,0,0,0.5); }}
                    
                    /* Tooltip */
                    #tooltip {{ display: none; position: absolute; background: rgba(0, 0, 0, 0.8); color: white; padding: 6px 12px; border-radius: 4px; font-size: 14px; z-index: 100; pointer-events: none; white-space: nowrap; }}
                    
                    /* 右側文字區 */
                    .text-section {{ flex: 4; padding: 30px; overflow-y: auto; font-size: 16px; line-height: 1.8; color: #333; }}
                    .claim-title {{ font-size: 22px; font-weight: bold; margin-bottom: 20px; color: #1e3a8a; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
                    
                    /* 高亮特效 */
                    .comp-text {{ transition: 0.3s; border-radius: 3px; padding: 0 2px; }}
                    .highlight-active {{ background-color: #ffeb3b; color: #b91c1c; font-weight: bold; transform: scale(1.05); display: inline-block; }}
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
                        <div class="claim-title">📜 請求項 1 文義解析</div>
                        <div id="claim-content">
                            {claim_text_full}
                        </div>
                    </div>
                </div>

                <script>
                    const tooltip = document.getElementById('tooltip');

                    function highlight(num, name) {{
                        // 1. Tooltip 跟隨滑鼠
                        document.onmousemove = function(e) {{
                            tooltip.style.left = (e.pageX + 15) + 'px';
                            tooltip.style.top = (e.pageY + 15) + 'px';
                        }};
                        tooltip.innerHTML = "標號 <b>" + num + "</b> : " + name;
                        tooltip.style.display = 'block';

                        // 2. 高亮右側文字並滾動
                        const targets = document.querySelectorAll('.comp-' + num);
                        targets.forEach(el => {{
                            el.classList.add('highlight-active');
                            // 平滑滾動到視窗中央
                            el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }});
                    }}

                    function removeHighlight(num) {{
                        document.onmousemove = null;
                        tooltip.style.display = 'none';
                        
                        const targets = document.querySelectorAll('.comp-' + num);
                        targets.forEach(el => {{
                            el.classList.remove('highlight-active');
                        }});
                    }}
                </script>
                </body>
                </html>
                """
                # 7. 渲染 HTML
                components.html(html_skeleton, height=880, scrolling=False)

        elif run_vis and not uploaded_img_t5:
            st.warning("⚠️ 請上傳圖片檔案，並確保【頁籤一】已有 AI 解析資料。")
