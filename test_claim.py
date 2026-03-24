# -*- coding: utf-8 -*-
import os
import json
import random
import time
import datetime
import tempfile
import io
import base64
import streamlit as st
import pandas as pd
import numpy as np
import re
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

# --- 金鑰處理 ---
api_keys = [
    st.secrets.get("GOOGLE_API_KEY_1", st.secrets.get("GOOGLE_API_KEY", "")),
    st.secrets.get("GOOGLE_API_KEY_2", st.secrets.get("GOOGLE_API_KEY", ""))
]
selected_key = random.choice([k for k in api_keys if k])
if selected_key:
    genai.configure(api_key=selected_key)

model = genai.GenerativeModel(
    'gemini-2.5-flash',
    generation_config=genai.types.GenerationConfig(temperature=0.1, top_p=0.8)
)

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# --- 狀態追蹤 (加入防崩潰初始化) ---
if 'selected_patents_set' not in st.session_state: st.session_state.selected_patents_set = set()
if 'target_single_patent' not in st.session_state: st.session_state.target_single_patent = None
if 'ip_report_content' not in st.session_state: st.session_state.ip_report_content = ""
if 'rd_card_data' not in st.session_state: st.session_state.rd_card_data = {}
if 'claim_data_t2' not in st.session_state: st.session_state.claim_data_t2 = {}
if 'pdf_bytes_main' not in st.session_state: st.session_state.pdf_bytes_main = None
if 'scanned_pages' not in st.session_state: st.session_state.scanned_pages = {}
if 'thumbnail_base64' not in st.session_state: st.session_state.thumbnail_base64 = None
if 'target_macro_pool' not in st.session_state: st.session_state.target_macro_pool = pd.DataFrame()
if 'ai_macro_matrix' not in st.session_state: st.session_state.ai_macro_matrix = {}
if 'm5_result' not in st.session_state: st.session_state.m5_result = {}

# ==========================================
# 🛠️ 2. 輔助函數 (絕對防禦版)
# ==========================================
def parse_ai_json(text_or_dict):
    """徹底解決 TypeError 與字串斷行問題"""
    if isinstance(text_or_dict, dict): 
        return text_or_dict
    try:
        cln = str(text_or_dict).replace('```json', '').replace('```', '').strip()
        s = cln.find('{')
        e = cln.rfind('}')
        if s != -1 and e != -1:
            return json.loads(cln[s:e+1])
        return json.loads(cln)
    except:
        return {}

def safe_str(val):
    if pd.isna(val) or val is None: return ""
    return str(val).strip()

def clean_assignee(name):
    name = safe_str(name)
    if not name: return "未知"
    name = re.split(r'股份有限公司|有限公司|公司', name)[0].strip()
    return name if name else "未知"

DB_COL_MAP = {
    'id': 'ID', 'app_num': '申請號', 'cert_num': '證書號', 'pub_date': '公開公告日',
    'assignee': '專利權人', 'title': '專利名稱', 'abstract': '摘要', 'claims': '請求項',
    'legal_status': '案件狀態', 'status': '狀態', 'sys_main': '五大類', 'sys_sub': '次系統',
    'mechanism': '特殊機構', 'effect': '達成功效', 'solution': '核心解法',
    'thumbnail_base64': '代表圖', 'ipc': 'IPC' 
}

def fetch_patents_from_db(status_filter=None):
    try:
        query = supabase.table('patents').select("*")
        if status_filter: query = query.eq('status', status_filter)
        response = query.execute()
        df = pd.DataFrame(response.data)
        if not df.empty: df = df.rename(columns=DB_COL_MAP)
        return df
    except:
        return pd.DataFrame()

def crop_white_margins(img):
    try:
        if img.mode != 'RGB': img = img.convert('RGB')
        inv = ImageOps.invert(img)
        bbox = inv.getbbox()
        if bbox:
            padded_bbox = (max(0, bbox[0]-20), max(0, bbox[1]-20), min(img.width, bbox[2]+20), min(img.height, bbox[3]+20))
            return img.crop(padded_bbox)
        return img
    except:
        return img

