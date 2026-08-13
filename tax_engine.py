class TaxEngine:
    @staticmethod
    def calculate_lvit(
        present_value: float,
        original_value: float,
        cpi: float,
        area: float,
        holding_ratio_numerator: float,
        holding_ratio_denominator: float,
        deductions: float,
        holding_years: int,
        is_self_use: bool = False
    ) -> dict:
        """
        計算土地增值稅 (Land Value Increment Tax)
        """
        holding_ratio = holding_ratio_numerator / holding_ratio_denominator
        
        # 1. 計算按物價指數調整後的原規定地價 (Tax Base)
        adjusted_original_value_per_sqm = original_value * (cpi / 100.0) if cpi > 100.0 else original_value
        tax_base = adjusted_original_value_per_sqm * area * holding_ratio
        
        # 2. 計算土地漲價總數額 (Total Increment)
        total_increment = (present_value * area * holding_ratio) - tax_base - deductions
        
        if total_increment <= 0:
            return {
                "tax_base": tax_base,
                "total_increment": 0,
                "increment_ratio": 0,
                "tax_payable": 0,
                "tax_rate_level": "無漲價",
                "details": "無漲價或漲價總數額小於0，免繳土地增值稅"
            }
            
        # 3. 計算漲價倍數 (Increment Ratio)
        increment_ratio = total_increment / tax_base
        
        # 4. 計算應納稅額
        tax_payable = 0
        tax_rate_level = ""
        
        if is_self_use:
            # 自用住宅用地優惠稅率 (10%)
            tax_payable = total_increment * 0.10
            tax_rate_level = "自用住宅 (10%)"
        else:
            # 一般用地累進稅率
            base_tax_20 = total_increment * 0.20
            actual_tax = 0
            
            if increment_ratio <= 1.0:
                actual_tax = base_tax_20
                tax_rate_level = "第一級 (20%)"
            elif 1.0 < increment_ratio <= 2.0:
                actual_tax = total_increment * 0.30 - tax_base * 0.10
                tax_rate_level = "第二級 (30%)"
            else:
                actual_tax = total_increment * 0.40 - tax_base * 0.30
                tax_rate_level = "第三級 (40%)"
                
            # 計算長期持有減徵 (僅針對超過 20% 稅率的部分)
            tax_above_20 = actual_tax - base_tax_20
            if tax_above_20 > 0:
                discount_rate = 0.0
                if holding_years >= 40:
                    discount_rate = 0.40
                elif holding_years >= 30:
                    discount_rate = 0.30
                elif holding_years >= 20:
                    discount_rate = 0.20
                
                if discount_rate > 0:
                    tax_above_20_discounted = tax_above_20 * (1 - discount_rate)
                    tax_payable = base_tax_20 + tax_above_20_discounted
                    tax_rate_level += f" (適用長期持有減徵 {int(discount_rate*100)}%)"
                else:
                    tax_payable = actual_tax
            else:
                tax_payable = actual_tax
                
        # 四捨五入至整數
        tax_payable = round(tax_payable)
        total_increment = round(total_increment)
        tax_base = round(tax_base)
        
        return {
            "tax_base": tax_base,
            "total_increment": total_increment,
            "increment_ratio": round(increment_ratio, 4),
            "tax_payable": tax_payable,
            "tax_rate_level": tax_rate_level,
            "details": f"漲價總數額: {total_increment}, 應納稅額: {tax_payable}",
            "steps": {
                "present_value_total": round(present_value * area * holding_ratio),
                "original_value_adjusted": round(adjusted_original_value_per_sqm),
                "area": area,
                "holding_ratio": holding_ratio,
                "deductions": deductions,
                "cpi": cpi,
                "is_self_use": is_self_use,
                "holding_years": holding_years
            }
        }
