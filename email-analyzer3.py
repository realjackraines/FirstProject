import os
import base64
import pandas as pd
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import anthropic

class GmailThreadAnalyzer:
    def __init__(self):
        # If modifying these SCOPES, delete the file token.json.
        self.SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        self.service = self._get_gmail_service()
        self.anthropic_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

    def _get_gmail_service(self):
        """Authenticate and create Gmail service."""
        creds = None
        # The file token.json stores the user's access and refresh tokens
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)
        
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', self.SCOPES)
            creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.json', 'w') as token:
                token.write(creds.to_json())

        return build('gmail', 'v1', credentials=creds)

    def _decode_message_body(self, msg):
        """Decode the body of a Gmail message."""
        # Handle different parts of the message
        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part['mimeType'] in ['text/plain', 'text/html']:
                    try:
                        return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    except:
                        continue
        elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
            try:
                return base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')
            except:
                return ""
        return ""

    def _generate_reply_summary(self, body):
        """Generate a summary of an individual email reply using Claude."""
        try:
            prompt = f"""Provide a concise summary of the following email reply. 
            Capture the key points, main ideas, and any important information or actions.

            Email Body:
            {body}
            """
            
            response = self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text
        except Exception as e:
            print(f"Error generating summary: {e}")
            return "Unable to generate summary"

    def get_thread_details(self, thread_id):
        """Retrieve full details of a Gmail thread."""
        try:
            # Fetch the entire thread
            thread = self.service.users().threads().get(userId='me', id=thread_id).execute()
            
            # Process messages in the thread
            thread_details = []
            for message in thread['messages']:
                # Extract key message details
                headers = {h['name']: h['value'] for h in message['payload']['headers']}
                
                # Decode message body
                body = self._decode_message_body(message)
                
                # Generate summary of the reply
                reply_summary = self._generate_reply_summary(body)
                
                thread_details.append({
                    'id': message['id'],
                    'sender': headers.get('From', 'Unknown'),
                    'subject': headers.get('Subject', 'No Subject'),
                    'date': headers.get('Date', 'Unknown Date'),
                    'body': body,
                    'reply_summary': reply_summary
                })
            
            return thread_details
        except Exception as e:
            print(f"Error retrieving thread: {e}")
            return []

    def get_thread_ids_for_message_ids(self, message_ids):
        """Find thread IDs for specific message IDs."""
        thread_ids = []
        for msg_id in message_ids:
            try:
                # Search for messages with the specific Message-ID
                query = f'rfc822msgid:{msg_id}'
                results = self.service.users().messages().list(
                    userId='me', 
                    q=query
                ).execute()
                
                # Extract thread IDs
                for message in results.get('messages', []):
                    if message['threadId'] not in thread_ids:
                        thread_ids.append(message['threadId'])
            
            except Exception as e:
                print(f"Error finding thread for message ID {msg_id}: {e}")
        
        return thread_ids

def analyze_email_threads(message_ids):
    """
    Analyze multiple email threads based on Message-IDs
    
    :param message_ids: List of Message-IDs to analyze
    :return: DataFrame of thread details and summary
    """
    # Initialize Gmail analyzer
    gmail_analyzer = GmailThreadAnalyzer()
    
    # Collect all thread details
    all_thread_details = []
    
    # Get thread IDs for the given message IDs
    thread_ids = gmail_analyzer.get_thread_ids_for_message_ids(message_ids)
    
    # Retrieve full thread details for each thread
    for thread_id in thread_ids:
        thread_details = gmail_analyzer.get_thread_details(thread_id)
        all_thread_details.extend(thread_details)
    
    # Create DataFrame
    df = pd.DataFrame(all_thread_details)
    
    # Save to Excel
    output_file = 'email_thread_analysis.xlsx'
    df.to_excel(output_file, index=False)
    print(f"Excel file saved: {output_file}")
    
    # Prepare comprehensive prompt for overall thread analysis
    thread_text = "\n\n--- Message Separator ---\n\n".join([
        f"From: {msg['sender']}\n"
        f"Date: {msg['date']}\n"
        f"Subject: {msg['subject']}\n"
        f"Body: {msg['body']}"
        for msg in all_thread_details
    ])
    
    # Use Claude to analyze the overall thread
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    prompt = f"""Please provide a comprehensive summary of the following email thread(s):

Analyze the entire conversation, including:
- Overall context and purpose of the communication
- Key discussion points
- Important decisions or action items
- Tone and sentiment of the conversation
- Any unresolved issues or follow-up needs

Full Thread Details:
{thread_text}
"""
    
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    
    # Print overall summary
    print("\nOverall Email Thread Summary:")
    print(response.content[0].text)
    
    return df

# Example usage
if __name__ == "__main__":
    # Specific Message-IDs to analyze
    message_ids_to_analyze = [
        'CA+mHjZ8er6XWSAUu28Ri9tLkW2sV+0-x2LnqM_vFKK9Xr4CMvg@mail.gmail.com',
        'CA+mHjZ_R0pGROezwiH8J2cC4+SeJXH=ZjnKDa4rVxpRPNQSThw@mail.gmail.com'
    ]
    
    # Analyze threads and save to Excel
    df = analyze_email_threads(message_ids_to_analyze)
