import streamlit as st
import random
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import streamlit.components.v1 as components

# --- 1. ページ設定 ---
st.set_page_config(page_title="英単語マスター", page_icon="🎓", layout="centered")

# --- 2. スタイル設定 ---
def set_button_color(color_code):
    st.markdown(f"""
        <style>
        div.stButton > button:first-child {{
            background-color: {color_code} !important;
            color: white !important;
            border: None !important;
        }}
        h1 {{
            cursor: pointer;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }}
        </style>
    """, unsafe_allow_html=True)

# --- 音声再生ロジック ---
def add_voice_logic(text):
    if text:
        safe_text = text.replace('"', '\\"')
        js_code = f"""
            <script>
            function speak() {{
                window.speechSynthesis.cancel();
                var msg = new SpeechSynthesisUtterance();
                msg.text = "{safe_text}";
                msg.lang = "en-US";
                msg.rate = 1.0;
                window.speechSynthesis.speak(msg);
            }}
            setTimeout(speak, 300);
            const h1Elements = window.parent.document.querySelectorAll('h1');
            h1Elements.forEach(el => {{ el.onclick = speak; }});
            </script>
        """
        components.html(js_code, height=0)

# --- 3. Googleスプレッドシート連携 (高速化) ---
@st.cache_resource
def get_sheet():
    try:
        raw_key = st.secrets["json_key"].strip().lstrip('.')
        info = json.loads(raw_key)
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key(st.secrets["spreadsheet_id"]).sheet1
    except: return None

@st.cache_data(ttl=5)
def load_gs_data():
    sheet = get_sheet()
    if not sheet: return []
    try:
        data = sheet.get_all_values()
        if len(data) < 2: return []
        return [{
            'en': r[0], 'ja': r[1], 
            'count': int(float(r[2])) if len(r)>2 and r[2] else 0,
            'no': int(float(r[3])) if len(r)>3 and r[3] else 0,
            'total_shown': int(float(r[4])) if len(r)>4 and r[4] else 0,
            'is_done': str(r[5]) if len(r)>5 else '0'
        } for r in data[1:] if r[0]]
    except: return []

def sync_result(word_dict, res_type):
    sheet = get_sheet()
    if not sheet: return
    try:
        en_target = str(word_dict['en']).strip()
        # 全データを一度に取得して通信回数を減らす
        data = sheet.get_all_values()
        col1 = [r[0].strip() for r in data]
        
        if en_target in col1:
            row_idx = col1.index(en_target) + 1
            row_data = data[row_idx-1]
            
            # 既存データの更新値を計算
            old_shown = int(float(row_data[4])) if len(row_data)>4 and row_data[4] else 0
            updates = []
            
            # total_shownの更新
            updates.append({'range': gspread.utils.rowcol_to_a1(row_idx, 5), 'values': [[old_shown + 1]]})

            if res_type == 'ok':
                old_count = int(float(row_data[2])) if len(row_data)>2 and row_data[2] else 0
                new_count = old_count + 1
                if new_count >= 5:
                    updates.append({'range': gspread.utils.rowcol_to_a1(row_idx, 3), 'values': [[5]]})
                    updates.append({'range': gspread.utils.rowcol_to_a1(row_idx, 6), 'values': [[1]]})
                else:
                    updates.append({'range': gspread.utils.rowcol_to_a1(row_idx, 3), 'values': [[new_count]]})
            else:
                updates.append({'range': gspread.utils.rowcol_to_a1(row_idx, 3), 'values': [[0]]})
                updates.append({'range': gspread.utils.rowcol_to_a1(row_idx, 6), 'values': [[0]]})
            
            sheet.batch_update(updates)
        else:
            word_no = int(float(word_dict.get('no', 0)))
            is_ok = 1 if res_type == 'ok' else 0
            sheet.append_row([en_target, word_dict['ja'], 5 if is_ok else 0, word_no, 1, 1 if is_ok else 0])
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
            df['no'] = pd.to_numeric(df.get('no', 0), errors='coerce').fillna(0)
            return df.dropna(subset=['en', 'ja']).to_dict('records')
        except: continue
    return []

# --- 4. データ準備 ---
if 'all_words' not in st.session_state:
    st.session_state.all_words = load_csv()

gs_rows = load_gs_data()
pending_words = [d for d in gs_rows if d['is_done'] != '1']
gs_dict = {d['en'].strip(): d for d in gs_rows}

