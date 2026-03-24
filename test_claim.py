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
# ⚙️ 1. 系統環境保護 (防禦 Secrets 缺失)
# ==========================================
st.set_page_config(page_title="機車專利 AI 戰略分析系統", layout="wide")

def get_secret(key):
    try: return st.secrets[key]
    except: return None

S_URL = get_secret("SUPABASE_URL")
S_KEY = get_secret("SUPABASE_KEY")
G_KEY = get_secret("GOOGLE_API_KEY")

if not all([S_URL, S_KEY, G_KEY]):
    st.error("❌ 系統偵測到雲端 Secrets 設定缺失！請在 Streamlit 後台檢查 SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY 是否填寫正確。")
    st.stop()

# 初始化 AI
genai.configure(api_key=G_KEY)
model = genai.GenerativeModel('gemini-2.5-flash', generation_config=genai.types.GenerationConfig(temperature=0.1, top_p=0.8))

@st.cache_resource
def init_supabase() -> Client:
    return create_client(S_URL, S_KEY)
supabase = init_supabase()

# 狀態安全初始化
for key in ['selected_patents_set', 'scanned_pages']:
    if key not in st.session_state: st.session_state[key] = {}
if 'target_single_patent' not in st.session_state: st.session_state.target_single_patent = None
if 'rd_card_data' not in st.session_state: st.session_state.rd_card_data = {}
if 'claim_data_t2' not in st.session_state: st.session_state.claim_data_t2 = {}
if 'ip_report_content' not in st.session_state: st.session_state.ip_report_content = ""
if 'pdf_bytes_main' not in st.session_state: st.session_state.pdf_bytes_main = None

# ==========================================
# 🛠️ 2. 核心功能函數
# ==========================================
def parse_ai_json(text):
    try:
        cln = str(text).replace('```json', '').replace('```', '').strip()
        s, e = cln.find('{'), cln.rfind('}')
        return json.loads(cln[s:e+1]) if s != -1 else {}
    except: return {}

def crop_margins(img):
    try:
        inv = ImageOps.invert(img.convert('RGB'))
        box = inv.getbbox()
        return img.crop((max(0,box[0]-20), max(0,box[1]-20), min(img.width,box[2]+20), min(img.height,box[3]+20))) if box else img
    except: return img

def fetch_patents(status=None):
    try:
        q = supabase.table('patents').select("*")
        if status: q = q.eq('status', status)
        return pd.DataFrame(q.execute().data)
    except: return pd.DataFrame()

# ==========================================
# 📊 3. 介面與模組
# ==========================================
with st.sidebar:
    st.title("系統控制台")
    if st.button("🗑️ 徹底重置快取 (卡死必按)", use_container_width=True):
        st.session_state.clear()
        st.rerun()

t1, t2, t3, t4, t5 = st.tabs(["📥 匯入", "📊 知識庫", "🕵️ 深度拆解", "🗺️ 宏觀", "⚔️ 攻防"])

with t2:
    df = fetch_patents('COMPLETED')
    if not df.empty:
        st.dataframe(df[['title', 'assignee', 'sys_main']])
        for _, r in df.iterrows():
            if st.button(f"進入單篇分析：{r['title']}", key=f"btn_{r['id']}"):
                st.session_state.target_single_patent = r
                st.rerun()

