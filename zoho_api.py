import requests
import config
from zoho_auth import auth
import json as json_lib


def _h():
    return {'Authorization': f'Zoho-oauthtoken {auth.get_token()}'}


def _api_headers():
    return {
        'Authorization': f'Zoho-oauthtoken {auth.get_token()}',
        'Content-Type': 'application/json'
    }


def get_candidate(cid):
    r = requests.get(f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}", headers=_h())
    r.raise_for_status()
    return r.json()['data'][0]


def get_job_opening(jid):
    r = requests.get(f"{config.ZOHO_RECRUIT_BASE}/Job_Openings/{jid}", headers=_h())
    r.raise_for_status()
    return r.json()['data'][0]


def get_associated_job(cid):
    r = requests.get(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}/associate",
        headers=_h()
    )
    if r.status_code != 200:
        print(f"[Zoho] No associated job: {r.status_code} - {r.text}")
        return None
    data = r.json()
    if 'data' in data and len(data['data']) > 0:
        return data['data'][0]
    return None


def get_attachments(module, record_id):
    r = requests.get(
        f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments",
        headers=_h()
    )
    if r.status_code in (204, 400):
        return []
    if r.status_code != 200:
        print(f"[Zoho] Get attachments failed: {r.status_code} - {r.text}")
        return []
    return r.json().get('data', [])


def download_attachment(module, record_id, att_id):
    urls = [
        f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}",
        f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}/$download",
        f"https://recruit.zoho.com/recruit/v2/files/{att_id}",
    ]
    for i, url in enumerate(urls, 1):
        print(f"[Zoho] Download attempt {i}: {url}")
        r = requests.get(url, headers=_h())
        if r.status_code == 200 and len(r.content) > 0:
            print(f"[Zoho] Download success (method {i}): {len(r.content)} bytes")
            return r.content
    print(f"[Zoho] All download methods failed for attachment {att_id}")
    return None


def get_candidate_cv(cid):
    attachments = get_attachments("Candidates", cid)
    for att in attachments:
        fname = att.get('File_Name', '').lower()
        if any(ext in fname for ext in ['.pdf', '.docx', '.doc']):
            content = download_attachment("Candidates", cid, att['id'])
            if content:
                return content, att['File_Name']
    return None, None


def get_job_documents(jid):
    from file_parser import extract_text

    attachments = get_attachments("Job_Openings", jid)
    jd_text = None
    icp_text = None

    print(f"[Zoho] Found {len(attachments)} attachments for job {jid}")

    for att in attachments:
        fname = att.get('File_Name', '').lower()
        att_id = att.get('id')
        print(f"[Zoho] Processing attachment: {fname} (ID: {att_id})")

        content = download_attachment("Job_Openings", jid, att_id)
        if not content:
            continue

        text = extract_text(content, att['File_Name'])
        if not text:
            continue

        print(f"[Zoho] Parsed {fname}: {len(text)} chars")

        if 'jd' in fname or 'job' in fname or 'description' in fname:
            jd_text = text
        elif 'icp' in fname or 'ideal' in fname or 'profile' in fname:
            icp_text = text
        else:
            if jd_text is None:
                jd_text = text
            elif icp_text is None:
                icp_text = text

    return jd_text, icp_text


# ============================================================
#  CORE: Update & Status Change Logic
# ============================================================

def _update_record(cid, fields):
    """ველების განახლება (არა სტატუსი)"""
    payload = {'data': [fields]}
    print(f"[Zoho] Updating candidate {cid}: {fields}")

    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers=_api_headers(),
        json=payload
    )
    print(f"[Zoho] Response: {r.status_code} - {r.text}")

    if r.status_code != 200:
        return False, f"HTTP {r.status_code}"

    try:
        resp = r.json()
        code = resp.get('data', [{}])[0].get('code', '')
        return code == 'SUCCESS', code
    except Exception:
        return False, "Parse error"


def _get_blueprint_transitions(cid):
    """
    Blueprint-ის ხელმისაწვდომი transition-ების წამოღება
    """
    url = f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}/actions/blueprint"
    print(f"[Blueprint] Getting transitions: {url}")

    r = requests.get(url, headers=_h())
    print(f"[Blueprint] Response: {r.status_code}")

    if r.status_code != 200:
        print(f"[Blueprint] No blueprint or error: {r.text}")
        return None, []

    data = r.json()
    print(f"[Blueprint] Full response: {json_lib.dumps(data, indent=2)}")

    blueprint = data.get('blueprint', {})
    transitions = blueprint.get('transitions', [])

    print(f"[Blueprint] Found {len(transitions)} transitions:")
    for t in transitions:
        print(f"  - ID: {t.get('id')} | Name: '{t.get('name')}' "
              f"| Next: '{t.get('next_field_value', 'N/A')}'")

    return blueprint, transitions


def _find_transition_to_status(transitions, target_status):
    """
    target_status-ზე გადასვლის transition-ის პოვნა
    """
    target_lower = target_status.lower().strip()

    for t in transitions:
        # მეთოდი 1: next_field_value-ით
        next_val = str(t.get('next_field_value', '')).lower().strip()
        if next_val == target_lower:
            print(f"[Blueprint] ✅ Found transition by next_field_value: {t.get('name')} (ID: {t.get('id')})")
            return t

        # მეთოდი 2: name-ით
        name = str(t.get('name', '')).lower().strip()
        if target_lower in name or name in target_lower:
            print(f"[Blueprint] ✅ Found transition by name: {t.get('name')} (ID: {t.get('id')})")
            return t

    print(f"[Blueprint] ❌ No transition found for '{target_status}'")
    return None


