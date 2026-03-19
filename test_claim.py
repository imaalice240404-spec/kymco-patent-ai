import os
import json
import random 
import streamlit as st
import google.generativeai as genai
import tempfile
import pypdfium2 as pdfium
import base64
import streamlit.components.v1 as components
import io 
from PIL import Image, ImageOps

# ==========================================
# 🛑 核心配置與 API 初始化 (原碼移植)
# ==========================================
st.set_page_config(page_title="機車專利迴避設計戰情室", layout="wide")

# 👇 建立 API 鑰匙池
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# 🌟 初始化系統記憶體 (原碼移植 + 新增 RD 卡記憶)
if 'claim_data' not in st.session_state: st.session_state.claim_data = None
if 'pdf_bytes' not in st.session_state: st.session_state.pdf_bytes = None 
if 'scanned_pages' not in st.session_state: st.session_state.scanned_pages = {} # 座標快取
if 'rd_patent_card' not in st.session_state: st.session_state.rd_patent_card = None # 新增：存放 RD 分析文字
if 'fto_result' not in st.session_state: st.session_state.fto_result = None # 新增：存放 FTO 判定

# --- 簡易影像處理：自動裁切白邊 (原碼移植) ---
def crop_white_margins(img):
    if img.mode != 'RGB':
        img = img.convert('RGB')
    inv = ImageOps.invert(img)
    bbox = inv.getbbox()
    if bbox:
        padded_bbox = (max(0, bbox[0]-20), max(0, bbox[1]-20), min(img.width, bbox[2]+20), min(img.height, bbox[3]+20))
        return img.crop(padded_bbox)
    return img

# ==========================================
# 🧱 畫面介面大重組 (理想排版實作)
# ==========================================
st.title("🏍️ 機車專利迴避設計戰情室 (Tab 1 理想版)")
st.markdown("---")

# 利用 columns 將畫面分為左右兩大支柱
col_left_strategy, col_right_visual = st.columns([1.2, 1])

