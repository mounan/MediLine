import requests
import pandas as pd
import streamlit as st

# API Endpoint
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


def fetch_real_data(limit=10, query_term="lung cancer"):
    """
    ClinicalTrials.gov API v2 からデータを取得。
    Update: Logic Documentに基づき、DetailedDescription, PrimaryOutcome, CompletionDateを追加。
    """

    params = {
        "format": "json",
        "pageSize": limit,
        "query.term": query_term,
        "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|COMPLETED",
        "sort": "LastUpdatePostDate:desc"
    }

    try:
        if st.runtime.exists():
            with st.spinner(f'Fetching {limit} trials for "{query_term}"...'):
                response = requests.get(BASE_URL, params=params, timeout=20)
        else:
            print(f"Requesting API: {BASE_URL}...")
            response = requests.get(BASE_URL, params=params, timeout=20)

        response.raise_for_status()
        data = response.json()

    except Exception as e:
        print(f"⚠️ API Connection Error: {e}")
        return pd.DataFrame()

    trials = []

    if 'studies' not in data:
        return pd.DataFrame()

    for study in data['studies']:
        try:
            proto = study.get('protocolSection', {})

            # --- Identification ---
            ident = proto.get('identificationModule', {})
            nct_id = ident.get('nctId', 'N/A')
            title = ident.get('officialTitle') or ident.get(
                'briefTitle', 'No Title')
            org_study_id = ident.get('orgStudyIdInfo', {}).get('id', 'N/A')

            # --- Sponsor & Responsibility ---
            sponsor_mod = proto.get('sponsorCollaboratorsModule', {})
            lead_sponsor = sponsor_mod.get('leadSponsor', {})
            sponsor_name = lead_sponsor.get('name', 'Unknown')
            agency_class = lead_sponsor.get('class', 'OTHER')

            resp_party = sponsor_mod.get('responsibleParty', {})
            resp_type = resp_party.get('type', 'Unknown')

            # --- Status & Dates (For Launch Prediction) ---
            status_mod = proto.get('statusModule', {})
            # Primary Completion Date (主要評価項目データ収集完了日)
            pcd_struct = status_mod.get('primaryCompletionDateStruct', {})
            primary_completion_date = pcd_struct.get('date', 'N/A')

            # --- Oversight (FDA Regulation) ---
            oversight = proto.get('oversightModule', {})
            is_fda_drug = "Yes" if oversight.get(
                'isFdaRegulatedDrug') is True else "No"
            is_fda_device = "Yes" if oversight.get(
                'isFdaRegulatedDevice') is True else "No"

            # --- Design ---
            design = proto.get('designModule', {})
            study_type = design.get('studyType', 'Unknown')
            phases_list = design.get('phases', [])
            phase = phases_list[0] if phases_list else "Not Applicable"

            # --- Intervention (Drugs) ---
            arms = proto.get('armsInterventionsModule', {})
            interventions_list = arms.get('interventions', [])
            drug_names = []
            aliases = []
            for item in interventions_list:
                if item.get('type') in [
                        'DRUG', 'BIOLOGICAL', 'GENETIC', 'COMBINATION_PRODUCT'
                ]:
                    drug_names.append(item.get('name'))
                    if 'otherNames' in item:
                        aliases.extend(item['otherNames'])
            intervention_str = ", ".join(
                drug_names) if drug_names else "No Drug Listed"
            alias_str = ", ".join(aliases) if aliases else ""

            # --- Text Corpus (For Mining) ---
            desc_mod = proto.get('descriptionModule', {})
            brief_summary = desc_mod.get('briefSummary', '')
            detailed_desc = desc_mod.get('detailedDescription', '')  # 追加: 詳細説明

            # --- Outcomes (For Expert Review) ---
            out_mod = proto.get('outcomesModule', {})
            prim_outcomes = out_mod.get('primaryOutcomes', [])
            # 主要評価項目のリストを文字列化 (例: "OS; PFS")
            prim_measures = [p.get('measure', '') for p in prim_outcomes]
            primary_outcome_str = "; ".join(
                prim_measures) if prim_measures else "N/A"

            # --- データの格納 ---
            trials.append({
                "nct_id": nct_id,
                "official_title": title,
                "sponsor_name": sponsor_name,
                "agency_class": agency_class,
                "phase": phase,
                "study_type": study_type,
                "responsible_party_type": resp_type,
                "is_fda_regulated_drug": is_fda_drug,
                "is_fda_regulated_device": is_fda_device,
                "intervention_name": intervention_str,
                "aliases": alias_str,
                "org_study_id": org_study_id,
                "brief_summary": brief_summary,
                "detailed_description": detailed_desc,  # New
                "primary_completion_date": primary_completion_date,  # New
                "primary_outcomes": primary_outcome_str  # New
            })

        except Exception as parse_err:
            continue

    return pd.DataFrame(trials)
