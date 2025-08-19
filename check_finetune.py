from openai import OpenAI
import os
from dotenv import load_dotenv

# Load environment variables from your .env file
load_dotenv()

# The OpenAI client will automatically pick up the OPENAI_API_KEY
# from your environment variables after load_dotenv() is called.
client = OpenAI()

try:
    fine_tuning_jobs = client.fine_tuning.jobs.list(limit=1)
    
    print("Successfully accessed fine-tuning jobs. Your OpenAI subscription likely supports fine-tuning.")
    # If you want to see actual jobs, you can iterate:
    # for job in fine_tuning_jobs.data:
    #     print(job)

except Exception as e:
    print(f"An error occurred while trying to access fine-tuning: {e}")
    print("This could mean your subscription does not support fine-tuning, or there's another API issue.")
