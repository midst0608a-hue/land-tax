import datetime
import io
import zipfile
import re

def safe_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    s = s.replace(",", "").replace("$", "").replace("元", "").replace(" ", "")
    if not s:
        return default
    try:
        return float(s)
    except ValueError:
        return default

def safe_int(val, default=0):
    return int(safe_float(val, default))

def format_date_to_taiwan_yyymmdd(date_val):
    """
    將日期（date 或 str）轉換為民國日期格式：YYYMMDD（補零至 7 位數）
    例如：2026-05-22 -> 1150522, 1976-07-09 -> 0650709
    """
    if not date_val:
        return ""
    if isinstance(date_val, (datetime.date, datetime.datetime)):
        year = date_val.year - 1911
        return f"{year:03d}{date_val.month:02d}{date_val.day:02d}"
        
    s = str(date_val).strip()
    s = s.replace("民國", "").replace("年", "-").replace("月", "-").replace("日", "")
    s = s.replace("/", "-").replace(".", "-").replace(" ", "")
    
    if len(s) == 7 and s.isdigit():
        return s
        
    parts = s.split("-")
    if len(parts) == 3:
        try:
            year = int(parts[0])
            if year > 1900:
                year -= 1911
            month = int(parts[1])
            day = int(parts[2])
            return f"{year:03d}{month:02d}{day:02d}"
        except:
            pass
            
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 7:
        return digits
    elif len(digits) == 6:
        return "0" + digits
    elif len(digits) == 8:
        try:
            year = int(digits[:4]) - 1911
            month = int(digits[4:6])
            day = int(digits[6:8])
            return f"{year:03d}{month:02d}{day:02d}"
        except:
            pass
    return date_val

def format_land_number_8_digits(land_num_str):
    """
    將地號格式化為 8 位數（前四位為主號，後四位為子號）
    例如：189-1 -> 01890001, 151 -> 01510000
    """
    if not land_num_str:
        return "00000000"
    s = str(land_num_str).strip()
    for sep in ["-", "之", "_"]:
        s = s.replace(sep, "-")
        
    if "-" in s:
        parts = s.split("-")
        try:
            main = int(parts[0])
            sub = int(parts[1])
            return f"{main:04d}{sub:04d}"
        except:
            pass
    else:
        try:
            main = int(s)
            return f"{main:04d}0000"
        except:
            pass
            
    digits = "".join(c for c in s if c.isdigit())
    if len(digits) == 8:
        return digits
    elif len(digits) > 0:
        try:
            return f"{int(digits):08d}"
        except:
            pass
    return "00000000"

