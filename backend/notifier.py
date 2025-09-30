import os
import json
from pywebpush import webpush, WebPushException
from typing import Tuple

# Import security manager and initialize it
from .security_manager import security_manager

# Define project directories
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')

# Initialize security manager if not already initialized
if not security_manager.vapid_private_key:
    security_manager.data_dir = DATA_DIR
    security_manager.initialize()

async def send_push_notification_to_all(title: str, body: str, notification_type: str = "data-updated") -> Tuple[int, int]:
    """
    Sends a push notification to all subscribed users.

    Returns a tuple of (sent_count, failed_count).
    """
    subscriptions_file = os.path.join(DATA_DIR, 'push_subscriptions.json')
    if not os.path.exists(subscriptions_file):
        print("No push subscriptions file found.")
        return 0, 0

    with open(subscriptions_file, 'r', encoding='utf-8') as f:
        saved_subscriptions = json.load(f)

    if not saved_subscriptions:
        print("No subscriptions to send to.")
        return 0, 0

    notification_data = json.dumps({
        "title": title,
        "body": body,
        "type": notification_type
    })

    sent_count = 0
    failed_count = 0

    # In a real async implementation, you would use asyncio.gather here.
    # For simplicity in this context, we'll iterate.
    for sub_id, subscription_info in list(saved_subscriptions.items()):
        try:
            webpush(
                subscription_info=subscription_info,
                data=notification_data,
                vapid_private_key=security_manager.vapid_private_key,
                vapid_claims={"sub": security_manager.vapid_subject}
            )
            sent_count += 1
        except WebPushException as ex:
            print(f"Push failed for {sub_id}: {ex}")
            # If subscription is expired or invalid, it should be removed.
            # This logic can be enhanced to handle such cases.
            if ex.response and ex.response.status_code in [404, 410]:
                print(f"Subscription {sub_id} is invalid and should be removed.")
            failed_count += 1

    print(f"Push notifications sent: {sent_count}, failed: {failed_count}")
    return sent_count, failed_count