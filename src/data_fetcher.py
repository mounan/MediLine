import requests
import pandas as pd
import streamlit as st
import json

# API Endpoint
BASE_URL = "https://clinicaltrials.gov/api/v2/studies"


def fetch_real_data(limit=10, query_term="lung cancer", sponsor_term=None):
    """
    ClinicalTrials.gov API v2 からデータを取得。
    query_term: 疾患・条件 (query.term / query.cond)
    sponsor_term: スポンサー名 (query.spons)
    """

    # 基础参数
    params = {
        "format": "json",
        "pageSize": limit,
        "filter.overallStatus": "RECRUITING|ACTIVE_NOT_RECRUITING|COMPLETED",
        "sort": "LastUpdatePostDate:desc",
    }

    # 动态添加搜索条件
    # query_term 用于搜索疾病/条件 (API原有的 query.term)
    if query_term:
        params["query.term"] = query_term
    
    # 新增: sponsor_term 用于搜索特定公司 (API的 query.spons)
    if sponsor_term:
        params["query.spons"] = sponsor_term

    try:
        # 显示正在搜索的内容
        search_msg = f'"{query_term}"'
        if sponsor_term:
            search_msg += f' + Sponsor: "{sponsor_term}"'

        if st.runtime.exists():
            with st.spinner(f'Fetching {limit} trials for {search_msg}...'):
                response = requests.get(BASE_URL, params=params, timeout=20)
        else:
            print(f"Requesting API: {BASE_URL} with params {params}...")
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

            # --- Arms & Interventions ---
            arms_module = proto.get('armsInterventionsModule', {})

            # 試験臂（Arms）の取得
            arm_groups = arms_module.get('armGroups', [])
            arms_info = []
            for arm in arm_groups:
                arms_info.append({
                    "label":
                    arm.get('label', ''),
                    "type":
                    arm.get('type', ''),
                    "description":
                    arm.get('description', '')[:200]
                })

            # 干预措施（Interventions）の詳細取得
            interventions_list = arms_module.get('interventions', [])
            interventions_detailed = []
            drug_names = []
            aliases = []

            for item in interventions_list:
                intervention_type = item.get('type', '')
                if intervention_type in [
                        'DRUG', 'BIOLOGICAL', 'GENETIC', 'COMBINATION_PRODUCT'
                ]:
                    drug_name = item.get('name', '')
                    other_names = item.get('otherNames', [])
                    arm_labels = item.get('armGroupLabels', [])

                    drug_names.append(drug_name)
                    aliases.extend(other_names)

                    # 簡略版: roleなし
                    interventions_detailed.append({
                        "name":
                        drug_name,
                        "type":
                        intervention_type,
                        "aliases":
                        other_names,
                        "arms":
                        arm_labels,
                        "description":
                        item.get('description', '')[:200]
                    })

            # 主要新薬の識別
            primary_drug = _identify_primary_drug(
                interventions=interventions_detailed,
                arms_info=arms_info,
                sponsor_name=sponsor_name,
                title=title)

            # 従来形式の文字列（後方互換性）
            intervention_str = ", ".join(
                drug_names) if drug_names else "No Drug Listed"
            alias_str = ", ".join(aliases) if aliases else ""

            # --- Text Corpus (For Mining) ---
            desc_mod = proto.get('descriptionModule', {})
            brief_summary = desc_mod.get('briefSummary', '')
            detailed_desc = desc_mod.get('detailedDescription', '')

            # --- Outcomes (For Expert Review) ---
            out_mod = proto.get('outcomesModule', {})
            prim_outcomes = out_mod.get('primaryOutcomes', [])
            prim_measures = [p.get('measure', '') for p in prim_outcomes]
            primary_outcome_str = "; ".join(
                prim_measures) if prim_measures else "N/A"

            # --- データの格納 ---
            trials.append({
                "nct_id":
                nct_id,
                "official_title":
                title,
                "sponsor_name":
                sponsor_name,
                "agency_class":
                agency_class,
                "phase":
                phase,
                "study_type":
                study_type,
                "responsible_party_type":
                resp_type,
                "is_fda_regulated_drug":
                is_fda_drug,
                "is_fda_regulated_device":
                is_fda_device,

                # 従来形式（後方互換性）
                "intervention_name":
                intervention_str,
                "aliases":
                alias_str,

                # 主要新薬
                "primary_drug_name":
                primary_drug.get('name', '') if primary_drug else '',
                "primary_drug_aliases":
                ", ".join(primary_drug.get('aliases', []))
                if primary_drug else '',

                # 詳細構造（JSON文字列）
                "interventions_json":
                json.dumps(interventions_detailed, ensure_ascii=False),
                "arms_json":
                json.dumps(arms_info, ensure_ascii=False),

                # 薬物数とプラセボ有無
                "drug_count":
                len([
                    i for i in interventions_detailed
                    if i['type'] in ['DRUG', 'BIOLOGICAL']
                ]),
                "has_placebo":
                any('placebo' in i['name'].lower()
                    for i in interventions_detailed),
                "org_study_id":
                org_study_id,
                "brief_summary":
                brief_summary,
                "detailed_description":
                detailed_desc,
                "primary_completion_date":
                primary_completion_date,
                "primary_outcomes":
                primary_outcome_str
            })

        except Exception as parse_err:
            continue

    return pd.DataFrame(trials)


