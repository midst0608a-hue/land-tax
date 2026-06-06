import streamlit as st
import sys
import os
import datetime
import tempfile
import importlib

# 確保專案目錄在 sys.path 的最前面，解決 Streamlit Cloud 載入同目錄模組的問題
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    import pandas as pd
    from tax_engine import TaxEngine
    from pdf_parser import DataParser
    import extractor
    importlib.reload(extractor)
    from extractor import GeminiExtractor
    from contract_generator import generate_contract_html, format_date_to_taiwan, generate_application_html, generate_inventory_html
    from tax_file_generator import generate_tax_zip, safe_float, safe_int
except Exception as e:
    import traceback
    st.set_page_config(page_title="系統除錯診斷面板", page_icon="🛠️", layout="wide")
    st.error("🚨 載入系統模組時發生錯誤 (Error Loading Modules)")
    st.markdown("### 錯誤詳細資訊")
    st.code(f"錯誤類型: {type(e).__name__}\n錯誤訊息: {str(e)}")
    
    st.markdown("### 🔍 詳細錯誤追蹤 (Traceback)")
    st.code(traceback.format_exc())
    
    st.markdown("### 📂 系統環境診斷資料")
    st.write(f"目前工作目錄 (CWD): `{os.getcwd()}`")
    st.write(f"腳本所在目錄 (Script Dir): `{os.path.dirname(os.path.abspath(__file__))}`")
    st.write("`sys.path` 清單:")
    st.code("\n".join(sys.path))
    
    st.write("腳本目錄檔案列表:")
    try:
        st.code("\n".join(os.listdir(current_dir)))
    except Exception as list_err:
        st.write(f"無法列出檔案: {list_err}")
    st.stop()

def detect_tax_location(data):
    """
    從萃取出的資料與 truetax_sections.csv 資料庫自動偵測不動產所在的縣市與行政區。
    回傳：(county_key, town_key, org_key)
    """
    county_name = "台中市 (B)" # 預設台中市
    town_name = "西屯區 (06)"   # 預設西屯區
    org_name = "文心分局 (49)"  # 預設文心分局
    
    lands = data.get("lands", [])
    main_land = lands[0] if lands else {}
    sec = main_land.get("section", "")
    clean_sec = str(sec).replace("段", "").replace("小段", "").strip()
    
    # 嘗試從資料庫進行段名查詢
    if clean_sec:
        try:
            import os
            import pandas as pd
            csv_path = os.path.join(os.path.dirname(__file__), "truetax_sections.csv")
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path, dtype=str)
                
                # 先嘗試在台中市（B）進行精確比對
                df_b = df[df['CITY_CD'] == 'B']
                match = df_b[df_b['SEC_CHI_NM'] == clean_sec]
                if not match.empty:
                    town_cd = match.iloc[0]['TOWN_CD']
                    # 對應台中市的行政區與分局
                    taichung_towns = {
                        "01": ("中區 (01)", "民權分局 (43)"),
                        "02": ("東區 (02)", "大智分局 (47)"),
                        "03": ("南區 (03)", "大智分局 (47)"),
                        "04": ("西區 (04)", "民權分局 (43)"),
                        "05": ("北區 (05)", "民權分局 (43)"),
                        "06": ("西屯區 (06)", "文心分局 (49)"),
                        "07": ("南屯區 (07)", "文心分局 (49)"),
                        "08": ("北屯區 (08)", "東山分局 (42)"),
                        "09": ("豐原區 (09)", "豐原分局 (44)"),
                        "10": ("東勢區 (10)", "東勢分局 (45)"),
                        "11": ("大甲區 (11)", "沙鹿分局 (46)"),
                        "12": ("清水區 (12)", "沙鹿分局 (46)"),
                        "13": ("沙鹿區 (13)", "沙鹿分局 (46)"),
                        "14": ("梧棲區 (14)", "沙鹿分局 (46)"),
                        "15": ("后里區 (15)", "豐原分局 (44)"),
                        "16": ("神岡區 (16)", "豐原分局 (44)"),
                        "17": ("潭子區 (17)", "豐原分局 (44)"),
                        "18": ("大雅區 (18)", "豐原分局 (44)"),
                        "19": ("新社區 (19)", "東勢分局 (45)"),
                        "20": ("石岡區 (20)", "東勢分局 (45)"),
                        "21": ("外埔區 (21)", "沙鹿分局 (46)"),
                        "22": ("大安區 (22)", "沙鹿分局 (46)"),
                        "23": ("烏日區 (23)", "大屯分局 (48)"),
                        "24": ("大肚區 (24)", "沙鹿分局 (46)"),
                        "25": ("龍井區 (25)", "沙鹿分局 (46)"),
                        "26": ("霧峰區 (26)", "大屯分局 (48)"),
                        "27": ("太平區 (27)", "大屯分局 (48)"),
                        "28": ("大里區 (28)", "大屯分局 (48)"),
                        "29": ("和平區 (29)", "東勢分局 (45)")
                    }
                    if town_cd in taichung_towns:
                        return ("台中市 (B)", taichung_towns[town_cd][0], taichung_towns[town_cd][1])
                
                # 整個縣市比對
                match = df[df['SEC_CHI_NM'] == clean_sec]
                if not match.empty:
                    city_cd = match.iloc[0]['CITY_CD']
                    town_cd = match.iloc[0]['TOWN_CD']
                    
                    counties_rev = {
                        "A": "台北市 (A)", "B": "台中市 (B)", "C": "基隆市 (C)", "D": "台南市 (D)",
                        "E": "高雄市 (E)", "F": "新北市 (F)", "G": "宜蘭縣 (G)", "H": "桃園市 (H)",
                        "I": "嘉義市 (I)", "J": "新竹縣 (J)", "K": "苗栗縣 (K)", "M": "南投縣 (M)",
                        "N": "彰化縣 (N)", "O": "新竹市 (O)", "P": "雲林縣 (P)", "Q": "嘉義縣 (Q)",
                        "R": "台南縣 (R)", "S": "高雄縣 (S)", "T": "屏東縣 (T)", "U": "花蓮縣 (U)",
                        "V": "台東縣 (V)", "W": "金門縣 (W)", "X": "澎湖縣 (X)", "Z": "連江縣 (Z)"
                    }
                    
                    county_disp = counties_rev.get(city_cd, "台中市 (B)")
                    return (county_disp, town_cd, None)
        except Exception:
            pass
            
    # Fallback keyword matching
    text_to_search = ""
    for l in lands:
        text_to_search += str(l.get("section", "")) + " " + str(l.get("land_number", "")) + " "
        
    if "seller" in data:
        text_to_search += str(data["seller"].get("address", "")) + " "
    if "buyer" in data:
        text_to_search += str(data["buyer"].get("address", "")) + " "
    for s in data.get("sellers", []):
        text_to_search += str(s.get("address", "")) + " "
    for b in data.get("buyers", []):
        text_to_search += str(b.get("address", "")) + " "
        
    counties = {
        "台北": "台北市 (A)", "臺北": "台北市 (A)",
        "台中": "台中市 (B)", "臺中": "台中市 (B)",
        "新北": "新北市 (F)",
        "桃園": "桃園市 (H)",
        "台南": "台南市 (D)", "臺南": "台南市 (D)",
        "高雄": "高雄市 (E)",
        "基隆": "基隆市 (C)",
        "新竹市": "新竹市 (O)",
        "新竹縣": "新竹縣 (J)",
        "苗栗": "苗栗縣 (K)",
        "彰化": "彰化縣 (N)",
        "南投": "南投縣 (M)",
        "雲林": "雲林縣 (P)",
        "嘉義市": "嘉義市 (I)",
        "嘉義縣": "嘉義縣 (Q)",
        "屏東": "屏東縣 (T)",
        "宜蘭": "宜蘭縣 (G)",
        "花蓮": "花蓮縣 (U)",
        "台東": "台東縣 (V)", "臺東": "台東縣 (V)",
        "澎湖": "澎湖縣 (X)",
        "金門": "金門縣 (W)",
        "連江": "連江縣 (Z)"
    }
    
    for key, display_val in counties.items():
        if key in text_to_search:
            county_name = display_val
            break
            
    if "台中市" in county_name:
        taichung_towns_list = [
            ("西屯", "西屯區 (06)", "文心分局 (49)"),
            ("南屯", "南屯區 (07)", "文心分局 (49)"),
            ("中區", "中區 (01)", "民權分局 (43)"),
            ("東區", "東區 (02)", "大智分局 (47)"),
            ("南區", "南區 (03)", "大智分局 (47)"),
            ("西區", "西區 (04)", "民權分局 (43)"),
            ("北區", "北區 (05)", "民權分局 (43)"),
            ("北屯", "北屯區 (08)", "東山分局 (42)"),
            ("豐原", "豐原區 (09)", "豐原分局 (44)"),
            ("東勢", "東勢區 (10)", "東勢分局 (45)"),
            ("大甲", "大甲區 (11)", "沙鹿分局 (46)"),
            ("清水", "清水區 (12)", "沙鹿分局 (46)"),
            ("沙鹿", "沙鹿區 (13)", "沙鹿分局 (46)"),
            ("梧棲", "梧棲區 (14)", "沙鹿分局 (46)"),
            ("后里", "后里區 (15)", "豐原分局 (44)"),
            ("神岡", "神岡區 (16)", "豐原分局 (44)"),
            ("潭子", "潭子區 (17)", "豐原分局 (44)"),
            ("大雅", "大雅區 (18)", "豐原分局 (44)"),
            ("新社", "新社區 (19)", "東勢分局 (45)"),
            ("石岡", "石岡區 (20)", "東勢分局 (45)"),
            ("外埔", "外埔區 (21)", "沙鹿分局 (46)"),
            ("大安", "大安區 (22)", "沙鹿分局 (46)"),
            ("烏日", "烏日區 (23)", "大屯分局 (48)"),
            ("大肚", "大肚區 (24)", "沙鹿分局 (46)"),
            ("龍井", "龍井區 (25)", "沙鹿分局 (46)"),
            ("霧峰", "霧峰區 (26)", "大屯分局 (48)"),
            ("太平", "太平區 (27)", "大屯分局 (48)"),
            ("大里", "大里區 (28)", "大屯分局 (48)"),
            ("和平", "和平區 (29)", "東勢分局 (45)")
        ]
        
        for kw, town_disp, org_disp in taichung_towns_list:
            if kw in text_to_search:
                town_name = town_disp
                org_name = org_disp
                break
                
        return (county_name, town_name, org_name)
    else:
        return (county_name, None, None)

