import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- ページ設定 ---
st.set_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

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
                no_val = word_dict.get('no', 0)
                sheet.append_row([word_dict['en'], word_dict['ja'], 0, int(float(no_val))])
        except: pass

def update_correct_count_in_gs(en_word):
    sheet = get_spreadsheet()
    if not sheet: return False
    try:
        cell = sheet.find(en_word)
        if cell:
            val = sheet.cell(cell.row, 3).value
            current_count = int(val) if val and str(val).isdigit() else 0
            new_count = current_count + 1
            if new_count >= 5:
                sheet.delete_rows(cell.row)
            else:
                sheet.update_cell(cell.row, 3, new_count)
    except: pass
    return False

@st.cache_data
def load_base_data():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            if 'no' not in df.columns:
                df['no'] = range(1, len(df) + 1)
            df['no'] = pd.to_numeric(df['no'], errors='coerce').fillna(0)
            return df.dropna(subset=['en', 'ja']).to_dict('records')
        except: continue
    return []

def load_wrong_words():
    sheet = get_spreadsheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            return [d for d in data if d.get('en')]
        except: return []
    return []

# --- データの読み込み ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_base_data()
st.session_state.wrong_words = load_wrong_words()

# --- サイドバー ---
st.sidebar.title("🔍 メニュー")
mode = st.sidebar.radio("モード切替:", ["クイズ", "辞書"], horizontal=True)

filtered_words = []
if mode == "クイズ":
    st.sidebar.markdown("---")
    st.sidebar.title("🛠 出題設定")
    if st.session_state.all_words:
        nos = [int(w['no']) for w in st.session_state.all_words]
        min_n, max_n = min(nos), max(nos)
        start_no = st.sidebar.number_input("開始番号", min_n, max_n, min_n)
        end_no = st.sidebar.number_input("終了番号", min_n, max_n, max_n)
        filtered_words = [w for w in st.session_state.all_words if start_no <= int(w['no']) <= end_no]
        if 'last_range' not in st.session_state or st.session_state.last_range != (start_no, end_no):
            st.session_state.last_range = (start_no, end_no)
            if 'current_question' in st.session_state: del st.session_state.current_question
    
    st.sidebar.metric("現在の復習単語数", f"{len(st.session_state.wrong_words)} 語")
    quiz_mode = st.sidebar.radio("出題対象:", ["全問", "復習"], horizontal=True)
    if 'last_quiz_mode' not in st.session_state or st.session_state.last_quiz_mode != quiz_mode:
        st.session_state.last_quiz_mode = quiz_mode
        if 'current_question' in st.session_state: del st.session_state.current_question

# --- メインコンテンツ ---
if mode == "辞書":
    st.title("📖 単語検索辞書")
    search_q = st.text_input("検索 (英単語を入力)", "").strip().lower()
    if search_q:
        results = [w for w in st.session_state.all_words if w['en'].lower().startswith(search_q)]
        for res in results:
            with st.expander(f"📌 {res['en']}"):
                st.write(f"意味: {res['ja']} (No.{int(res['no'])})")
    else:
        st.info("英単語を入力してください。")

elif mode == "クイズ":
    active_list = st.session_state.wrong_words if (quiz_mode == "復習") else filtered_words

    if 'current_question' not in st.session_state:
        if not active_list:
            st.session_state.current_question = None
        else:
            target = random.choice(active_list)
            pool = st.session_state.all_words if st.session_state.all_words else active_list
            others = [w for w in pool if w['en'] != target['en']]
            choices = random.sample(others, min(len(others), 3)) + [target]
            random.shuffle(choices)
            st.session_state.current_question = {"target": target, "choices": choices, "answered": False}

    if st.session_state.current_question is None:
        st.warning("⚠️ 出題できる単語がありません。設定を確認してください。")
    else:
        q = st.session_state.current_question
        t = q['target']
        
        q_no = t.get('no', '?')
        q_count = t.get('count', 0)
        try: display_count = int(q_count)
        except: display_count = 0
        
        c_info = f" (あと {5 - display_count} 回)" if quiz_mode == "復習" else ""
        st.markdown(f"### No.{int(float(q_no))}{c_info}")
        st.markdown(f"# **{t['en']}**")

        if not q["answered"]:
            cols = st.columns(2)
            for i, choice in enumerate(q["choices"]):
                with cols[i % 2]:
                    if st.button(choice["ja"], key=f"btn_{i}", use_container_width=True):
                        q["answered"] = True
                        if choice["ja"] == t["ja"]:
                            st.session_state.res_type = "ok"
                            update_correct_count_in_gs(t['en'])
                        else:
                            st.session_state.res_type = "ng"
                            add_wrong_word_to_gs(t)
                        st.session_state.wrong_words = load_wrong_words()
                        st.rerun()
            
            if st.button("❓ わからない", key="dont_know", use_container_width=True):
                q["answered"] = True
                st.session_state.res_type = "unknown"
                add_wrong_word_to_gs(t)
                st.session_state.wrong_words = load_wrong_words()
                st.rerun()
        else:
            # 回答後の表示（ボタンを上に配置）
            if st.session_state.res_type == "ok":
                st.success(f"🎯 正解: {t['ja']}")
            elif st.session_state.res_type == "unknown":
                st.warning(f"💡 意味: {t['ja']}")
            else:
                st.error(f"❌ 不正解... 正解は: {t['ja']}")
            
            # 【ここが修正ポイント】ボタンを先に表示
            if st.button("次の問題へ ➡️", use_container_width=True, type="primary"):
                del st.session_state.current_question
                st.rerun()
            
            st.write("---")
            # 選択肢のまとめを下に表示
            for c in q["choices"]:
                m = "✅" if c['en'] == t['en'] else "・"
                st.write(f"{m} **{c['en']}** : {c['ja']}")