from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
from typing import List, Union
from groq import Groq
from typing import Optional
from starlette.responses import StreamingResponse
from starlette.responses import PlainTextResponse
from fastapi.responses import HTMLResponse, Response
import httpx


# Import settings before use
from app.config import settings

router = APIRouter()
client = Groq(api_key=settings.GROQ_API_KEY)

# Proxy image endpoint (must be after router is defined)
@router.get("/proxy-image")
async def proxy_image(url: str, request: Request):
    """
    Proxy an image from any URL to bypass CORS/hotlinking issues for widget icons.
    Usage: /api/proxy-image?url=https://example.com/image.png
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                return Response(status_code=404, content="Not an image.")
            # Pass through content type and cache headers
            headers = {"content-type": r.headers["content-type"]}
            if "cache-control" in r.headers:
                headers["cache-control"] = r.headers["cache-control"]
            return Response(content=r.content, headers=headers)
    except Exception as e:
        return Response(status_code=502, content=f"Proxy error: {e}")


# Move settings import to the top so it's available for client = Groq(api_key=settings.GROQ_API_KEY)
from app.config import settings
from app.rag import search_top_chunks
from app.db import get_conn, normalize_org_id
from collections import defaultdict, deque
import time
import base64, json, hmac, hashlib, uuid, datetime


class ChatBody(BaseModel):
    message: str
    org_id: str
    session_id: Optional[str] = None

class KeyBody(BaseModel):
    org_id: str

class BotConfigBody(BaseModel):
    org_id: str
    behavior: str
    system_prompt: Optional[str] = None
    website_url: Optional[str] = None
    role: Optional[str] = None
    tone: Optional[str] = None
    welcome_message: Optional[str] = None
    services: Optional[List[str]] = None
    form_config: Optional[dict] = None

class CalendarConfigBody(BaseModel):
    org_id: str
    provider: str = "google"
    calendar_id: str
    timezone: Optional[str] = None

class CreateEventBody(BaseModel):
    org_id: str
    summary: str
    start_iso: str
    end_iso: str
    attendees: Optional[List[str]] = None

class CreateBotBody(BaseModel):
    org_id: str
    behavior: str
    system_prompt: Optional[str] = None
    name: Optional[str] = None
    website_url: Optional[str] = None
    role: Optional[str] = None
    tone: Optional[str] = None
    welcome_message: Optional[str] = None
    services: Optional[List[str]] = None

class LeadBody(BaseModel):
    org_id: str
    bot_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    interest_details: Optional[str] = None
    comments: Optional[str] = None
    conversation_summary: Optional[str] = None
    interest_score: int = 0
    session_id: Optional[str] = None

router = APIRouter()
client = Groq(api_key=settings.GROQ_API_KEY)

# Cache for LLM intent detection results (to reduce API calls)
_INTENT_CACHE = {}
_CACHE_MAX_SIZE = 500

def _ensure_form_config_column(conn):
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from information_schema.columns where table_name=%s and column_name=%s",
            ("chatbots", "form_config"),
        )
        if cur.fetchone()[0] == 0:
            try:
                cur.execute("alter table chatbots add column form_config jsonb")
            except Exception:
                pass

def _llm_intent_detection(message: str, history: list = None) -> dict:
    """
    LLM-based intent detection for ambiguous cases.
    Uses Groq's fast LLM to understand implicit booking intent.
    
    Returns: {
        'is_booking': bool,
        'action': 'book'|'reschedule'|'cancel'|'status'|None,
        'confidence': float (0.0-1.0),
        'reasoning': str
    }
    """
    # Check cache first (normalize message for caching)
    cache_key = message.lower().strip()[:100]  # First 100 chars
    if cache_key in _INTENT_CACHE:
        return _INTENT_CACHE[cache_key]
    
    # Build context from history
    context = ""
    if history:
        recent = history[-3:] if len(history) > 3 else history
        context = "\n".join([f"{'User' if h.get('role') == 'user' else 'Bot'}: {h.get('content', '')}" for h in recent])
    
    # LLM prompt for intent detection
    prompt = f"""You are analyzing if a user message is SPECIFICALLY requesting to book, reschedule, cancel, or check an appointment. 

IMPORTANT: Only return is_booking=true if the user is EXPLICITLY trying to (even with typos):
1. Book/schedule a new appointment
2. Reschedule an existing appointment  
3. Cancel an appointment
4. Check appointment status

General questions about the bot's identity (who are you, who made you) or generic greetings (hello, hi) are NOT booking intents.
However, "How can I book?" or "I want to schedule" ARE booking intents.

Previous conversation:
{context if context else "(No previous messages)"}

Current message: "{message}"

Respond ONLY with a JSON object (no markdown, no explanation):
{{
  "is_booking": true/false,
  "action": "book"|"reschedule"|"cancel"|"status"|null,
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}}

BOOKING Examples (is_booking=true):
- "I need to book an appointment" → {{"is_booking": true, "action": "book", "confidence": 0.95}}
- "Can I schedule for tomorrow 3pm?" → {{"is_booking": true, "action": "book", "confidence": 0.9}}
- "reschedule my appointment" → {{"is_booking": true, "action": "reschedule", "confidence": 0.95}}
- "cancel my booking" → {{"is_booking": true, "action": "cancel", "confidence": 0.95}}
- "how can i dook the appomnyinment" (typos) → {{"is_booking": true, "action": "book", "confidence": 0.85}}
- "chek my staus" (typos) → {{"is_booking": true, "action": "status", "confidence": 0.85}}
- "how to book?" → {{"is_booking": true, "action": "book", "confidence": 0.9}}

NON-BOOKING Examples (is_booking=false):
- "hello" → {{"is_booking": false, "action": null, "confidence": 0.95}}
- "hi" → {{"is_booking": false, "action": null, "confidence": 0.95}}
- "what is your name" → {{"is_booking": false, "action": null, "confidence": 0.95}}
- "what can you do" → {{"is_booking": false, "action": null, "confidence": 0.95}}
- "who is your owner" → {{"is_booking": false, "action": null, "confidence": 0.95}}
- "what are your services" → {{"is_booking": false, "action": null, "confidence": 0.95}}
- "tell me about your company" → {{"is_booking": false, "action": null, "confidence": 0.95}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Fast and cheap
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # Low temperature for consistent results
            max_tokens=150
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        # Remove markdown code blocks if present
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        result = json.loads(result_text)
        
        # Cache the result
        if len(_INTENT_CACHE) >= _CACHE_MAX_SIZE:
            # Remove oldest entry
            _INTENT_CACHE.pop(next(iter(_INTENT_CACHE)))
        _INTENT_CACHE[cache_key] = result
        
        return result
    except Exception as e:
        # Fallback on error
        return {
            'is_booking': False,
            'action': None,
            'confidence': 0.0,
            'reasoning': f'LLM error: {str(e)}'
        }


def _detect_booking_intent(message: str, history: list = None) -> dict:
    """
    Smart multi-language booking intent detection.
    Supports: English, Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Urdu
    
    Returns: {
        'is_booking': bool,
        'action': 'book'|'reschedule'|'cancel'|'status'|None,
        'has_time': bool,
        'has_appointment_id': bool
    }
    """
    import re
    msg_lower = message.lower()
    
    # Explicit non-booking keywords - these should NEVER be booking intents (Multi-language)
    non_booking_keywords = [
        # Greetings (English + Indian languages)
        r'\b(hello|hi|hey|greetings|good morning|good afternoon|good evening)\b',
        r'\b(नमस्ते|हैलो|हाय|शुभ प्रभात|नमस्कार)\b',  # Hindi
        r'\b(வணக்கம்|ஹலோ|ஹாய்)\b',  # Tamil
        r'\b(నమస్కారం|హలో|హాయ్)\b',  # Telugu
        r'\b(ನಮಸ್ಕಾರ|ಹಲೋ|ಹಾಯ್)\b',  # Kannada
        r'\b(നമസ്കാരം|ഹലോ|ഹായ്)\b',  # Malayalam
        
        # Question words (English)
        r'\b(what is|what are|who is|who are|where is|where are|when is|how is|why is)\b',
        r'\b(tell me|show me|explain|describe|info|information)\b',
        
        # Question words (Hindi)
        r'\b(क्या है|कौन है|कहाँ है|कब है|कैसे|क्यों|बताओ|बताइए)\b',
        
        # Question words (Tamil)
        r'\b(என்ன|யார்|எங்கே|எப்போது|எப்படி|ஏன்|சொல்லுங்கள்)\b',
        
        # Question words (Telugu)
        r'\b(ఏమిటి|ఎవరు|ఎక్కడ|ఎప్పుడు|ఎలా|ఎందుకు|చెప్పండి)\b',
        
        # Question words (Kannada)
        r'\b(ಏನು|ಯಾರು|ಎಲ್ಲಿ|ಯಾವಾಗ|ಹೇಗೆ|ಯಾಕೆ|ಹೇಳಿ)\b',
        
        # Question words (Malayalam)
        r'\b(എന്താണ്|ആരാണ്|എവിടെ|എപ്പോൾ|എങ്ങനെ|എന്തുകൊണ്ട്|പറയൂ)\b',
        
        # Common non-booking topics (English + transliterations)
        r'\b(your name|your owner|you do|you can|about you|who you|what you)\b',
        r'\b(help|support|contact|email|phone|address|location)\b',
        r'\b(naam|name|owner|company|business|service|services)\b',
        
        # Common non-booking topics (Hindi)
        r'\b(नाम|मालिक|कंपनी|सेवा|सेवाएं|मदद|संपर्क)\b',
    ]
    
    # Check if it's explicitly a non-booking question
    is_non_booking = any(re.search(pattern, msg_lower, re.IGNORECASE) for pattern in non_booking_keywords)
    
    # If it's clearly NOT a booking question, return immediately
    if is_non_booking and len(message.split()) <= 10:  # Short questions
        return {
            'is_booking': False,
            'action': None,
            'has_time': False,
            'has_appointment_id': False,
            'confidence': 0.95,
            'detection_method': 'regex-negative'
        }
    
    # Booking keywords (English + Indian languages)
    booking_keywords = [
        # English
        r'\b(book|schedule|appointment|reserve|slot|meeting)\b',
        # Common typos (English)
        r'\b(dook|bok|boo|shcedule|scheduel|appoinment|appointmen|appoiment|appomnyinment|apointment|apoyntment|apptimnet|appintment)\b',
        # Hindi (Devanagari + transliteration)
        r'\b(बुक|अपॉइंटमेंट|समय|मिलना|बुकिंग|book|appointment|samay)\b',
        # Tamil
        r'\b(பதிவு|நேரம்|சந்திப்பு|புக்|appointment)\b',
        # Telugu
        r'\b(బుకింగ్|అపాయింట్మెంట్|సమయం|రిజర్వేషన్)\b',
        # Kannada
        r'\b(ಬುಕಿಂಗ್|ಅಪಾಯಿಂಟ್ಮೆಂಟ್|ಸಮಯ|ಕಾಲಾವಕಾಶ)\b',
        # Malayalam
        r'\b(ബുക്കിംഗ്|അപ്പോയിന്റ്മെന്റ്|സമയം)\b',
        # Bengali
        r'\b(বুকিং|অ্যাপয়েন্টমেন্ট|সময়|দেখা)\b',
        # Marathi
        r'\b(बुकिंग|भेट|वेळ|नियुक्ती)\b',
        # Gujarati
        r'\b(બુકિંગ|મુલાકાત|સમય|અપોઇન્ટમેન્ટ)\b',
        # Punjabi
        r'\b(ਬੁਕਿੰਗ|ਮੁਲਾਕਾਤ|ਸਮਾਂ|ਅਪਾਇੰਟਮੈਂਟ)\b',
        # Urdu
        r'\b(بکنگ|ملاقات|وقت|اپائنٹمنٹ)\b',
        # Common transliterations
        r'\b(apointment|apoyntment|milna|dekhna|samay|waqt)\b'
    ]
    
    # Cancellation keywords
    cancel_keywords = [
        r'\b(cancel|cancellation|delete|remove)\b',
        r'\b(रद्द|कैंसल|cancel|hatana)\b',
        r'\b(ரத்து|நீக்கு)\b',
        r'\b(రద్దు|తొలగించు)\b',
        r'\b(ರದ್ದು|ತೆಗೆದುಹಾಕು)\b',
        r'\b(റദ്ദാക്കുക|നീക്കം)\b',
        r'\b(বাতিল|সরান)\b',
        r'\b(रद्द|काढून)\b',
        r'\b(રદ|દૂર)\b',
        r'\b(ਰੱਦ|ਹਟਾਓ)\b',
        r'\b(منسوخ|ہٹانا)\b'
    ]
    
    # Reschedule keywords
    reschedule_keywords = [
        r'\b(reschedule|re[-\s]?schedule|reshedule|reschudule|rescedule|reschdule|reshedul|rechedule|rescheduel|reschedual|reschedul|rescheduling|change|modify|shift|move)\b',
        r'\b(बदल|परिवर्तन|पुनर्निर्धारण|change)\b',
        r'\b(மாற்று|மாற்றம்)\b',
        r'\b(మార్చు|మార్పు)\b',
        r'\b(ಬದಲಾಯಿಸಿ|ಬದಲಾವಣೆ)\b',
        r'\b(മാറ്റുക|മാറ്റം)\b',
        r'\b(পরিবর্তন|বদল)\b',
        r'\b(बदल|फेरबदल)\b',
        r'\b(બદલો|ફેરફાર)\b',
        r'\b(ਬਦਲੋ|ਤਬਦੀਲੀ)\b',
        r'\b(تبدیل|بدلنا)\b'
    ]
    
    # Status/check keywords
    status_keywords = [
        r'\b(status|check|view|show|my\s+appointment)\b',
        # Common typos (English)
        r'\b(staus|satus|statuse|stauts|chekc|chek|chk|veiw|viwe)\b',
        r'\b(स्थिति|देखो|मेरा|check|status)\b',
        r'\b(நிலை|பார்|என்)\b',
        r'\b(స్థితి|చూడు|నా)\b',
        r'\b(ಸ್ಥಿತಿ|ನೋಡಿ|ನನ್ನ)\b',
        r'\b(സ്ഥിതി|കാണുക|എന്റെ)\b',
        r'\b(অবস্থা|দেখুন|আমার)\b',
        r'\b(स्थिती|पहा|माझा)\b',
        r'\b(સ્થિતિ|જુઓ|મારું)\b',
        r'\b(ਸਥਿਤੀ|ਵੇਖੋ|ਮੇਰੀ)\b',
        r'\b(حالت|دیکھیں|میرا)\b'
    ]
    
    # Time indicators
    time_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # ISO date
        r'\d{1,2}:\d{2}',  # Time
        r'\d{1,2}\s*(am|pm|AM|PM)',  # 12hr format
        r'\b(today|tomorrow|tomorow|tommorow|tmrw|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
        r'\b(आज|कल|सोमवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार)\b',
        r'\b(இன்று|நாளை|திங்கள்|செவ்வாய்|புதன்|வியாழன்|வெள்ளி|சனி|ஞாயிறு)\b',
        r'\b(ఈరోజు|రేపు|సోమవారం|మంగళవారం|బుధవారం|గురువారం|శుక్రవారం|శనివారం|ఆదివారం)\b',
        r'\b(ಇಂದು|ನಾಳೆ|ಸೋಮವಾರ|ಮಂಗಳವಾರ|ಬುಧವಾರ|ಗುರುವಾರ|ಶುಕ್ರವಾರ|ಶನಿವಾರ|ಭಾನುವಾರ)\b',
        r'\b(ഇന്ന്|നാളെ|തിങ്കൾ|ചൊവ്വ|ബുധൻ|വ്യാഴം|വെള്ളി|ശനി|ഞായർ)\b',
        r'\b(আজ|কাল|সোমবার|মঙ্গলবার|বুধবার|বৃহস্পতিবার|শুক্রবার|শনিবার|রবিবার)\b',
        r'\b(आज|उद्या|सोमवार|मंगळवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार)\b',
        r'\b(આજે|કાલે|સોમવાર|મંગળવાર|બુધવાર|ગુરુવાર|શુક્રવાર|શનિવાર|રવિવાર)\b',
        r'\b(ਅੱਜ|ਕੱਲ੍ਹ|ਸੋਮਵਾਰ|ਮੰਗਲਵਾਰ|ਬੁੱਧਵਾਰ|ਵੀਰਵਾਰ|ਸ਼ੁੱਕਰਵਾਰ|ਸ਼ਨੀਚਰਵਾਰ|ਐਤਵਾਰ)\b',
        r'\b(آج|کل|پیر|منگل|بدھ|جمعرات|جمعہ|ہفتہ|اتوار)\b',
        r'\b(kal|aaj|subah|sham|dopahar|shaam)\b'  # Common transliterations
    ]
    
    # Appointment ID patterns
    id_pattern = r'\b(appointment|booking|id|number)?\s*[:#]?\s*\d+\b'
    
    # Check for booking intent
    is_booking = any(re.search(pattern, msg_lower, re.IGNORECASE | re.UNICODE) for pattern in booking_keywords)
    
    # Determine action
    action = None
    has_cancel = any(re.search(pattern, msg_lower, re.IGNORECASE | re.UNICODE) for pattern in cancel_keywords)
    has_reschedule = any(re.search(pattern, msg_lower, re.IGNORECASE | re.UNICODE) for pattern in reschedule_keywords)
    has_status = any(re.search(pattern, msg_lower, re.IGNORECASE | re.UNICODE) for pattern in status_keywords)
    
    if has_cancel:
        action = 'cancel'
    elif has_reschedule:
        action = 'reschedule'
    elif has_status:
        action = 'status'
    elif is_booking:
        action = 'book'
    # Fallback: if an appointment ID is present and a "to ..." phrase exists, treat as reschedule
    elif bool(re.search(id_pattern, msg_lower, re.IGNORECASE)) and (" to " in msg_lower):
        action = 'reschedule'
    
    # Check for time and ID
    has_time = any(re.search(pattern, msg_lower, re.IGNORECASE | re.UNICODE) for pattern in time_patterns)
    has_appointment_id = bool(re.search(id_pattern, msg_lower, re.IGNORECASE))
    
    # Calculate regex-based confidence score
    confidence = 0.0
    if has_appointment_id:
        confidence = 0.95  # Very high confidence if ID is present
    elif is_booking and has_time:
        confidence = 0.85  # High confidence with explicit keywords + time
    elif is_booking:
        confidence = 0.65  # Medium confidence with just keywords
    elif has_time and len(message.split()) <= 5:
        confidence = 0.40  # Low-medium confidence for short messages with time
    else:
        confidence = 0.20  # Low confidence
    
    # Boost confidence for clear action words
    if has_cancel or has_reschedule or has_status:
        confidence = min(0.95, confidence + 0.15)
    
    # Context-aware boost from history
    if history:
        recent_messages = [h.get('content', '').lower() for h in history[-3:]]
        booking_context = any(
            any(kw in msg for kw in ['appointment', 'booking', 'schedule', 'अपॉइंटमेंट', 'बुकिंग'])
            for msg in recent_messages
        )
        if booking_context:
            confidence = min(0.95, confidence + 0.15)
    
    return {
        'is_booking': is_booking,  # Only True if explicit booking keywords found
        'action': action,
        'has_time': has_time,
        'has_appointment_id': has_appointment_id,
        'confidence': confidence,
        'detection_method': 'regex'
    }


def _detect_sales_intent(message: str) -> dict:
    """
    Detect sales/lead intent from message.
    Returns: {'is_sales': bool, 'confidence': float}
    """
    import re
    msg = message.lower().strip()
    
    # Strong intent keywords (0.9 confidence)
    strong_keywords = [
        r'\b(demo|demonstration|quote|price|pricing|cost|buy|purchase|interested|enquiry|inquiry)\b',
        r'\b(talk to sales|speak to sales|contact sales|talk to an expert)\b',
        r'\b(book a demo|schedule a demo|request a demo)\b',
        r'\b(how much|what is the price|pricing details)\b'
    ]
    
    # Moderate intent keywords (0.6 confidence)
    moderate_keywords = [
        r'\b(details|more info|information|help me)\b',
        r'\b(contact|connect|support)\b'
    ]
    
    for pat in strong_keywords:
        if re.search(pat, msg):
            return {'is_sales': True, 'confidence': 0.9}
            
    for pat in moderate_keywords:
        if re.search(pat, msg):
            return {'is_sales': True, 'confidence': 0.6}
            
    return {'is_sales': False, 'confidence': 0.0}

def _hybrid_intent_detection(message: str, history: list = None) -> dict:
    """
    Hybrid intent detection combining regex and LLM.
    
    Strategy:
    1. Fast path: Regex detection (instant, free)
    2. High confidence (>0.75): Return immediately
    3. Ambiguous (0.30-0.75): Use LLM to validate
    4. Low confidence (<0.30): LLM decides
    
    Returns: {
        'is_booking': bool,
        'action': 'book'|'reschedule'|'cancel'|'status'|None,
        'confidence': float,
        'has_time': bool,
        'has_appointment_id': bool,
        'detection_method': 'regex'|'llm'|'hybrid',
        'language': str (detected language code)
    }
    """
    # Step 1: Fast regex detection
    regex_result = _detect_booking_intent(message, history)
    regex_confidence = regex_result.get('confidence', 0.0)
    
    # Detect language from message
    detected_lang = 'en'
    if any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in message):
        detected_lang = 'hi'  # Hindi (Devanagari)
    elif any(ord(c) >= 0x0B80 and ord(c) <= 0x0BFF for c in message):
        detected_lang = 'ta'  # Tamil
    elif any(ord(c) >= 0x0C00 and ord(c) <= 0x0C7F for c in message):
        detected_lang = 'te'  # Telugu
    elif any(ord(c) >= 0x0C80 and ord(c) <= 0x0CFF for c in message):
        detected_lang = 'kn'  # Kannada
    elif any(ord(c) >= 0x0D00 and ord(c) <= 0x0D7F for c in message):
        detected_lang = 'ml'  # Malayalam
    elif any(ord(c) >= 0x0980 and ord(c) <= 0x09FF for c in message):
        detected_lang = 'bn'  # Bengali
    elif any(ord(c) >= 0x0A80 and ord(c) <= 0x0AFF for c in message):
        detected_lang = 'gu'  # Gujarati
    elif any(ord(c) >= 0x0A00 and ord(c) <= 0x0A7F for c in message):
        detected_lang = 'pa'  # Punjabi
    
    # Step 2: High confidence? Return immediately
    if regex_confidence >= 0.75:
        return {
            **regex_result,
            'language': detected_lang,
            'detection_method': 'regex'
        }
    
    # Step 4: Ambiguous case - use LLM to validate
    llm_result = _llm_intent_detection(message, history)
    llm_confidence = llm_result.get('confidence', 0.0)
    
    # Step 5: Combine results with weighted average
    # If both agree, boost confidence
    # If they disagree, trust higher confidence source
    
    if regex_result.get('is_booking', False) == llm_result.get('is_booking', False):
        # Agreement: boost confidence
        final_confidence = (regex_confidence * 0.35) + (llm_confidence * 0.65)
        final_confidence = min(0.98, final_confidence + 0.10)  # Bonus for agreement
        final_action = llm_result.get('action') or regex_result.get('action')
        final_is_booking = regex_result.get('is_booking', False)
        method = 'hybrid-agreement'
    else:
        # Disagreement: trust higher confidence
        if llm_confidence > regex_confidence:
            final_confidence = llm_confidence * 0.90  # Slight penalty for disagreement
            final_action = llm_result.get('action')
            final_is_booking = llm_result.get('is_booking', False)
            method = 'hybrid-llm'
        else:
            final_confidence = regex_confidence * 0.90
            final_action = regex_result.get('action')
            final_is_booking = regex_result.get('is_booking', False)
            method = 'hybrid-regex'
    
    return {
        'is_booking': final_is_booking,
        'action': final_action,
        'confidence': final_confidence,
        'has_time': regex_result.get('has_time', False),
        'has_appointment_id': regex_result.get('has_appointment_id', False),
        'language': detected_lang,
        'detection_method': method,
        'llm_reasoning': llm_result.get('reasoning', '')
    }


def get_bot_meta(conn, bot_id: str, org_id: str):
    with conn.cursor() as cur:
        cur.execute(
            "select behavior, system_prompt, public_api_key from chatbots where id=%s",
            (bot_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Bot not found")
        if len(row) >= 3:
            return row[0], row[1], row[2]
        return row[0], row[1], None


_RATE_BUCKETS = defaultdict(deque)
_SESSION_STATE = defaultdict(dict)


def _get_conversation_history(conn, session_id: str, org_id: str, bot_id: str, max_messages: int = 10):
    """Retrieve conversation history for a session (last 24 hours)"""
    if not session_id:
        return []
    
    with conn.cursor() as cur:
        cur.execute(
            """
            select role, content from conversation_history 
            where session_id=%s and org_id=%s and bot_id=%s 
            and created_at > now() - interval '24 hours'
            order by created_at desc
            limit %s
            """,
            (session_id, normalize_org_id(org_id), bot_id, max_messages)
        )
        rows = cur.fetchall()
    
    # Reverse to get chronological order
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]


def _save_conversation_message(conn, session_id: str, org_id: str, bot_id: str, role: str, content: str):
    """Save a message to conversation history"""
    if not session_id:
        return
    
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into conversation_history (session_id, org_id, bot_id, role, content)
            values (%s, %s, %s, %s, %s)
            """,
            (session_id, normalize_org_id(org_id), bot_id, role, content)
        )


def _cleanup_old_conversations(conn):
    """Delete conversations older than 24 hours"""
    try:
        with conn.cursor() as cur:
            cur.execute(
                "delete from conversation_history where created_at < now() - interval '24 hours'"
            )
    except Exception:
        pass


def _rate_limit(bot_id: str, org_id: str, limit: int = 30, window_seconds: int = 60):
    key = f"{org_id}:{bot_id}"
    now = time.time()
    dq = _RATE_BUCKETS[key]
    while dq and now - dq[0] > window_seconds:
        dq.popleft()
    if len(dq) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    dq.append(now)

def _ensure_usage_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_usage_daily (
              org_id text not null,
              bot_id text not null,
              day date not null,
              chats int not null default 0,
              successes int not null default 0,
              fallbacks int not null default 0,
              sum_similarity double precision not null default 0,
              created_at timestamptz default now(),
              updated_at timestamptz default now(),
              primary key (org_id, bot_id, day)
            )
            """
        )
        def ensure_col(name: str, ddl: str):
            cur.execute(
                "select count(*) from information_schema.columns where table_name=%s and column_name=%s",
                ("bot_usage_daily", name),
            )
            if int(cur.fetchone()[0]) == 0:
                try:
                    cur.execute(f"alter table bot_usage_daily add column {ddl}")
                except Exception:
                    pass
        ensure_col("successes", "successes int not null default 0")
        ensure_col("fallbacks", "fallbacks int not null default 0")
        ensure_col("sum_similarity", "sum_similarity double precision not null default 0")

def _log_chat_usage(conn, org_id: str, bot_id: str, similarity: float, fallback: bool):
    from app.db import normalize_org_id, normalize_bot_id
    org_n = normalize_org_id(org_id)
    bot_n = normalize_bot_id(bot_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into bot_usage_daily (org_id, bot_id, day, chats, successes, fallbacks, sum_similarity)
            values (%s,%s,current_date,1,%s,%s,%s)
            on conflict (org_id, bot_id, day)
            do update set chats = bot_usage_daily.chats + 1,
                          successes = bot_usage_daily.successes + %s,
                          fallbacks = bot_usage_daily.fallbacks + %s,
                          sum_similarity = bot_usage_daily.sum_similarity + %s,
                          updated_at = now()
            """,
            (org_n, bot_n, 0 if fallback else 1, 1 if fallback else 0, float(similarity), 0 if fallback else 1, 1 if fallback else 0, float(similarity)),
        )


@router.post("/leads/submit")
def submit_lead(body: LeadBody, x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        behavior, _, public_api_key = get_bot_meta(conn, body.bot_id, body.org_id)
        if public_api_key:
             if not x_bot_key or x_bot_key != public_api_key:
                pass 
        
        # Auto-generate summary from conversation history if not provided
        summary = body.conversation_summary
        if not summary and body.session_id:
            try:
                hist = _get_conversation_history(conn, body.session_id, body.org_id, body.bot_id, max_messages=20)
                if hist:
                    lines = []
                    for msg in hist:
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        lines.append(f"{role}: {content}")
                    summary = "\n".join(lines)
            except Exception as e:
                print(f"Error fetching history for summary: {e}")

        with conn.cursor() as cur:
            cur.execute(
                """
                insert into leads (org_id, bot_id, name, email, phone, interest_details, comments, conversation_summary, interest_score, status, session_id)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (normalize_org_id(body.org_id), body.bot_id, body.name, body.email, body.phone, body.interest_details, body.comments, summary, body.interest_score, "new", body.session_id)
            )
            lid = cur.fetchone()[0]
        return {"id": lid, "status": "success"}
    finally:
        conn.close()

@router.get("/leads/{bot_id}")
def get_leads(bot_id: str, org_id: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select id, name, email, phone, interest_details, status, created_at, interest_score, conversation_summary, comments from leads where bot_id=%s and org_id=%s order by created_at desc",
                (bot_id, normalize_org_id(org_id))
            )
            rows = cur.fetchall()
        return [{"id": r[0], "name": r[1], "email": r[2], "phone": r[3], "details": r[4], "status": r[5], "created_at": r[6], "score": r[7], "summary": r[8], "comments": r[9]} for r in rows]
    finally:
        conn.close()

class UpdateLeadBody(BaseModel):
    status: str
    org_id: str

@router.patch("/leads/{lead_id}/status")
def update_lead_status(lead_id: int, body: UpdateLeadBody):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "update leads set status=%s where id=%s and org_id=%s",
                (body.status, lead_id, normalize_org_id(body.org_id))
            )
            conn.commit()
        return {"status": "success"}
    finally:
        conn.close()

@router.delete("/leads/{lead_id}")
def delete_lead(lead_id: int, org_id: str):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "delete from leads where id=%s and org_id=%s",
                (lead_id, normalize_org_id(org_id))
            )
            conn.commit()
        return {"status": "success"}
    finally:
        conn.close()

