import os
import base64
import pickle
import anthropic
import pandas as pd
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

# 🔒 Securely fetch Anthropic API Key
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    raise ValueError("Missing Anthropic API Key. Set it as an environment variable.")

# ✅ Initialize Anthropic client
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def get_gmail_service():
    """Authenticate and return Gmail API service."""
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = None

    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('gmail', 'v1', credentials=creds)

def extract_email_body(msg):
    """Extract and decode email body (handling base64 encoding)."""
    body = None
    if 'parts' in msg['payload']:
        for part in msg['payload']['parts']:
            if part['mimeType'] == 'text/plain' and 'body' in part:
                data = part['body'].get('data', '')
                body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            elif part['mimeType'] == 'text/html' and not body:
                data = part['body'].get('data', '')
                body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    else:
        if 'body' in msg['payload'] and 'data' in msg['payload']['body']:
            data = msg['payload']['body']['data']
            body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
    
    return body.strip() if body else None

def analyze_feedback(email_body):
    """Analyze feedback using Anthropic API."""
    prompt = f"""
    Analyze this product feedback:
    {email_body}

    Identify:
    1. Main issues/bugs
    2. UX friction points
    3. Sentiment (positive/negative)
    """

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content if response else "No analysis available."

def main():
    service = get_gmail_service()
    feedback_data = []

    # 🔍 Replace these with the two Message IDs you found
    MESSAGE_ID_1 = "CA+mHjZ8er6XWSAUu28Ri9tLkW2sV+0-x2LnqM_vFKK9Xr4CMvg@mail.gmail.com"
    MESSAGE_ID_2 = "CA+mHjZ_R0pGROezwiH8J2cC4+SeJXH=ZjnKDa4rVxpRPNQSThw@mail.gmail.com"

    # Gmail search query to get only replies to these two emails
    query = f"in:sent rfc822msgid:{MESSAGE_ID_1} OR rfc822msgid:{MESSAGE_ID_2}"

    # Fetch only replies to these emails
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    for message in messages:
        msg = service.users().messages().get(userId='me', id=message['id'], format='full').execute()
        email_data = {'date': None, 'from': None, 'body': None, 'analysis': None}

        # Extract headers
        for header in msg['payload']['headers']:
            if header['name'] == 'Date':
                email_data['date'] = header['value']
            elif header['name'] == 'From':
                email_data['from'] = header['value']

        # Extract email body
        email_data['body'] = extract_email_body(msg)

        # Analyze feedback
        if email_data['body']:
            email_data['analysis'] = analyze_feedback(email_data['body'])

        feedback_data.append(email_data)

    # Export to Excel
    df = pd.DataFrame(feedback_data)
    df.to_excel('feedback_analysis.xlsx', index=False)
    print("Filtered feedback analysis saved to feedback_analysis.xlsx.")


if __name__ == '__main__':
    main()