def generate_tax_zip(data: dict, agent: dict, contract_date, reason: str = "買賣", price_type: str = "公告現值", custom_price: float = 0.0) -> bytes:
    """
    根據申報資料與代理人設定，生成符合台灣地方稅申報作業規範的 5 個 CSV 檔案並打包為 ZIP 格式的 bytes。
    """
    # 1. 整理基礎變數
    hsn = agent.get("hsn", "B")
    org = agent.get("org", "49")
    town = agent.get("town", "06")
    agent_id = agent.get("id_number", "L102769057")
    agent_name = agent.get("name", "張培聰")
    agent_tel = agent.get("tel", "0423591548 0963138957")
    agent_addr = agent.get("address", "台中市西屯區工業區38路92號")
    agent_zip = agent.get("zip", "407")
    
    # 決定案件原因代碼與類別
    case_tp = "1"
    tran_reas = "21" if reason == "買賣" else "34"
    
    # 民國立契日期格式化
    flg_date = format_date_to_taiwan_yyymmdd(contract_date or datetime.date.today())
    
    # 取得雙方名單
    sellers = data.get("sellers", [])
    if not sellers and "seller" in data:
        sellers = [data["seller"]]
    buyers = data.get("buyers", [])
    if not buyers and "buyer" in data:
        buyers = [data["buyer"]]
        
    lands = data.get("lands", [])
    if not lands:
        # 建立預設防呆土地
        lands = [{"section": "順和段", "land_number": "0189-0001", "area": 99.02, "holding_numerator": 1, "holding_denominator": 1, "value_per_sqm": 60000}]
        
    # 主土地資訊 (使用第一筆土地)
    main_land = lands[0]
    land_sec = main_land.get("section", "順和段").replace("段", "")
    land_num_raw = main_land.get("land_number", "0189-0001")
    land_num_8 = format_land_number_8_digits(land_num_raw)
    
    land_area = safe_float(main_land.get("area") or 0.0)
    land_num_numerator = safe_float(main_land.get("holding_numerator") or 1.0)
    land_num_denominator = safe_float(main_land.get("holding_denominator") or 1.0)
    
    # 公告現值
    anno_pr_val_prc = safe_float(main_land.get("value_per_sqm") or 0.0)
    
    # 計算移轉面積與公告現值總金額
    # 土地移轉價值 = 面積 * (分子/分母) * 公告現值
    ratio = land_num_numerator / land_num_denominator if land_num_denominator > 0 else 1.0
    tran_area = land_area * ratio
    calculated_price = land_area * ratio * anno_pr_val_prc
    
    if reason == "買賣" and price_type == "自訂買賣價":
        tran_prc = custom_price
    else:
        tran_prc = calculated_price
        
    # 地段代碼與標示號碼
    sec_code = main_land.get("section_code", "0371")  # 預設使用順和段的代號 0371
    lnd_mark = f"{town}{sec_code}{land_num_8}"
    loc_nm = f"{town}區{land_sec} {land_num_8}"
    
    # ----------------------------------------------------
    # A. 產出 HEADER.csv 內容
    # 格式：一行以逗號分隔的數值
    # 欄位：ORG, TOWN, (空), AGENT_ID, null, null, null, null, 4, V105, HSN
    # ----------------------------------------------------
    header_cols = [org, town, "", agent_id, "null", "null", "null", "null", "4", "V105", hsn]
    header_content = ",".join(header_cols) + "\n"
    
    # ----------------------------------------------------
    # B. 產出 AVM001_*.csv 內容 (KEY=VALUE 格式)
    # ----------------------------------------------------
    avm_lines = [
        f"HSN={hsn}",
        f"ORG={org}",
        f"CASE_TP={case_tp}",
        f"TRAN_REAS={tran_reas}",
        f"TRAN_AREA={tran_area:.2f}",
        f"FLG_DATE={flg_date}",
        "NTC_SURDOCU_DATE=",
        f"TRD_DATE={flg_date}",
        f"TOWN={town}",
        f"LUMP_LND_AREA={land_area:.2f}",
        "SLF_NTF=0",
        "CITY_TP=1",
        f"LOC_NM={loc_nm}",
        f"TRAN_RATE_NMRT={int(land_num_numerator)}",
        f"TRAN_RATE_DNT={int(land_num_denominator)}",
        f"ANNO_PR_VAL_PRC={int(anno_pr_val_prc)}",
        f"TRAN_PRC={int(tran_prc)}",
        "LND2= ",
        "LEGAL8=無",
        "LEGAL9=",
        "LEGAL91=",
        "LEGAL92=",
        "F=Y",
        f"LND_MARK={lnd_mark}",
        "LND_PRVLG_MK=Y",
        "HOU_LOSN=",
        "LND_PAY_DOCU_ADDR=同戶籍地址",
        f"O_HOLDERS={len(sellers)}",
        f"N_HOLDERS={len(buyers)}",
        f"AGT_IDN={agent_id}",
        f"AGENT_NM={agent_name}",
        f"AGENT_TEL={agent_tel}",
        f"AGENT_ADD={agent_addr}",
        "CHK7=",
        "CHK11=",
        "CHK12=",
        "CHK13=",
        "CHK14=",
        "CHK2=FALSE",
        "CHK21=",
        "CHK22=",
        "CHK23=",
        "CHK241=N",
        "CHK24=",
        "CHK25=N",
        "CHK26=",
        "CHK31=",
        "CHK32=N",
        "CHK41=",
        "CHK51=",
        "CHK61=",
        "CHKS=",
        f"PRES={len(sellers)}",
        "ANNO_PR_VAL=1"
    ]
    
    # 前次移轉資訊與義務人資訊 (一個義務人對應一個前次移轉資訊)
    for idx, s in enumerate(sellers):
        s_idx = idx + 1
        s_id = s.get("id_number", "L122317568")
        
        # 民國生日
        bday_m = format_date_to_taiwan_yyymmdd(s.get("birthday", ""))
        
        # 前次現值與移轉持分
        prev_year_m = s.get("prev_year_month", "10704")
        prev_price = safe_int(s.get("prev_value_per_sqm") or 19000)
        prev_nmrt = safe_int(s.get("prev_holding_numerator") or 1)
        prev_dnt = safe_int(s.get("prev_holding_denominator") or 2)
        
        pre_val = f"{s_id}_{land_num_8}_{prev_year_m}_{prev_price}_{prev_nmrt}_{prev_dnt}"
        avm_lines.append(f"PRE_{s_idx}={pre_val}")
        
        # 義務人欄位
        avm_lines.append(f"OIDN_BAN_{s_idx}={s_id}")
        avm_lines.append(f"OIDN_NM_{s_idx}={s.get('name', '')}")
        avm_lines.append(f"OBORN_DATE_{s_idx}={bday_m}")
        avm_lines.append(f"O_HOLDER_TRAN_NMRT_{s_idx}={prev_nmrt}")
        avm_lines.append(f"O_HOLDER_TRAN_DNT_{s_idx}={prev_dnt}")
        avm_lines.append(f"O_HOLDER_TEL_{s_idx}=")
        avm_lines.append(f"O_HOLDER_HADDR_{s_idx}={s.get('address', '')}")
        avm_lines.append(f"O_HOLDER_HZIP_{s_idx}=")
        avm_lines.append(f"O_HOLDER_CADDR_{s_idx}=")
        avm_lines.append(f"O_HOLDER_CZIP_{s_idx}=")
        avm_lines.append(f"O_EMAIL_ADDR_{s_idx}=")
        avm_lines.append(f"O_FAX_{s_idx}=")
        avm_lines.append(f"O_PUB_HAVE_{s_idx}=N")
        
        avm_lines.append(f"O_AGT_NAME_{s_idx}_B=")
        avm_lines.append(f"O_AGT_IDN_{s_idx}_B=")
        avm_lines.append(f"O_AGT_ADDR_{s_idx}_B=")
        avm_lines.append(f"O_AGT_TEL_{s_idx}_B=")
        avm_lines.append(f"O_AGT_NAME_{s_idx}_C=")
        avm_lines.append(f"O_AGT_IDN_{s_idx}_C=")
        avm_lines.append(f"O_AGT_ADDR_{s_idx}_C=")
        avm_lines.append(f"O_AGT_TEL_{s_idx}_C=")
        avm_lines.append(f"O_AGT_TYPE_NM_{s_idx}_C=")

    # 權利人資訊
    for idx, b in enumerate(buyers):
        b_idx = idx + 1
        b_id = b.get("id_number", "B160007232")
        bday_m = format_date_to_taiwan_yyymmdd(b.get("birthday", ""))
        
        # 取得權利比例
        b_nmrt = safe_int(b.get("holding_numerator") or 1)
        b_dnt = safe_int(b.get("holding_denominator") or 1)
        
        avm_lines.append(f"NIDN_BAN_{b_idx}={b_id}")
        avm_lines.append(f"NIDN_NM_{b_idx}={b.get('name', '')}")
        avm_lines.append(f"NBORN_DATE_{b_idx}={bday_m}")
        avm_lines.append(f"N_HOLDER_TRAN_NMRT_{b_idx}={b_nmrt}")
        avm_lines.append(f"N_HOLDER_TRAN_DNT_{b_idx}={b_dnt}")
        avm_lines.append(f"N_HOLDER_TEL_{b_idx}=")
        avm_lines.append(f"N_HOLDER_HADDR_{b_idx}={b.get('address', '')}")
        avm_lines.append(f"N_HOLDER_HZIP_{b_idx}={b.get('zip', '407')}")
        avm_lines.append(f"N_HOLDER_CADDR_{b_idx}=")
        avm_lines.append(f"N_HOLDER_CZIP_{b_idx}=")
        avm_lines.append(f"N_EMAIL_ADDR_{b_idx}=")
        avm_lines.append(f"N_FAX_{b_idx}=")
        avm_lines.append(f"N_PUB_HAVE_{b_idx}=N")
        
        avm_lines.append(f"N_AGT_NAME_{b_idx}_B=")
        avm_lines.append(f"N_AGT_IDN_{b_idx}_B=")
        avm_lines.append(f"N_AGT_ADDR_{b_idx}_B=")
        avm_lines.append(f"N_AGT_TEL_{b_idx}_B=")
        avm_lines.append(f"N_AGT_NAME_{b_idx}_C=")
        avm_lines.append(f"N_AGT_IDN_{b_idx}_C=")
        avm_lines.append(f"N_AGT_ADDR_{b_idx}_C=")
        avm_lines.append(f"N_AGT_TEL_{b_idx}_C=")
        avm_lines.append(f"N_AGT_TYPE_NM_{b_idx}_C=")
        
    avm_content = "\n".join(avm_lines) + "\n"
    
    # ----------------------------------------------------
    # C. 產出 SMI01_*.csv 內容 (印花稅憑證 / KEY=VALUE 格式)
    # SMI01 僅需填寫主要買受人（權利人第一位）代表申報
    # ----------------------------------------------------
    main_buyer = buyers[0] if buyers else {"name": "胡協俊", "id_number": "B160007232", "address": "台中市西屯區協和里18鄰工業區三十八路10號", "zip": "407"}
    vouch_amt = int(tran_prc)
    stamp_tax = int(round(vouch_amt * 0.001)) # 千分之一
    
    smi_lines = [
        "VOUCH_NM_CD=02",
        f"VOUCH_TARGET={loc_nm}",
        f"IDN_BAN={main_buyer.get('id_number', '')}",
        f"BAN_NM={main_buyer.get('name', '')}",
        f"BAN_ADDR={main_buyer.get('address', '')}",
        f"ZIP_CD={main_buyer.get('zip', '407')}",
        "TEL_NO=",
        "MOBILEPHONE=",
        "EMAIL=",
        f"AGT_IDN_BAN={agent_id}",
        f"AGT_NM={agent_name}",
        f"AGT_ADDR={agent_addr}",
        f"AGT_ZIP_CD={agent_zip}",
        f"AGT_TEL_NO={agent_tel}",
        "AGT_MOBIL_NO=",
        "AGT_EMAIL=",
        "RESP_NM=",
        "RESP_IDN=",
        f"VOUCH_AMT={vouch_amt}",
        f"VOUCH_APP_DATE={flg_date}",
        f"TAX={stamp_tax}"
    ]
    smi_content = "\n".join(smi_lines) + "\n"
    
    # ----------------------------------------------------
    # D. 產出 CHT001_*.csv 與 SMI02_*.csv 內容 (契稅/空白檔)
    # ----------------------------------------------------
    cht_content = ""
    smi02_content = ""
    
    # ----------------------------------------------------
    # E. 打包為 ZIP 檔案
    # 使用 Big5 (CP950) 編碼以完全相容於台灣地政報稅離線版
    # ----------------------------------------------------
    # 檔名中的日期使用西元格式：YYYYMMDD
    # 例如：1150522 -> 20260522
    west_year = int(flg_date[:3]) + 1911
    filename_date = f"{west_year}{flg_date[3:7]}"
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 寫入 HEADER
        zip_file.writestr(
            f"HEADER_{agent_id}_{filename_date}.csv", 
            header_content.encode("cp950", errors="replace")
        )
        # 寫入 AVM001
        zip_file.writestr(
            f"AVM001_{agent_id}_{filename_date}_N.csv", 
            avm_content.encode("cp950", errors="replace")
        )
        # 寫入 SMI01
        zip_file.writestr(
            f"SMI01_{agent_id}_{filename_date}.csv", 
            smi_content.encode("cp950", errors="replace")
        )
        # 寫入 CHT001
        zip_file.writestr(
            f"CHT001_{agent_id}_{filename_date}.csv", 
            cht_content.encode("cp950", errors="replace")
        )
        # 寫入 SMI02
        zip_file.writestr(
            f"SMI02_{agent_id}_{filename_date}.csv", 
            smi02_content.encode("cp950", errors="replace")
        )
        
    return zip_buffer.getvalue()
