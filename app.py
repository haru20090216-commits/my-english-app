import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- Googleスプレッドシート連携 ---
@st.cache_resource
def get_spreadsheet():
    try:
        raw_key = st.secrets["json_key"].strip().lstrip('.')
        info = json.loads(raw_key)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except:
        return None

def add_wrong_word_to_gs(word_dict):
    sheet = get_spreadsheet()
    if sheet:
        try:
            existing = sheet.col_values(1)
            if word_dict['en'] not in existing:
                sheet.append_row([word_dict['en'], word_dict['ja']])
        except: pass

def remove_wrong_word_from_gs(en_word):
    sheet = get_spreadsheet()
    if sheet:
        try:
            cell = sheet.find(en_word)
            if cell: sheet.delete_rows(cell.row)
        except: pass

# --- データ読み込み ---
@st.cache_data
def load_base_data():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            # no列を数値型に変換
            if 'no' in df.columns:
                df['no'] = pd.to_numeric(df['no'], errors='coerce')
            return df.dropna(subset=['en', 'ja']).to_dict('records')
        except: continue
    return []

# --- 初期化 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_base_data()

if 'wrong_words' not in st.session_state:
    from_gs = []
    try:
        sheet = get_spreadsheet()
        if sheet: from_gs = sheet.get_all_records()
    except: pass
    st.session_state.wrong_words = from_gs

# --- サイドバー：設定 ---
st.sidebar.title("🛠 設定")

# 1. 範囲設定
if st.session_state.all_words:
    nos = [int(w['no']) for w in st.session_state.all_words if 'no' in w and not pd.isna(w['no'])]
    if nos:
        min_v, max_v = min(nos), max(nos)
        # スライダーの値が変わったら問題をリセットするための仕組み
        range_select = st.sidebar.slider("出題範囲 (No.)", min_v, max_v, (min_v, max_v), key="range_slider")
        
        # フィルタリング
        filtered_words = [w for w in st.session_state.all_words if range_select[0] <= int(w['no']) <= range_select[1]]
        
        # 範囲が以前と変わったかチェック
        if 'last_range' not in st.session_state or st.session_state.last_range != range_select:
            st.session_state.last_range = range_select
            if 'current_question' in st.session_state:
                del st.session_state.current_question # 範囲が変わったら今の問題を破棄
    else:
        filtered_words = st.session_state.all_words
else:
    filtered_words = []

# 2. モード選択
wrong_count = len(st.session_state.wrong_words)
st.sidebar.metric("現在の復習単語数", f"{wrong_count} 語")
mode = st.sidebar.radio("モード:", ["全問", "復習"], horizontal=True)

if 'last_mode' not in st.session_state: st.session_state.last_mode = mode
if st.session_state.last_mode != mode:
    st.session_state.last_mode = mode
    if 'current_question' in st.session_state: del st.session_state.current_question

# --- 出題リストの決定 ---
if mode == "復習" and st.session_state.wrong_words:
    active_list = st.session_state.wrong_words
else:
    active_list = filtered_words

# --- 問題作成関数 ---
def next_question():
    if not active_list:
        st.session_state.current_question = None
    else:
        target = random.choice(active_list)
        # 選択肢は全単語から（難易度を保つため）
        others = [w for w in st.session_state.all_words if w['en'] != target['en']]
        choices = random.sample(others, min(len(others), 3)) + [target]
        random.shuffle(choices)
        st.session_state.current_question = {"target": target, "choices": choices, "answered": False}

if 'current_question' not in st.session_state:
    next_question()

# --- メイン画面 ---
if not st.session_state.all_words:
    st.error("words.csvが正しく読み込めていません。'no', 'en', 'ja' の列があるか確認してください。")
elif st.session_state.current_question is None:
    st.warning("選択された範囲に単語がありません。")
else:
    q = st.session_state.current_question
    no_txt = f"No.{int(q['target']['no'])} " if 'no' in q['target'] else ""
    st.markdown(f"### {no_txt}")
    st.markdown(f"# **{q['target']['en']}**")

    if not q["answered"]:
        cols = st.columns(2)
        for i, choice in enumerate(q["choices"]):
            with cols[i % 2]:
                if st.button(choice["ja"], key=f"btn_{i}", use_container_width=True):
                    q["answered"] = True
                    if choice["ja"] == q["target"]["ja"]:
                        st.session_state.result_type = "correct"
                        st.session_state.wrong_words = [w for w in st.session_state.wrong_words if w['en'] != q['target']['en']]
                        remove_wrong_word_from_gs(q['target']['en'])
                    else:
                        st.session_state.result_type = "wrong"
                        if not any(w['en'] == q['target']['en'] for w in st.session_state.wrong_words):
                            st.session_state.wrong_words.append(q['target'])
                            add_wrong_word_to_gs(q['target'])
                    st.rerun()
        
        st.write("")
        if st.button("❓ わからない", key="dont_know", use_container_width=True):
            q["answered"] = True
            st.session_state.result_type = "unknown"
            if not any(w['en'] == q['target']['en'] for w in st.session_state.wrong_words):
                st.session_state.wrong_words.append(q['target'])
                add_wrong_word_to_gs(q['target'])
            st.rerun()
    else:
        if st.session_state.result_type == "correct":
            st.success(f"🎯 正解！: {q['target']['ja']}")
        elif st.session_state.result_type == "unknown":
            st.warning(f"💡 覚えておきましょう: {q['target']['ja']}")
        else:
            st.error(f"❌ 不正解... 正解は: {q['target']['ja']}")
        
        st.write("---")
        st.write("💡 **今回の復習:**")
        for c in q["choices"]:
            mark = "✅" if c['en'] == q['target']['en'] else "・"
            st.write(f"{mark} **{c['en']}** : {c['ja']}")
        
        if st.button("次の問題へ ➡️", use_container_width=True):
            del st.session_state.current_question
            st.rerun()