@router.get("/form/lead/{bot_id}")
def get_lead_form(bot_id: str, org_id: str, bot_key: Optional[str] = None, session_id: Optional[str] = None):
    # Fetch services and form config from DB
    conn = get_conn()
    services_list = []
    form_config = {}
    try:
        _ensure_form_config_column(conn)
        with conn.cursor() as cur:
            cur.execute("select services, form_config from chatbots where id=%s", (bot_id,))
            row = cur.fetchone()
            if row:
                if row[0]:
                    services_list = row[0]
                if row[1]:
                    if isinstance(row[1], str):
                        try:
                            form_config = json.loads(row[1])
                        except Exception:
                            form_config = {}
                    else:
                        form_config = row[1]
    finally:
        conn.close()

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        :root {{
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --bg: #f3f4f6;
            --card-bg: #ffffff;
            --text-main: #1f2937;
            --text-muted: #6b7280;
            --border: #e5e7eb;
            --error: #ef4444;
        }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; 
            padding: 20px; 
            margin: 0; 
            background: var(--bg); 
            color: var(--text-main);
            display: flex;
            justify-content: center;
            min-height: 100vh;
        }}
        #form-container {{
            background: var(--card-bg);
            padding: 32px;
            border-radius: 12px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            width: 100%;
            max-width: 480px;
            box-sizing: border-box;
        }}
        h2 {{ margin-top: 0; margin-bottom: 24px; font-size: 24px; font-weight: 700; text-align: center; color: #111827; }}
        .form-group {{ margin-bottom: 20px; }}
        label {{ display: block; margin-bottom: 8px; font-weight: 600; font-size: 14px; color: #374151; }}
        .input-wrapper {{ position: relative; }}
        input, textarea, select {{ 
            width: 100%; 
            padding: 12px 16px; 
            border: 1px solid var(--border); 
            border-radius: 8px; 
            font-size: 15px; 
            box-sizing: border-box; 
            transition: all 0.2s;
            background: #f9fafb;
        }}
        input:focus, textarea:focus, select:focus {{ 
            outline: none; 
            border-color: var(--primary); 
            box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1); 
            background: #fff;
        }}
        input.invalid {{ border-color: var(--error); box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1); }}
        
        button {{ 
            width: 100%; 
            padding: 14px; 
            background: var(--primary); 
            color: white; 
            border: none; 
            border-radius: 8px; 
            font-weight: 600; 
            font-size: 16px;
            cursor: pointer; 
            transition: background 0.2s; 
            margin-top: 8px;
        }}
        button:hover {{ background: var(--primary-hover); }}
        button:disabled {{ opacity: 0.7; cursor: not-allowed; }}
        
        .success {{ display: none; text-align: center; padding: 40px 20px; background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        .success h3 {{ color: #059669; margin-bottom: 12px; font-size: 22px; }}
        .success p {{ color: var(--text-muted); line-height: 1.5; }}
        
        .checkbox-group {{ display: flex; flex-direction: column; gap: 10px; }}
        .checkbox-item {{ 
            display: flex; 
            align-items: center; 
            gap: 12px; 
            padding: 10px; 
            border: 1px solid var(--border); 
            border-radius: 8px; 
            cursor: pointer;
            transition: background 0.1s;
        }}
        .checkbox-item:hover {{ background: #f9fafb; }}
        .checkbox-item input {{ width: 18px; height: 18px; margin: 0; cursor: pointer; }}
        
        .helper-text {{ font-size: 12px; color: var(--text-muted); margin-top: 6px; }}
        .error-msg {{ color: var(--error); font-size: 13px; margin-top: 6px; display: none; font-weight: 500; }}
        
        .tag {{ 
            background: #eff6ff; 
            color: #1d4ed8; 
            padding: 6px 12px; 
            border-radius: 20px; 
            font-size: 13px; 
            display: inline-flex; 
            align-items: center; 
            gap: 6px; 
            font-weight: 500;
        }}
        .tag span {{ cursor: pointer; opacity: 0.6; font-size: 16px; line-height: 1; }}
        .tag span:hover {{ opacity: 1; }}
        
        /* Input prefix for phone */
        .phone-input-container {{ display: flex; position: relative; }}
        .phone-prefix {{
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0 12px;
            background: #f3f4f6;
            border: 1px solid var(--border);
            border-right: none;
            border-radius: 8px 0 0 8px;
            color: #4b5563;
            font-weight: 500;
            font-size: 14px;
            white-space: nowrap;
        }}
        .phone-input-container input {{ border-radius: 0 8px 8px 0; }}
        .phone-input-container.has-prefix input {{ border-radius: 0 8px 8px 0; }}
        .phone-input-container:not(.has-prefix) input {{ border-radius: 8px; }}
        
        .required-mark {{ color: var(--error); margin-left: 4px; }}
        
      </style>
    </head>
    <body>
      <div id="form-container">
        <h2>Contact Us</h2>
        <div class="form-group">
          <label>Name <span class="required-mark">*</span></label>
          <input type="text" id="name" required placeholder="Your full name">
        </div>
        <div class="form-group">
          <label>Email <span class="required-mark">*</span></label>
          <input type="email" id="email" required placeholder="you@company.com">
          <div id="email-helper" class="helper-text"></div>
          <div id="email-error" class="error-msg">Please enter a valid email address.</div>
        </div>
        <div class="form-group">
          <label>Phone <span class="required-mark">*</span></label>
          <div class="phone-input-container" id="phone-container">
             <!-- Prefix injected by JS if needed -->
             <input type="tel" id="phone" required placeholder="123 456 7890">
          </div>
          <div id="phone-helper" class="helper-text"></div>
          <div id="phone-error" class="error-msg">Please enter a valid phone number.</div>
        </div>
        
        <div class="form-group">
          <label>Services of Interest <span class="required-mark" id="services-required" style="display:none">*</span></label>
          <div id="services-container">
            {'<div class="checkbox-group">' + ''.join([f'<label class="checkbox-item"><input type="checkbox" value="{s}" onchange="updateServices()">{s}</label>' for s in services_list]) + '</div>' if services_list else ''}
            <div class="service-input-group" style="display: flex; gap: 8px; margin-bottom: 12px; margin-top: 12px;">
              <input type="text" id="service-input" placeholder="Other service..." onkeypress="if(event.key==='Enter'){{event.preventDefault();addService();}}">
              <button type="button" onclick="addService()" style="width: auto; padding: 0 20px; margin: 0; background: #4b5563;">Add</button>
            </div>
            <div id="tags-container" style="display: flex; flex-wrap: wrap; gap: 8px;">
              <!-- Tags will appear here -->
            </div>
            <input type="hidden" id="interest-details-hidden">
          </div>
        </div>

        <div class="form-group">
          <label>Additional Comments</label>
          <textarea id="interest" rows="3" placeholder="Any specific requirements or questions?"></textarea>
        </div>
        <button onclick="submitForm()">Submit Enquiry</button>
      </div>
      <div id="success" class="success">
        <div style="font-size: 48px; margin-bottom: 16px;">🎉</div>
        <h3>Thank you!</h3>
        <p>We have received your details and will contact you shortly.</p>
      </div>
      <script>
        const services = [];
        const preDefinedServices = {services_list};
        const formConfig = {json.dumps(form_config)};

        // Initialize UI based on config
        (function initUI() {{
            // Services required check
            if (preDefinedServices && preDefinedServices.length > 0) {{
                const sr = document.getElementById('services-required');
                if (sr) sr.style.display = 'inline';
            }}

            // Email helper and placeholder
            const emailInput = document.getElementById('email');
            if (formConfig.email_domains && formConfig.email_domains.length > 0) {{
                const domains = formConfig.email_domains.join(', ');
                document.getElementById('email-helper').textContent = 'Allowed domains: ' + domains;
                if (formConfig.email_domains.length === 1) {{
                    emailInput.placeholder = 'name@' + formConfig.email_domains[0];
                }}
            }}

            // Phone UI
            const phoneContainer = document.getElementById('phone-container');
            const phoneInput = document.getElementById('phone');
            const phoneHelper = document.getElementById('phone-helper');
            
            if (formConfig.phone_country_code) {{
                const prefix = document.createElement('div');
                prefix.className = 'phone-prefix';
                prefix.textContent = formConfig.phone_country_code;
                phoneContainer.insertBefore(prefix, phoneInput);
                phoneContainer.classList.add('has-prefix');
            }}

            let helperText = [];
            if (formConfig.phone_restriction) {{
                if (formConfig.phone_restriction === 'digits_only') {{
                    helperText.push('Digits only');
                    phoneInput.placeholder = '1234567890';
                }}
                if (formConfig.phone_restriction === '10_digits') {{
                    helperText.push('10 digits required');
                    phoneInput.placeholder = '9876543210';
                }}
                if (formConfig.phone_restriction === '10_plus_digits') {{
                    helperText.push('Min 10 digits');
                }}
            }}
            if (helperText.length > 0) {{
                phoneHelper.textContent = helperText.join(', ');
            }}
        }})();

        function updateServices() {{
          const checkboxes = document.querySelectorAll('.checkbox-item input:checked');
          const checked = Array.from(checkboxes).map(c => c.value);
          // Combine checked with manually added services
          const all = [...new Set([...checked, ...services])];
          document.getElementById('interest-details-hidden').value = all.join(', ');
        }}

        function addService() {{
          const input = document.getElementById('service-input');
          const val = input.value.trim();
          if (val && !services.includes(val)) {{
            services.push(val);
            renderTags();
            input.value = '';
            updateServices();
          }}
        }}

        function removeService(idx) {{
          services.splice(idx, 1);
          renderTags();
          updateServices();
        }}

        function renderTags() {{
          const container = document.getElementById('tags-container');
          container.innerHTML = services.map((s, i) => `
            <span class="tag">
              ${{s}}
              <span onclick="removeService(${{i}})">&times;</span>
            </span>
          `).join('');
        }}
        
        // Initialize
        updateServices();

        // Validation helpers
        function validateEmail(email) {{
          const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (!re.test(email)) return false;
          
          // Domain restriction
          if (formConfig.email_domains && formConfig.email_domains.length > 0) {{
            const domain = email.split('@')[1].toLowerCase();
            return formConfig.email_domains.some(d => domain === d.toLowerCase() || domain.endsWith('.' + d.toLowerCase()));
          }}
          return true;
        }}

        function validatePhone(phone) {{
          if (!phone) return true;
          
          let cleanPhone = phone.replace(/[\s-]/g, '');
          const digits = phone.replace(/\D/g, '');
          
          // Country code validation logic
          if (formConfig.phone_country_code) {{
             const code = formConfig.phone_country_code;
             const codeDigits = code.replace(/\D/g, '');
             
             // If user typed the code, strip it for length check
             if (cleanPhone.startsWith(code) || cleanPhone.startsWith('+' + codeDigits) || cleanPhone.startsWith('00' + codeDigits)) {{
                 // It has the code, effectively valid prefix-wise
             }} else {{
                 // User didn't type code, that's fine if we are showing the prefix
             }}
          }}

          const restriction = formConfig.phone_restriction || '';
          
          // Calculate effective length (ignoring country code if present in input)
          let effectiveDigits = digits;
          if (formConfig.phone_country_code) {{
             const codeDigits = formConfig.phone_country_code.replace(/\D/g, '');
             if (digits.startsWith(codeDigits)) {{
                 effectiveDigits = digits.substring(codeDigits.length);
             }}
          }}
          
          if (restriction === 'digits_only') {{
             return !/[a-zA-Z]/.test(phone) && effectiveDigits.length >= 7; 
          }} else if (restriction === '10_digits') {{
             return effectiveDigits.length === 10;
          }} else if (restriction === '10_plus_digits') {{
             return effectiveDigits.length >= 10;
          }}
          
          return digits.length >= 7;
        }}

        // Update error messages based on config
        const emailErrorMsg = document.getElementById('email-error');
        if (formConfig.email_domains && formConfig.email_domains.length > 0) {{
            emailErrorMsg.textContent = 'Please enter a valid email address from allowed domains (' + formConfig.email_domains.join(', ') + ').';
        }}
        
        const phoneErrorMsg = document.getElementById('phone-error');
        if (formConfig.phone_country_code || formConfig.phone_restriction) {{
            let msg = '';
            
            // If prefix is shown, we don't need to tell them to start with it, just valid number
            if (formConfig.phone_restriction === '10_digits') {{
                msg = 'Must be exactly 10 digits.';
            }} else if (formConfig.phone_restriction === '10_plus_digits') {{
                msg = 'Must be at least 10 digits.';
            }} else if (!msg) {{
                msg = 'Please enter a valid phone number.';
            }}
            
            phoneErrorMsg.textContent = msg;
        }}

        // Add event listeners
        const emailInput = document.getElementById('email');
        const phoneInput = document.getElementById('phone');
        const emailError = document.getElementById('email-error');
        const phoneError = document.getElementById('phone-error');

        if (emailInput) {{
            emailInput.addEventListener('input', function() {{
              if (validateEmail(this.value)) {{
                emailError.style.display = 'none';
                this.classList.remove('invalid');
              }}
            }});
            
            emailInput.addEventListener('blur', function() {{
              if (!validateEmail(this.value)) {{
                emailError.style.display = 'block';
                this.classList.add('invalid');
              }}
            }});
        }}

        if (phoneInput) {{
            phoneInput.addEventListener('input', function() {{
              if (validatePhone(this.value)) {{
                phoneError.style.display = 'none';
                this.classList.remove('invalid');
              }}
            }});
            
            phoneInput.addEventListener('blur', function() {{
               if (!validatePhone(this.value)) {{
                phoneError.style.display = 'block';
                this.classList.add('invalid');
              }}
            }});
        }}

        async function submitForm() {{
          const btn = document.querySelector('button[onclick="submitForm()"]');
          
          // Validate inputs
          const email = document.getElementById('email').value;
          const phone = document.getElementById('phone').value;
          let valid = true;
          
          // Validate Services (Required if defined)
          if (preDefinedServices && preDefinedServices.length > 0) {{
             const selectedServices = document.getElementById('interest-details-hidden').value;
             if (!selectedServices) {{
                 alert('Please select at least one service of interest.');
                 return;
             }}
          }}
          
          if (!validateEmail(email)) {{
            if (emailError) emailError.style.display = 'block';
            if (emailInput) emailInput.classList.add('invalid');
            valid = false;
          }}
          
          if (!validatePhone(phone)) {{
            if (phoneError) phoneError.style.display = 'block';
            if (phoneInput) phoneInput.classList.add('invalid');
            valid = false;
          }}
          
          if (!valid) return;

          btn.disabled = true;
          btn.textContent = 'Submitting...';
          
          const comments = document.getElementById('interest').value;
          const serviceList = document.getElementById('interest-details-hidden').value;
          const finalServices = serviceList ? serviceList : comments;
          
          // Prepare phone with country code if needed
          let finalPhone = document.getElementById('phone').value;
          if (formConfig.phone_country_code) {{
              const code = formConfig.phone_country_code;
              const codeDigits = code.replace(/\D/g, '');
              const clean = finalPhone.replace(/[\s-]/g, '');
              // If not already starting with code
              if (!clean.startsWith(code) && !clean.startsWith(codeDigits) && !clean.startsWith('00' + codeDigits)) {{
                  finalPhone = code + ' ' + finalPhone;
              }}
          }}

          const data = {{
            org_id: "{org_id}",
            bot_id: "{bot_id}",
            session_id: "{session_id or ''}",
            name: document.getElementById('name').value,
            email: document.getElementById('email').value,
            phone: finalPhone,
            interest_details: serviceList,
            comments: comments,
            interest_score: 50 // Default score
          }};
          
          try {{
            const res = await fetch('/api/leads/submit', {{
              method: 'POST',
              headers: {{ 'Content-Type': 'application/json', 'x-bot-key': '{bot_key or ""}' }},
              body: JSON.stringify(data)
            }});
            
            if (res.ok) {{
              const json = await res.json();
              document.getElementById('form-container').style.display = 'none';
              document.getElementById('success').style.display = 'block';
              try {{
                if (window.opener) {{
                    window.opener.postMessage({{ type: 'LEAD_SUBMITTED', id: json.id }}, '*');
                }} else if (window.parent) {{
                    window.parent.postMessage({{ type: 'LEAD_SUBMITTED', id: json.id }}, '*');
                }}
              }} catch(e) {{ console.error(e); }}
              setTimeout(function() {{ window.close(); }}, 3000);
            }} else {{
              alert('Error submitting form. Please try again.');
              btn.disabled = false;
              btn.textContent = 'Submit Enquiry';
            }}
          }} catch (e) {{
            console.error(e);
            alert('Error submitting form.');
            btn.disabled = false;
            btn.textContent = 'Submit Enquiry';
          }}
        }}
      </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)





@router.post("/chat/{bot_id}")
def chat(bot_id: str, body: ChatBody, x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, body.org_id)
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        _rate_limit(bot_id, body.org_id)

        # Check if user has already submitted a lead in this session
        has_submitted_lead = False
        if body.session_id:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select 1 from leads where session_id=%s and org_id=%s and bot_id=%s limit 1",
                        (body.session_id, normalize_org_id(body.org_id), bot_id)
                    )
                    if cur.fetchone():
                        has_submitted_lead = True
            except Exception as e:
                print(f"Error checking lead submission: {e}")
        
        # Smart booking intent detection for appointment bots
        if (behavior or '').strip().lower() == 'appointment':
            def _reply_with_history(text, citations=None, similarity=0.0):
                if body.session_id:
                    _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "user", body.message)
                    _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "assistant", text)
                return {"answer": text, "citations": citations or [], "similarity": similarity}

            import re
            msg = body.message.strip()
            m0lower = msg.lower()
            
            # Handle greetings
            is_greet = bool(m0lower) and (
                m0lower in {"hi", "hello", "hey", "hola", "hii", "bonjour", "hallo", "ciao", "namaste"} or
                any(m0lower.startswith(g + " ") for g in ["hi", "hello", "hey", "hola", "bonjour", "hallo"])
            )
            if is_greet:
                wm = None
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "select welcome_message from chatbots where id=%s",
                            (bot_id,),
                        )
                        rwm = cur.fetchone()
                        wm = rwm[0] if rwm else None
                except Exception:
                    wm = None
                def gen_hi():
                    text = wm or "Hello! I'm here to help you book an appointment. When would you like to schedule a visit?"
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                return StreamingResponse(gen_hi(), media_type="text/event-stream")
            
            # Get conversation history for context-aware detection
            history = _get_conversation_history(conn, body.session_id, body.org_id, bot_id, max_messages=10)
            
            # Hybrid intent detection (regex + LLM for ambiguous cases)
            intent_result = _hybrid_intent_detection(msg, history)
            
            
            base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
            form_url = f"{base}/api/form/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
            res_form_url = f"{base}/api/reschedule/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
            
            # Check for ID presence globally to bypass prompts
            m_id_global = re.search(r"\b(?:appointment|id)\s*[:#]?\s*(\d+)\b", msg, re.IGNORECASE)
            has_id_global = bool(m_id_global)

            with open("debug_flow.log", "a") as f:
                f.write(f"MSG: {msg}, has_id_global: {has_id_global}\n")

            # Handle different intents with user-friendly responses
            # Only show prompts if NO ID is provided (let ID management handle it otherwise)
            if intent_result['is_booking'] and not has_id_global:
                intent_type = intent_result.get('action', 'book')
                # Map action to response key
                if intent_type == 'book':
                    intent_type = 'new_booking'
                elif intent_type == 'status':
                    intent_type = 'check_status'
                    
                lang = intent_result.get('language', 'en')
                
                # Multi-language responses with booking form links
                responses = {
                    'new_booking': {
                        'en': f"I'd be happy to help you book an appointment! Please use our [booking form]({form_url}) to see available time slots and choose a convenient time.",
                        'hi': f"मुझे आपकी अपॉइंटमेंट बुक करने में मदद करके खुशी होगी! कृपया उपलब्ध समय देखने के लिए हमारा [बुकिंग फॉर्म]({form_url}) उपयोग करें।",
                        'ta': f"உங்கள் சந்திப்பை பதிவு செய்ய நான் உதவ மகிழ்ச்சியாக உள்ளேன்! கிடைக்கும் நேர இடைவெளிகளைப் பார்க்க எங்கள் [பதிவு படிவத்தை]({form_url}) பயன்படுத்தவும்.",
                        'te': f"మీ అపాయింట్మెంట్ బుక్ చేయడానికి నేను సంతోషంగా సహాయం చేస్తాను! అందుబాటులో ఉన్న సమయ స్లాట్లను చూడటానికి మా [బుకింగ్ ఫారమ్]({form_url}) ఉపయోగించండి.",
                        'kn': f"ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ನಾನು ಸಹಾಯ ಮಾಡಲು ಸಂತೋಷಪಡುತ್ತೇನೆ! ಲಭ್ಯವಿರುವ ಸಮಯ ಸ್ಲಾಟ್ಗಳನ್ನು ನೋಡಲು ನಮ್ಮ [ಬುಕಿಂಗ್ ಫಾರ್ಮ್]({form_url}) ಬಳಸಿ.",
                        'ml': f"നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് ബുക്ക് ചെയ്യാൻ സഹായിക്കുന്നതിൽ എനിക്ക് സന്തോഷമുണ്ട്! ലഭ്യമായ സമയ സ്ലോട്ടുകൾ കാണാൻ ഞങ്ങളുടെ [ബുക്കിംഗ് ഫോം]({form_url}) ഉപയോഗിക്കുക.",
                        'bn': f"আপনার অ্যাপয়েন্টমেন্ট বুক করতে সাহায্য করে আমি খুশি! উপলব্ধ সময় স্লট দেখতে আমাদের [বুকিং ফর্ম]({form_url}) ব্যবহার করুন।",
                        'mr': f"तुमची भेट बुक करण्यास मदत करण्यात मला आनंद होईल! उपलब्ध वेळ स्लॉट पाहण्यासाठी आमचा [बुकिंग फॉर्म]({form_url}) वापरा.",
                        'gu': f"તમારી મુલાકાત બુક કરવામાં મદદ કરીને મને આનંદ થશે! ઉપલબ્ધ સમય સ્લોટ જોવા માટે અમારા [બુકિંગ ફોર્મ]({form_url}) નો ઉપયોગ કરો.",
                        'pa': f"ਤੁਹਾਡੀ ਮੁਲਾਕਾਤ ਬੁੱਕ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰਕੇ ਮੈਨੂੰ ਖੁਸ਼ੀ ਹੋਵੇਗੀ! ਉਪਲਬਧ ਸਮਾਂ ਸਲਾਟ ਦੇਖਣ ਲਈ ਸਾਡੇ [ਬੁਕਿੰਗ ਫਾਰਮ]({form_url}) ਦੀ ਵਰਤੋਂ ਕਰੋ.",
                        'es': f"¡Con gusto te ayudo a reservar una cita! Por favor usa nuestro [formulario de reserva]({form_url}) para ver los horarios disponibles.",
                        'fr': f"Je serais ravi de vous aider à prendre un rendez-vous! Veuillez utiliser notre [formulaire de réservation]({form_url}) pour voir les créneaux disponibles.",
                        'de': f"Gerne helfe ich Ihnen einen Termin zu buchen! Bitte nutzen Sie unser [Buchungsformular]({form_url}) um verfügbare Zeiten zu sehen.",
                        'pt': f"Ficarei feliz em ajudá-lo a agendar uma consulta! Por favor, use nosso [formulário de agendamento]({form_url}) para ver os horários disponíveis.",
                    },
                    'reschedule': {
                        'en': f"To reschedule your appointment, use the [reschedule form]({res_form_url}) to select a new time.",
                        'hi': f"अपनी अपॉइंटमेंट को रीशेड्यूल करने के लिए [रीशेड्यूल फॉर्म]({res_form_url}) का उपयोग करें और नया समय चुनें।",
                        'ta': f"உங்கள் சந்திப்பை மீண்டும் திட்டமிட [மறு அட்டவணை படிவம்]({res_form_url}) பயன்படுத்தி புதிய நேரத்தைத் தேர்ந்தெடுக்கவும்.",
                        'te': f"మీ అపాయింట్మెంట్‌ను రీషెడ్యూల్ చేయడానికి [రీషెడ్యూల్ ఫారమ్]({res_form_url}) ఉపయోగించి కొత్త సమయాన్ని ఎంచుకోండి.",
                        'kn': f"ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಮರುನಿಗದಿಗೆ [ಮರುನಿಗದಿ ಫಾರ್ಮ್]({res_form_url}) ಬಳಸಿ ಮತ್ತು ಹೊಸ ಸಮಯವನ್ನು ಆಯ್ಕೆಮಾಡಿ.",
                        'ml': f"നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് റീഷെഡ്യൂൾ ചെയ്യാൻ [റീഷെഡ്യൂൾ ഫോം]({res_form_url}) ഉപയോഗിച്ച് പുതിയ സമയം തിരഞ്ഞെടുക്കുക.",
                        'bn': f"আপনার অ্যাপয়েন্টমেন্ট রিশিডিউল করতে [রিশিডিউল ফর্ম]({res_form_url}) ব্যবহার করে নতুন সময় নির্বাচন করুন।",
                        'mr': f"तुमची भेट रीशेड्यूल करण्यासाठी [रीशेड्यूल फॉर्म]({res_form_url}) वापरून नवीन वेळ निवडा.",
                        'gu': f"તમારી મુલાકાતને રીશેડ્યૂલ કરવા [રીશેડ્યૂલ ફોર્મ]({res_form_url}) નો ઉપયોગ કરીને નવો સમય પસંદ કરો.",
                        'pa': f"ਆਪਣੀ ਮੁਲਾਕਾਤ ਨੂੰ ਰੀਸ਼ਡਿਊਲ ਕਰਨ ਲਈ [ਰੀਸ਼ਡਿਊਲ ਫਾਰਮ]({res_form_url}) ਵਰਤੋਂ ਅਤੇ ਨਵਾਂ ਸਮਾਂ ਚੁਣੋ.",
                        'es': f"Para reprogramar su cita, use el [formulario de reprogramación]({res_form_url}) para seleccionar un nuevo horario.",
                        'fr': f"Pour reprogrammer votre rendez-vous, utilisez le [formulaire de replanification]({res_form_url}) pour choisir un nouvel horaire.",
                        'de': f"Um Ihren Termin zu verschieben, verwenden Sie das [Umlageformular]({res_form_url}), um eine neue Zeit auszuwählen.",
                        'pt': f"Para remarcar sua consulta, use o [formulário de remarcação]({res_form_url}) para selecionar um novo horário.",
                    },
                    'cancel': {
                        'en': "I can help you cancel your appointment. Please provide your appointment ID (e.g., 'appointment 123' or 'ID: 123').",
                        'hi': "मैं आपकी अपॉइंटमेंट रद्द करने में मदद कर सकता हूं। कृपया अपनी अपॉइंटमेंट ID बताएं (जैसे, 'अपॉइंटमेंट 123' या 'ID: 123')।",
                        'ta': "உங்கள் சந்திப்பை ரத்து செய்ய நான் உதவ முடியும். உங்கள் அப்பாயின்ட்மென்ட் ID வழங்கவும் (எ.கா., 'அப்பாயின்ட்மென்ட் 123' அல்லது 'ID: 123').",
                        'te': "మీ అపాయింట్మెంట్ను రద్దు చేయడానికి నేను సహాయం చేయగలను. దయచేసి మీ అపాయింట్మెంట్ ID అందించండి (ఉదా., 'అపాయింట్మెంట్ 123' లేదా 'ID: 123').",
                        'kn': "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ರದ್ದುಗೊಳಿಸಲು ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ID ನೀಡಿ (ಉದಾ., 'ಅಪಾಯಿಂಟ್ಮೆಂಟ್ 123' ಅಥವಾ 'ID: 123').",
                        'ml': "നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് റദ്ദാക്കാൻ എനിക്ക് സഹായിക്കാം. ദയവായി നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് ID നൽകുക (ഉദാ., 'അപ്പോയിന്റ്മെന്റ് 123' അല്ലെങ്കിൽ 'ID: 123').",
                        'bn': "আপনার অ্যাপয়েন্টমেন্ট বাতিল করতে আমি সাহায্য করতে পারি। অনুগ্রহ করে আপনার অ্যাপয়েন্টমেন্ট ID প্রদান করুন (যেমন, 'অ্যাপয়েন্টমেন্ট 123' বা 'ID: 123')।",
                        'mr': "तुमची भेट रद्द करण्यात मी मदत करू शकतो. कृपया तुमचा अपॉइंटमेंट ID द्या (उदा., 'अपॉइंटमेंट 123' किंवा 'ID: 123').",
                        'gu': "હું તમારી મુલાકાત રદ કરવામાં મદદ કરી શકું છું. કૃપા કરીને તમારી એપોઇન્ટમેન્ટ ID આપો (દા.ત., 'એપોઇન્ટમેન્ટ 123' અથવા 'ID: 123').",
                        'pa': "ਮੈਂ ਤੁਹਾਡੀ ਮੁਲਾਕਾਤ ਰੱਦ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣੀ ਮੁਲਾਕਾਤ ID ਦਿਓ (ਜਿਵੇਂ, 'ਮੁਲਾਕਾਤ 123' ਜਾਂ 'ID: 123').",
                        'es': "Puedo ayudarte a cancelar tu cita. Por favor proporciona tu ID de cita (ej., 'cita 123' o 'ID: 123').",
                        'fr': "Je peux vous aider à annuler votre rendez-vous. Veuillez fournir votre ID de rendez-vous (ex., 'rendez-vous 123' ou 'ID: 123').",
                        'de': "Ich kann Ihnen helfen, Ihren Termin abzusagen. Bitte geben Sie Ihre Termin-ID an (z.B. 'Termin 123' oder 'ID: 123').",
                        'pt': "Posso ajudá-lo a cancelar sua consulta. Por favor, forneça seu ID de consulta (ex., 'consulta 123' ou 'ID: 123').",
                    },
                    'check_status': {
                        'en': "I can check your appointment status. Please provide your appointment ID or email address.",
                        'hi': "मैं आपकी अपॉइंटमेंट की स्थिति जांच सकता हूं। कृपया अपनी अपॉइंटमेंट ID या ईमेल पता बताएं।",
                        'ta': "உங்கள் சந்திப்பு நிலையை நான் சரிபார்க்க முடியும். உங்கள் அப்பாயின்ட்மென்ட் ID அல்லது மின்னஞ்சல் முகவரியை வழங்கவும்.",
                        'te': "మీ అపాయింట్మెంట్ స్థితిని నేను తనిఖీ చేయగలను. దయచేసి మీ అపాయింట్మెంట్ ID లేదా ఇమెయిల్ చిరునామా అందించండి.",
                        'kn': "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಸ್ಥಿತಿಯನ್ನು ನಾನು ಪರಿಶೀಲಿಸಬಹುದು. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ID ಅಥವಾ ಇಮೇಲ್ ವಿಳಾಸವನ್ನು ನೀಡಿ.",
                        'ml': "നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് സ്ഥിതി എനിക്ക് പരിശോധിക്കാം. ദയവായി നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് ID അല്ലെങ്കിൽ ഇമെയിൽ വിലാസം നൽകുക.",
                        'bn': "আমি আপনার অ্যাপয়েন্টমেন্ট স্ট্যাটাস চেক করতে পারি। অনুগ্রহ করে আপনার অ্যাপয়েন্টমেন্ট ID বা ইমেইল ঠিকানা প্রদান করুন।",
                        'mr': "मी तुमच्या भेटीची स्थिती तपासू शकतो. कृपया तुमचा अपॉइंटमेंट ID किंवा ईमेल पत्ता द्या.",
                        'gu': "હું તમારી મુલાકાતની સ્થિતિ તપાસી શકું છું. કૃપા કરીને તમારી એપોઇન્ટમેન્ટ ID અથવા ઇમેઇલ સરનામું આપો.",
                        'pa': "ਮੈਂ ਤੁਹਾਡੀ ਮੁਲਾਕਾਤ ਦੀ ਸਥਿਤੀ ਜਾਂਚ ਸਕਦਾ ਹਾਂ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣੀ ਮੁਲਾਕਾਤ ID ਜਾਂ ਈਮੇਲ ਪਤਾ ਦਿਓ।",
                        'es': "Puedo verificar el estado de tu cita. Por favor proporciona tu ID de cita o correo electrónico.",
                        'fr': "Je peux vérifier le statut de votre rendez-vous. Veuillez fournir votre ID de rendez-vous ou adresse e-mail.",
                        'de': "Ich kann Ihren Terminstatus überprüfen. Bitte geben Sie Ihre Termin-ID oder E-Mail-Adresse an.",
                        'pt': "Posso verificar o status da sua consulta. Por favor, forneça seu ID de consulta ou endereço de e-mail.",
                    }
                }
                
                # Use language-specific response
                response_text = responses[intent_type].get(lang, responses[intent_type]['en'])
                
                # For status check, only return prompt if no ID is detected
                # If ID exists, let it fall through to the ID-based status check below
                if intent_type == 'check_status':
                    # Check if appointment ID is in the message
                    has_id = bool(re.search(r"\b(?:appointment|id)\s*[:#]?\s*\d+\b", msg, re.IGNORECASE))
                    if not has_id:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, intent_result['confidence'], False)
                        return _reply_with_history(response_text, [], intent_result['confidence'])
                    # Has ID - continue to ID-based status check below
                elif intent_type in ['new_booking', 'reschedule', 'cancel']:
                    # For other intents, return the prompt immediately
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, intent_result['confidence'], False)
                    return _reply_with_history(response_text, [], intent_result['confidence'])
            
            # Continue with existing appointment ID management code
            def _norm_month(s: str) -> int:
                m = s.lower()
                d = {
                    'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,'sep':9,'sept':9,'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12
                }
                return d.get(m,0)
            def _norm_weekday(s: str) -> int:
                m = s.lower()
                d = {'sunday':6,'sun':6,'monday':0,'mon':0,'tuesday':1,'tue':1,'tues':1,'wednesday':2,'wed':2,'thursday':3,'thu':3,'thur':3,'thurs':3,'friday':4,'fri':4,'saturday':5,'sat':5}
                return d.get(m,-1)
            def _parse_natural(s: str):
                from datetime import datetime, timedelta
                now = datetime.now()
                base_date = None
                m = re.search(r"\b(today|tomorrow|tomorow|tommorow|tmrw)\b", s, re.IGNORECASE)
                if m:
                    w = m.group(1).lower()
                    base_date = now.date() if w == 'today' else (now + timedelta(days=1)).date()
                if base_date is None:
                    mwd = re.search(r"\b(next\s+)?(mon(day)?|tue(s|sday)?|wed(nesday)?|thu(rs|rsday)?|fri(day)?|sat(urday)?|sun(day)?)\b", s, re.IGNORECASE)
                    if mwd:
                        is_next = bool(mwd.group(1))
                        wd = _norm_weekday(mwd.group(2))
                        if wd >= 0:
                            cur = now.weekday()
                            delta = (wd - cur) % 7
                            if delta == 0:
                                delta = 7 if is_next else 0
                            elif is_next:
                                delta = delta + 7
                            base_date = (now + timedelta(days=delta)).date()
                if base_date is None:
                    mmd = re.search(r"\b(\d{1,2})\s*(?:/|-)\s*(\d{1,2})(?:\s*(\d{4}))?\b", s)
                    if mmd:
                        d1 = int(mmd.group(1)); d2 = int(mmd.group(2)); y = int(mmd.group(3)) if mmd.group(3) else now.year
                        try:
                            base_date = datetime(y, d1, d2).date()
                        except Exception:
                            try:
                                base_date = datetime(y, d2, d1).date()
                            except Exception:
                                base_date = None
                if base_date is None:
                    mname = re.search(r"\b([A-Za-z]{3,9})\s*(\d{1,2})(?:,?\s*(\d{4}))?\b", s)
                    if mname:
                        mo = _norm_month(mname.group(1)); day = int(mname.group(2)); year = int(mname.group(3)) if mname.group(3) else now.year
                        if mo > 0:
                            try:
                                base_date = datetime(year, mo, day).date()
                            except Exception:
                                base_date = None
                st_h = None; st_m = 0; en_h = None; en_m = 0; dur_min = None
                mt = re.search(r"\b(at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", s, re.IGNORECASE)
                if mt:
                    sh = int(mt.group(2)); sm = int(mt.group(3) or '0'); ap = (mt.group(4) or '').lower()
                    if ap == 'pm' and sh < 12:
                        sh += 12
                    if ap == 'am' and sh == 12:
                        sh = 0
                    st_h, st_m = sh, sm
                mend = re.search(r"\b(to|until)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", s, re.IGNORECASE)
                if mend:
                    eh = int(mend.group(2)); em = int(mend.group(3) or '0'); ap = (mend.group(4) or '').lower()
                    if ap == 'pm' and eh < 12:
                        eh += 12
                    if ap == 'am' and eh == 12:
                        eh = 0
                    en_h, en_m = eh, em
                mdur = re.search(r"\bfor\s*(\d{1,3})\s*(minute|min|mins|hour|hr|hours|h)\b", s, re.IGNORECASE)
                if mdur:
                    val = int(mdur.group(1)); unit = mdur.group(2).lower()
                    dur_min = val * 60 if unit in {'hour','hours','hr','h'} else val
                if base_date and st_h is not None:
                    start_dt = datetime(base_date.year, base_date.month, base_date.day, st_h, st_m)
                    if en_h is not None:
                        end_dt = datetime(base_date.year, base_date.month, base_date.day, en_h, en_m)
                    else:
                        mins = dur_min if dur_min is not None else 30
                        end_dt = start_dt + timedelta(minutes=mins)
                    return start_dt.isoformat(), end_dt.isoformat()
                return None
            # --- Appointment management by ID: cancel/reschedule/status ---
            try:
                m_id = re.search(r"\b(?:appointment|id)\s*[:#]?\s*(\d+)\b", msg, re.IGNORECASE)
                ap_id = int(m_id.group(1)) if m_id else None
            except Exception:
                ap_id = None
            
            with open("debug_flow.log", "a") as f:
                f.write(f"ap_id: {ap_id}\n")

            if ap_id:
                lowmsg = msg.lower()
                try:
                    _ensure_oauth_table(conn)
                    _ensure_booking_settings_table(conn)
                    _ensure_audit_logs_table(conn)
                    
                    with conn.cursor() as cur:
                        # Check bot_appointments
                        cur.execute(
                            "select external_event_id, start_iso, end_iso, status, 'bot_appointments' as source from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                            (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id),
                        )
                        row_bot = cur.fetchone()
                        
                        # Check bookings
                        cur.execute(
                            """
                            select calendar_event_id, 
                                   (booking_date::text || 'T' || start_time::text) as start_iso,
                                   (booking_date::text || 'T' || end_time::text) as end_iso,
                                   status,
                                   'bookings' as source
                            from bookings 
                            where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s
                            """,
                            (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id),
                        )
                        row_booking = cur.fetchone()

                    if not row_bot and not row_booking:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": f"Appointment ID {ap_id} not found.", "citations": [], "similarity": 0.0}

                    # Determine intent
                    is_cancel = "cancel" in lowmsg
                    is_reschedule = any(x in lowmsg for x in ["reschedule", "re schedule", "change", "reshedule", "reschudule", "rescedule", " to "])
                    
                    if not is_cancel and not is_reschedule:
                        # Status check logic with Google Calendar fetch
                        row = row_booking if row_booking else row_bot
                        ev_id = row[0]
                        
                        # Try to fetch from Google Calendar for rich details
                        g_event = None
                        try:
                            # Reuse logic to build service
                            with conn.cursor() as cur:
                                cur.execute(
                                    "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                                    (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                                )
                                c = cur.fetchone()
                            
                            if c:
                                cal_id, at_enc, rt_enc, exp = c
                                from app.services.calendar_google import _decrypt, build_service_from_tokens, get_event_oauth
                                at = _decrypt(at_enc) if at_enc else None
                                rt = _decrypt(rt_enc) if rt_enc else None
                                svc = build_service_from_tokens(at or "", rt, exp)
                                if svc and ev_id:
                                    g_event = get_event_oauth(svc, cal_id or "primary", ev_id)
                        except Exception as e:
                            print(f"Error fetching Google Event: {e}")
                        
                        # Format response
                        msgs = []
                        if g_event:
                            summary = g_event.get('summary', 'Appointment')
                            start = g_event.get('start', {}).get('dateTime', g_event.get('start', {}).get('date'))
                            end = g_event.get('end', {}).get('dateTime', g_event.get('end', {}).get('date'))
                            link = g_event.get('htmlLink')
                            meet = g_event.get('hangoutLink')
                            desc = g_event.get('description')
                            
                            # Parse dates
                            try:
                                dt_start = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                                dt_end = datetime.datetime.fromisoformat(end.replace('Z', '+00:00'))
                                time_str = f"{dt_start.strftime('%B %d, %Y at %I:%M %p')} - {dt_end.strftime('%I:%M %p')}"
                            except:
                                time_str = f"{start} to {end}"
                                
                            msg = f"**{summary}**\n\n🕒 **Time:** {time_str}\n✅ **Status:** {g_event.get('status', 'confirmed')}"
                            if meet:
                                msg += f"\n📹 **Join Meeting:** [Google Meet]({meet})"
                            if link:
                                msg += f"\n📅 **Calendar Link:** [View Event]({link})"
                            if desc:
                                msg += f"\n📝 **Description:** {desc}"
                            msgs.append(msg)
                        else:
                            # Fallback to DB
                            if row_booking:
                                 # Parse ISO
                                 try:
                                     dt_s = datetime.datetime.fromisoformat(row_booking[1])
                                     dt_e = datetime.datetime.fromisoformat(row_booking[2])
                                     time_str = f"{dt_s.strftime('%B %d, %Y at %I:%M %p')} - {dt_e.strftime('%I:%M %p')}"
                                 except:
                                     time_str = f"{row_booking[1]} to {row_booking[2]}"
                                 msgs.append(f"**Booking #{ap_id}**\n\n🕒 **Time:** {time_str}\n✅ **Status:** {row_booking[3]}")
                            elif row_bot:
                                 try:
                                     dt_s = datetime.datetime.fromisoformat(row_bot[1])
                                     dt_e = datetime.datetime.fromisoformat(row_bot[2])
                                     time_str = f"{dt_s.strftime('%B %d, %Y at %I:%M %p')} - {dt_e.strftime('%I:%M %p')}"
                                 except:
                                     time_str = f"{row_bot[1]} to {row_bot[2]}"
                                 msgs.append(f"**Appointment #{ap_id}**\n\n🕒 **Time:** {time_str}\n✅ **Status:** {row_bot[3]}")
                        
                        status_text = "\n\n".join(msgs)
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return _reply_with_history(status_text, [], 1.0)

                    # Prioritize booking for actions
                    row = row_booking if row_booking else row_bot
                    ev_id, cur_si, cur_ei, cur_st = row[0], row[1], row[2], row[3]

                    with conn.cursor() as cur:
                        cur.execute(
                            "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                            (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                        )
                        c = cur.fetchone()
                    if not c:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "Calendar not connected. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")", "citations": [], "similarity": 0.0}
                    cal_id, at_enc, rt_enc, exp = c
                    from app.services.calendar_google import _decrypt, build_service_from_tokens, update_event_oauth, delete_event_oauth
                    at = _decrypt(at_enc) if at_enc else None
                    rt = _decrypt(rt_enc) if rt_enc else None
                    svc = build_service_from_tokens(at or "", rt, exp)
                    if not svc:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "Calendar service unavailable.", "citations": [], "similarity": 0.0}
                    if is_cancel:
                        if ((cur_st or '').lower() == 'completed'):
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                            return {"answer": "Completed appointment cannot be cancelled.", "citations": [], "similarity": 0.0}
                        ok = delete_event_oauth(svc, cal_id or "primary", ev_id)
                        if not ok:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return {"answer": "Cancel failed.", "citations": [], "similarity": 0.0}
                        with conn.cursor() as cur:
                            cur.execute("select 1 from bookings where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s", (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id))
                            in_bookings = cur.fetchone()
                            if in_bookings:
                                cur.execute("update bookings set status=%s, cancelled_at=now(), updated_at=now() where id=%s", ("cancelled", ap_id))
                            else:
                                cur.execute("update bot_appointments set status=%s, updated_at=now() where id=%s", ("cancelled", ap_id))
                        _log_audit(conn, body.org_id, bot_id, ap_id, "cancel", {})
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return _reply_with_history(f"Cancelled appointment ID: {ap_id}", [], 1.0)
                    if ("reschedule" in lowmsg) or ("re schedule" in lowmsg) or ("change" in lowmsg) or ("reshedule" in lowmsg) or ("reschudule" in lowmsg) or ("rescedule" in lowmsg) or (" to " in lowmsg):
                        si_ei = None
                        m = re.search(r"\bto\b(.+)$", msg, re.IGNORECASE)
                        if m:
                            si_ei = _parse_natural(m.group(1)) or None
                        if not si_ei:
                            si_ei = _parse_natural(msg)
                        if not si_ei:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "Use the [reschedule form](" + res_form_url + ") to reschedule your appointment.", "citations": [], "similarity": 0.0}
                        new_si, new_ei = si_ei
                        patch = {"start": {"dateTime": new_si}, "end": {"dateTime": new_ei}}
                        ok = update_event_oauth(svc, cal_id or "primary", ev_id, patch)
                        if not ok:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return {"answer": "Reschedule failed.", "citations": [], "similarity": 0.0}
                        with conn.cursor() as cur:
                            cur.execute("update bot_appointments set start_iso=%s, end_iso=%s, status=%s, updated_at=now() where id=%s", (new_si, new_ei, "booked", ap_id))
                        _log_audit(conn, body.org_id, bot_id, ap_id, "reschedule", {"new_start_iso": new_si, "new_end_iso": new_ei})
                        try:
                            desc = f"Appointment ID: {ap_id}\nName: {info.get('name') or ''}\nEmail: {info.get('email') or ''}\nPhone: {info.get('phone') or ''}\nNotes: {info.get('notes') or ''}"
                            patch2 = {"summary": "Appointment #"+str(ap_id)+" - "+(info.get('name') or ''), "description": desc}
                            update_event_oauth(svc, cal_id or "primary", ev_id, patch2)
                        except Exception:
                            pass
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return _reply_with_history(f"Rescheduled ID {ap_id} to {new_si} - {new_ei}", [], 1.0)
                    
                    # Status check - use multi-language responses
                    lang = intent_result.get('language', 'en')
                    status_responses = {
                        'en': f"Appointment #{ap_id}\nTime: {cur_si} to {cur_ei}\nStatus: {cur_st}",
                        'hi': f"अपॉइंटमेंट #{ap_id}\nसमय: {cur_si} से {cur_ei}\nस्थिति: {cur_st}",
                        'ta': f"சந்திப்பு #{ap_id}\nநேரம்: {cur_si} முதல் {cur_ei}\nநிலை: {cur_st}",
                        'te': f"అపాయింట్మెంట్ #{ap_id}\nసమయం: {cur_si} నుండి {cur_ei}\nస్థితి: {cur_st}",
                        'kn': f"ಅಪಾಯಿಂಟ್ಮೆಂಟ್ #{ap_id}\nಸಮಯ: {cur_si} ರಿಂದ {cur_ei}\nಸ್ಥಿತಿ: {cur_st}",
                        'ml': f"അപ്പോയിന്റ്മെന്റ് #{ap_id}\nസമയം: {cur_si} മുതൽ {cur_ei}\nസ്ഥിതി: {cur_st}",
                        'bn': f"অ্যাপয়েন্টমেন্ট #{ap_id}\nসময়: {cur_si} থেকে {cur_ei}\nঅবস্থা: {cur_st}",
                        'mr': f"भेट #{ap_id}\nवेळ: {cur_si} ते {cur_ei}\nस्थिती: {cur_st}",
                        'gu': f"મુલાકાત #{ap_id}\nસમય: {cur_si} થી {cur_ei}\nસ્થિતિ: {cur_st}",
                        'pa': f"ਮੁਲਾਕਾਤ #{ap_id}\nਸਮਾਂ: {cur_si} ਤੋਂ {cur_ei}\nਸਥਿਤੀ: {cur_st}",
                    }
                    status_text = status_responses.get(lang, status_responses['en'])
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                    return _reply_with_history(status_text, [], 1.0)
                except Exception:
                    try:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                    except Exception:
                        pass
                    return {"answer": "Error handling appointment.", "citations": [], "similarity": 0.0}
            if not ap_id and "my booking" in msg.lower():
                try:
                    with conn.cursor() as cur:
                        cur.execute("select id, start_iso, end_iso, status from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s order by created_at desc limit 1", (normalize_org_id(body.org_id), body.org_id, bot_id))
                        row = cur.fetchone()
                    if not row:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "No appointments found.", "citations": [], "similarity": 0.0}
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, 0.5, False)
                    return {"answer": f"Latest appointment ID {int(row[0])}: {row[1]} to {row[2]}. Status: {row[3]}", "citations": [], "similarity": 0.5}
                except Exception:
                    pass
            # Check if this is a new booking request (not reschedule/cancel) - show form directly
            lowmsg = msg.lower()
            is_new_booking = bool(re.search(r"\b(book|schedule|appointment)\b", lowmsg)) and not bool(re.search(r"\b(cancel|reschedule|change|status)\b", lowmsg))
            if not ap_id and is_new_booking:
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                return {"answer": "Please use the [booking form](" + form_url + ") to schedule your appointment. It shows available time slots and you can select a convenient time.", "citations": [], "similarity": 0.0}
            patt = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})(?:[T\s](?P<start>\d{2}:\d{2})(?:\s*(?:to|-|until)\s*(?P<end>\d{2}:\d{2}))?)", re.IGNORECASE)
            m = patt.search(msg)
            if m:
                d = m.group('date')
                st = m.group('start')
                en = m.group('end') or None
                if not en:
                    try:
                        sd = f"{d}T{st}:00"
                        from datetime import datetime, timedelta
                        start_dt = datetime.fromisoformat(sd)
                        end_dt = start_dt + timedelta(minutes=30)
                        ei = end_dt.isoformat()
                    except Exception:
                        ei = f"{d}T{st}:00"
                else:
                    ei = f"{d}T{en}:00"
                si = f"{d}T{st}:00"
            else:
                parsed = _parse_natural(msg)
                if parsed:
                    si, ei = parsed
                else:
                    si = None; ei = None
            try:
                _ensure_oauth_table(conn)
                _ensure_booking_settings_table(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        "select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                        (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                    )
                    row = cur.fetchone()
                    if not row:
                        raise Exception("Calendar not connected")
                    cal_id, at_enc, rt_enc = row
                    cur.execute(
                        "select timezone, slot_duration_minutes, capacity_per_slot, required_user_fields from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                        (normalize_org_id(body.org_id), body.org_id, bot_id),
                    )
                    bs = cur.fetchone()
                    from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth, create_event_oauth
                    at = _decrypt(at_enc) if at_enc else None
                    rt = _decrypt(rt_enc) if rt_enc else None
                    svc = build_service_from_tokens(at or "", rt, None)
                    tzv = (bs[0] if bs and len(bs) > 0 else None) or None
                    slot_dur = int(bs[1]) if bs and bs[1] else 30
                    capacity = int(bs[2]) if bs and bs[2] else 1
                    import json as _json
                    required_fields = []
                    try:
                        rfraw = (bs[3] if bs and len(bs) > 3 else None)
                        required_fields = rfraw if isinstance(rfraw, list) else (_json.loads(rfraw) if isinstance(rfraw, str) else [])
                    except Exception:
                        required_fields = []
                    import datetime as _dt
                    if not si or not ei:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        _link = res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url
                        return {"answer": "Could not parse date/time. Try formats like '2025-12-06 15:30' or 'tomorrow at 3pm for 30 minutes'. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + _link + ")", "citations": [], "similarity": 0.0}
                    tmn = _dt.datetime.fromisoformat(si)
                    tmx = _dt.datetime.fromisoformat(ei)
                    if not svc:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": "Calendar not connected. Please connect Google Calendar in the dashboard. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")", "citations": [], "similarity": 0.0}
                    items = list_events_oauth(svc, cal_id or "primary", tmn.isoformat(), tmx.isoformat())
                    # extract user info from message
                    info = {}
                    try:
                        em = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", msg)
                        if em:
                            info["email"] = em.group(0)
                        ph = re.search(r"\+?\d[\d \-]{7,}\d", msg)
                        if ph:
                            import re as _re
                            info["phone"] = _re.sub(r"\D", "", ph.group(0))
                        nm = re.search(r"(?:my name is|i am|this is)\s+([A-Za-z][A-Za-z .'-]{1,50})", msg, re.IGNORECASE)
                        if nm:
                            info["name"] = nm.group(1).strip()
                        nt = re.search(r"(?:purpose|note|reason)[:\-]\s*(.+)$", msg, re.IGNORECASE)
                        if nt:
                            info["notes"] = nt.group(1).strip()
                    except Exception:
                        pass
                    missing = [f for f in (required_fields or []) if not info.get(f)]
                    if missing:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": ("Please provide: " + ", ".join(missing) + ". Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")"), "citations": [], "similarity": 0.0}
                    occ = len(items) if items else 0
                    with conn.cursor() as cur:
                        # Check capacity from unified bookings table
                        try:
                            # Extract date and time from ISO string
                            import datetime as dt_check
                            dt_obj = dt_check.datetime.fromisoformat(si.replace('Z', '+00:00'))
                            booking_date = dt_obj.date()
                            start_time = dt_obj.time()
                            
                            cur.execute(
                                "select count(*) from bookings where bot_id=%s and booking_date=%s and start_time=%s and status not in ('cancelled','rejected')",
                                (bot_id, booking_date, start_time),
                            )
                            occ_db = int(cur.fetchone()[0])
                        except Exception:
                            # Fallback to counting all bookings in that time range
                            cur.execute(
                                "select count(*) from bookings where bot_id=%s and status not in ('cancelled','rejected')",
                                (bot_id,),
                            )
                            occ_db = 0  # If we can't parse, don't block
                    if max(occ, occ_db) < capacity:
                        apid = None
                        ext_id = None
                        try:
                            attns = ([info.get("email")] if info.get("email") else None)
                            desc = f"Appointment\nName: {info.get('name') or ''}\nEmail: {info.get('email') or ''}\nPhone: {info.get('phone') or ''}\nNotes: {info.get('notes') or ''}"
                            ext_id = create_event_oauth(svc, cal_id or "primary", "Appointment", si, ei, attns, tzv, desc)
                            if not ext_id:
                                _ensure_usage_table(conn)
                                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                                return {"answer": "Calendar booking failed. Please try again after reconnecting Google Calendar. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")", "citations": [], "similarity": 0.0}
                            _ensure_appointments_table(conn)
                            
                            # Debug logging
                            print(f"[DEBUG] Creating appointment:")
                            print(f"[DEBUG] org_id (raw): {body.org_id}")
                            print(f"[DEBUG] org_id (normalized): {normalize_org_id(body.org_id)}")
                            print(f"[DEBUG] bot_id: {bot_id}")
                            print(f"[DEBUG] start_iso: {si}, end_iso: {ei}")
                            
                            try:
                                with conn.cursor() as cur:
                                    cur.execute(
                                        """
                                        insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json, status, external_event_id)
                                        values (%s,%s,%s,%s,%s,%s,%s,%s)
                                        returning id
                                        """,
                                        (normalize_org_id(body.org_id), bot_id, "Appointment", si, ei, None if not info else __import__("json").dumps(info), "scheduled", ext_id),
                                    )
                                    apid = int(cur.fetchone()[0])
                                    print(f"[DEBUG] Created appointment with ID: {apid}")
                            except Exception as e:
                                print(f"[DEBUG] ERROR creating appointment: {e}")
                                import traceback
                                traceback.print_exc()
                                raise
                            try:
                                from app.services.calendar_google import update_event_oauth
                                desc = f"Appointment ID: {apid}\nName: {info.get('name') or ''}\nEmail: {info.get('email') or ''}\nPhone: {info.get('phone') or ''}\nNotes: {info.get('notes') or ''}"
                                patch = {
                                    "summary": "Appointment #"+str(apid)+" - "+(info.get('name') or ''),
                                    "description": desc,
                                    "extendedProperties": {"private": {"appointment_id": str(apid), "org_id": body.org_id, "bot_id": bot_id}},
                                }
                                update_event_oauth(svc, cal_id or "primary", ext_id, patch)
                            except Exception:
                                _log_audit(conn, body.org_id, bot_id, apid, "calendar_patch_error", {"ext_id": ext_id})
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                            return _reply_with_history(f"Booked. ID: {apid}", [], 1.0)
                        except Exception:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return {"answer": "Booking failed. Please try again or provide a different time. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")", "citations": [], "similarity": 0.0}
                    else:
                        sugg = []
                        cur_t = _dt.datetime.fromisoformat(si)
                        for _ in range(6):
                            cur_t = cur_t + _dt.timedelta(minutes=slot_dur)
                            end_t = cur_t + _dt.timedelta(minutes=slot_dur)
                            evs = list_events_oauth(svc, cal_id or "primary", cur_t.isoformat(), end_t.isoformat())
                            if not evs or len(evs) < capacity:
                                sugg.append(cur_t.isoformat())
                            if len(sugg) >= 3:
                                break
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return {"answer": ("Unavailable. Alternatives: " + ", ".join(sugg) + ". Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")"), "citations": [], "similarity": 0.0}
            except Exception:
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return {"answer": "Could not process booking request. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")", "citations": [], "similarity": 0.0}
        m0 = (body.message or '').strip().lower()
        wm = None
        is_greet = bool(m0) and (m0 in {"hi","hello","hey","hola","hii"} or m0.startswith("hi ") or m0.startswith("hello ") or m0.startswith("hey "))
        if is_greet:
            try:
                with conn.cursor() as cur:
                    cur.execute("select welcome_message from chatbots where id=%s", (bot_id,))
                    rwm = cur.fetchone(); wm = rwm[0] if rwm else None
            except Exception:
                wm = None
            def gen_hi():
                text = wm or "Hello! How can I help you?"
                yield f"data: {text}\n\n"; yield "event: end\n\n"
            _ensure_usage_table(conn)
            _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
            return StreamingResponse(gen_hi(), media_type="text/event-stream")

        # Sales Bot: Check for strong lead generation intent
        beh_lower = (behavior or '').strip().lower()
        if ('sale' in beh_lower or beh_lower == 'sales') and not has_submitted_lead:
            try:
                sales_intent = _detect_sales_intent(body.message)
                if sales_intent['is_sales'] and sales_intent['confidence'] >= 0.8:
                    base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
                    lead_form_url = f"{base}/api/form/lead/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
                    
                    # Check for multi-language response needed
                    is_indian_lang = any(ord(c) >= 0x0900 for c in body.message)
                    
                    if is_indian_lang:
                         # Simple fallback for Indian languages - we can improve this later
                         resp_text = f"कृपया हमारी बिक्री टीम से संपर्क करने के लिए इस फॉर्म को भरें: [Enquiry Form]({lead_form_url})"
                    else:
                         resp_text = f"I'd be happy to connect you with our sales team! Please fill out this quick form so we can assist you better: [Enquiry Form]({lead_form_url})"
                    
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                    
                    if body.session_id:
                        _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "user", body.message)
                        _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "assistant", resp_text)
                        
                    return {"answer": resp_text, "citations": [], "similarity": 1.0}
            except Exception as e:
                print(f"[ERROR] Sales intent detection failed: {e}")
                # Fall through to normal chat logic


        chunks = search_top_chunks(body.org_id, bot_id, body.message, settings.MAX_CONTEXT_CHUNKS)
        if not chunks:
            msg = body.message.strip().lower()
            wm = None
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select welcome_message, behavior, system_prompt from chatbots where id=%s",
                        (bot_id,),
                    )
                    rwm = cur.fetchone()
                    wm = rwm[0] if rwm else None
                    beh = rwm[1] if rwm else None
                    sys = rwm[2] if rwm else None
            except Exception:
                wm = None
                beh = None
                sys = None
            is_greet = bool(msg) and (
                msg in {"hi", "hello", "hey", "hola", "hii"} or
                msg.startswith("hi ") or msg.startswith("hello ") or msg.startswith("hey ")
            )
            if is_greet:
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                welcome_msg = (wm or "Hello! How can I help you?")
                # Save greeting exchange to conversation history
                if body.session_id:
                    _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "user", body.message)
                    _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "assistant", welcome_msg)
                return {"answer": welcome_msg, "citations": [], "similarity": 0.0}
            
            # Get conversation history for context
            history = _get_conversation_history(conn, body.session_id, body.org_id, bot_id, max_messages=10)
            
            try:
                sysmsg = (
                    f"You are a {beh or 'helpful'} assistant. "
                    + (sys or "Answer with general knowledge when needed.")
                    + " Keep responses short and informative."
                )
                
                # Build messages with conversation history
                messages = [{"role": "system", "content": sysmsg}]
                messages.extend(history)  # Add conversation history
                messages.append({"role": "user", "content": body.message})
                
                resp = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    temperature=0.5,
                    messages=messages,
                )
                answer = resp.choices[0].message.content
                
                # Save to conversation history
                if body.session_id:
                    _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "user", body.message)
                    _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "assistant", answer)
            except Exception:
                answer = "I don't have that information."
            _ensure_usage_table(conn)
            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
            return {"answer": answer, "citations": [], "similarity": 0.0}

        context = "\n\n".join([c[0] for c in chunks])
        
        # Add context about lead submission
        lead_context_prompt = ""
        if has_submitted_lead:
            lead_context_prompt = " The user has already submitted their details/enquiry form. Acknowledge this if relevant, and do not ask them to fill the form again unless explicitly requested."

        base = f"You are a {behavior} assistant."
        if (behavior or '').strip().lower() == 'appointment':
            base += f" You handle appointment booking. IMPORTANT: You MUST NOT ask the user for personal details (Name, Phone, Email, Time) to book an appointment. Instead, simply provide this booking link: {form_url} . For rescheduling, provide this link: {res_form_url} . Only for cancellation or status checks, you MUST ask the user for their Appointment ID. Tell users to type 'cancel' followed by their ID to cancel, or 'status' followed by their ID to check status."
        suffix = " Keep responses short and informative."
        if (behavior or '').strip().lower() == 'appointment':
            suffix += " Do NOT ask for booking details (Name, Phone, etc). Use the provided links."
        
        system = (
            (base + " " + system_prompt + suffix + lead_context_prompt)
            if system_prompt
            else (
                base + " Use only the provided context. If the answer is not in context, say: \"I don't have that information.\" " + suffix + lead_context_prompt
            )
        )
        user = f"Context:\n{context}\n\nQuestion:\n{body.message}"
        
        # Get conversation history for context
        history = _get_conversation_history(conn, body.session_id, body.org_id, bot_id, max_messages=8)

        try:
            # Build messages with conversation history
            messages = [{"role": "system", "content": system}]
            messages.extend(history)  # Add conversation history
            messages.append({"role": "user", "content": user})
            
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                messages=messages,
            )
            answer = resp.choices[0].message.content
            
            # Save to conversation history
            if body.session_id:
                _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "user", body.message)
                _save_conversation_message(conn, body.session_id, body.org_id, bot_id, "assistant", answer)
        except Exception:
            answer = "I don't have that information."
        import math
        sim = float(chunks[0][2])
        if not math.isfinite(sim):
            sim = 0.0
        _ensure_usage_table(conn)
        _log_chat_usage(conn, body.org_id, bot_id, sim, answer == "I don't have that information.")
        return {
            "answer": answer,
            "citations": [c[0][:120] for c in chunks],
            "similarity": sim,
        }
    finally:
        conn.close()

