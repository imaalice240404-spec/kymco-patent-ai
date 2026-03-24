# -*- coding: utf-8 -*-
import os, json, random, time, datetime, tempfile, io, base64
import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
from supabase import create_client, Client
import pypdfium2 as pdfium
from docx import Document
import streamlit.components.v1 as components
import plotly.express as px
from PIL import Image, ImageOps

# ==========================================
# ⚙️ 1. 系統初始化
# ==========================================
st.set_page_config(page_title="機車專利 AI 戰略分析系統", layout="wide")

api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key: genai.configure(api_key=selected_key)
model = genai.GenerativeModel('gemini-2.5-flash', generation_config=genai.types.GenerationConfig(temperature=0.1, top_p=0.8))

@st.cache_resource
def init_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = init_supabase()

# 狀態初始化 (安全氣囊)
for key in ['selected_patents_set', 'scanned_pages']:
    if key not in st.session_state: st.session_state[key] = {} if key == 'scanned_pages' else set()
if 'target_single_patent' not in st.session_state: st.session_state.target_single_patent = None
if 'rd_card_data' not in st.session_state: st.session_state.rd_card_data = {}
if 'claim_data_t2' not in st.session_state: st.session_state.claim_data_t2 = {}
if 'ip_report_content' not in st.session_state: st.session_state.ip_report_content = ""

# ==========================================
# 🛠️ 2. 輔助函數
# ==========================================
def parse_ai_json(text_or_dict):
    if isinstance(text_or_dict, dict): return text_or_dict
    try:
        cln = str(text_or_dict).replace('```json', '').replace('```', '').strip()
        s, e = cln.find('{'), cln.rfind('}')
        return json.loads(cln[s:e+1]) if s != -1 else {}
    except: return {}

def crop_white_margins(img):
    try:
        inv = ImageOps.invert(img.convert('RGB'))
        bbox = inv.getbbox()
        return img.crop((max(0,bbox[0]-20), max(0,bbox[1]-20), min(img.width,bbox[2]+20), min(img.height,bbox[3]+20))) if bbox else img
    except: return img

def fetch_patents(status=None):
    q = supabase.table('patents').select("*")
    if status: q = q.eq('status', status)
    res = q.execute()
    return pd.DataFrame(res.data)

# ==========================================
# 📊 3. 主介面
# ==========================================
with st.sidebar:
    st.header("系統控制")
    if st.button("🗑️ 重置當前分析 (防卡死必按)", use_container_width=True):
        st.session_state.target_single_patent = None
        st.session_state.rd_card_data = {}
        st.session_state.claim_data_t2 = {}
        st.rerun()

t1, t2, t3, t4, t5 = st.tabs(["📥 匯入", "📊 知識庫", "🕵️ 深度拆解", "🗺️ 宏觀", "⚔️ 攻防"])

