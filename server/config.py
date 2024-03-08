import os

from dotenv import load_dotenv

load_dotenv()

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION = os.getenv("AWS_REGION")
AWS_DATA_STREAM_NAME = os.getenv("AWS_DATA_STREAM_NAME")
OPENAI_CHATGPT_API_KEY = os.getenv("OPENAI_CHATGPT_API_KEY")