st.set_page_config(page_title="台灣不動產全能工作站", page_icon="🏦", layout="wide")

st.title("🏦 台灣不動產全能工作站")

# 設定 API Key
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

with st.sidebar:
    st.header("⚙️ 全域設定")
    api_key_input = st.text_input("請輸入 Google Gemini API Key", type="password", value=st.session_state.api_key)
    if api_key_input:
        st.session_state.api_key = api_key_input
        
    st.markdown("---")
    st.markdown("### 💡 如何取得 API Key？")
    st.markdown("1. 前往 [Google AI Studio](https://aistudio.google.com/)")
    st.markdown("2. 登入 Google 帳號並點擊 Get API key")
    
    st.markdown("---")
    st.header("💼 申報代理人（代書）設定")
    agent_name = st.text_input("代理人姓名", value="張培聰")
    agent_id = st.text_input("代理人身分證字號", value="L102769057")
    agent_tel = st.text_input("聯絡電話", value="0423591548 0963138957")
    agent_addr = st.text_input("服務地址", value="台中市西屯區工業區38路92號")
    agent_zip = st.text_input("郵遞區號", value="407")
    
    # 預設申報轄區與機關代碼（會在 Tab 4 中依據謄本自動偵測與進行選單微調）
    agent_hsn = "B"
    agent_org = "49"
    agent_town = "06"
    
    agent_info = {
        "name": agent_name,
        "id_number": agent_id,
        "tel": agent_tel,
        "address": agent_addr,
        "zip": agent_zip,
        "hsn": agent_hsn,
        "org": agent_org,
        "town": agent_town
    }

tab1, tab2, tab3, tab4 = st.tabs(["🧮 土地增值稅試算", "📄 智能資料萃取", "🔍 智能案卷預審", "✍️ 智能契約生成"])