@router.post("/bots")
def create_bot(body: CreateBotBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    import uuid
    bot_id = str(uuid.uuid4())
    allowed = {"sales", "support", "appointment", "qna"}
    beh = (body.behavior or "support").strip().lower()
    if beh in {"appointments", "appointment booking", "bookings"}:
        beh = "appointment"
    if beh in {"sale", "sales bot"}:
        beh = "sales"
    if beh not in allowed:
        raise HTTPException(status_code=400, detail=f"behavior must be one of {sorted(allowed)}")
    nm = (body.name or "").strip() or f"{beh.title()} Bot"
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select 1 from organizations where id=%s",
                (normalize_org_id(body.org_id),),
            )
            r = cur.fetchone()
            if not r:
                cur.execute(
                    "insert into organizations (id, name) values (%s,%s)",
                    (normalize_org_id(body.org_id), body.org_id),
                )
            def ensure_col(name: str, ddl: str):
                try:
                    cur.execute(ddl)
                except Exception:
                    pass
            ensure_col("name", "alter table chatbots add column if not exists name text")
            ensure_col("website_url", "alter table chatbots add column if not exists website_url text")
            ensure_col("role", "alter table chatbots add column if not exists role text")
            ensure_col("tone", "alter table chatbots add column if not exists tone text")
            ensure_col("welcome_message", "alter table chatbots add column if not exists welcome_message text")
            ensure_col("services", "alter table chatbots add column if not exists services text[]")
            try:
                cur.execute(
                    """
                    insert into chatbots (id, org_id, behavior, system_prompt, name, website_url, role, tone, welcome_message, services)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (bot_id, normalize_org_id(body.org_id), beh, body.system_prompt, nm, body.website_url, body.role, body.tone, body.welcome_message, body.services),
                )
            except Exception:
                try:
                    cur.execute(
                        "insert into chatbots (id, org_id, behavior, system_prompt, name) values (%s,%s,%s,%s,%s)",
                        (bot_id, normalize_org_id(body.org_id), beh, body.system_prompt, nm),
                    )
                except Exception:
                    cur.execute(
                        "insert into chatbots (id, org_id, behavior, system_prompt, name) values (%s,%s,%s,%s,%s)",
                        (bot_id, normalize_org_id(body.org_id), beh, body.system_prompt, nm),
                    )
        return {"bot_id": bot_id}
    finally:
        conn.close()

class UpdateBotBody(BaseModel):
    org_id: str
    behavior: Optional[str] = None
    system_prompt: Optional[str] = None
    name: Optional[str] = None
    website_url: Optional[str] = None
    role: Optional[str] = None
    tone: Optional[str] = None
    welcome_message: Optional[str] = None
    services: Optional[List[str]] = None
    form_config: Optional[dict] = None

@router.put("/bots/{bot_id}")
def update_bot(bot_id: str, body: UpdateBotBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Build dynamic update query
            fields = []
            params = []
            if body.behavior:
                fields.append("behavior=%s")
                params.append(body.behavior)
            if body.system_prompt is not None:
                fields.append("system_prompt=%s")
                params.append(body.system_prompt)
            if body.name is not None:
                fields.append("name=%s")
                params.append(body.name)
            if body.website_url is not None:
                fields.append("website_url=%s")
                params.append(body.website_url)
            if body.role is not None:
                fields.append("role=%s")
                params.append(body.role)
            if body.tone is not None:
                fields.append("tone=%s")
                params.append(body.tone)
            if body.welcome_message is not None:
                fields.append("welcome_message=%s")
                params.append(body.welcome_message)
            if body.services is not None:
                fields.append("services=%s")
                params.append(body.services)
            if body.form_config is not None:
                fields.append("form_config=%s")
                params.append(json.dumps(body.form_config))
                
            if not fields:
                return {"updated": False}
                
            sql = f"update chatbots set {', '.join(fields)}, updated_at=now() where id=%s and org_id=%s"
            params.append(bot_id)
            params.append(normalize_org_id(body.org_id))
            
            cur.execute(sql, tuple(params))
            return {"updated": cur.rowcount > 0}
    finally:
        conn.close()

@router.get("/bots")
def list_bots(org_id: str, authorization: Optional[str] = Header(default=None)):
    if authorization:
        _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        org_n = normalize_org_id(org_id)
        import uuid
        nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org_id))
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "select id, name, behavior, system_prompt, public_api_key, website_url, role, tone, welcome_message, services from chatbots where org_id=%s",
                    (org_n,),
                )
            except Exception:
                cur.execute(
                    "select id, NULL as name, behavior, system_prompt, NULL as public_api_key, NULL as website_url, NULL as role, NULL as tone, NULL as welcome_message, NULL as services from chatbots where org_id=%s",
                    (org_n,),
                )
            rows = cur.fetchall()
        items = []
        for r in rows:
            items.append({
                "bot_id": r[0],
                "name": r[1],
                "behavior": r[2],
                "system_prompt": r[3],
                "has_key": bool(r[4]) if len(r) > 4 else False,
                "website_url": r[5] if len(r) > 5 else None,
                "role": r[6] if len(r) > 6 else None,
                "tone": r[7] if len(r) > 7 else None,
                "welcome_message": r[8] if len(r) > 8 else None,
                "services": r[9] if len(r) > 9 else None,
            })
        return {"bots": items}
    finally:
        conn.close()

@router.options("/bots")
def options_bots():
    return Response(status_code=204)


@router.post("/chat/stream/{bot_id}")
def chat_stream(bot_id: str, body: ChatBody, x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, body.org_id)
        if public_api_key:
            if not x_bot_key or x_bot_key != public_api_key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        _rate_limit(bot_id, body.org_id)
        
        # Check if user has already submitted a lead in this session
        has_submitted_lead = False
        if body.session_id:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select 1 from leads where session_id=%s and org_id=%s and bot_id=%s limit 1",
                        (body.session_id, normalize_org_id(body.org_id), bot_id)
                    )
                    if cur.fetchone():
                        has_submitted_lead = True
            except Exception as e:
                print(f"Error checking lead submission: {e}")
        
        # Sales intent detection for sales bots
        _is_sales_bot = (behavior or '').strip().lower() == 'sales'
        if _is_sales_bot and not has_submitted_lead:
            msg = body.message.strip()
            sales_intent = _detect_sales_intent(msg)
            if sales_intent.get('is_sales') and sales_intent.get('confidence', 0.0) >= 0.6:
                base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
                form_url = f"{base}/api/form/lead/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
                
                response_text = f"I'd be happy to help! Please fill out our [enquiry form]({form_url}) so we can better understand your needs and connect you with the right person."
                
                def gen_sales_response():
                    yield f"data: {response_text}\n\n"
                    yield "event: end\n\n"
                
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, sales_intent.get('confidence', 0.0), False)
                return StreamingResponse(gen_sales_response(), media_type="text/event-stream")

        # Smart booking intent detection for appointment bots
        _is_appointment_bot = (behavior or '').strip().lower() == 'appointment'
        _is_booking_query = False
        
        if _is_appointment_bot:
            import re
            msg = body.message.strip()
            
            # Get conversation history for context-aware detection
            history = _get_conversation_history(conn, body.session_id, body.org_id, bot_id, max_messages=10)
            
            # Hybrid intent detection (regex + LLM for ambiguous cases)
            intent_result = _hybrid_intent_detection(msg, history)
            
            # Debug logging
            print(f"[INTENT DEBUG] Message: '{msg}'")
            print(f"[INTENT DEBUG] Result: is_booking={intent_result.get('is_booking')}, action={intent_result.get('action')}, confidence={intent_result.get('confidence')}")
            
            # Set flag to determine if this is a booking query
            _is_booking_query = intent_result.get('is_booking', False)
            
            # Only handle booking intents with the smart system
            if _is_booking_query:
                # Check if message contains an ID - if so, skip generic intent response and process the ID
                has_id_global = bool(re.search(r"\b(?:appointment|id)\s*[:#]?\s*\d+\b", msg, re.IGNORECASE))
                
                if not has_id_global:
                    base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
                    form_url = f"{base}/api/form/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
                    res_form_url = f"{base}/api/reschedule/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
                    
                    # Determine intent type and map to response key
                    intent_type = intent_result.get('action', 'book')
                    if intent_type == 'book':
                        intent_type = 'new_booking'
                    elif intent_type == 'status':
                        intent_type = 'check_status'
                        
                    lang = intent_result.get('language', 'en')
                    # print(f"[LANGUAGE DEBUG] Detected language: {lang}")
                    
                    # Multi-language responses with booking form links (same as non-streaming)
                    responses = {
                        'new_booking': {
                            'en': f"I'd be happy to help you book an appointment! Please use our [booking form]({form_url}) to see available time slots and choose a convenient time.",
                            'hi': f"मुझे आपकी अपॉइंटमेंट बुक करने में मदद करके खुशी होगी! कृपया उपलब्ध समय देखने के लिए हमारा [बुकिंग फॉर्म]({form_url}) उपयोग करें।",
                            'ta': f"உங்கள் சந்திப்பை பதிவு செய்ய நான் உதவ மகிழ்ச்சியாக உள்ளேன்! கிடைக்கும் நேர இடைவெளிகளைப் பார்க்க எங்கள் [பதிவு படிவத்தை]({form_url}) பயன்படுத்தவும்.",
                            'te': f"మీ అపాయింట్మెంట్ బుక్ చేయడానికి నేను సంతోషంగా సహాయం చేస్తాను! అందుబాటులో ఉన్న సమయ స్లాట్లను చూడటానికి మా [బుకింగ్ ఫారమ్]({form_url}) ఉపయోగించండి.",
                            'kn': f"ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಬುಕ್ ಮಾಡಲು ನಾನು ಸಹಾಯ ಮಾಡಲು ಸಂತೋಷಪಡುತ್ತೇನೆ! ಲಭ್ಯವಿರುವ ಸಮಯ ಸ್ಲಾಟ್ಗಳನ್ನು ನೋಡಲು ನಮ್ಮ [ಬುಕಿಂಗ್ ಫಾರ್ಮ್]({form_url}) ಬಳಸಿ.",
                            'ml': f"നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് ബുക്ക് ചെയ്യാൻ സഹായിക്കുന്നതിൽ എനിക്ക് സന്തോഷമുണ്ട്! ലഭ്യമായ സമയ സ്ലോട്ടുകൾ കാണാൻ ഞങ്ങളുടെ [ബുക്കിംഗ് ഫോം]({form_url}) ഉപയോഗിക്കുക.",
                            'bn': f"আপনার অ্যাপয়েন্টমেন্ট বুক করতে সাহায্য করে আমি খুশি! উপলব্ধ সময় স্লট দেখতে আমাদের [বুকিং ফর্ম]({form_url}) ব্যবহার করুন।",
                            'mr': f"तुमची भेट बुक करण্यास मदत करण्यात मला आनंद होईल! उपलब्ध वेळ स्लॉट पाहण्यासाठी आमचा [बुकिंग फॉर्म]({form_url}) वापरा.",
                            'gu': f"તમારી મુલાકાત બુક કરવામાં મદદ કરીને મને આનંદ થશે! ઉપલબ્ધ સમય સ્લોટ જોવા માટે અમારા [બુકિંગ ફોર્મ]({form_url}) નો ઉપયોગ કરો.",
                            'pa': f"ਤੁਹਾਡੀ ਮੁਲਾਕਾਤ ਬੁੱਕ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰਕੇ ਮੈਨੂੰ ਖੁਸ਼ੀ ਹੋਵੇਗੀ! ਉਪਲਬਧ ਸਮਾਂ ਸਲਾਟ ਦੇਖਣ ਲਈ ਸਾਡੇ [ਬੁਕਿੰਗ ਫਾਰਮ]({form_url}) ਦੀ ਵਰਤੋਂ ਕਰੋ.",
                        },
                        'reschedule': {
                            'en': f"To reschedule your appointment, use the [reschedule form]({res_form_url}) to select a new time.",
                            'hi': f"अपनी अपॉइंटमेंट को रीशेड्यूल करने के लिए [रीशेड्यूल फॉर्म]({res_form_url}) का उपयोग करें और नया समय चुनें।",
                            'ta': f"உங்கள் சந்திப்பை மீண்டும் திட்டமிட [மறு அட்டவணை படிவம்]({res_form_url}) பயன்படுத்தி புதிய நேரத்தைத் தேர்ந்தெடுக்கவும்.",
                            'te': f"మీ అపాయింట్మెంట్‌ను రీషెడ్యూల్ చేయడానికి [రీషెడ్యూల్ ఫారమ్]({res_form_url}) ఉపయోగించి కొత్త సమయాన్ని ఎంచుకోండి.",
                            'kn': f"ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಮರುನಿಗದಿಗೆ [ಮರುನಿಗದಿ ಫಾರ್ಮ್]({res_form_url}) ಬಳಸಿ ಮತ್ತು ಹೊಸ ಸಮಯವನ್ನು ಆಯ್ಕೆಮಾಡಿ.",
                            'ml': f"നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് റീഷെഡ്യൂൾ ചെയ്യാൻ [റീഷെഡ്യൂൾ ഫോം]({res_form_url}) ഉപയോഗിച്ച് പുതിയ സമയം തിരഞ്ഞെടുക്കുക.",
                            'bn': f"আপনার অ্যাপয়েন্টমেন্ট রিশিডিউল করতে [রিশিডিউল ফর্ম]({res_form_url}) ব্যবহার করে নতুন সময় নির্বাচন করুন।",
                            'mr': f"तुमची भेट रीशेड्यूल करण्यासाठी [रीशेड्यूल फॉर्म]({res_form_url}) वापरून नवीन वेळ निवडा.",
                            'gu': f"તમારી મુલાકાતને રીશેડ્યૂલ કરવા [રીશેડ્યૂલ ફોર્મ]({res_form_url}) નો ઉપયોગ કરીને નવો સમય પસંદ કરો.",
                            'pa': f"ਆਪਣੀ ਮੁਲਾਕਾਤ ਨੂੰ ਰੀਸ਼ਡਿਊਲ ਕਰਨ ਲਈ [ਰੀਸ਼ਡਿਊਲ ਫਾਰਮ]({res_form_url}) ਵਰਤੋਂ ਅਤੇ ਨਵਾਂ ਸਮਾਂ ਚੁਣੋ.",
                        },
                        'cancel': {
                            'en': "I can help you cancel your appointment. Please provide your appointment ID (e.g., 'appointment 123' or 'ID: 123').",
                            'hi': "मैं आपकी अपॉइंटमेंट रद्द करने में मदद कर सकता हूं। कृपया अपनी अपॉइंटमेंट ID बताएं (जैसे, 'अपॉइंटमेंट 123' या 'ID: 123')।",
                            'ta': "உங்கள் சந்திப்பை ரத்து செய்ய நான் உதவ முடியும். உங்கள் அப்பாயின்ட்மென்ட் ID வழங்கவும் (எ.கா., 'அப்பாயின்ட்மென்ட் 123' அல்லது 'ID: 123').",
                            'te': "మీ అపాయింట్మెంట్ను రద్దు చేయడానికి నేను సహాయం చేయగలను. దయచేసి మీ అపాయింట్మెంట్ ID అందించండి (ఉదా., 'అపాయింట్మెంట్ 123' లేదా 'ID: 123').",
                            'kn': "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ರದ್ದುಗೊಳಿಸಲು ನಾನು ಸಹಾಯ ಮಾಡಬಲ್ಲೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ID ನೀಡಿ (ಉದಾ., 'ಅಪಾಯಿಂಟ್ಮೆಂಟ್ 123' ಅಥವಾ 'ID: 123').",
                            'ml': "നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് റദ്ദാക്കാൻ എനിക്ക് സഹായിക്കാം. ദയവായി നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് ID നൽകുക (ഉദാ., 'അപ്പോയിന്റ്മെന്റ് 123' അല്ലെങ്കിൽ 'ID: 123').",
                            'bn': "আপনার অ্যাপয়েন্টমেন্ট বাতিল করতে আমি সাহায্য করতে পারি। অনুগ্রহ করে আপনার অ্যাপয়েন্টমেন্ট ID প্রদান করুন (যেমন, 'অ্যাপয়েন্টমেন্ট 123' বা 'ID: 123')।",
                            'mr': "तुमची भेट रद्द करण्यात मी मदत करू शकतो. कृपया तुमचा अपॉइंटमेंट ID द्या (उदा., 'अपॉइंटमेंट 123' किंवा 'ID: 123').",
                            'gu': "હું તમારી મુલાકાત રદ કરવામાં મદદ કરી શકું છું. કૃપા કરીને તમારી એપોઇન્ટમેન્ટ ID આપો (દા.ત., 'એપોઇન્ટમેન્ટ 123' અથવા 'ID: 123').",
                            'pa': "ਮੈਂ ਤੁਹਾਡੀ ਮੁਲਾਕਾਤ ਰੱਦ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣੀ ਮੁਲਾਕਾਤ ID ਦਿਓ (ਜਿਵੇਂ, 'ਮੁਲਾਕਾਤ 123' ਜਾਂ 'ID: 123').",
                        },
                        'check_status': {
                            'en': "I can check your appointment status. Please provide your appointment ID or email address.",
                            'hi': "मैं आपकी अपॉइंटमेंट की स्थिति जांच सकता हूं। कृपया अपनी अपॉइंटमेंट ID या ईमेल पता बताएं।",
                            'ta': "உங்கள் சந்திப்பு நிலையை நான் சரிபார்க்க முடியும். உங்கள் அப்பாயின்ட்மென்ட் ID அல்லது மின்னஞ்சல் முகவரியை வழங்கவும்.",
                            'te': "మీ అపాయింట్మెంట్ స్థితిని నేను తనిఖీ చేయగలను. దయచేసి మీ అపాయింట్మెంట్ ID లేదా ఇమెయిల్ చిరునామా అందించండి.",
                            'kn': "ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ಸ್ಥಿತಿಯನ್ನು ನಾನು ಪರಿಶೀಲಿಸಬಹುದು. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಅಪಾಯಿಂಟ್ಮೆಂಟ್ ID ಅಥವಾ ಇಮೇಲ್ ವಿಳಾಸವನ್ನು ನೀಡಿ.",
                            'ml': "നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് സ്ഥിതി എനിക്ക് പരിശോധിക്കാം. ദയവായി നിങ്ങളുടെ അപ്പോയിന്റ്മെന്റ് ID അല്ലെങ്കിൽ ഇമെയിൽ വിലാസം നൽകുക.",
                            'bn': "আমি আপনার অ্যাপয়েন্টমেন্ট স্ট্যাটাস চেক করতে পারি। অনুগ্রহ করে আপনার অ্যাপয়েন্টমেন্ট ID বা ইমেইল ঠিকানা প্রদান করুন।",
                            'mr': "मी तुमच्या भेटीची स्थिती तपासू शकतो. कृपया तुमचा अपॉइंटमेंट ID किंवा ईमेल पत्ता द्या.",
                            'gu': "હું તમારી મુલાકાતની સ્થિતિ તપાસી શકું છું. કૃપા કરીને તમારી એપોઇન્ટમેન્ટ ID અથવા ઇમેઇલ સરનામું આપો.",
                            'pa': "ਮੈਂ ਤੁਹਾਡੀ ਮੁਲਾਕਾਤ ਦੀ ਸਥਿਤੀ ਜਾਂਚ ਸਕਦਾ ਹਾਂ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣੀ ਮੁਲਾਕਾਤ ID ਜਾਂ ਈਮੇਲ ਪਤਾ ਦਿਓ।",
                        }
                    }
                    
                    response_text = responses.get(intent_type, {}).get(lang, responses.get(intent_type, {}).get('en', f"Please use our [booking form]({form_url}) to schedule your appointment."))
                    
                    def gen_response():
                        yield f"data: {response_text}\n\n"
                        yield "event: end\n\n"
                    
                    _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, intent_result.get('confidence', 0.0), False)
                return StreamingResponse(gen_response(), media_type="text/event-stream")
        
        # If message contains an explicit appointment ID, handle status/cancel/reschedule immediately
        if _is_appointment_bot:
            import re
            msg = body.message.strip()
            try:
                m_id = re.search(r"\b(?:appointment|id)\s*[:#]?\s*(\d+)\b", msg, re.IGNORECASE)
                ap_id = int(m_id.group(1)) if m_id else None
            except Exception:
                ap_id = None
            print(f"[STREAM DEBUG] Detected ap_id (early): {ap_id}")
            if ap_id:
                base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
                form_url = f"{base}/api/form/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
                res_form_url = f"{base}/api/reschedule/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
                def gen_status(text):
                    lines = str(text).splitlines() or [str(text)]
                    for ln in lines:
                        yield f"data: {ln}\n"
                    yield "\n"
                    yield "event: end\n\n"
                try:
                    _ensure_oauth_table(conn)
                    _ensure_booking_settings_table(conn)
                    _ensure_audit_logs_table(conn)
                    
                    with conn.cursor() as cur:
                        # Check both bot_appointments and bookings tables
                        cur.execute(
                            "select external_event_id, start_iso, end_iso, status, 'bot_appointments' as source from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                            (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id),
                        )
                        row = cur.fetchone()
                        if not row:
                            cur.execute(
                                """
                                select calendar_event_id, 
                                       (booking_date::text || 'T' || start_time::text) as start_iso,
                                       (booking_date::text || 'T' || end_time::text) as end_iso,
                                       status,
                                       'bookings' as source
                                from bookings 
                                where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s
                                """,
                                (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id),
                            )
                            row = cur.fetchone()
                    if not row:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return StreamingResponse(gen_status(f"Appointment ID {ap_id} not found."), media_type="text/event-stream")
                    ev_id, cur_si, cur_ei, cur_st = row[0], row[1], row[2], row[3]
                    
                    # Build Google service
                    svc = None
                    cal_id = None
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                            )
                            c = cur.fetchone()
                        if c:
                            cal_id, at_enc, rt_enc, exp = c
                            from app.services.calendar_google import _decrypt, build_service_from_tokens, get_event_oauth, delete_event_oauth
                            at = _decrypt(at_enc) if at_enc else None
                            rt = _decrypt(rt_enc) if rt_enc else None
                            svc = build_service_from_tokens(at or "", rt, exp)
                    except Exception as e:
                        print(f"Error fetching Google tokens: {e}")
                    
                    lw = msg.lower()
                    
                    # Cancel
                    if ("cancel" in lw):
                        if ((cur_st or '').lower() == 'completed'):
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                            return StreamingResponse(gen_status("Completed appointment cannot be cancelled."), media_type="text/event-stream")
                        ok = False
                        if svc:
                            try:
                                ok = delete_event_oauth(svc, cal_id or "primary", ev_id)
                            except Exception as e:
                                print(f"Error cancelling Google event: {e}")
                        if not svc:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return StreamingResponse(gen_status("Calendar service unavailable."), media_type="text/event-stream")
                        if not ok:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return StreamingResponse(gen_status("Cancel failed."), media_type="text/event-stream")
                        with conn.cursor() as cur:
                            cur.execute("select 1 from bookings where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s", (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id))
                            in_bookings = cur.fetchone()
                            if in_bookings:
                                cur.execute("update bookings set status=%s, cancelled_at=now(), updated_at=now() where id=%s", ("cancelled", ap_id))
                            else:
                                cur.execute("update bot_appointments set status=%s, updated_at=now() where id=%s", ("cancelled", ap_id))
                        _log_audit(conn, body.org_id, bot_id, ap_id, "cancel", {})
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return StreamingResponse(gen_status(f"Cancelled appointment ID: {ap_id}"), media_type="text/event-stream")
                    
                    # Reschedule
                    if ("reschedule" in lw) or ("change" in lw):
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                        return StreamingResponse(gen_status("Use the [reschedule form](" + res_form_url + ") to reschedule your appointment."), media_type="text/event-stream")
                    
                    # Status details
                    g_event = None
                    if svc and ev_id:
                        try:
                            g_event = get_event_oauth(svc, cal_id or "primary", ev_id)
                        except Exception as e:
                            print(f"Error fetching Google Event: {e}")
                    msgs = []
                    if g_event:
                        summary = g_event.get('summary', 'Appointment')
                        start = g_event.get('start', {}).get('dateTime', g_event.get('start', {}).get('date'))
                        end = g_event.get('end', {}).get('dateTime', g_event.get('end', {}).get('date'))
                        link = g_event.get('htmlLink')
                        meet = g_event.get('hangoutLink')
                        desc = g_event.get('description')
                        try:
                            import datetime as _dt
                            dt_start = _dt.datetime.fromisoformat(start.replace('Z', '+00:00'))
                            dt_end = _dt.datetime.fromisoformat(end.replace('Z', '+00:00'))
                            time_str = f"{dt_start.strftime('%B %d, %Y at %I:%M %p')} - {dt_end.strftime('%I:%M %p')}"
                        except:
                            time_str = f"{start} to {end}"
                        msg_text = f"**{summary}**\n\n🕒 **Time:** {time_str}\n✅ **Status:** {g_event.get('status', 'confirmed')}"
                        if meet:
                            msg_text += f"\n📹 **Join Meeting:** [Google Meet]({meet})"
                        if link:
                            msg_text += f"\n📅 **Calendar Link:** [View Event]({link})"
                        if desc:
                            msg_text += f"\n📝 **Description:** {desc}"
                        msgs.append(msg_text)
                    else:
                        msgs.append(f"Appointment {ap_id}: {cur_si} to {cur_ei}. Status: {cur_st}")
                    status_text = "\n\n".join(msgs)
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                    return StreamingResponse(gen_status(status_text), media_type="text/event-stream")
                except Exception:
                    def gen_err():
                        yield "data: Error handling appointment\n\n"
                        yield "event: end\n\n"
                    return StreamingResponse(gen_err(), media_type="text/event-stream")
        
        # Old booking logic - only run if appointment bot AND booking intent detected
        import re
        msg_raw = (body.message or '').strip()
        low = msg_raw.lower()
        has_time = bool(
            re.search(r"\d{4}-\d{2}-\d{2}", msg_raw) or
            re.search(r"\b(today|tomorrow|mon|tue|wed|thu|fri|sat|sun)\b", low) or
            re.search(r"\b(\d{1,2}:\d{2})\b", msg_raw) or
            re.search(r"\b\d{1,2}\s*(am|pm)\b", low)
        )
        has_action = bool(re.search(r"\b(book|schedule|reschedule|cancel|change)\b", low))
        has_id = bool(re.search(r"\b(?:appointment|id)\s*[:#]?\s*\d+\b", low))
        
        # Only run old booking system if: 1) it's an appointment bot, 2) booking intent detected, 3) has time/action/id
        if _is_appointment_bot and _is_booking_query and (has_time or has_action or has_id):
            import re
            msg = body.message.strip()
            base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
            form_url = f"{base}/api/form/{bot_id}?org_id={body.org_id}" + (f"&bot_key={public_api_key}" if public_api_key else "")
            def _norm_month(s: str) -> int:
                m = s.lower()
                d = {
                    'jan':1,'january':1,'feb':2,'february':2,'mar':3,'march':3,'apr':4,'april':4,'may':5,'jun':6,'june':6,'jul':7,'july':7,'aug':8,'august':8,'sep':9,'sept':9,'september':9,'oct':10,'october':10,'nov':11,'november':11,'dec':12,'december':12
                }
                return d.get(m,0)
            def _norm_weekday(s: str) -> int:
                m = s.lower()
                d = {'sunday':6,'sun':6,'monday':0,'mon':0,'tuesday':1,'tue':1,'tues':1,'wednesday':2,'wed':2,'thursday':3,'thu':3,'thur':3,'thurs':3,'friday':4,'fri':4,'saturday':5,'sat':5}
                return d.get(m,-1)
            def _parse_natural(s: str):
                from datetime import datetime, timedelta
                now = datetime.now()
                base_date = None
                m = re.search(r"\b(today|tomorrow)\b", s, re.IGNORECASE)
                if m:
                    w = m.group(1).lower()
                    base_date = now.date() if w == 'today' else (now + timedelta(days=1)).date()
                if base_date is None:
                    mwd = re.search(r"\b(next\s+)?(mon(day)?|tue(s|sday)?|wed(nesday)?|thu(rs|rsday)?|fri(day)?|sat(urday)?|sun(day)?)\b", s, re.IGNORECASE)
                    if mwd:
                        is_next = bool(mwd.group(1))
                        wd = _norm_weekday(mwd.group(2))
                        if wd >= 0:
                            cur = now.weekday()
                            delta = (wd - cur) % 7
                            if delta == 0:
                                delta = 7 if is_next else 0
                            base_date = (now + timedelta(days=delta)).date()
                tm = re.search(r"\b(\d{1,2})(?:\:(\d{2}))?\s*(am|pm)\b", s, re.IGNORECASE)
                if base_date and tm:
                    hh = int(tm.group(1)) % 12
                    mm = int(tm.group(2) or '00')
                    ap = tm.group(3).lower()
                    if ap == 'pm':
                        hh += 12
                    start_dt = datetime.combine(base_date, datetime.min.time()).replace(hour=hh, minute=mm)
                    end_dt = start_dt + timedelta(minutes=30)
                    return start_dt.isoformat(), end_dt.isoformat()
                return None
            try:
                m_id = re.search(r"\b(?:appointment|id)\s*[:#]?\s*(\d+)\b", msg, re.IGNORECASE)
                ap_id = int(m_id.group(1)) if m_id else None
            except Exception:
                ap_id = None
            if ap_id:
                def gen_status(text):
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                try:
                    _ensure_oauth_table(conn)
                    _ensure_booking_settings_table(conn)
                    _ensure_audit_logs_table(conn)
                    
                    # Debug logging for streaming endpoint
                    print(f"[STREAM DEBUG] Looking for appointment ID: {ap_id}")
                    print(f"[STREAM DEBUG] org_id (raw): {body.org_id}")
                    print(f"[STREAM DEBUG] org_id (normalized): {normalize_org_id(body.org_id)}")
                    print(f"[STREAM DEBUG] bot_id: {bot_id}")
                    
                    with conn.cursor() as cur:
                        # Check both bot_appointments and bookings tables
                        # First try bot_appointments (chat-created appointments)
                        cur.execute(
                            "select external_event_id, start_iso, end_iso, status, 'bot_appointments' as source from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                            (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id),
                        )
                        row = cur.fetchone()
                        
                        # If not found, try bookings table (form-created bookings)
                        if not row:
                            print(f"[STREAM DEBUG] Not in bot_appointments, checking bookings table...")
                            cur.execute(
                                """
                                select calendar_event_id, 
                                       (booking_date::text || 'T' || start_time::text) as start_iso,
                                       (booking_date::text || 'T' || end_time::text) as end_iso,
                                       status,
                                       'bookings' as source
                                from bookings 
                                where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s
                                """,
                                (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id),
                            )
                            row = cur.fetchone()
                            if row:
                                print(f"[STREAM DEBUG] Found in bookings table!")
                    if not row:
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                        return StreamingResponse(gen_status(f"Appointment ID {ap_id} not found."), media_type="text/event-stream")
                    ev_id, cur_si, cur_ei, cur_st = row[0], row[1], row[2], row[3]
                    
                    # 1. Fetch Google Service (common for all ops)
                    svc = None
                    cal_id = None
                    try:
                        with conn.cursor() as cur:
                            cur.execute(
                                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                            )
                            c = cur.fetchone()
                        
                        if c:
                            cal_id, at_enc, rt_enc, exp = c
                            from app.services.calendar_google import _decrypt, build_service_from_tokens, get_event_oauth, delete_event_oauth
                            at = _decrypt(at_enc) if at_enc else None
                            rt = _decrypt(rt_enc) if rt_enc else None
                            svc = build_service_from_tokens(at or "", rt, exp)
                    except Exception as e:
                        print(f"Error fetching Google tokens: {e}")

                    lw = msg.lower()

                    # 2. Handle Cancel
                    if ("cancel" in lw):
                        if ((cur_st or '').lower() == 'completed'):
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                            return StreamingResponse(gen_status("Completed appointment cannot be cancelled."), media_type="text/event-stream")
                        
                        ok = False
                        if svc:
                            try:
                                ok = delete_event_oauth(svc, cal_id or "primary", ev_id)
                            except Exception as e:
                                print(f"Error cancelling Google event: {e}")
                        
                        # Even if Google cancel fails (or no svc), we might want to cancel in DB? 
                        # Original logic required 'ok' to be true. Let's stick to that if svc exists.
                        # If svc is None, we can't cancel on Google, so maybe fail?
                        # But if no Google Calendar connected, we should still allow cancelling local DB?
                        # Original logic: if not svc: return "Calendar service unavailable."
                        # So I should follow that strictly.
                        
                        if not svc:
                             _ensure_usage_table(conn)
                             _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                             return StreamingResponse(gen_status("Calendar service unavailable."), media_type="text/event-stream")

                        if not ok:
                            _ensure_usage_table(conn)
                            _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                            return StreamingResponse(gen_status("Cancel failed."), media_type="text/event-stream")
                        
                        with conn.cursor() as cur:
                            cur.execute("select 1 from bookings where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s", (ap_id, normalize_org_id(body.org_id), body.org_id, bot_id))
                            in_bookings = cur.fetchone()
                            if in_bookings:
                                cur.execute("update bookings set status=%s, cancelled_at=now(), updated_at=now() where id=%s", ("cancelled", ap_id))
                            else:
                                cur.execute("update bot_appointments set status=%s, updated_at=now() where id=%s", ("cancelled", ap_id))
                        _log_audit(conn, body.org_id, bot_id, ap_id, "cancel", {})
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                        return StreamingResponse(gen_status(f"Cancelled appointment ID: {ap_id}"), media_type="text/event-stream")

                    # 3. Handle Reschedule
                    if ("reschedule" in lw) or ("change" in lw):
                        _ensure_usage_table(conn)
                        _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                        return StreamingResponse(gen_status("Use the [reschedule form](" + res_form_url + ") to reschedule your appointment."), media_type="text/event-stream")

                    # 4. Handle Status (fetch rich details)
                    g_event = None
                    if svc and ev_id:
                        try:
                            g_event = get_event_oauth(svc, cal_id or "primary", ev_id)
                        except Exception as e:
                            print(f"Error fetching Google Event: {e}")
                    
                    # Format response
                    msgs = []
                    if g_event:
                        summary = g_event.get('summary', 'Appointment')
                        start = g_event.get('start', {}).get('dateTime', g_event.get('start', {}).get('date'))
                        end = g_event.get('end', {}).get('dateTime', g_event.get('end', {}).get('date'))
                        link = g_event.get('htmlLink')
                        meet = g_event.get('hangoutLink')
                        desc = g_event.get('description')
                        
                        # Parse dates
                        try:
                            import datetime as _dt
                            dt_start = _dt.datetime.fromisoformat(start.replace('Z', '+00:00'))
                            dt_end = _dt.datetime.fromisoformat(end.replace('Z', '+00:00'))
                            time_str = f"{dt_start.strftime('%B %d, %Y at %I:%M %p')} - {dt_end.strftime('%I:%M %p')}"
                        except:
                            time_str = f"{start} to {end}"
                        
                        msg = f"**{summary}**\n\n🕒 **Time:** {time_str}\n✅ **Status:** {g_event.get('status', 'confirmed')}"
                        if meet:
                            msg += f"\n📹 **Join Meeting:** [Google Meet]({meet})"
                        if link:
                            msg += f"\n📅 **Calendar Link:** [View Event]({link})"
                        if desc:
                            msg += f"\n📝 **Description:** {desc}"
                        msgs.append(msg)
                    else:
                        msgs.append(f"Appointment {ap_id}: {cur_si} to {cur_ei}. Status: {cur_st}")
                    
                    status_text = "\n\n".join(msgs)
                    _ensure_usage_table(conn)
                    _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
                    return StreamingResponse(gen_status(status_text), media_type="text/event-stream")

                except Exception:
                    def gen_err():
                        yield "data: Error handling appointment\n\n"
                        yield "event: end\n\n"
                    return StreamingResponse(gen_err(), media_type="text/event-stream")
            # Check if this is a new booking request (not reschedule/cancel) - show form directly
            lowmsg = msg.lower()
            is_new_booking = bool(re.search(r"\b(book|schedule|appointment)\b", lowmsg)) and not bool(re.search(r"\b(cancel|reschedule|change|status)\b", lowmsg))
            if not ap_id and is_new_booking:
                def gen_form():
                    yield f"data: Please use the [booking form]({form_url}) to schedule your appointment. It shows available time slots and you can select a convenient time.\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                return StreamingResponse(gen_form(), media_type="text/event-stream")
            patt = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})(?:[T\s](?P<start>\d{2}:\d{2})(?:\s*(?:to|-|until)\s*(?P<end>\d{2}:\d{2}))?)", re.IGNORECASE)
            m0 = patt.search(msg)
            si = None
            ei = None
            if m0:
                d = m0.group('date')
                st = m0.group('start')
                en = m0.group('end') or None
                if not en:
                    try:
                        sd = f"{d}T{st}:00"
                        from datetime import datetime, timedelta
                        start_dt = datetime.fromisoformat(sd)
                        end_dt = start_dt + timedelta(minutes=30)
                        ei = end_dt.isoformat()
                    except Exception:
                        ei = f"{d}T{st}:00"
                else:
                    ei = f"{d}T{en}:00"
                si = f"{d}T{st}:00"
            else:
                parsed = _parse_natural(msg)
                if parsed:
                    si, ei = parsed
            key = f"{body.org_id}:{bot_id}"
            st = _SESSION_STATE[key]
            if not si and st.get('start_iso'):
                si = st.get('start_iso')
            if not ei and st.get('end_iso'):
                ei = st.get('end_iso')
            if si:
                st['start_iso'] = si
            if ei:
                st['end_iso'] = ei
            _ensure_oauth_table(conn)
            _ensure_booking_settings_table(conn)
            with conn.cursor() as cur:
                cur.execute(
                    "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                    (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
                )
                row = cur.fetchone()
                cal_id, at_enc, rt_enc, tok_exp = (row[0] if row else None), (row[1] if row else None), (row[2] if row else None), (row[3] if row else None)
                cur.execute(
                    "select timezone, slot_duration_minutes, capacity_per_slot, required_user_fields from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                    (normalize_org_id(body.org_id), body.org_id, bot_id),
                )
                bs = cur.fetchone()
            tzv = bs[0] if bs else None
            slotm = int(bs[1]) if bs and bs[1] else 30
            capacity = int(bs[2]) if bs and bs[2] else 1
            aw = None; min_notice=None; max_future=None
            try:
                cur.execute(
                    "select timezone, available_windows, min_notice_minutes, max_future_days from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                    (normalize_org_id(org_id), org_id, bot_id),
                )
                more = cur.fetchone()
                if more:
                    tzv = more[0] or tzv
                import json
                aw = None if (not more or more[1] is None) else (more[1] if isinstance(more[1], list) else json.loads(more[1]) if isinstance(more[1], str) else None)
                min_notice = int(more[2]) if more and more[2] else None
                max_future = int(more[3]) if more and more[3] else None
            except Exception:
                aw = None; min_notice=None; max_future=None
            try:
                rfraw = bs[3] if bs else None
                _json = __import__("json")
                required_fields = rfraw if isinstance(rfraw, list) else (_json.loads(rfraw) if isinstance(rfraw, str) else [])
            except Exception:
                required_fields = []
            svc = None
            try:
                from app.services.calendar_google import _decrypt, _encrypt, build_service_from_tokens, list_events_oauth, create_event_oauth, refresh_access_token
                from datetime import datetime, timedelta, timezone
                
                at = _decrypt(at_enc) if at_enc else None
                rt = _decrypt(rt_enc) if rt_enc else None
                
                # Proactive refresh if expired or expiring soon (within 5 mins)
                now_utc = datetime.now(timezone.utc)
                should_refresh = False
                if not at:
                    should_refresh = True
                elif tok_exp:
                    # tok_exp from DB might be offset-naive or offset-aware depending on driver
                    # psycopg returns offset-aware if column is timestamptz
                    if tok_exp.tzinfo is None:
                        tok_exp = tok_exp.replace(tzinfo=timezone.utc)
                    if now_utc > (tok_exp - timedelta(minutes=5)):
                        should_refresh = True
                
                if should_refresh and rt:
                    print(f"🔄 Token expired or missing, refreshing for bot {bot_id}")
                    new_toks = refresh_access_token(rt)
                    if new_toks and new_toks.get("access_token"):
                        at = new_toks["access_token"]
                        new_rt = new_toks.get("refresh_token")
                        if new_rt: 
                            rt = new_rt
                        
                        # Update DB
                        try:
                            enc_at = _encrypt(at)
                            enc_rt = _encrypt(rt) if rt else None
                            new_exp = new_toks.get("expiry")
                            with conn.cursor() as cur:
                                cur.execute(
                                    """
                                    update bot_calendar_oauth 
                                    set access_token_enc=%s, refresh_token_enc=coalesce(%s, refresh_token_enc), token_expiry=%s, updated_at=now()
                                    where org_id=%s and bot_id=%s and provider='google'
                                    """,
                                    (enc_at, enc_rt, new_exp, normalize_org_id(body.org_id), bot_id)
                                )
                        except Exception as e:
                            print(f"⚠ Failed to update refreshed token in DB: {e}")
                
                svc = build_service_from_tokens(at, rt, tok_exp)
            except Exception:
                svc = None
            if not si or not ei:
                def gen_need_time():
                    _link = res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url
                    text = "Could not parse date/time. Try formats like '2025-12-06 15:30' or 'tomorrow at 3pm for 30 minutes'. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + _link + ")"
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_need_time(), media_type="text/event-stream")
            if not svc:
                def gen_need_cal():
                    text = "Calendar not connected. Please connect Google Calendar in the dashboard. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")"
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_need_cal(), media_type="text/event-stream")
            import datetime as _dt
            tmn = _dt.datetime.fromisoformat(si)
            tmx = _dt.datetime.fromisoformat(ei)
            items = list_events_oauth(svc, cal_id or "primary", tmn.isoformat(), tmx.isoformat())
            info = {}
            try:
                em = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", msg)
                if em:
                    info["email"] = em.group(0)
                ph = re.search(r"\+?\d[\d \-]{7,}\d", msg)
                if ph:
                    import re as _re
                    info["phone"] = _re.sub(r"\D", "", ph.group(0))
                nm = re.search(r"(?:my name is|i am|this is)\s+([A-Za-z][A-Za-z .'-]{1,50})", msg, re.IGNORECASE)
                if nm:
                    info["name"] = nm.group(1).strip()
                nt = re.search(r"(?:purpose|note|reason)[:\-]\s*(.+)$", msg, re.IGNORECASE)
                if nt:
                    info["notes"] = nt.group(1).strip()
            except Exception:
                pass
            prev = st.get('info') or {}
            prev.update(info)
            st['info'] = prev
            missing = [f for f in (required_fields or []) if not prev.get(f)]
            if missing:
                def gen_need_fields():
                    text = ("Please provide: " + ", ".join(missing) + ". Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")")
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_need_fields(), media_type="text/event-stream")
            occ = len(items) if items else 0
            with conn.cursor() as cur:
                cur.execute(
                    "select count(*) from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso=%s and end_iso=%s and status in ('scheduled','booked')",
                    (normalize_org_id(body.org_id), body.org_id, bot_id, si, ei),
                )
                occ_db = int(cur.fetchone()[0])
            if max(occ, occ_db) >= capacity:
                def gen_busy():
                    text = "That time is unavailable. Please suggest another time. Or use the [" + ("reschedule form" if (intent_result and intent_result.get('action') == 'reschedule') else "booking form") + "](" + (res_form_url if (intent_result and intent_result.get('action') == 'reschedule') else form_url) + ")"
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_busy(), media_type="text/event-stream")
            ext_id = None
            try:
                attns = ([prev.get("email")] if prev.get("email") else None)
                ext_id = create_event_oauth(svc, cal_id or "primary", "Appointment", si, ei, attns, tzv)
            except Exception:
                ext_id = None
            if not ext_id:
                def gen_fail():
                    text = "Calendar booking failed. Please try again after reconnecting Google Calendar."
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, True)
                return StreamingResponse(gen_fail(), media_type="text/event-stream")
            
            # Ensure the appointments table exists before inserting
            _ensure_appointments_table(conn)
            
            apid = None
            
            # Debug logging for appointment creation
            print(f"[STREAM DEBUG] Creating appointment:")
            print(f"[STREAM DEBUG] org_id (raw): {body.org_id}")
            print(f"[STREAM DEBUG] org_id (normalized): {normalize_org_id(body.org_id)}")
            print(f"[STREAM DEBUG] bot_id: {bot_id}")
            print(f"[STREAM DEBUG] start_iso: {si}, end_iso: {ei}")
            
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json, status, external_event_id) values (%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                        (normalize_org_id(body.org_id), bot_id, "Appointment", si, ei, (__import__("json").dumps(attns) if attns else None), "booked", ext_id),
                    )
                    r = cur.fetchone()
                    apid = int(r[0]) if r else None
                    print(f"[STREAM DEBUG] Created appointment with ID: {apid}")
            except Exception as e:
                print(f"[STREAM DEBUG] ERROR creating appointment: {e}")
                import traceback
                traceback.print_exc()
                apid = None
            _SESSION_STATE[key] = {}
            def gen_ok():
                text = f"Booked your appointment for {si} to {ei}. ID: {apid}"
                yield f"data: {text}\n\n"
                yield "event: end\n\n"
            _ensure_usage_table(conn)
            _log_chat_usage(conn, body.org_id, bot_id, 1.0, False)
            return StreamingResponse(gen_ok(), media_type="text/event-stream")
        chunks = search_top_chunks(body.org_id, bot_id, body.message, settings.MAX_CONTEXT_CHUNKS)
        if not chunks:
            msg = body.message.strip().lower()
            wm = None
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "select welcome_message from chatbots where id=%s",
                        (bot_id,),
                    )
                    rwm = cur.fetchone()
                    wm = rwm[0] if rwm else None
            except Exception:
                wm = None
            is_greet = bool(msg) and (
                msg in {"hi", "hello", "hey", "hola", "hii"} or
                msg.startswith("hi ") or msg.startswith("hello ") or msg.startswith("hey ")
            )
            if is_greet:
                def gen_hi():
                    text = wm or "Hello! How can I help you?"
                    # Save greeting exchange to conversation history
                    if body.session_id:
                        try:
                            sconn = get_conn()
                            try:
                                _save_conversation_message(sconn, body.session_id, body.org_id, bot_id, "user", body.message)
                                _save_conversation_message(sconn, body.session_id, body.org_id, bot_id, "assistant", text)
                            finally:
                                sconn.close()
                        except Exception:
                            pass
                    yield f"data: {text}\n\n"
                    yield "event: end\n\n"
                _ensure_usage_table(conn)
                _log_chat_usage(conn, body.org_id, bot_id, 0.0, False)
                return StreamingResponse(gen_hi(), media_type="text/event-stream")
            def gen_fb():
                text = "I don't have that information."
                yield f"data: {text}\n\n"
                yield "event: end\n\n"
                try:
                    cconn = get_conn()
                    try:
                        _ensure_usage_table(cconn)
                        _log_chat_usage(cconn, body.org_id, bot_id, 0.0, True)
                    finally:
                        cconn.close()
                except Exception:
                    pass
            return StreamingResponse(gen_fb(), media_type="text/event-stream")

        context = "\n\n".join([c[0] for c in chunks])
        
        # Add context about lead submission to system prompt
        lead_context_prompt = ""
        if has_submitted_lead:
            lead_context_prompt = " The user has already submitted their details/enquiry form. Acknowledge this if relevant, and do not ask them to fill the form again unless explicitly requested."

        system = (
            (system_prompt + lead_context_prompt + " Keep responses short and informative.")
            if system_prompt
            else f"You are a {behavior} assistant. Use only the provided context. If the answer is not in context, say: \"I don't have that information.\"{lead_context_prompt} Keep responses short and informative."
        )
        user = f"Context:\n{context}\n\nQuestion:\n{body.message}"
        
        # Get conversation history for context
        history = _get_conversation_history(conn, body.session_id, body.org_id, bot_id, max_messages=8)

        def gen():
            full_response = ""
            try:
                # Build messages with conversation history
                messages = [{"role": "system", "content": system}]
                messages.extend(history)  # Add conversation history
                messages.append({"role": "user", "content": user})
                
                resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                temperature=0.2,
                messages=messages,
                stream=True,
            )
                buf = ""
                for evt in resp:
                    try:
                        content = evt.choices[0].delta.content
                    except Exception:
                        content = None
                    if content:
                        buf += content
                        full_response += content
                        import re as _re
                        while True:
                            m = _re.search(r"[ \t\n\.,!\?;:\)\]\}]", buf)
                            if not m:
                                break
                            idx = m.end()
                            seg = buf[:idx]
                            buf = buf[idx:]
                            yield f"data: {seg}\n\n"
                if buf:
                    yield f"data: {buf}\n\n"
                yield "event: end\n\n"
                
                # Save to conversation history after streaming completes
                if body.session_id and full_response:
                    try:
                        sconn = get_conn()
                        try:
                            _save_conversation_message(sconn, body.session_id, body.org_id, bot_id, "user", body.message)
                            _save_conversation_message(sconn, body.session_id, body.org_id, bot_id, "assistant", full_response)
                        finally:
                            sconn.close()
                    except Exception:
                        pass
                
                try:
                    cconn = get_conn()
                    try:
                        _ensure_usage_table(cconn)
                        from math import isfinite
                        simv = float(chunks[0][2])
                        if not isfinite(simv):
                            simv = 0.0
                        _log_chat_usage(cconn, body.org_id, bot_id, simv, False)
                    finally:
                        cconn.close()
                except Exception:
                    pass
            except Exception:
                from math import isfinite
                sim = float(chunks[0][2])
                if not isfinite(sim):
                    sim = 0.0
                text = "I don't have that information."
                yield f"data: {text}\n\n"
                yield "event: end\n\n"
                try:
                    cconn = get_conn()
                    try:
                        _ensure_usage_table(cconn)
                        _log_chat_usage(cconn, body.org_id, bot_id, 0.0, True)
                    finally:
                        cconn.close()
                except Exception:
                    pass

        return StreamingResponse(gen(), media_type="text/event-stream")
    finally:
        conn.close()

@router.get("/usage/{org_id}/{bot_id}")
def usage(org_id: str, bot_id: str, days: int = 30, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_usage_table(conn)
        from app.db import normalize_org_id, normalize_bot_id
        org_n = normalize_org_id(org_id)
        bot_n = normalize_bot_id(bot_id)
        with conn.cursor() as cur:
            cur.execute(
                "select day, chats, successes, fallbacks, sum_similarity from bot_usage_daily where (org_id=%s or org_id::text=%s) and bot_id=%s and day >= current_date - %s::int order by day asc",
                (org_n, org_id, bot_n, days),
            )
            rows = cur.fetchall()
        return {"daily": [{"day": r[0].isoformat(), "chats": int(r[1]), "successes": int(r[2]), "fallbacks": int(r[3]), "avg_similarity": (float(r[4]) / int(r[1])) if int(r[1]) > 0 else 0.0} for r in rows]}
    finally:
        conn.close()

@router.get("/usage/summary/{org_id}/{bot_id}")
def usage_summary(org_id: str, bot_id: str, days: int = 30, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_usage_table(conn)
        from app.db import normalize_org_id, normalize_bot_id
        org_n = normalize_org_id(org_id)
        bot_n = normalize_bot_id(bot_id)
        with conn.cursor() as cur:
            cur.execute(
                "select coalesce(sum(chats),0), coalesce(sum(successes),0), coalesce(sum(fallbacks),0), coalesce(sum(sum_similarity),0) from bot_usage_daily where (org_id=%s or org_id::text=%s) and bot_id=%s and day >= current_date - %s::int",
                (org_n, org_id, bot_n, days),
            )
            row = cur.fetchone()
            total = int(row[0])
            succ = int(row[1])
            fail = int(row[2])
            sumsim = float(row[3])
        return {"chats": total, "successes": succ, "fallbacks": fail, "avg_similarity": (sumsim / total) if total > 0 else 0.0}
    finally:
        conn.close()

@router.get("/rate/{org_id}/{bot_id}")
def rate_status(org_id: str, bot_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    key = f"{org_id}:{bot_id}"
    dq = _RATE_BUCKETS[key]
    return {"in_window": len(dq), "limit": 30, "window_seconds": 60}

@router.post("/bots/{bot_id}/config")
def update_bot_config(bot_id: str, body: BotConfigBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_form_config_column(conn)
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, body.org_id))
            allowed = {"sales", "support", "appointment", "qna"}
            beh = (body.behavior or "").strip().lower()
            if beh in {"appointments", "appointment booking", "bookings"}:
                beh = "appointment"
            if beh in {"sale", "sales bot"}:
                beh = "sales"
            if beh and beh not in allowed:
                raise HTTPException(status_code=400, detail=f"behavior must be one of {sorted(allowed)}")
            
            fc = json.dumps(body.form_config) if body.form_config is not None else None
            
            try:
                update_fields = ["behavior=%s", "system_prompt=%s", "website_url=%s", "role=%s", "tone=%s", "welcome_message=%s"]
                params = [beh or body.behavior, body.system_prompt, body.website_url, body.role, body.tone, body.welcome_message]
                
                if body.services is not None:
                    update_fields.append("services=%s")
                    params.append(body.services)
                
                if fc is not None:
                    update_fields.append("form_config=%s")
                    params.append(fc)
                
                sql = f"update chatbots set {', '.join(update_fields)} where id=%s and org_id::text in (%s,%s,%s)"
                params.extend([bot_id, normalize_org_id(body.org_id), body.org_id, nu])
                
                cur.execute(sql, tuple(params))
            except Exception as e:
                print(f"Error updating bot config: {e}")
                cur.execute(
                    "update chatbots set behavior=%s, system_prompt=%s where id=%s and org_id::text in (%s,%s,%s)",
                    (beh or body.behavior, body.system_prompt, bot_id, normalize_org_id(body.org_id), body.org_id, nu),
                )
            
            cur.execute(
                "select behavior, system_prompt, website_url, role, tone, welcome_message, services, form_config from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                (bot_id, normalize_org_id(body.org_id), body.org_id, nu),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot not found")
            
            fc = row[7]
            if isinstance(fc, str):
                try:
                    fc = json.loads(fc)
                except Exception:
                    fc = {}
            
            return {"behavior": row[0], "system_prompt": row[1], "website_url": row[2], "role": row[3], "tone": row[4], "welcome_message": row[5], "services": row[6], "form_config": fc}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/config")
def get_bot_config(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_form_config_column(conn)
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org_id))
            cur.execute(
                "select behavior, system_prompt, website_url, role, tone, welcome_message, services, form_config from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                (bot_id, normalize_org_id(org_id), org_id, nu),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot not found")
            fc = row[7]
            if isinstance(fc, str):
                try:
                    fc = json.loads(fc)
                except Exception:
                    fc = {}
            return {"behavior": row[0], "system_prompt": row[1], "website_url": row[2], "role": row[3], "tone": row[4], "welcome_message": row[5], "services": row[6], "form_config": fc}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/key")
def get_bot_key(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            try:
                import uuid
                nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org_id))
                cur.execute(
                    "select public_api_key, public_api_key_rotated_at from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                    (bot_id, normalize_org_id(org_id), org_id, nu),
                )
            except Exception:
                return {"public_api_key": None, "rotated_at": None}
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot not found")
            return {"public_api_key": row[0], "rotated_at": row[1].isoformat() if row[1] else None}
    finally:
        conn.close()

def _ensure_public_api_key_columns(conn):
    with conn.cursor() as cur:
        cur.execute(
            "select count(*) from information_schema.columns where table_name=%s and column_name=%s",
            ("chatbots", "public_api_key"),
        )
        c1 = cur.fetchone()[0]
        if int(c1) == 0:
            try:
                cur.execute("alter table chatbots add column public_api_key text")
            except Exception:
                pass
        cur.execute(
            "select count(*) from information_schema.columns where table_name=%s and column_name=%s",
            ("chatbots", "public_api_key_rotated_at"),
        )
        c2 = cur.fetchone()[0]
        if int(c2) == 0:
            try:
                cur.execute("alter table chatbots add column public_api_key_rotated_at timestamptz")
            except Exception:
                pass

@router.post("/bots/{bot_id}/key/rotate")
def rotate_bot_key(bot_id: str, body: KeyBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    import secrets
    new_key = secrets.token_urlsafe(32)
    conn = get_conn()
    try:
        _ensure_public_api_key_columns(conn)
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, body.org_id))
            cur.execute(
                "update chatbots set public_api_key=%s, public_api_key_rotated_at=now() where id=%s and org_id::text in (%s,%s,%s)",
                (new_key, bot_id, normalize_org_id(body.org_id), body.org_id, nu),
            )
            cur.execute(
                "select public_api_key, public_api_key_rotated_at from chatbots where id=%s and org_id::text in (%s,%s,%s)",
                (bot_id, normalize_org_id(body.org_id), body.org_id, nu),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Bot not found")
            return {"public_api_key": row[0], "rotated_at": row[1].isoformat() if row[1] else None}
    finally:
        conn.close()

@router.post("/bots/{bot_id}/key/revoke")
def revoke_bot_key(bot_id: str, body: KeyBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_public_api_key_columns(conn)
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, body.org_id))
            cur.execute(
                "update chatbots set public_api_key=NULL, public_api_key_rotated_at=NULL where id=%s and org_id::text in (%s,%s,%s)",
                (bot_id, normalize_org_id(body.org_id), body.org_id, nu),
            )
        return {"revoked": True}
    finally:
        conn.close()

def _ensure_calendar_settings_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_calendar_settings (
              org_id text not null,
              bot_id text not null,
              provider text not null,
              calendar_id text,
              timezone text,
              created_at timestamptz default now(),
              updated_at timestamptz default now(),
              primary key (org_id, bot_id, provider)
            )
            """
        )

