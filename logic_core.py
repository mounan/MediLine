import pandas as pd
from google import genai
from google.genai import types
import os
import streamlit as st
from dotenv import load_dotenv
import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("MediLine_AI")

load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

class RegistrationTrialExtractor:
    def __init__(self):
        self.model_id = "gemini-3-flash-preview"
        if API_KEY:
            self.client = genai.Client(api_key=API_KEY)
        else:
            self.client = None
            st.error("⚠️ API Key not found")
        
        self.prompt_template = self._load_prompt_template()


    

    def _load_prompt_template(self):
        template_path = os.path.join(os.path.dirname(__file__), 'ct_filter_prompt.txt')
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return None

    def _should_skip_ai_analysis(self, row):
        nct_id = row.get('nct_id', 'Unknown')
        phase = str(row.get('phase', '')).upper()
        if 'PHASE 1' in phase and '2' not in phase:
            return True, "Rule: Phase 1"
        if phase == 'EARLY_PHASE1':
            return True, "Rule: Early Phase 1"
        if phase == 'NOT APPLICABLE':
            return True, "Rule: Phase N/A"

        study_type = str(row.get('study_type', '')).upper()
        if study_type != 'INTERVENTIONAL':
            return True, f"Rule: {study_type}"

        agency = str(row.get('agency_class', '')).upper()
        if agency in ['NIH', 'FED']:
            return True, f"Rule: Non-Industry ({agency})"

        return False, None

    async def _call_gemini_ai_async(self, row):
        nct_id = row.get('nct_id', 'Unknown')

        # 1. Pre-screening
        skip, skip_reason = self._should_skip_ai_analysis(row)
        if skip:
            return 0, skip_reason

        # 2. Prepare AI call
        if not self.client or not self.prompt_template:
            return 0, "Error"

        official_title = row.get('official_title', 'N/A')
        brief_summary = row.get('brief_summary', 'N/A')
        detailed_description = str(row.get('detailed_description', 'N/A'))[:3000] # Truncate for token efficiency

        prompt = self.prompt_template.format(
            official_title=official_title,
            brief_summary=brief_summary,
            detailed_description=detailed_description
        )
        

        try:
            # Configure Safety Settings (BLOCK_NONE)
            response = await self.client.aio.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1, 
                    safety_settings=[
                        types.SafetySetting(
                            category="HARM_CATEGORY_HATE_SPEECH",
                            threshold="BLOCK_NONE"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_DANGEROUS_CONTENT",
                            threshold="BLOCK_NONE"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_HARASSMENT",
                            threshold="BLOCK_NONE"
                        ),
                        types.SafetySetting(
                            category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                            threshold="BLOCK_NONE"
                        ),
                    ]
                )
            )
            
            # Check for empty response
            if not response.text:
                finish_reason = "Unknown"
                if response.candidates:
                    finish_reason = response.candidates[0].finish_reason
                
                logger.error(f"⚠️ [{nct_id}] Empty Response. Finish Reason: {finish_reason}")
                return 0, f"AI Error: Empty Response ({finish_reason})"

            result_text = response.text.strip()

            score = 1 if "1" in result_text else 0
            reason = "AI: Registration Intent" if score == 1 else "AI: Exploratory/Supportive"
            return score, reason

        except Exception as e:
            logger.error(f"⚠️ [{nct_id}] AI API Error: {str(e)}")
            return 0, f"AI API Error: {str(e)}"

    async def _process_all(self, df):
        sem = asyncio.Semaphore(20)

        async def safe_call(row):
            async with sem:
                return await self._call_gemini_ai_async(row)

        tasks = [safe_call(row) for _, row in df.iterrows()]
        return await asyncio.gather(*tasks)

    def process(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty: return df

        try:
            ai_results = asyncio.run(self._process_all(df))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            ai_results = loop.run_until_complete(self._process_all(df))

        final_rows = []
        for (idx, row), (score, reason) in zip(df.iterrows(), ai_results):
            status = ""
            if score == 0:
                if reason.startswith("Rule"):
                    status = "REJECTED_RULE"
                else:
                    status = "REJECTED_AI"
            else:
                phase_str = str(row.get('phase', '')).upper()
                is_p2 = "2" in phase_str and "3" not in phase_str
                status = "KEPT_PRIORITY" if is_p2 else "KEPT_HIGH"
            
            row_res = row.copy()
            row_res['final_decision'] = status
            row_res['reject_reason'] = reason
            
            if "REJECTED" in status:
                row_res['ui_status'] = "❌ Rejected"
            elif "PRIORITY" in status:
                row_res['ui_status'] = "🔥 Priority"
            else:
                row_res['ui_status'] = "✅ Kept"
            final_rows.append(row_res)
            
        return pd.DataFrame(final_rows)