from google import genai

# The client gets the API key from the environment variable `GEMINI_API_KEY`.
client = genai.Client("AIzaSyADZ_zGkBUss6QiaRT7Lko69Ej7faDDHlw")

response = client.models.generate_content(
    model="gemini-2.5-flash", contents="Explain how AI works in a few words"
)
print(response.text)