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
# ⚙️ 1. 系統診斷與環境初始化
# ==========================================
st.set_page_config(page_title="機車專利 AI 戰略分析系統", layout="wide")

# 🔍 診斷工具：這行會幫你確認 Secrets 到底有沒有被系統讀到
if st.secrets:
    st.info(f"🔍 系統診斷 - 當前偵測到的 Secrets 鑰匙清單：{list(st.secrets.keys())}")
else:
    st.error("❌ 系統診斷 - 完全偵測不到任何 Secrets 設定！請檢查 Streamlit 後台設定。")

def get_config(keys):
    """嘗試從多個可能的變數名中取得設定"""
    for k in keys:
        try: return st.secrets[k]
        except: continue
    return None

S_URL = get_config(["SUPABASE_URL", "supabase_url", "URL"])
S_KEY = get_config(["SUPABASE_KEY", "supabase_key", "KEY"])
G_KEY = get_config(["GOOGLE_API_KEY", "google_api_key", "GEMINI_KEY", "API_KEY"])

if not all([S_URL, S_KEY, G_KEY]):
    st.warning("⚠️ 等待 Secrets 設定中... 請確保後台已填寫 SUPABASE_URL, SUPABASE_KEY, GOOGLE_API_KEY。")
    st.stop()

# 初始化連線
genai.configure(api_key=G_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

@st.cache_resource
def init_supabase() -> Client:
    return create_client(S_URL, S_KEY)
supabase = init_supabase()

# 狀態安全氣囊
if 'target_single_patent' not in st.session_state: st.session_state.target_single_patent = None
if 'rd_card_data' not in st.session_state: st.session_state.rd_card_data = {}
if 'claim_data_t2' not in st.session_state: st.session_state.claim_data_t2 = {}
if 'scanned_pages' not in st.session_state: st.session_state.scanned_pages = {}

# ==========================================
# 🛠️ 2. 核心工具
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

# ==========================================
# 📊 3. 介面模組
# ==========================================
with st.sidebar:
    st.title("系統控制")
    if st.button("🗑️ 徹底重置快取", use_container_width=True):
        st.session_state.clear()
        st.rerun()

t1, t2, t3, t4, t5 = st.tabs(["📥 匯入資料", "📊 專利知識庫", "🕵️ 深度拆解工作站", "🗺️ 宏觀趨勢", "⚔️ 攻防推演"])

# --- 模組二：知識庫 ---
with t2:
    try:
        res = supabase.table('patents').select("*").eq('status', 'COMPLETED').execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            st.dataframe(df[['title', 'assignee', 'sys_main']])
            for _, r in df.iterrows():
                if st.button(f"進入分析：{r['title']}", key=f"sel_{r['id']}"):
                    st.session_state.target_single_patent = r
                    st.rerun()
        else: st.info("目前資料庫無 COMPLETED 狀態的專利。")
    except: st.error("資料庫連線失敗。")

# --- 模組三：深度拆解 ---
with t3:
    target = st.session_state.target_single_patent
    if not target:
        st.info("👈 請先從專利知識庫選擇一篇專利")
    else:
        st.subheader(f"當前拆解專利：{target.get('title')}")
        pdf_file = st.file_uploader("上傳專利 PDF 說明書", type=["pdf"])
        
        if pdf_file and st.button("🚀 啟動 AI 全文深度拆解", type="primary"):
            with st.spinner("AI 正在閱讀 PDF 並進行 10 大天條審查..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(pdf_file.getvalue())
                        gem_file = genai.upload_file(tmp.name)
                    
                    p = "請分析PDF專利。輸出純JSON包含:\n"
                    p += "1. rd_card: {title, problem, solution, risk_check(List), design_avoid_rd(List)}\n"
                    p += "2. vis_data: {claims(List), components(List of {id, name}), spec_texts(List), loophole_quote(String)}\n"
                    p += "3. ip_report: 遵守10大天條(FTO風險判定、技術快照、部門派發、破口、Claim Chart、地雷探測、可偵測性、打假、迴避建議、機構整併)。"
                    
                    res = model.generate_content([gem_file, p])
                    parsed = parse_ai_json(res.text)
                    st.session_state.rd_card_data = parsed.get("rd_card", {})
                    st.session_state.claim_data_t2 = parsed.get("vis_data", {})
                    st.session_state.ip_report_content = parsed.get("ip_report", "")
                    st.session_state.pdf_bytes_main = pdf_file.getvalue()
                    st.success("✅ 解析成功！")
                except Exception as e: st.error(f"分析失敗：{e}")

        if st.session_state.get("pdf_bytes_main") and st.session_state.get("rd_card_data"):
            c_data = st.session_state.claim_data_t2
            doc = pdfium.PdfDocument(st.session_state.pdf_bytes_main)
            
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1: pg = st.number_input("頁碼", 1, len(doc), 2)
            with c2: rot = st.radio("旋轉", [0, 90, 180, 270], horizontal=True)
            
            pil = doc[pg-1].render(scale=2.0).to_pil()
            if rot != 0: pil = pil.rotate(-rot, expand=True, fillcolor='white')
            
            buf = io.BytesIO()
            crop_margins(pil).save(buf, format='JPEG')
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            
            with c3:
                st.write("")
                if st.button("🔍 標號鎖定座標"):
                    with st.spinner("AI 視覺標記中..."):
                        vp = f"找出圖中標號座標(x_rel, y_rel 0~1)。已知元件：{json.dumps(c_data.get('components',[]), ensure_ascii=False)}"
                        vr = model.generate_content([pil, vp])
                        st.session_state.scanned_pages[f"{pg}_{rot}"] = parse_ai_json(vr.text).get("hotspots", [])
                        st.rerun()

            # HTML 連動視窗
            raw_cls = c_data.get("claims", [])
            claims_list = raw_cls if isinstance(raw_cls, list) else [str(raw_cls)]
            loophole = str(c_data.get("loophole_quote", ""))
            
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
            <div style="display:flex;height:700px;border:1px solid #ddd;overflow:hidden;background:white;">
                <div style="flex:6;position:relative;overflow:auto;background:#f0f0f0;display:flex;justify-content:center;padding:10px;">
                    <div style="position:relative;display:inline-block;"><img src="data:image/jpeg;base64,{img_b64}" style="max-width:100%;">{spots}</div>
                </div>
                <div style="flex:4;padding:25px;overflow-y:auto;background:white;font-size:15px;line-height:1.7;color:#333;">{html_cls}</div>
            </div>
            <script>function hoverT(id){{const el=document.getElementById('hs-'+id);if(el)el.style.backgroundColor='rgba(255,255,0,0.6)';}}</script>
            """, height=720)

with t1: st.info("資料匯入模組穩定中...")
with t4: st.info("宏觀趨勢地圖模組穩定中...")
with t5: st.info("組合攻防推演模組穩定中...")

# ===================== 🚀 程式碼完美結束 🚀 =====================