# --- 5. サイドバー ---
st.sidebar.title("🎓 学習メニュー")
mode = st.sidebar.selectbox("モード", ["英→日クイズ", "日→英クイズ", "単語帳"])
st.sidebar.divider()
st.sidebar.metric("復習が必要な単語数", f"{len(pending_words)} 語")

if mode != "単語帳":
    nos = [int(w['no']) for w in st.session_state.all_words] or [0]
    col1, col2 = st.sidebar.columns(2)
    s_no = col1.number_input("開始No.", min(nos), max(nos), min(nos))
    e_no = col2.number_input("終了No.", min(nos), max(nos), max(nos))
    quiz_target = st.sidebar.radio("出題対象", ["全問", "復習のみ"], horizontal=True)

    current_settings = f"{s_no}-{e_no}-{quiz_target}-{mode}"
    if 'last_settings' in st.session_state and st.session_state.last_settings != current_settings:
        st.session_state.reset_q = True
    st.session_state.last_settings = current_settings

    active_list = pending_words if quiz_target == "復習のみ" else [w for w in st.session_state.all_words if s_no <= w['no'] <= e_no]

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 出題頻度のみリセット", use_container_width=True):
        sheet = get_sheet()
        if sheet:
            rows = len(sheet.get_all_values())
            if rows > 1:
                cell_list = sheet.range(2, 5, rows, 5)
                for cell in cell_list: cell.value = 0
                sheet.update_cells(cell_list)
            st.cache_data.clear()
            st.session_state.reset_q = True
            st.rerun()

# --- 6. メインコンテンツ ---
if mode == "単語帳":
    st.title("📖 単語帳")
    st.dataframe(pd.DataFrame(st.session_state.all_words)[['no', 'en', 'ja']], hide_index=True, use_container_width=True)
else:
    if 'q' not in st.session_state or st.session_state.get('reset_q'):
        if not active_list:
            st.warning("対象となる単語がありません。")
            st.stop()
        
        # 重み付け計算の高速化
        weights = [1.0 / (gs_dict.get(str(w['en']).strip(), {}).get('total_shown', 0) + 1.0) for w in active_list]
        
        target = random.choices(active_list, weights=weights, k=1)[0]
        others = random.sample([w for w in st.session_state.all_words if str(w['en']).strip() != str(target['en']).strip()], min(len(st.session_state.all_words)-1, 3))
        choices = others + [target]
        random.shuffle(choices)
        st.session_state.q = {"t": target, "c": choices, "ans": False}
        st.session_state.reset_q = False

    q = st.session_state.q
    m_gs = gs_dict.get(str(q['t']['en']).strip(), {})
    
    # ステータス表示
    if m_gs:
        status = " | ✅ 完了済み" if m_gs['is_done'] == '1' else f" | 🔥 あと {max(0, 5 - m_gs['count'])} 回"
        status += f" | 📊 学習: {m_gs['total_shown']}回目"
    else:
        status = " | 📊 学習: 初回"

    st.write(f"No.{int(float(q['t'].get('no', 0)))}{status}")
    
    question_text = q['t']['en'] if mode == "英→日クイズ" else q['t']['ja']
    st.markdown(f"# {question_text}")
    add_voice_logic(q['t']['en'])

    if not q["ans"]:
        cols = st.columns(2)
        for i, c in enumerate(q["c"]):
            choice_text = c['ja'] if mode == "英→日クイズ" else c['en']
            if cols[i % 2].button(choice_text, key=f"b{i}", use_container_width=True):
                q["ans"] = True
                st.session_state.res_type = "ok" if (str(c['en']).strip() == str(q['t']['en']).strip()) else "ng"
                sync_result(q['t'], st.session_state.res_type)
                st.rerun()
        if st.button("❓ わからない", use_container_width=True):
            q["ans"] = True
            st.session_state.res_type = "unknown"
            sync_result(q['t'], "unknown")
            st.rerun()
    else:
        ans_text = f"{q['t']['en']} : {q['t']['ja']}"
        if st.session_state.res_type == "ok":
            set_button_color("#28a745")
            st.success(f"🎯 正解！\n\n{ans_text}")
        else:
            set_button_color("#dc3545")
            msg = "💡 答え" if st.session_state.res_type == "unknown" else "❌ 残念..."
            st.error(f"{msg}\n\n正解は: {ans_text}")
        
        if st.button("次の問題へ ➡️", use_container_width=True):
            st.session_state.reset_q = True
            st.rerun()

        for choice in q["c"]:
            mark = "✅" if (str(choice['en']).strip() == str(q['t']['en']).strip()) else "・"
            st.write(f"{mark} **{choice['en']}** : {choice['ja']}")
        st.divider()