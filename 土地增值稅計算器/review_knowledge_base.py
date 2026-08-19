import re
import os
import time
import math
import json
import shutil
import subprocess
import threading
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Tuple

def get_gmt8_now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """取得台灣時間 (GMT+8) 格式化字串"""
    tz_gmt8 = timezone(timedelta(hours=8))
    return datetime.now(tz_gmt8).strftime(fmt)

class ReviewKnowledgeBase:
    """
    土地登記審查手冊與實務防護知識庫模組
    - 結構化切片與混合檢索 (Structural Chunking & Hybrid Search)
    - 支援上傳圖檔 (JPG/PNG/WEBP) 與公文 PDF 永久留存於 knowledge_docs/
    - 支援歸檔時「背景自動同步 GitHub」+「本地定時滾動備份」
    - 支援跨電腦一鍵 Pull 同步與歷史案件比對
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
        base_dir = os.path.dirname(__file__)
        self.base_dir = base_dir
        self.feedback_memory_path = os.path.join(base_dir, "feedback_memory.json")
        self.docs_storage_dir = os.path.join(base_dir, "knowledge_docs")
        self.backup_dir = os.path.join(base_dir, "backups")
        
        # 確保知識庫實體文件與備份存放資料夾存在
        for p in [self.docs_storage_dir, self.backup_dir]:
            if not os.path.exists(p):
                try:
                    os.makedirs(p, exist_ok=True)
                except Exception:
                    pass

        if manual_pdf_path and os.path.exists(manual_pdf_path):
            self._load_and_chunk_pdf(manual_pdf_path)

    def load_feedback_memory(self) -> List[Dict[str, Any]]:
        """讀取地政實務防護知識庫資料 (優先直接從本地 feedback_memory.json 極速讀取)"""
        if os.path.exists(self.feedback_memory_path):
            try:
                with open(self.feedback_memory_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception:
                return []
        return []

    def create_local_backup(self):
        """建立本地自動歷史備份 (最多保留最新 30 份)"""
        try:
            timestamp = get_gmt8_now_str("%Y%m%d_%H%M%S")
            backup_file = os.path.join(self.backup_dir, f"feedback_memory_{timestamp}.json")
            if os.path.exists(self.feedback_memory_path):
                shutil.copy2(self.feedback_memory_path, backup_file)
                
            # 清理過期備份
            all_backups = sorted([os.path.join(self.backup_dir, f) for f in os.listdir(self.backup_dir) if f.startswith("feedback_memory_")])
            if len(all_backups) > 30:
                for old_b in all_backups[:-30]:
                    try:
                        os.remove(old_b)
                    except Exception:
                        pass
        except Exception as e:
            print(f"本地備份失敗: {e}")

    def sync_to_github_async(self, commit_msg: str = "自動同步實務防護知識庫與公文附件"):
        """在背景執行緒自動推送到 GitHub，完全不阻塞前端 UI"""
        def _task():
            try:
                status_res = subprocess.run(["git", "status", "--porcelain"], cwd=self.base_dir, capture_output=True, text=True)
                if status_res.stdout.strip():
                    subprocess.run(["git", "add", "."], cwd=self.base_dir, check=True)
                    subprocess.run(["git", "commit", "-m", commit_msg], cwd=self.base_dir, check=True)
                    subprocess.run(["git", "push", "origin", "master:main"], cwd=self.base_dir, check=True)
                    print("✅ GitHub 知識庫自動背景同步完成！")
            except Exception as e:
                print(f"GitHub 自動同步失敗：{e}")

        thread = threading.Thread(target=_task, daemon=True)
        thread.start()

    def pull_from_github(self) -> Tuple[bool, str]:
        """從 GitHub 拉取最新知識庫與附件檔案"""
        try:
            res = subprocess.run(["git", "pull", "origin", "master:main"], cwd=self.base_dir, capture_output=True, text=True)
            if res.returncode == 0:
                return True, "✅ 成功從 GitHub 同步最新知識庫！"
            else:
                return False, f"拉取失敗：{res.stderr or res.stdout}"
        except Exception as e:
            return False, f"執行失敗：{str(e)}"

    def save_feedback_entry(self, entry: Dict[str, Any], source_file_path: str = None, original_filename: str = None, auto_sync_github: bool = True) -> bool:
        """
        寫入一筆新的實務防護經驗至知識庫：
        1. 將附件圖檔/PDF 永久保存於 knowledge_docs/ 資料夾
        2. 寫入本地 feedback_memory.json
        3. 建立本地歷史備份 (backups/)
        4. 背景自動推送到 GitHub (跨電腦同步)
        """
        local_ok = False
        try:
            records = self.load_feedback_memory()
            timestamp_str = get_gmt8_now_str("%Y%m%d_%H%M%S")
            entry_id = entry.get("id") or f"KB_{timestamp_str}_{len(records)+1}"
            entry["id"] = entry_id
            if "created_at" not in entry:
                entry["created_at"] = get_gmt8_now_str("%Y-%m-%d %H:%M:%S")

            # 處理原始圖檔 / PDF 永久保存
            if source_file_path and os.path.exists(source_file_path):
                orig_name = original_filename or os.path.basename(source_file_path)
                ext = os.path.splitext(orig_name)[1].lower()
                safe_name = f"{entry_id}{ext}"
                target_path = os.path.join(self.docs_storage_dir, safe_name)
                
                shutil.copy2(source_file_path, target_path)
                
                is_pdf = (ext == ".pdf")
                entry["attached_file"] = {
                    "original_name": orig_name,
                    "stored_filename": safe_name,
                    "relative_path": os.path.join("knowledge_docs", safe_name),
                    "file_type": "pdf" if is_pdf else "image",
                    "file_size": os.path.getsize(target_path)
                }

            records.append(entry)
            with open(self.feedback_memory_path, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            local_ok = True

            # 執行本地滾動備份
            self.create_local_backup()

            # 背景自動推送到 GitHub
            if auto_sync_github:
                self.sync_to_github_async(commit_msg=f"自動歸檔經驗 [{entry.get('title', '新案例')}] 並同步附件")

        except Exception as e:
            print(f"Error saving feedback entry: {e}")

        return local_ok

    def delete_feedback_entry(self, entry_id: str, auto_sync_github: bool = True) -> bool:
        """刪除單筆知識庫條目並清理對應保存的圖檔/PDF，同步更新至 GitHub"""
        try:
            records = self.load_feedback_memory()
            updated_records = []
            deleted_title = ""
            for r in records:
                if r.get("id") == entry_id:
                    deleted_title = r.get("title", entry_id)
                    att = r.get("attached_file")
                    if att and isinstance(att, dict) and att.get("stored_filename"):
                        file_path = os.path.join(self.docs_storage_dir, att["stored_filename"])
                        if os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                            except Exception:
                                pass
                else:
                    updated_records.append(r)

            with open(self.feedback_memory_path, "w", encoding="utf-8") as f:
                json.dump(updated_records, f, ensure_ascii=False, indent=2)
            
            # 建立本地備份
            self.create_local_backup()

            # 背景同步 GitHub
            if auto_sync_github:
                self.sync_to_github_async(commit_msg=f"刪除經驗條目 [{deleted_title}] 並同步更新")

            return True
        except Exception:
            return False

    def _load_and_chunk_pdf(self, pdf_path: str):
        """依據《土地登記審查手冊》的章節與點次進行結構化切片"""
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
                        rule_match = re.search(r"(點次\s*\d+[-\d]*|\d+[\.\、]\s*([^\n]+))", clean_line)

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

    def search_hybrid(self, registration_type: str, keywords: List[str], case_desc: str = "", top_k: int = 5) -> List[Dict[str, Any]]:
        """
        混合檢索 (Hybrid Search)：
        - Metadata 過濾: matching registration_type
        - 包含實務累積之自建知識庫 (feedback_memory.json + 留存之圖檔與公文)
        - BM25 / 精確關鍵字評分
        """
        fb_records = self.load_feedback_memory()
        converted_fb = []
        for fb in fb_records:
            attached = fb.get("attached_file")
            converted_fb.append({
                "id": fb.get("id", "KB"),
                "section_title": "🛡️ 團隊實務防護知識庫 (歷史案例)",
                "rule_index": "歷史案件經驗",
                "registration_type": [fb.get("registration_type", "通用")],
                "title": f"實務防護提醒：{fb.get('title', '補正眉角')}",
                "content": fb.get("content", ""),
                "check_points": [fb.get("content", "")],
                "statute_ref": f"實務留存案例 ({fb.get('created_at', '')})",
                "is_custom_kb": True,
                "attached_file": attached
            })

        all_pool = list(self.CORE_RULES_DATABASE) + converted_fb + self.dynamic_chunks
        scored_results = []

        query_terms = set(keywords)
        if case_desc:
            words = re.findall(r"[\u4e00-\u9fa5]{2,6}", case_desc)
            for w in words:
                if any(kw in w for kw in ["印鑑", "代理", "權利範圍", "持分", "增值稅", "契稅", "繼承", "贈與", "土地", "建物", "抵押權", "切結", "戶籍", "協議", "簽名", "蓋章", "34-1", "告知"]):
                    query_terms.add(w)

        for rule in all_pool:
            score = 0.0

            # 1. Metadata 評分 (權重 4.0)
            rule_reg_types = rule.get("registration_type", [])
            if "通用" in rule_reg_types or registration_type in rule_reg_types or any(rt in registration_type for rt in rule_reg_types):
                score += 4.0
            else:
                score -= 1.5

            # 自建實務經驗優先加分 (權重 +3.5)
            if rule.get("is_custom_kb"):
                score += 3.5

            # 2. 關鍵字精確比對
            rule_text = f"{rule.get('section_title', '')} {rule.get('title', '')} {rule.get('content', '')} {' '.join(rule.get('check_points', []))}"
            for term in query_terms:
                if term in rule_text:
                    if term in ["印鑑證明", "預告登記", "公設保留地", "地上權", "契稅免稅", "土地增值稅", "分割協議", "法定代理人", "34-1", "切結書"]:
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
