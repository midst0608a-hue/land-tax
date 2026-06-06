import datetime

def to_chinese_number(num):
    """
    將阿拉伯數字轉換為中文大寫（如：壹佰貳拾萬）
    """
    try:
        num = int(round(float(num)))
    except:
        return "零"
    if num == 0:
        return "零"
        
    digits = "零壹貳參肆伍陸柒捌玖"
    units = ["", "拾", "佰", "仟"]
    big_units = ["", "萬", "億", "兆"]
    
    num_str = str(num)
    length = len(num_str)
    res = []
    
    for i, char in enumerate(num_str):
        idx = length - 1 - i
        val = int(char)
        if val != 0:
            res.append(digits[val])
            res.append(units[idx % 4])
        else:
            if res and res[-1] != "零" and idx % 4 != 0:
                res.append("零")
        if idx % 4 == 0 and idx // 4 > 0:
            if res and res[-1] == "零":
                res.pop()
            res.append(big_units[idx // 4])
            
    final_res = "".join(res)
    # 移除重複的零或尾部零
    while final_res.endswith("零"):
        final_res = final_res[:-1]
    if not final_res:
        return "零"
    return final_res

def format_date_to_taiwan(date_val):
    """
    將 datetime 轉為民國日期格式：民國 X 年 X 月 X 日
    """
    if not date_val:
        return "民國　年　月　日"
    if isinstance(date_val, str):
        if "年" in date_val:
            return date_val
        try:
            date_val = datetime.datetime.strptime(date_val, "%Y-%m-%d").date()
        except:
            return date_val
            
    year = date_val.year - 1911
    return f"民國 {year} 年 {date_val.month} 月 {date_val.day} 日"

def generate_contract_html(data: dict, contract_type: str = "買賣", contract_date = None, price_type: str = "公告現值", custom_price: float = 0.0) -> str:
    """
    根據萃取出來的資料與使用者的自訂參數，產生符合台灣官方公契格式的 HTML 契約書。
    支援合併土地與建物。
    """
    contract_date_str = format_date_to_taiwan(contract_date or datetime.date.today())
    
    sellers = data.get("sellers", [])
    if not sellers and "seller" in data:
        sellers = [data["seller"]]
    buyers = data.get("buyers", [])
    if not buyers and "buyer" in data:
        buyers = [data["buyer"]]
        
    seller = sellers[0] if sellers else {}
    buyer = buyers[0] if buyers else {}
    lands = data.get("lands", [])
    buildings = data.get("buildings", [])
    
    seller_names = "、".join([s.get("name", "") for s in sellers if s.get("name")]) or "________________"
    buyer_names = "、".join([b.get("name", "") for b in buyers if b.get("name")]) or "________________"
    
    # 計算土地契約價格
    land_rows_html = ""
    total_land_price = 0.0
    for idx, land in enumerate(lands):
        sec = land.get("section", "")
        num = land.get("land_number", "")
        area = float(land.get("area") or 0.0)
        num_numerator = float(land.get("holding_numerator") or 1.0)
        num_denominator = float(land.get("holding_denominator") or 1.0)
        holding_ratio_str = f"{int(num_numerator)} 分之 {int(num_denominator)}" if num_denominator > 1 else "全部"
        val_per_sqm = float(land.get("value_per_sqm") or 0.0)
        ratio = num_numerator / num_denominator if num_denominator > 0 else 1.0
        calculated_price = area * ratio * val_per_sqm
        total_land_price += calculated_price
        
        land_rows_html += f"""
        <tr>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{idx+1}</td>
            <td style="border: 1px solid black; padding: 8px;">{sec}段 {num}地號</td>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">建</td>
            <td style="border: 1px solid black; padding: 8px; text-align: right;">{area:,.2f}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{holding_ratio_str}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{holding_ratio_str}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: right;">{val_per_sqm:,.0f}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: right;">{calculated_price:,.0f}</td>
        </tr>
        """

    # 計算建物契約價格
    building_rows_html = ""
    total_building_price = 0.0
    for idx, b in enumerate(buildings):
        b_num = b.get("building_number", "")
        door = b.get("door_number", "")
        land_site = b.get("land_number", "")
        area_details = b.get("area_details", "")
        total_area = float(b.get("total_area") or 0.0)
        attached_area = b.get("attached_area", "")
        num_numerator = float(b.get("holding_numerator") or 1.0)
        num_denominator = float(b.get("holding_denominator") or 1.0)
        holding_ratio_str = f"{int(num_numerator)} 分之 {int(num_denominator)}" if num_denominator > 1 else "全部"
        val_eval = float(b.get("value_per_sqm") or 0.0) # 房屋評定現值
        
        total_building_price += val_eval
        
        building_rows_html += f"""
        <tr>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{idx+1}</td>
            <td style="border: 1px solid black; padding: 8px;">{land_site}<br/>建號 {b_num}</td>
            <td style="border: 1px solid black; padding: 8px;">{door}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: right;">{total_area:,.2f}<br/><span style="font-size: 11px; color:#555;">({area_details})</span></td>
            <td style="border: 1px solid black; padding: 8px;">{attached_area}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{holding_ratio_str}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{holding_ratio_str}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: right;">{val_eval:,.0f}</td>
        </tr>
        """
        
    total_calculated_price = total_land_price + total_building_price
    if contract_type == "買賣" and price_type == "自訂買賣價":
        final_price = custom_price
    else:
        final_price = total_calculated_price
        
    final_price_chinese = to_chinese_number(final_price)
    
    # 決定標題與契約原因
    has_b = len(buildings) > 0
    title = f"土地{'建物' if has_b else ''}{contract_type}所有權移轉契約書"
    reason_text = contract_type
    
    # 動態產生簽章欄位 HTML
    sign_rows_html = ""
    for idx, s in enumerate(sellers):
        identity = "出賣人<br/>(義務人)" if idx == 0 else ""
        sign_rows_html += f"""
        <tr>
            <td style="font-weight: bold; text-align: center; border: 1px solid black;">{identity}</td>
            <td style="border: 1px solid black;">
                <b>{s.get("name", "")}</b><br/>
                <span style="color: #999; font-size: 12px;">(簽名/蓋用印鑑章)</span>
            </td>
            <td style="text-align: center; border: 1px solid black;">{s.get("id_number", "")}</td>
            <td style="text-align: center; border: 1px solid black;">{s.get("birthday", "")}</td>
            <td style="border: 1px solid black;">{s.get("address", "")}</td>
        </tr>
        """
    for idx, b in enumerate(buyers):
        identity = "買受人<br/>(權利人)" if idx == 0 else ""
        sign_rows_html += f"""
        <tr>
            <td style="font-weight: bold; text-align: center; border: 1px solid black;">{identity}</td>
            <td style="border: 1px solid black;">
                <b>{b.get("name", "")}</b><br/>
                <span style="color: #999; font-size: 12px;">(簽名/蓋用印鑑章)</span>
            </td>
            <td style="text-align: center; border: 1px solid black;">{b.get("id_number", "")}</td>
            <td style="text-align: center; border: 1px solid black;">{b.get("birthday", "")}</td>
            <td style="border: 1px solid black;">{b.get("address", "")}</td>
        </tr>
        """
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <style>
        body {{
            font-family: "標楷體", "DFKai-SB", "Microsoft JhengHei", sans-serif;
            line-height: 1.6;
            margin: 40px auto;
            max-width: 800px;
            color: #000;
        }}
        .header {{
            text-align: center;
            font-size: 26px;
            font-weight: bold;
            margin-bottom: 30px;
            letter-spacing: 2px;
            text-decoration: underline;
        }}
        .clause {{
            font-size: 16px;
            margin-top: 15px;
            text-indent: -2em;
            margin-left: 2em;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 15px;
        }}
        th, td {{
            border: 1px solid #000;
            padding: 8px;
        }}
        th {{
            background-color: #f2f2f2;
            text-align: center;
        }}
        .sign-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        .sign-table td {{
            height: 60px;
            vertical-align: top;
        }}
        .footer-date {{
            text-align: right;
            font-size: 16px;
            margin-top: 40px;
            font-weight: bold;
        }}
        .note {{
            font-size: 13px;
            color: #555;
            margin-top: 20px;
        }}
    </style>
</head>
<body>

    <div class="header">{title}</div>
    
    <div style="text-align: right; font-weight: bold; margin-bottom: 20px;">
        立契人：買受人（權利人） {buyer_names} <br/>
        立契人：出賣人（義務人） {seller_names}
    </div>

    <div class="clause">
        立所有權移轉契約人雙方同意依本契約條款申辦土地與建物移轉登記，各就其標示、債權債務關係條款開列如下，以資共同遵守：
    </div>

    <div class="clause">
        <b>第一條：移轉登記原因與標的</b><br/>
        出賣人（義務人）【<b>{seller_names}</b>】將其所有下列土地及建物所有權，依【<b>{reason_text}</b>】登記原因移轉予買受人（權利人）【<b>{buyer_names}</b>】。
    </div>

    <div style="font-weight: bold; margin-top: 15px;">一、土地標示部分：</div>
    <table>
        <thead>
            <tr>
                <th style="width: 5%;">序號</th>
                <th style="width: 35%;">土地坐落（段、地號）</th>
                <th style="width: 8%;">地目</th>
                <th style="width: 12%;">面積 (㎡)</th>
                <th style="width: 13%;">原持分範圍</th>
                <th style="width: 13%;">本次移轉持分</th>
                <th style="width: 12%;">申報現值 (元/㎡)</th>
                <th style="width: 12%;">總現值金額 (元)</th>
            </tr>
        </thead>
        <tbody>
            {land_rows_html}
        </tbody>
    </table>
"""

    if has_b:
        html += f"""
    <div style="font-weight: bold; margin-top: 15px;">二、建物標示部分：</div>
    <table>
        <thead>
            <tr>
                <th style="width: 5%;">序號</th>
                <th style="width: 20%;">建物坐落及建號</th>
                <th style="width: 25%;">門牌號碼</th>
                <th style="width: 15%;">主建物面積 (㎡)</th>
                <th style="width: 15%;">附屬建物</th>
                <th style="width: 10%;">原持分範圍</th>
                <th style="width: 10%;">本次移轉持分</th>
                <th style="width: 10%;">評定現值 (元)</th>
            </tr>
        </thead>
        <tbody>
            {building_rows_html}
        </tbody>
    </table>
"""

    html += f"""
    <div class="clause">
        <b>第二條：契約總金額</b><br/>
        本案移轉土地及建物之契約總金額（或公告現值總金額）經雙方合議，共計新台幣：<br/>
        <span style="font-size: 18px; font-weight: bold; text-decoration: underline; letter-spacing: 1px;">
            【 {final_price_chinese}元整 】
        </span>
        （小寫：NT$ {final_price:,.0f} 元）
    </div>

    <div class="clause">
        <b>第三條：付款及交付（或債務履行）條件</b><br/>
        買受人（權利人）應依合約或法規將價款付清予出賣人，出賣人於本登記契約書用印之時，即代表已收受相應對價或同意進行贈與。雙方應協同備齊所有登記申請文件，向地政事務所申辦所有權移轉登記。
    </div>

    <div class="clause">
        <b>第四條：稅費負擔分配</b><br/>
        本案所產生之土地增值稅、契稅、印花稅、登記規費、地政士代辦費等，除法律另有強制規定外，買賣雙方同意依通常地政慣例處理（如：買受人負擔登記規費與契稅，出賣人負擔土地增值稅，印花稅由雙方依各自取得之契約憑證負擔，或由雙方另行約定）。
    </div>

    <div class="clause">
        <b>第五條：瑕疵擔保及糾紛處理</b><br/>
        出賣人擔保本案土地與建物於點交前，無任何涉訟、抵押權設定糾紛、或第三人主張權利之情事。若有上述爭議，出賣人應負責於登記前清理完畢，否則應賠償買受人因此所受之一切損害。
    </div>

    <div style="margin-top: 30px; font-weight: bold; font-size: 16px;">
        第六條：立契約人雙方簽章與基本資訊
    </div>

    <table class="sign-table">
        <tr>
            <th style="width: 15%;">身份別</th>
            <th style="width: 25%;">姓名與蓋章</th>
            <th style="width: 20%;">統一編號</th>
            <th style="width: 15%;">出生年月日</th>
            <th style="width: 25%;">戶籍地址</th>
        </tr>
        {sign_rows_html}
    </table>

    <div class="footer-date">
        立契日期：{contract_date_str}
    </div>

    <div class="note">
        ※ 說明：此格式完全相容於 Microsoft Word。點擊網頁上的下載按鈕後，以 Word 開啟此 HTML 檔案即可直接進行編輯、列印或蓋章。
    </div>

</body>
</html>
"""
    return html

def generate_application_html(data: dict, agent_info: dict, documents: list, contract_type: str = "買賣", contract_date = None) -> str:
    """
    產生符合台灣官方「土地登記申請書」樣式的 HTML，相容於 Word。
    """
    date_str = format_date_to_taiwan(contract_date or datetime.date.today())
    
    sellers = data.get("sellers", [])
    if not sellers and "seller" in data:
        sellers = [data["seller"]]
    buyers = data.get("buyers", [])
    if not buyers and "buyer" in data:
        buyers = [data["buyer"]]
        
    # 行政區對應
    hsn_name = agent_info.get("hsn_name", "台中市")
    org_name = agent_info.get("org_name", "龍井")
    
    # 登記事由與原因
    reason_code = "買賣" if contract_type == "買賣" else "贈與"
    
    # 組合附繳證件
    doc_rows = ""
    for idx in range(0, 12, 2):
        doc1 = documents[idx] if idx < len(documents) else ""
        doc2 = documents[idx+1] if idx+1 < len(documents) else ""
        doc_rows += f"""
        <tr>
            <td style="border: 1px solid black; padding: 6px; width: 50%;">{idx+1}. {doc1}</td>
            <td style="border: 1px solid black; padding: 6px; width: 50%;">{idx+2}. {doc2}</td>
        </tr>
        """

    # 組合申請人表格行
    applicant_rows = ""
    
    # 1. 義務人
    for idx, s in enumerate(sellers):
        role = "義務人" if idx == 0 else ""
        applicant_rows += f"""
        <tr>
            <td style="border: 1px solid black; padding: 6px; text-align: center; font-weight: bold;">{role}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{s.get("name", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{s.get("birthday", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{s.get("id_number", "")}</td>
            <td style="border: 1px solid black; padding: 6px;">{s.get("address", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center; height: 45px;"><span style="color:#aaa; font-size:11px;">蓋章</span></td>
        </tr>
        """
        
    # 2. 權利人
    for idx, b in enumerate(buyers):
        role = "權利人" if idx == 0 else ""
        applicant_rows += f"""
        <tr>
            <td style="border: 1px solid black; padding: 6px; text-align: center; font-weight: bold;">{role}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{b.get("name", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{b.get("birthday", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{b.get("id_number", "")}</td>
            <td style="border: 1px solid black; padding: 6px;">{b.get("address", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center; height: 45px;"><span style="color:#aaa; font-size:11px;">蓋章</span></td>
        </tr>
        """
        
    # 3. 代理人
    if agent_info.get("name"):
        applicant_rows += f"""
        <tr>
            <td style="border: 1px solid black; padding: 6px; text-align: center; font-weight: bold;">代理人</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{agent_info.get("name", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{agent_info.get("birthday", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{agent_info.get("id_number", "")}</td>
            <td style="border: 1px solid black; padding: 6px;">{agent_info.get("address", "")}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center; height: 45px;"><span style="color:#aaa; font-size:11px;">蓋章</span></td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>土地登記申請書</title>
    <style>
        body {{
            font-family: "標楷體", "DFKai-SB", "Microsoft JhengHei", sans-serif;
            margin: 20px auto;
            max-width: 850px;
            color: #000;
            font-size: 14px;
        }}
        .header {{
            text-align: center;
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 20px;
            letter-spacing: 4px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
        }}
        td {{
            vertical-align: top;
        }}
    </style>
</head>
<body>

    <div class="header">土 地 登 記 申 請 書</div>
    
    <!-- 收件與規費收據欄位 -->
    <table style="border: 1px solid black;">
        <tr>
            <td style="border: 1px solid black; padding: 6px; width: 12%; text-align: center; font-weight: bold; background-color: #f2f2f2;">收件</td>
            <td style="border: 1px solid black; padding: 6px; width: 38%;">
                日期時間：民國　　年　　月　　日　　時　　分<br/>
                字號：　　字第　　　　　　　　號
            </td>
            <td style="border: 1px solid black; padding: 6px; width: 12%; text-align: center; font-weight: bold; background-color: #f2f2f2;">規費收據</td>
            <td style="border: 1px solid black; padding: 6px; width: 38%;">
                登記費：元　書狀費：元　罰鍰：元<br/>
                合計：　　　　元　收據字號：
            </td>
        </tr>
    </table>

    <!-- 申請書主要內容 -->
    <table style="border: 1px solid black;">
        <!-- 1. 受理機關與原因日期 -->
        <tr>
            <td style="border: 1px solid black; padding: 6px; width: 15%; font-weight: bold; background-color: #f2f2f2;">(1) 受理機關</td>
            <td style="border: 1px solid black; padding: 6px; width: 35%;">{hsn_name}{org_name}地政事務所</td>
            <td style="border: 1px solid black; padding: 6px; width: 15%; font-weight: bold; background-color: #f2f2f2;">(2) 原因發生日期</td>
            <td style="border: 1px solid black; padding: 6px; width: 35%;">{date_str}</td>
        </tr>
        
        <!-- 2. 事由與原因 -->
        <tr>
            <td style="border: 1px solid black; padding: 6px; font-weight: bold; background-color: #f2f2f2;">(3) 申請登記事由</td>
            <td style="border: 1px solid black; padding: 6px;">■ 所有權移轉登記</td>
            <td style="border: 1px solid black; padding: 6px; font-weight: bold; background-color: #f2f2f2;">(4) 登記原因</td>
            <td style="border: 1px solid black; padding: 6px;">■ {reason_code}</td>
        </tr>
        
        <!-- 3. 標示與附繳證件 -->
        <tr>
            <td style="border: 1px solid black; padding: 6px; font-weight: bold; background-color: #f2f2f2;">(5) 標示及申請權利內容</td>
            <td style="border: 1px solid black; padding: 6px;">■ 契約書<br/>■ 登記清冊</td>
            <td style="border: 1px solid black; padding: 6px; font-weight: bold; background-color: #f2f2f2;">(6) 附繳證件</td>
            <td style="padding: 0;">
                <table style="margin: 0; border: none; width: 100%;">
                    {doc_rows}
                </table>
            </td>
        </tr>
        
        <!-- 4. 委任關係與聯絡方式 -->
        <tr>
            <td style="border: 1px solid black; padding: 6px; font-weight: bold; background-color: #f2f2f2;">(7) 委任關係</td>
            <td style="border: 1px solid black; padding: 6px;" colspan="3">
                本土地登記案之申請委託 <b>{agent_info.get("name", "張培聰")}</b> 代理。委託人確為登記標的物之權利關係人，並親自簽名蓋章，如有虛偽不實，代理人（複代理人）願負法律責任。
                <br/><br/>
                <span style="font-size: 12px; color: #555;">委託人（簽章欄見下方申請人名冊）</span>
            </td>
        </tr>
        <tr>
            <td style="border: 1px solid black; padding: 6px; font-weight: bold; background-color: #f2f2f2;">(8) 聯絡資訊</td>
            <td style="border: 1px solid black; padding: 6px;" colspan="3">
                代理人電話：{agent_info.get("tel", "")} &nbsp;&nbsp;&nbsp;&nbsp; 代理人戶籍地址：{agent_info.get("address", "")}
            </td>
        </tr>
        
        <!-- 5. 備註 -->
        <tr>
            <td style="border: 1px solid black; padding: 6px; font-weight: bold; background-color: #f2f2f2;">(9) 備註</td>
            <td style="border: 1px solid black; padding: 6px;" colspan="3">
                {agent_info.get("remarks", "本案係申報土地建物所有權移轉登記。")}
            </td>
        </tr>
    </table>

    <div style="font-weight: bold; margin-top: 15px; margin-bottom: 5px;">(10) 申請人名冊</div>
    <table style="border: 1px solid black;">
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th style="border: 1px solid black; padding: 6px; width: 12%;">身份別 (11)</th>
                <th style="border: 1px solid black; padding: 6px; width: 13%;">姓名 (12)</th>
                <th style="border: 1px solid black; padding: 6px; width: 12%;">出生年月日 (13)</th>
                <th style="border: 1px solid black; padding: 6px; width: 15%;">統一編號 (14)</th>
                <th style="border: 1px solid black; padding: 6px; width: 33%;">住所 (15)</th>
                <th style="border: 1px solid black; padding: 6px; width: 15%;">簽章 (16)</th>
            </tr>
        </thead>
        <tbody>
            {applicant_rows}
        </tbody>
    </table>

</body>
</html>
"""
    return html

def generate_inventory_html(data: dict, contract_type: str = "買賣", contract_date = None) -> str:
    """
    產生符合台灣官方「登記清冊」樣式的 HTML，相容於 Word。
    """
    sellers = data.get("sellers", [])
    if not sellers and "seller" in data:
        sellers = [data["seller"]]
    buyers = data.get("buyers", [])
    if not buyers and "buyer" in data:
        buyers = [data["buyer"]]
        
    buyer_names = "、".join([b.get("name", "") for b in buyers if b.get("name")]) or "________________"
    
    lands = data.get("lands", [])
    buildings = data.get("buildings", [])
    
    # 1. 土地清冊列
    land_rows = ""
    for idx, l in enumerate(lands):
        sec = l.get("section", "")
        num = l.get("land_number", "")
        area = float(l.get("area") or 0.0)
        num_numerator = float(l.get("holding_numerator") or 1.0)
        num_denominator = float(l.get("holding_denominator") or 1.0)
        holding_ratio_str = f"{int(num_numerator)} / {int(num_denominator)}" if num_denominator > 1 else "1/1"
        
        land_rows += f"""
        <tr>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{idx+1}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">龍井區</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{sec}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;"></td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{num}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">建</td>
            <td style="border: 1px solid black; padding: 6px; text-align: right;">{area:,.2f}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{holding_ratio_str}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{l.get("remarks", "")}</td>
        </tr>
        """
        
    # 2. 建物清冊列
    building_rows = ""
    for idx, b in enumerate(buildings):
        b_num = b.get("building_number", "")
        door = b.get("door_number", "")
        land_site = b.get("land_number", "")
        area_details = b.get("area_details", "")
        total_area = float(b.get("total_area") or 0.0)
        attached_area = b.get("attached_area", "")
        num_numerator = float(b.get("holding_numerator") or 1.0)
        num_denominator = float(b.get("holding_denominator") or 1.0)
        holding_ratio_str = f"{int(num_numerator)} / {int(num_denominator)}" if num_denominator > 1 else "1/1"
        
        building_rows += f"""
        <tr>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{idx+1}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{b_num}</td>
            <td style="border: 1px solid black; padding: 6px;">{door}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{land_site}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: right;">{total_area:,.2f}<br/><span style="font-size: 11px; color:#555;">({area_details})</span></td>
            <td style="border: 1px solid black; padding: 6px;">{attached_area}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{holding_ratio_str}</td>
            <td style="border: 1px solid black; padding: 6px; text-align: center;">{b.get("remarks", "")}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>登記清冊</title>
    <style>
        body {{
            font-family: "標楷體", "DFKai-SB", "Microsoft JhengHei", sans-serif;
            margin: 20px auto;
            max-width: 850px;
            color: #000;
            font-size: 14px;
        }}
        .header {{
            text-align: center;
            font-size: 24px;
            font-weight: bold;
            margin-bottom: 20px;
            letter-spacing: 6px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 25px;
        }}
        th, td {{
            border: 1px solid #000;
            padding: 6px;
        }}
        th {{
            background-color: #f2f2f2;
            text-align: center;
        }}
    </style>
</head>
<body>

    <div class="header">登 記 清 冊</div>
    
    <div style="text-align: right; font-weight: bold; margin-bottom: 15px;">
        申請人：{buyer_names} 等
    </div>
    
    <!-- 土地標示清冊 -->
    <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px;">一、土地標示</div>
    <table>
        <thead>
            <tr>
                <th style="width: 5%;">序號</th>
                <th style="width: 12%;">鄉鎮市區 (1)</th>
                <th style="width: 13%;">段</th>
                <th style="width: 10%;">小段</th>
                <th style="width: 15%;">地號 (2)</th>
                <th style="width: 8%;">地目 (3)</th>
                <th style="width: 12%;">面積 (㎡) (4)</th>
                <th style="width: 13%;">權利範圍 (5)</th>
                <th style="width: 12%;">備註 (6)</th>
            </tr>
        </thead>
        <tbody>
            {land_rows}
        </tbody>
    </table>

    <!-- 建物標示清冊 -->
    <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px; margin-top: 20px;">二、建物標示</div>
    <table>
        <thead>
            <tr>
                <th style="width: 5%;">序號</th>
                <th style="width: 12%;">建號 (7)</th>
                <th style="width: 28%;">門牌號碼 (8)</th>
                <th style="width: 15%;">基地坐落地號 (9)</th>
                <th style="width: 15%;">建物面積 (㎡) (10)</th>
                <th style="width: 10%;">附屬建物 (11)</th>
                <th style="width: 8%;">權利範圍 (12)</th>
                <th style="width: 7%;">備註 (13)</th>
            </tr>
        </thead>
        <tbody>
            {building_rows}
        </tbody>
    </table>

</body>
</html>
"""
    return html
