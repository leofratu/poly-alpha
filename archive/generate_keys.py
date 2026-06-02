import json
import os
from eth_account import Account
from dotenv import set_key

def generate_poly_wallet():
    # Enable un-audited HD Wallet features
    Account.enable_unaudited_hdwallet_features()
    
    # Generate a fresh Ethereum/Polygon private key
    acct = Account.create('poly-alpha-engine-entropy')
    
    env_path = "/home/leo_dwelon_com/.openclaw/workspace/poly-alpha/.env"
    
    # Save the keys to .env
    with open(env_path, "a") as f:
        f.write(f"\nPOLY_PRIVATE_KEY={acct.key.hex()}\n")
        f.write(f"POLY_ADDRESS={acct.address}\n")
        f.write("POLY_CLOB_API_KEY=\n")
        f.write("POLY_CLOB_API_SECRET=\n")
        f.write("POLY_CLOB_API_PASSPHRASE=\n")
        
    print("\n[SUCCESS] Generated Fresh EOA Wallet for Poly-Alpha Execution:")
    print(f"Address: {acct.address}")
    print(f"Private Key: {acct.key.hex()}")
    print("\nKeys saved to .env file.")
    print("Next step: Derive the CLOB API Credentials using the py_clob_client.")

if __name__ == "__main__":
    generate_poly_wallet()
