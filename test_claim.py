import os
import json
import random 
import streamlit as st
import google.generativeai as genai
import tempfile
import pypdfium2 as pdfium
import base64
import streamlit.components.v1 as components
import io  # 🌟 新增：處理記憶體圖片轉換
from PIL import Image

# 👇 建立 API 鑰匙池
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash')

st.set_page_config(page_title="Claim Construction 沙盒 V3", layout="wide")

if 'claim_data' not in st.session_state:
    st.session_state.claim_data = None
if 'pdf_bytes' not in st.session_state:
    st.session_state.pdf_bytes = None # 🌟 暫存 PDF 檔案，供各頁籤共用

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
st.markdown("整合 Gemini AI 深度解析、**PDF 自動切割**與**前端沉浸式圖文連動**技術。")
st.markdown("---")

uploaded_pdf = st.file_uploader("📥 第一步：請上傳一份專利 PDF 檔 (供 AI 解析與後續截圖用)", type=["pdf"])

if st.button("🤖 啟動精細拆解 (建立全文本與全元件字典)", use_container_width=True):
    if uploaded_pdf is None:
        st.warning("⚠️ 請先上傳 PDF 檔案！")
    else:
        # 將上傳的 PDF 存入 Session State 供後續頁籤直接讀取
        st.session_state.pdf_bytes = uploaded_pdf.getvalue()
        
        with st.spinner("大腦正在建立全本專利的「符號字典」與「所有請求項」... (約需 20 秒)"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(st.session_state.pdf_bytes)
                    tmp_file_path = tmp_file.name

                gemini_file = genai.upload_file(tmp_file_path)

                # 🌟 更新 Prompt：要求抓取「所有」請求項
                prompt = '''
                你現在是一個精準的專利資料庫解析系統。請閱讀這份專利，並將內容轉化為結構化的 JSON 格式。

                【任務 1：完整元件符號字典 (絕對不能漏)】
                請去尋找專利說明書最後面的「符號簡單說明」或文中的對應段落。將裡面提及的【每一個】元件符號跟名稱提取出來。

                【任務 2：所有請求項拆解】
                將「所有請求項」(包含獨立項與附屬項) 逐項、逐句拆解為陣列。

                【任務 3：實施方式全文本提取】
                請將專利中「發明說明 / 實施方式」的所有段落完整提取出來，必須保留原本的【00xx】段落編號。

                【🔴 絕對指令：輸出純 JSON 格式】
                嚴格符合以下結構：
                {
                  "claims": [
                    "1. 一種機車，包含：",
                    "一車架10；",
                    "2. 如請求項1所述之機車，其中..."
                  ],
                  "components": [
                    {"id": "10", "name": "車架"},
                    {"id": "11", "name": "頭管"}
                  ],
                  "spec_texts": [
                    "【0015】如圖1所示，車架10包含...",
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
# 實務級展示區 (頁籤模式)
# ==========================================
if st.session_state.claim_data and st.session_state.pdf_bytes:
    st.markdown("---")
    
    tab_workspace, tab_immersive = st.tabs(["⚖️ 實務級三聯屏", "🎯 沉浸式圖文連動 (免上傳版)"])

    # --- 頁籤一：實務工作站 (省略部分未修改的程式碼以保持整潔，與之前相同) ---
    with tab_workspace:
        st.write("這是你原本的工作站，已支援全本字典...")
        # (保留你原本的三視窗選擇器程式碼即可)
        pass 

    # --- 頁籤二：🌟 終極自動化沉浸式圖文連動 ---
    with tab_immersive:
        st.markdown("### 🎯 沉浸式圖文連動解析")
        st.markdown("直接從你剛剛上傳的 PDF 中選取頁碼，AI 將自動辨識該頁圖式並與**所有請求項**進行連動。")

        # 1. 直接讀取剛才上傳的 PDF 檔案
        pdf_doc_v = pdfium.PdfDocument(st.session_state.pdf_bytes)
        total_pages = len(pdf_doc_v)

        col_v1, col_v2 = st.columns([1, 2])
        with col_v1:
            # 🌟 直接用選單取代上傳圖片
            target_page = st.number_input(f"📄 選擇要分析的專利圖紙頁碼 (共 {total_pages} 頁)", min_value=1, max_value=total_pages, value=min(2, total_pages), key="vis_page_select")
            
            # 即時預覽該頁面
            page = pdf_doc_v[target_page - 1]
            pil_img = page.render(scale=2.0).to_pil()
            st.image(pil_img, caption=f"第 {target_page} 頁預覽", width=300)
            
        with col_v2:
            st.write("") 
            st.write("")
            run_vis = st.button("🌟 啟動 AI 視覺辨識與沉浸式連動", use_container_width=True, key="btn_run_t5")

        if run_vis:
            with st.spinner("🧠 正在啟動 Gemini 多模態視覺，尋找畫面上的標號座標... (約需 10 秒)"):
                try:
                    # 2. 將 PIL Image 轉為 Base64 供前端顯示
                    img_byte_arr = io.BytesIO()
                    pil_img.save(img_byte_arr, format='JPEG')
                    encoded_img = base64.b64encode(img_byte_arr.getvalue()).decode()
                    img_uri = f"data:image/jpeg;base64,{encoded_img}"

                    # 3. 準備元件字典清單，提示 Gemini
                    comp_dict_list = st.session_state.claim_data.get("components", [])
                    known_comps_str = json.dumps(comp_dict_list, ensure_ascii=False)

                    # 4. 🌟 直接呼叫 Gemini Vision 取得真實座標
                    prompt_vision = f"""
                    這是一張機車專利圖式。請觀察這張圖片。
                    已知本專利的部分元件對應表為：{known_comps_str}
                    
                    【任務】
                    找出這張圖片上「所有肉眼可見的數字標號」。
                    如果該數字有在元件對應表中，請填寫對應的 name；如果沒有，name 填 "未知"。
                    請估算這些標號在圖片上的「相對中心座標」(X軸由左至右 0.0~1.0，Y軸由上至下 0.0~1.0)。
                    
                    嚴格輸出 JSON：
                    {{
                      "hotspots": [
                        {{"number": "31", "name": "汽缸頭", "x_rel": 0.45, "y_rel": 0.55}}
                      ]
                    }}
                    """
                    # Gemini 可以直接吃 PIL image 物件
                    response_vis = model.generate_content([pil_img, prompt_vision])
                    clean_text_vis = response_vis.text.replace('```json', '').replace('```', '').strip()
                    clean_text_vis = clean_text_vis[clean_text_vis.find('{'):clean_text_vis.rfind('}')+1]
                    ai_visual_data = json.loads(clean_text_vis).get("hotspots", [])

                    st.toast(f"✅ AI 在此頁面成功辨識到 {len(ai_visual_data)} 個標號！", icon="🎯")

                    # 5. 處理「所有」請求項文字
                    claim_lines = st.session_state.claim_data.get("claims", [])
                    claim_text_full = "<br><br>".join(claim_lines)
                    
                    # 預處理右側文字：包裝上 <span> 標籤
                    for comp in comp_dict_list:
                        comp_num = comp["id"]
                        comp_name = comp["name"]
                        replacement = f'<span class="comp-text comp-{comp_num}">{comp_name} ({comp_num})</span>'
                        claim_text_full = claim_text_full.replace(comp_name, replacement)
                    
                    # 6. 利用 AI 回傳的座標生成 HTML 熱區
                    hotspots_html = ""
                    for spot in ai_visual_data:
                        hotspots_html += f"""
                        <div class="hotspot" 
                             style="left: {spot['x_rel']*100}%; top: {spot['y_rel']*100}%;"
                             onmouseover="highlight('{spot['number']}', '{spot['name']}')" 
                             onmouseout="removeHighlight('{spot['number']}')">
                        </div>
                        """

                    # 7. 渲染前端 HTML
                    html_skeleton = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                    <style>
                        body {{ margin: 0; font-family: sans-serif; background: #f0f2f6; }}
                        .main-container {{ display: flex; height: 850px; width: 100%; border-radius: 8px; overflow: hidden; background: white; border: 1px solid #ddd; }}
                        
                        /* 左側大圖區 */
                        .img-section {{ flex: 6; position: relative; overflow: auto; background: #e0e0e0; border-right: 2px solid #ddd; display: flex; justify-content: center; align-items: flex-start; padding: 10px; }}
                        .img-wrapper {{ position: relative; display: inline-block; }}
                        .patent-img {{ max-width: 100%; height: auto; }}
                        
                        /* 透明熱區 */
                        .hotspot {{ position: absolute; width: 45px; height: 45px; transform: translate(-50%, -50%); border-radius: 50%; cursor: pointer; transition: 0.2s; border: 2px solid transparent; }}
                        .hotspot:hover {{ background: rgba(255, 0, 0, 0.3); border: 2px solid red; box-shadow: 0 0 10px rgba(255,0,0,0.5); }}
                        
                        /* Tooltip */
                        #tooltip {{ display: none; position: absolute; background: rgba(0, 0, 0, 0.8); color: white; padding: 6px 12px; border-radius: 4px; font-size: 14px; z-index: 100; pointer-events: none; white-space: nowrap; }}
                        
                        /* 右側文字區 */
                        .text-section {{ flex: 4; padding: 30px; overflow-y: auto; font-size: 16px; line-height: 1.8; color: #333; }}
                        .claim-title {{ font-size: 22px; font-weight: bold; margin-bottom: 20px; color: #1e3a8a; border-bottom: 2px solid #ddd; padding-bottom: 10px; position: sticky; top: 0; background: white; z-index: 10; }}
                        
                        /* 高亮特效 */
                        .comp-text {{ transition: 0.3s; border-radius: 3px; padding: 0 2px; }}
                        .highlight-active {{ background-color: #ffeb3b; color: #b91c1c; font-weight: bold; transform: scale(1.05); display: inline-block; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }}
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
                            <div class="claim-title">📜 全文請求項對照</div>
                            <div id="claim-content">
                                {claim_text_full}
                            </div>
                        </div>
                    </div>

                    <script>
                        const tooltip = document.getElementById('tooltip');

                        function highlight(num, name) {{
                            document.onmousemove = function(e) {{
                                tooltip.style.left = (e.pageX + 15) + 'px';
                                tooltip.style.top = (e.pageY + 15) + 'px';
                            }};
                            tooltip.innerHTML = "標號 <b>" + num + "</b> : " + name;
                            tooltip.style.display = 'block';

                            const targets = document.querySelectorAll('.comp-' + num);
                            targets.forEach((el, index) => {{
                                el.classList.add('highlight-active');
                                // 只滾動到出現的第一個元件，避免畫面亂跳
                                if (index === 0) {{
                                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                                }}
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
                    components.html(html_skeleton, height=880, scrolling=False)

                except Exception as e:
                    st.error(f"視覺解析失敗：{e}")