with t3:
    target = st.session_state.target_single_patent
    if not target:
        st.info("👈 請先從知識庫選擇一篇專利")
    else:
        st.subheader(f"當前拆解：{target.get('title')}")
        pdf_file = st.file_uploader("上傳該案 PDF 說明書", type=["pdf"])
        
        if pdf_file and st.button("🚀 執行 AI 深度拆解", type="primary"):
            with st.spinner("AI 地毯式搜索中..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(pdf_file.getvalue())
                        gem_file = genai.upload_file(tmp.name)
                    
                    # 組合 Prompt 確保安全
                    p = "請針對PDF分析。輸出純JSON包含: rd_card, vis_data, ip_report。\n"
                    p += "1. rd_card: {title, problem, solution, risk_check(獨立項拆解清單), design_avoid_rd}\n"
                    p += "2. vis_data: {claims, components(id與name), spec_texts, loophole_quote(一字不漏抄錄獨立項最關鍵限制金句)}\n"
                    p += "3. ip_report: 遵守10大天條(FTO判定、Claim Chart等)。元件id須精準對應標號。"
                    
                    res = model.generate_content([gem_file, p])
                    parsed = parse_ai_json(res.text)
                    st.session_state.rd_card_data = parsed.get("rd_card", {})
                    st.session_state.claim_data_t2 = parsed.get("vis_data", {})
                    st.session_state.ip_report_content = parsed.get("ip_report", "")
                    st.session_state.pdf_bytes_main = pdf_file.getvalue()
                    st.success("✅ 分析完成！")
                except Exception as e: st.error(f"分析失敗：{e}")

        if st.session_state.pdf_bytes_main and st.session_state.rd_card_data:
            c_data = st.session_state.claim_data_t2
            doc = pdfium.PdfDocument(st.session_state.pdf_bytes_main)
            
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1: pg = st.number_input("頁碼", 1, len(doc), 2)
            with c2: rot = st.radio("旋轉", [0, 90, 180, 270], horizontal=True)
            
            pil = doc[pg-1].render(scale=2.0).to_pil()
            if rot != 0: pil = pil.rotate(-rot, expand=True, fillcolor='white')
            img_b64 = base64.b64encode(io.BytesIO().tap(lambda b: crop_margins(pil).save(b, format='JPEG')).getvalue()).decode()
            
            with c3:
                st.write("")
                if st.button("🔍 標號鎖定座標"):
                    with st.spinner("定位中..."):
                        vp = f"找出圖中標號座標(x_rel, y_rel 0~1)。元件清單：{json.dumps(c_data.get('components',[]), ensure_ascii=False)}"
                        vr = model.generate_content([pil, vp])
                        st.session_state.scanned_pages[f"{pg}_{rot}"] = parse_ai_json(vr.text).get("hotspots", [])
                        st.rerun()

            # HTML 雙向連動引擎
            loophole = str(c_data.get("loophole_quote", ""))
            raw_cls = c_data.get("claims", [])
            claims_list = raw_cls if isinstance(raw_cls, list) else [str(raw_cls)]
            
            html_cls = ""
            for i, line in enumerate(claims_list):
                txt = str(line)
                if i == 0 and loophole and loophole in txt:
                    txt = txt.replace(loophole, f'<mark style="background:#ffeb3b;font-weight:bold;">{loophole}</mark>')
                for cp in c_data.get("components", []):
                    cid, cnm = str(cp.get("id","")), str(cp.get("name",""))
                    if cid and cnm:
                        txt = txt.replace(cnm, f'<span style="color:#0284c7;font-weight:bold;cursor:pointer;border-bottom:1px dashed;" onmouseover="hoverT(\'{cid}\')">{cnm}({cid})</span>')
                html_cls += f'<div style="margin-bottom:12px;">{txt}</div>'

            spots = "".join([f'<div style="position:absolute;width:30px;height:30px;border:3px solid red;border-radius:50%;left:{s.get("x_rel",0)*100}%;top:{s.get("y_rel",0)*100}%;transform:translate(-50%,-50%);" id="hs-{s.get("number","")}"></div>' for s in st.session_state.scanned_pages.get(f"{pg}_{rot}", [])])

            components.html(f"""
            <div style="display:flex;height:700px;border:1px solid #ddd;overflow:hidden;">
                <div style="flex:6;position:relative;overflow:auto;background:#f0f0f0;display:flex;justify-content:center;">
                    <div style="position:relative;display:inline-block;"><img src="data:image/jpeg;base64,{img_b64}" style="max-width:100%;">{spots}</div>
                </div>
                <div style="flex:4;padding:25px;overflow-y:auto;background:white;font-size:15px;line-height:1.7;">{html_cls}</div>
            </div>
            <script>function hoverT(id){{const el=document.getElementById('hs-'+id);if(el)el.style.boxShadow='0 0 15px yellow';}}</script>
            """, height=720)

with t1: st.info("模組功能開發中，請先從知識庫手動進入單篇分析。")
with t4: st.info("宏觀分析功能開發中。")
with t5: st.info("組合分析功能開發中。")
