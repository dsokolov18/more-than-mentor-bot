import requests

headers = {
    "Authorization": "Bearer sk-вставь_сюда_свой_ключ",
    "Content-Type": "application/json"
}
data = {
    "model": "openai/gpt-4.1",
    "messages": [{"role": "user", "content": "Привет!"}]
}
response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
print(response.json())