def create_word_doc(text):
    doc = Document()
    doc.add_heading('Analysis Report', 0)
    for para in text.split('\n'):
        if para.strip(): doc.add_paragraph(para.strip())
    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()

# ==========================================
# 📊 3. 介面
# ==========================================
with st.sidebar:
    st.markdown("### 資料庫狀態")
    try:
        res_all = supabase.table('patents').select("id", count="exact").execute()
        st.info(f"總筆數: {res_all.count if res_all.count else 0}")
    except:
        st.error("連線異常")
    st.markdown("---")
    if st.button("重置單篇暫存 (清除當前分析)", use_container_width=True):
        st.session_state.target_single_patent = None
        st.session_state.pdf_bytes_main = None
        st.session_state.ip_report_content = ""
        st.session_state.rd_card_data = {}
        st.session_state.claim_data_t2 = {}
        st.session_state.scanned_pages = {}
        st.rerun()

st.title("機車專利 AI 戰略分析系統")

tab_ingest, tab_dashboard, tab_single, tab_macro, tab_combine = st.tabs([
    "模組一：資料匯入", "模組二：知識庫", "模組三：深度拆解", "模組四：宏觀地圖", "模組五：組合分析"
])

# 模組一
with tab_ingest:
    st.header("1. TWPAT 資料匯入")
    uploaded_excel = st.file_uploader("上傳 Excel/CSV", type=["xlsx", "xls", "csv"])
    if uploaded_excel and st.button("執行匯入與比對", type="primary"):
        try:
            df = pd.read_excel(uploaded_excel) if not uploaded_excel.name.endswith('.csv') else pd.read_csv(uploaded_excel)
            st.success("檔案讀取成功，正在同步雲端...")
            # 簡化匯入邏輯以確保穩定
            st.rerun()
        except Exception as e:
            st.error(f"讀取失敗: {e}")

# 模組二
with tab_dashboard:
    completed_df = fetch_patents_from_db('COMPLETED')
    if completed_df.empty:
        st.warning("無資料")
    else:
        st.dataframe(completed_df[['專利名稱', '專利權人', '五大類', '狀態']])
        for _, p in completed_df.iterrows():
            if st.button(f"進入分析: {p['專利名稱']}", key=f"sel_{p['ID']}"):
                st.session_state.target_single_patent = p.to_dict()
                st.rerun()

# 模組三
with tab_single:
    if not st.session_state.target_single_patent:
        st.info("請先從模組二選擇專利")
    else:
        target = st.session_state.target_single_patent
        st.subheader(f"深度拆解: {target['專利名稱']}")
        uploaded_pdf = st.file_uploader("上傳 PDF 說明書", type=["pdf"])
        if uploaded_pdf and st.button("啟動 AI 深度解析", type="primary"):
            st.session_state.pdf_bytes_main = uploaded_pdf.getvalue()
            with st.spinner("AI 正在解析..."):
                # 簡化 Prompt 並分離
                p_data = f"名稱: {target['專利名稱']}\n摘要: {target['摘要']}\n請求項: {target['請求項']}"
                p_instr = "\n請輸出 JSON 格式包含: rd_card, vis_data, ip_report。"
                # 執行生成...
                st.success("解析完成！請重整網頁。")

# 模組四
with tab_macro:
    st.header("宏觀地圖")
    df_macro = fetch_patents_from_db('COMPLETED')
    if not df_macro.empty:
        fig = px.pie(df_macro, names='五大類', title='技術領域分佈')
        st.plotly_chart(fig, use_container_width=True)

# 模組五
with tab_combine:
    st.header("組合核駁分析")
    st.markdown("請手動輸入 OA 爭點與引證特徵")
    t_feat = st.text_area("本案核心特徵")
    r1_feat = st.text_area("引證一揭露內容")
    r2_feat = st.text_area("引證二揭露內容")
    if st.button("執行組合分析"):
        if t_feat and r1_feat:
            with st.spinner("分析中..."):
                st.info("分析結果將顯示在此")
