import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# CSSで余白を詰める
st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    div.stButton > button { width: 100%; margin-top: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- Googleスプレッドシート連携関数 ---
@st.cache_resource
def get_spreadsheet():
    try:
        info = json.loads(st.secrets["json_key"])
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except Exception as e:
        st.error(f"Google連携エラー: {e}")
        return None

def load_wrong_words_from_gs():
    sheet = get_spreadsheet()
    if sheet:
        return sheet.get_all_records()
    return []

def add_wrong_word_to_gs(word_dict):
    sheet = get_spreadsheet()
    if sheet:
        existing = sheet.col_values(1)
        if word_dict['en'] not in existing:
            sheet.append_row([word_dict['en'], word_dict['ja']])

def remove_wrong_word_from_gs(en_word):
    sheet = get_spreadsheet()
    if sheet:
        try:
            cell = sheet.find(en_word)
            if cell:
                sheet.delete_rows(cell.row)
        except:
            pass

# --- データ読み込み（words.csv） ---
@st.cache_data
def load_base_data():
    path = "words.csv"
    if not os.path.exists(path):
        st.error("words.csvが見つかりません")
        st.stop()
    for enc in ['utf-8-sig', 'shift_jis']:
        try:
            return pd.read_csv(path, encoding=enc).to_dict('records')
        except:
            continue
    return []

# --- 初期化 ---
if 'word_list' not in st.session_state:
    st.session_state.word_list = load_base_data()

if 'wrong_words' not in st.session_state:
    try:
        st.session_state.wrong_words = load_wrong_words_from_gs()
    except:
        st.session_state.wrong_words = []

# --- モード選択 ---
mode = st.sidebar.radio("モード:", ["全問", "復習"], horizontal=True)

if 'last_mode' not in st.session_state:
    st.session_state.last_mode = mode

if st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    if 'current_question' in st.session_state:
        del st.session_state.current_question

active_list = st.session_state.wrong_words if (mode == "復習" and st.session_state.wrong_words) else st.session_state.word_list

# --- 問題作成 ---
def next_question():
    if not active_list:
        st.session_state.current_question = None
        return
    target = random.choice(active_list)
    others = [w for w in st.session_state.word_list if w['en'] != target['en']]
    choices = random.sample(others, min(len(others), 3)) + [target]
    random.shuffle(choices)
    st.session_state.current_question = {"target": target, "choices": choices, "ans": None}

if 'current_question' not in st.session_state:
    next_question()

# --- クイズ画面 ---
if st.session_state.current_question is None:
    st.info("問題がありません。モードを切り替えてみてください。")
else:
    q = st.session_state.current_question
    st.write(f"**Q: {q['target']['en']}** (苦手:{len(st.session_state.wrong_words)}語)")

    selection = st.radio("選択:", [opt["ja"] for opt in q["choices"]], index=None, key=f"q_{q['target']['en']}", disabled=(q["ans"] is not None), label_visibility="collapsed")

    if selection and q["ans"] is None:
        q["ans"] = selection
        if selection == q["target"]["ja"]:
            st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
            remove_wrong_word_from_gs(q['target']['en']) 
            st.toast("🎯 正解！")
        else:
            if not any(w['en'] == q['target']['en'] for w in st.session_state.wrong_words):
                st.session_state.wrong_words.append(q['target'])
                add_wrong_word_to_gs(q['target'])
            st.toast("❌ 記録しました")
        st.rerun()

    if q["ans"]:
        if q["ans"] == q["target"]["ja"]:
            st.markdown(f"<span style='color:green'>● **正解**: {q['target']['ja']}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='color:red'>● **ミス**: 正解は {q['target']['ja']}</span>", unsafe_allow_html=True)
        
        if st.button("次へ"):
            del st.session_state.current_question
            st.rerun()