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
    """კანდიდატის ასოცირებული Job Opening"""
    r = requests.get(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}/associate",
        headers=_h()
    )
    if r.status_code != 200:
        print(f"[Zoho] No associated job: {r.status_code}")
        return None
    
    data = r.json()
    if 'data' in data and len(data['data']) > 0:
        return data['data'][0]
    return None


def get_attachments(module, record_id):
    """ატაჩმენტების სია"""
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
    """ატაჩმენტის ჩამოტვირთვა - ორი მეთოდით ცდა"""
    
    # Method 1: Standard endpoint
    url1 = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}"
    print(f"[Zoho] Download attempt 1: {url1}")
    r = requests.get(url1, headers=_h())
    
    if r.status_code == 200 and len(r.content) > 0:
        print(f"[Zoho] Download success (method 1): {len(r.content)} bytes")
        return r.content
    
    # Method 2: $download endpoint
    url2 = f"{config.ZOHO_RECRUIT_BASE}/{module}/{record_id}/Attachments/{att_id}/$download"
    print(f"[Zoho] Download attempt 2: {url2}")
    r = requests.get(url2, headers=_h())
    
    if r.status_code == 200 and len(r.content) > 0:
        print(f"[Zoho] Download success (method 2): {len(r.content)} bytes")
        return r.content
    
    # Method 3: Direct file download
    url3 = f"https://recruit.zoho.com/recruit/v2/files/{att_id}"
    print(f"[Zoho] Download attempt 3: {url3}")
    r = requests.get(url3, headers=_h())
    
    if r.status_code == 200 and len(r.content) > 0:
        print(f"[Zoho] Download success (method 3): {len(r.content)} bytes")
        return r.content
    
    print(f"[Zoho] All download methods failed for attachment {att_id}")
    return None


def get_candidate_cv(cid):
    """CV ფაილის ჩამოტვირთვა"""
    attachments = get_attachments("Candidates", cid)
    for att in attachments:
        fname = att.get('File_Name', '').lower()
        if any(ext in fname for ext in ['.pdf', '.docx', '.doc']):
            content = download_attachment("Candidates", cid, att['id'])
            if content:
                return content, att['File_Name']
    return None, None


def get_job_documents(jid):
    """JD და ICP ატაჩმენტების ჩამოტვირთვა და დაპარსვა"""
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


def update_candidate(cid, score, assessment):
    """კანდიდატის განახლება — Score + Assessment"""
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
    """კანდიდატის რეჯექტი"""
    r = requests.put(
        f"{config.ZOHO_RECRUIT_BASE}/Candidates/{cid}",
        headers={**_h(), 'Content-Type': 'application/json'},
        json={'data': [{
            'Candidate_Status': 'Rejected'
        }]}
    )
    print(f"[Zoho] Rejected: {r.status_code}")
    return r.json()
