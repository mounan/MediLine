import pandas as pd

class RegistrationTrialExtractor:
    def __init__(self):
        # NLP: Negative Keywords (Logic Doc: Section 2)
        self.negative_keywords = [
            'extension', 'rollover', 'pilot', 'feasibility', 
            'proof of concept', 'poc', 'exploratory', 'expanded access',
            'vitamin', 'yoga', 'dietary', 'device', 'survey', 'questionnaire'
        ]
        # NLP: Positive Keywords (Logic Doc: Section 2)
        self.positive_keywords = [
            'pivotal', 'confirmatory', 'registration', 'registrational', 
            'superiority', 'non-inferiority', 'marketing authorization',
            'bla', 'nda', 'ind filing'
        ]

    def _apply_hard_rules(self, row):
        """
        Logic Doc Section 1: 構造化データによる一次フィルタリング
        """
        reasons = []
        
        # 1. Agency Class: Industry Only
        if str(row['agency_class']).upper() != 'INDUSTRY':
            reasons.append(f"Non-Industry ({row['agency_class']})")
            
        # 2. Responsible Party: Sponsor Only (No IIT)
        # PI (Principal Investigator) は医師主導治験の可能性大
        if str(row['responsible_party_type']).upper() == 'PRINCIPAL_INVESTIGATOR':
            reasons.append("Investigator Initiated Trial (IIT)")
            
        # 3. Phase: Phase 2 or 3
        valid_phases = ['PHASE2', 'PHASE3', 'PHASE 2', 'PHASE 3', 'PHASE 2/3']
        phase_str = str(row['phase']).upper()
        # "Phase 1/Phase 2" のようなケースも考慮し、単純な包含チェックではなくリスト照合推奨だが、
        # ここでは API の Enum に合わせて柔軟に対応
        if phase_str not in valid_phases and "3" not in phase_str and "2" not in phase_str:
             reasons.append(f"Early Phase ({row['phase']})")
             
        # 4. Study Type: Interventional Only
        if str(row['study_type']).upper() != 'INTERVENTIONAL':
            reasons.append(f"Non-Interventional ({row['study_type']})")
            
        # 5. FDA Regulated (Logic Doc: Setting Value = "Yes")
        # ドキュメントに従い厳格化。ただし、完全に弾くと海外治験が消えるため
        # "REJECTED_SOFT"（要確認）として処理する設計にする
        if row['is_fda_regulated_drug'] == 'No' and row['is_fda_regulated_device'] == 'No':
            reasons.append("Not FDA Regulated (Check for Global Trial)")

        # "Not FDA Regulated" だけなら Soft Reject、それ以外は Hard Reject
        if reasons:
            if len(reasons) == 1 and "Not FDA Regulated" in reasons[0]:
                return "REJECTED_SOFT", reasons[0]
            else:
                return "REJECTED_HARD", "; ".join(reasons)
        
        return "PASSED_HARD", None

    def _apply_soft_rules(self, row):
        """
        Logic Doc Section 2: テキストマイニング & Section 3: グレーゾーン判定
        """
        # 詳細説明も含めてスキャン
        text_corpus = (
            str(row['official_title']) + " " + 
            str(row['brief_summary']) + " " + 
            str(row['detailed_description'])
        ).lower()
        
        # 1. Negative Check
        found_neg = [k for k in self.negative_keywords if k in text_corpus]
        if found_neg:
            return "REJECTED_CONTEXT", f"Exploratory Keywords: {found_neg}"
            
        # 2. Positive Check
        found_pos = [k for k in self.positive_keywords if k in text_corpus]
        
        # 3. Phase 2 Pivotal Logic (Logic Doc Step 1: グレーゾーン判定)
        # Phase 2 だが Pivotal などの単語がある -> 優先度高
        is_phase2 = "2" in str(row['phase']) and "3" not in str(row['phase'])
        
        if found_pos:
            if is_phase2:
                # これは「迅速承認」などの可能性が高い重要候補
                return "KEPT_PRIORITY", f"🔥 Phase 2 Pivotal Candidate (Keywords: {found_pos})"
            else:
                return "KEPT_HIGH", f"Confirmed Registration Intent (Keywords: {found_pos})"
            
        # 4. Neutral
        return "KEPT_NEUTRAL", "Qualified Candidate (No Intent Keywords)"

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        results = []
        if df.empty: return df
        
        for _, row in df.iterrows():
            # Stage 1
            status, reason = self._apply_hard_rules(row)
            
            # Stage 2 (Only if Passed Hard Rule)
            if status == "PASSED_HARD":
                status, reason = self._apply_soft_rules(row)
            
            # FDA規制なしだが、ポジティブキーワードがある場合の救済措置 (Optional)
            if status == "REJECTED_SOFT":
                # タイトルに Pivotal と書いてあれば、FDAフラグがNoでも復活させる
                text_corpus = (str(row['official_title'])).lower()
                found_pos = [k for k in self.positive_keywords if k in text_corpus]
                if found_pos:
                    status = "KEPT_HIGH"
                    reason = f"Rescued: Non-FDA but Pivotal Keywords found {found_pos}"

            row_res = row.copy()
            row_res['final_decision'] = status
            row_res['reject_reason'] = reason if reason else "Qualified"
            
            # UI用ステータス分類
            if "REJECTED" in status:
                row_res['ui_status'] = "❌ Rejected"
            elif "PRIORITY" in status:
                row_res['ui_status'] = "🔥 Priority"
            else:
                row_res['ui_status'] = "✅ Kept"
                
            results.append(row_res)
            
        return pd.DataFrame(results)