def _ensure_appointments_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_appointments (
              id bigserial primary key,
              org_id text not null,
              bot_id text not null,
              summary text,
              start_iso text,
              end_iso text,
              attendees_json jsonb,
              status text,
              external_event_id text,
              updated_at timestamptz default now(),
              created_at timestamptz default now()
            )
            """
        )
        try:
            cur.execute("alter table bot_appointments add column if not exists status text")
            cur.execute("alter table bot_appointments add column if not exists external_event_id text")
            cur.execute("alter table bot_appointments add column if not exists updated_at timestamptz default now()")
        except Exception:
            pass

def _ensure_oauth_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_calendar_oauth (
              org_id text not null,
              bot_id text not null,
              provider text not null,
              access_token_enc text,
              refresh_token_enc text,
              token_expiry timestamptz,
              calendar_id text,
              timezone text,
              watch_channel_id text,
              watch_resource_id text,
              watch_expiration timestamptz,
              created_at timestamptz default now(),
              updated_at timestamptz default now(),
              primary key (org_id, bot_id, provider)
            )
            """
        )
        # Add timezone column if it doesn't exist (migration)
        try:
            cur.execute("""
                ALTER TABLE bot_calendar_oauth 
                ADD COLUMN IF NOT EXISTS timezone text
            """)
            print("✓ Added timezone column to bot_calendar_oauth")
        except Exception as e:
            print(f"Note: {str(e)}")

