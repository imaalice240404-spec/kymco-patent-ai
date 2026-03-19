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
from PIL import Image, ImageOps # 🌟 新增：影像處理套件

# 👇 建立 API 鑰匙池
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

st.set_page_config(page_title="Claim Construction 沙盒 V4", layout="wide")

# 🌟 初始化系統記憶體 (新增了 scanned_pages 快取)
if 'claim_data' not in st.session_state:
    st.session_state.claim_data = None
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None 
if 'scanned_pages' not in st.session_state:
    st.session_state.scanned_pages = {} # 記錄已掃描過的圖紙與座標

# --- 簡易影像處理：自動裁切白邊 ---
def crop_white_margins(img):
    if img.mode != 'RGB':
        img = img.convert('RGB')
    # 反轉顏色，讓白底變黑底，這樣 getbbox 才能抓到非黑色的圖形範圍
    inv = ImageOps.invert(img)
    bbox = inv.getbbox()
    if bbox:
        # 為了不要切太齊，外圍加一點點 padding
        padded_bbox = (max(0, bbox[0]-20), max(0, bbox[1]-20), min(img.width, bbox[2]+20), min(img.height, bbox[3]+20))
        return img.crop(padded_bbox)
    return img

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

st.title("⚖️ 請求項文義解析工作站 (V4 雙向連動版)")
st.markdown("雙向互動：滑鼠指圖片 ➔ 文字高亮；**滑鼠指文字 ➔ 圖片標號螢光標示！**")
st.markdown("---")

uploaded_pdf = st.file_uploader("📥 第一步：請上傳專利 PDF 檔", type=["pdf"])

