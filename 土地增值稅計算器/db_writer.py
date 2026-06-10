import os
import json
import tempfile
import subprocess
import datetime

def write_case_to_db(db_path: str, data: dict, agent_info: dict, contract_reason: str, contract_date) -> dict:
    """
    將萃取並過濾後的不動產案件資料寫入代書軟體資料庫 LandAgent.mdb 中。
    使用 Windows 原生 PowerShell + OLEDB 進行交易式寫入，不需額外安裝 Python 套件。
    """
    if not os.path.exists(db_path):
        return {"success": False, "error": f"找不到資料庫檔案：{db_path}"}

    # 格式化立約日期 (例如: 11506100205)
    today = datetime.datetime.now()
    taiwan_year = contract_date.year - 1911 if contract_date else today.year - 1911
    month = contract_date.month if contract_date else today.month
    day = contract_date.day if contract_date else today.day
    
    # 產生案件編號 (BIOID)
    bioid = f"{taiwan_year:03d}{month:02d}{day:02d}{today.hour:02d}{today.minute:02d}{today.second:02d}"
    
    # 案件類型描述
    doc_name = f"土地{'建物' if data.get('buildings') else ''}{contract_reason}所有權移轉登記"
    
    # 組合 JSON 資料 payload
    payload = {
        "bioid": bioid,
        "agent_name": agent_info.get("name", "張培聰"),
        "agent_id": agent_info.get("id_number", "L102769057"),
        "agent_birthday": agent_info.get("birthday", "民國 41.8.13"),
        "agent_tel": agent_info.get("tel", "04-23591548"),
        "agent_address": agent_info.get("address", "台中市西屯區工業區38路92號"),
        "doc_name": doc_name,
        "city_name": agent_info.get("city_name", "台中市").replace(" (B)", "").replace(" (A)", ""),
        "area_name": agent_info.get("area_name", "西屯區").split(" (")[0],
        "docdate": f"{contract_date.year}/{contract_date.month:02d}/{contract_date.day:02d}" if contract_date else today.strftime("%Y/%m/%d"),
        "doctime": today.strftime("%H:%M:%S"),
        "sellers": [],
        "buyers": [],
        "lands": [],
        "buildings": []
    }
    
    # 整理當事人 (義務人 PE00 = 義務人, 權利人 PE00 = 權利人)
    for s in data.get("sellers", []):
        payload["sellers"].append({
            "name": s.get("name", ""),
            "id_number": s.get("id_number", ""),
            "birthday": s.get("birthday", ""),
            "address": s.get("address", ""),
            "numerator": int(s.get("prev_holding_numerator") or 1),
            "denominator": int(s.get("prev_holding_denominator") or 2),
            "tel": s.get("tel", ""),
            # 前次移轉資料
            "prev_year_month": s.get("prev_year_month", "10704"),
            "prev_value": int(s.get("prev_value_per_sqm") or 19000)
        })
        
    for b in data.get("buyers", []):
        payload["buyers"].append({
            "name": b.get("name", ""),
            "id_number": b.get("id_number", ""),
            "birthday": b.get("birthday", ""),
            "address": b.get("address", ""),
            "numerator": int(b.get("holding_numerator") or 1),
            "denominator": int(b.get("holding_denominator") or 1),
            "tel": b.get("tel", "")
        })
        
    # 整理土地
    for l in data.get("lands", []):
        num = int(l.get("holding_numerator") or 1)
        den = int(l.get("holding_denominator") or 1)
        ratio = num / den if den > 0 else 1.0
        area = float(l.get("area") or 0.0)
        val = float(l.get("value_per_sqm") or 0.0)
        
        payload["lands"].append({
            "section": l.get("section", ""),
            "land_number": l.get("land_number", ""),
            "holding_str": f"{num}/{den}",
            "value_per_sqm": val,
            "area": area,
            "total_price": area * ratio * val
        })
        
    # 整理建物與樓層明細
    for idx, b in enumerate(data.get("buildings", [])):
        num = int(b.get("holding_numerator") or 1)
        den = int(b.get("holding_denominator") or 1)
        ratio = num / den if den > 0 else 1.0
        
        payload["buildings"].append({
            "building_number": b.get("building_number", ""),
            "door_number": b.get("door_number", ""),
            "land_number": b.get("land_number", ""),
            "total_area": float(b.get("total_area") or 0.0),
            "attached_area": b.get("attached_area", ""),
            "holding_ratio": ratio,
            # 樓層拆解 (如果有明細格式，例如「一層 43.30, 二層 56.46」)
            "floors": parse_building_floors(b.get("area_details", ""))
        })

    # 建立 PowerShell 腳本寫入資料庫
    ps_script = """
Param(
    [string]$jsonPath,
    [string]$dbPath
)

$data = Get-Content $jsonPath -Raw | ConvertFrom-Json
$connStr = "Provider=Microsoft.ACE.OLEDB.12.0;Data Source=$dbPath;"

try {
    $conn = New-Object System.Data.OleDb.OleDbConnection($connStr)
    $conn.Open()
    
    $transaction = $conn.BeginTransaction()
    
    # 產生全新的 GUID 關聯所有表格
    $guid = "{" + [Guid]::NewGuid().ToString().ToUpper() + "}"
    
    # 1. 寫入 Main
    $cmd = $conn.CreateCommand()
    $cmd.Transaction = $transaction
    $cmd.CommandText = "INSERT INTO [Main] (ISNEED, GUID, BIOID, USERID, USER_NAME, DOC_NAME, CITY_NAME, AREA_NAME, DOCDATE, DOCTIME) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    $cmd.Parameters.AddWithValue("isneed", "Y") | Out-Null
    $cmd.Parameters.AddWithValue("guid", $guid) | Out-Null
    $cmd.Parameters.AddWithValue("bioid", $data.bioid) | Out-Null
    $cmd.Parameters.AddWithValue("userid", "AGENT") | Out-Null
    $cmd.Parameters.AddWithValue("user_name", $data.agent_name) | Out-Null
    $cmd.Parameters.AddWithValue("doc_name", $data.doc_name) | Out-Null
    $cmd.Parameters.AddWithValue("city_name", $data.city_name) | Out-Null
    $cmd.Parameters.AddWithValue("area_name", $data.area_name) | Out-Null
    $cmd.Parameters.AddWithValue("docdate", $data.docdate) | Out-Null
    $cmd.Parameters.AddWithValue("doctime", $data.doctime) | Out-Null
    $cmd.ExecuteNonQuery() | Out-Null
    
    # 2. 寫入當事人 (Sellers / Buyers / Agent)
    # 2.1 Sellers (義務人)
    foreach ($s in $data.sellers) {
        $cmd = $conn.CreateCommand()
        $cmd.Transaction = $transaction
        $cmd.CommandText = "INSERT INTO [Person] (ISNEED, GUID, PE00, PE01, PE02, PE03, PE04, PE05, PE06, PE07) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        $cmd.Parameters.AddWithValue("isneed", "Y") | Out-Null
        $cmd.Parameters.AddWithValue("guid", $guid) | Out-Null
        $cmd.Parameters.AddWithValue("pe00", "義務人") | Out-Null
        $cmd.Parameters.AddWithValue("pe01", $s.name) | Out-Null
        $cmd.Parameters.AddWithValue("pe02", $s.id_number) | Out-Null
        $cmd.Parameters.AddWithValue("pe03", $s.birthday) | Out-Null
        $cmd.Parameters.AddWithValue("pe04", $s.address) | Out-Null
        $cmd.Parameters.AddWithValue("pe05", $s.numerator) | Out-Null
        $cmd.Parameters.AddWithValue("pe06", $s.denominator) | Out-Null
        $cmd.Parameters.AddWithValue("pe07", $s.tel) | Out-Null
        $cmd.ExecuteNonQuery() | Out-Null
        
        # 寫入前次移轉資料 (LandObtain) - 對應每筆土地的前次移轉現值
        foreach ($l in $data.lands) {
            $cmd = $conn.CreateCommand()
            $cmd.Transaction = $transaction
            $cmd.CommandText = "INSERT INTO [LandObtain] (ISNEED, GUID, LO01, LO02, LO03, LO04, LO05, LO06) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            $cmd.Parameters.AddWithValue("isneed", "Y") | Out-Null
            $cmd.Parameters.AddWithValue("guid", $guid) | Out-Null
            $cmd.Parameters.AddWithValue("lo01", $s.name) | Out-Null
            $cmd.Parameters.AddWithValue("lo02", $s.prev_year_month) | Out-Null
            $cmd.Parameters.AddWithValue("lo03", ($s.numerator.ToString() + "/" + $s.denominator.ToString())) | Out-Null
            $cmd.Parameters.AddWithValue("lo04", $s.prev_value) | Out-Null
            $cmd.Parameters.AddWithValue("lo05", $l.section) | Out-Null
            $cmd.Parameters.AddWithValue("lo06", $l.land_number) | Out-Null
            $cmd.ExecuteNonQuery() | Out-Null
        }
    }
    
    # 2.2 Buyers (權利人)
    foreach ($b in $data.buyers) {
        $cmd = $conn.CreateCommand()
        $cmd.Transaction = $transaction
        $cmd.CommandText = "INSERT INTO [Person] (ISNEED, GUID, PE00, PE01, PE02, PE03, PE04, PE05, PE06, PE07) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        $cmd.Parameters.AddWithValue("isneed", "Y") | Out-Null
        $cmd.Parameters.AddWithValue("guid", $guid) | Out-Null
        $cmd.Parameters.AddWithValue("pe00", "權利人") | Out-Null
        $cmd.Parameters.AddWithValue("pe01", $b.name) | Out-Null
        $cmd.Parameters.AddWithValue("pe02", $b.id_number) | Out-Null
        $cmd.Parameters.AddWithValue("pe03", $b.birthday) | Out-Null
        $cmd.Parameters.AddWithValue("pe04", $b.address) | Out-Null
        $cmd.Parameters.AddWithValue("pe05", $b.numerator) | Out-Null
        $cmd.Parameters.AddWithValue("pe06", $b.denominator) | Out-Null
        $cmd.Parameters.AddWithValue("pe07", $b.tel) | Out-Null
        $cmd.ExecuteNonQuery() | Out-Null
    }
    
    # 2.3 Agent (代理人/代書)
    if ($data.agent_name) {
        $cmd = $conn.CreateCommand()
        $cmd.Transaction = $transaction
        $cmd.CommandText = "INSERT INTO [Person] (ISNEED, GUID, PE00, PE01, PE02, PE03, PE04, PE05, PE06, PE07) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        $cmd.Parameters.AddWithValue("isneed", "Y") | Out-Null
        $cmd.Parameters.AddWithValue("guid", $guid) | Out-Null
        $cmd.Parameters.AddWithValue("pe00", "代理人") | Out-Null
        $cmd.Parameters.AddWithValue("pe01", $data.agent_name) | Out-Null
        $cmd.Parameters.AddWithValue("pe02", $data.agent_id) | Out-Null
        $cmd.Parameters.AddWithValue("pe03", $data.agent_birthday) | Out-Null
        $cmd.Parameters.AddWithValue("pe04", $data.agent_address) | Out-Null
        $cmd.Parameters.AddWithValue("pe05", 1) | Out-Null
        $cmd.Parameters.AddWithValue("pe06", 1) | Out-Null
        $cmd.Parameters.AddWithValue("pe07", $data.agent_tel) | Out-Null
        $cmd.ExecuteNonQuery() | Out-Null
    }
    
    # 3. 寫入土地清冊 (Land)
    foreach ($l in $data.lands) {
        $cmd = $conn.CreateCommand()
        $cmd.Transaction = $transaction
        $cmd.CommandText = "INSERT INTO [Land] (ISNEED, GUID, LA01, LA02, LA03, LA04, LA05, LA06, LA07, LA08) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        $cmd.Parameters.AddWithValue("isneed", "Y") | Out-Null
        $cmd.Parameters.AddWithValue("guid", $guid) | Out-Null
        $cmd.Parameters.AddWithValue("la01", $l.section) | Out-Null
        $cmd.Parameters.AddWithValue("la02", $l.land_number) | Out-Null
        $cmd.Parameters.AddWithValue("la03", $l.holding_str) | Out-Null
        $cmd.Parameters.AddWithValue("la04", "建") | Out-Null
        $cmd.Parameters.AddWithValue("la05", $l.value_per_sqm.ToString()) | Out-Null
        $cmd.Parameters.AddWithValue("la06", $l.area) | Out-Null
        $cmd.Parameters.AddWithValue("la07", "") | Out-Null
        $cmd.Parameters.AddWithValue("la08", $l.total_price) | Out-Null
        $cmd.ExecuteNonQuery() | Out-Null
    }
    
    # 4. 寫入建物清冊 (Build & BuildDetail)
    foreach ($b in $data.buildings) {
        $cmd = $conn.CreateCommand()
        $cmd.Transaction = $transaction
        $cmd.CommandText = "INSERT INTO [Build] (ISNEED, GUID, BU01, BU02, BU03, BU04, BU05, BU06, BU07, BU08, BU09) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        $cmd.Parameters.AddWithValue("isneed", "Y") | Out-Null
        $cmd.Parameters.AddWithValue("guid", $guid) | Out-Null
        $cmd.Parameters.AddWithValue("bu01", $b.building_number) | Out-Null
        $cmd.Parameters.AddWithValue("bu02", $b.door_number) | Out-Null
        $cmd.Parameters.AddWithValue("bu03", $b.land_number) | Out-Null
        $cmd.Parameters.AddWithValue("bu04", $b.total_area.ToString()) | Out-Null
        $cmd.Parameters.AddWithValue("bu05", $b.attached_area) | Out-Null
        $cmd.Parameters.AddWithValue("bu06", 0) | Out-Null
        $cmd.Parameters.AddWithValue("bu07", "鋼筋混凝土造") | Out-Null
        $cmd.Parameters.AddWithValue("bu08", "") | Out-Null
        $cmd.Parameters.AddWithValue("bu09", $b.holding_ratio) | Out-Null
        $cmd.ExecuteNonQuery() | Out-Null
        
        # 寫入建物層次明細
        foreach ($fl in $b.floors) {
            $cmd = $conn.CreateCommand()
            $cmd.Transaction = $transaction
            $cmd.CommandText = "INSERT INTO [BuildDetail] (ISNEED, GUID, BD01, BD02, BD03, BD04) VALUES (?, ?, ?, ?, ?, ?)"
            $cmd.Parameters.AddWithValue("isneed", "Y") | Out-Null
            $cmd.Parameters.AddWithValue("guid", $guid) | Out-Null
            $cmd.Parameters.AddWithValue("bd01", $fl.level) | Out-Null
            $cmd.Parameters.AddWithValue("bd02", $fl.area) | Out-Null
            $cmd.Parameters.AddWithValue("bd03", "") | Out-Null
            $cmd.Parameters.AddWithValue("bd04", "") | Out-Null
            $cmd.ExecuteNonQuery() | Out-Null
        }
    }
    
    $transaction.Commit()
    Write-Host "COMMIT_SUCCESS"
    $conn.Close()
} catch {
    if ($transaction) { $transaction.Rollback() }
    Write-Error $_
    if ($conn) { $conn.Close() }
    exit 1
}
"""
    
    # 建立暫存 JSON 檔案與 PowerShell 腳本檔案
    temp_dir = tempfile.gettempdir()
    json_temp = os.path.join(temp_dir, f"case_payload_{int(datetime.datetime.now().timestamp())}.json")
    ps_temp = os.path.join(temp_dir, f"write_case_db_{int(datetime.datetime.now().timestamp())}.ps1")
    
    try:
        with open(json_temp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            
        with open(ps_temp, "w", encoding="utf-8-sig") as f:
            f.write(ps_script)
            
        # 執行 PowerShell 寫入
        cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_temp, json_temp, db_path]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="cp950", errors="ignore")
        
        if "COMMIT_SUCCESS" in res.stdout:
            return {
                "success": True, 
                "bioid": bioid, 
                "message": f"成功匯入代書軟體資料庫！案件編號為：{bioid}。"
            }
        else:
            err_msg = res.stderr if res.stderr else res.stdout
            return {
                "success": False, 
                "error": f"資料庫交易失敗或發生異常。詳細診斷：{err_msg}"
            }
            
    except Exception as e:
        return {"success": False, "error": f"處理匯入程序時發生錯誤：{str(e)}"}
        
    finally:
        # 清理暫存檔
        for path in [json_temp, ps_temp]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

def parse_building_floors(details_str: str) -> list:
    """
    將層次面積明細解析為結構化樓層清單。
    例如：「一層 43.30, 二層 56.46, 騎樓 15.05...」
    """
    floors = []
    if not details_str:
        return floors
    
    # 支援逗號或分號分割
    parts = details_str.replace("，", ",").replace("；", ",").replace(";", ",").split(",")
    for p in parts:
        p_clean = p.strip()
        if not p_clean:
            continue
        # 分離文字與數字 (例如 一層 43.30)
        items = p_clean.split()
        if len(items) >= 2:
            level = items[0]
            try:
                area = float(items[1])
                floors.append({"level": level, "area": str(area)})
            except:
                pass
        elif len(p_clean) > 0:
            floors.append({"level": p_clean, "area": "0.0"})
            
    return floors
