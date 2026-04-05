import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.credentials import ApiCreds

def derive_clob_credentials():
    load_dotenv()
    
    host = "https://clob.polymarket.com"
    key = os.getenv("POLY_PRIVATE_KEY")
    chain_id = 137 # Polygon Mainnet
    
    if not key:
        print("Missing POLY_PRIVATE_KEY in .env")
        return
        
    client = ClobClient(host, key=key, chain_id=chain_id)
    
    try:
        # Create API credentials directly against the CLOB
        creds = client.create_or_derive_api_creds()
        print("\n[SUCCESS] Derived L2 CLOB API Credentials!")
        print(f"API Key: {creds.api_key}")
        print(f"API Secret: {creds.api_secret}")
        print(f"Passphrase: {creds.api_passphrase}")
        
        # Save them back to .env
        env_path = "/home/leo_dwelon_com/.openclaw/workspace/poly-alpha/.env"
        with open(env_path, "a") as f:
            f.write(f"POLY_CLOB_API_KEY={creds.api_key}\n")
            f.write(f"POLY_CLOB_API_SECRET={creds.api_secret}\n")
            f.write(f"POLY_CLOB_API_PASSPHRASE={creds.api_passphrase}\n")
            
        print("\nStored L2 API keys in .env. Execution engine is now fully authenticated.")
    except Exception as e:
        print(f"Failed to derive credentials: {e}")

if __name__ == "__main__":
    derive_clob_credentials()
