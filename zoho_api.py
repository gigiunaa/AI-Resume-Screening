import requests
import config
from zoho_auth import auth


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
#  ძირითადი ცვლილება: სტატუსის განახლების ლოგიკა
# ============================================================

def _update_record(cid, fields):
    """
    ერთიანი update ფუნქცია — ყველა ველს ერთ API call-ში აგზავნის.
    აბრუნებს (success: bool, response_detail: str)
    """
    payload = {'data': [fields]}

    print(f"[Zoho] Updating candidate {cid}")
    print(f"[Zoho] Payload: {fields}")

    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers=_api_headers(),
        json=payload
    )

    print(f"[Zoho] Response status: {r.status_code}")
    print(f"[Zoho] Response body: {r.text}")

    # --- Response validation ---
    if r.status_code != 200:
        return False, f"HTTP {r.status_code}: {r.text}"

    try:
        resp_json = r.json()
    except Exception:
        return False, f"Invalid JSON response: {r.text}"

    # Zoho returns {"data": [{"code": "SUCCESS", ...}]}
    if 'data' not in resp_json:
        return False, f"No 'data' in response: {resp_json}"

    record_result = resp_json['data'][0]
    code = record_result.get('code', '')
    details = record_result.get('details', {})
    message = record_result.get('message', '')

    if code == 'SUCCESS':
        print(f"[Zoho] ✅ Update SUCCESS: {details}")
        return True, "SUCCESS"
    else:
        print(f"[Zoho] ❌ Update FAILED: code={code}, message={message}, details={details}")
        return False, f"{code}: {message}"


def _verify_candidate_status(cid, expected_status):
    """
    განახლების შემდეგ — ვამოწმებთ რეალურად შეიცვალა თუ არა
    """
    try:
        candidate = get_candidate(cid)
        actual_status = candidate.get('Candidate_Status', 'Unknown')
        ai_score = candidate.get('AI_Score', 'N/A')

        if actual_status == expected_status:
            print(f"[Zoho] ✅ VERIFIED: Status = '{actual_status}', AI_Score = {ai_score}")
            return True
        else:
            print(f"[Zoho] ❌ MISMATCH: Expected '{expected_status}', Got '{actual_status}'")
            return False
    except Exception as e:
        print(f"[Zoho] Verification failed: {e}")
        return False


def apply_screening_result(cid, score, assessment):
    """
    AI Score + Assessment + Status — ყველაფერი ერთ API call-ში
    """
    score = int(score)

    # 1. სტატუსის განსაზღვრა
    if score < config.REJECT_THRESHOLD:
        target_status = config.STATUS_REJECTED
    elif score < config.SAVE_FOR_FUTURE_THRESHOLD:
        target_status = config.STATUS_SAVE_FOR_FUTURE
    else:
        target_status = None  # 80+ → სტატუსი არ იცვლება

    print(f"\n[Zoho] === APPLYING SCREENING RESULT ===")
    print(f"[Zoho] Score: {score}")
    print(f"[Zoho] Target status: {target_status or 'NO CHANGE (80+)'}")

    # 2. ველების მომზადება — ყველაფერი ერთ payload-ში
    fields = {
        'AI_Score': score,
        'AI_Assessment': str(assessment)[:2000]  # Zoho text field limit
    }

    if target_status:
        fields['Candidate_Status'] = target_status

    # 3. ერთი API call — score + assessment + status ერთად
    success, detail = _update_record(cid, fields)

    if success:
        print(f"[Zoho] ✅ Combined update succeeded")
    else:
        print(f"[Zoho] ❌ Combined update failed: {detail}")

        # 4. Fallback: თუ ერთიანი ვერ მოხერხდა, ცალ-ცალკე ვცადოთ
        print(f"[Zoho] Trying separate updates as fallback...")

        # ჯერ score + assessment
        success_fields, _ = _update_record(cid, {
            'AI_Score': score,
            'AI_Assessment': str(assessment)[:2000]
        })
        print(f"[Zoho] Fields update: {'✅' if success_fields else '❌'}")

        # მერე status ცალკე
        if target_status:
            success_status, detail_status = _update_record(cid, {
                'Candidate_Status': target_status
            })
            print(f"[Zoho] Status update: {'✅' if success_status else '❌'}")

            if not success_status:
                # მეთოდი 3: status change action endpoint
                print(f"[Zoho] Trying status change action endpoint...")
                _change_status_via_action(cid, target_status)

    # 5. ვერიფიკაცია — ნამდვილად შეიცვალა?
    if target_status:
        print(f"[Zoho] Verifying status change...")
        verified = _verify_candidate_status(cid, target_status)
        if not verified:
            print(f"[Zoho] ⚠️ WARNING: Status verification failed!")
            print(f"[Zoho] ⚠️ The status might not have changed in Zoho")

    print(f"[Zoho] === SCREENING RESULT APPLIED ===\n")
    return target_status


def _change_status_via_action(cid, status_value):
    """
    ალტერნატიული მეთოდი: Zoho Recruit status change action endpoint
    ზოგ Zoho კონფიგურაციაში მხოლოდ ეს მეთოდი მუშაობს
    """
    url = f"{config.ZOHO_RECRUIT_BASE}/Candidates/actions/status"
    payload = {
        'data': [{
            'ids': [str(cid)],
            'Candidate_Status': status_value
        }]
    }

    print(f"[Zoho] Action endpoint URL: {url}")
    print(f"[Zoho] Action endpoint payload: {payload}")

    r = requests.put(url, headers=_api_headers(), json=payload)

    print(f"[Zoho] Action endpoint response: {r.status_code}")
    print(f"[Zoho] Action endpoint body: {r.text}")

    return r.status_code == 200


def auto_reject_candidate(cid, assessment):
    """ქვეყნით auto-reject"""
    print(f"\n[Zoho] === AUTO REJECT BY COUNTRY ===")

    fields = {
        'AI_Score': 0,
        'AI_Assessment': str(assessment),
        'Candidate_Status': config.STATUS_REJECTED
    }

    success, detail = _update_record(cid, fields)

    if not success:
        print(f"[Zoho] Combined auto-reject failed, trying separately...")
        _update_record(cid, {'AI_Score': 0, 'AI_Assessment': str(assessment)})
        _update_record(cid, {'Candidate_Status': config.STATUS_REJECTED})
        _change_status_via_action(cid, config.STATUS_REJECTED)

    _verify_candidate_status(cid, config.STATUS_REJECTED)
    print(f"[Zoho] === AUTO REJECT DONE ===\n")
    return config.STATUS_REJECTED
