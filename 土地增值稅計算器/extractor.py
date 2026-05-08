import os
import json
import base64
import requests

class GeminiExtractor:
    def __init__(self, api_key: str):
        self.api_key = api_key
        
    def _get_prompt(self):
        return """
        你是一個專業的台灣不動產與身分證件資料萃取助理。
        請分析使用者提供的文件 (可能是土地謄本、建物謄本，或是身分證件)。
        
        請從文件中萃取以下所有欄位：
        1. 地號 (如果是土地謄本)
        2. 面積 (包含單位，如平方公尺)
        3. 持分 (權利範圍)
        4. 現值 (當期申報地價或前次移轉現值)
        5. 所有權人 (姓名)
        6. 統一編號 (身分證字號或統編)
        7. 前次移轉現值
        8. 歷次取得範圍
        9. 地址 (包含身分證上的戶籍地址或謄本上的住址)
        
        如果一份文件中有多筆權利紀錄 (例如同一個地號有多個持分人)，請你把「每一筆紀錄」都當成一個獨立的物件。
        
        請以嚴格的 JSON 陣列 (JSON Array) 格式回傳，不要包含任何 Markdown 標記 (如 ```json) 或是其他多餘的說明文字。
        如果某個欄位在文件中找不到，請留空字串 ""。
        
        JSON 格式範例：
        [
            {
                "地號": "西屯區順和段 0151-0000",
                "面積": "679.07 平方公尺",
                "持分": "10000分之384",
                "現值": "4,160.0元／平方公尺",
                "所有權人": "吳林桂花",
                "統一編號": "N201807918",
                "前次移轉現值": "13,000.0元／平方公尺",
                "歷次取得範圍": "10000分之384",
                "地址": "台中市西屯區協和里..."
            }
        ]
        """

    def _call_api(self, mime_type: str, file_data: bytes):
        base64_data = base64.b64encode(file_data).decode('utf-8')
        prompt = self._get_prompt()
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64_data
                        }
                    }
                ]
            }]
        }
        
        # 優先嘗試 gemini-1.5-flash
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.api_key}"
        response = requests.post(url, headers={"Content-Type": "application/json"}, json=payload)
        
        # 如果遇到 404 或出錯，自動降級/切換至 gemini-1.5-pro 旗艦版
        if response.status_code != 200:
            url_pro = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={self.api_key}"
            response = requests.post(url_pro, headers={"Content-Type": "application/json"}, json=payload)
            if response.status_code != 200:
                return {"error": f"API 發生錯誤 ({response.status_code})：請確認 API Key 是否有效。詳細錯誤：{response.text}"}
                
        resp_data = response.json()
        try:
            text = resp_data['candidates'][0]['content']['parts'][0]['text']
            return self._parse_response(text)
        except Exception as e:
            return {"error": "AI 回傳格式異常。", "raw": str(resp_data)}

    def process_image(self, image_path: str):
        """處理單張圖片 (如身分證 JPG/PNG)"""
        try:
            with open(image_path, "rb") as f:
                ext = image_path.split('.')[-1].lower()
                mime = f"image/{ext}" if ext in ["png", "jpeg"] else "image/jpeg"
                return self._call_api(mime, f.read())
        except Exception as e:
            return {"error": str(e)}

    def process_pdf(self, pdf_path: str):
        """處理 PDF 檔案 (如電子謄本或掃描謄本)"""
        try:
            with open(pdf_path, "rb") as f:
                return self._call_api("application/pdf", f.read())
        except Exception as e:
            return {"error": str(e)}

    def _parse_response(self, text: str):
        """解析 Gemini 回傳的 JSON 文字"""
        try:
            clean_text = text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
                
            clean_text = clean_text.strip()
            data = json.loads(clean_text)
            return {"success": True, "data": data}
        except json.JSONDecodeError:
            return {"error": "無法解析 AI 的回覆格式，請重新嘗試。", "raw": text}

    def _parse_response(self, text: str):
        """解析 Gemini 回傳的 JSON 文字"""
        try:
            # 嘗試清除可能的 Markdown 標記
            clean_text = text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
                
            clean_text = clean_text.strip()
            data = json.loads(clean_text)
            return {"success": True, "data": data}
        except json.JSONDecodeError:
            return {"error": "無法解析 AI 的回覆格式，請重新嘗試。", "raw": text}