if st.button("🤖 啟動精細拆解 (建立全文本與全元件字典)", use_container_width=True):
    if uploaded_pdf is None:
        st.warning("⚠️ 請先上傳 PDF 檔案！")
    else:
        st.session_state.pdf_bytes = uploaded_pdf.getvalue()
        # 只要重新上傳，就清空過去的圖紙快取
        st.session_state.scanned_pages = {} 
        
        with st.spinner("大腦正在建立全本專利的「符號字典」與「所有請求項」... (約需 20 秒)"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(st.session_state.pdf_bytes)
                    tmp_file_path = tmp_file.name

                gemini_file = genai.upload_file(tmp_file_path)

                prompt = '''
                你現在是一個精準的專利資料庫解析系統。請閱讀這份專利，並將內容轉化為結構化的 JSON 格式。
                【任務 1】提取「符號說明」段落中【每一個】元件符號跟名稱。
                【任務 2】將「所有請求項」逐項、逐句拆解為陣列。
                【任務 3】提取「實施方式」所有段落。
                【🔴 絕對指令：輸出純 JSON 格式】
                嚴格符合以下結構：
                {
                  "claims": ["1. 一種機車，包含：", "一車架10；"],
                  "components": [{"id": "10", "name": "車架"}],
                  "spec_texts": ["【0015】如圖1所示..."]
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
                st.error(f"分析失敗，錯誤：{e}")

# ==========================================
# 實務級展示區
# ==========================================
if st.session_state.claim_data and st.session_state.pdf_bytes:
    st.markdown("---")
    
    tab_workspace, tab_immersive = st.tabs(["⚖️ 實務級三聯屏", "🎯 終極雙向連動大屏"])

    # --- 頁籤一：實務工作站 (保持原樣) ---
    with tab_workspace:
        st.write("已進入舊版比對模式 (省略，供參照)。")
        pass 

    # --- 頁籤二：🌟 終極自動化沉浸式雙向連動 ---
    with tab_immersive:
        pdf_doc_v = pdfium.PdfDocument(st.session_state.pdf_bytes)
        total_pages = len(pdf_doc_v)

        col_v1, col_v2 = st.columns([1, 2])
        with col_v1:
            target_page = st.number_input(f"📄 選擇要分析的專利圖紙頁碼 (共 {total_pages} 頁)", min_value=1, max_value=total_pages, value=min(2, total_pages), key="vis_page_select")
            
            # 即時預覽並裁切白邊
            page = pdf_doc_v[target_page - 1]
            raw_pil_img = page.render(scale=2.0).to_pil()
            cropped_img = crop_white_margins(raw_pil_img) # 🌟 魔法：裁掉無用白邊
            
            # 將裁切後的圖片轉 Base64
            img_byte_arr = io.BytesIO()
            cropped_img.save(img_byte_arr, format='JPEG')
            encoded_img = base64.b64encode(img_byte_arr.getvalue()).decode()
            img_uri = f"data:image/jpeg;base64,{encoded_img}"

        with col_v2:
            st.write("") 
            st.write("")
            is_scanned = str(target_page) in st.session_state.scanned_pages
            
            if is_scanned:
                st.success(f"⚡ 第 {target_page} 頁已在快取中，瞬間讀取完成！")
            else:
                run_scan = st.button(f"🔍 AI 視覺掃描第 {target_page} 頁 (僅需掃描一次)", use_container_width=True, key="btn_scan_t5")
                
                if run_scan:
                    with st.spinner("🧠 Gemini Vision 正在鎖定畫面上的所有標號座標..."):
                        try:
                            comp_dict_list = st.session_state.claim_data.get("components", [])
                            known_comps_str = json.dumps(comp_dict_list, ensure_ascii=False)

                            prompt_vision = f"""
                            這是一張機車專利圖式。已知本專利的部分元件對應表為：{known_comps_str}
                            找出圖片上「所有肉眼可見的數字標號」。如果在對應表中，填寫 name；沒有則填 "未知"。
                            估算該標號的「相對中心座標」(0.0~1.0)。
                            嚴格輸出 JSON：
                            {{ "hotspots": [ {{"number": "31", "name": "汽缸頭", "x_rel": 0.45, "y_rel": 0.55}} ] }}
                            """
                            # 送出被裁切過的圖片，精準度會大幅提升
                            response_vis = model.generate_content([cropped_img, prompt_vision])
                            clean_text_vis = response_vis.text.replace('```json', '').replace('```', '').strip()
                            clean_text_vis = clean_text_vis[clean_text_vis.find('{'):clean_text_vis.rfind('}')+1]
                            ai_visual_data = json.loads(clean_text_vis).get("hotspots", [])

                            # 🌟 將結果寫入記憶體快取
                            st.session_state.scanned_pages[str(target_page)] = ai_visual_data
                            st.rerun() # 重新整理畫面載入快取
                        except Exception as e:
                            st.error(f"視覺解析失敗：{e}")

        # ==== 開始渲染雙向連動 HTML ====
        if is_scanned:
            ai_visual_data = st.session_state.scanned_pages[str(target_page)]
            comp_dict_list = st.session_state.claim_data.get("components", [])
            
            claim_lines = st.session_state.claim_data.get("claims", [])
            claim_text_full = "<br><br>".join(claim_lines)
            
            # 1. 預處理右側文字：加入 JS 雙向觸發事件 onmouseover="hoverText('32')"
            for comp in comp_dict_list:
                comp_num = comp["id"]
                comp_name = comp["name"]
                # 把元件文字綁定事件，滑過文字時通知 JS 去亮起圖片標記
                replacement = f'<span class="comp-text comp-{comp_num}" onmouseover="hoverText(\'{comp_num}\')" onmouseout="leaveText(\'{comp_num}\')">{comp_name} ({comp_num})</span>'
                claim_text_full = claim_text_full.replace(comp_name, replacement)
            
            # 2. 生成圖片熱區：加入唯一的 ID 讓文字可以找到它
            hotspots_html = ""
            for spot in ai_visual_data:
                hotspots_html += f"""
                <div class="hotspot hotspot-marker-{spot['number']}" id="hotspot-{spot['number']}"
                     style="left: {spot['x_rel']*100}%; top: {spot['y_rel']*100}%;"
                     onmouseover="hoverImage('{spot['number']}', '{spot['name']}')" 
                     onmouseout="leaveImage('{spot['number']}')">
                </div>
                """

            # 3. 雙向連動專屬 HTML/JS 骨架
            html_skeleton = f"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
                body {{ margin: 0; font-family: sans-serif; background: #f0f2f6; }}
                .main-container {{ display: flex; height: 850px; width: 100%; border-radius: 8px; overflow: hidden; background: white; border: 1px solid #ddd; }}
                
                /* 左側大圖區 */
                .img-section {{ flex: 5; position: relative; overflow: auto; background: #e0e0e0; border-right: 2px solid #ddd; display: flex; justify-content: center; align-items: flex-start; padding: 10px; }}
                .img-wrapper {{ position: relative; display: inline-block; }}
                /* 圖紙已經過 Python 裁邊，現在可以盡可能放大 */
                .patent-img {{ max-width: 100%; height: auto; display: block; }}
                
                /* 透明熱區 (平時隱藏/微弱) */
                .hotspot {{ position: absolute; width: 40px; height: 40px; transform: translate(-50%, -50%); border-radius: 50%; cursor: pointer; transition: 0.2s; border: 2px solid transparent; z-index: 10; }}
                /* 滑鼠指圖片時的特效 */
                .hotspot:hover {{ background: rgba(255, 0, 0, 0.3); border: 2px solid red; box-shadow: 0 0 10px rgba(255,0,0,0.5); z-index: 50; }}
                /* 🌟 文字反向觸發時的爆亮特效 */
                .hotspot-active {{ background: rgba(255, 255, 0, 0.6) !important; border: 3px solid red !important; box-shadow: 0 0 20px red !important; transform: translate(-50%, -50%) scale(1.3); z-index: 50; }}
                
                #tooltip {{ display: none; position: absolute; background: rgba(0, 0, 0, 0.8); color: white; padding: 6px 12px; border-radius: 4px; font-size: 14px; z-index: 100; pointer-events: none; white-space: nowrap; }}
                
                /* 右側文字區 */
                .text-section {{ flex: 5; padding: 30px; overflow-y: auto; font-size: 16px; line-height: 1.8; color: #333; }}
                .claim-title {{ font-size: 22px; font-weight: bold; margin-bottom: 20px; color: #1e3a8a; border-bottom: 2px solid #ddd; padding-bottom: 10px; position: sticky; top: 0; background: white; z-index: 10; }}
                
                .comp-text {{ transition: 0.2s; border-radius: 3px; padding: 0 2px; border-bottom: 1px dotted #ccc; cursor: pointer; }}
                .comp-text:hover {{ background-color: #e0f2fe; }} /* 文字自體 hover 提示 */
                .highlight-active {{ background-color: #ffeb3b; color: #b91c1c; font-weight: bold; transform: scale(1.05); display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.2); border-bottom: none; }}
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
                    <div class="claim-title">📜 雙向連動：滑鼠指引文字試試！</div>
                    <div id="claim-content">
                        {claim_text_full}
                    </div>
                </div>
            </div>

            <script>
                const tooltip = document.getElementById('tooltip');

                // 📌 動作一：滑鼠指圖片 ➔ 亮右邊文字
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
                        if (index === 0) el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                    }});
                }}

                function leaveImage(num) {{
                    document.onmousemove = null;
                    tooltip.style.display = 'none';
                    document.querySelectorAll('.comp-' + num).forEach(el => el.classList.remove('highlight-active'));
                }}

                // 📌 動作二：滑鼠指右邊文字 ➔ 爆亮左邊圖片標號
                function hoverText(num) {{
                    // 1. 自己(文字)也要亮起來
                    const targets = document.querySelectorAll('.comp-' + num);
                    targets.forEach(el => el.classList.add('highlight-active'));

                    // 2. 找到圖片上對應的熱區，讓它變色變大
                    const hotspot = document.getElementById('hotspot-' + num);
                    if (hotspot) {{
                        hotspot.classList.add('hotspot-active');
                        // 讓圖片區域自動捲動到那個點 (如果圖太大的話)
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
            components.html(html_skeleton, height=880, scrolling=False)
