import os
from dotenv import load_dotenv

# --- Flask Imports ---
from flask import Flask, request, jsonify, Response
from flask_cors import CORS # Import the CORS library

# --- Supabase Imports ---
from supabase import create_client, Client

# --- Pydantic & LangChain Imports ---
from pydantic import BaseModel, Field
from typing import List
from langchain_mistralai import ChatMistralAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser

# Load environment variables from .env file
load_dotenv()

# --- Initialize Clients ---

# Flask App
app = Flask(__name__)

# This allows your frontend to call your backend
CORS(app)

# Supabase Client Initialization
try:
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")
    supabase: Client = create_client(supabase_url, supabase_key)
except Exception as e:
    supabase = None
    print(f"Warning: Could not initialize Supabase client. Error: {e}.")

# LangChain/Mistral Client
try:
    model = ChatMistralAI(
        # FIX: Use a more memory-efficient model for the free tier
        model="open-mixtral-8x7b",
        api_key=os.getenv("MISTRAL_API_KEY"),
        model_kwargs={"response_format": {"type": "json_object"}}
    )
except Exception as e:
    model = None
    print(f"Warning: Could not initialize ChatMistralAI. Error: {e}.")


# --- Pydantic Models for Startup Validator ---
class MonetizationStrategy(BaseModel):
    strategy: str = Field(description="The specific name of the strategy.")
    description: str = Field(description="Explain how this strategy applies.")
    viability: str = Field(description="A rating of this strategy's viability ('High', 'Medium', 'Low').")
class SimilarStartup(BaseModel):
    name: str = Field(description="Name of a direct or indirect competitor.")
    differentiation: str = Field(description="What they do and, critically, how this new idea MUST be different.")
class RiskFactor(BaseModel):
    level: str = Field(description="A risk rating: 'Low', 'Medium', 'High', or 'Very High'.")
    analysis: str = Field(description="A critical summary of the top 3 risks.")
    mitigation: str = Field(description="Suggest a concrete step to mitigate the primary risk.")
class StartupAnalysis(BaseModel):
    target_audience: str = Field(description="Describe the ideal customer persona (ICP).")
    monetization_plan: List[MonetizationStrategy]
    similar_startups: List[SimilarStartup]
    risk_factor: RiskFactor
    summary_and_verdict: str = Field(description="A concluding summary and final verdict.")

# --- LangChain Prompt Setup ---
system_prompt_text = (
    "You are a highly critical and pragmatic Venture Capital analyst at a top-tier firm. Your primary role is to identify flaws, risks, and weaknesses in startup ideas. Your analysis must be brutally honest, concise, and avoid any marketing fluff or overly optimistic language. Focus on business fundamentals: market viability, defensibility, and execution risk. You MUST respond ONLY with a valid JSON object that strictly adheres to the provided schema. Do not include any other text, explanations, or apologies before or after the JSON object."
)
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt_text + "\n{format_instructions}"),
    ("human", "Please provide a critical analysis of this startup idea: {idea}")
]).partial(format_instructions=PydanticOutputParser(pydantic_object=StartupAnalysis).get_format_instructions())


# --- Simple Auth Endpoints ---
@app.route("/signup", methods=['POST'])
def signup_user():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Email and password are required."}), 400
    if not supabase:
        return jsonify({"error": "Supabase client not initialized."}), 500

    try:
        res = supabase.auth.sign_up({"email": data.get('email'), "password": data.get('password')})
        if res.user:
            # FIX: Use .model_dump() instead of .dict() for Pydantic v2
            return jsonify({"message": "User signed up successfully.", "user": res.user.model_dump()}), 201
        elif res.error:
            return jsonify({"error": res.error.message}), 400
        return jsonify({"error": "An unknown error occurred during signup."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/login", methods=['POST'])
def login_user():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Email and password are required."}), 400
    if not supabase:
        return jsonify({"error": "Supabase client not initialized."}), 500
        
    try:
        res = supabase.auth.sign_in_with_password({"email": data.get('email'), "password": data.get('password')})
        if res.session:
            # FIX: Use .model_dump() instead of .dict() for Pydantic v2
            return jsonify(res.session.model_dump()), 200
        elif res.error:
            return jsonify({"error": res.error.message}), 400
        return jsonify({"error": "An unknown error occurred during login."}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- AI Endpoints ---
@app.route("/stream-validate-idea", methods=['POST'])
def stream_validate_idea():
    data = request.get_json()
    if not data or 'idea' not in data:
        return Response('{"error": "Request body must be JSON with an \'idea\' key."}', status=400, mimetype='application/json')
    if not model:
        return Response('{"error": "AI Model not initialized. Check API Key."}', status=500, mimetype='application/json')

    def generate_stream(idea_text):
        try:
            streaming_chain = prompt | model | StrOutputParser()
            for chunk in streaming_chain.stream({"idea": idea_text}):
                yield chunk
        except Exception as e:
            yield f'{{"error": "An error occurred during streaming: {str(e)}"}}'

    return Response(generate_stream(data['idea']), mimetype='text/event-stream')


@app.route("/")
def read_root():
    return jsonify({"status": "AI Startup Validator with Flask is running"})

# --- Flask Server Entry Point for Production ---
if __name__ == '__main__':
    # Render provides the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)