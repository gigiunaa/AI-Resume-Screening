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
    url1 = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}"
    print(f"[Zoho] Download attempt 1: {url1}")
    r = requests.get(url1, headers=_h())

    if r.status_code == 200 and len(r.content) > 0:
        print(f"[Zoho] Download success (method 1): {len(r.content)} bytes")
        return r.content

    url2 = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}/$download"
    print(f"[Zoho] Download attempt 2: {url2}")
    r = requests.get(url2, headers=_h())

    if r.status_code == 200 and len(r.content) > 0:
        print(f"[Zoho] Download success (method 2): {len(r.content)} bytes")
        return r.content

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
    """AI_Score და AI_Assessment ველების განახლება"""
    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers={**_h(), 'Content-Type': 'application/json'},
        json={'data': [data]}
    )

    print(f"[Zoho] Update fields status: {r.status_code}")
    print(f"[Zoho] Update fields response: {r.text}")
    return r


def update_candidate_status(cid, jid, status_value):
    """
    Zoho Recruit-ში Candidate_Status-ის შეცვლა.
    ⚠️ სავალდებულოა jobids პარამეტრი!
    
    Args:
        cid: Candidate ID
        jid: Job Opening ID (associated job)
        status_value: ახალი სტატუსი
    """

    url = f"{config.ZOHO_RECRUIT_BASE}/Candidates/status"
    payload = {
        'data': [{
            'ids': [str(cid)],
            'jobids': [str(jid)],          # <-- ეს იყო missing piece!
            'Candidate_Status': status_value
        }]
    }

    print(f"[Zoho] Change Status: {url}")
    print(f"[Zoho] Payload: {payload}")

    r = requests.put(
        url,
        headers={**_h(), 'Content-Type': 'application/json'},
        json=payload
    )

    print(f"[Zoho] Status API response: {r.status_code} - {r.text}")

    if r.status_code == 200:
        result = r.json().get('data', [{}])[0]
        if result.get('code') == 'SUCCESS':
            print(f"[Zoho] ✅ Status changed to: {status_value}")
            return True

    print(f"[Zoho] ❌ Status change failed!")
    return False


def apply_screening_result(cid, jid, score, assessment):
    """
    Score + Assessment შენახვა და სტატუსის ცვლილება.
    
    Args:
        cid: Candidate ID
        jid: Job Opening ID
        score: AI score (0-100)
        assessment: AI assessment text
    """

    # ყოველთვის ვინახავთ score + assessment
    update_candidate_fields(cid, {
        'AI_Score': int(score),
        'AI_Assessment': assessment
    })

    # სტატუსის ლოგიკა
    if score < config.REJECT_THRESHOLD:
        print(f"[Zoho] Score {score} < {config.REJECT_THRESHOLD} -> REJECTING")
        update_candidate_status(cid, jid, config.STATUS_REJECTED)
        return config.STATUS_REJECTED

    if config.REJECT_THRESHOLD <= score < config.SAVE_FOR_FUTURE_THRESHOLD:
        print(f"[Zoho] Score {score} in [{config.REJECT_THRESHOLD}, {config.SAVE_FOR_FUTURE_THRESHOLD}) -> SAVE FOR FUTURE")
        update_candidate_status(cid, jid, config.STATUS_SAVE_FOR_FUTURE)
        return config.STATUS_SAVE_FOR_FUTURE

    # 80+ -> სტატუსი არ იცვლება
    print(f"[Zoho] Score {score} >= {config.SAVE_FOR_FUTURE_THRESHOLD} -> keeping current status")
    return None


def auto_reject_candidate(cid, jid, assessment):
    """
    ქვეყნის მიხედვით ავტო-reject.
    
    Args:
        cid: Candidate ID
        jid: Job Opening ID (შეიძლება None იყოს)
        assessment: reject-ის მიზეზი
    """

    update_candidate_fields(cid, {
        'AI_Score': 0,
        'AI_Assessment': assessment
    })

    if jid:
        update_candidate_status(cid, jid, config.STATUS_REJECTED)
    else:
        print(f"[Zoho] ⚠️ No job_opening_id for auto-reject, trying without jobids...")
        # jobids გარეშე fallback — შეიძლება არ იმუშაოს
        url = f"{config.ZOHO_RECRUIT_BASE}/Candidates/status"
        r = requests.put(
            url,
            headers={**_h(), 'Content-Type': 'application/json'},
            json={'data': [{'ids': [str(cid)], 'Candidate_Status': config.STATUS_REJECTED}]}
        )
        print(f"[Zoho] Fallback status response: {r.status_code} - {r.text}")

    return config.STATUS_REJECTED
