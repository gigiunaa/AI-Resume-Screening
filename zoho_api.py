import requests
import config
from zoho_auth import auth


def _h():
    return {'Authorization': f'Zoho-oauthtoken {auth.get_token()}'}


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

    if r.status_code == 204 or r.status_code == 400:
        return []

    if r.status_code != 200:
        print(f"[Zoho] Get attachments failed: {r.status_code} - {r.text}")
        return []

    return r.json().get('data', [])


def download_attachment(module, record_id, att_id):
    # Method 1
    url1 = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}"
    print(f"[Zoho] Download attempt 1: {url1}")
    r = requests.get(url1, headers=_h())

    if r.status_code == 200 and len(r.content) > 0:
        print(f"[Zoho] Download success (method 1): {len(r.content)} bytes")
        return r.content

    # Method 2
    url2 = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}/$download"
    print(f"[Zoho] Download attempt 2: {url2}")
    r = requests.get(url2, headers=_h())

    if r.status_code == 200 and len(r.content) > 0:
        print(f"[Zoho] Download success (method 2): {len(r.content)} bytes")
        return r.content

    # Method 3
    url3 = f"https://recruit.zoho.com/recruit/v2/files/{att_id}"
    print(f"[Zoho] Download attempt 3: {url3}")
    r = requests.get(url3, headers=_h())

    if r.status_code == 200 and len(r.content) > 0:
        print(f"[Zoho] Download success (method 3): {len(r.content)} bytes")
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
            print(f"[Zoho] Failed to download: {fname}")
            continue

        text = extract_text(content, att['File_Name'])

        if not text:
            print(f"[Zoho] Failed to parse: {fname}")
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


def update_candidate_fields(cid, data):
    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers={**_h(), 'Content-Type': 'application/json'},
        json={'data': [data]}
    )

    print(f"[Zoho] Update candidate fields status: {r.status_code}")
    print(f"[Zoho] Update candidate fields response: {r.text}")
    return r


def update_candidate_status(cid, status_value):
    payload = {
        'Candidate_Status': status_value
    }

    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers={**_h(), 'Content-Type': 'application/json'},
        json={'data': [payload]}
    )

    print(f"[Zoho] Update status -> {status_value}: {r.status_code}")
    print(f"[Zoho] Update status response: {r.text}")
    return r


def apply_screening_result(cid, score, assessment):
    # Always save score + assessment
    update_candidate_fields(cid, {
        'AI_Score': int(score),
        'AI_Assessment': assessment
    })

    # Then apply status logic
    if score < config.REJECT_THRESHOLD:
        update_candidate_status(cid, config.STATUS_REJECTED)
        return config.STATUS_REJECTED

    if config.REJECT_THRESHOLD <= score < config.SAVE_FOR_FUTURE_THRESHOLD:
        update_candidate_status(cid, config.STATUS_SAVE_FOR_FUTURE)
        return config.STATUS_SAVE_FOR_FUTURE

    # 80+ -> keep current status as is
    print("[Zoho] Score is 80+, keeping current status unchanged")
    return None


def auto_reject_candidate(cid, assessment):
    update_candidate_fields(cid, {
        'AI_Score': 0,
        'AI_Assessment': assessment
    })

    update_candidate_status(cid, config.STATUS_REJECTED)
    return config.STATUS_REJECTED