def _execute_blueprint_transition(cid, transition):
    """
    Blueprint transition-ის შესრულება
    """
    transition_id = transition.get('id')
    url = f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}/actions/blueprint"

    payload = {
        "blueprint": [
            {
                "transition_id": str(transition_id),
                "data": {}
            }
        ]
    }

    print(f"[Blueprint] Executing transition ID: {transition_id}")
    print(f"[Blueprint] URL: {url}")
    print(f"[Blueprint] Payload: {json_lib.dumps(payload)}")

    r = requests.put(url, headers=_api_headers(), json=payload)

    print(f"[Blueprint] Execute response: {r.status_code}")
    print(f"[Blueprint] Execute body: {r.text}")

    if r.status_code == 200:
        resp = r.json()
        code = resp.get('data', [{}])[0].get('code', '') if 'data' in resp else ''
        if code == 'SUCCESS' or r.status_code == 200:
            print(f"[Blueprint] ✅ Transition executed successfully")
            return True

    print(f"[Blueprint] ❌ Transition failed")
    return False


def _change_status_via_blueprint(cid, target_status):
    """
    Blueprint-ის მეშვეობით სტატუსის შეცვლა
    შეიძლება რამდენიმე ნაბიჯი იყოს საჭირო (multi-step)
    """
    max_steps = 5  # უსაფრთხოების ლიმიტი
    
    for step in range(max_steps):
        print(f"\n[Blueprint] === Step {step + 1} ===")
        
        # მიმდინარე სტატუსის შემოწმება
        candidate = get_candidate(cid)
        current = candidate.get('Candidate_Status', '')
        print(f"[Blueprint] Current status: '{current}'")
        
        if current.lower().strip() == target_status.lower().strip():
            print(f"[Blueprint] ✅ Already at target status!")
            return True
        
        # ხელმისაწვდომი transition-ები
        blueprint, transitions = _get_blueprint_transitions(cid)
        
        if not transitions:
            print(f"[Blueprint] No transitions available from '{current}'")
            return False
        
        # target-ისკენ transition
        transition = _find_transition_to_status(transitions, target_status)
        
        if not transition:
            # შეიძლება შუალედური ნაბიჯი გჭირდეს
            print(f"[Blueprint] No direct transition to '{target_status}'")
            print(f"[Blueprint] Available transitions:")
            for t in transitions:
                print(f"  → {t.get('name')} (next: {t.get('next_field_value', '?')})")
            return False
        
        # transition-ის შესრულება
        success = _execute_blueprint_transition(cid, transition)
        if not success:
            return False
    
    return False


def _verify_candidate_status(cid, expected_status):
    """განახლების ვერიფიკაცია"""
    try:
        candidate = get_candidate(cid)
        actual = candidate.get('Candidate_Status', 'Unknown')
        ai_score = candidate.get('AI_Score', 'N/A')

        if actual == expected_status:
            print(f"[Zoho] ✅ VERIFIED: Status='{actual}', AI_Score={ai_score}")
            return True
        else:
            print(f"[Zoho] ❌ MISMATCH: Expected='{expected_status}', Got='{actual}'")
            return False
    except Exception as e:
        print(f"[Zoho] Verification error: {e}")
        return False


def apply_screening_result(cid, score, assessment):
    """
    მთავარი ფუნქცია: AI Score + Assessment + Status
    """
    score = int(score)

    if score < config.REJECT_THRESHOLD:
        target_status = config.STATUS_REJECTED
    elif score < config.SAVE_FOR_FUTURE_THRESHOLD:
        target_status = config.STATUS_SAVE_FOR_FUTURE
    else:
        target_status = None

    print(f"\n[Zoho] === APPLYING SCREENING RESULT ===")
    print(f"[Zoho] Score: {score}")
    print(f"[Zoho] Target status: {target_status or 'NO CHANGE (80+)'}")

    # 1. AI_Score + AI_Assessment ჩაწერა (ეს მუშაობს)
    fields_success, _ = _update_record(cid, {
        'AI_Score': score,
        'AI_Assessment': str(assessment)[:2000]
    })
    print(f"[Zoho] Fields (score+assessment): {'✅' if fields_success else '❌'}")

    # 2. სტატუსის ცვლილება Blueprint-ით
    if target_status:
        print(f"\n[Zoho] Changing status via Blueprint...")
        bp_success = _change_status_via_blueprint(cid, target_status)

        if bp_success:
            print(f"[Zoho] ✅ Blueprint status change succeeded")
        else:
            print(f"[Zoho] ❌ Blueprint failed, trying direct update...")
            _update_record(cid, {'Candidate_Status': target_status})

        # ვერიფიკაცია
        _verify_candidate_status(cid, target_status)

    print(f"[Zoho] === SCREENING RESULT APPLIED ===\n")
    return target_status


def auto_reject_candidate(cid, assessment):
    """ქვეყნით auto-reject"""
    print(f"\n[Zoho] === AUTO REJECT BY COUNTRY ===")

    _update_record(cid, {
        'AI_Score': 0,
        'AI_Assessment': str(assessment)
    })

    bp_success = _change_status_via_blueprint(cid, config.STATUS_REJECTED)

    if not bp_success:
        _update_record(cid, {'Candidate_Status': config.STATUS_REJECTED})

    _verify_candidate_status(cid, config.STATUS_REJECTED)
    print(f"[Zoho] === AUTO REJECT DONE ===\n")
    return config.STATUS_REJECTED
