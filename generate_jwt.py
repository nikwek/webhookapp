from dotenv import load_dotenv
import os
from coinbase import jwt_generator

# Load environment variables from .env file
load_dotenv()

api_key = f"organizations/{os.getenv('ORG_ID')}/apiKeys/{os.getenv('KEY_ID')}"
api_secret = f"-----BEGIN EC PRIVATE KEY-----\n{os.getenv('PRIVATE_KEY')}\n-----END EC PRIVATE KEY-----\n"

request_method = "GET"
request_path = "/api/v3/brokerage/accounts"

def main():
    jwt_uri = jwt_generator.format_jwt_uri(request_method, request_path)
    jwt_token = jwt_generator.build_rest_jwt(jwt_uri, api_key, api_secret)
    print(jwt_token)

if __name__ == "__main__":
    main()