def _identify_primary_drug(interventions: list, arms_info: list,
                           sponsor_name: str, title: str) -> dict:
    """
    主要新薬を識別する
    
    優先順位:
    1. EXPERIMENTAL臂にのみ存在する薬物
    2. スポンサーの製品と推定される薬物
    3. タイトルに含まれる薬物
    4. 最初のDRUG/BIOLOGICAL（プラセボ以外）
    """
    if not interventions:
        return None

    # EXPERIMENTAL臂のラベルを取得
    experimental_arms = set()
    for arm in arms_info:
        if arm.get('type', '').upper() == 'EXPERIMENTAL':
            experimental_arms.add(arm['label'])

    # 1. EXPERIMENTAL臂にのみ存在する薬物を探す
    for drug in interventions:
        if 'placebo' in drug['name'].lower():
            continue
        drug_arms = set(drug.get('arms', []))
        # この薬物がEXPERIMENTAL臂にのみ存在するか
        if drug_arms and drug_arms.issubset(experimental_arms):
            return drug

    # 2. スポンサーの製品を探す
    for drug in interventions:
        if 'placebo' in drug['name'].lower():
            continue
        if _is_sponsor_drug(drug['name'], sponsor_name):
            return drug

    # 3. タイトルに含まれる薬物を探す
    title_lower = title.lower()
    for drug in interventions:
        if 'placebo' in drug['name'].lower():
            continue
        drug_name_lower = drug['name'].lower()
        first_word = drug_name_lower.split()[0] if drug_name_lower else ''
        if first_word and len(first_word) > 3 and first_word in title_lower:
            return drug

    # 4. 最初のDRUG/BIOLOGICAL（プラセボ以外）
    for drug in interventions:
        if drug['type'] in ['DRUG', 'BIOLOGICAL'
                            ] and 'placebo' not in drug['name'].lower():
            return drug

    return interventions[0] if interventions else None


def _is_sponsor_drug(drug_name: str, sponsor_name: str) -> bool:
    """
    薬物がスポンサーの製品かどうかを推定
    """
    sponsor_lower = sponsor_name.lower()
    drug_lower = drug_name.lower()

    sponsor_prefixes = {
        'merck': ['mk-', 'keytruda'],
        'bristol': ['bms-', 'opdivo'],
        'roche': ['ro-', 'tecentriq'],
        'genentech': ['ro-', 'tecentriq'],
        'hoffmann': ['ro-'],  # Hoffmann-La Roche
        'pfizer': ['pf-', 'ibrance'],
        'novartis': ['nvp-', 'kisqali'],
        'astrazeneca': ['azd-', 'imfinzi', 'tagrisso'],
        'lilly': ['ly-', 'verzenio'],
        'abbvie': ['abbv-'],
        'mirati': ['mrtx-', 'adagrasib', 'krazati'],
        'amgen': ['amg-'],
        'sanofi': ['sar-'],
        'bayer': ['bay-'],
        'takeda': ['tak-'],
        'gilead': ['gs-'],
    }

    for sponsor_key, prefixes in sponsor_prefixes.items():
        if sponsor_key in sponsor_lower:
            for prefix in prefixes:
                if prefix in drug_lower:
                    return True

    return False


# ============================================================================
# ユーティリティ関数: 並査集（Union-Find）用のデータ抽出
# ============================================================================


def extract_drug_aliases_for_union_find(df: pd.DataFrame) -> list:
    """
    DataFrameから薬物名と別名のペアを抽出（並査集構築用）
    
    Returns:
        list of tuples: [(drug_name, alias), ...]
    """
    pairs = []

    for _, row in df.iterrows():
        try:
            interventions = json.loads(row.get('interventions_json', '[]'))
            for drug in interventions:
                drug_name = drug.get('name', '')
                aliases = drug.get('aliases', [])

                for alias in aliases:
                    if alias and drug_name:
                        pairs.append((drug_name, alias))
        except:
            continue

    return pairs


def get_all_drug_names(df: pd.DataFrame) -> set:
    """
    DataFrameから全ての薬物名（主名称+別名）を抽出
    
    Returns:
        set: 全ての薬物名
    """
    all_names = set()

    for _, row in df.iterrows():
        try:
            interventions = json.loads(row.get('interventions_json', '[]'))
            for drug in interventions:
                drug_name = drug.get('name', '')
                if drug_name:
                    all_names.add(drug_name)

                aliases = drug.get('aliases', [])
                for alias in aliases:
                    if alias:
                        all_names.add(alias)
        except:
            continue

    return all_names
