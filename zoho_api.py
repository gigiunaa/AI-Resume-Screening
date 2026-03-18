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


def get_attachments(module, record_id):
    r = requests.get(
        f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments",
        headers=_h()
    )
    if r.status_code == 204:
        return []
    r.raise_for_status()
    return r.json().get('data', [])


def download_attachment(module, record_id, att_id):
    """ატაჩმენტის ჩამოტვირთვა"""
    url = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}"
    print(f"[Zoho] Downloading attachment: {url}")
    
    r = requests.get(url, headers=_h())
    
    # თუ 400 error - სცადე $download endpoint
    if r.status_code == 400:
        url2 = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}/$download"
        print(f"[Zoho] Trying alternative URL: {url2}")
        r = requests.get(url2, headers=_h())
    
    if r.status_code != 200:
        print(f"[Zoho] Attachment download failed: {r.status_code} - {r.text}")
        return None
    
    return r.content


def get_candidate_cv(cid):
    attachments = get_attachments("Candidates", cid)
    for att in attachments:
        fname = att.get('File_Name', '').lower()
        if any(ext in fname for ext in ['.pdf', '.docx', '.doc']):
            content = download_attachment("Candidates", cid, att['id'])
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
        text = extract_text(content, att['File_Name'])

        if not text:
            continue

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


def update_candidate(cid, score, assessment):
    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers={**_h(), 'Content-Type': 'application/json'},
        json={'data': [{
            'AI_Score': int(score),
            'AI_Assessment': assessment
        }]}
    )
    print(f"[Zoho] Update score: {r.status_code}")

    if score < config.REJECT_THRESHOLD:
        reject_candidate(cid)

    return r.json()


def reject_candidate(cid):
    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers={**_h(), 'Content-Type': 'application/json'},
        json={'data': [{
            'Candidate_Status': 'Rejected'
        }]}
    )
    print(f"[Zoho] Rejected: {r.status_code}")
    return r.json()
