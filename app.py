import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# --- 1. ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- 2. Googleスプレッドシート連携 (最小限の通信) ---
@st.cache_resource
def get_sheet():
    try:
        raw_key = st.secrets["json_key"].strip().lstrip('.')
        info = json.loads(raw_key)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except:
        return None

@st.cache_data(ttl=300) # 5分間キャッシュ（読み込み速度重視）
def load_gs_data():
    sheet = get_sheet()
    if sheet:
        try:
            return sheet.get_all_records()
        except: return []
    return []

# 書き込み処理（ここが重いので、実行時にメッセージを出さない工夫）
def sync_result(word_dict, is_correct):
    sheet = get_sheet()
    if not sheet: return
    try:
        en = word_dict['en']
        if is_correct:
            cell = sheet.find(en)
            if cell:
                curr = int(sheet.cell(cell.row, 3).value or 0)
                if curr + 1 >= 5: sheet.delete_rows(cell.row)
                else: sheet.update_cell(cell.row, 3, curr + 1)
        else:
            cells = sheet.col_values(1)
            if en not in cells:
                sheet.append_row([en, word_dict['ja'], 0, int(float(word_dict.get('no', 0)))])
    except: pass
    st.cache_data.clear()

@st.cache_data
def load_csv():
    path = "words.csv"
    if not os.path.exists(path): return []
    for enc in ['utf-8-sig', 'shift_jis', 'cp932']:
        try:
            df = pd.read_csv(path, encoding=enc)
            df.columns = df.columns.str.strip()
            df['no'] = pd.to_numeric(df.get('no', range(1, len(df)+1)), errors='coerce').fillna(0)
            return df.dropna(subset=['en', 'ja']).to_dict('records')
        except: continue
    return []

# --- 3. データ準備 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_csv()

# 復習用データ
wrong_data = load_gs_data()
st.session_state.wrong_words = [d for d in wrong_data if d.get('en')]

# --- 4. メイン処理 ---
st.sidebar.title("🔍 メニュー")
mode = st.sidebar.radio("モード", ["クイズ", "辞書"], horizontal=True)

if mode == "辞書":
    st.title("📖 辞書")
    search = st.text_input("検索", "").strip().lower()
    if search:
        res = [w for w in st.session_state.all_words if w['en'].lower().startswith(search)]
        for r in res[:20]: st.write(f"**{r['en']}**: {r['ja']} (No.{int(r['no'])})")
else:
    # クイズ設定
    st.sidebar.markdown("---")
    nos = [int(w['no']) for w in st.session_state.all_words] or [0]
    s_no = st.sidebar.number_input("開始", min(nos), max(nos), min(nos))
    e_no = st.sidebar.number_input("終了", min(nos), max(nos), max(nos))
    quiz_target = st.sidebar.radio("対象", ["全問", "復習"], horizontal=True)
    
    active_list = st.session_state.wrong_words if quiz_target == "復習" else [w for w in st.session_state.all_words if s_no <= w['no'] <= e_no]

    if 'q' not in st.session_state or st.session_state.get('reset_q'):
        if not active_list:
            st.warning("単語がありません")
            st.stop()
        target = random.choice(active_list)
        others = random.sample([w for w in st.session_state.all_words if w['en'] != target['en']], 3)
        choices = others + [target]
        random.shuffle(choices)
        st.session_state.q = {"t": target, "c": choices, "ans": False}
        st.session_state.reset_q = False

    q = st.session_state.q
    st.write(f"No.{int(float(q['t']['no']))}")
    st.markdown(f"# {q['t']['en']}")

    if not q["ans"]:
        cols = st.columns(2)
        for i, c in enumerate(q["c"]):
            with cols[i % 2]:
                if st.button(c["ja"], key=f"b{i}", use_container_width=True):
                    q["ans"] = True
                    st.session_state.is_correct = (c['en'] == q['t']['en'])
                    # 通信は画面表示の「裏」で行うイメージで最後に配置
                    sync_result(q['t'], st.session_state.is_correct)
                    st.rerun()
    else:
        if st.session_state.is_correct: st.success(f"🎯 正解: {q['t']['ja']}")
        else: st.error(f"❌ 正解: {q['t']['ja']}")
        
        if st.button("次へ ➡️", use_container_width=True, type="primary"):
            st.session_state.reset_q = True
            st.rerun()

        st.divider()
        for c in q["c"]:
            st.write(f"{'✅' if c['en']==q['t']['en'] else '・'} **{c['en']}**: {c['ja']}")