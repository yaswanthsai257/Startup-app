import os
from dotenv import load_dotenv

# --- Flask Imports ---
from flask import Flask, request, jsonify, Response

# --- Supabase Imports ---
from supabase import create_client, Client

# --- Pydantic & LangChain Imports ---
from pydantic import BaseModel, Field
from typing import List
from langchain_mistralai import ChatMistralAI
from flask_cors import CORS # Import the CORS library
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser

# Load environment variables from .env file
load_dotenv()

# --- Initialize Clients ---

# Flask App
app = Flask(__name__)


CORS(app, resources={r"/*": {"origins": "*"}})

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
        model="mistral-large-latest",
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
    "You are a highly critical and pragmatic Venture Capital analyst..."
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
        res = supabase.auth.sign_up({
            "email": data.get('email'),
            "password": data.get('password'),
        })
        if res.user:
            return jsonify({"message": "User signed up successfully.", "user": res.user.dict()}), 201
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
        res = supabase.auth.sign_in_with_password({
            "email": data.get('email'),
            "password": data.get('password')
        })
        if res.session:
            return jsonify(res.session.dict()), 200
        elif res.error:
            return jsonify({"error": res.error.message}), 400
        return jsonify({"error": "An unknown error occurred during login."}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# --- AI Endpoints ---

@app.route("/validate-idea", methods=['POST'])
def validate_idea():
    data = request.get_json()
    if not data or 'idea' not in data:
        return jsonify({"error": "Request body must be JSON with an 'idea' key."}), 400
    if not model:
        return jsonify({"error": "AI Model not initialized. Check API Key."}), 500
    try:
        parser = PydanticOutputParser(pydantic_object=StartupAnalysis)
        chain = prompt | model | parser
        analysis = chain.invoke({"idea": data['idea']})
        return jsonify(analysis.model_dump())
    except Exception as e:
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

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

    return Response(generate_stream(data['idea']), mimetype='text/plain')


@app.route("/")
def read_root():
    return jsonify({"status": "AI Startup Validator with Flask is running"})

# --- Flask Server Entry Point ---
if __name__ == '__main__':
    app.run(debug=True)