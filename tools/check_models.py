import os
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

models = ["gpt-3.5-turbo", "gpt-4o-mini", "gpt-5-nano"]
question = "what is 1 plus 1"

for model in models:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": question}],
    )
    answer = response.choices[0].message.content
    print(f"[{model}] {answer}\n")
