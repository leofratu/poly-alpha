import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

host = "https://clob.polymarket.com"
key = "6778ad46d8f452de379fde84408143abdb2f3c4c80ebab0de320089b1fafb86c"
chain_id = 137 

creds = ApiCreds(
    api_key="10adfedd-e9f7-3e1c-47fd-ec4a0f4b5d5b",
    api_secret="ncH1ZL_dzcRwIKxvebXLqLsmgTKYqP85EDNHcTwS9VE=",
    api_passphrase="60cca0321f865a832d6055e0407a820e366f3fc513f9f290c49ae747ff25d055"
)

client = ClobClient(host, key=key, chain_id=chain_id, creds=creds)

try:
    print("Testing CLOB WebSocket and L2 API Authentication...")
    
    # Test Auth
    resp = client.get_api_keys()
    print(f"Authenticated L2 Status: Success. Active API Keys: {len(resp)}")
    print(f"Address: {client.get_address()}")
    
except Exception as e:
    print(f"Error: {e}")