with tab1:
    st.markdown("上傳土地謄本 (PDF) 與物價指數表 (Excel)，系統將自動擷取所有土地並批次試算土地增值稅。 (自動略過建物謄本)")
    
    # 建立暫存資料夾
    if 'temp_dir' not in st.session_state:
        st.session_state.temp_dir = tempfile.mkdtemp()

    # ==========================================
    # 1. 檔案上傳與解析區
    # ==========================================
    st.header("1. 檔案上傳區")
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        pdf_file = st.file_uploader("📄 上傳土地登記謄本 (PDF)", type=['pdf'])
    with col_up2:
        excel_file = st.file_uploader("📊 上傳物價指數表 (Excel)", type=['xlsx', 'xls'])
    
    if st.button("🔍 解析文件提取資料", type="primary"):
        if pdf_file is not None:
            with st.spinner("正在解析 PDF 內容..."):
                pdf_path = os.path.join(st.session_state.temp_dir, "temp.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(pdf_file.getbuffer())
                
                # 執行批次解析
                extracted_parcels = DataParser.extract_from_pdf(pdf_path)
                
                if len(extracted_parcels) > 0 and "error" in extracted_parcels[0]:
                    st.error(extracted_parcels[0]["error"])
                elif len(extracted_parcels) == 0:
                    st.warning("找不到任何土地謄本資料。請確認檔案格式或是否僅包含建物謄本。")
                else:
                    st.success(f"✅ 解析成功！共找到 {len(extracted_parcels)} 筆土地謄本。")
                    
                    # 初始化 DataFrame 結構
                    df_data = []
                    for p in extracted_parcels:
                        df_data.append({
                            "地號": p["id"],
                            "所有權人": p.get("owner_name", ""),
                            "統一編號": p.get("owner_id", ""),
                            "面積": p["area"],
                            "持分分子": p["holding_numerator"],
                            "持分分母": p["holding_denominator"],
                            "前次現值": p["original_value"],
                            "前次年": p["original_year"],
                            "前次月": p["original_month"],
                            "本次現值": p["present_value"],
                            "自定扣除額": 0.0,
                            "自用住宅": False
                        })
                    st.session_state.parcels_df = pd.DataFrame(df_data)
                    st.session_state.extracted_parcels = extracted_parcels
                    
                    # Debug 面板：讓使用者可以查看原始萃取出的文字
                    with st.expander("🛠️ (除錯用) 查看 PDF 轉出的原始文字"):
                        st.write("請將下方的文字截圖或複製給 AI，這樣 AI 就能知道文字到底是怎麼排列的！")
                        for p in extracted_parcels:
                            st.markdown(f"**{p['id']}**")
                            st.text(p["extracted_text"])
                    
                    # 如果有上傳 Excel，一併處理
                    if excel_file is not None:
                        excel_path = os.path.join(st.session_state.temp_dir, excel_file.name)
                        with open(excel_path, "wb") as f:
                            f.write(excel_file.getbuffer())
                        st.session_state.excel_path = excel_path
                        st.info("已成功讀取物價指數 Excel 檔案。")
                    else:
                        st.session_state.excel_path = None
                        st.warning("未上傳物價指數表，計算時預設指數將為 100% (無調整)")
        else:
            st.error("請先上傳 PDF 檔案！")
    
    st.divider()

    # ==========================================
    # 2. 參數確認與計算區
    # ==========================================
    if 'parcels_df' in st.session_state:
        st.header("2. 參數確認與批次修改")
        st.markdown("您可以直接在下方的表格中修改數字、打勾「自用住宅」，甚至是新增/刪除列（點擊表格邊緣即可操作）。")
        
        # 全局設定 (本次申報年月)
        col_cy, col_cm = st.columns(2)
        today = datetime.datetime.now()
        curr_year = col_cy.number_input("本次申報 (民國年)", value=today.year - 1911, step=1)
        curr_month = col_cm.number_input("本次申報 (月份)", value=today.month, min_value=1, max_value=12, step=1)
        
        # 呈現資料編輯器
        edited_df = st.data_editor(
            st.session_state.parcels_df, 
            num_rows="dynamic", 
            use_container_width=True,
            column_config={
                "自用住宅": st.column_config.CheckboxColumn("自用住宅 (10%)", default=False)
            }
        )
        
        if st.button("🧮 執行批次稅額計算", type="primary", use_container_width=True):
            st.divider()
            st.header("3. 計算結果與明細")
            
            total_tax_payable = 0
            results_list = []
            
            # 逐列計算
            for index, row in edited_df.iterrows():
                land_id = row.get("地號", f"第 {index+1} 筆土地")
                area = float(row.get("面積", 0))
                ratio_num = float(row.get("持分分子", 1))
                ratio_den = float(row.get("持分分母", 1))
                orig_val = float(row.get("前次現值", 0))
                orig_year = int(row.get("前次年", 100))
                orig_month = int(row.get("前次月", 1))
                pres_val = float(row.get("本次現值", 0))
                deductions = float(row.get("自定扣除額", 0))
                is_self_use = bool(row.get("自用住宅", False))
                
                # 計算持有年限
                calc_hold_years = max(0, curr_year - orig_year)
                if curr_month < orig_month and calc_hold_years > 0:
                    calc_hold_years -= 1
                    
                # 取得 CPI
                cpi = 100.0
                if st.session_state.get('excel_path'):
                    cpi = DataParser.get_cpi_from_excel(st.session_state.excel_path, orig_year, orig_month)
                    
                if ratio_den == 0:
                    st.error(f"{land_id}: 持分分母不可為 0！已略過計算。")
                    continue
                    
                # 呼叫計算引擎
                result = TaxEngine.calculate_lvit(
                    present_value=pres_val,
                    original_value=orig_val,
                    cpi=cpi,
                    area=area,
                    holding_ratio_numerator=ratio_num,
                    holding_ratio_denominator=ratio_den,
                    deductions=deductions,
                    holding_years=calc_hold_years,
                    is_self_use=is_self_use
                )
                
                total_tax_payable += result['tax_payable']
                results_list.append({
                    "land_id": land_id,
                    "result": result
                })
                
            # 顯示總計
            st.success(f"### 💰 所有土地應納稅額總計： {total_tax_payable:,.0f} 元")
            
            # 顯示各筆明細
            st.markdown("#### 每一筆土地的計算明細")
            for r in results_list:
                land_id = r["land_id"]
                res = r["result"]
                steps = res.get("steps", {})
                
                with st.expander(f"📍 {land_id} - 應納稅額: {res['tax_payable']:,.0f} 元 [{res['tax_rate_level']}]"):
                    col_d1, col_d2 = st.columns(2)
                    
                    with col_d1:
                        st.markdown("**1️⃣ 計算稅基 (按物價調整後原規定地價總額)**")
                        st.latex(r"\text{稅基} = \text{前次現值} \times \frac{\text{CPI}}{100} \times \text{面積} \times \text{持分}")
                        st.write(f"$= {steps.get('original_value_adjusted', 0):,.0f} \\times {steps.get('area', 0)} \\times {steps.get('holding_ratio', 0):.4f}$")
                        st.write(f"$= {res['tax_base']:,.0f}$ 元")
                        
                        st.markdown("**2️⃣ 計算土地漲價總數額**")
                        st.latex(r"\text{漲價總數額} = \text{本次申報現值總額} - \text{稅基} - \text{扣除額}")
                        st.write(f"$= {steps.get('present_value_total', 0):,.0f} - {res['tax_base']:,.0f} - {steps.get('deductions', 0):,.0f}$")
                        st.write(f"$= {res['total_increment']:,.0f}$ 元")
                        
                    with col_d2:
                        st.markdown("**3️⃣ 判斷漲價倍數與稅率**")
                        st.latex(r"\text{漲價倍數} = \frac{\text{漲價總數額}}{\text{稅基}}")
                        st.write(f"$= {res['increment_ratio']:.2f}$ 倍")
                        st.write(f"👉 適用級距：**{res['tax_rate_level']}**")
                        
                        st.markdown("**4️⃣ 最終應納稅額**")
                        st.write(f"👉 持有年限：**{steps.get('holding_years', 0)} 年**")
                        st.info(f"**最終稅額： {res['tax_payable']:,.0f} 元**")

with tab2:
    st.header("📄 謄本與身分證自動萃取神器")
    st.markdown("上傳紙本掃描圖檔、PDF、或身分證件，AI 將自動辨識所有權人、地址、統編等資訊並輸出純文字。")
    
    if not st.session_state.api_key:
        st.warning("⚠️ 請先在左側欄輸入您的 Google Gemini API Key 才能開啟此功能！")
    else:
        uploaded_file2 = st.file_uploader("請上傳圖檔或 PDF", type=["pdf", "jpg", "jpeg", "png"], key="extractor_up")
        if uploaded_file2 is not None:
            if 'temp_dir' not in st.session_state:
                st.session_state.temp_dir = tempfile.mkdtemp()
            file_path = os.path.join(st.session_state.temp_dir, "extract_" + uploaded_file2.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file2.getbuffer())
                
            file_ext = uploaded_file2.name.split(".")[-1].lower()
            
            st.info("🤖 AI 正在努力閱讀並萃取資料中，請稍候 (約需 5~15 秒)...")
            extractor = GeminiExtractor(api_key=st.session_state.api_key)
            
            with st.spinner("解析中..."):
                if file_ext == "pdf":
                    result = extractor.process_pdf(file_path)
                else:
                    result = extractor.process_image(file_path)
                    
            if "error" in result:
                st.error(f"❌ 發生錯誤：{result['error']}")
                if "raw" in result:
                    with st.expander("查看原始 AI 回覆"):
                        st.text(result["raw"])
            else:
                st.success("✅ 萃取成功！")
                data_list = result["data"]
                if not isinstance(data_list, list):
                    data_list = [data_list]
                    
                if len(data_list) == 0:
                    st.warning("AI 沒有在這份文件中找到相符的資料。")
                else:
                    formatted_text = ""
                    for i, record in enumerate(data_list):
                        formatted_text += f"【紀錄 {i+1}】\n"
                        keys_order = ["地號", "面積", "持分", "現值", "所有權人", "統一編號", "前次移轉現值", "歷次取得範圍", "地址"]
                        
                        for key in keys_order:
                            if key in record and record[key]:
                                formatted_text += f"{key}：{record[key]}\n"
                                
                        for key, value in record.items():
                            if key not in keys_order and value:
                                formatted_text += f"{key}：{value}\n"
                                
                        formatted_text += "\n"
                        
                    st.markdown("### 📋 萃取結果 (可直接複製)")
                    st.code(formatted_text.strip(), language="text")

with tab3:
    st.header("🔍 智能案卷預審 (AI Pre-Review)")
    st.markdown("上傳要審核的公契、土地登記申請書等公文影像，輸入案件背景描述，AI 將自動與地政審查規範進行對照，分析填寫疏漏、文件完整度或欄位不一致的潛在風險。")
    
    if not st.session_state.api_key:
        st.warning("⚠️ 請先在左側欄輸入您的 Google Gemini API Key 才能開啟此功能！")
    else:
        # 建立案件背景描述區
        case_desc_input = st.text_area(
            "📝 請輸入案件口語描述 (背景資訊)",
            placeholder="例如：本案為夫妻贈與所有權移轉登記，先生（義務人）將大安區土地贈與給太太（權利人），由地政士代理送件。先生有欠繳地價稅已補繳，檢附補繳收據。",
            height=150
        )
        
        # 檢查是否有預設手冊並提示使用者
        default_manual_name = "土地登記審查手冊.pdf"
        default_manual_path = os.path.join(os.path.dirname(__file__), default_manual_name)
        has_default_manual = os.path.exists(default_manual_path)
        
        if has_default_manual:
            st.info(f"💡 系統偵測到預設手冊「{default_manual_name}」，若不另行上傳自訂手冊，將自動以此進行比對與預審。")
        else:
            st.warning(f"⚠️ 尚未偵測到預設審查手冊。您可以將「{default_manual_name}」放置於專案目錄下以供自動載入，或在下方直接上傳手冊。")

        col_rev1, col_rev2 = st.columns(2)
        with col_rev1:
            uploaded_doc = st.file_uploader("📄 上傳要審查的文件 (公契/申請書/附件PDF或圖檔)", type=["pdf", "jpg", "jpeg", "png"], key="reviewer_doc")
        with col_rev2:
            uploaded_manual = st.file_uploader("📘 (選填) 上傳自訂審查手冊或指引 PDF", type=["pdf"], key="reviewer_manual")
            
        if st.button("🚀 開始智能預審", type="primary", use_container_width=True):
            if not case_desc_input.strip():
                st.error("請先輸入案件描述！")
            elif uploaded_doc is None:
                st.error("請先上傳要審查的文件！")
            else:
                if 'temp_dir' not in st.session_state:
                    st.session_state.temp_dir = tempfile.mkdtemp()
                    
                # 儲存要審查的文件
                doc_path = os.path.join(st.session_state.temp_dir, "review_doc_" + uploaded_doc.name)
                with open(doc_path, "wb") as f:
                    f.write(uploaded_doc.getbuffer())
                
                doc_ext = uploaded_doc.name.split(".")[-1].lower()
                doc_mime = "application/pdf" if doc_ext == "pdf" else (f"image/{doc_ext}" if doc_ext in ["png", "jpeg"] else "image/jpeg")
                
                # 儲存審查手冊 (優先使用上傳的，其次使用預設的)
                manual_path = None
                manual_mime = None
                if uploaded_manual is not None:
                    manual_path = os.path.join(st.session_state.temp_dir, "review_manual_" + uploaded_manual.name)
                    with open(manual_path, "wb") as f:
                        f.write(uploaded_manual.getbuffer())
                    manual_mime = "application/pdf"
                elif has_default_manual:
                    manual_path = default_manual_path
                    manual_mime = "application/pdf"
                
                st.info("🤖 AI 正在比對公契與手冊中，可能需要 10~20 秒，請稍候...")
                extractor = GeminiExtractor(api_key=st.session_state.api_key)
                
                with st.spinner("AI 審查比對中..."):
                    review_result = extractor.process_review(
                        doc_path=doc_path,
                        doc_mime=doc_mime,
                        case_desc=case_desc_input,
                        manual_path=manual_path,
                        manual_mime=manual_mime
                    )
                    
                if "error" in review_result:
                    st.error(f"❌ 審查失敗：{review_result['error']}")
                else:
                    st.success("✅ 預審查完成！")
                    st.markdown(review_result["report"])

with tab4:
    st.header("✍️ 土地所有權移轉契約書智能生成")
    st.markdown("上傳您的土地登記謄本、出賣人（義務人）與買受人（權利人）的身分證件。AI 將自動辨識雙方姓名、身分證字號、住所與土地標示，套入符合地政官方格式的契約書，並提供下載 Word（HTML相容）格式的契約檔案。")
    
    if not st.session_state.api_key:
        st.warning("⚠️ 請先在左側欄輸入您的 Google Gemini API Key 才能開啟此功能！")
    else:
        st.markdown("### 1. 上傳檔案 (支援 PDF 或圖檔，可分開上傳)")
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        with col_c1:
            up_land = st.file_uploader("📄 土地登記謄本", type=["pdf", "png", "jpg", "jpeg"], key="c_up_land")
        with col_c2:
            up_building = st.file_uploader("🏢 建物登記謄本", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, key="c_up_building")
        with col_c3:
            up_sellers = st.file_uploader("👤 出賣人 (義務人) 身分證件", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, key="c_up_seller")
        with col_c4:
            up_buyers = st.file_uploader("👤 買受人 (權利人) 身分證件", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True, key="c_up_buyer")
            
        st.markdown("### 2. 契約設定參數")
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            contract_reason = st.selectbox("登記原因", ["買賣", "贈與"], index=0, key="c_reason")
            contract_date = st.date_input("立約日期", datetime.date.today(), key="c_date")
        with col_s2:
            price_type = st.selectbox("契約價格認定方式", ["公告現值自動計算", "自訂買賣價"], index=0, key="c_price_type")
            custom_price = st.number_input("自訂買賣價 (元)", min_value=0.0, value=0.0, step=10000.0, key="c_custom_price")
            
        if st.button("✨ 一鍵智能生成公契契約書", type="primary", use_container_width=True):
            if 'temp_dir' not in st.session_state:
                st.session_state.temp_dir = tempfile.mkdtemp()
                
            land_path, land_mime = None, None
            building_paths, building_mimes = [], []
            seller_paths, seller_mimes = [], []
            buyer_paths, buyer_mimes = [], []
            
            with st.spinner("正在讀取並分析上傳的文件，此步驟可能需要 10-25 秒，請稍候..."):
                if up_land:
                    ext = up_land.name.split(".")[-1].lower()
                    land_path = os.path.join(st.session_state.temp_dir, f"land_temp.{ext}")
                    with open(land_path, "wb") as f:
                        f.write(up_land.getbuffer())
                    land_mime = "application/pdf" if ext == "pdf" else f"image/{ext}"
                    
                if up_building:
                    for idx, up_bld in enumerate(up_building):
                        ext = up_bld.name.split(".")[-1].lower()
                        b_path = os.path.join(st.session_state.temp_dir, f"building_temp_{idx}.{ext}")
                        with open(b_path, "wb") as f:
                            f.write(up_bld.getbuffer())
                        building_paths.append(b_path)
                        building_mimes.append("application/pdf" if ext == "pdf" else f"image/{ext}")
                    
                if up_sellers:
                    for idx, up_sel in enumerate(up_sellers):
                        ext = up_sel.name.split(".")[-1].lower()
                        s_path = os.path.join(st.session_state.temp_dir, f"seller_temp_{idx}.{ext}")
                        with open(s_path, "wb") as f:
                            f.write(up_sel.getbuffer())
                        seller_paths.append(s_path)
                        seller_mimes.append("application/pdf" if ext == "pdf" else f"image/{ext}")
                    
                if up_buyers:
                    for idx, up_buy in enumerate(up_buyers):
                        ext = up_buy.name.split(".")[-1].lower()
                        b_path = os.path.join(st.session_state.temp_dir, f"buyer_temp_{idx}.{ext}")
                        with open(b_path, "wb") as f:
                            f.write(up_buy.getbuffer())
                        buyer_paths.append(b_path)
                        buyer_mimes.append("application/pdf" if ext == "pdf" else f"image/{ext}")
                    
                extractor = GeminiExtractor(api_key=st.session_state.api_key)
                result = extractor.process_contract_extraction(
                    land_doc_path=land_path, land_doc_mime=land_mime,
                    building_doc_paths=building_paths, building_doc_mimes=building_mimes,
                    seller_id_paths=seller_paths, seller_id_mimes=seller_mimes,
                    buyer_id_paths=buyer_paths, buyer_id_mimes=buyer_mimes
                )
                
                if "error" in result:
                    st.error(f"❌ 生成失敗：{result['error']}")
                else:
                    # 初始化 sellers 與 buyers 與 buildings 列表以支援多所有權人、建物與報稅
                    extracted_data = result["data"]
                    if "sellers" not in extracted_data:
                        if "seller" in extracted_data:
                            extracted_data["sellers"] = [extracted_data["seller"]]
                        else:
                            extracted_data["sellers"] = []
                    if "buyers" not in extracted_data:
                        if "buyer" in extracted_data:
                            extracted_data["buyers"] = [extracted_data["buyer"]]
                        else:
                            extracted_data["buyers"] = []
                    if "buildings" not in extracted_data:
                        if "building" in extracted_data:
                            extracted_data["buildings"] = [extracted_data["building"]]
                        else:
                            extracted_data["buildings"] = []
                            
                    st.session_state.extracted_contract_data = extracted_data
                    
                    # 自動偵測不動產轄區與稅務分局，並更新 selectbox 的預設值
                    county_key, town_key, org_key = detect_tax_location(extracted_data)
                    st.session_state.detected_county = county_key
                    st.session_state.detected_town = town_key
                    st.session_state.detected_org = org_key
                    
                    if extracted_data["sellers"]:
                        extracted_data["seller"] = extracted_data["sellers"][0]
                    if extracted_data["buyers"]:
                        extracted_data["buyer"] = extracted_data["buyers"][0]
                        
                    st.session_state.generated_contract_html = generate_contract_html(
                        data=extracted_data,
                        contract_type=contract_reason,
                        contract_date=contract_date,
                        price_type=price_type,
                        custom_price=custom_price
                    )
                    st.rerun()
                    
        # 顯示生成後的預覽與編輯調整
        if "generated_contract_html" in st.session_state and "extracted_contract_data" in st.session_state:
            st.success("✅ 契約書已智能生成！")
            
            # 提供使用者手動微調
            with st.expander("🛠️ (可選) 檢視與調整 AI 萃取出的欄位資料"):
                st.info("如果 AI 辨識的統編、姓名或地址有微小偏差，您可以在下方表格中直接修正，系統會即時重新生成契約書與報稅申報預覽！")
                data = st.session_state.extracted_contract_data
                
                # 取得或初始化列表
                sellers_list = data.get("sellers", [])
                if not sellers_list and "seller" in data:
                    sellers_list = [data["seller"]]
                for s in sellers_list:
                    s.setdefault("name", "")
                    s.setdefault("id_number", "")
                    s.setdefault("birthday", "")
                    s.setdefault("address", "")
                    s.setdefault("prev_year_month", "10704")
                    s.setdefault("prev_value_per_sqm", 19000.0)
                    s.setdefault("prev_holding_numerator", 1.0)
                    s.setdefault("prev_holding_denominator", 2.0)
                
                st.markdown("##### 👥 出賣人（義務人）名單")
                edited_sellers = st.data_editor(
                    pd.DataFrame(sellers_list), 
                    num_rows="dynamic", 
                    key="edit_sellers_df",
                    use_container_width=True,
                    column_config={
                        "name": st.column_config.TextColumn("姓名", width="medium"),
                        "id_number": st.column_config.TextColumn("身分證字號/統編", width="medium"),
                        "birthday": st.column_config.TextColumn("出生年月日", width="medium"),
                        "address": st.column_config.TextColumn("戶籍地址", width="large"),
                        "prev_year_month": st.column_config.TextColumn("前次移轉年月 (如10704)", width="small"),
                        "prev_value_per_sqm": st.column_config.NumberColumn("前次現值 (元/㎡)", width="small"),
                        "prev_holding_numerator": st.column_config.NumberColumn("前次持分分子", width="small"),
                        "prev_holding_denominator": st.column_config.NumberColumn("前次持分分母", width="small")
                    }
                )
                data["sellers"] = edited_sellers.to_dict(orient="records")
                if data["sellers"]:
                    data["seller"] = data["sellers"][0]
                
                buyers_list = data.get("buyers", [])
                if not buyers_list and "buyer" in data:
                    buyers_list = [data["buyer"]]
                for b in buyers_list:
                    b.setdefault("name", "")
                    b.setdefault("id_number", "")
                    b.setdefault("birthday", "")
                    b.setdefault("address", "")
                    b.setdefault("holding_numerator", 1.0)
                    b.setdefault("holding_denominator", 1.0)
                    b.setdefault("zip", "407")
                    
                st.markdown("##### 👥 買受人（權利人）名單")
                edited_buyers = st.data_editor(
                    pd.DataFrame(buyers_list),
                    num_rows="dynamic",
                    key="edit_buyers_df",
                    use_container_width=True,
                    column_config={
                        "name": st.column_config.TextColumn("姓名", width="medium"),
                        "id_number": st.column_config.TextColumn("身分證字號/統編", width="medium"),
                        "birthday": st.column_config.TextColumn("出生年月日", width="medium"),
                        "address": st.column_config.TextColumn("戶籍地址", width="large"),
                        "holding_numerator": st.column_config.NumberColumn("持分分子", width="small"),
                        "holding_denominator": st.column_config.NumberColumn("持分分母", width="small"),
                        "zip": st.column_config.TextColumn("郵遞區號", width="small")
                    }
                )
                data["buyers"] = edited_buyers.to_dict(orient="records")
                if data["buyers"]:
                    data["buyer"] = data["buyers"][0]
                
                st.markdown("##### 📍 土地標示資訊")
                lands_list = data.get("lands", [])
                if not lands_list:
                    lands_list = [{"section": "順和段", "land_number": "0189-0001", "area": 99.02, "holding_numerator": 1.0, "holding_denominator": 1.0, "value_per_sqm": 60000.0}]
                for l in lands_list:
                    l.setdefault("section", "順和段")
                    l.setdefault("land_number", "0189-0001")
                    l.setdefault("area", 99.02)
                    l.setdefault("holding_numerator", 1.0)
                    l.setdefault("holding_denominator", 1.0)
                    l.setdefault("value_per_sqm", 60000.0)
                    
                edited_lands = st.data_editor(
                    pd.DataFrame(lands_list), 
                    num_rows="dynamic", 
                    key="edit_lands_df",
                    use_container_width=True,
                    column_config={
                        "section": st.column_config.TextColumn("段名", width="medium"),
                        "land_number": st.column_config.TextColumn("地號 (如0189-0001)", width="medium"),
                        "area": st.column_config.NumberColumn("面積 (㎡)", width="small"),
                        "holding_numerator": st.column_config.NumberColumn("持分分子", width="small"),
                        "holding_denominator": st.column_config.NumberColumn("持分分母", width="small"),
                        "value_per_sqm": st.column_config.NumberColumn("公告現值", width="small")
                    }
                )
                data["lands"] = edited_lands.to_dict(orient="records")
                
                st.markdown("##### 🏢 建物標示資訊")
                buildings_list = data.get("buildings", [])
                for b in buildings_list:
                    b.setdefault("building_number", "")
                    b.setdefault("door_number", "")
                    b.setdefault("land_number", "")
                    b.setdefault("area_details", "")
                    b.setdefault("total_area", 0.0)
                    b.setdefault("attached_area", "")
                    b.setdefault("holding_numerator", 1.0)
                    b.setdefault("holding_denominator", 1.0)
                    b.setdefault("value_per_sqm", 0.0)
                    b.setdefault("remarks", "")
                    
                edited_buildings = st.data_editor(
                    pd.DataFrame(buildings_list),
                    num_rows="dynamic",
                    key="edit_buildings_df",
                    use_container_width=True,
                    column_config={
                        "building_number": st.column_config.TextColumn("建號", width="small"),
                        "door_number": st.column_config.TextColumn("門牌號碼", width="medium"),
                        "land_number": st.column_config.TextColumn("基地坐落地號", width="medium"),
                        "area_details": st.column_config.TextColumn("層次面積明細", width="medium"),
                        "total_area": st.column_config.NumberColumn("主建物總面積 (㎡)", width="small"),
                        "attached_area": st.column_config.TextColumn("附屬建物明細", width="small"),
                        "holding_numerator": st.column_config.NumberColumn("移轉持分分子", width="small"),
                        "holding_denominator": st.column_config.NumberColumn("移轉持分分母", width="small"),
                        "value_per_sqm": st.column_config.NumberColumn("評定現值", width="small"),
                        "remarks": st.column_config.TextColumn("備註", width="small")
                    }
                )
                data["buildings"] = edited_buildings.to_dict(orient="records")
                
                st.markdown("##### 💼 登記代理人 (地政士) 資訊設定")
                col_ag1, col_ag2, col_ag3 = st.columns(3)
                with col_ag1:
                    agent_name = st.text_input("代理人姓名", value=data.get("agent", {}).get("name", "張培聰"), key="c_agent_name")
                    agent_id = st.text_input("身分證統一編號", value=data.get("agent", {}).get("id_number", "L102769057"), key="c_agent_id")
                with col_ag2:
                    agent_birthday = st.text_input("出生年月日", value=data.get("agent", {}).get("birthday", "民國 41.8.13"), key="c_agent_birthday")
                    agent_tel = st.text_input("聯絡電話", value=data.get("agent", {}).get("tel", "04-23591548"), key="c_agent_tel")
                with col_ag3:
                    agent_addr = st.text_input("事務所地址", value=data.get("agent", {}).get("address", "台中市西屯區工業區38路92號"), key="c_agent_addr")
                    agent_remarks = st.text_input("登記申請書備註", value=data.get("agent", {}).get("remarks", "本案係申報土地建物所有權移轉登記。"), key="c_agent_remarks")

                data["agent"] = {
                    "name": agent_name,
                    "id_number": agent_id,
                    "birthday": agent_birthday,
                    "tel": agent_tel,
                    "address": agent_addr,
                    "remarks": agent_remarks,
                    "hsn_name": "台中市",
                    "org_name": "龍井"
                }

                st.markdown("##### 📄 附繳證件清單設定 (土地登記申請書用)")
                if contract_reason == "買賣":
                    default_docs = [
                        "土地建物買賣所有權移轉契約書正、副本各 1份",
                        "登記清冊 1份",
                        "雙方身分證明文件各 1份",
                        "土地、建物所有權狀 1份",
                        "出賣人印鑑證明 1份",
                        "土地增值稅、契稅繳清證明書各 1份"
                    ]
                else: # 贈與
                    default_docs = [
                        "土地建物贈與所有權移轉契約書正、副本各 1份",
                        "登記清冊 1份",
                        "雙方身分證明文件各 1份",
                        "土地、建物所有權狀 1份",
                        "贈與人印鑑證明 1份",
                        "土地增值稅、契稅繳清證明書各 1份",
                        "贈與稅免稅或繳清證明書 1份"
                    ]
                
                if "prev_contract_reason" not in st.session_state or st.session_state.prev_contract_reason != contract_reason:
                    st.session_state.prev_contract_reason = contract_reason
                    st.session_state.attached_docs_value = "\n".join(default_docs)
                    
                doc_text = st.text_area("附繳證件明細 (每行一個證件，最多12個)", value=st.session_state.attached_docs_value, height=140, key="attached_docs_textarea")
                st.session_state.attached_docs_value = doc_text
                selected_docs = [d.strip() for d in doc_text.split("\n") if d.strip()]
                
                st.markdown("##### 📍 申報轄區與機關設定")
                st.caption("💡 縣市別 (HSN)、稽徵機關 (ORG)、鄉鎮市區 (TOWN) 為地方稅網路申報系統之大批匯入規定的行政代號。")
                
                county_map = {
                    "台中市 (B)": "B",
                    "台北市 (A)": "A",
                    "新北市 (F)": "F",
                    "桃園市 (H)": "H",
                    "台南市 (D)": "D",
                    "高雄市 (E)": "E",
                    "基隆市 (C)": "C",
                    "新竹市 (O)": "O",
                    "新竹縣 (J)": "J",
                    "苗栗縣 (K)": "K",
                    "彰化縣 (N)": "N",
                    "南投縣 (M)": "M",
                    "雲林縣 (P)": "P",
                    "嘉義市 (I)": "I",
                    "嘉義縣 (Q)": "Q",
                    "台南縣 (R)": "R",
                    "高雄縣 (S)": "S",
                    "屏東縣 (T)": "T",
                    "宜蘭縣 (G)": "G",
                    "花蓮縣 (U)": "U",
                    "台東縣 (V)": "V",
                    "澎湖縣 (X)": "X",
                    "金門縣 (W)": "W",
                    "連江縣 (Z)": "Z"
                }
                
                county_list = list(county_map.keys())
                default_county_idx = 0
                if "detected_county" in st.session_state and st.session_state.detected_county in county_list:
                    default_county_idx = county_list.index(st.session_state.detected_county)
                    
                selected_county = st.selectbox(
                    "縣市別 (HSN)", 
                    county_list, 
                    index=default_county_idx, 
                    help="地方稅申報系統之縣市代碼（例如 B 代表台中市）。",
                    key="tab4_selected_county"
                )
                agent_hsn = county_map[selected_county]
                
                if agent_hsn == "B":
                    taichung_org_map = {
                        "文心分局 (49)": "49",
                        "東山分局 (42)": "42",
                        "民權分局 (43)": "43",
                        "豐原分局 (44)": "44",
                        "東勢分局 (45)": "45",
                        "沙鹿分局 (46)": "46",
                        "大智分局 (47)": "47",
                        "大屯分局 (48)": "48",
                        "地方稅務局總局 (41)": "41"
                    }
                    taichung_org_list = list(taichung_org_map.keys())
                    default_org_idx = 0
                    if "detected_org" in st.session_state and st.session_state.detected_org in taichung_org_list:
                        default_org_idx = taichung_org_list.index(st.session_state.detected_org)
                        
                    selected_org = st.selectbox(
                        "稽徵機關 (ORG)", 
                        taichung_org_list, 
                        index=default_org_idx,
                        help="申報所屬地方稅務局分局代碼。",
                        key="tab4_selected_org"
                    )
                    agent_org = taichung_org_map[selected_org]
                    
                    taichung_town_map = {
                        "西屯區 (06)": "06",
                        "中區 (01)": "01",
                        "東區 (02)": "02",
                        "南區 (03)": "03",
                        "西區 (04)": "04",
                        "北區 (05)": "05",
                        "南屯區 (07)": "07",
                        "北屯區 (08)": "08",
                        "豐原區 (09)": "09",
                        "東勢區 (10)": "10",
                        "大甲區 (11)": "11",
                        "清水區 (12)": "12",
                        "沙鹿區 (13)": "13",
                        "梧棲區 (14)": "14",
                        "后里區 (15)": "15",
                        "神岡區 (16)": "16",
                        "潭子區 (17)": "17",
                        "大雅區 (18)": "18",
                        "新社區 (19)": "19",
                        "石岡區 (20)": "20",
                        "外埔區 (21)": "21",
                        "大安區 (22)": "22",
                        "烏日區 (23)": "23",
                        "大肚區 (24)": "24",
                        "龍井區 (25)": "25",
                        "霧峰區 (26)": "26",
                        "太平區 (27)": "27",
                        "大里區 (28)": "28",
                        "和平區 (29)": "29"
                    }
                    taichung_town_list = list(taichung_town_map.keys())
                    default_town_idx = 0
                    if "detected_town" in st.session_state and st.session_state.detected_town in taichung_town_list:
                        default_town_idx = taichung_town_list.index(st.session_state.detected_town)
                        
                    selected_town = st.selectbox(
                        "鄉鎮市區 (TOWN)", 
                        taichung_town_list, 
                        index=default_town_idx,
                        help="申報土地所屬行政區代碼（例如 06 代表西屯區）。",
                        key="tab4_selected_town"
                    )
                    agent_town = taichung_town_map[selected_town]
                else:
                    col_org_custom, col_town_custom = st.columns(2)
                    
                    default_org_val = "41"
                    default_town_val = "01"
                    
                    detected_org = st.session_state.get("detected_org")
                    detected_town = st.session_state.get("detected_town")
                    
                    if detected_org:
                        default_org_val = str(detected_org).split("(")[-1].replace(")", "").strip()
                    if detected_town:
                        default_town_val = str(detected_town).split("(")[-1].replace(")", "").strip()
                        
                    with col_org_custom:
                        agent_org = st.text_input("稽徵機關 (ORG)", value=default_org_val, help="請輸入對應縣市的稽徵機關代碼。", key="tab4_selected_org_custom")
                    with col_town_custom:
                        agent_town = st.text_input("鄉鎮市區 (TOWN)", value=default_town_val, help="請輸入對應縣市的鄉鎮市區代碼。", key="tab4_selected_town_custom")
                        
                agent_info = {
                    "name": agent_name,
                    "id_number": agent_id,
                    "tel": agent_tel,
                    "address": agent_addr,
                    "zip": agent_zip,
                    "hsn": agent_hsn,
                    "org": agent_org,
                    "town": agent_town
                }
                    
                st.session_state.extracted_contract_data = data
                
                # 即時重新生成 HTML
                st.session_state.generated_contract_html = generate_contract_html(
                    data=data,
                    contract_type=contract_reason,
                    contract_date=contract_date,
                    price_type=price_type,
                    custom_price=custom_price
                )

            # 計算預覽與印花稅資訊
            total_contract_price = 0.0
            for land in data.get("lands", []):
                area = safe_float(land.get("area") or 0.0)
                num_num = safe_float(land.get("holding_numerator") or 1.0)
                num_den = safe_float(land.get("holding_denominator") or 1.0)
                val_per_sqm = safe_float(land.get("value_per_sqm") or 0.0)
                ratio = num_num / num_den if num_den > 0 else 1.0
                total_contract_price += area * ratio * val_per_sqm
                
            if contract_reason == "買賣" and price_type == "自訂買賣價":
                final_price = custom_price
            else:
                final_price = total_contract_price
                
            stamp_tax = int(round(final_price * 0.001))
            tran_reas = "21" if contract_reason == "買賣" else "34"

            # ----------------------------------------------------
            # 地方稅網路申報資料預覽 (Checklist)
            # ----------------------------------------------------
            st.divider()
            st.markdown("### 📋 地方稅網路申報預覽核對表")
            st.info("💡 請先核對以下自動彙整的土地增值稅與印花稅申報內容。確認無誤後，即可於下方下載線上報稅匯入檔 (.zip)。")
            
            with st.container(border=True):
                st.markdown("<h4 style='text-align: center; color: #1E3A8A; margin-top: 10px; margin-bottom: 20px;'>土地增值稅暨印花稅大批申報核對表</h4>", unsafe_allow_html=True)
                
                col_i1, col_i2, col_i3 = st.columns(3)
                with col_i1:
                    st.metric("申報土地移轉總金額 (現值)", f"{final_price:,.0f} 元")
                with col_i2:
                    st.metric("應納印花稅 (千分之一憑證稅)", f"{stamp_tax:,.0f} 元", "1‰ 課徵率")
                with col_i3:
                    st.metric("案件登記原因", f"{contract_reason} (原因代碼: {tran_reas})")
                
                st.markdown("---")
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    st.markdown("**📂 申報案件基礎設定**")
                    st.markdown(f"""
                    - **申報縣市別 (HSN)**: `{agent_info['hsn']}` (台中市)
                    - **主轄稽徵機關 (ORG)**: `{agent_info['org']}` (分局代號)
                    - **申報鄉鎮市區 (TOWN)**: `{agent_info['town']}`
                    - **立契申報日期 (TRD_DATE)**: `{format_date_to_taiwan(contract_date)}`
                    - **移轉價格認定**: `{price_type}` (金額: {final_price:,.0f} 元)
                    """)
                with col_d2:
                    st.markdown("**💼 申報代理人 (地政士/代書) 資訊**")
                    st.markdown(f"""
                    - **代理人姓名**: `{agent_info['name']}`
                    - **統一編號/身分證**: `{agent_info['id_number']}`
                    - **聯絡電話**: `{agent_info['tel']}`
                    - **通訊地址**: `{agent_info['address']}` (郵遞區號: `{agent_info['zip']}`)
                    """)
                
                st.markdown("---")
                st.markdown("**📍 申報土地標示明細**")
                land_preview_data = []
                for idx, land in enumerate(data.get("lands", [])):
                    sec = land.get("section", "")
                    num = land.get("land_number", "")
                    area = safe_float(land.get("area") or 0.0)
                    num_num = safe_float(land.get("holding_numerator") or 1.0)
                    num_den = safe_float(land.get("holding_denominator") or 1.0)
                    val_per_sqm = safe_float(land.get("value_per_sqm") or 0.0)
                    holding_ratio = f"{int(num_num)}/{int(num_den)}" if num_den > 1 else "全部"
                    
                    ratio = num_num / num_den if num_den > 0 else 1.0
                    tran_a = area * ratio
                    land_val = tran_a * val_per_sqm
                    
                    land_preview_data.append({
                        "序號": idx+1,
                        "土地坐落": f"{sec}段 {num}地號",
                        "面積 (㎡)": f"{area:,.2f}",
                        "移轉比例": holding_ratio,
                        "移轉持分面積 (㎡)": f"{tran_a:,.2f}",
                        "公告現值 (元/㎡)": f"{val_per_sqm:,.0f}",
                        "本次移轉土地總值 (元)": f"{land_val:,.0f}"
                    })
                st.table(pd.DataFrame(land_preview_data))
                
                col_sb1, col_sb2 = st.columns(2)
                with col_sb1:
                    st.markdown("**👤 出賣人 (義務人/原所有權人) 資訊**")
                    for idx, s in enumerate(data.get("sellers", [])):
                        st.markdown(f"""
                        **出賣人 {idx+1}: {s.get('name', '無姓名')}**
                        - 統一編號/統編: `{s.get('id_number', '')}`
                        - 出生日期: `{s.get('birthday', '')}`
                        - 戶籍住所: `{s.get('address', '')}`
                        - 前次移轉年月: `{s.get('prev_year_month', '10704')}`
                        - 前次申報現值: `{safe_int(s.get('prev_value_per_sqm') or 19000):,} 元/㎡`
                        - 前次取得持分: `{safe_int(s.get('prev_holding_numerator') or 1)}/{safe_int(s.get('prev_holding_denominator') or 2)}`
                        """)
                with col_sb2:
                    st.markdown("**👤 買受人 (權利人/新所有權人) 資訊**")
                    for idx, b in enumerate(data.get("buyers", [])):
                        st.markdown(f"""
                        **買受人 {idx+1}: {b.get('name', '無姓名')}**
                        - 統一編號/統編: `{b.get('id_number', '')}`
                        - 出生日期: `{b.get('birthday', '')}`
                        - 戶籍住所: `{b.get('address', '')}` (郵遞區號: `{b.get('zip', '407')}`)
                        - 移轉取得持分: `{safe_int(b.get('holding_numerator') or 1)}/{safe_int(b.get('holding_denominator') or 1)}`
                        """)
                        
            # 下載按鈕區域
            st.markdown("### 📥 申報檔案與公契下載")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                # 產出土地所有權移轉契約書 HTML
                has_b = len(data.get("buildings", [])) > 0
                file_name = f"土地{'建物' if has_b else ''}{contract_reason}所有權移轉契約書.html"
                st.download_button(
                    label=f"📥 下載土地{'建物' if has_b else ''}{contract_reason}移轉契約書 (A4 Word 格式)",
                    data=st.session_state.generated_contract_html,
                    file_name=file_name,
                    mime="text/html",
                    use_container_width=True
                )
            with col_dl2:
                # 產出大批匯入申報 ZIP
                try:
                    tax_zip_bytes = generate_tax_zip(
                        data=data,
                        agent=agent_info,
                        contract_date=contract_date,
                        reason=contract_reason,
                        price_type=price_type,
                        custom_price=custom_price
                    )
                    west_year = contract_date.year
                    filename_date = f"{west_year}{contract_date.month:02d}{contract_date.day:02d}"
                    zip_filename = f"TAX_IMPORT_{agent_info['id_number']}_{filename_date}.zip"
                    
                    st.download_button(
                        label="📥 下載線上報稅匯入檔 (.zip)",
                        data=tax_zip_bytes,
                        file_name=zip_filename,
                        mime="application/zip",
                        use_container_width=True
                    )
                except Exception as e_zip:
                    st.error(f"無法產生報稅檔案：{str(e_zip)}")
            
            # 土地登記申請書 與 登記清冊 下載
            col_dl3, col_dl4 = st.columns(2)
            with col_dl3:
                app_html = generate_application_html(
                    data=data,
                    agent_info=data.get("agent", {}),
                    documents=selected_docs,
                    contract_type=contract_reason,
                    contract_date=contract_date
                )
                st.download_button(
                    label="📥 下載土地登記申請書 (A4 Word 格式)",
                    data=app_html,
                    file_name="土地登記申請書.html",
                    mime="text/html",
                    use_container_width=True
                )
            with col_dl4:
                inv_html = generate_inventory_html(
                    data=data,
                    contract_type=contract_reason,
                    contract_date=contract_date
                )
                st.download_button(
                    label="📥 下載登記清冊 (A4 Word 格式)",
                    data=inv_html,
                    file_name="登記清冊.html",
                    mime="text/html",
                    use_container_width=True
                )
            
            # HTML 預覽
            st.markdown("### 📄 契約書線上預覽 (以下為 A4 預覽樣式)")
            st.components.v1.html(st.session_state.generated_contract_html, height=800, scrolling=True)