# --- 模組三：深度拆解 (核心修復區) ---
with t3:
    if not st.session_state.target_single_patent:
        st.info("請先從模組二選擇專利")
    else:
        target = st.session_state.target_single_patent
        st.subheader(f"分析目標：{target.get('title', '無名稱')}")
        
        pdf_file = st.file_uploader("上傳 PDF 說明書", type=["pdf"])
        if pdf_file and st.button("🚀 啟動 AI 深度拆解", type="primary"):
            with st.spinner("AI 地毯式搜索中..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(pdf_file.getvalue())
                        gemini_file = genai.upload_file(tmp.name)
                    
                    # 🌟 完整恢復所有限制條件的 Prompt (字串插值法避免括號)
                    prompt = "請針對PDF進行機車專利深度分析。輸出純JSON包含:\n"
                    prompt += "1. rd_card: {title, problem, solution, risk_check(獨立項要件拆解清單), design_avoid_rd(迴避方向)}\n"
                    prompt += "2. vis_data: {claims(包含編號的全文), components(id與name配對), spec_texts(說明書段落), loophole_quote(一字不漏抄錄獨立項中最關鍵的限制金句)}\n"
                    prompt += "3. ip_report: 遵守10大天條(FTO風險判定、技術快照、部門派發、破口分析、Claim Chart等)並使用紅黃綠燈Emoji。\n"
                    prompt += "⚠️防呆：元件id必須與標號100%對應，例如下降管部不可配錯對。"
                    
                    res = model.generate_content([gemini_file, prompt])
                    parsed = parse_ai_json(res.text)
                    st.session_state.rd_card_data = parsed.get("rd_card", {})
                    st.session_state.claim_data_t2 = parsed.get("vis_data", {})
                    st.session_state.ip_report_content = parsed.get("ip_report", "分析失敗")
                    st.session_state.pdf_bytes_main = pdf_file.getvalue()
                    st.success("分析完成！")
                except Exception as e: st.error(f"分析崩潰：{e}")

        # 🌟 繪圖區 (加入大量安全氣囊防止 KeyError)
        if st.session_state.get("pdf_bytes_main") and st.session_state.rd_card_data:
            c_rd, c_ip = st.tabs(["🧑‍💻 研發看板", "⚖️ 智權報告"])
            with c_rd:
                # 準備圖紙
                doc = pdfium.PdfDocument(st.session_state.pdf_bytes_main)
                col_p, col_r, col_b = st.columns([1, 1.5, 1.5])
                with col_p: pg = st.number_input("頁碼", 1, len(doc), 2)
                with col_r: rot = st.radio("旋轉", [0, 90, 180, 270], horizontal=True)
                
                # 旋轉與轉圖
                pil_img = doc[pg-1].render(scale=2.0).to_pil()
                if rot != 0: pil_img = pil_img.rotate(-rot, expand=True, fillcolor='white')
                img_b64 = base64.b64encode(io.BytesIO().tap(lambda b: crop_white_margins(pil_img).save(b, format='JPEG')).getvalue()).decode()
                
                # 視覺定位按鈕
                scan_key = f"{pg}_{rot}"
                with col_b:
                    st.write("")
                    if st.button("🔍 標號鎖定"):
                        with st.spinner("定位中..."):
                            v_prompt = f"找出圖中所有標號座標(x_rel, y_rel 0~1)，已知元件：{json.dumps(st.session_state.claim_data_t2.get('components',[]), ensure_ascii=False)}"
                            v_res = model.generate_content([pil_img, v_prompt])
                            st.session_state.scanned_pages[scan_key] = parse_ai_json(v_res.text).get("hotspots", [])
                            st.rerun()

                # 🌟 核心：雙向連動 HTML (加上安全讀取)
                c_data = st.session_state.claim_data_t2
                raw_claims = c_data.get("claims", [])
                loophole = str(c_data.get("loophole_quote", ""))
                
                # 生成高亮 HTML
                claim_html = ""
                for i, line in enumerate(raw_claims):
                    line_txt = str(line)
                    if i == 0 and loophole and loophole in line_txt:
                        line_txt = line_txt.replace(loophole, f'<mark style="background:#ffeb3b;font-weight:bold;">{loophole}</mark>')
                    for comp in c_data.get("components", []):
                        cid, cnm = str(comp.get("id","")), str(comp.get("name",""))
                        if cid: line_txt = line_txt.replace(cnm, f'<span style="color:#0284c7;font-weight:bold;cursor:pointer;border-bottom:1px dashed;" onmouseover="hoverT(\'{cid}\')">{cnm}({cid})</span>')
                    claim_html += f'<div style="margin-bottom:10px;">{line_txt}</div>'

                # 產生 Hotspots
                spots_html = "".join([f'<div style="position:absolute;width:30px;height:30px;border:2px solid red;border-radius:50%;left:{s.get("x_rel",0)*100}%;top:{s.get("y_rel",0)*100}%;transform:translate(-50%,-50%);" id="hs-{s.get("number","")}"></div>' for s in st.session_state.scanned_pages.get(scan_key, [])])

                components.html(f"""
                <div style="display:flex;height:600px;border:1px solid #ddd;">
                    <div style="flex:6;position:relative;overflow:auto;background:#eee;display:flex;justify-content:center;">
                        <div style="position:relative;display:inline-block;"><img src="data:image/jpeg;base64,{img_b64}" style="max-width:100%;">{spots_html}</div>
                    </div>
                    <div style="flex:4;padding:20px;overflow-y:auto;background:white;font-size:14px;line-height:1.6;">{claim_html}</div>
                </div>
                <script>function hoverT(id){{const el=parent.document.getElementById('hs-'+id);if(el)el.style.background='rgba(255,255,0,0.5)';}}</script>
                """, height=620)

# --- 其他模組簡化版 (確保不報錯) ---
with t1: st.write("請使用 Excel 匯入專利")
with t2:
    df = fetch_patents('COMPLETED')
    if not df.empty:
        st.dataframe(df[['專利名稱', '專利權人', '五大類']])
        for _, r in df.iterrows():
            if st.button(f"選擇：{r['專利名稱']}", key=f"btn_{r['ID']}"):
                st.session_state.target_single_patent = r.to_dict()
                st.rerun()
with t4: st.write("宏觀分析地圖製作中")
with t5: st.write("TSM 組合攻防推演中")