def _ensure_booking_settings_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists bot_booking_settings (
              org_id text not null,
              bot_id text not null,
              timezone text,
              available_windows jsonb,
              slot_duration_minutes int default 30,
              capacity_per_slot int default 1,
              min_notice_minutes int default 60,
              max_future_days int default 60,
              suggest_strategy text default 'next_best',
              required_user_fields jsonb,
              created_at timestamptz default now(),
              updated_at timestamptz default now(),
              primary key (org_id, bot_id)
            )
            """
        )
        try:
            cur.execute("alter table bot_booking_settings add column if not exists required_user_fields jsonb")
        except Exception:
            pass

def _ensure_audit_logs_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists booking_audit_logs (
              id bigserial primary key,
              org_id text not null,
              bot_id text not null,
              appointment_id bigint,
              action text not null,
              metadata jsonb,
              created_at timestamptz default now()
            )
            """
        )

def _ensure_notifications_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists booking_notifications (
              id bigserial primary key,
              org_id text not null,
              bot_id text not null,
              appointment_id bigint,
              type text not null,
              recipient text,
              payload jsonb,
              status text default 'queued',
              created_at timestamptz default now(),
              updated_at timestamptz default now()
            )
            """
        )

def _log_audit(conn, org_id: str, bot_id: str, appointment_id: int, action: str, metadata: dict):
    with conn.cursor() as cur:
        cur.execute(
            "insert into booking_audit_logs (org_id, bot_id, appointment_id, action, metadata) values (%s,%s,%s,%s,%s)",
            (normalize_org_id(org_id), bot_id, appointment_id, action, __import__("json").dumps(metadata or {})),
        )

def _enqueue_notification(conn, org_id: str, bot_id: str, appointment_id: int, typ: str, recipient: str, payload: dict):
    with conn.cursor() as cur:
        cur.execute(
            "insert into booking_notifications (org_id, bot_id, appointment_id, type, recipient, payload) values (%s,%s,%s,%s,%s,%s)",
            (normalize_org_id(org_id), bot_id, appointment_id, typ, recipient, __import__("json").dumps(payload or {})),
        )

@router.post("/bots/{bot_id}/calendar/config")
def set_calendar_config(bot_id: str, body: CalendarConfigBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_calendar_settings_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot_calendar_settings (org_id, bot_id, provider, calendar_id, timezone)
                values (%s,%s,%s,%s,%s)
                on conflict (org_id, bot_id, provider)
                do update set calendar_id=excluded.calendar_id, timezone=excluded.timezone, updated_at=now()
                returning provider, calendar_id, timezone
                """,
                (normalize_org_id(body.org_id), bot_id, body.provider, body.calendar_id, body.timezone),
            )
            row = cur.fetchone()
            return {"provider": row[0], "calendar_id": row[1], "timezone": row[2]}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/calendar/config")
def get_calendar_config(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_calendar_settings_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select provider, calendar_id, timezone from bot_calendar_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(org_id), org_id, bot_id),
            )
            row = cur.fetchone()
        if not row:
            return {"provider": None, "calendar_id": None, "timezone": None}
        return {"provider": row[0], "calendar_id": row[1], "timezone": row[2]}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/calendar/google/oauth/start")
def google_oauth_start(bot_id: str, org_id: str, redirect_uri: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    url = None
    try:
        from app.services.calendar_google import oauth_authorize_url
        url = oauth_authorize_url(org_id, bot_id, redirect_uri)
    except Exception:
        url = None
    if not url:
        raise HTTPException(status_code=500, detail="oauth not configured")
    return {"url": url}

@router.get("/calendar/google/oauth/callback")
def google_oauth_callback(code: str, state: Optional[str] = None, redirect_uri: str = ""):
    try:
        import urllib.parse
        raw = urllib.parse.unquote(state or "")
        qs = urllib.parse.parse_qs(raw)
        org_id = (qs.get("org") or [None])[0]
        bot_id = (qs.get("bot") or [None])[0]
    except Exception:
        org_id = None
        bot_id = None
    if not org_id or not bot_id:
        raise HTTPException(status_code=400, detail="invalid state")
    from app.db import get_conn, normalize_org_id
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        _ensure_calendar_settings_table(conn)
        data = None
        try:
            from app.services.calendar_google import exchange_code_for_tokens, _encrypt
            data = exchange_code_for_tokens(code, redirect_uri)
        except Exception:
            data = None
        if not data or not data.get("access_token"):
            raise HTTPException(status_code=500, detail="oauth exchange failed")
        at = _encrypt(data.get("access_token"))
        rt = _encrypt(data.get("refresh_token")) if data.get("refresh_token") else None
        exp = data.get("expiry")
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot_calendar_oauth (org_id, bot_id, provider, access_token_enc, refresh_token_enc, token_expiry, calendar_id)
                values (%s,%s,%s,%s,%s,%s,%s)
                on conflict (org_id, bot_id, provider)
                do update set access_token_enc=excluded.access_token_enc, refresh_token_enc=coalesce(excluded.refresh_token_enc, bot_calendar_oauth.refresh_token_enc), token_expiry=excluded.token_expiry, calendar_id=coalesce(bot_calendar_oauth.calendar_id, excluded.calendar_id), updated_at=now()
                returning calendar_id
                """,
                (normalize_org_id(org_id), bot_id, "google", at, rt, exp, "primary"),
            )
            row = cur.fetchone()
            cal_id = row[0] if row else "primary"
            cur.execute(
                """
                insert into bot_calendar_settings (org_id, bot_id, provider, calendar_id)
                values (%s,%s,%s,%s)
                on conflict (org_id, bot_id, provider)
                do update set calendar_id=excluded.calendar_id, updated_at=now()
                """,
                (normalize_org_id(org_id), bot_id, "google", cal_id or "primary"),
            )
        return {"connected": True, "calendar_id": cal_id or "primary"}
    finally:
        conn.close()

class BookingSettingsBody(BaseModel):
    org_id: str
    timezone: Optional[str] = None
    available_windows: Optional[list] = None
    slot_duration_minutes: Optional[int] = None
    capacity_per_slot: Optional[int] = None
    min_notice_minutes: Optional[int] = None
    max_future_days: Optional[int] = None
    suggest_strategy: Optional[str] = None
    required_user_fields: Optional[list] = None

@router.post("/bots/{bot_id}/booking/settings")
def set_booking_settings(bot_id: str, body: BookingSettingsBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_booking_settings_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into bot_booking_settings (org_id, bot_id, timezone, available_windows, slot_duration_minutes, capacity_per_slot, min_notice_minutes, max_future_days, suggest_strategy, required_user_fields)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                on conflict (org_id, bot_id)
                do update set timezone=excluded.timezone, available_windows=excluded.available_windows, slot_duration_minutes=excluded.slot_duration_minutes, capacity_per_slot=excluded.capacity_per_slot, min_notice_minutes=excluded.min_notice_minutes, max_future_days=excluded.max_future_days, suggest_strategy=excluded.suggest_strategy, required_user_fields=excluded.required_user_fields, updated_at=now()
                returning timezone, available_windows, slot_duration_minutes, capacity_per_slot, min_notice_minutes, max_future_days, suggest_strategy, required_user_fields
                """,
                (
                    normalize_org_id(body.org_id),
                    bot_id,
                    body.timezone,
                    None if body.available_windows is None else __import__("json").dumps(body.available_windows),
                    body.slot_duration_minutes,
                    body.capacity_per_slot,
                    body.min_notice_minutes,
                    body.max_future_days,
                    body.suggest_strategy,
                    None if body.required_user_fields is None else __import__("json").dumps(body.required_user_fields),
                ),
            )
            row = cur.fetchone()
            
            # Also update timezone in bot_calendar_oauth if Google Calendar is connected
            if body.timezone:
                try:
                    cur.execute(
                        """
                        UPDATE bot_calendar_oauth
                        SET timezone = %s
                        WHERE bot_id = %s AND provider = 'google'
                        """,
                        (body.timezone, bot_id)
                    )
                    print(f"✅ Updated Google Calendar timezone to: {body.timezone}")
                except Exception as e:
                    print(f"⚠️ Could not update calendar timezone: {str(e)}")
        import json
        aw = None
        try:
            if row[1] is None:
                aw = None
            elif isinstance(row[1], (list, dict)):
                aw = row[1]
            else:
                aw = json.loads(row[1])
        except Exception:
            aw = None
        return {
            "timezone": row[0],
            "available_windows": aw,
            "slot_duration_minutes": row[2],
            "capacity_per_slot": row[3],
            "min_notice_minutes": row[4],
            "max_future_days": row[5],
            "suggest_strategy": row[6],
            "required_user_fields": (None if row[7] is None else (row[7] if isinstance(row[7], list) else json.loads(row[7]) if isinstance(row[7], str) else None)),
        }
    finally:
        conn.close()

@router.get("/bots/{bot_id}/booking/settings")
def get_booking_settings(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None), x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, org_id)
    finally:
        conn.close()
    if public_api_key:
        if x_bot_key and x_bot_key == public_api_key:
            pass
        elif authorization:
            _require_auth(authorization, org_id)
        elif not x_bot_key:
            pass
        else:
            raise HTTPException(status_code=403, detail="Invalid bot key")
    else:
        _require_auth(authorization, org_id)
    conn = get_conn()
    try:
        _ensure_booking_settings_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select timezone, available_windows, slot_duration_minutes, capacity_per_slot, min_notice_minutes, max_future_days, suggest_strategy, required_user_fields from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(org_id), org_id, bot_id),
            )
            row = cur.fetchone()
        import json
        if not row:
            return {"timezone": None, "available_windows": [], "slot_duration_minutes": 30, "capacity_per_slot": 1, "min_notice_minutes": 60, "max_future_days": 60, "suggest_strategy": "next_best", "required_user_fields": ["name","email"]}
        aw = []
        try:
            raw = row[1]
            if raw is None:
                aw = []
            elif isinstance(raw, list):
                aw = raw
            elif isinstance(raw, str):
                try:
                    aw = json.loads(raw)
                except Exception:
                    aw = []
            elif isinstance(raw, dict):
                # If it's a dict, it's not a list of windows. Treat as empty or try to wrap?
                # Assuming empty or invalid structure.
                aw = []
        except Exception:
            aw = []
        ruf = None
        try:
            if row[7] is None:
                ruf = None
            elif isinstance(row[7], (list, dict)):
                ruf = row[7] if isinstance(row[7], list) else None
            else:
                ruf = json.loads(row[7])
        except Exception:
            ruf = None
        return {
            "timezone": row[0],
            "available_windows": aw,
            "slot_duration_minutes": row[2],
            "capacity_per_slot": row[3],
            "min_notice_minutes": row[4],
            "max_future_days": row[5],
            "suggest_strategy": row[6],
            "required_user_fields": ruf,
        }
    finally:
        conn.close()

