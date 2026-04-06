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
        sheet = client.open_by_key(st.secrets["spreadsheet_id"]).sheet1
        if not sheet.get_all_values():
            sheet.append_row(["en", "ja", "count", "no"])
        return sheet
    except Exception as e:
        st.error(f"GS接続エラー: {e}")
        return None

def load_wrong_words():
    sheet = get_spreadsheet()
    if sheet:
        try:
            data = sheet.get_all_records()
            return [d for d in data if d.get('en')]
        except: return []
    return []

def add_wrong_word_to_gs(word_dict):
    sheet = get_spreadsheet()
    if sheet:
        try:
            existing = sheet.col_values(1)
            if word_dict['en'] not in existing:
                sheet.append_row([word_dict['en'], word_dict['ja'], 0, int(word_dict.get('no', 0))])
        except: pass

def update_correct_count_in_gs(en_word):
    sheet = get_spreadsheet()
    if not sheet: return
    try:
        cell = sheet.find(en_word)
        if cell:
            val = sheet.cell(cell.row, 3).value
            count = int(val) if val and str(val).isdigit() else 0
            if count + 1 >= 5:
                sheet.delete_rows(cell.row)
            else:
                sheet.update_cell(cell.row, 3, count + 1)
    except: pass

@st.cache_data
def load_csv_data():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            if 'no' in df.columns:
                df['no'] = pd.to_numeric(df['no'], errors='coerce')
            return df.dropna(subset=['en', 'ja', 'no']).to_dict('records')
        except: continue
    return []

# --- 初期化 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_csv_data()
st.session_state.wrong_words = load_wrong_words()

# --- サイドバー ---
st.sidebar.title("🔍 メニュー")
main_mode = st.sidebar.radio("モード:", ["クイズ", "単語帳"], horizontal=True)

if st.session_state.all_words:
    nos = [int(w['no']) for w in st.session_state.all_words]
    st.sidebar.markdown("---")
    start_no = st.sidebar.number_input("開始No", min(nos), max(nos), min(nos))
    end_no = st.sidebar.number_input("終了No", min(nos), max(nos), max(nos))
    filtered = [w for w in st.session_state.all_words if start_no <= int(w['no']) <= end_no]
    if 'last_range' not in st.session_state or st.session_state.last_range != (start_no, end_no):
        st.session_state.last_range = (start_no, end_no)
        if 'current_q' in st.session_state: del st.session_state.current_q
else:
    filtered = []

if main_mode == "クイズ":
    direction = st.sidebar.radio("方向:", ["英 → 日", "日 → 英"], horizontal=True)
    st.sidebar.metric("復習が必要な単語", f"{len(st.session_state.wrong_words)} 語")
    q_target = st.sidebar.radio("対象:", ["全問", "復習"], horizontal=True)
    if 'last_config' not in st.session_state or st.session_state.last_config != (direction, q_target):
        st.session_state.last_config = (direction, q_target)
        if 'current_q' in st.session_state: del st.session_state.current_q

# --- メイン ---
if main_mode == "単語帳":
    st.title("📑 一覧表示")
    for w in filtered:
        c1, c2, c3 = st.columns([1, 4, 4])
        c1.write(f"{int(w['no'])}")
        c2.write(f"**{w['en']}**")
        c3.write(w['ja'])
        st.divider()

elif main_mode == "クイズ":
    active_list = st.session_state.wrong_words if (q_target == "復習" and st.session_state.wrong_words) else filtered

    if 'current_q' not in st.session_state:
        if not active_list:
            st.session_state.current_q = None
        else:
            target = random.choice(active_list)
            others = [w for w in st.session_state.all_words if w['en'] != target['en']]
            choices = random.sample(others, min(len(others), 3)) + [target]
            random.shuffle(choices)
            st.session_state.current_q = {"target": target, "choices": choices, "answered": False}

    if st.session_state.current_q is None:
        st.warning("対象の単語がありません。")
    else:
        q = st.session_state.current_q
        t = q['target']
        st.markdown(f"### No.{t.get('no', '?')} {'(復習中)' if q_target=='復習' else ''}")
        st.markdown(f"# **{t['en'] if direction=='英 → 日' else t['ja']}**")

        if not q["answered"]:
            cols = st.columns(2)
            for i, c in enumerate(q["choices"]):
                label = c['ja'] if direction == "英 → 日" else c['en']
                with cols[i % 2]:
                    if st.button(label, key=f"b{i}", use_container_width=True):
                        q["answered"] = True
                        if c['en'] == t['en']:
                            st.session_state.res = "ok"
                            update_correct_count_in_gs(t['en'])
                        else:
                            st.session_state.res = "ng"
                            add_wrong_word_to_gs(t)
                        st.rerun()
            
            if st.button("❓ わからない", use_container_width=True):
                q["answered"] = True
                st.session_state.res = "unknown"
                add_wrong_word_to_gs(t)
                st.rerun()
        else:
            # 回答後の表示エリア
            if st.session_state.res == "ok":
                st.success(f"🎯 正解！")
            else:
                st.error(f"❌ 不正解...")

            # 正解の強調表示
            st.info(f"**{t['en']}** = **{t['ja']}**")

            # --- ここが修正ポイント：全選択肢の訳を表示 ---
            st.markdown("---")
            st.write("📖 **今回の選択肢のまとめ:**")
            for c in q["choices"]:
                # 正解にはチェックマークをつける
                mark = "✅" if c['en'] == t['en'] else "・"
                st.write(f"{mark} **{c['en']}** : {c['ja']}")
            st.markdown("---")

            if st.button("次へ ➡️", use_container_width=True):
                del st.session_state.current_q
                st.rerun()