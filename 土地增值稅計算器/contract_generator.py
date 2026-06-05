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
        # 假設是民國格式已經給了
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
    此 HTML 使用標準 Table 與 CSS 邊框，可以直接在 Word 中無痛開啟。
    """
    # 轉換立約日期
    contract_date_str = format_date_to_taiwan(contract_date or datetime.date.today())
    
    # 取得雙方當事人資料
    seller = data.get("seller", {})
    buyer = data.get("buyer", {})
    lands = data.get("lands", [])
    
    # 計算土地移轉契約價格資訊
    land_rows_html = ""
    total_contract_price = 0.0
    
    for idx, land in enumerate(lands):
        sec = land.get("section", "")
        num = land.get("land_number", "")
        area = float(land.get("area") or 0.0)
        
        # 取得分子分母
        num_numerator = float(land.get("holding_numerator") or 1.0)
        num_denominator = float(land.get("holding_denominator") or 1.0)
        
        # 預設移轉持分與持分相同
        holding_ratio_str = f"{int(num_numerator)} 分之 {int(num_denominator)}" if num_denominator > 1 else "全部"
        
        # 公告現值
        val_per_sqm = float(land.get("value_per_sqm") or 0.0)
        
        # 計算此土地移轉面積金額
        # 土地移轉價值 = 面積 * (分子/分母) * 公告現值
        ratio = num_numerator / num_denominator if num_denominator > 0 else 1.0
        calculated_price = area * ratio * val_per_sqm
        total_contract_price += calculated_price
        
        land_rows_html += f"""
        <tr>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{idx+1}</td>
            <td style="border: 1px solid black; padding: 8px;">{sec}段 {num}地號</td>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">建/田/地</td>
            <td style="border: 1px solid black; padding: 8px; text-align: right;">{area:,.2f}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{holding_ratio_str}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: center;">{holding_ratio_str}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: right;">{val_per_sqm:,.0f}</td>
            <td style="border: 1px solid black; padding: 8px; text-align: right;">{calculated_price:,.0f}</td>
        </tr>
        """
        
    # 若使用者選擇自訂合約價格（買賣價），則合約總價為自訂金額
    if contract_type == "買賣" and price_type == "自訂買賣價":
        final_price = custom_price
    else:
        final_price = total_contract_price
        
    final_price_chinese = to_chinese_number(final_price)
    
    # 決定標題與契約原因
    title = "土地買賣所有權移轉契約書" if contract_type == "買賣" else "土地贈與所有權移轉契約書"
    reason_text = "買賣" if contract_type == "買賣" else "贈與"
    
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

    <div class="header">土地所有權移轉契約書</div>
    
    <div style="text-align: right; font-weight: bold; margin-bottom: 20px;">
        立契人：買受人（權利人） {buyer.get("name", "________________")} <br/>
        立契人：出賣人（義務人） {seller.get("name", "________________")}
    </div>

    <div class="clause">
        立所有權移轉契約人雙方同意依本契約條款申辦土地移轉登記，各就其土地標示、債權債務關係條款開列如下，以資共同遵守：
    </div>

    <div class="clause">
        <b>第一條：移轉登記原因與標的</b><br/>
        出賣人（義務人）將其所有下列土地所有權，依【<b>{reason_text}</b>】登記原因移轉予買受人（權利人）。
    </div>

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

    <div class="clause">
        <b>第二條：契約總金額</b><br/>
        本案移轉土地之契約總金額（或公告現值總金額）經雙方合議，共計新台幣：<br/>
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
        本案所產生之土地增值稅、印花稅、登記規費、地政士代辦費等，除法律另有強制規定外，買賣雙方同意依通常地政慣例處理（如：買方負擔登記規費與契稅，賣方負擔土地增值稅，或由雙方另行約定）。
    </div>

    <div class="clause">
        <b>第五條：瑕疵擔保及糾紛處理</b><br/>
        出賣人擔保本案土地於點交前，無任何涉訟、抵押權設定糾紛、或第三人主張權利之情事。若有上述爭議，出賣人應負責於登記前清理完畢，否則應賠償買受人因此所受之一切損害。
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
        <tr>
            <td style="font-weight: bold; text-align: center;">出賣人<br/>(義務人)</td>
            <td>
                <b>{seller.get("name", "")}</b><br/>
                <span style="color: #999; font-size: 12px;">(簽名/蓋用印鑑章)</span>
            </td>
            <td style="text-align: center;">{seller.get("id_number", "")}</td>
            <td style="text-align: center;">{seller.get("birthday", "")}</td>
            <td>{seller.get("address", "")}</td>
        </tr>
        <tr>
            <td style="font-weight: bold; text-align: center;">買受人<br/>(權利人)</td>
            <td>
                <b>{buyer.get("name", "")}</b><br/>
                <span style="color: #999; font-size: 12px;">(簽名/蓋用印鑑章)</span>
            </td>
            <td style="text-align: center;">{buyer.get("id_number", "")}</td>
            <td style="text-align: center;">{buyer.get("birthday", "")}</td>
            <td>{buyer.get("address", "")}</td>
        </tr>
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