@router.get("/bots/{bot_id}/booking/availability")
def booking_availability(bot_id: str, org_id: str, time_min_iso: str, time_max_iso: str, authorization: Optional[str] = Header(default=None), x_bot_key: Optional[str] = Header(default=None)):
    try:
        conn = get_conn()
        try:
            _ensure_booking_settings_table(conn)
            _ensure_oauth_table(conn)
            behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, org_id)
            if public_api_key:
                if x_bot_key and x_bot_key == public_api_key:
                    pass
                elif authorization:
                    _require_auth(authorization, org_id)
                elif not x_bot_key:
                    pass
                else:
                    raise HTTPException(status_code=403, detail="Invalid bot key")
            with conn.cursor() as cur:
                cur.execute(
                    "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                    (normalize_org_id(org_id), org_id, bot_id, "google"),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=400, detail="calendar not connected")
                cal_id, at_enc, rt_enc, exp = row
                cur.execute(
                    "select timezone, slot_duration_minutes, capacity_per_slot, available_windows, min_notice_minutes, max_future_days from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                    (normalize_org_id(org_id), org_id, bot_id),
                )
                bs = cur.fetchone()
            slotm = int(bs[1]) if bs and bs[1] else 30
            capacity = int(bs[2]) if bs and bs[2] else 1
            tzv = bs[0] if bs else None
            import json
            aw = None if (not bs or bs[3] is None) else (bs[3] if isinstance(bs[3], list) else json.loads(bs[3]) if isinstance(bs[3], str) else None)
            min_notice = int(bs[4]) if bs and bs[4] else None
            max_future = int(bs[5]) if bs and bs[5] else None
            from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth
            at = _decrypt(at_enc) if at_enc else None
            rt = _decrypt(rt_enc) if rt_enc else None
            svc = build_service_from_tokens(at, rt, exp)
            if not svc:
                raise HTTPException(status_code=500, detail="calendar service unavailable")
            items = list_events_oauth(svc, cal_id or "primary", time_min_iso, time_max_iso)
            extra = {}
            try:
                with conn.cursor() as cur:
                    # Count bookings from unified bookings table grouped by start time
                    cur.execute("""
                        select 
                            (booking_date || 'T' || start_time)::text as start_iso,
                            count(*) as booking_count
                        from bookings 
                        where bot_id=%s 
                          and status not in ('cancelled', 'rejected')
                          and booking_date >= %s::date
                          and booking_date <= %s::date
                        group by booking_date, start_time
                    """, (bot_id, time_min_iso[:10], time_max_iso[:10]))
                    rows = cur.fetchall()
                    extra = {r[0]: int(r[1]) for r in rows}
            except Exception as e:
                print(f"Error counting bookings: {e}")
                extra = {}
            from app.services.booking import compute_availability
            slots = compute_availability(time_min_iso, time_max_iso, slotm, capacity, items, tzv, aw, extra, min_notice, max_future)
            return {"slots": slots}
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class CreateAppointmentBody(BaseModel):
    org_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    start_iso: str
    end_iso: str

@router.post("/bots/{bot_id}/booking/appointment")
def booking_create(bot_id: str, body: CreateAppointmentBody, authorization: Optional[str] = Header(default=None), x_bot_key: Optional[str] = Header(default=None)):
    import traceback
    conn = get_conn()
    try:
        _ensure_booking_settings_table(conn)
        _ensure_oauth_table(conn)
        _ensure_appointments_table(conn)
        _ensure_audit_logs_table(conn)
        _ensure_notifications_table(conn)
        behavior, system_prompt, public_api_key = get_bot_meta(conn, bot_id, body.org_id)
        # Allow public booking if bot key matches or if authorization is provided
        if public_api_key:
            if x_bot_key and x_bot_key == public_api_key:
                pass  # Valid bot key - allow booking
            elif authorization:
                _require_auth(authorization, body.org_id)
            else:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        else:
            # No public key set - require authorization
            _require_auth(authorization, body.org_id)
        with conn.cursor() as cur:
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc, exp = row
            cur.execute(
                "select timezone, slot_duration_minutes, capacity_per_slot, required_user_fields from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            bs = cur.fetchone()
        tzv = bs[0] if bs else None
        slotm = int(bs[1]) if bs and bs[1] else 30
        capacity = int(bs[2]) if bs and bs[2] else 1
        try:
            rfraw = bs[3] if bs else None
            _json = __import__("json")
            required_fields = rfraw if isinstance(rfraw, list) else (_json.loads(rfraw) if isinstance(rfraw, str) else [])
        except Exception:
            required_fields = []
        info = {"name": body.name, "email": body.email, "phone": body.phone, "notes": body.notes}
        missing = [f for f in (required_fields or []) if not info.get(f)]
        if missing:
            raise HTTPException(status_code=400, detail="missing fields: " + ", ".join(missing))
        from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth, create_event_oauth
        import logging
        logging.info(f"Decrypting tokens - at_enc exists: {bool(at_enc)}, rt_enc exists: {bool(rt_enc)}")
        at = _decrypt(at_enc) if at_enc else None
        rt = _decrypt(rt_enc) if rt_enc else None
        logging.info(f"Decrypted tokens - at exists: {bool(at)}, rt exists: {bool(rt)}")
        if not at:
            raise HTTPException(status_code=500, detail="Failed to decrypt access token - calendar may need to be reconnected")
        svc = build_service_from_tokens(at, rt, exp)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service unavailable")
        import datetime as _dt
        tmn = _dt.datetime.fromisoformat(body.start_iso)
        tmx = _dt.datetime.fromisoformat(body.end_iso)
        items = list_events_oauth(svc, cal_id or "primary", tmn.isoformat(), tmx.isoformat())
        occ = len(items) if items else 0
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso=%s and end_iso=%s and status in ('scheduled','booked')",
                (normalize_org_id(body.org_id), body.org_id, bot_id, body.start_iso, body.end_iso),
            )
            occ_db = int(cur.fetchone()[0])
        # Business hours enforcement
        try:
            cur.execute(
                "select timezone, available_windows, min_notice_minutes, max_future_days from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            srow = cur.fetchone()
            tzv = srow[0] if srow else None
            import json
            aw = None if (not srow or srow[1] is None) else (srow[1] if isinstance(srow[1], list) else json.loads(srow[1]) if isinstance(srow[1], str) else None)
        except Exception:
            tzv=None; aw=None
        from datetime import datetime
        def _in_hours(si):
            if not aw:
                return True
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(tzv) if tzv else None
                dt = datetime.fromisoformat(si.replace("Z","+00:00"))
                local = dt.astimezone(tz) if tz else dt
                day = ["mon","tue","wed","thu","fri","sat","sun"][local.weekday()]
                minutes = local.hour*60 + local.minute
                for w in aw:
                    d=(w.get("day") or "").strip().lower()[:3]
                    if d!=day: continue
                    sh,sm=[int(x) for x in (w.get("start") or "00:00").split(":",1)]
                    eh,em=[int(x) for x in (w.get("end") or "23:59").split(":",1)]
                    if minutes>=sh*60+sm and minutes<eh*60+em:
                        return True
                return False
            except Exception:
                return True
        if not _in_hours(body.start_iso):
            raise HTTPException(status_code=422, detail="outside business hours")
        if max(occ, occ_db) >= capacity:
            raise HTTPException(status_code=409, detail="slot unavailable")
        attns = ([body.email] if body.email else None)
        desc = f"Appointment\nName: {body.name or ''}\nEmail: {body.email or ''}\nPhone: {body.phone or ''}\nNotes: {body.notes or ''}"
        ext_id = create_event_oauth(svc, cal_id or "primary", "Appointment", body.start_iso, body.end_iso, attns, tzv, desc)
        if not ext_id:
            raise HTTPException(status_code=500, detail="booking failed")
        with conn.cursor() as cur:
            cur.execute(
                "insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json, status, external_event_id) values (%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                (normalize_org_id(body.org_id), bot_id, "Appointment", body.start_iso, body.end_iso, (__import__("json").dumps(info) if info else None), "booked", ext_id),
            )
            apid = int(cur.fetchone()[0])
        try:
            from app.services.calendar_google import update_event_oauth
            desc = f"Appointment ID: {apid}\nName: {body.name or ''}\nEmail: {body.email or ''}\nPhone: {body.phone or ''}\nNotes: {body.notes or ''}"
            patch = {
                "summary": "Appointment #"+str(apid)+" - "+(body.name or ""),
                "description": desc,
                "extendedProperties": {"private": {"appointment_id": str(apid), "org_id": body.org_id, "bot_id": bot_id}},
            }
            update_event_oauth(svc, cal_id or "primary", ext_id, patch)
        except Exception:
            _log_audit(conn, body.org_id, bot_id, apid, "calendar_patch_error", {"ext_id": ext_id})
        _log_audit(conn, body.org_id, bot_id, apid, "create", {"start_iso": body.start_iso, "end_iso": body.end_iso})
        if body.email:
            _enqueue_notification(conn, body.org_id, bot_id, apid, "confirmation", body.email, {"appointment_id": apid})
        return {"appointment_id": apid, "external_event_id": ext_id}
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Booking appointment error: {str(e)}")
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Booking failed: {str(e)}")
    finally:
        conn.close()

class RescheduleBody(BaseModel):
    org_id: str
    new_start_iso: str
    new_end_iso: str

@router.post("/bots/{bot_id}/booking/appointment/{appointment_id}/reschedule")
def booking_reschedule(bot_id: str, appointment_id: int, body: RescheduleBody, authorization: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        _require_auth(authorization, body.org_id)
        _ensure_oauth_table(conn)
        _ensure_audit_logs_table(conn)
        _ensure_notifications_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select external_event_id from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                (appointment_id, normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            ev_id = row[0]
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            c = cur.fetchone()
            if not c:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc, exp = c
            cur.execute(
                "select timezone, slot_duration_minutes, capacity_per_slot from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            bs = cur.fetchone()
        tzv = bs[0] if bs else None
        capacity = int(bs[2]) if bs and bs[2] else 1
        from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth, update_event_oauth
        at = _decrypt(at_enc) if at_enc else None
        rt = _decrypt(rt_enc) if rt_enc else None
        svc = build_service_from_tokens(at, rt, exp)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service unavailable")
        import datetime as _dt
        tmn = _dt.datetime.fromisoformat(body.new_start_iso)
        tmx = _dt.datetime.fromisoformat(body.new_end_iso)
        items = list_events_oauth(svc, cal_id or "primary", tmn.isoformat(), tmx.isoformat())
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso=%s and end_iso=%s and status in ('scheduled','booked')",
                (normalize_org_id(body.org_id), body.org_id, bot_id, body.new_start_iso, body.new_end_iso),
            )
            occ_db = int(cur.fetchone()[0])
        # Business hours enforcement for reschedule
        try:
            cur.execute(
                "select timezone, available_windows from bot_booking_settings where (org_id=%s or org_id::text=%s) and bot_id=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            srow = cur.fetchone()
            tzv = srow[0] if srow else None
            import json
            aw = None if (not srow or srow[1] is None) else (srow[1] if isinstance(srow[1], list) else json.loads(srow[1]) if isinstance(srow[1], str) else None)
        except Exception:
            tzv=None; aw=None
        from datetime import datetime
        def _in_hours(si):
            if not aw:
                return True
            try:
                import zoneinfo
                tz = zoneinfo.ZoneInfo(tzv) if tzv else None
                dt = datetime.fromisoformat(si.replace("Z","+00:00"))
                local = dt.astimezone(tz) if tz else dt
                day = ["mon","tue","wed","thu","fri","sat","sun"][local.weekday()]
                minutes = local.hour*60 + local.minute
                for w in aw:
                    d=(w.get("day") or "").strip().lower()[:3]
                    if d!=day: continue
                    sh,sm=[int(x) for x in (w.get("start") or "00:00").split(":",1)]
                    eh,em=[int(x) for x in (w.get("end") or "23:59").split(":",1)]
                    if minutes>=sh*60+sm and minutes<eh*60+em:
                        return True
                return False
            except Exception:
                return True
        if not _in_hours(body.new_start_iso):
            raise HTTPException(status_code=422, detail="outside business hours")
        if max(len(items or []), occ_db) >= capacity:
            raise HTTPException(status_code=409, detail="slot unavailable")
        ok = update_event_oauth(svc, cal_id or "primary", ev_id, {"start": {"dateTime": body.new_start_iso, **({"timeZone": tzv} if tzv else {})}, "end": {"dateTime": body.new_end_iso, **({"timeZone": tzv} if tzv else {})}})
        if not ok:
            raise HTTPException(status_code=500, detail="reschedule failed")
        with conn.cursor() as cur:
            cur.execute(
                "update bot_appointments set start_iso=%s, end_iso=%s, updated_at=now() where id=%s",
                (body.new_start_iso, body.new_end_iso, appointment_id),
            )
        _log_audit(conn, body.org_id, bot_id, appointment_id, "reschedule", {"new_start_iso": body.new_start_iso, "new_end_iso": body.new_end_iso})
        return {"rescheduled": True}
    finally:
        conn.close()

class CancelBody(BaseModel):
    org_id: str

@router.post("/bots/{bot_id}/booking/appointment/{appointment_id}/cancel")
def booking_cancel(bot_id: str, appointment_id: int, body: CancelBody, authorization: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        _require_auth(authorization, body.org_id)
        _ensure_oauth_table(conn)
        _ensure_audit_logs_table(conn)
        _ensure_notifications_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select external_event_id from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                (appointment_id, normalize_org_id(body.org_id), body.org_id, bot_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            ev_id = row[0]
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            c = cur.fetchone()
            if not c:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc, exp = c
        from app.services.calendar_google import _decrypt, build_service_from_tokens, delete_event_oauth
        at = _decrypt(at_enc) if at_enc else None
        rt = _decrypt(rt_enc) if rt_enc else None
        svc = build_service_from_tokens(at, rt, exp)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service unavailable")
        ok = delete_event_oauth(svc, cal_id or "primary", ev_id)
        if not ok:
            raise HTTPException(status_code=500, detail="cancel failed")
        with conn.cursor() as cur:
            cur.execute("update bot_appointments set status=%s, updated_at=now() where id=%s", ("cancelled", appointment_id))
        _log_audit(conn, body.org_id, bot_id, appointment_id, "cancel", {})
        return {"cancelled": True}
    finally:
        conn.close()

@router.get("/form/{bot_id}", response_class=HTMLResponse)
def booking_form(bot_id: str, org_id: str, bot_key: Optional[str] = None):
    base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
    api_url = base.rstrip('/')
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Book Appointment</title>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1\">"
        "<style>"
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:12px}"
        ".container{background:#fff;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.3);max-width:600px;width:100%;padding:32px;max-height:90vh;overflow-y:auto}"
        ".header{margin-bottom:28px}"
        ".header h1{font-size:28px;font-weight:700;color:#1a1a1a;margin-bottom:8px}"
        ".header p{font-size:14px;color:#666}"
        ".form-group{margin-bottom:20px}"
        ".form-group label{display:block;font-size:13px;font-weight:600;color:#333;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px}"
        ".form-group input[type='text'],.form-group input[type='email'],.form-group input[type='tel'],.form-group input[type='number'],.form-group input[type='date'],.form-group input[type='time'],.form-group select,.form-group textarea{width:100%;padding:12px 14px;border:2px solid #e0e0e0;border-radius:8px;font-size:14px;transition:all 0.3s ease;font-family:inherit}"
        ".form-group textarea{min-height:80px;resize:vertical}"
        ".form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:#667eea;box-shadow:0 0 0 3px rgba(102,126,234,0.1)}"
        ".form-group input.error,.form-group select.error,.form-group textarea.error{border-color:#dc2626}"
        ".form-group.required label::after{content:' *';color:#dc2626}"
        ".help-text{font-size:12px;color:#666;margin-top:4px}"
        ".checkbox-group{display:flex;align-items:center;gap:8px}"
        ".checkbox-group input[type='checkbox']{width:auto;margin:0}"
        ".radio-group{display:flex;flex-direction:column;gap:8px}"
        ".radio-option{display:flex;align-items:center;gap:8px;padding:8px;border:2px solid #e0e0e0;border-radius:6px;cursor:pointer}"
        ".radio-option:hover{background:#f9f9f9}"
        ".radio-option input[type='radio']{width:auto;margin:0}"
        ".section{margin-bottom:24px;padding-bottom:24px;border-bottom:1px solid #e5e5e5}"
        ".section:last-of-type{border-bottom:none}"
        ".section-title{font-size:16px;font-weight:700;color:#333;margin-bottom:16px}"
        ".time-slots{display:grid;grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px;margin-top:12px}"
        ".time-slot{padding:10px;border:2px solid #e0e0e0;border-radius:8px;background:#f9f9f9;cursor:pointer;text-align:center;font-size:13px;font-weight:600;color:#333;transition:all 0.2s ease}"
        ".time-slot:hover{border-color:#667eea;background:#f0f4ff}"
        ".time-slot.selected{background:#667eea;color:#fff;border-color:#667eea}"
        ".time-slot .cap{display:block;font-size:11px;color:#666;margin-top:4px;font-weight:500}"
        ".time-slot.selected .cap{color:#fff}"
        ".slot-status{font-size:13px;color:#666;padding:12px;text-align:center;background:#f5f5f5;border-radius:8px;margin-top:12px}"
        ".loading-spinner{display:inline-block;width:14px;height:14px;border:2px solid #e0e0e0;border-top:2px solid #667eea;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:6px}"
        "@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}"
        ".button-group{display:flex;gap:12px;margin-top:28px}"
        "#submit{flex:1;padding:14px 24px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:700;cursor:pointer;transition:all 0.3s ease;text-transform:uppercase;letter-spacing:0.5px}"
        "#submit:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(102,126,234,0.4)}"
        "#submit:active{transform:translateY(0)}"
        "#submit:disabled{opacity:0.6;cursor:not-allowed;transform:none}"
        "#out{margin-top:16px;padding:14px;border-radius:8px;font-size:14px;font-weight:600;display:none}"
        "#out.success{background:#d1fae5;color:#065f46;border-left:4px solid #10b981;display:block}"
        "#out.error{background:#fee2e2;color:#7f1d1d;border-left:4px solid #dc2626;display:block}"
        "#out.info{background:#dbeafe;color:#1e40af;border-left:4px solid #3b82f6;display:block}"
        ".required-fields{font-size:12px;color:#999;margin-top:12px}"
        "</style>"
        "</head><body>"
        "<div class=\"container\">"
        "<div class=\"header\"><h1>Book Appointment</h1><p>Fill in your details and select a time</p></div>"
        "<div id=\"form-container\">"
        "<div class=\"section\"><div class=\"loading-spinner\"></div> Loading form...</div>"
        "</div>"
        "<div id=\"out\"></div>"
        "</div>"
        "<script>"
        "const ORG='" + org_id + "',BOT='" + bot_id + "',BOT_KEY='" + (bot_key or '') + "',API='" + api_url + "';"
        "let chosen=null,loading=false,formFields=[],resources={},formConfig=null,allResources=[],slotPoll=null;"
        "function showMsg(t,ty){const o=document.getElementById('out');o.textContent=t;o.className=ty;o.style.display='block';}"
        "function startSlotPolling(){try{if(slotPoll)clearInterval(slotPoll);}catch(e){}slotPoll=setInterval(()=>{try{if(document.visibilityState==='visible')loadSlots();}catch(e){}},15000);}"
        
        # Load form configuration and fields
        "async function loadFormConfig(){"
        "  try{"
        "    const h={};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;"
        "    const r1=await fetch(API+'/api/form-configs/'+BOT,{headers:h});"
        "    if(r1.ok){"
        "      formConfig=await r1.json();"
        "      const r2=await fetch(API+'/api/form-configs/'+formConfig.id+'/fields',{headers:h});"
        "      if(r2.ok){"
        "        const data=await r2.json();"
        "        formFields=data.fields||[];"
        "      }"
        "      const r3=await fetch(API+'/api/resources/'+BOT,{headers:h});"
        "      if(r3.ok){"
        "        const data=await r3.json();"
        "        allResources=data.resources||[];"
        "        resources=allResources.reduce((acc,r)=>{acc[r.resource_type]=acc[r.resource_type]||[];acc[r.resource_type].push(r);return acc;},{});"
        "        window._resourceIndex=allResources.reduce((m,r)=>{"
        "          m.ids[r.id]=r;"
        "          if(r.resource_code)m.codes[r.resource_code]=r;"
        "          if(r.resource_name)m.names[(r.resource_name||'').toLowerCase()]=r;"
        "          return m;"
        "        },{ids:{},codes:{},names:{}});"
        "      }"
        "    }"
        "    renderForm();"
        "  }catch(e){console.error('Form config error:',e);renderDefaultForm();}"
        "}"
        
        # Render dynamic form fields
        "function renderForm(){"
        "  const container=document.getElementById('form-container');"
        "  let html='<div class=\"section\"><div class=\"section-title\">Personal Information</div>';"
        "  html+='<div class=\"form-group required\"><label>Full Name</label><input id=\"customer_name\" type=\"text\" placeholder=\"John Doe\" required></div>';"
        "  html+='<div class=\"form-group required\"><label>Email</label><input id=\"customer_email\" type=\"email\" placeholder=\"john@example.com\" required></div>';"
        "  html+='<div class=\"form-group\"><label>Phone</label><input id=\"customer_phone\" type=\"tel\" placeholder=\"+1234567890\"></div>';"
        "  html+='</div>';"
        "  if(formFields.length>0){"
        "    html+='<div class=\"section\"><div class=\"section-title\">Appointment Details</div>';"
        "    formFields.forEach(f=>{"
        "      const req=f.is_required?'required':'';const reqClass=f.is_required?' required':'';"
        "      html+='<div class=\"form-group'+reqClass+'\">';"
        "      html+='<label>'+f.field_label+'</label>';"
        "      if(f.field_type==='text'||f.field_type==='email'||f.field_type==='phone'||f.field_type==='number'){"
        "        html+='<input id=\"field_'+f.field_name+'\" type=\"'+f.field_type+'\" placeholder=\"'+(f.placeholder||'')+'\" '+req+'>';"
        "      }else if(f.field_type==='date'||f.field_type==='time'){"
        "        html+='<input id=\"field_'+f.field_name+'\" type=\"'+f.field_type+'\" '+req+'>';"
        "      }else if(f.field_type==='textarea'){"
        "        html+='<textarea id=\"field_'+f.field_name+'\" placeholder=\"'+(f.placeholder||'')+'\" '+req+'></textarea>';"
        "      }else if(f.field_type==='select'){"
        "        html+='<select id=\"field_'+f.field_name+'\" '+req+'><option value=\"\">Select...</option>';"
        "        const opts=f.options||[];"
        "        opts.forEach(o=>html+='<option value=\"'+o.value+'\">'+o.label+'</option>');"
        "        const resType=f.field_name.includes('doctor')?'doctor':f.field_name.includes('stylist')?'staff':null;"
        "        if(resType&&resources[resType]){"
        "          resources[resType].forEach(r=>html+='<option value=\"'+r.id+'\">'+r.resource_name+'</option>');"
        "        }"
        "        html+='</select>';"
        "      }else if(f.field_type==='radio'){"
        "        html+='<div class=\"radio-group\">';"
        "        const opts=f.options||[];"
        "        opts.forEach(o=>{"
        "          html+='<label class=\"radio-option\"><input type=\"radio\" name=\"field_'+f.field_name+'\" value=\"'+o.value+'\" '+req+'>'+o.label+'</label>';"
        "        });"
        "        html+='</div>';"
        "      }else if(f.field_type==='checkbox'){"
        "        html+='<div class=\"checkbox-group\"><input id=\"field_'+f.field_name+'\" type=\"checkbox\"><label>'+f.field_label+'</label></div>';"
        "      }"
        "      if(f.help_text)html+='<div class=\"help-text\">'+f.help_text+'</div>';"
        "      html+='</div>';"
        "    });"
        "    html+='</div>';"
        "  }"
        "  html+='<div class=\"section\"><div class=\"section-title\">Select Date & Time</div>';"
        "  html+='<div class=\"form-group required\"><label>Date</label><input id=\"booking_date\" type=\"date\" required></div>';"
        "  html+='<div class=\"time-slots\" id=\"slots\"></div>';"
        "  html+='<div class=\"slot-status\" id=\"slot-status\" style=\"display:none\"></div>';"
        "  html+='</div>';"
        "  html+='<div class=\"button-group\"><button id=\"submit\" type=\"button\">Book Appointment</button></div>';"
        "  html+='<div class=\"required-fields\">* Required fields</div>';"
        "  container.innerHTML=html;"
        "  document.getElementById('booking_date').addEventListener('change',()=>{loadSlots();startSlotPolling();});"
        "  Array.from(document.querySelectorAll('select')).forEach(s=>s.addEventListener('change',()=>{loadSlots();startSlotPolling();}));"
        "  document.getElementById('submit').addEventListener('click',submitBooking);"
        "  const today=new Date();"
        "  const todayIso=today.toISOString().slice(0,10);"
        "  const dateInput=document.getElementById('booking_date');"
        "  dateInput.value=todayIso;"
        "  dateInput.setAttribute('min', todayIso);"
        "  loadSlots();startSlotPolling();"
        "}"
        
        "function renderDefaultForm(){"
        "  const container=document.getElementById('form-container');"
        "  let html='<div class=\"section\">';"
        "  html+='<div class=\"form-group required\"><label>Full Name</label><input id=\"customer_name\" type=\"text\" required></div>';"
        "  html+='<div class=\"form-group required\"><label>Email</label><input id=\"customer_email\" type=\"email\" required></div>';"
        "  html+='<div class=\"form-group\"><label>Phone</label><input id=\"customer_phone\" type=\"tel\"></div>';"
        "  html+='<div class=\"form-group\"><label>Notes</label><input id=\"notes\" type=\"text\"></div>';"
        "  html+='</div>';"
        "  html+='<div class=\"section\"><div class=\"form-group required\"><label>Date</label><input id=\"booking_date\" type=\"date\" required></div>';"
        "  html+='<div class=\"time-slots\" id=\"slots\"></div><div class=\"slot-status\" id=\"slot-status\" style=\"display:none\"></div></div>';"
        "  html+='<div class=\"button-group\"><button id=\"submit\" type=\"button\">Book Appointment</button></div>';"
        "  container.innerHTML=html;"
        "  document.getElementById('booking_date').addEventListener('change',()=>{loadSlots();startSlotPolling();});"
        "  Array.from(document.querySelectorAll('select')).forEach(s=>s.addEventListener('change',()=>{loadSlots();startSlotPolling();}));"
        "  document.getElementById('submit').addEventListener('click',submitBooking);"
        "  const today=new Date();document.getElementById('booking_date').value=today.toISOString().slice(0,10);loadSlots();startSlotPolling();"
        "}"
        
        # Load available time slots
        "async function loadSlots(){"
        "  const dt=document.getElementById('booking_date').value;if(!dt)return;"
        "  chosen=null;"
        "  const h={};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;"
        "  const el=document.getElementById('slots'),st=document.getElementById('slot-status');"
        "  el.innerHTML='';st.innerHTML='<span class=\"loading-spinner\"></span> Loading...';st.style.display='block';"
        "  let resourceId=null;"
        "  const hasResources=allResources&&allResources.length>0;"
        "  try{"
        "    const formData={};"
        "    formFields.forEach(f=>{"
        "      const el=document.getElementById('field_'+f.field_name)||document.querySelector('input[name=\"field_'+f.field_name+'\"]:checked');"
        "      if(el){formData[f.field_name]=el.type==='checkbox'?el.checked:(el.value||'');}"
        "    });"
        "    resourceId=(formData.doctor||formData.stylist||formData.consultant||formData.tutor||formData.service||formData.resource||null);"
        "    if(!resourceId){"
        "      Array.from(document.querySelectorAll('select')).forEach(s=>{"
        "        const val=s.value;"
        "        const opt=s.options&&s.options[s.selectedIndex];"
        "        const txt=(opt?(opt.text||opt.textContent||''):'');"
        "        if(!val)return;"
        "        if(window._resourceIndex){"
        "          const byId=window._resourceIndex.ids[val];"
        "          const byCode=window._resourceIndex.codes[val];"
        "          const byName=window._resourceIndex.names[(val||'').toLowerCase()];"
        "          const byText=window._resourceIndex.names[(txt||'').toLowerCase()];"
        "          const picked=(byId||byCode||byName||byText);"
        "          if(picked)resourceId=picked.id;"
        "        }"
        "      });"
        "    }"
        "  }catch(e){}"
        "  if(hasResources&&!resourceId){resourceId=allResources[0]&&allResources[0].id;}"
        "  const url=resourceId?(API+'/api/resources/'+resourceId+'/available-slots?booking_date='+dt):(API+'/api/bots/'+BOT+'/available-slots?booking_date='+dt);"
        "  try{"
        "    const r=await fetch(url,{headers:h});"
        "    if(!r.ok){st.textContent='Error loading slots';return;}"
        "    const d=await r.json();"
        "    const rawSlots=(d.slots||[]).filter(s=>Number(s.available_capacity||0)>0);"
        "    const now=new Date();"
        "    const upcoming=rawSlots.filter(s=>{"
        "      try{"
        "        return new Date(dt+'T'+(s.start_time||'00:00:00'))>now;"
        "      }catch(e){return true;}"
        "    });"
        "    if(upcoming.length===0){st.textContent='No upcoming slots for this date';return;}"
        "    st.style.display='none';"
        "    upcoming.forEach(s=>{"
        "      const b=document.createElement('button');b.type='button';b.className='time-slot';"
        "      const [h,m]=s.start_time.split(':');"
        "      const hNum=parseInt(h,10);const ampm=hNum>=12?'PM':'AM';const h12=hNum%12||12;"
        "      const cap=s.available_capacity;"
        "      b.innerHTML=h12+':'+(m||'00')+' '+ampm+(cap?('<span class=\"cap\">'+cap+' available</span>'):'');"
        "      b.onclick=()=>{"
        "        chosen={start:dt+'T'+s.start_time,end:dt+'T'+s.end_time};"
        "        document.querySelectorAll('.time-slot').forEach(x=>x.classList.remove('selected'));"
        "        b.classList.add('selected');"
        "      };"
        "      el.appendChild(b);"
        "    });"
        "  }catch(e){console.error(e);st.textContent='Error: '+e.message;}"
        "}"
        
        # Submit booking with dynamic form data
        "async function submitBooking(){"
        "  const name=document.getElementById('customer_name').value.trim();"
        "  const email=document.getElementById('customer_email').value.trim();"
        "  const phone=(document.getElementById('customer_phone')||{}).value||'';"
        "  const date=document.getElementById('booking_date').value;"
        "  if(!name||!email||!date){showMsg('Please fill required fields','error');return;}"
        "  if(!chosen){showMsg('Please select a time slot','error');return;}"
        "  const formData={};"
        "  formFields.forEach(f=>{"
        "    const el=document.getElementById('field_'+f.field_name)||document.querySelector('input[name=\"field_'+f.field_name+'\"]:checked');"
        "    if(el){formData[f.field_name]=el.type==='checkbox'?el.checked:(el.value||'');}"
        "  });"
        "  let resourceId=(formData.doctor||formData.stylist||formData.consultant||formData.tutor||formData.service||formData.resource||null);"
        "  if(!resourceId){"
        "    Array.from(document.querySelectorAll('select')).forEach(s=>{"
        "      const val=s.value;const opt=s.options&&s.options[s.selectedIndex];const txt=(opt?(opt.text||opt.textContent||''):'');"
        "      if(window._resourceIndex){"
        "        const byId=window._resourceIndex.ids[val];"
        "        const byCode=window._resourceIndex.codes[val];"
        "        const byName=window._resourceIndex.names[(val||'').toLowerCase()];"
        "        const byText=window._resourceIndex.names[(txt||'').toLowerCase()];"
        "        const picked=(byId||byCode||byName||byText);"
        "        if(picked)resourceId=picked.id;"
        "      }"
        "    });"
        "    if(!resourceId&&window._resourceIndex){"
        "      const rv=document.querySelector('input[type=\"radio\"]:checked');"
        "      const tv=document.querySelector('input[type=\"text\"]');"
        "      const cand=[(rv||{}).value,(tv||{}).value].filter(Boolean);"
        "      cand.forEach(v=>{if(resourceId)return;const byId=window._resourceIndex.ids[v];const byCode=window._resourceIndex.codes[v];const byName=window._resourceIndex.names[(v||'').toLowerCase()];const picked=(byId||byName||byCode);if(picked)resourceId=picked.id;});"
        "    }"
        "  }"
        "  if(!resourceId&&Array.isArray(allResources)&&allResources.length>0){resourceId=allResources[0].id;}"
        "  const startTime=new Date(chosen.start).toTimeString().slice(0,8);"
        "  const endTime=new Date(chosen.end).toTimeString().slice(0,8);"
        "  const payload={org_id:ORG,bot_id:BOT,customer_name:name,customer_email:email,customer_phone:phone,booking_date:date,start_time:startTime,end_time:endTime,resource_id:resourceId,form_data:formData};"
        "  const h={'Content-Type':'application/json'};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;"
        "  const btn=document.getElementById('submit');btn.disabled=true;btn.textContent='Booking...';"
        "  try{"
        "    const r=await fetch(API+'/api/bookings',{method:'POST',headers:h,body:JSON.stringify(payload)});"
        "    if(!r.ok){const d=await r.json().catch(()=>({}));showMsg('Error: '+(d.detail||r.status),'error');btn.disabled=false;btn.textContent='Book Appointment';return;}"
        "    const d=await r.json();"
        "    const calStatus=d.calendar_synced?' ✓ Added to Calendar':' (Calendar sync pending)';"
        "    showMsg('✓ Booking Confirmed!\\nBooking ID: '+d.id+calStatus,'success');btn.textContent='Success';"
        "    const startDisplay=date+' '+startTime;"
        "    const endDisplay=date+' '+endTime;"
        "    const confirmMsg='Booked your appointment for '+name+' on '+date+' at '+startTime+'. Booking ID: '+d.id+(d.calendar_synced?' ✓ Added to Google Calendar':'');"
        "    if(window.parent&&window.parent.postMessage){window.parent.postMessage({type:'BOOKING_SUCCESS',id:d.id,start:startDisplay,end:endDisplay,message:confirmMsg,calendarSynced:d.calendar_synced},'*');}"
        "    try{loadSlots();}catch(e){}"
        "    setTimeout(()=>window.close(),2000);"
        "  }catch(e){console.error(e);showMsg('Request failed','error');btn.disabled=false;btn.textContent='Book Appointment';}"
        "}"
        
        "loadFormConfig();"
        "</script>"
        "</body></html>"
    )
    return html

@router.get("/reschedule/{bot_id}", response_class=HTMLResponse)
def reschedule_form(bot_id: str, org_id: str, bot_key: Optional[str] = None):
    base = getattr(settings, 'PUBLIC_API_BASE_URL', '') or ''
    api_url = base.rstrip('/')
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Reschedule Appointment</title>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1\">"
        "<style>"
        "*{margin:0;padding:0;box-sizing:border-box}"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f6f7f9;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:12px}"
        ".container{background:#fff;border-radius:14px;box-shadow:0 12px 32px rgba(0,0,0,0.12);max-width:560px;width:100%;padding:24px;max-height:92vh;overflow-y:auto;overflow-x:hidden}"
        ".header{margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}"
        ".header h1{font-size:22px;font-weight:800;color:#111;margin-bottom:2px}"
        ".header p{font-size:12px;color:#666}"
        ".steps{display:flex;gap:6px;align-items:center;overflow-x:auto;-webkit-overflow-scrolling:touch;padding-bottom:4px}"
        ".step{padding:6px 10px;border-radius:999px;background:#e9eaec;color:#444;font-size:12px;font-weight:700}"
        ".step.active{background:#111;color:#fff}"
        ".form-group{margin-bottom:20px}"
        ".form-group label{display:block;font-size:13px;font-weight:600;color:#333;margin-bottom:8px;text-transform:uppercase;letter-spacing:0.5px}"
        ".form-group input,.form-group select,.form-group textarea{width:100%;padding:12px 14px;border:2px solid #e5e7eb;border-radius:10px;font-size:14px;transition:all 0.3s ease;font-family:inherit;background:#fafafa}"
        ".form-group input:focus,.form-group select:focus,.form-group textarea:focus{outline:none;border-color:#22c1c3;box-shadow:0 0 0 3px rgba(34,193,195,0.15)}"
        ".form-group textarea{min-height:80px;resize:vertical}"
        ".form-group.required label:after{content:' *';color:#dc2626}"
        ".help-text{font-size:11px;color:#6b7280;margin-top:4px}"
        ".radio-group,.checkbox-group{display:flex;flex-direction:column;gap:8px}"
        ".radio-option{display:flex;align-items:center;gap:8px;padding:8px;border:2px solid #e5e7eb;border-radius:8px;cursor:pointer;transition:all 0.2s}"
        ".radio-option:hover{border-color:#22c1c3;background:#f0fdfa}"
        ".radio-option input{margin:0}"
        ".section{margin-bottom:16px;padding:16px;border:1px solid #eee;border-radius:12px;background:#fff}"
        ".section:last-of-type{border-bottom:none}"
        ".section-title{font-size:16px;font-weight:700;color:#333;margin-bottom:16px}"
        ".grid{display:grid;grid-template-columns:1fr;gap:16px}"
        "@media(min-width:760px){.grid{grid-template-columns:1fr 1fr}}"
        ".time-slots{display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:10px;margin-top:12px}"
        ".time-slot{padding:12px;border:2px solid #e5e7eb;border-radius:12px;background:#f9fafb;cursor:pointer;text-align:center;font-size:13px;font-weight:700;color:#333;transition:all 0.2s ease}"
        ".time-slot:hover{border-color:#111;background:#f2f4f7}"
        ".time-slot.selected{background:#22c1c3;color:#fff;border-color:#22c1c3}"
        ".time-slot .cap{display:block;font-size:11px;color:#666;margin-top:4px}"
        ".slot-status{font-size:13px;color:#666;padding:12px;text-align:center;background:#f5f5f5;border-radius:8px;margin-top:12px}"
        ".button-group{display:flex;gap:12px;margin-top:24px}"
        ".btn{padding:12px 18px;border:none;border-radius:10px;font-size:14px;font-weight:800;cursor:pointer;transition:all 0.25s ease}"
        ".btn.primary{flex:1;background:#22c1c3;color:#fff}"
        ".btn.secondary{background:#374151;color:#fff}"
        ".btn:hover{transform:translateY(-1px)}"
        ".btn:disabled{opacity:0.6;cursor:not-allowed}"
        "#out{margin-top:16px;padding:14px;border-radius:8px;font-size:14px;font-weight:600;display:none}"
        "#out.success{background:#d1fae5;color:#065f46;border-left:4px solid #10b981;display:block}"
        "#out.error{background:#fee2e2;color:#7f1d1d;border-left:4px solid #dc2626;display:block}"
        "#out.info{background:#dbeafe;color:#1e40af;border-left:4px solid #3b82f6;display:block}"
        "@media(max-width:480px){"
        "  .container{padding:16px}"
        "  .header h1{font-size:20px}"
        "  .section{padding:12px}"
        "  .form-group input,.form-group select{padding:10px 12px}"
        "  .time-slots{grid-template-columns:repeat(auto-fill,minmax(80px,1fr));gap:8px}"
        "  .button-group{flex-wrap:wrap}"
        "  .btn{width:100%}"
        "}"
        "@media(max-width:360px){"
        "  .time-slots{grid-template-columns:repeat(auto-fill,minmax(72px,1fr));gap:6px}"
        "  .step{padding:5px 8px;font-size:11px}"
        "}"
        "</style>"
        "</head><body>"
        "<div class=\"container\">"
        "<div class=\"header\"><div><h1>Reschedule Appointment</h1><p>Enter your appointment ID and pick a new time</p></div><div class=\"steps\"><div class=\"step active\" id=\"st1\">1. Enter ID</div><div class=\"step\" id=\"st2\">2. Review</div><div class=\"step\" id=\"st3\">3. New Time</div></div></div>"
        "<div id=\"form-container\">"
        "<div class=\"section\">"
        "<div class=\"form-group\"><label>Appointment ID</label><input id=\"booking_id\" type=\"number\" placeholder=\"e.g., 123\"></div>"
        "<div class=\"button-group\"><button id=\"load\" type=\"button\" class=\"btn primary\">Load Details</button></div>"
        "</div>"
        "<div class=\"grid\">"
        "<div class=\"section\" id=\"details\" style=\"display:none\">"
        "<div class=\"section-title\">Current Details</div>"
        "<div id=\"current\"></div>"
        "</div>"
        "<div class=\"section\" id=\"rescheduler\" style=\"display:none\">"
        "<div class=\"section-title\">Select Date, Time & Doctor/Service</div>"
        "<div class=\"form-group\"><label>Date</label><input id=\"booking_date\" type=\"date\"></div>"
        "<div class=\"form-group\"><label>Doctor/Service</label><select id=\"resource_select\"><option value=\"\">Current</option></select></div>"
        "<div class=\"time-slots\" id=\"slots\"></div>"
        "<div class=\"slot-status\" id=\"slot-status\" style=\"display:none\"></div>"
        "</div>"
        "</div>"
        "<div class=\"button-group\" id=\"actions\" style=\"display:none\"><button id=\"submit\" type=\"button\" class=\"btn primary\" disabled>Reschedule</button></div>"
        "<div id=\"out\"></div>"
        "</div>"
        "</div>"
        "<script>"
        "const ORG='" + org_id + "',BOT='" + bot_id + "',BOT_KEY='" + (bot_key or '') + "',API='" + api_url + "';"
        "let current=null,chosen=null,resourcesByType={},resourceIndex=null,allResources=[],slotPoll=null;"
        "function showMsg(t,ty){const o=document.getElementById('out');o.textContent=t;o.className=ty;o.style.display='block';}"
        "function startSlotPolling(){try{if(slotPoll)clearInterval(slotPoll);}catch(e){}slotPoll=setInterval(()=>{try{if(document.visibilityState==='visible')loadSlots();}catch(e){}},15000);}"
        "async function loadResources(){"
        "  try{"
        "    const h={};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;"
        "    const r=await fetch(API+'/api/resources/'+BOT,{headers:h});"
        "    if(!r.ok)return;"
        "    const data=await r.json();"
        "    allResources=(data.resources||[]);"
        "    resourcesByType=allResources.reduce((acc,r)=>{acc[r.resource_type]=acc[r.resource_type]||[];acc[r.resource_type].push(r);return acc;},{});"
        "    resourceIndex=allResources.reduce((m,r)=>{m.ids[r.id]=r;if(r.resource_code)m.codes[r.resource_code]=r;m.names[(r.resource_name||'').toLowerCase()]=r;return m;},{ids:{},codes:{},names:{}});"
        "    const sel=document.getElementById('resource_select');"
        "    sel.innerHTML='<option value=\"\">Current</option>';"
        "    allResources.forEach(r=>{const opt=document.createElement('option');opt.value=r.id;opt.textContent=r.resource_name;sel.appendChild(opt);});"
        "  }catch(e){}"
        "}"
        "async function loadBooking(){"
        "  const id=parseInt(document.getElementById('booking_id').value,10);"
        "  if(!id){showMsg('Enter a valid appointment ID','error');return;}"
        "  const h={};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;"
        "  try{"
        "    current=null;"
        "    document.getElementById('details').style.display='none';"
        "    document.getElementById('rescheduler').style.display='none';"
        "    document.getElementById('actions').style.display='none';"
        "    (document.getElementById('current')||{}).innerHTML='';"
        "    const r=await fetch(API+'/api/booking/'+id,{headers:h});"
        "    if(!r.ok){showMsg('Booking not found','error'); if(window.parent&&window.parent.postMessage){window.parent.postMessage({type:'RESCHEDULE_BLOCKED',message:'Booking not found'},'*');} return;}"
        "    current=await r.json();"
        "    document.getElementById('st1').classList.add('active');"
        "    document.getElementById('st2').classList.add('active');"
        "    try{"
        "      var status=(current.status||'').toLowerCase();"
        "      var end=new Date((current.booking_date||'')+'T'+(current.end_time||'00:00:00'));"
        "      var now=new Date();"
        "      if(status==='cancelled'){"
        "        showMsg('Cancelled appointment cannot be rescheduled.','error');"
        "        if(window.parent&&window.parent.postMessage){window.parent.postMessage({type:'RESCHEDULE_BLOCKED',message:'Cancelled appointment cannot be rescheduled.'},'*');}"
        "        document.getElementById('details').style.display='block';"
        "        document.getElementById('rescheduler').style.display='none';"
        "        document.getElementById('actions').style.display='none';"
        "        const cur=document.getElementById('current');"
        "        cur.innerHTML='<div class=\"form-group\"><label>Name</label><input type=\"text\" value=\"'+(current.customer_name||'')+'\" disabled></div>'+"
        "                     '<div class=\"form-group\"><label>Email</label><input type=\"text\" value=\"'+(current.customer_email||'')+'\" disabled></div>'+"
        "                     '<div class=\"form-group\"><label>Current Doctor/Service</label><input type=\"text\" value=\"'+(current.resource_name||'')+'\" disabled></div>'+"
        "                     '<div class=\"form-group\"><label>Current Date</label><input type=\"text\" value=\"'+(current.booking_date||'')+'\" disabled></div>'+"
        "                     '<div class=\"form-group\"><label>Current Time</label><input type=\"text\" value=\"'+(current.start_time||'')+' - '+(current.end_time||'')+'\" disabled></div>';"
        "        return;"
        "      }"
        "      if(status==='completed' || (end && !isNaN(end.getTime()) && end.getTime()<=now.getTime())){"
        "        showMsg('Past appointment cannot be rescheduled.','error');"
        "        if(window.parent&&window.parent.postMessage){window.parent.postMessage({type:'RESCHEDULE_BLOCKED',message:'Past appointment cannot be rescheduled.'},'*');}"
        "        document.getElementById('details').style.display='block';"
        "        document.getElementById('rescheduler').style.display='none';"
        "        document.getElementById('actions').style.display='none';"
        "        const cur=document.getElementById('current');"
        "        cur.innerHTML='<div class=\"form-group\"><label>Name</label><input type=\"text\" value=\"'+(current.customer_name||'')+'\" disabled></div>'+"
        "                     '<div class=\"form-group\"><label>Email</label><input type=\"text\" value=\"'+(current.customer_email||'')+'\" disabled></div>'+"
        "                     '<div class=\"form-group\"><label>Current Doctor/Service</label><input type=\"text\" value=\"'+(current.resource_name||'')+'\" disabled></div>'+"
        "                     '<div class=\"form-group\"><label>Current Date</label><input type=\"text\" value=\"'+(current.booking_date||'')+'\" disabled></div>'+"
        "                     '<div class=\"form-group\"><label>Current Time</label><input type=\"text\" value=\"'+(current.start_time||'')+' - '+(current.end_time||'')+'\" disabled></div>';"
        "        return;"
        "      }"
        "    }catch(e){}"
        "    document.getElementById('details').style.display='block';"
        "    const cur=document.getElementById('current');"
        "    cur.innerHTML='<div class=\"form-group\"><label>Name</label><input type=\"text\" value=\"'+(current.customer_name||'')+'\" disabled></div>'+"
        "                 '<div class=\"form-group\"><label>Email</label><input type=\"text\" value=\"'+(current.customer_email||'')+'\" disabled></div>'+"
        "                 '<div class=\"form-group\"><label>Current Doctor/Service</label><input type=\"text\" value=\"'+(current.resource_name||'')+'\" disabled></div>'+"
        "                 '<div class=\"form-group\"><label>Current Date</label><input type=\"text\" value=\"'+(current.booking_date||'')+'\" disabled></div>'+"
        "                 '<div class=\"form-group\"><label>Current Time</label><input type=\"text\" value=\"'+(current.start_time||'')+' - '+(current.end_time||'')+'\" disabled></div>';"
        "    document.getElementById('rescheduler').style.display='block';"
        "    document.getElementById('actions').style.display='flex';"
        "    const d=document.getElementById('booking_date');"
        "    const todayIso=new Date().toISOString().slice(0,10);"
        "    d.value=(current.booking_date||todayIso);"
        "    d.setAttribute('min', todayIso);"
        "    document.getElementById('st3').classList.add('active');"
        "    document.getElementById('submit').disabled=true;"
        "    await loadResources();"
        "    try{"
        "      var end=new Date((current.booking_date||'')+'T'+(current.end_time||'00:00:00'));"
        "      var now=new Date();"
        "      if(end && !isNaN(end.getTime()) && end.getTime()<=now.getTime()){"
        "        showMsg('This appointment has already passed and is marked completed. Only upcoming appointments can be rescheduled.','info');"
        "        document.getElementById('rescheduler').style.display='none';"
        "        document.getElementById('actions').style.display='none';"
        "        return;"
        "      }"
        "    }catch(e){}"
        "    await loadSlots();startSlotPolling();"
        "  }catch(e){showMsg('Error loading booking','error');}"
        "}"
        "async function loadSlots(){"
        "  const dt=document.getElementById('booking_date').value;"
        "  if(!dt||!current)return;"
        "  chosen=null;document.getElementById('submit').disabled=true;"
        "  const h={};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;"
        "  const el=document.getElementById('slots'),st=document.getElementById('slot-status');"
        "  el.innerHTML='';st.innerHTML='<span class=\"loading-spinner\"></span> Loading...';st.style.display='block';"
        "  const hasResources=allResources&&allResources.length>0;"
        "  let resourceId=document.getElementById('resource_select').value||current.resource_id||null;"
        "  if(hasResources&&!resourceId){st.textContent='Please select a service or doctor first';st.style.display='block';return;}"
        "  const url=resourceId?(API+'/api/resources/'+resourceId+'/available-slots?booking_date='+dt):(API+'/api/bots/'+BOT+'/available-slots?booking_date='+dt);"
        "  try{"
        "    const r=await fetch(url,{headers:h});"
        "    if(!r.ok){st.textContent='Error loading slots';return;}"
        "    const d=await r.json();const slots=(d.slots||[]).filter(s=>Number(s.available_capacity||0)>0);"
        "    const now=new Date();"
        "    const upcoming=(slots||[]).filter(s=>{"
        "      try{"
        "        return new Date(dt+'T'+(s.start_time||'00:00:00'))>now;"
        "      }catch(e){return true;}"
        "    });"
        "    if(upcoming.length===0){st.textContent='No upcoming slots for this date';return;}"
        "    st.style.display='none';"
        "    upcoming.forEach(s=>{"
        "      const b=document.createElement('button');b.type='button';b.className='time-slot';"
        "      const [h0,m0]=s.start_time.split(':');"
        "      const hNum=parseInt(h0,10);const ampm=hNum>=12?'PM':'AM';const h12=hNum%12||12;"
        "      const cap=s.available_capacity;"
        "      b.innerHTML=h12+':'+(m0||'00')+' '+ampm+(cap?('<span class=\"cap\">'+cap+' available</span>'):'');"
        "      b.onclick=()=>{"
        "        chosen={start:dt+'T'+s.start_time,end:dt+'T'+s.end_time};"
        "        document.querySelectorAll('.time-slot').forEach(x=>x.classList.remove('selected'));"
        "        b.classList.add('selected');"
        "        document.getElementById('submit').disabled=false;"
        "      };"
        "      el.appendChild(b);"
        "    });"
        "  }catch(e){st.textContent='Error: '+e.message;}"
        "}"
        "async function submitReschedule(){"
        "  if(!current){showMsg('Load an appointment first','error');return;}"
        "  if(!chosen){showMsg('Select a time slot','error');return;}"
        "  const id=current.id;"
        "  const date=document.getElementById('booking_date').value;"
        "  const startTime=new Date(chosen.start).toTimeString().slice(0,8);"
        "  const endTime=new Date(chosen.end).toTimeString().slice(0,8);"
        "  const resourceId=document.getElementById('resource_select').value||current.resource_id||null;"
        "  const payload={org_id:ORG,booking_date:date,start_time:startTime,end_time:endTime,resource_id:resourceId};"
        "  const h={'Content-Type':'application/json'};if(BOT_KEY)h['X-Bot-Key']=BOT_KEY;"
        "  const btn=document.getElementById('submit');btn.disabled=true;btn.textContent='Rescheduling...';"
        "  try{"
        "    const r=await fetch(API+'/api/bookings/'+id+'/reschedule',{method:'POST',headers:h,body:JSON.stringify(payload)});"
        "    const d=await r.json().catch(()=>({}));"
        "    if(!r.ok){showMsg('Error: '+(d.detail||r.status),'error');btn.disabled=false;btn.textContent='Reschedule';return;}"
        "    const calStatus=d.calendar_synced?' ✓ Updated in Calendar':' (Calendar sync pending)';"
        "    showMsg('✓ Rescheduled! ID: '+d.id+calStatus,'success');btn.textContent='Success';"
        "    const startDisplay=date+' '+startTime; const endDisplay=date+' '+endTime;"
        "    if(window.parent&&window.parent.postMessage){window.parent.postMessage({type:'RESCHEDULE_SUCCESS',id:d.id,start:startDisplay,end:endDisplay,message:'Rescheduled your appointment to '+date+' '+startTime+' - '+endTime+'. ID: '+d.id},'*');}"
        "    setTimeout(()=>window.close(),2000);"
        "  }catch(e){showMsg('Request failed','error');btn.disabled=false;btn.textContent='Reschedule';}"
        "}"
        "document.getElementById('load').addEventListener('click',loadBooking);"
        "document.getElementById('resource_select').addEventListener('change',()=>{loadSlots();startSlotPolling();});"
        "document.getElementById('booking_date').addEventListener('change',()=>{loadSlots();startSlotPolling();});"
        "document.getElementById('submit').addEventListener('click',submitReschedule);"
        "</script>"
        "</body></html>"
    )
    return html

@router.get("/bots/{bot_id}/calendar/events")
def list_calendar_events(bot_id: str, org_id: str, time_min_iso: str, time_max_iso: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    _rate_limit(bot_id, org_id, limit=600, window_seconds=60)
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(org_id), org_id, bot_id, "google"),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc = row
        from app.services.calendar_google import _decrypt, build_service_from_tokens, list_events_oauth
        at = _decrypt(at_enc) if at_enc else None
        rt = _decrypt(rt_enc) if rt_enc else None
        svc = build_service_from_tokens(at or "", rt, None)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service error")
        items = list_events_oauth(svc, cal_id or "primary", time_min_iso, time_max_iso)
        # Augment with appointment details from DB so frontend shows clear titles/descriptions
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "select id, external_event_id, attendees_json from bot_appointments where (org_id=%s or org_id::text=%s) and bot_id=%s and start_iso>=%s and end_iso<=%s",
                    (normalize_org_id(org_id), org_id, bot_id, time_min_iso, time_max_iso),
                )
                rows = cur.fetchall() or []
            amap = {}
            for r in rows:
                ap_id = int(r[0]); ext = r[1]; att = r[2]
                name = ""; email = ""; phone = ""; notes = ""
                try:
                    import json
                    info = json.loads(att) if isinstance(att, str) else (att if isinstance(att, dict) else {})
                    name = info.get("name") or ""
                    email = info.get("email") or ""
                    phone = info.get("phone") or ""
                    notes = info.get("notes") or ""
                except Exception:
                    pass
                amap[ext] = {"summary": f"Appointment #{ap_id} - {name}", "description": f"Appointment ID: {ap_id}\nName: {name}\nEmail: {email}\nPhone: {phone}\nNotes: {notes}"}
            for it in (items or []):
                ext = it.get("id")
                if ext and ext in amap:
                    meta = amap[ext]
                    # Override summary/description for clarity in dashboard modal
                    it["summary"] = meta["summary"]
                    it["description"] = meta["description"]
        except Exception:
            pass
        return {"events": items}
    finally:
        conn.close()

class BookingRequestBody(BaseModel):
    org_id: str
    summary: str
    start_iso: str
    end_iso: str
    attendees: Optional[List[str]] = None

 

@router.post("/bots/{bot_id}/booking/book")
def booking_book(bot_id: str, body: BookingRequestBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    _rate_limit(bot_id, body.org_id)
    from app.db import get_conn, normalize_org_id
    from datetime import datetime
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        _ensure_booking_settings_table(conn)
        
        with conn.cursor() as cur:
            # Get calendar OAuth config
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where bot_id=%s and provider=%s",
                (bot_id, "google"),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="calendar not connected")
            cal_id, at_enc, rt_enc = row
            
        at = __import__("app.services.calendar_google", fromlist=["_decrypt"])._decrypt(at_enc) if at_enc else None
        rt = __import__("app.services.calendar_google", fromlist=["_decrypt"])._decrypt(rt_enc) if rt_enc else None
        svc = __import__("app.services.calendar_google", fromlist=["build_service_from_tokens"]).build_service_from_tokens(at or "", rt, None)
        if not svc:
            raise HTTPException(status_code=500, detail="calendar service error")
        
        try:
            c2 = psycopg.connect(settings.SUPABASE_DB_DSN, autocommit=False)
        except Exception:
            c2 = conn
        try:
            with c2.cursor() as cur2:
                # Parse start and end times
                start_dt = datetime.fromisoformat(body.start_iso.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(body.end_iso.replace('Z', '+00:00'))
                
                # Extract date and time components
                booking_date = start_dt.date()
                start_time = start_dt.time()
                end_time = end_dt.time()
                
                # Get customer info from attendees
                customer_name = body.summary.replace("Appointment: ", "") if body.summary else "Test User"
                customer_email = body.attendees[0] if body.attendees and len(body.attendees) > 0 else None
                
                # Insert into bookings table
                cur2.execute(
                    """
                    insert into bookings (bot_id, form_config_id, customer_name, customer_email, booking_date, start_time, end_time, status)
                    values (%s, (select id from form_configurations where bot_id = %s limit 1), %s, %s, %s, %s, %s, %s)
                    returning id
                    """,
                    (bot_id, bot_id, customer_name, customer_email, booking_date, start_time, end_time, "booked"),
                )
                rid = int(cur2.fetchone()[0])
                
                # Create Google Calendar event
                ext_id = __import__("app.services.calendar_google", fromlist=["create_event_oauth"]).create_event_oauth(
                    svc, cal_id or "primary", body.summary, body.start_iso, body.end_iso, body.attendees if body.attendees else None, None
                )
                if not ext_id:
                    raise Exception("calendar create failed")
                
                # Update booking with external event ID
                cur2.execute("update bookings set external_event_id=%s where id=%s", (ext_id, rid))
            
            try:
                c2.commit()
            except Exception:
                pass
            return {"scheduled": True, "appointment_id": rid, "external_event_id": ext_id}
        except Exception as e:
            try:
                c2.rollback()
            except Exception:
                pass
            raise HTTPException(status_code=500, detail=f"booking failed: {str(e)}")
        finally:
            try:
                if c2 is not conn:
                    c2.close()
            except Exception:
                pass
    finally:
        conn.close()

class CancelBody(BaseModel):
    org_id: str
    appointment_id: int

@router.post("/bots/{bot_id}/booking/cancel")
def booking_cancel(bot_id: str, body: CancelBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    _rate_limit(bot_id, body.org_id)
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        with conn.cursor() as cur:
            # Get booking from bookings table
            cur.execute("select coalesce(calendar_event_id, external_event_id) from bookings where id=%s and bot_id=%s", (body.appointment_id, bot_id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="booking not found")
            ext_id = row[0]
            
            # Get calendar OAuth config
            cur.execute("select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where bot_id=%s and provider=%s", (bot_id, "google"))
            cr = cur.fetchone()
            
            # Delete from Google Calendar if event exists
            if ext_id and cr:
                from app.services.calendar_google import _decrypt, build_service_from_tokens, delete_event_oauth
                at = _decrypt(cr[1]) if cr[1] else None
                rt = _decrypt(cr[2]) if cr[2] else None
                svc = build_service_from_tokens(at or "", rt, None)
                if svc:
                    delete_event_oauth(svc, (cr[0] or "primary"), ext_id)
            
            # Update booking status
            cur.execute("update bookings set status='cancelled' where id=%s", (body.appointment_id,))
            conn.commit()
                
        return {"cancelled": True}
    finally:
        conn.close()

class RescheduleBody(BaseModel):
    org_id: str
    appointment_id: int
    start_iso: str
    end_iso: str

@router.post("/bots/{bot_id}/booking/reschedule")
def booking_reschedule(bot_id: str, body: RescheduleBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    _rate_limit(bot_id, body.org_id)

@router.get("/bots/{bot_id}/booking/appointments")
def booking_list(bot_id: str, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    _rate_limit(bot_id, org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Get bookings from bookings table (dynamic forms system)
            cur.execute("""
                select b.id, b.customer_name, b.booking_date, b.start_time, b.end_time, 
                       b.status, b.customer_email, b.customer_phone, b.notes, b.form_data,
                       coalesce(b.calendar_event_id, b.external_event_id) as external_event_id,
                       b.calendar_event_id,
                       r.resource_name
                from bookings b
                left join booking_resources r on b.resource_id = r.id
                where b.bot_id = %s
                order by b.created_at desc
            """, (bot_id,))
            bookings = cur.fetchall()
            
            # Convert bookings to response format
            rows = []
            for db in bookings:
                booking_id, cust_name, booking_date, start_time, end_time, status, email, phone, notes, form_data, ext_event_id, cal_event_id, resource_name = db
                summary = f"Appointment: {cust_name}"
                if resource_name:
                    summary += f" with {resource_name}"
                start_iso = f"{booking_date}T{start_time}"
                end_iso = f"{booking_date}T{end_time}"
                attendees_json = {"name": cust_name, "email": email, "phone": phone, "notes": notes, "form_data": form_data}
                rows.append((booking_id, summary, start_iso, end_iso, ext_event_id, status, attendees_json, cal_event_id))
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(org_id), org_id, bot_id, "google"),
            )
            oauth_row = cur.fetchone()
        import json
        def _parse_attendees(raw):
            if raw is None:
                return {}
            if isinstance(raw, dict):
                return raw
            try:
                return json.loads(raw)
            except Exception:
                return {}
        def _flatten(info: dict):
            return {
                "name": info.get("name"),
                "email": info.get("email"),
                "phone": info.get("phone"),
                "notes": info.get("notes") or info.get("reason") or info.get("note"),
                "info": info,
            }
        svc = None; cal_id = None
        if oauth_row:
            try:
                from app.services.calendar_google import _decrypt, build_service_from_tokens, get_event_oauth
                cal_id = oauth_row[0]
                at = _decrypt(oauth_row[1]) if oauth_row[1] else None
                rt = _decrypt(oauth_row[2]) if oauth_row[2] else None
                svc = build_service_from_tokens(at, rt, oauth_row[3])
            except Exception:
                svc = None
        def _merge_with_desc(info: dict, ev):
            if not ev:
                return info
            desc = ev.get("description") or ""
            lines = desc.splitlines()
            out = dict(info)
            for ln in lines:
                l = ln.strip()
                if l.lower().startswith("name:") and not out.get("name"):
                    out["name"] = l.split(":",1)[1].strip()
                elif l.lower().startswith("email:") and not out.get("email"):
                    out["email"] = l.split(":",1)[1].strip()
                elif l.lower().startswith("phone:") and not out.get("phone"):
                    out["phone"] = l.split(":",1)[1].strip()
                elif l.lower().startswith("notes:") and not out.get("notes"):
                    out["notes"] = l.split(":",1)[1].strip()
            return out
        appts = []
        for r in rows:
            info = _parse_attendees(r[6])
            
            # Fetch full event details from Google Calendar to get description with form data
            event_description = None
            if svc and r[4]:  # if we have a service and external_event_id
                try:
                    from app.services.calendar_google import get_event_oauth
                    ev = get_event_oauth(svc, cal_id or "primary", r[4])
                    if ev:
                        event_description = ev.get("description", "")
                        # Also merge basic info from description if needed
                        info = _merge_with_desc(info, ev)
                except Exception as e:
                    print(f"Could not fetch event {r[4]}: {str(e)}")
            
            appts.append({
                "id": int(r[0]),
                "summary": r[1],
                "start_iso": r[2],
                "end_iso": r[3],
                "external_event_id": r[4],
                "status": r[5],
                "name": info.get("name"),
                "email": info.get("email"),
                "phone": info.get("phone"),
                "notes": info.get("notes"),
                "form_data": info.get("form_data"),
                "event_description": event_description,
                "info": info,
                "calendar_event_id": r[7],
            })
        return {"appointments": appts}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/booking/appointment/{appointment_id}")
def booking_get(bot_id: str, appointment_id: int, org_id: str, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, org_id)
    _rate_limit(bot_id, org_id)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "select id, summary, start_iso, end_iso, external_event_id, status, attendees_json from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s",
                (appointment_id, normalize_org_id(org_id), org_id, bot_id),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            cur.execute(
                "select calendar_id, access_token_enc, refresh_token_enc, token_expiry from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(org_id), org_id, bot_id, "google"),
            )
            oauth_row = cur.fetchone()
        import json
        info = {}
        try:
            info = row[6] if isinstance(row[6], dict) else (json.loads(row[6]) if row[6] else {})
        except Exception:
            info = {}
        missing = not info.get("name") or not info.get("email") or not info.get("phone") or not info.get("notes")
        if missing and oauth_row:
            try:
                from app.services.calendar_google import _decrypt, build_service_from_tokens, get_event_oauth
                cal_id = oauth_row[0]
                at = _decrypt(oauth_row[1]) if oauth_row[1] else None
                rt = _decrypt(oauth_row[2]) if oauth_row[2] else None
                svc = build_service_from_tokens(at, rt, oauth_row[3])
                ev = get_event_oauth(svc, cal_id or "primary", row[4]) if svc and row[4] else None
                if ev and (ev.get("description")):
                    desc = ev.get("description") or ""
                    for ln in desc.splitlines():
                        l = ln.strip()
                        if l.lower().startswith("name:") and not info.get("name"):
                            info["name"] = l.split(":",1)[1].strip()
                        elif l.lower().startswith("email:") and not info.get("email"):
                            info["email"] = l.split(":",1)[1].strip()
                        elif l.lower().startswith("phone:") and not info.get("phone"):
                            info["phone"] = l.split(":",1)[1].strip()
                        elif l.lower().startswith("notes:") and not info.get("notes"):
                            info["notes"] = l.split(":",1)[1].strip()
            except Exception:
                pass
        return {
            "id": int(row[0]),
            "summary": row[1],
            "start_iso": row[2],
            "end_iso": row[3],
            "external_event_id": row[4],
            "status": row[5],
            "name": info.get("name"),
            "email": info.get("email"),
            "phone": info.get("phone"),
            "notes": info.get("notes") or info.get("reason") or info.get("note"),
            "info": info,
        }
    finally:
        conn.close()
    conn = get_conn()
    try:
        _ensure_oauth_table(conn)
        with conn.cursor() as cur:
            cur.execute("select external_event_id from bot_appointments where id=%s and (org_id=%s or org_id::text=%s) and bot_id=%s", (body.appointment_id, normalize_org_id(body.org_id), body.org_id, bot_id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="appointment not found")
            ext_id = row[0]
            cur.execute("select calendar_id, access_token_enc, refresh_token_enc from bot_calendar_oauth where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s", (normalize_org_id(body.org_id), body.org_id, bot_id, "google"))
            cr = cur.fetchone()
        from app.services.calendar_google import _decrypt, build_service_from_tokens, update_event_oauth
        at = _decrypt(cr[1]) if cr and cr[1] else None
        rt = _decrypt(cr[2]) if cr and cr[2] else None
        svc = build_service_from_tokens(at or "", rt, None)
        ok = update_event_oauth(svc, (cr[0] or "primary"), ext_id, {"start": {"dateTime": body.start_iso}, "end": {"dateTime": body.end_iso}}) if (svc and ext_id) else False
        with conn.cursor() as cur:
            cur.execute("update bot_appointments set start_iso=%s, end_iso=%s, status='scheduled', updated_at=now() where id=%s", (body.start_iso, body.end_iso, body.appointment_id))
        return {"rescheduled": True, "updated_external": bool(ok)}
    finally:
        conn.close()

@router.post("/bots/{bot_id}/calendar/event")
def create_calendar_event(bot_id: str, body: CreateEventBody, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization, body.org_id)
    conn = get_conn()
    try:
        _ensure_calendar_settings_table(conn)
        _ensure_appointments_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "select calendar_id from bot_calendar_settings where (org_id=%s or org_id::text=%s) and bot_id=%s and provider=%s",
                (normalize_org_id(body.org_id), body.org_id, bot_id, "google"),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                raise HTTPException(status_code=400, detail="Calendar not configured")
            cal_id = row[0]
            cur.execute(
                """
                insert into bot_appointments (org_id, bot_id, summary, start_iso, end_iso, attendees_json)
                values (%s,%s,%s,%s,%s,%s)
                returning id
                """,
                (normalize_org_id(body.org_id), bot_id, body.summary, body.start_iso, body.end_iso, None if body.attendees is None else __import__("json").dumps(body.attendees)),
            )
            rid = cur.fetchone()[0]
        ext_id = None
        try:
            from app.services.calendar_google import create_event as _g_create
            ext_id = _g_create(cal_id, body.summary, body.start_iso, body.end_iso, body.attendees, None)
        except Exception:
            ext_id = None
        return {"scheduled": True, "appointment_id": int(rid), "calendar_id": cal_id, "external_event_id": ext_id}
    finally:
        conn.close()

@router.get("/bots/{bot_id}/embed")
def get_embed_snippet(bot_id: str, org_id: str, widget: str = "bubble", authorization: Optional[str] = Header(default=None), x_bot_key: Optional[str] = Header(default=None)):
    conn = get_conn()
    try:
        _ensure_public_api_key_columns(conn)
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "select public_api_key, welcome_message from chatbots where id=%s and (org_id=%s or org_id::text=%s)",
                    (bot_id, normalize_org_id(org_id), org_id),
                )
                row = cur.fetchone()
                key = row[0] if row else None
                welcome = row[1] if row else None
            except Exception:
                cur.execute(
                    "select NULL as public_api_key, NULL as welcome_message",
                )
                r2 = cur.fetchone()
                key = r2[0] if r2 else None
                welcome = r2[1] if r2 else None
        # If a public API key exists and X-Bot-Key header is provided, ensure it matches
        if key:
            if x_bot_key and x_bot_key != key:
                raise HTTPException(status_code=403, detail="Invalid bot key")
        # If Authorization is provided, validate org access
        if authorization:
            try:
                _require_auth(authorization, org_id)
            except HTTPException as e:
                # Allow unauthenticated retrieval of embed snippet if no Authorization header
                if authorization:
                    raise
        # Bot key optional: if present, widget will use it; otherwise unauthenticated
        base = settings.PUBLIC_API_BASE_URL.rstrip("/")
        url = f"{base}/api/chat/stream/{bot_id}"
        theme = settings.WIDGET_THEME
        wmsg = welcome or ""
        wmsg_js = wmsg.replace("\\", "\\\\").replace("'", "\\'")
        def cdn():
            js = (
                "<!-- Chatbot widget: required botId, orgId, apiBase; optional botKey -->"
                f"<script>(function(){{var C=window.chatbotConfig||{{}};window.chatbotConfig=Object.assign({{}},C,{{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',greeting:'{wmsg_js}',botName:(C.botName||''),icon:(C.icon||'')}});}})();</script>"
                "<!-- Optional keys: botName (header/button), icon (emoji/avatar), welcome/greeting (first bot message) -->"
                f"<script src='{base}/api/widget.js' async></script>"
            )
            return js
        def bubble():
            js = (
                "<!-- Bubble widget: fixed position bubble -->"
                f"<script>(function(){{var C=window.chatbotConfig||{{}};window.chatbotConfig=Object.assign({{}},C,{{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',greeting:'{wmsg_js}',mode:'bubble',botName:(C.botName||''),icon:(C.icon||'')}});}})();</script>"
                f"<script src='{base}/api/widget.js' async></script>"
            )
            return js
        def inline():
            js = (
                "<!-- Inline widget: embedded in page -->"
                "<div id=\"bot-inline\"></div>"
                f"<script>(function(){{var C=window.chatbotConfig||{{}};window.chatbotConfig=Object.assign({{}},C,{{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',greeting:'{wmsg_js}',mode:'inline',containerId:'bot-inline',botName:(C.botName||''),icon:(C.icon||'')}});}})();</script>"
                f"<script src='{base}/api/widget.js' async></script>"
            )
            return js
        def iframe():
            js = (
                "<!-- Iframe widget: self-contained script -->"
                f"<script>(function(){{var C=window.chatbotConfig||{{}};window.chatbotConfig=Object.assign({{}},C,{{botId:'{bot_id}',orgId:'{org_id}',apiBase:'{base}',botKey:'{key or ''}',greeting:'{wmsg_js}',botName:(C.botName||''),icon:(C.icon||'')}});}})();</script>"
                f"<script src='{base}/api/widget.js' async></script>"
            )
            return js
        snippet = cdn() if widget == "cdn" else bubble() if widget == "bubble" else inline() if widget == "inline" else iframe()
        return {"snippet": snippet, "widget": widget}
    finally:
        conn.close()

from fastapi.responses import PlainTextResponse
# import settings

@router.get("/widget.js", response_class=PlainTextResponse)
def widget_js():
    base = settings.PUBLIC_API_BASE_URL.rstrip("/")
    theme = settings.WIDGET_THEME
    
    js = (
        "(function(){\n"
        "  var C=window.chatbotConfig||{};"
        "  var B=C.botId,O=C.orgId;"
        "  var A=C.apiBase||'"+base+"';"
        "  var K=C.botKey||null;"
        "  var T='"+theme+"';"
        "  var W=(C.welcome||C.greeting||'Hello! How can I help you?');"
        "  var N=C.botName||'Chatbot';"
        "  var I=C.icon||'';"
        "  var POS=C.position||'right';"
        "  var AUTO=C.autoOpen||false;"
        "  var MODE=C.mode||'bubble';"
        "  var CONTAINER=C.containerId||'bot-inline';"
        "  var ACC=C.buttonColor||C.accent||'#2563eb';"
        "  // Contrast auto-adjust helper (prevents light accent on light card in dark mode)\n"
        "  try{(function(){function _hexToRgb(h){h=h.replace(/#/,'');if(h.length===3){h=h.split('').map(x=>x+x).join('');}var num=parseInt(h,16);return {r:(num>>16)&255,g:(num>>8)&255,b:num&255};}function _lum(c){var r=c.r/255,g=c.g/255,b=c.b/255;[r,g,b]=[r,g,b].map(v=>{return v<=0.03928? v/12.92: Math.pow((v+0.055)/1.055,2.4);});return 0.2126*r+0.7152*g+0.0722*b;}function _isHex(x){return /^#?[0-9a-f]{3,6}$/i.test(x);}if(T==='dark'){if(_isHex(ACC)){var rgb=_hexToRgb(ACC);if(_lum(rgb)>0.7){ACC='#3b82f6';}}if(_isHex(BG)){var rgbBG=_hexToRgb(BG);if(_lum(rgbBG)>0.2){BG='#0b111a';}}if(_isHex(CARD)){var rgbCARD=_hexToRgb(CARD);var rgbBG2=_hexToRgb(BG.replace('#',''));if(Math.abs(_lum(rgbCARD)-_lum(rgbBG2))<0.04){CARD='#162131';}}}})();}catch(__){}\n"
        "  // Dark / Light palette with stronger dark contrasts\n"
        "  var BG=C.bg||((T==='dark')?'#0b111a':'#ffffff');"
        "  var CARD=C.card||((T==='dark')?'#162131':'#ffffff');"
        "  var TEXT=C.text||((T==='dark')?'#f1f5f9':'#0f1724');"
        "  var MUTED=C.muted||((T==='dark')?'#7a8694':'#64748b');"
        "  var BORDER=C.border||((T==='dark')?'rgba(255,255,255,0.12)':'rgba(16,24,40,0.06)');"
        "  var ME=C.bubbleMe||((T==='dark')?'linear-gradient(180deg,#3b82f6,#1e3a8a)':'linear-gradient(180deg,#2563eb,#1e40af)');"
        "  var BOT=C.bubbleBot||((T==='dark')?'rgba(255,255,255,0.06)':'#ffffff');"
        "  try{ if(T==='dark' && BOT===BG){ BOT='rgba(255,255,255,0.06)'; } }catch(__){}\n"
        "  var SHADOW=C.shadow||((T==='dark')?'0 24px 72px rgba(0,0,0,0.65),0 8px 24px rgba(0,0,0,0.45)':'0 10px 30px rgba(0,0,0,0.15)');"
        "  var RADIUS=(C.radius!==undefined?C.radius+'px':'12px');"
        "  var LSIZE=(C.launcherSize||56);"
        "  var ISCALE=(C.iconScale||60);"
        "  var TRANSPARENT=C.transparentBubble||false;"
        "  var BN='CodeWeft';"
        "  var BL='https://github.com/CodeWeft-Technologies';\n"
        "  if(!O){console.warn('Chatbot: OrgId missing');return;}\n"
        "  var busy=false;\n"
        "  var SHOW_BADGE=(C.showButtonTyping===undefined)?true:!!C.showButtonTyping;\n"
        "  // Generate or retrieve session ID from localStorage\n"
        "  var SESSION_KEY='chatbot_session_'+O+'_'+B;\n"
        "  var SESSION_ID=(function(){\n"
        "    try{\n"
        "      var stored=localStorage.getItem(SESSION_KEY);\n"
        "      if(stored){\n"
        "        var parsed=JSON.parse(stored);\n"
        "        var age=Date.now()-parsed.created;\n"
        "        if(age<24*60*60*1000)return parsed.id;\n"
        "      }\n"
        "    }catch(__){}\n"
        "    var newId='sess_'+Date.now()+'_'+Math.random().toString(36).substr(2,9);\n"
        "    try{localStorage.setItem(SESSION_KEY,JSON.stringify({id:newId,created:Date.now()}));}catch(__){}\n"
        "    return newId;\n"
        "  })();\n"
        "  var BTN_BG=TRANSPARENT?'transparent':'linear-gradient(135deg, '+ACC+', color-mix(in srgb, '+ACC+' 80%, black))';"
        "  var BTN_SHADOW=TRANSPARENT?'none':'0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08)';"
        "  // --- CSS Injection ---\n"
        "  var __cw_css = `\n"
        "    :root {\n"
        "      --cb-right: ${POS==='left'?'auto':'20px'};\n"
        "      --cb-left: ${POS==='left'?'20px':'auto'};\n"
        "      --cb-origin: ${POS==='left'?'left bottom':'right bottom'};\n"
        "      --cb-accent: ${ACC};\n"
        "      --cb-bg: ${BG};\n"
        "      --cb-card: ${CARD};\n"
        "      --cb-text: ${TEXT};\n"
        "      --cb-muted: ${MUTED};\n"
        "      --cb-border: ${BORDER};\n"
        "      --cb-bubble-me: ${ME};\n"
        "      --cb-bubble-bot: ${BOT};\n"
        "      --cb-shadow: ${SHADOW};\n"
        "      --cb-radius: ${RADIUS};\n"
        "      --cb-lsize: ${LSIZE}px;\n"
        "      --cb-icon-scale: ${ISCALE}%;\n"
        "      --cb-icon-fs: ${ISCALE*0.4}px;\n"
        "      --cb-btn-bg: ${BTN_BG};\n"
        "      --cb-btn-shadow: ${BTN_SHADOW};\n"
        "      --cb-mode: ${T};\n"
        "    }\n"
        "    :root[data-cb-theme='dark'] { color-scheme:dark; }\n"
        "    .cb-btn { position:fixed; bottom:20px; right:var(--cb-right); left:var(--cb-left); width:var(--cb-lsize); height:var(--cb-lsize); border-radius:var(--cb-radius); border:none; background:var(--cb-btn-bg); display:flex; align-items:center; justify-content:center; cursor:pointer; z-index:99999; box-shadow:var(--cb-btn-shadow); transition:all .3s cubic-bezier(0.4, 0, 0.2, 1); backdrop-filter:blur(10px); -webkit-backdrop-filter:blur(10px); }\n"
        "    .cb-btn:hover { transform:translateY(-2px) scale(1.05); box-shadow:0 12px 36px rgba(0,0,0,0.16), 0 4px 12px rgba(0,0,0,0.12); }\n"
        "    .cb-btn:active { transform:translateY(0) scale(0.98); }\n"
        "    .cb-btn svg { width:var(--cb-icon-scale); height:var(--cb-icon-scale); display:block; fill:#fff; filter:drop-shadow(0 2px 4px rgba(0,0,0,0.1)); }\n"
        "    .cb-emoji { font-size:var(--cb-icon-fs); line-height:1; filter:drop-shadow(0 2px 4px rgba(0,0,0,0.1)); }\n"
        "    .cb-badge { position:absolute; top:-4px; right:-4px; min-width:24px; height:18px; padding:0 6px; border-radius:999px; display:none; align-items:center; justify-content:center; background:linear-gradient(135deg, #ef4444, #dc2626); color:#fff; box-shadow:0 4px 12px rgba(239,68,68,0.4); z-index:999999; font-size:10px; font-weight:700; }\n"
        "    .cb-badge .dot { width:4px; height:4px; border-radius:50%; background:#fff; display:inline-block; margin:0 1px; opacity:.6; animation:badge-dot 1.2s ease-in-out infinite; }\n"
        "    .cb-badge .dot:nth-child(2) { animation-delay:.15s; } .cb-badge .dot:nth-child(3) { animation-delay:.3s; }\n"
        "    @keyframes badge-dot { 0%,100%{transform:translateY(0) scale(1);opacity:.6} 50%{transform:translateY(-4px) scale(1.1);opacity:1} }\n"
        "    .cb-panel { position:fixed; bottom:85px; right:var(--cb-right); left:var(--cb-left); width:380px; max-width:calc(100vw - 24px); max-height:min(550px, calc(100vh - 120px)); border-radius:var(--cb-radius); overflow:hidden; display:none; flex-direction:column; z-index:99998; box-shadow:0 20px 60px rgba(0,0,0,0.2), 0 8px 24px rgba(0,0,0,0.12); background:var(--cb-bg); border:1px solid var(--cb-border); transform-origin:var(--cb-origin); opacity:0; transform:translateY(16px) scale(0.95); transition:all .3s cubic-bezier(0.4, 0, 0.2, 1); }\n"
        "    @media (max-width: 480px) { .cb-panel { width:calc(100vw - 16px); max-height:calc(100vh - 100px); bottom:75px; } .cb-btn { width:52px; height:52px; bottom:16px; } }\n"
        "    .cb-head { display:flex; align-items:center; justify-content:space-between; padding:14px 18px; border-bottom:1px solid var(--cb-border); background:linear-gradient(135deg, var(--cb-card), color-mix(in srgb, var(--cb-card) 97%, black)); backdrop-filter:blur(10px); }\n"
        "    .cb-title { font-weight:700; font-size:15px; color:var(--cb-text); display:flex; align-items:center; gap:8px; letter-spacing:-0.01em; }\n"
        "    .cb-body { height:min(400px, calc(100vh - 280px)); overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:12px; background:var(--cb-bg); scroll-behavior:smooth; }\n"
        "    @media (max-width: 480px) { .cb-body { height:min(350px, calc(100vh - 220px)); padding:12px; gap:10px; } .cb-head { padding:12px 14px; } .cb-title { font-size:14px; } }\n"
        "    .cb-body::-webkit-scrollbar { width:6px; }\n"
        "    .cb-body::-webkit-scrollbar-track { background:transparent; }\n"
        "    .cb-body::-webkit-scrollbar-thumb { background:var(--cb-border); border-radius:999px; }\n"
        "    .cb-body::-webkit-scrollbar-thumb:hover { background:var(--cb-muted); }\n"
        "    .cb-input { display:flex; gap:10px; padding:14px 16px; border-top:1px solid var(--cb-border); background:var(--cb-card); backdrop-filter:blur(10px); }\n"
        "    .cb-input input { flex:1; padding:10px 14px; border-radius:calc(var(--cb-radius) - 4px); border:1.5px solid var(--cb-border); background:var(--cb-bg); color:var(--cb-text); outline:none; font-size:13px; transition:all .2s ease; }\n"
        "    @media (max-width: 480px) { .cb-input { padding:12px 14px; gap:8px; } .cb-input input { padding:9px 12px; font-size:13px; } }\n"
        "    .cb-input input:focus { border-color:var(--cb-accent); box-shadow:0 0 0 3px color-mix(in srgb, var(--cb-accent) 10%, transparent); }\n"
        "    .cb-input input::placeholder { color:var(--cb-muted); }\n"
        "    .cb-send { padding:10px 18px; border-radius:calc(var(--cb-radius) - 4px); border:none; background:linear-gradient(135deg, var(--cb-accent), color-mix(in srgb, var(--cb-accent) 85%, black)); color:#fff; font-weight:600; cursor:pointer; font-size:13px; transition:all .2s ease; box-shadow:0 2px 8px color-mix(in srgb, var(--cb-accent) 30%, transparent); }\n"
        "    @media (max-width: 480px) { .cb-send { padding:9px 16px; font-size:13px; } }\n"
        "    .cb-send:hover { transform:translateY(-1px); box-shadow:0 4px 12px color-mix(in srgb, var(--cb-accent) 40%, transparent); }\n"
        "    .cb-send:active { transform:translateY(0); }\n"
        "    .cb-send:disabled { opacity:0.5; cursor:not-allowed; }\n"
        "    .cb-footer { padding:8px 14px; font-size:10px; color:var(--cb-muted); text-align:center; background:var(--cb-card); border-top:1px solid var(--cb-border); }\n"
        "    @media (max-width: 480px) { .cb-footer { padding:6px 12px; font-size:9px; } }\n"
        "    .cb-footer a { color:var(--cb-accent); text-decoration:none; font-weight:600; transition:opacity .2s; }\n"
        "    .cb-footer a:hover { opacity:0.8; }\n"
        "    .row { display:flex; width:100%; animation:slideUp .3s ease; }\n"
        "    @keyframes slideUp { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }\n"
        "    .bubble { max-width:82%; padding:11px 14px; border-radius:calc(var(--cb-radius) + 4px); line-height:1.5; font-size:13px; word-break:break-word; box-shadow:0 2px 12px rgba(0,0,0,0.06); position:relative; transition:all .2s ease; }\n"
        "    @media (max-width: 480px) { .bubble { max-width:85%; padding:10px 12px; font-size:13px; } }\n"
        "    .bubble:hover { box-shadow:0 4px 16px rgba(0,0,0,0.1); }\n"
        "    .bubble.me { margin-left:auto; background:var(--cb-bubble-me); color:#fff; border-bottom-right-radius:6px; box-shadow:0 2px 12px color-mix(in srgb, var(--cb-accent) 20%, transparent); }\n"
        "    .bubble.bot { margin-right:auto; background:var(--cb-bubble-bot); color:var(--cb-text); border:1.5px solid var(--cb-border); border-bottom-left-radius:6px; }\n"
        "    .bubble pre { background:rgba(0,0,0,0.05); padding:10px 12px; border-radius:8px; overflow-x:auto; margin:8px 0; font-family:'Courier New',monospace; font-size:13px; border:1px solid var(--cb-border); }\n"
        "    .bubble code { background:rgba(0,0,0,0.06); padding:3px 6px; border-radius:6px; font-size:13px; font-family:'Courier New',monospace; }\n"
        "    .bubble.bot pre { background:rgba(0,0,0,0.03); color:var(--cb-text); }\n"
        "    .bubble a { color:inherit; text-decoration:underline; font-weight:600; }\n"
        "    .typing { display:inline-flex; align-items:flex-end; gap:5px; padding:8px 10px; }\n"
        "    .typing .dot { width:7px; height:7px; border-radius:50%; background:var(--cb-muted); animation:dot 1.4s ease-in-out infinite; }\n"
        "    .typing .dot:nth-child(2){animation-delay:.2s} .typing .dot:nth-child(3){animation-delay:.4s}\n"
        "    @keyframes dot{0%,100%{transform:translateY(0) scale(1);opacity:.5}50%{transform:translateY(-8px) scale(1.1);opacity:1}}\n"
        "  `;\n"
        "  try{var s=document.createElement('style');s.innerHTML=__cw_css;document.head.appendChild(s);}catch(_){}\n"

        "  function applyTheme(){\n"
        "    var root=document.documentElement;\n"
        "    try{\n"
        "      var BTN_BG=TRANSPARENT?'transparent':'linear-gradient(135deg, '+ACC+', color-mix(in srgb, '+ACC+' 80%, black))';"
        "      var BTN_SHADOW=TRANSPARENT?'none':'0 8px 32px rgba(0,0,0,0.12), 0 2px 8px rgba(0,0,0,0.08)';"
        "      root.style.setProperty('--cb-btn-bg', BTN_BG);\n"
        "      root.style.setProperty('--cb-btn-shadow', BTN_SHADOW);\n"
        "      root.style.setProperty('--cb-right', (POS==='left'?'auto':'20px'));\n"
        "      root.style.setProperty('--cb-left', (POS==='left'?'20px':'auto'));\n"
        "      root.style.setProperty('--cb-origin', (POS==='left'?'left bottom':'right bottom'));\n"
        "      root.style.setProperty('--cb-accent', ACC);\n"
        "      root.style.setProperty('--cb-bg', BG);\n"
        "      root.style.setProperty('--cb-card', CARD);\n"
        "      root.style.setProperty('--cb-text', TEXT);\n"
        "      root.style.setProperty('--cb-muted', MUTED);\n"
        "      root.style.setProperty('--cb-border', BORDER);\n"
        "      root.style.setProperty('--cb-bubble-me', ME);\n"
        "      root.style.setProperty('--cb-bubble-bot', BOT);\n"
        "      root.style.setProperty('--cb-shadow', SHADOW);\n"
        "      root.style.setProperty('--cb-radius', RADIUS);\n"
        "      root.style.setProperty('--cb-lsize', LSIZE+'px');\n"
        "      root.style.setProperty('--cb-icon-scale', ISCALE+'%');\n"
        "      root.style.setProperty('--cb-icon-fs', (ISCALE*0.4)+'px');\n"
        "      root.setAttribute('data-cb-theme', T);\n"
        "    }catch(__){ }\n"
        "  }\n"
        "  function refreshConfig(){\n"
        "    var C=window.chatbotConfig||{};\n"
        "    N = (C.title||C.name||C.botName||N);\n"
        "    I = (C.icon!==undefined?C.icon:I);\n"
        "    POS = (C.position||POS);\n"
        "    T = (C.theme||T);\n"
        "    ACC=(C.buttonColor||C.accent||ACC); BG=(C.bg||BG); CARD=(C.card||CARD); TEXT=(C.text||TEXT); MUTED=(C.muted||MUTED); BORDER=(C.border||BORDER); ME=(C.bubbleMe||ME); BOT=(C.bubbleBot||BOT); SHADOW=(C.shadow||SHADOW); RADIUS=(C.radius!==undefined?(C.radius+'px'):RADIUS);\n"
        "    LSIZE=(C.launcherSize||LSIZE); ISCALE=(C.iconScale||ISCALE); TRANSPARENT=(C.transparentBubble!==undefined?C.transparentBubble:TRANSPARENT);\n"
        "    applyTheme();\n"
        "    try{ alignPanel(); }catch(__){ }\n"
        "    try{ var t=panel.querySelector('.cb-title'); if(t){ t.textContent=N||'Chatbot'; } }catch(__){ }\n"
        "    if(footer){ footer.style.display='block'; footer.innerHTML='Powered by <a href=\"https://codeweft.in\" target=\"_blank\" style=\"color:inherit;text-decoration:none;font-weight:600;\">CodeWeft</a>'; try{ Object.defineProperty(footer, 'innerHTML', { writable: false, configurable: false }); Object.defineProperty(footer.style, 'display', { value: 'block', writable: false, configurable: false }); }catch(__){ } }\n"
        "  }\n"
        "  try{ window.Chatbot = window.Chatbot || {}; window.Chatbot.updateConfig = function(partial){ var C=window.chatbotConfig||{}; window.chatbotConfig=Object.assign({},C,partial); refreshConfig(); }; }catch(__){ }\n"
        "  applyTheme();\n"
        "  if(footer){ footer.style.display='block'; footer.innerHTML='Powered by <a href=\"https://codeweft.in\" target=\"_blank\" style=\"color:inherit;text-decoration:none;font-weight:600;\">CodeWeft</a>'; try{ Object.defineProperty(footer, 'innerHTML', { writable: false, configurable: false }); Object.defineProperty(footer.style, 'display', { value: 'block', writable: false, configurable: false }); }catch(__){ } }\n"

        "  // --- Markdown Parser ---\n"
        "  function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}\n"
        "  function md(s){\n"
        "     var t=esc(s);\n"
        "     t=t.replace(/```([\\s\\S]*?)```/g,function(_,c){return '<pre><code>'+c+'</code></pre>';});\n"
        "     t=t.replace(/`([^`]+)`/g,'<code>$1</code>');\n"
        "     t=t.replace(/\\*\\*([^*]+)\\*\\*/g,'<strong>$1</strong>');\n"
        "     t=t.replace(/\[(.*?)\]\s*\(([\s\S]*?)\)/g,function(_,txt,url){var u=(url||'').replace(/[\"']/g,'').trim();return '<a href=\"'+u+'\" style=\"color:inherit;text-decoration:underline\">'+txt+'</a>';});\n"
        "     t=t.replace(/https?:\\/\\/[^\s<)]+/g,function(u,idx,s){var pre=s.slice(Math.max(0,idx-12),idx); if(pre.indexOf('href=')>-1) return u; var pre2=pre.replace(/\s+/g,''); if(/\]\($/.test(pre2)) return u; var uu=(u||'').replace(/[\"']/g,'');return '<a href=\"'+uu+'\" style=\"color:inherit;text-decoration:underline\">'+u+'</a>';});\n"
        "     t=t.replace(/(?:^|\\n)[*-]\\s+(.*)/g,'<div style=\"display:flex;gap:6px\"><span>•</span><span>$1</span></div>');\n"
        "     t=t.replace(/(?:^|\\n)•\\s+(.*)/g,'<div style=\"display:flex;gap:6px\"><span>•</span><span>$1</span></div>');\n"
        "     t=t.replace(/(?:^|\\n)\\s*={3,}\\s*(?:\\n|$)/g,'<hr style=\"border:none;border-top:1px solid var(--cb-border);margin:8px 0\">');\n"
        "     t=t.replace(/(?:^|\\n)(APPOINTMENT DETAILS|FORM DETAILS)\\s*(?:\\n|$)/g,function(_,h){return '\\n<div style=\"font-weight:700;color:var(--cb-text);margin:6px 0 4px;letter-spacing:0.02em;text-transform:uppercase\">'+h+'</div>\\n';});\n"
        "     t=t.replace(/(^|\\n)\\s*data:\\s*/g,'$1');\n"
        "     t=t.replace(/\\n\\n/g,'<br><br>');\n"
        "     t=t.replace(/\\n/g,'<br>');\n"
        "     return t;\n"
        "  }\n"
        "  function normalizeWords(t){\n"
        "    if(!t) return t;\n"
        "    t=t.replace(/\\b([A-HJ-Z])\\s+([a-z]{2,})\\b/g,'$1$2');\n"
        "    t=t.replace(/\\b([a-z]{3,})\\s+(ing|tion|sion|ment|less|ness|able|ible|ally|fully|ial|ional|tions|ments|ings|ware|care)\\b/g,'$1$2');\n"
        "    t=t.replace(/\\b(multi|pre|re|con|inter|trans|sub|super|over|under|non|anti|auto|bio|cyber|data|micro|macro|hyper)\\s+([a-z]{3,})\\b/g,'$1$2');\n"
        "    return t;\n"
        "  }\n"
        "  function joinToken(acc,t){\n"
        "    var token=String(t||'');\n"
        "    if(!acc) return token;\n"
        "    return acc+token;\n"
        "  }\n"

        "  // --- UI Elements ---\n"
        "  var btn = document.createElement('button');\n"
        "  btn.className = 'cb-btn';\n"
        "  btn.setAttribute('aria-label', 'Open chat');\n"
        
        "  // **UPDATED ICON LOGIC**\n"
        "  // 1. Check if Icon is URL (http/data). 2. Check if Icon exists (Emoji/Text). 3. Default SVG.\n"
        "  if(I && (I.indexOf('http')===0 || I.indexOf('data:image')===0)){\n"
        "     var img = document.createElement('img'); img.src=I; img.style.objectFit='cover';\n"
        "     if(TRANSPARENT){ img.style.width=ISCALE+'%'; img.style.height=ISCALE+'%'; img.style.borderRadius=RADIUS; }\n"
        "     else { img.style.width=ISCALE+'%'; img.style.height=ISCALE+'%'; img.style.borderRadius='50%'; }\n"
        "     btn.appendChild(img);\n"
        "  } else if (I) {\n"
        "     var spn = document.createElement('span'); spn.className='cb-emoji'; spn.textContent=I;\n"
        "     btn.appendChild(spn);\n"
        "  } else {\n"
        "     btn.innerHTML = '<svg viewBox=\"0 0 24 24\" fill=\"none\" xmlns=\"http://www.w3.org/2000/svg\"><path d=\"M12 3C7.03 3 3 6.69 3 11c0 2.5 1.45 4.73 3.8 6.05L6 21l4.3-1.64c.9.2 1.85.31 2.7.31 4.97 0 9-3.69 9-8.01S16.97 3 12 3Z\"/></svg>';\n"
        "  }\n"
        "  if(MODE!=='inline'){ document.body.appendChild(btn); }\n"

        "  var badge = document.createElement('span');\n"
        "  badge.className='cb-badge';\n"
        "  badge.innerHTML='<span class=\"dot\"></span><span class=\"dot\"></span><span class=\"dot\"></span>';\n"
        "  btn.appendChild(badge);\n"

        "  var panel = document.createElement('div');\n"
        "  panel.className = 'cb-panel';\n"
        "  panel.innerHTML = `\n"
        "    <div class=\"cb-head\">\n"
        "      <div class=\"cb-title\">\n"
        "        `+(I?'<span style=\"font-size:20px;line-height:1\">'+(I.indexOf('http')===0?'<img src=\"'+I+'\" style=\"width:24px;height:24px;border-radius:50%\">':I)+'</span> ':'') + N +`\n"
        "      </div>\n"
        "      <button class=\"cb-close\" style=\"background:transparent;border:none;font-size:20px;color:var(--cb-text);cursor:pointer;line-height:1\">×</button>\n"
        "    </div>\n"
        "    <div class=\"cb-body\"></div>\n"
        "    <div class=\"cb-input\">\n"
        "      <input type=\"text\" placeholder=\"Ask a question...\">\n"
        "      <button class=\"cb-send\">Send</button>\n"
        "    </div>\n"
        "    <div class=\"cb-footer\"></div>\n"
        "  `;\n"
        "  var mount = (MODE==='inline' ? (document.getElementById(CONTAINER)||document.body) : document.body);\n"
        "  mount.appendChild(panel);\n"

        "  var body = panel.querySelector('.cb-body');\n"
        "  var input = panel.querySelector('input');\n"
        "  var sendBtn = panel.querySelector('.cb-send');\n"
        "  var closeBtn = panel.querySelector('.cb-close');\n"
        "  var footer = panel.querySelector('.cb-footer');\n"
        "  if(footer){ footer.style.display='block'; footer.innerHTML='Powered by <a href=\"https://codeweft.in\" target=\"_blank\" style=\"color:var(--cb-accent);text-decoration:none;font-weight:600;transition:opacity .2s;\">CodeWeft</a>'; try{ Object.defineProperty(footer,'innerHTML',{writable:false,configurable:false}); Object.defineProperty(footer.style,'display',{value:'block',writable:false,configurable:false}); }catch(__){} }\n"
        "  var shownWelcome=false;\n"
        "  var opened=false;\n"
        "  function getW(){ var C=window.chatbotConfig||{}; return (C.welcome||C.greeting||''); }\n"

        "  // --- Logic ---\n"
        "  function alignPanel(){\n"
        "     var br = btn.getBoundingClientRect();\n"
        "     if(POS==='left'){\n"
        "        btn.style.left='24px'; btn.style.right='auto';\n"
        "        panel.style.left=Math.max(8,br.left)+'px'; panel.style.right='auto'; panel.style.transformOrigin='left bottom';\n"
        "     } else {\n"
        "        btn.style.right='24px'; btn.style.left='auto';\n"
        "        panel.style.right=Math.max(8,window.innerWidth-br.right)+'px'; panel.style.left='auto'; panel.style.transformOrigin='right bottom';\n"
        "     }\n"
        "     panel.style.bottom = (window.innerHeight - br.top + 12) + 'px';\n"
        "  }\n"
        "  setTimeout(alignPanel, 100); window.addEventListener('resize', alignPanel);\n"

        "  function open(){\n"
        "    alignPanel();\n"
        "    panel.style.display='flex';\n"
        "    requestAnimationFrame(function(){ panel.style.opacity='1'; panel.style.transform='translateY(0) scale(1)'; });\n"
        "    var W0=getW(); if(body.childNodes.length===0 && W0){ addMsg('bot', W0); shownWelcome=true; }\n"
        "    opened=true;\n"
        "    input.focus();\n"
        "  }\n"
        "  function close(){\n"
        "    opened=false;\n"
        "    panel.style.opacity='0'; panel.style.transform='translateY(10px) scale(0.98)';\n"
        "    setTimeout(function(){ panel.style.display='none'; }, 200);\n"
        "  }\n"

        "  function addMsg(type, text){\n"
        "     var r = document.createElement('div'); r.className='row';\n"
        "     var b = document.createElement('div'); b.className='bubble '+(type==='me'?'me':'bot');\n"
        "     if(text) b.innerHTML = md(text);\n"
        "     r.appendChild(b); body.appendChild(r);\n"
        "     body.scrollTop = body.scrollHeight;\n"
        "     return b;\n"
        "  }\n"
        "  function openPopup(u){ body.style.display='none'; var inpDiv=panel.querySelector('.cb-input'); if(inpDiv)inpDiv.style.display='none'; if(footer)footer.style.display='none'; panel.style.height = '550px'; var frm=document.createElement('div'); frm.className='cb-form-layer'; frm.style.flex='1'; frm.style.display='flex'; frm.style.flexDirection='column'; frm.style.background=BG; var hd=document.createElement('div'); hd.style.padding='8px 12px'; hd.style.borderBottom='1px solid '+BORDER; hd.style.display='flex'; hd.style.alignItems='center'; hd.style.gap='10px'; hd.style.background=CARD; var back=document.createElement('button'); back.innerHTML='&#8592; Back'; back.style.background='transparent'; back.style.border='none'; back.style.color=ACC; back.style.fontWeight='600'; back.style.cursor='pointer'; back.style.fontSize='13px'; var title=document.createElement('span'); title.style.fontWeight='600'; title.style.fontSize='14px'; title.textContent=(u.indexOf('reschedule')>-1?'Reschedule':'Booking'); hd.appendChild(back); hd.appendChild(title); frm.appendChild(hd); var fr=document.createElement('iframe'); fr.src=u+(u.indexOf('?')>-1?'&':'?')+'session_id='+encodeURIComponent(SESSION_ID); fr.style.flex='1'; fr.style.border='none'; frm.appendChild(fr); panel.insertBefore(frm, footer); function closeForm(){ frm.remove(); body.style.display='flex'; if(inpDiv)inpDiv.style.display='flex'; if(footer)footer.style.display='block'; panel.style.height = ''; window._cbCloseForm=null; } back.onclick=closeForm; window._cbCloseForm=closeForm; }\n"
        "  body.addEventListener('click', function(e){ var a=e.target.closest('a'); if(!a) return; var href=a.getAttribute('href')||''; if(href.indexOf('/api/form/')>-1 || href.indexOf('/api/reschedule/')>-1){ e.preventDefault(); openPopup(href); } });\n"
        "  window.addEventListener('message', function(e){ var d=e.data; if(d && (d.type==='appointment-booked'||d.type==='BOOKING_SUCCESS'||d.type==='RESCHEDULE_SUCCESS'||d.type==='RESCHEDULE_BLOCKED'||d.type==='LEAD_SUBMITTED')){ if(d.message){ addMsg('bot', d.message); }else if(d.type==='RESCHEDULE_SUCCESS'){ addMsg('bot', 'Rescheduled your appointment to '+(d.start||'')+' - '+(d.end||'')+'. ID: '+(d.id||'')); }else if(d.type==='LEAD_SUBMITTED'){ addMsg('bot', 'Thanks! Your enquiry has been submitted. Reference ID: '+(d.id||'')); }else{ addMsg('bot', 'Booked your appointment for '+(d.start||'')+' to '+(d.end||'')+'. ID: '+d.id); } if(window._cbCloseForm){ window._cbCloseForm(); } try{ var ov=document.querySelector('.cb-popup'); if(ov){ ov.remove(); } }catch(__){} } });\n"
        "  function setBadge(on){\n"
        "    if(!SHOW_BADGE) return;\n"
        "    badge.style.display = on ? 'inline-flex' : 'none';\n"
        "  }\n"

        "  function sendApi(m, onchunk){\n"
        "     var h={'Content-Type':'application/json'};\n"
        "     if(K) h['X-Bot-Key']=K;\n"
        "     var payload=JSON.stringify({message:m, org_id:O, session_id:SESSION_ID});\n"
        "     fetch(A+'/api/chat/stream/'+B, {method:'POST',headers:h,body:payload})\n"
        "     .then(function(r){\n"
        "         var rd=r.body.getReader(); var d=new TextDecoder(); var buf='';\n"
        "         function pump(){\n"
        "            rd.read().then(function(x){\n"
        "               if(x.done){ onchunk(null,true); return; }\n"
        "               buf += d.decode(x.value);\n"
        "               var idx=buf.indexOf('\\n\\n');\n"
        "               while(idx>-1){\n"
        "                  var l=buf.slice(0,idx);\n"
        "                  buf=buf.slice(idx+2);\n"
        "                  if(l.indexOf('data: ')===0){ onchunk(l.replace(/^data:\\s*/,''), false); }\n"
        "                  else if(l.indexOf('event: end')===0){ onchunk(null,true); }\n"
        "                  idx=buf.indexOf('\\n\\n');\n"
        "               }\n"
        "               pump();\n"
        "            });\n"
        "         } pump();\n"
        "     }).catch(function(e){ onchunk('Error connecting.', true); });\n"
        "  }\n"

        "  function doSend(){\n"
        "     if(busy) return;\n"
        "     var txt = input.value.trim(); if(!txt) return;\n"
        "     var m0 = txt.toLowerCase();\n"
        "     var isGreet = (m0==='hi'||m0==='hello'||m0==='hey'||m0==='hola'||m0==='hii'||m0.startsWith('hi ')||m0.startsWith('hello ')||m0.startsWith('hey '));\n"
        "     var W0=getW(); if(isGreet && W0 && !shownWelcome){ input.value=''; addMsg('me', txt); addMsg('bot', W0); shownWelcome=true; input.focus(); return; }\n"
        "     busy = true; input.value=''; input.disabled=true; sendBtn.disabled=true;\n"
        "     addMsg('me', txt);\n"
        "     var botRow = document.createElement('div'); botRow.className='row';\n"
        "     var botBub = document.createElement('div'); botBub.className='bubble bot';\n"
        "     botBub.innerHTML = '<div class=\"typing\"><span class=\"dot\"></span><span class=\"dot\"></span><span class=\"dot\"></span></div>';\n"
        "     botRow.appendChild(botBub); body.appendChild(botRow); body.scrollTop=body.scrollHeight;\n"
        "     setBadge(true);\n"
        "     var acc = '';\n"
        "     sendApi(txt, function(token, end){\n"
        "        if(end){\n"
        "           busy=false; input.disabled=false; sendBtn.disabled=false; setBadge(false); input.focus();\n"
        "           return;\n"
        "        }\n"
        "        if(acc==='') botBub.innerHTML='';\n"
        "        acc = joinToken(acc, token);\n"
        "        botBub.innerHTML = md(normalizeWords(acc));\n"
        "        body.scrollTop = body.scrollHeight;\n"
        "     });\n"
        "  }\n"

        "  if(MODE!=='inline'){ btn.onclick = function(){ if(opened) close(); else open(); }; }\n"
        "  closeBtn.onclick = close;\n"
        "  sendBtn.onclick = doSend;\n"
        "  input.onkeydown = function(e){ if(e.key==='Enter' || e.keyCode===13){ e.preventDefault(); doSend(); } };\n"

        "  function isUuid(s){return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);}\n"
        "  function init(){\n"
        "    fetch(A+'/api/bots?org_id='+encodeURIComponent(O))\n"
        "    .then(r=>r.json()).then(d=>{\n"
        "       if(d.bots && d.bots.length > 0) {\n"
        "           var found=null;\n"
        "           if(B && isUuid(B)){ found = d.bots.find(function(x){return x.bot_id===B;}) || d.bots[0]; } else { B=d.bots[0].bot_id; found=d.bots[0]; }\n"
        "           var C=window.chatbotConfig||{};\n"
        "           if(!(C.welcome||C.greeting) && found.welcome_message){ W=found.welcome_message; window.chatbotConfig=Object.assign({},C,{welcome:found.welcome_message}); }\n"
        "           if(AUTO && !opened){ setTimeout(function(){ open(); }, 10); }\n"
        "        }\n"
        "    }).catch(e=>{});\n"
        "  }\n"
        "  init();\n"
        "  if(MODE==='inline'){ AUTO=true; }\n"
        "  if(AUTO){ setTimeout(function(){ open(); }, 100); }\n"
        "})();"
    )
    return js

@router.get("/api/widget.js", response_class=PlainTextResponse)
def widget_js_compat():
    return widget_js()

@router.get("/dashboard/{org_id}")
def dashboard(org_id: str):
    conn = get_conn()
    try:
        org_n = normalize_org_id(org_id)
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org_id))
            try:
                cur.execute(
                    "select id, behavior, system_prompt, public_api_key from chatbots where org_id::text in (%s,%s,%s)",
                    (org_n, org_id, nu),
                )
                bots = cur.fetchall()
            except Exception:
                cur.execute(
                    "select id, behavior, system_prompt from chatbots where org_id::text in (%s,%s,%s)",
                    (org_n, org_id, nu),
                )
                bots = cur.fetchall()
            cur.execute(
                "select bot_id, count(*) from rag_embeddings where (org_id=%s or org_id::text=%s or org_id=%s) group by bot_id",
                (org_n, org_id, nu),
            )
            counts = {r[0]: int(r[1]) for r in cur.fetchall()}
        items = []
        for b in bots:
            bid = b[0]
            beh = b[1]
            sys = b[2]
            k = b[3] if len(b) > 3 else None
            items.append({
                "bot_id": bid,
                "behavior": beh,
                "system_prompt": sys,
                "has_key": bool(k),
                "embedding_count": counts.get(bid, 0),
            })
        return {"bots": items}
    finally:
        conn.close()

@router.get("/dashboard/ui/{org_id}", response_class=HTMLResponse)
def dashboard_ui(org_id: str):
    html = (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>Dashboard</title>"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<style>body{font-family:system-ui,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #e5e7eb;padding:8px;text-align:left}code{background:#f3f4f6;padding:2px 4px;border-radius:4px}button{background:#0ea5e9;color:#fff;border:none;border-radius:6px;padding:8px 12px}input,select{padding:8px;border:1px solid #e5e7eb;border-radius:6px}#grid{display:grid;grid-template-columns:1fr 1fr;gap:24px}.bar{display:flex;gap:8px;align-items:center;margin-bottom:16px}</style></head><body>"
        f"<h1>Org {org_id} Dashboard</h1>"
        "<div class=\"bar\"><input id=\"email\" type=\"email\" placeholder=\"email\"><input id=\"password\" type=\"password\" placeholder=\"password\"><button id=\"login\">Login</button><span id=\"authmsg\" style=\"color:#6b7280;font-size:12px\"></span></div>"
        "<div id=\"grid\">"
        "<div><h2>Bots</h2><div id=\"bots\">Loading...</div></div>"
        "<div><h2>Usage</h2><div id=\"usage\">Select a bot</div><h2 style=\"margin-top:16px\">Test</h2><div id=\"test\">Select a bot</div></div>"
        "</div>"
        "<script>\n"
        "const ORG = '" + org_id + "';\n"
        "let TOKEN = localStorage.getItem('TOKEN') || '';\n"
        "function setToken(t){TOKEN=t||'';if(TOKEN){localStorage.setItem('TOKEN',TOKEN);document.getElementById('authmsg').textContent='Authenticated';}else{localStorage.removeItem('TOKEN');document.getElementById('authmsg').textContent='';}}\n"
        "async function api(path){const h = TOKEN?{Authorization:'Bearer '+TOKEN}:{ };const r=await fetch(path,{headers:h});if(r.status===401){document.getElementById('authmsg').textContent='Login required';throw new Error('unauthorized');}return await r.json();}\n"
        "document.getElementById('login').onclick=async()=>{const e=document.getElementById('email').value.trim();const p=document.getElementById('password').value;try{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:e,password:p})});if(!r.ok){document.getElementById('authmsg').textContent='Login failed';return;}const d=await r.json();setToken(d.token);loadBots();}catch(_){document.getElementById('authmsg').textContent='Login error';}};\n"
        "async function loadBots(){const data=await api('/api/bots?org_id='+ORG);const el=document.getElementById('bots');el.innerHTML='';"
        "const tbl=document.createElement('table');tbl.innerHTML='<thead><tr><th>Bot</th><th>Behavior</th><th>Has Key</th><th>Actions</th></tr></thead>';const tb=document.createElement('tbody');tbl.appendChild(tb);"
        "data.bots.forEach(b=>{const tr=document.createElement('tr');tr.innerHTML='<td>'+b.bot_id+'</td><td>'+b.behavior+'</td><td>'+(b.has_key?'yes':'no')+'</td><td></td>';const td=tr.querySelector('td:last-child');const btn=document.createElement('button');btn.textContent='Usage';btn.onclick=()=>loadUsage(b.bot_id);td.appendChild(btn);const snip=document.createElement('button');snip.textContent='Embed';snip.style.marginLeft='8px';snip.onclick=()=>loadSnippet(b.bot_id);td.appendChild(snip);const test=document.createElement('button');test.textContent='Test';test.style.marginLeft='8px';test.onclick=()=>loadTest(b.bot_id);td.appendChild(test);const cfg=document.createElement('button');cfg.textContent='Configure';cfg.style.marginLeft='8px';cfg.onclick=()=>loadConfig(b.bot_id);td.appendChild(cfg);tb.appendChild(tr);});el.appendChild(tbl);}\n"
        "async function loadUsage(bot){const d=await api('/api/usage/summary/'+ORG+'/'+bot+'?days=30');document.getElementById('usage').innerHTML='<p><b>Chats:</b> '+d.chats+' &nbsp; <b>Successes:</b> '+d.successes+' &nbsp; <b>Fallbacks:</b> '+d.fallbacks+' &nbsp; <b>Avg Similarity:</b> '+(Math.round(d.avg_similarity*100)/100)+'</p>'; }\n"
        "async function loadSnippet(bot){const d=await api('/api/bots/'+bot+'/embed?org_id='+ORG+'&widget=bubble');const el=document.getElementById('usage');el.innerHTML='';const pre=document.createElement('pre');pre.textContent=d.snippet;el.appendChild(pre);const frame=document.createElement('iframe');frame.style.width='100%';frame.style.height='540px';frame.style.border='1px solid #e5e7eb';const apiBase=location.origin;frame.srcdoc='<!doctype html><html><head><meta charset=\"utf-8\"></head><body><script>window.chatbotConfig={botId:\"'+bot+'\",orgId:\"'+ORG+'\",apiBase:\"'+apiBase+'\",mode:\"bubble\",accent:\"#2563eb\"};<\\/script><script src=\"'+apiBase+'/api/widget.js\" async><\\/script></body></html>';el.appendChild(frame);}\n"
        "async function loadConfig(bot){const el=document.getElementById('usage');el.textContent='Loading config...';const cfg=await api('/api/bots/'+bot+'/config?org_id='+ORG);el.innerHTML='';const wrap=document.createElement('div');const lbl=document.createElement('label');lbl.textContent='Greeting (welcome) message';const br=document.createElement('br');const inp=document.createElement('input');inp.id='wm';inp.style.width='60%';inp.value=(cfg.welcome_message||'');const actions=document.createElement('div');actions.style.marginTop='8px';const save=document.createElement('button');save.id='save';save.textContent='Save';actions.appendChild(save);wrap.appendChild(lbl);wrap.appendChild(br);wrap.appendChild(inp);wrap.appendChild(actions);el.appendChild(wrap);save.onclick=async()=>{const hs={'Content-Type':'application/json'};if(TOKEN){hs.Authorization='Bearer '+TOKEN;}const r=await fetch('/api/bots/'+bot+'/config',{method:'POST',headers:hs,body:JSON.stringify({org_id:ORG,welcome_message:inp.value})});if(!r.ok){el.textContent='Failed to save';return;}const d=await r.json();el.textContent='Saved. New welcome: '+(d.welcome_message||'');};}\n"
        "async function loadTest(bot){const el=document.getElementById('test');el.innerHTML='';const wrap=document.createElement('div');const inp=document.createElement('input');inp.type='text';inp.placeholder='Type a message';inp.style.width='70%';const send=document.createElement('button');send.textContent='Ask';send.style.marginLeft='8px';const out=document.createElement('div');out.style.marginTop='12px';wrap.appendChild(inp);wrap.appendChild(send);wrap.appendChild(out);el.appendChild(wrap);let XBK=null;try{const k=await api('/api/bots/'+bot+'/key?org_id='+ORG);XBK=k.public_api_key||null;}catch(_){XBK=null;}send.onclick=async()=>{const q=inp.value.trim();if(!q){return;}out.textContent='Asking...';try{const hs={ 'Content-Type':'application/json' };if(TOKEN){hs.Authorization='Bearer '+TOKEN;}if(XBK){hs['X-Bot-Key']=XBK;}const r=await fetch('/api/chat/'+bot,{method:'POST',headers:hs,body:JSON.stringify({message:q,org_id:ORG})});if(!r.ok){out.textContent='Error '+r.status;return;}const d=await r.json();out.textContent='Answer: '+d.answer+(d.similarity!==undefined?'\nSimilarity: '+(Math.round(d.similarity*100)/100):'');}catch(e){out.textContent='Error';}};}\n"
        "if(TOKEN){document.getElementById('authmsg').textContent='Authenticated';loadBots();}\n"
        "</script>"
        "</body></html>"
    )
    return html
from starlette.responses import Response
def _ensure_users_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            create table if not exists app_users (
              id text primary key,
              email text unique not null,
              password_hash text not null,
              org_id text not null,
              created_at timestamptz not null default now()
            )
            """
        )

def _hash_password(pw: str) -> str:
    salt = base64.urlsafe_b64encode(hashlib.sha256(uuid.uuid4().bytes).digest())[:16].decode()
    iterations = 150000
    pep = getattr(settings, 'PASSWORD_PEPPER', '') or getattr(settings, 'JWT_SECRET', 'dev-secret')
    dk = hashlib.pbkdf2_hmac('sha256', (pw+pep).encode(), salt.encode(), iterations)
    return f"pbkdf2${iterations}${salt}${base64.urlsafe_b64encode(dk).decode()}"

def _verify_password(pw: str, stored: str) -> bool:
    try:
        _, it_s, salt, hv = stored.split('$')
        it = int(it_s)
        pep = getattr(settings, 'PASSWORD_PEPPER', '') or getattr(settings, 'JWT_SECRET', 'dev-secret')
        dk = hashlib.pbkdf2_hmac('sha256', (pw+pep).encode(), salt.encode(), it)
        return hmac.compare_digest(base64.urlsafe_b64encode(dk).decode(), hv)
    except Exception:
        return False

def _jwt_secret() -> str:
    return getattr(settings, 'JWT_SECRET', 'dev-secret')

def _require_auth(authorization: Optional[str], org_id: str) -> dict:
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail="missing bearer token")
    payload = _jwt_decode(authorization.split(' ',1)[1])
    tok_org = payload.get('org_id')
    if normalize_org_id(tok_org or '') != normalize_org_id(org_id):
        raise HTTPException(status_code=403, detail="forbidden for org")
    return payload

def _jwt_encode(payload: dict, exp_minutes: int = 120) -> str:
    header = {"alg":"HS256","typ":"JWT"}
    now = int(datetime.datetime.utcnow().timestamp())
    payload = dict(payload)
    payload.setdefault('iat', now)
    payload.setdefault('exp', now + exp_minutes*60)
    def b64(x):
        return base64.urlsafe_b64encode(json.dumps(x, separators=(',',':')).encode()).rstrip(b'=').decode()
    signing_input = f"{b64(header)}.{b64(payload)}"
    sig = hmac.new(_jwt_secret().encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"

def _jwt_decode(token: str) -> dict:
    try:
        h,p,s = token.split('.')
        signing_input = f"{h}.{p}"
        sig = base64.urlsafe_b64decode(s + '==')
        calc = hmac.new(_jwt_secret().encode(), signing_input.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(sig, calc):
            raise HTTPException(status_code=401, detail="Invalid token signature")
        payload = json.loads(base64.urlsafe_b64decode(p + '==').decode())
        exp = int(payload.get('exp', 0))
        if exp and int(datetime.datetime.utcnow().timestamp()) > exp:
            raise HTTPException(status_code=401, detail="Token expired")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

class RegisterBody(BaseModel):
    email: str
    password: str
    org_id: Optional[str] = None
    org_name: Optional[str] = None

class LoginBody(BaseModel):
    email: str
    password: str

@router.post("/auth/register")
def auth_register(body: RegisterBody):
    email = body.email.strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="email and password required")
    conn = get_conn()
    try:
        _ensure_users_table(conn)
        org = body.org_id.strip() if body.org_id else email.split('@')[0]
        with conn.cursor() as cur:
            try:
                cur.execute("select 1 from organizations where id=%s", (normalize_org_id(org),))
                r = cur.fetchone()
                if not r:
                    cur.execute("insert into organizations (id, name) values (%s,%s)", (normalize_org_id(org), body.org_name or org))
            except Exception:
                pass
            cur.execute("select id from app_users where email=%s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="email already registered")
            uid = str(uuid.uuid4())
            ph = _hash_password(body.password)
            cur.execute("insert into app_users (id, email, password_hash, org_id) values (%s,%s,%s,%s)", (uid, email, ph, normalize_org_id(org)))
        token = _jwt_encode({"sub": email, "org_id": normalize_org_id(org)})
        return {"token": token, "org_id": normalize_org_id(org)}
    finally:
        conn.close()

@router.post("/auth/login")
def auth_login(body: LoginBody):
    email = body.email.strip().lower()
    conn = get_conn()
    try:
        _ensure_users_table(conn)
        with conn.cursor() as cur:
            cur.execute("select password_hash, org_id from app_users where email=%s", (email,))
            row = cur.fetchone()
            if not row or not _verify_password(body.password, row[0]):
                raise HTTPException(status_code=401, detail="invalid credentials")
            org = row[1]
        token = _jwt_encode({"sub": email, "org_id": normalize_org_id(org)})
        return {"token": token, "org_id": normalize_org_id(org)}
    finally:
        conn.close()

@router.get("/auth/me")
def auth_me(authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail="missing bearer token")
    payload = _jwt_decode(authorization.split(' ',1)[1])
    return {"email": payload.get('sub'), "org_id": payload.get('org_id')}

class CleanupBody(BaseModel):
    org_id: Optional[str] = None
    confirm: bool = False

@router.post("/admin/cleanup")
def admin_cleanup(body: CleanupBody, authorization: Optional[str] = Header(default=None)):
    payload = _require_auth(authorization, body.org_id or _jwt_decode(authorization.split(' ',1)[1]).get('org_id'))
    org = body.org_id or payload.get('org_id')
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    conn = get_conn()
    try:
        org_n = normalize_org_id(org)
        counts = {}
        with conn.cursor() as cur:
            import uuid
            nu = str(uuid.uuid5(uuid.NAMESPACE_URL, org))
            for name, sql in [
                ("rag_embeddings", "delete from rag_embeddings where org_id::text in (%s,%s,%s)"),
                ("bot_usage_daily", "delete from bot_usage_daily where org_id::text in (%s,%s,%s)"),
                ("bot_calendar_settings", "delete from bot_calendar_settings where org_id::text in (%s,%s,%s)"),
                ("bot_appointments", "delete from bot_appointments where org_id::text in (%s,%s,%s)"),
                ("chatbots", "delete from chatbots where org_id::text in (%s,%s,%s)"),
            ]:
                try:
                    cur.execute(sql + " returning 1", (org_n, org, nu))
                    counts[name] = cur.rowcount
                except Exception:
                    try:
                        cur.execute(sql, (org_n, org, nu))
                        counts[name] = cur.rowcount
                    except Exception:
                        counts[name] = 0
        return {"deleted": counts, "org_id": org}
    finally:
        conn.close()

class AllCleanupBody(BaseModel):
    confirm: bool = False
    preserve_users: bool = True

@router.post("/admin/cleanup_all")
def admin_cleanup_all(body: AllCleanupBody, authorization: Optional[str] = Header(default=None)):
    if not authorization or not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail="missing bearer token")
    _jwt_decode(authorization.split(' ',1)[1])
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    conn = get_conn()
    try:
        counts = {}
        with conn.cursor() as cur:
            for name, sql in [
                ("rag_embeddings", "delete from rag_embeddings"),
                ("bot_usage_daily", "delete from bot_usage_daily"),
                ("bot_calendar_settings", "delete from bot_calendar_settings"),
                ("bot_appointments", "delete from bot_appointments"),
                ("chatbots", "delete from chatbots"),
            ]:
                try:
                    cur.execute(sql)
                    counts[name] = cur.rowcount
                except Exception:
                    counts[name] = 0
            if body.preserve_users:
                try:
                    cur.execute("delete from organizations o where not exists (select 1 from app_users u where u.org_id=o.id)")
                    counts["organizations"] = cur.rowcount
                except Exception:
                    counts["organizations"] = 0
            else:
                try:
                    cur.execute("delete from organizations")
                    counts["organizations"] = cur.rowcount
                except Exception:
                    counts["organizations"] = 0
        return {"deleted": counts}
    finally:
        conn.close()

# Delete a single bot and all of its related data within an org
class DeleteBotBody(BaseModel):
    org_id: str
    confirm: bool = False

@router.post("/bots/{bot_id}/delete")
def delete_bot(bot_id: str, body: DeleteBotBody, authorization: Optional[str] = Header(default=None)):
    from app.db import get_conn, normalize_org_id, normalize_bot_id
    _require_auth(authorization, body.org_id)
    if not body.confirm:
        raise HTTPException(status_code=400, detail="confirm=true required")
    conn = get_conn()
    try:
        org_n = normalize_org_id(body.org_id)
        bot_n = normalize_bot_id(bot_id)
        counts = {}
        with conn.cursor() as cur:
            for name, sql in [
                ("rag_embeddings", "delete from rag_embeddings where org_id::text in (%s,%s) and bot_id::text in (%s,%s)"),
                ("bot_usage_daily", "delete from bot_usage_daily where org_id::text in (%s,%s) and bot_id::text in (%s,%s)"),
                ("bot_calendar_settings", "delete from bot_calendar_settings where org_id::text in (%s,%s) and bot_id::text in (%s,%s)"),
                ("bot_appointments", "delete from bot_appointments where org_id::text in (%s,%s) and bot_id::text in (%s,%s)"),
                ("chatbots", "delete from chatbots where org_id::text in (%s,%s) and id::text in (%s,%s)"),
            ]:
                try:
                    cur.execute(sql + " returning 1", (org_n, body.org_id, bot_n, bot_id))
                    counts[name] = cur.rowcount
                except Exception:
                    try:
                        cur.execute(sql, (org_n, body.org_id, bot_n, bot_id))
                        counts[name] = cur.rowcount
                    except Exception:
                        counts[name] = 0
        return {"deleted": counts, "bot_id": bot_n, "org_id": org_n}
    finally:
        conn.close()