# ==========================================
# 👈 左支柱：設定與研發戰略卡
# ==========================================
with col_left_strategy:
    st.subheader("1️⃣ 案件資訊與 PDF 上傳")
    
    # --- 附圖中的設定區域 ---
    col_input1, col_input2 = st.columns(2)
    with col_input1:
        applicant = st.text_input("申請人 (對手公司)", placeholder="例如：光陽工業")
        patent_num = st.text_input("專利號", placeholder="例如：I856744")
        if patent_num:
            # 模擬 Google Patents 連結 (A碼功能保留)
            google_patents_url = f"https://patents.google.com/patent/TW{patent_num}B"
            st.markdown(f"👉 [傳送門：Google Patents 查看 **{patent_num}** 原件]({google_patents_url})")
            
    with col_input2:
        # 新型/發明會影響 Prompt (A碼功能)
        is_utility_model = st.toggle("這是「新型」專利 (未經實審)", value=False)
        status = st.selectbox("目前案件狀態", ["請選擇...", "公開", "公告/核准", "撤回/消滅"])

    # PDF 上傳 (原碼移植位置調整)
    uploaded_pdf = st.file_uploader("📥 上傳專利 PDF 檔", type=["pdf"])

    run_analysis = st.button("🚀 啟動 PDF 視覺化與研發深度解剖", use_container_width=True, type="primary")

    # --- 🌟 AI 分析邏輯 (整合核心) ---
    if run_analysis:
        if uploaded_pdf is None or patent_num == "" or status == "請選擇...":
            st.warning("⚠️ 請確認專利 PDF 已上傳，且專利號與狀態已設定！")
        else:
            # 更新 Session State
            st.session_state.pdf_bytes = uploaded_pdf.getvalue()
            st.session_state.scanned_pages = {} # 清空舊快取
            
            with st.spinner("大腦正在深挖技術與地雷，請稍候約 30 秒..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                        tmp_file.write(st.session_state.pdf_bytes)
                        tmp_file_path = tmp_file.name
                    gemini_file = genai.upload_file(tmp_file_path)

                    # 🌟 [Prompt 大升級] 強制 AI 同時輸出法律比對用 JSON 與研發專屬 Patent Card
                    patent_type_str = "新型專利 (未經實審，僅保護構造)" if is_utility_model else "發明專利 (經過實審，保護範圍較廣)"
                    prompt_master = f"""
                    你現在是一位資深機車專利代理人與研發主管。請閱讀這份PDF全文。
                    申請人：{applicant} / 目前法律狀態：{status} / 專利類型：{patent_type_str}

                    【⚠️ 指令 1：法律比對用 JSON】
                    將內容轉化為結構化的 JSON 格式 (原 V4 沙盒任務)：提取完整「符號字典」、將「所有請求項」逐項逐句拆解、提取「實施方式」文本 (含段落編號)。

                    【⚠️ 指令 2：研發戰略用 Patent Card】
                    從 PDF 內容中提煉出以下資訊：技術命名、解決痛點、核心解法(白話文機構原理解釋)、3-5個核心關鍵字、應用場景(例如：速克達、重機)。

                    【🔴 絕對指令：輸出純 JSON 格式】
                    嚴格符合以下結構，不要輸出 Markdown 標記：
                    {{
                      "visual_比對_data": {{
                        "claims": ["1. 一種機車，包含：", "一車架10；"],
                        "components": [ {{"id": "10", "name": "車架"}} ],
                        "spec_texts": ["【0015】如圖1所示..."]
                      }},
                      "rd_patent_card": {{
                        "title": "...",
                        "problem": "...",
                        "solution": "用工程師聽得懂的白話文解釋其特殊機構如何解決問題...",
                        "keywords": "...",
                        "application": "...",
                        "constraints_checklist": ["獨立項特徵1", "獨立項特徵2", "獨立項特徵3"]
                      }},
                      "fto_status": {{
                        "stoplight": "🔴/🟡/🟢",
                        "reason": "..."
                      }}
                    }}
                    """
                    
                    response = model.generate_content([gemini_file, prompt_master])
                    clean_text = response.text.replace('```json', '').replace('```', '').strip()
                    clean_text = clean_text[clean_text.find('{'):clean_text.rfind('}')+1]
                    master_data = json.loads(clean_text)
                    
                    # 派發數據到 Session State
                    st.session_state.claim_data = master_data.get("visual_比對_data")
                    st.session_state.rd_patent_card = master_data.get("rd_patent_card")
                    st.session_state.fto_result = master_data.get("fto_status")
                    
                    st.success("✅ 視覺化連動與研發深度解剖完成！")
                    os.remove(tmp_file_path)
                    genai.delete_file(gemini_file.name)
                    st.rerun() # 重新渲染以載入數據
                    
                except Exception as e:
                    st.error(f"分析失敗，請檢查 API KEY 或 PDF 內容。錯誤：{e}")

    # --- 附圖左下：🚀 RD 專屬十秒專利卡 ---
    st.markdown("---")
    if st.session_state.rd_patent_card:
        card = st.session_state.rd_patent_card
        st.subheader("🚀 RD 專屬十秒專利卡 (Patent Card)")
        
        with st.container(border=True):
            st.markdown(f"**📝 Title (技術命名)**：{card.get('title', 'N/A')}")
            st.markdown(f"**🔥 Problem (解決痛點)**：{card.get('problem', 'N/A')}")
            st.markdown(f"**💡 Solution (核心解法)**：\n> {card.get('solution', 'N/A')}")
            
            c1, c2 = st.columns(2)
            c1.markdown(f"**🏷️ Key Elements (關鍵字)**：\n`{card.get('keywords', 'N/A')}`")
            c2.markdown(f"**🎯 Application (應用場景)**：\n{card.get('application', 'N/A')}")
            
            # --- 附圖：⚔️ 侵權風險視覺化 (自家技術對比清單) ---
            st.markdown("---")
            st.markdown("#### ⚔️ 自家技術 CheckBox 對比清單")
            st.caption("AI 已自動拆解獨立項最嚴格之特徵。請勾選我司技術**是否具備**該特徵 (✔全選=🔴侵權)：")
            
            checks = card.get('constraints_checklist', [])
            checked_count = 0
            for i, check in enumerate(checks):
                # 利用 st.checkbox 模擬附圖的✔
                if st.checkbox(f"**特徵限制**：{check}", key=f"risk_check_{i}"):
                    checked_count += 1
            
            # 簡易 FTO 判定邏輯 (全要件原則)
            total_checks = len(checks)
            if total_checks > 0:
                if checked_count == total_checks:
                    st.error(f"🔴 風險警告：命中 {checked_count}/{total_checks} 個權利限制特徵 (文義侵權風險極高)。建議立即進行迴避設計。")
                elif checked_count > 0:
                    st.warning(f"🟡均等論風險：命中 {checked_count}/{total_checks} 個特徵。雖然文義未讀取，但具備等效性質，需法律判斷。")
                else:
                    st.success("🎉 安全安全：自家技術全數避開對手特徵。迴避設計成功。")
            
    else:
        st.info("啟動 AI 分析後，這裡將呈現 R&D 專屬戰略專利卡。")

# ==========================================
# 👉 右支柱：🚦 FTO 風險判定 & 🎯 視覺化大屏
# ==========================================
with col_right_visual:
    # --- 附圖右上：🚦 FTO 風險判定 ---
    st.subheader("🚦 宏觀 FTO 風險燈號")
    if st.session_state.fto_result:
        fto = st.session_state.fto_result
        light = fto.get("stoplight", "🟢")
        
        # 影像化的燈號呈現 (原碼無此功能，為理想排版新增)
        if light == "🔴": col1, col2 = st.columns([1, 4]); col1.error("<h1>🔴</h1>", unsafe_allow_html=True); col2.markdown(f"**紅燈：具威脅**\n{fto.get('reason')}")
        elif light == "🟡": col1, col2 = st.columns([1, 4]); col1.warning("<h1>🟡</h1>", unsafe_allow_html=True); col2.markdown(f"**黃燈：需注意**\n{fto.get('reason')}")
        else: col1, col2 = st.columns([1, 4]); col1.success("<h1>🟢</h1>", unsafe_allow_html=True); col2.markdown(f"**綠燈：低風險**\n{fto.get('reason')}")
    else:
        st.info("啟動 AI 分析後，Gemini 將給出 FTO 燈號判定。")

    st.markdown("---")
    
    # ==========================================
    # 🎯 終極雙向連動大屏 (您原碼的 V4 沙盒功能)
    # ==========================================
    if st.session_state.claim_data and st.session_state.pdf_bytes:
        # st.markdown("### 🎯 研發終極迴避大屏") # 標題與 FTO 合併，省略
        
        # 使用 pypdfium2 處理 State 中的二進位資料
        pdf_doc_v = pdfium.PdfDocument(st.session_state.pdf_bytes)
        total_pages = len(pdf_doc_v)

        # 頁碼選擇器 (原碼位置調整)
        target_page = st.number_input(f"📄 選擇專利圖紙頁碼 (共 {total_pages} 頁)", min_value=1, max_value=total_pages, value=min(2, total_pages), key="vis_page_rd")
        
        # 即時預覽並裁切白邊
        page = pdf_doc_v[target_page - 1]
        raw_pil_img = page.render(scale=2.0).to_pil()
        cropped_img = crop_white_margins(raw_pil_img) # 🌟 魔法：裁掉無用白邊
        
        # 將裁切後的圖片轉 Base64
        img_byte_arr = io.BytesIO()
        cropped_img.save(img_byte_arr, format='JPEG')
        encoded_img = base64.b64encode(img_byte_arr.getvalue()).decode()
        img_uri = f"data:image/jpeg;base64,{encoded_img}"

        # 檢查快取 (原碼移植)
        is_scanned = str(target_page) in st.session_state.scanned_pages
        
        # 如果尚未掃描，呈現預覽與「視覺掃描」按鈕
        if not is_scanned:
            st.image(cropped_img, use_container_width=True, caption=f"第 {target_page} 頁預覽 (尚未視覺掃描)")
            run_scan = st.button(f"🔍 啟動 Gemini 視覺掃描第 {target_page} 頁 (僅需掃描一次)", use_container_width=True, key="btn_scan_rd")
            
            if run_scan:
                with st.spinner("🧠 Gemini Vision 正在鎖定畫面上的所有標號座標..."):
                    try:
                        # 拿之前的解析數據來用
                        comp_dict_list = st.session_state.claim_data.get("components", [])
                        known_comps_str = json.dumps(comp_dict_list, ensure_ascii=False)

                        prompt_vision = f"""
                        這是一張機車專利圖式。已知本專利的部分元件對應表為：{known_comps_str}
                        找出圖片上「所有肉眼可見的數字標號」。如果在對應表中，填寫 name；沒有則填 "未知"。
                        估算該標號的「相對中心座標」(0.0~1.0)。
                        嚴格輸出 JSON：
                        {{ "hotspots": [ {{"number": "31", "name": "汽缸頭", "x_rel": 0.45, "y_rel": 0.55}} ] }}
                        """
                        # 送出被裁切過的圖片 (原碼邏輯)
                        response_vis = model.generate_content([cropped_img, prompt_vision])
                        clean_text_vis = response_vis.text.replace('```json', '').replace('```', '').strip()
                        clean_text_vis = clean_text_vis[clean_text_vis.find('{'):clean_text_vis.rfind('}')+1]
                        ai_visual_data = json.loads(clean_text_vis).get("hotspots", [])

                        # 🌟 將結果寫入記憶體快取
                        st.session_state.scanned_pages[str(target_page)] = ai_visual_data
                        st.rerun() # 重新整理畫面載入快取
                    except Exception as e:
                        st.error(f"視覺解析失敗：{e}")

        # ==== 🌟 終極整合：JS 雙向連動 HTML (原碼移植) ====
        if is_scanned:
            ai_visual_data = st.session_state.scanned_pages[str(target_page)]
            comp_dict_list = st.session_state.claim_data.get("components", [])
            
            # 準備請求項文字 (原碼邏輯)
            claim_lines = st.session_state.claim_data.get("claims", [])
            claim_text_full = "<br><br>".join(claim_lines)
            
            # 1. 預處理右側文字：加入 JS 雙向觸發事件
            for comp in comp_dict_list:
                comp_num = comp["id"]
                comp_name = comp["name"]
                replacement = f'<span class="comp-text comp-{comp_num}" onmouseover="hoverText(\'{comp_num}\')" onmouseout="leaveText(\'{comp_num}\')">{comp_name} ({comp_num})</span>'
                # 簡單替換 (原碼邏輯，實務上可用 Regex 優化)
                claim_text_full = claim_text_full.replace(comp_name, replacement)
            
            # 2. 生成圖片熱區 HTML (原碼邏輯)
            hotspots_html = ""
            for spot in ai_visual_data:
                # 只亮在元件字典裡的標號 (原碼無此邏輯，為研發大屏優化)
                if spot['name'] != "未知":
                    hotspots_html += f"""
                    <div class="hotspot hotspot-marker-{spot['number']}" id="hotspot-{spot['number']}"
                         style="left: {spot['x_rel']*100}%; top: {spot['y_rel']*100}%;"
                         onmouseover="hoverImage('{spot['number']}', '{spot['name']}')" 
                         onmouseout="leaveImage('{spot['number']}')">
                    </div>
                    """

            # 3. 雙向連動專屬 HTML/JS 骨架 (原碼移植，高度调整)
            # 注意：這裡的大括號要雙重 "{{ }}" 來跳脫 Streamlit f-string
            html_v_skeleton = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
                body {{ margin: 0; font-family: sans-serif; background: white; }}
                .main-container {{ display: flex; height: 750px; width: 100%; border: 1px solid #ddd; overflow: hidden; }}
                
                /* 左側大圖區 */
                .img-section {{ flex: 6; position: relative; overflow: auto; background: #e0e0e0; border-right: 2px solid #ddd; display: flex; justify-content: center; align-items: flex-start; padding: 10px; }}
                .img-wrapper {{ position: relative; display: inline-block; }}
                .patent-img {{ max-width: 100%; height: auto; display: block; }}
                
                /* 透明熱區 (原碼 CSS) */
                .hotspot {{ position: absolute; width: 35px; height: 35px; transform: translate(-50%, -50%); border-radius: 50%; cursor: pointer; transition: 0.2s; border: 2px solid transparent; z-index: 10; }}
                .hotspot:hover {{ background: rgba(255, 0, 0, 0.3); border: 2px solid red; box-shadow: 0 0 10px rgba(255,0,0,0.5); z-index: 50; }}
                /* 🌟 文字反向觸發特效 (原碼移植) */
                .hotspot-active {{ background: rgba(255, 255, 0, 0.6) !important; border: 3px solid red !important; box-shadow: 0 0 20px red !important; transform: translate(-50%, -50%) scale(1.3); z-index: 50; }}
                
                #tooltip {{ display: none; position: absolute; background: rgba(0, 0, 0, 0.8); color: white; padding: 6px 12px; border-radius: 4px; font-size: 13px; z-index: 100; pointer-events: none; white-space: nowrap; }}
                
                /* 右側文字區 */
                .text-section {{ flex: 4; padding: 20px; overflow-y: auto; font-size: 15px; line-height: 1.7; color: #333; background: #fafafa; }}
                .claim-title {{ font-size: 18px; font-weight: bold; margin-bottom: 15px; color: #1e3a8a; border-bottom: 2px solid #eee; padding-bottom: 8px; position: sticky; top: 0; background: #fafafa; z-index: 10; }}
                
                /* 文字連動效果 (原碼 CSS) */
                .comp-text {{ transition: 0.2s; border-radius: 3px; padding: 0 2px; border-bottom: 1px dotted #ccc; cursor: pointer; color: #0066cc; font-weight: bold; }}
                .comp-text:hover {{ background-color: #ffcccc; }} 
                .highlight-active {{ background-color: #ffeb3b; color: #b91c1c; font-weight: bold; display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.2); border-bottom: none; }}
            </style>
            </head>
            <body>

            <div class="main-container">
                <div class="img-section" id="img-container">
                    <div class="img-wrapper" id="img-wrapper">
                        <img src="{img_uri}" class="patent-img">
                        {hotspots_html}
                    </div>
                    <div id="tooltip"></div>
                </div>
                
                <div class="text-section">
                    <div class="claim-title">🎯 技術特徵連動比對</div>
                    <div id="claim-content">
                        {claim_text_full}
                    </div>
                </div>
            </div>

            <script>
                const tooltip = document.getElementById('tooltip');

                // 📌 動作一：滑鼠指圖片 ➔ 亮右邊文字 (原碼移植)
                function hoverImage(num, name) {{
                    document.onmousemove = function(e) {{
                        tooltip.style.left = (e.pageX + 15) + 'px';
                        tooltip.style.top = (e.pageY + 15) + 'px';
                    }};
                    tooltip.innerHTML = "標號 <b>" + num + "</b> : " + name;
                    tooltip.style.display = 'block';

                    const targets = document.querySelectorAll('.comp-' + num);
                    targets.forEach((el, index) => {{
                        el.classList.add('highlight-active');
                        // 自動捲動到最上面那個文字
                        if (index === 0) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    }});
                }}

                function leaveImage(num) {{
                    document.onmousemove = null;
                    tooltip.style.display = 'none';
                    document.querySelectorAll('.comp-' + num).forEach(el => el.classList.remove('highlight-active'));
                }}

                // 📌 動作二：滑鼠指右邊文字 ➔ 爆亮左邊圖片標號 (原碼移植)
                function hoverText(num) {{
                    //自己亮起
                    document.querySelectorAll('.comp-' + num).forEach(el => el.classList.add('highlight-active'));

                    //通知左邊熱區
                    const hotspot = document.getElementById('hotspot-' + num);
                    if (hotspot) {{
                        hotspot.classList.add('hotspot-active');
                        //圖太大的話自動捲動到對應點
                        hotspot.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    }}
                }}

                function leaveText(num) {{
                    document.querySelectorAll('.comp-' + num).forEach(el => el.classList.remove('highlight-active'));
                    const hotspot = document.getElementById('hotspot-' + num);
                    if (hotspot) hotspot.classList.remove('hotspot-active');
                }}
            </script>
            </body>
            </html>
            """
            components.html(html_v_skeleton, height=760, scrolling=False)
    
    else:
        st.info("請於左側設定案件並按下「啟動」後，這裡將呈現雙向連動的研發大屏。")
