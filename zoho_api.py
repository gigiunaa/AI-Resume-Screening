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
    """
    ✅ იპოვის Job Opening ID-ს რომელზეც Associated არის კანდიდატი
    """
    candidate = get_candidate(cid)
    
    # მეთოდი 1: Latest_Job_Opening ველიდან
    job_name = candidate.get('Latest_Job_Opening')
    if job_name:
        try:
            r = requests.get(
                f"{config.ZOHO_RECRUIT_BASE}/Job_Openings/search",
                headers=_h(),
                params={"criteria": f"(Posting_Title:equals:{job_name})"}
            )
            if r.status_code == 200 and r.json().get('data'):
                job_id = r.json()['data'][0]['id']
                print(f"[Zoho] Found associated job: {job_name} (ID: {job_id})")
                return job_id
        except Exception as e:
            print(f"[Zoho] Error finding job by name: {e}")
    
    print(f"[Zoho] No associated job found for candidate {cid}")
    return None


def get_attachments(module, record_id):
    r = requests.get(
        f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments",
        headers=_h()
    )

    if r.status_code == 204 or r.status_code == 400:
        return []

    if r.status_code != 200:
        print(f"[Zoho] Get attachments failed: {r.status_code}")
        return []

    return r.json().get('data', [])


def download_attachment(module, record_id, att_id):
    url = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}"
    r = requests.get(url, headers=_h())

    if r.status_code == 200 and len(r.content) > 0:
        return r.content

    print(f"[Zoho] Failed to download attachment {att_id}")
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

    for att in attachments:
        fname = att.get('File_Name', '').lower()
        content = download_attachment("Job_Openings", jid, att['id'])

        if not content:
            continue

        text = extract_text(content, att['File_Name'])
        if not text:
            continue

        if 'jd' in fname or 'job' in fname:
            jd_text = text
        elif 'icp' in fname or 'ideal' in fname:
            icp_text = text
        elif not jd_text:
            jd_text = text

    return jd_text, icp_text


def update_candidate_fields(cid, data):
    """AI_Score და AI_Assessment ველების განახლება"""
    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers={**_h(), 'Content-Type': 'application/json'},
        json={'data': [data]}
    )
    print(f"[Zoho] Update fields: {r.status_code}")
    return r


def update_candidate_status(cid, jid, status_value):
    """
    ✅ Candidate_Status-ის შეცვლა jobids-ით
    
    Args:
        cid: Candidate ID
        jid: Job Opening ID (can be None for non-Associated candidates)
        status_value: New status
    """
    if not jid:
        # ვეძებთ associated job-ს
        print("[Zoho] No job_opening_id provided, trying to find it...")
        jid = get_associated_job(cid)
    
    if jid:
        # ✅ Associated candidate - use jobids
        payload = {
            'data': [{
                'ids': [str(cid)],
                'jobids': [str(jid)],
                'Candidate_Status': status_value
            }]
        }
        
        r = requests.put(
            f"{config.ZOHO_RECRUIT_BASE}/Candidates/status",
            headers={**_h(), 'Content-Type': 'application/json'},
            json=payload,
            timeout=30
        )
        
        print(f"[Zoho] Status update (with jobids): {r.status_code}")
        
        if r.status_code == 200:
            result = r.json().get('data', [{}])[0]
            if result.get('code') == 'SUCCESS':
                print(f"[Zoho] ✅ Status → {status_value}")
                return True
            else:
                print(f"[Zoho] ❌ {result.get('message')}")
        else:
            print(f"[Zoho] ❌ HTTP {r.status_code}: {r.text}")
        
        return False
    
    else:
        # Fallback: direct field update (for non-Associated)
        print("[Zoho] No job found, trying direct update...")
        
        payload = {'Candidate_Status': status_value}
        
        r = requests.put(
            f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
            headers={**_h(), 'Content-Type': 'application/json'},
            json={'data': [payload]},
            timeout=30
        )
        
        print(f"[Zoho] Direct status update: {r.status_code}")
        print(f"[Zoho] Response: {r.text}")
        
        return r.status_code == 200


def apply_screening_result(cid, jid, score, assessment):
    """
    ✅ Score + Assessment შენახვა და სტატუსის ცვლილება
    
    Args:
        cid: Candidate ID
        jid: Job Opening ID (can be None)
        score: AI score
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

    if score < config.SAVE_FOR_FUTURE_THRESHOLD:
        print(f"[Zoho] Score {score} < {config.SAVE_FOR_FUTURE_THRESHOLD} -> SAVE FOR FUTURE")
        update_candidate_status(cid, jid, config.STATUS_SAVE_FOR_FUTURE)
        return config.STATUS_SAVE_FOR_FUTURE

    # 80+ -> სტატუსი არ იცვლება
    print(f"[Zoho] Score {score} >= {config.SAVE_FOR_FUTURE_THRESHOLD} -> keeping status")
    return None


def auto_reject_candidate(cid, jid, assessment):
    """
    ✅ ქვეყნის მიხედვით ავტო-reject
    
    Args:
        cid: Candidate ID
        jid: Job Opening ID (can be None)
        assessment: Rejection reason
    """
    update_candidate_fields(cid, {
        'AI_Score': 0,
        'AI_Assessment': assessment
    })

    update_candidate_status(cid, jid, config.STATUS_REJECTED)
    return config.STATUS_REJECTED
