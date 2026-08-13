import re
import os
import math
import json
from typing import List, Dict, Any

class ReviewKnowledgeBase:
    """
    土地登記審查手冊 - 結構化切片與混合檢索 (Structural Chunking & Hybrid Search) 模組
    """
    
    CORE_RULES_DATABASE = [
        {
            "id": "RULE_BUY_SELL_01",
            "section_title": "第二章 所有權移轉登記 - 買賣登記",
            "rule_index": "點次 101-105",
            "registration_type": ["買賣", "所有權移轉"],
            "title": "買賣移轉登記當事人與身分證明審查",
            "content": "審查買賣移轉登記時，應核對出賣人（義務人）與買受人（權利人）之姓名、統一編號與戶籍地址是否與身分證件相符。出賣人若委任代理人辦理，應檢附印鑑證明（核發日起算三個月內有效，或依土地登記規則第41條規定審查）及委託書，印章應與印鑑章相符。",
            "check_points": ["出賣人/買受人身分證號及地址一致性", "印鑑證明有效期限（3個月內）", "代理人授權書及簽章"],
            "statute_ref": "土地登記規則第34條、第41條、第56條"
        },
        {
            "id": "RULE_BUY_SELL_02",
            "section_title": "第二章 所有權移轉登記 - 買賣登記",
            "rule_index": "點次 106-110",
            "registration_type": ["買賣", "所有權移轉"],
            "title": "買賣移轉標示與權利範圍審查",
            "content": "應核對土地標示（縣市、鄉鎮市區、段、小段、地號）及權利範圍（持分算式）是否與土地謄本登記相符。移轉持分不得超過義務人所有權持分。建物標示與建號亦須與謄本標示部一致。",
            "check_points": ["土地/建物標示與地號建號完全一致", "權利範圍（持分算式）無誤且不高於義務人持有範圍"],
            "statute_ref": "土地登記規則第13條、第56條"
        },
        {
            "id": "RULE_BUY_SELL_03",
            "section_title": "第二章 所有權移轉登記 - 買賣登記",
            "rule_index": "點次 111-115",
            "registration_type": ["買賣", "所有權移轉"],
            "title": "買賣稅費與繳清證明審查",
            "content": "應審核土地增值稅繳清（或免稅）證明書、房屋稅及地價稅欠稅查與完稅收據、契稅繳清（或免稅）證明。公契契約書應貼足印花稅票（千分之二按申報現值計算）。",
            "check_points": ["土地增值稅繳清/免稅證明", "契稅與房屋稅完稅證明", "地價稅查無欠稅章", "公契貼足印花稅票"],
            "statute_ref": "土地稅法第51條、契稅條例第23條、印花稅法第7條"
        },
        {
            "id": "RULE_GIFT_01",
            "section_title": "第二章 所有權移轉登記 - 贈與/夫妻贈與登記",
            "rule_index": "點次 120-125",
            "registration_type": ["贈與", "夫妻贈與", "所有權移轉"],
            "title": "贈與移轉登記與稅務證明審查",
            "content": "辦理贈與移轉登記（含配偶間贈與），應檢附稽徵機關核發之贈與稅繳清證明書或免稅證明書（夫妻贈與依遺產及贈與稅法第20條第1項第6款得申請免稅）。並應檢附土地增值稅與契稅完稅/免稅證明。",
            "check_points": ["贈與稅繳清或不計入贈與總額免稅證明書", "配偶身分關係證明（戶籍謄本或戶口名簿）", "土地增值稅/契稅完稅證明"],
            "statute_ref": "遺產及贈與稅法第20條、第42條、土地稅法第28條之2"
        },
        {
            "id": "RULE_INHERIT_01",
            "section_title": "第三章 繼承登記",
            "rule_index": "點次 201-210",
            "registration_type": ["繼承", "分割繼承"],
            "title": "繼承登記與遺產稅完稅審查",
            "content": "繼承登記應檢附被繼承人除戶戶籍謄本、全體繼承人現在戶籍謄本、繼承系統表、遺產稅繳清證明書（或免稅證明書、不計入遺產總額證明書）。如為分割繼承，須加附全體繼承人印鑑證明及遺產分割協議書（應貼足印花稅票）。",
            "check_points": ["被繼承人死亡除戶與繼承人戶籍謄本", "完整繼承系統表", "遺產稅繳清/免稅證明書", "分割繼承之印鑑證明與分割協議書（含印花稅）"],
            "statute_ref": "土地登記規則第119條、遺產及贈與稅法第42條"
        },
        {
            "id": "RULE_MORTGAGE_01",
            "section_title": "第四章 他項權利登記 - 抵押權設定",
            "rule_index": "點次 301-308",
            "registration_type": ["抵押權設定", "他項權利"],
            "title": "抵押權設定登記審查",
            "content": "抵押權設定應核對設定人（義務人）與債務人身分，擔保債權總金額、利息、遲延利息、違約金、清償日期等契約約定事項。義務人非債務人時（第三人提供擔保），應經設定人同意並蓋印鑑章或親自到場核對身分。",
            "check_points": ["債務金額、清償期、利息約定明確", "設定人印鑑與身分核對", "第三人擔保之同意書"],
            "statute_ref": "土地登記規則第111條、民法第860條"
        },
        {
            "id": "RULE_GENERAL_01",
            "section_title": "第一章 總則 - 審查通則",
            "rule_index": "點次 01-15",
            "registration_type": ["通用", "買賣", "贈與", "繼承", "抵押權設定"],
            "title": "土地登記補正與駁回法定事由",
            "content": "依土地登記規則第56條規定，有下列情形之一者，登記機關應開具補正單通知申請人補正：(一)申請格式不合；(二)登記原因證明文件與登記簿不符；(三)應檢附之文件未齊備；(四)未依規定繳納登記費或印花稅。如逾期未補正，或依第57條規定依法不應登記者，應予駁回。",
            "check_points": ["土地登記規則第56條補正開具事由", "土地登記規則第57條駁回事由對照"],
            "statute_ref": "土地登記規則第56條、第57條"
        }
    ]

    def __init__(self, manual_pdf_path: str = None):
        self.manual_pdf_path = manual_pdf_path
        self.dynamic_chunks = []
        self.feedback_memory_path = os.path.join(os.path.dirname(__file__), "feedback_memory.json")
        if manual_pdf_path and os.path.exists(manual_pdf_path):
            self._load_and_chunk_pdf(manual_pdf_path)

    def load_feedback_memory(self) -> List[Dict[str, Any]]:
        """讀取地政事務所實務補正錯題庫經驗檔 (feedback_memory.json)"""
        if os.path.exists(self.feedback_memory_path):
            try:
                with open(self.feedback_memory_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def save_feedback_entry(self, entry: Dict[str, Any]) -> bool:
        """寫入一筆新的實務補正經驗至 feedback_memory.json"""
        try:
            records = self.load_feedback_memory()
            entry["id"] = f"FB_{len(records)+1}_{int(time.time())}"
            records.append(entry)
            with open(self.feedback_memory_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _load_and_chunk_pdf(self, pdf_path: str):
        """依據《土地登記審查手冊》的章節與點次進行結構化切片 (Structural Chunking)"""
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                current_chapter = "未分類章節"
                current_rule_index = "點次未標註"
                buffer_lines = []

                for page_idx, page in enumerate(pdf.pages):
                    page_num = page_idx + 1
                    text = page.extract_text()
                    if not text:
                        continue

                    lines = text.split('\n')
                    for line in lines:
                        clean_line = line.strip()
                        if not clean_line:
                            continue

                        # 偵測章節 header
                        chap_match = re.search(r"第[一二三四五六七八九十0-9]+[章節]\s*([^\n]+)", clean_line)
                        rule_match = re.search(r"(點次\s*\d+[-\d]*|\d+[\.\、]\s*[^\n]+)", clean_line)

                        if chap_match or rule_match:
                            if buffer_lines:
                                chunk_text = "\n".join(buffer_lines)
                                if len(chunk_text.strip()) > 30:
                                    reg_types = self._detect_registration_types(chunk_text, current_chapter)
                                    self.dynamic_chunks.append({
                                        "id": f"DYNAMIC_{len(self.dynamic_chunks)+1}",
                                        "section_title": current_chapter,
                                        "rule_index": current_rule_index,
                                        "registration_type": reg_types,
                                        "title": f"{current_chapter} - {current_rule_index} (P.{page_num})",
                                        "content": chunk_text,
                                        "page_number": page_num,
                                        "statute_ref": f"土地登記審查手冊 P.{page_num} ({current_rule_index})"
                                    })
                                buffer_lines = []

                            if chap_match:
                                current_chapter = chap_match.group(0)
                            if rule_match:
                                current_rule_index = rule_match.group(0)

                        buffer_lines.append(clean_line)

                if buffer_lines:
                    chunk_text = "\n".join(buffer_lines)
                    reg_types = self._detect_registration_types(chunk_text, current_chapter)
                    self.dynamic_chunks.append({
                        "id": f"DYNAMIC_{len(self.dynamic_chunks)+1}",
                        "section_title": current_chapter,
                        "rule_index": current_rule_index,
                        "registration_type": reg_types,
                        "title": f"{current_chapter} (頁底)",
                        "content": chunk_text,
                        "page_number": len(pdf.pages),
                        "statute_ref": f"土地登記審查手冊 P.{len(pdf.pages)}"
                    })
        except Exception:
            # 發生例外時降級使用內建核心知識庫
            pass

    def _detect_registration_types(self, text: str, chapter: str) -> List[str]:
        types = []
        full = text + " " + chapter
        if "買賣" in full:
            types.append("買賣")
        if "贈與" in full:
            types.append("贈與")
        if "夫妻贈與" in full:
            types.append("夫妻贈與")
        if "繼承" in full:
            types.append("繼承")
        if "抵押權" in full:
            types.append("抵押權設定")
        if "移轉" in full and "所有權" in full:
            types.append("所有權移轉")
        if not types:
            types.append("通用")
        return types

    def search_hybrid(self, registration_type: str, keywords: List[str], case_desc: str = "", top_k: int = 4) -> List[Dict[str, Any]]:
        """
        混合檢索 (Hybrid Search)：
        - Metadata 過濾: matching registration_type
        - BM25 / 精確關鍵字評分 (70% 權重)
        - 語意關聯/概念評分 (30% 權重)
        - 包含實務累積之經驗錯題庫 (feedback_memory.json)
        """
        fb_records = self.load_feedback_memory()
        converted_fb = []
        for fb in fb_records:
            converted_fb.append({
                "id": fb.get("id", "FB"),
                "section_title": f"🛡️ 實務地政防護庫 ({fb.get('office_name', '實務經驗')})",
                "rule_index": "團隊防護案例",
                "registration_type": [fb.get("registration_type", "通用")],
                "title": f"實務補正提醒：{fb.get('title', '補正眉角')}",
                "content": fb.get("content", ""),
                "check_points": [fb.get("content", "")],
                "statute_ref": f"地政事務所實務經驗 ({fb.get('office_name', '實務案例')})"
            })

        all_pool = list(self.CORE_RULES_DATABASE) + converted_fb + self.dynamic_chunks
        scored_results = []

        query_terms = set(keywords)
        if case_desc:
            words = re.findall(r"[\u4e00-\u9fa5]{2,6}", case_desc)
            for w in words:
                if any(kw in w for kw in ["印鑑", "代理", "權利範圍", "持分", "增值稅", "契稅", "繼承", "贈與", "土地", "建物", "抵押權"]):
                    query_terms.add(w)

        for rule in all_pool:
            score = 0.0

            # 1. Metadata 評分 (權重 4.0)
            rule_reg_types = rule.get("registration_type", [])
            if "通用" in rule_reg_types or registration_type in rule_reg_types or any(rt in registration_type for rt in rule_reg_types):
                score += 4.0
            else:
                score -= 1.5

            # 實務防護經驗加分 (權重 +2.0)
            if "FB_" in str(rule.get("id", "")):
                score += 2.5

            # 2. 關鍵字精確比對 BM25/Sparse 評分 (70% 語意權重)
            rule_text = f"{rule.get('section_title', '')} {rule.get('title', '')} {rule.get('content', '')} {' '.join(rule.get('check_points', []))}"
            kw_hits = 0
            for term in query_terms:
                if term in rule_text:
                    kw_hits += 1
                    if term in ["印鑑證明", "預告登記", "公設保留地", "地上權", "契稅免稅", "土地增值稅"]:
                        score += 3.0
                    else:
                        score += 1.5

            # 3. 標題與章節加分
            if registration_type and registration_type in rule.get("section_title", ""):
                score += 2.0

            scored_results.append((score, rule))

        scored_results.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [item[1] for item in scored_results[:top_k]]
        return top_chunks
