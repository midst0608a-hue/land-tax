import os
import json
import time
from google import genai
from google.genai import types
from review_knowledge_base import ReviewKnowledgeBase

class GeminiExtractor:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name

    def _call_gemini_with_retry(self, client, model: str, contents: list, config = None, max_retries: int = 5) -> str:
        """
        呼叫 Gemini API，並在遭遇 503, 429 或其他暫時性服務不可用/超時的錯誤時，
        進行指數退避 (exponential backoff) 重試。
        """
        import random

        delay = 2.0  # 初始等待 2 秒
        last_exception = None

        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config
                )
                return response.text
            except Exception as e:
                last_exception = e
                err_msg = str(e).upper()

                # 判斷是否為暫時性錯誤 (如: 503 Unavailable, 429 Rate Limit/Resource Exhausted, 或者包含 high demand 等說明)
                is_transient = any(
                    indicator in err_msg
                    for indicator in [
                        "503", "429", "RESOURCE_EXHAUSTED", "UNAVAILABLE",
                        "HIGH DEMAND", "TEMPORARY", "SPIKE", "OVERLOADED",
                        "RATE_LIMIT", "QUOTA"
                    ]
                )

                # 如果不是明確的暫時性錯誤，且已經試了 2 次，就不再浪費時間重試，直接拋出
                if not is_transient and attempt >= 2:
                    raise e

                if attempt < max_retries - 1:
                    # 嘗試解析 Google API 回傳的精確等待時間 (RetryInfo)
                    import re
                    retry_seconds = 0.0
                    retry_match = re.search(r"retryDelay[\'\"]?:\s*[\'\"]?(\d+)s", str(e))
                    if retry_match:
                        try:
                            retry_seconds = float(retry_match.group(1))
                        except:
                            pass
                    
                    if retry_seconds > 0:
                        sleep_time = retry_seconds + 2.0
                    else:
                        # 加入隨機擾動 (jitter) 避免多個請求同時重試
                        sleep_time = delay + random.uniform(0, 1)
                        delay *= 2  # 指數級增加等待時間
                        
                    time.sleep(sleep_time)
                else:
                    break

        raise last_exception

    def _get_prompt(self):
        return """
        你是一個專業的台灣不動產與身分證件資料萃取助理。
        請分析使用者提供的文件 (可能是土地謄本、建物謄本，或是身分證件)。
        
        請從文件中萃取以下所有欄位：
        1. 地號 (如果是土地謄本)
        2. 面積 (包含單位，如平方公尺)
        3. 持分 (權利範圍)
        4. 現值 (請明確抓取「公告土地現值」，請勿抓取「當期申報地價」)
        5. 所有權人 (若是身分證，請抓取「姓名」填入此欄位；若是謄本，請抓取所有權人姓名)
        6. 統一編號 (身分證字號或統編)
        7. 出生年月日 (如果是身分證，請務必抓取出生日期。請特別注意：在中華民國國民身分證上，此欄位通常是以「出 生」與「年 月 日」上下分行的方式呈現，其右側對應的日期格式為「中華民國XX年XX月XX日」或「民國XX年XX月XX日」或「XX年XX月XX日」。請仔細辨識，並完整且精確地萃取該日期，填入「出生年月日」欄位，不可遺漏。)
        8. 前次移轉現值 (必須包含年月與價格。如果同一個地號有多筆前次移轉紀錄，請分別列出，例如：「109年5月：13,000元／平方公尺；111年2月：15,000元／平方公尺」)
        9. 歷次取得範圍 (若有多筆對應前次移轉的持分取得範圍，也請分別列出)
        10. 地址 (包含身分證上的戶籍地址或謄本上的住址)
        
        【特別指示：針對建物謄本】
        如果這是一份「建物謄本」，除了抓取原有資訊外，請務必一併抓取「建物標示部」的內容。請確保自行在 JSON 內新增並包含以下欄位：
        - 建號
        - 門牌
        - 主要用途
        - 主要建材
        - 建築完成日期
        - 層次與面積 (請將各層次及其對應的面積詳細列出)
        - 主建物總面積 (【重要計算邏輯】除明確標示為「附屬建物」外，其餘所有層次之面積必須全部加總，作為正確的主建物總面積)
        - 附屬建物用途與面積 (若有標示為附屬建物，請務必同時抓取其「用途性質」與對應的「面積」，例如：「陽台：10.5平方公尺；雨遮：2.0平方公尺」。請獨立列出每一項附屬建物，切勿只給總和數字，也切勿計入主建物總面積)
        - 房屋現值（評定現值）(若無則填 0)
        - 備註 (例如公同共有或空白)
        請將這些建物標示部的資訊與所有權人等資訊「整合在同一個紀錄物件中」，確保內容完整不遺漏。
        
        【欄位鍵值限制】
        請務必且只能使用以下鍵值名稱作為 JSON 物件的 Key，切勿自行使用任何其他同義詞：
        - 「地號」
        - 「面積」
        - 「持分」
        - 「現值」
        - 「所有權人」
        - 「統一編號」
        - 「出生年月日」 (必須使用此名稱，切勿使用「出生日期」或「生日」或「出生」)
        - 「前次移轉現值」
        - 「歷次取得範圍」
        - 「地址」
        
        如果一份文件中有多筆權利紀錄 (例如同一個地號有多個持分人)，請你把「每一筆紀錄」都當成一個獨立的物件。
        
        請以嚴格的 JSON 陣列 (JSON Array) 格式回傳，不要包含任何 Markdown 標記 (如 ```json) 或是其他多餘 of 的說明文字。
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
                "出生年月日": "民國60年5月21日",
                "前次移轉現值": "109年5月：13,000.0元／平方公尺",
                "歷次取得範圍": "10000分之384",
                "地址": "台中市西屯區協和里..."
            }
        ]
        """

    def process_file(self, file_path: str, mime_type: str):
        uploaded_file = None
        temp_ascii_path = None
        try:
            client = genai.Client(api_key=self.api_key)
            prompt = self._get_prompt()

            # Check if filename contains non-ASCII characters to avoid google-genai SDK header encoding bug
            filename = os.path.basename(file_path)
            try:
                filename.encode('ascii')
                upload_path = file_path
            except UnicodeEncodeError:
                import shutil
                import tempfile
                ext = os.path.splitext(file_path)[1]
                temp_dir = os.path.dirname(file_path) or tempfile.gettempdir()
                temp_ascii_path = os.path.join(temp_dir, f"temp_upload_ascii_{int(time.time())}{ext}")
                shutil.copy2(file_path, temp_ascii_path)
                upload_path = temp_ascii_path

            # 使用 File API 上傳檔案
            uploaded_file = client.files.upload(
                file=upload_path,
                config={'mime_type': mime_type}
            )

            # 等待檔案處理完成 (變成 ACTIVE 狀態)
            while True:
                file_info = client.files.get(name=uploaded_file.name)
                state_str = str(file_info.state)
                if "ACTIVE" in state_str:
                    break
                elif "FAILED" in state_str:
                    return {"error": f"API 檔案處理失敗 (狀態: {state_str})，請嘗試換一個檔案。"}
                time.sleep(2)

            # 呼叫 Gemini 進行萃取
            try:
                response_text = self._call_gemini_with_retry(
                    client=client,
                    model=self.model_name,
                    contents=[file_info, prompt],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
            except Exception as e_flash:
                return {"error": f"Gemini 生成內容時發生錯誤：{str(e_flash)}"}

            return self._parse_response(response_text)

        except Exception as e:
            return {"error": f"API 發生錯誤：請確認 API Key 是否有效。詳細錯誤：{str(e)}"}
        finally:
            # 清理：無論成功或失敗，都盡可能刪除雲端上的暫存檔案
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass
            # 清理 ASCII 暫存檔案
            if temp_ascii_path and os.path.exists(temp_ascii_path):
                try:
                    os.remove(temp_ascii_path)
                except Exception:
                    pass

    def process_image(self, image_path: str):
        """處理單張圖片 (如身分證 JPG/PNG)"""
        ext = image_path.split('.')[-1].lower()
        mime = f"image/{ext}" if ext in ["png", "jpeg"] else "image/jpeg"
        return self.process_file(image_path, mime)

    def process_pdf(self, pdf_path: str):
        """處理 PDF 檔案 (如電子謄本或掃描謄本)"""
        return self.process_file(pdf_path, "application/pdf")

    def _parse_response(self, text: str):
        """解析 Gemini 回傳的 JSON 文字"""
        try:
            # 嘗試清除可能的 Markdown 標記
            clean_text = text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            elif clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            clean_text = clean_text.strip()
            data = json.loads(clean_text)
            return {"success": True, "data": data}
        except json.JSONDecodeError:
            return {"error": "無法解析 AI 的回覆格式，請重新嘗試。", "raw": text}

    def process_review(self, doc_path: str, doc_mime: str, case_desc: str, manual_path: str = None, manual_mime: str = None, review_focus: list = None):
        """
        Agentic Workflow 土地登記案卷預審系統：
        1. 資訊萃取 (Extraction): 抽出案件結構化 JSON (登記原因, 申請人身分, 標的, 檢附文件)
        2. 混合檢索 (Hybrid Search Retrieval): 依據 JSON 與標籤對照《土地登記審查手冊》精準點次
        3. 邏輯比對 (Audit & Empowering Packaging): 套用溫和賦能與 Checklist 檢核表輸出
        """
        uploaded_doc = None
        uploaded_manual = None
        temp_doc_ascii = None
        temp_manual_ascii = None
        try:
            client = genai.Client(api_key=self.api_key)
            import shutil
            import tempfile

            # Ensure doc_path is ASCII-safe to avoid google-genai SDK header encoding bug
            doc_filename = os.path.basename(doc_path)
            try:
                doc_filename.encode('ascii')
                upload_doc_path = doc_path
            except UnicodeEncodeError:
                ext = os.path.splitext(doc_path)[1]
                temp_dir = os.path.dirname(doc_path) or tempfile.gettempdir()
                temp_doc_ascii = os.path.join(temp_dir, f"temp_doc_ascii_{int(time.time())}{ext}")
                shutil.copy2(doc_path, temp_doc_ascii)
                upload_doc_path = temp_doc_ascii

            # 上傳審查文件
            uploaded_doc = client.files.upload(
                file=upload_doc_path,
                config={'mime_type': doc_mime}
            )

            while True:
                doc_info = client.files.get(name=uploaded_doc.name)
                state_str = str(doc_info.state)
                if "ACTIVE" in state_str:
                    break
                elif "FAILED" in state_str:
                    return {"error": f"審查文件處理失敗 (狀態: {state_str})"}
                time.sleep(2)

            # Step 1: 結構化資訊萃取 (Extraction)
            extraction_prompt = f"""
            你是一個專業的台灣地政登記案件資料萃取器。
            請閱讀所提供之審查文件（公契/土地登記申請書/附件圖檔）與使用者輸入之案件描述：
            【案件口語描述】：
            {case_desc}

            請輸出一段嚴格符合 JSON 格式的數據，包含：
            - "registration_type": "買賣" / "贈與" / "夫妻贈與" / "繼承" / "抵押權設定" / "所有權移轉" / "其他"
            - "obligor_name": "義務人/出賣人/贈與人姓名"
            - "obligor_id": "義務人身分證號/統編"
            - "right_holder_name": "權利人/買受人/受贈人姓名"
            - "right_holder_id": "權利人身分證號/統編"
            - "property_identifiers": ["土地或建物地號/建號/段名"]
            - "holding_ratio": "移轉持分或權利範圍"
            - "contract_date": "公契或原約定日期"
            - "attached_docs": ["已提示之檢附文件，如印鑑證明、稅單、戶籍謄本等"]
            - "key_terms": ["專有名詞標籤，如印鑑證明, 土地增值稅, 契稅免稅, 預告登記"]
            """
            
            extract_response = self._call_gemini_with_retry(
                client=client,
                model=self.model_name,
                contents=[doc_info, extraction_prompt]
            )

            extracted_data = {}
            try:
                clean_json = extract_response.strip().replace("```json", "").replace("```", "").strip()
                extracted_data = json.loads(clean_json)
            except Exception:
                extracted_data = {
                    "registration_type": "所有權移轉",
                    "key_terms": ["印鑑證明", "土地增值稅", "契稅"],
                    "raw_extraction": extract_response
                }

            # Step 2: 結構化混合檢索 (Hybrid Search Retrieval)
            kb = ReviewKnowledgeBase(manual_pdf_path=manual_path if (manual_path and os.path.exists(manual_path)) else None)
            reg_type = extracted_data.get("registration_type", "所有權移轉")
            keywords = extracted_data.get("key_terms", ["印鑑證明", "土地增值稅"])
            if review_focus:
                keywords.extend(review_focus)

            matched_chunks = kb.search_hybrid(
                registration_type=reg_type,
                keywords=keywords,
                case_desc=case_desc,
                top_k=4
            )

            retrieved_rules_str = ""
            for idx, chunk in enumerate(matched_chunks, 1):
                retrieved_rules_str += f"""
                【規範點次 {idx}】：{chunk.get('section_title', '')} - {chunk.get('title', '')} ({chunk.get('statute_ref', '')})
                【內容依據】：{chunk.get('content', '')}
                【核心審查對照點】：{', '.join(chunk.get('check_points', []))}
                """

            # Step 3: 邏輯比對與溫和賦能包裝輸出 (Audit & Tone Packaging)
            focus_str = f"【使用者指定的重點加強項目】：{', '.join(review_focus)}" if review_focus else ""

            final_audit_prompt = f"""
            你是一個貼心、極具專業高度且溫和的「地政士與登記案件專業審查助手」。
            你的目標是為地政士/辦理人員提供「送件前安全防護網 (Checklist)」，協助提升送件一次補正率與順暢度。

            【極重要語氣與表達規範 (Value Packaging)】：
            - 請絕對避免使用尖銳、批判性或帶有批判懲罰意味的字眼（嚴禁使用：「錯誤」、「無效」、「退件」、「違法」、「不合規定」）。
            - 請將所有發現的差異與缺漏，包裝為「💡 為確保送件順利，建議您覆核以下項目」或「建議加強核對事項」。
            - 請以賦能（Empowerment）與專業協作的語氣呈現，強調這是一份能節省時間、避免多次跑地政事務所的「安全備忘錄」。
            - 每一項提醒，請务必附上我們為您檢索出的《土地登記審查手冊》具體點次或法規條文依據作為權威後盾。

            【案件萃取資訊】：
            {json.dumps(extracted_data, ensure_ascii=False, indent=2)}

            【案件背景描述】：
            {case_desc}

            {focus_str}

            【從《土地登記審查手冊》精準檢索到的審查規範依據】：
            {retrieved_rules_str}

            請輸出結構清晰、排版美觀的 Markdown 預審報告，必須包含以下區塊：

            ### 💡 1. 案件送件安全防護網 (Checklist 覆核表)
            (使用表格或勾選框 [ ] 呈現，分為：✅ 填寫相符項目、💡 建議送件前再覆核/確認項目)

            ### 📋 2. 案件基本資料與欄位比對清單
            (呈現當事人姓名/身分證字號、土地標示與權利範圍之核對結果)

            ### 📘 3. 審查手冊點次與法規依據 (Citations & Rules)
            (列出本案件適用之《土地登記審查手冊》點次、土地登記規則第34/41/56條等條文依據)

            ### 🤝 4. 專業送件小叮嚀與檢附文件建議
            (提醒應齊備之附件，如印鑑證明3個月效期、完稅證明章、委託書簽章等)
            """

            response_text = self._call_gemini_with_retry(
                client=client,
                model=self.model_name,
                contents=[doc_info, final_audit_prompt]
            )

            return {
                "success": True,
                "report": response_text,
                "extracted_data": extracted_data,
                "retrieved_rules": matched_chunks
            }

        except Exception as e:
            return {"error": f"審查過程發生錯誤：{str(e)}"}
        finally:
            if uploaded_doc:
                try:
                    client.files.delete(name=uploaded_doc.name)
                except Exception:
                    pass
            if uploaded_manual:
                try:
                    client.files.delete(name=uploaded_manual.name)
                except Exception:
                    pass
            if temp_doc_ascii and os.path.exists(temp_doc_ascii):
                try:
                    os.remove(temp_doc_ascii)
                except Exception:
                    pass
            if temp_manual_ascii and os.path.exists(temp_manual_ascii):
                try:
                    os.remove(temp_manual_ascii)
                except Exception:
                    pass

    def process_feedback_analysis(self, doc_path: str = None, doc_mime: str = None, user_note: str = "", office_name: str = "地政事務所"):
        """
        多模態補正單照片 / 口語備忘 AI 分析與歸檔助理
        """
        uploaded_file = None
        temp_ascii = None
        try:
            client = genai.Client(api_key=self.api_key)
            import shutil
            import tempfile

            contents = []
            if doc_path and os.path.exists(doc_path):
                filename = os.path.basename(doc_path)
                try:
                    filename.encode('ascii')
                    upload_path = doc_path
                except UnicodeEncodeError:
                    ext = os.path.splitext(doc_path)[1]
                    temp_ascii = os.path.join(tempfile.gettempdir(), f"fb_temp_ascii_{int(time.time())}{ext}")
                    shutil.copy2(doc_path, temp_ascii)
                    upload_path = temp_ascii

                uploaded_file = client.files.upload(
                    file=upload_path,
                    config={'mime_type': doc_mime or 'image/jpeg'}
                )

                while True:
                    file_info = client.files.get(name=uploaded_file.name)
                    state_str = str(file_info.state)
                    if "ACTIVE" in state_str:
                        break
                    elif "FAILED" in state_str:
                        return {"error": f"照片處理失敗 (狀態: {state_str})"}
                    time.sleep(2)

                contents.append(file_info)

            prompt = f"""
            你是一個專業的台灣地政經驗知識庫歸檔助理。
            使用者上傳了一張地政事務所開立的補正通知單照片/文件，或者口述了一段實務補正經驗：
            【使用者口述/對話備忘】：
            {user_note}

            【機關名稱】：{office_name}

            【工作任務】：
            1. 分析照片與文字中的補正事由、涉及欄位、法規與改善作法。
            2. 以對話式、極具專業賦能感的語氣摘要這項實務眉角。
            3. 輸出 JSON 格式供知識庫歸檔：
            - "title": "簡短的眉角標題（例如：分割繼承協議書騎縫章與印花稅）"
            - "registration_type": "買賣" / "贈與" / "繼承" / "抵押權設定" / "通用"
            - "office_name": "{office_name}"
            - "content": "詳細補正事由與建議作法說明"
            - "summary_dialogue": "給使用者的互動回覆與確認語句"
            """
            contents.append(prompt)

            response_text = self._call_gemini_with_retry(
                client=client,
                model=self.model_name,
                contents=contents
            )

            clean_json = response_text.strip().replace("```json", "").replace("```", "").strip()
            try:
                data = json.loads(clean_json)
                return {"success": True, "analysis": data, "raw": response_text}
            except Exception:
                return {
                    "success": True,
                    "analysis": {
                        "title": "地政實務補正經驗備忘",
                        "registration_type": "通用",
                        "office_name": office_name,
                        "content": user_note or response_text[:200],
                        "summary_dialogue": response_text
                    },
                    "raw": response_text
                }
        except Exception as e:
            return {"error": f"補正單分析失敗：{str(e)}"}
        finally:
            if uploaded_file:
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass
            if temp_ascii and os.path.exists(temp_ascii):
                try:
                    os.remove(temp_ascii)
                except Exception:
                    pass

    def process_contract_extraction(self,
                                 land_doc_path: str = None, land_doc_mime: str = None,
                                 building_doc_paths: list = None, building_doc_mimes: list = None,
                                 seller_id_paths: list = None, seller_id_mimes: list = None,
                                 buyer_id_paths: list = None, buyer_id_mimes: list = None,
                                 seller_id_path: str = None, seller_id_mime: str = None,
                                 buyer_id_path: str = None, buyer_id_mime: str = None,
                                 doc_paths: list = None, doc_mimes: list = None):
        """
        上傳多個檔案（謄本及身分證件），利用 Gemini 2.5 Flash 進行資料萃取，對齊公契與報稅所需欄位。
        """
        client = genai.Client(api_key=self.api_key)
        uploaded_files = []
        temp_ascii_paths = []
        contents = []

        # 動態建立要上傳與處理的檔案清單
        files_to_process = []

        if doc_paths is not None:
            # 優先使用整合上傳的檔案清單
            for idx, (path, mime) in enumerate(zip(doc_paths, doc_mimes)):
                if path and mime:
                    files_to_process.append((f"doc_{idx}", path, mime))
        else:
            # 向後相容單一類別的舊參數
            if seller_id_paths is None:
                seller_id_paths = [seller_id_path] if seller_id_path else []
            if seller_id_mimes is None:
                seller_id_mimes = [seller_id_mime] if seller_id_mime else []
            if buyer_id_paths is None:
                buyer_id_paths = [buyer_id_path] if buyer_id_path else []
            if buyer_id_mimes is None:
                buyer_id_mimes = [buyer_id_mime] if buyer_id_mime else []
            if building_doc_paths is None:
                building_doc_paths = []
            if building_doc_mimes is None:
                building_doc_mimes = []

            if land_doc_path and land_doc_mime:
                files_to_process.append(("land_doc", land_doc_path, land_doc_mime))

            for idx, (path, mime) in enumerate(zip(building_doc_paths, building_doc_mimes)):
                if path and mime:
                    files_to_process.append((f"building_doc_{idx}", path, mime))

            for idx, (path, mime) in enumerate(zip(seller_id_paths, seller_id_mimes)):
                if path and mime:
                    files_to_process.append((f"seller_id_{idx}", path, mime))

            for idx, (path, mime) in enumerate(zip(buyer_id_paths, buyer_id_mimes)):
                if path and mime:
                    files_to_process.append((f"buyer_id_{idx}", path, mime))

        try:
            import shutil
            import tempfile

            for key, path, mime in files_to_process:
                if path and mime:
                    filename = os.path.basename(path)
                    try:
                        filename.encode('ascii')
                        upload_path = path
                    except UnicodeEncodeError:
                        ext = os.path.splitext(path)[1]
                        temp_dir = os.path.dirname(path) or tempfile.gettempdir()
                        temp_ascii = os.path.join(temp_dir, f"temp_{key}_ascii_{int(time.time())}{ext}")
                        shutil.copy2(path, temp_ascii)
                        temp_ascii_paths.append(temp_ascii)
                        upload_path = temp_ascii

                    # 上傳檔案
                    uploaded_file = client.files.upload(
                        file=upload_path,
                        config={'mime_type': mime}
                    )
                    uploaded_files.append(uploaded_file)

                    # 等待 ACTIVE
                    while True:
                        file_info = client.files.get(name=uploaded_file.name)
                        state_str = str(file_info.state)
                        if "ACTIVE" in state_str:
                            break
                        elif "FAILED" in state_str:
                            return {"error": f"檔案 {key} 處理失敗 (狀態: {state_str})"}
                        time.sleep(2)

                    # 依據檔案類型加入描述，幫助 AI 識別
                    desc = ""
                    if key == "land_doc":
                        desc = "【土地登記謄本檔案】"
                    elif key.startswith("building_doc_"):
                        desc = f"【建物登記謄本檔案 {key.split('_')[-1]}】"
                    elif key.startswith("seller_id_"):
                        desc = f"【出賣人/義務人身分證明文件 {key.split('_')[-1]}】"
                    elif key.startswith("buyer_id_"):
                        desc = f"【買受人/權利人身分證明文件 {key.split('_')[-1]}】"
                    elif key.startswith("doc_"):
                        desc = f"【上傳文件 {key.split('_')[-1]}】"
                    
                    if desc:
                        contents.append(desc)
                    contents.append(file_info)

            # 如果沒有任何上傳文件，直接返回空欄位
            if not contents:
                return {
                    "success": True,
                    "data": {
                        "sellers": [],
                        "buyers": [],
                        "lands": [],
                        "buildings": []
                    }
                }

            prompt = """
            你是一個專業的台灣地政登記案件資料萃取助理。
            請從上傳的所有文件中（包含土地登記謄本、建物登記謄本、身分證影本等），精確萃取所有相關人、土地與建物資訊，以供填寫「土地建物所有權移轉契約書 (公契)」、「土地登記申請書」與「登記清冊」之用。

            【特別指示：當事人身分證與謄本辨識】
            1. 請完整辨識並萃取所有文件（包含身分證件與謄本）中出現的所有自然人。
            2. 請根據身分分類，分開填入 `sellers` 與 `buyers` 兩個不同的陣列中：
               - 出賣人（義務人）/ 贈與人：通常代表讓與權利的一方，其資料填入 `sellers` 陣列中。
               - 買受人（權利人）/ 受贈人：通常代表取得權利的一方，其資料填入 `buyers` 陣列中。
            3. 若有不同的身分證，屬於不同的角色，請一定要正確區分其屬於「出賣人（義務人）」或「買受人（權利人）/ 受贈人」。
               - 若未上傳土地謄本，僅有身分證，請直接依據上傳類別（出賣人證件為 sellers，買受人證件為 buyers）進行填寫。
            4. 前次移轉現值申報資訊 (出賣人)：
               - 請從土地登記謄本之所有權部（「前次移轉現值」或「歷次取得權利範圍」欄位）中，擷取該出賣人（所有權人）取得該土地時的「前次移轉年月」（格式如民國年月：10704，代表107年4月）、「前次移轉現值（單價）」（格式如：19000）、以及取得該持分時的「持分分子/分母」。

            【特別指示：針對建物登記謄本】
            如果上傳的檔案包含「建物登記謄本」，請務必擷取以下資訊並填入 `buildings` 陣列中：
            - 建號：例如「183」或「00183-000」
            - 門牌：例如「龍井區三港路水裡港巷68之16號」
            - 主要用途：例如「住家用」或「商業用」
            - 基地坐落地號：例如「田水段 859-23地號」
            - 層次與面積：各樓層面積，例如「一層 43.30, 二層 56.46, 騎樓 15.05... 共計 124.71」
            - 附屬建物：用途與面積，例如「陽台 2.42」
            - 移轉權利範圍：持分分子/分母，例如「1/1」
            - 房屋現值（評定現值）：如果文件中含有課稅現值或房屋評定現值（若無則為 0）
            - 備註：例如「公同共有」或空白

            請以嚴格的 JSON 格式回傳，且必須符合以下 JSON 結構：
            {
              "sellers": [
                {
                  "name": "出賣人/義務人姓名",
                  "id_number": "出賣人統一編號（身分證字號）",
                  "birthday": "出賣人出生年月日，請轉換為民國年格式，例如：民國50年10月12日",
                  "address": "出賣人戶籍地址",
                  "prev_year_month": "前次移轉年月（民國格式，如 10704，若沒有則預設 10704）",
                  "prev_value_per_sqm": "前次移轉現值，僅數字（元/平方公尺，若沒有則預設 19000）",
                  "prev_holding_numerator": "前次移轉持分分子，僅數字（若沒有則預設 1）",
                  "prev_holding_denominator": "前次移轉持分分母，僅數字（若沒有則預設 2）"
                }
              ],
              "buyers": [
                {
                  "name": "買受人/權利人姓名",
                  "id_number": "買受人統一編號（身分證字號）",
                  "birthday": "買受人出生年月日，請轉換為民國年格式，例如：民國80年1月5日",
                  "address": "買受人戶籍地址",
                  "holding_numerator": "移轉權利範圍（持分分子），僅數字，例如 1",
                  "holding_denominator": "移轉權利範圍（持分分母），僅數字，例如 1",
                  "zip": "買受人郵遞區號，例如 407，若沒有則預設 407"
                }
              ],
              "lands": [
                {
                  "section": "地段名稱，例如：順和段",
                  "land_number": "地號，例如：0151-0000",
                  "area": "面積，僅填寫數字（單位為平方公尺），例如：679.07",
                  "holding_numerator": "移轉權利範圍（持分分子），僅數字，例如 1",
                  "holding_denominator": "移轉權利範圍（持分分母），僅數字，例如 1",
                  "value_per_sqm": "公告地段現值，僅填寫數字，例如：4160"
                }
              ],
              "buildings": [
                {
                  "building_number": "建號，例如：183",
                  "door_number": "門牌地址，例如：龍井區三港路水裡港巷68之16號",
                  "land_number": "基地坐落地號，例如：田水段 859-23地號",
                  "area_details": "層次面積明細，例如：一層 43.30, 二層 56.46, 騎樓 15.05",
                  "total_area": "主建物總面積，僅填寫數字，例如：124.7",
                  "attached_area": "附屬建物明細，例如：陽台 2.42",
                  "holding_numerator": "移轉持分分子，僅數字，例如：1",
                  "holding_denominator": "移轉持分分母，僅數字，例如：1",
                  "value_per_sqm": "評定現值，僅填寫數字，若無則填 0",
                  "remarks": "備註，例如：公同共有"
                }
              ]
            }

            請不要包含 any Markdown 標記 (如 ```json) 或是其他多餘的說明文字。
            如果某個檔案未提供，或某個欄位在文件中確實找不到，請填寫空字串 ""。
            """

            contents.append(prompt)

            # 呼叫 Gemini
            response_text = self._call_gemini_with_retry(
                client=client,
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            return self._parse_response(response_text)

        except Exception as e:
            return {"error": f"資料萃取失敗：{str(e)}"}
        finally:
            # 清理雲端暫存檔
            for f in uploaded_files:
                try:
                    client.files.delete(name=f.name)
                except:
                    pass
            # 清理本機 ASCII 暫存檔
            for p in temp_ascii_paths:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except:
                        pass
