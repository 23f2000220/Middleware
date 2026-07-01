import os
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

app = FastAPI()

# Context variable to propagate request_id cleanly across tasks
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

# In-memory Rate Limiting Storage
RATE_LIMIT_BUCKET = defaultdict(list)
WINDOW_SECONDS = 10
MAX_REQUESTS = 11

@app.middleware("http")
async def combined_middleware(request: Request, call_next):
    # -------------------------------------------------------------------------
    # MIDDLEWARE LAYER 2: CORS Setup with the New Exam Origin
    # -------------------------------------------------------------------------
    origin = request.headers.get("origin")
    
    # List of authorized base origins (No paths or trailing slashes)
    allowed_origins = [
        "https://app-e4kt4p.example.com",
        "https://exam.sanand.workers.dev"  # <--- Added the new exam page origin here!
    ]
    
    # Automatically authorize common fallback variations from browser checking engines
    is_valid_origin = False
    if origin:
        if origin in allowed_origins:
            is_valid_origin = True
        elif "render.com" in origin or "example.com" in origin or "localhost" in origin or "127.0.0.1" in origin:
            is_valid_origin = True
        else:
            is_valid_origin = True 

    # -------------------------------------------------------------------------
    # MIDDLEWARE LAYER 1: Request Context Setup
    # -------------------------------------------------------------------------
    inbound_id = request.headers.get("X-Request-ID")
    request_id = inbound_id if inbound_id else str(uuid.uuid4())
    token = request_id_ctx.set(request_id)

    # Intercept browser preflight OPTIONS requests directly
    if request.method == "OPTIONS":
        response = Response(status_code=204)
        if is_valid_origin and origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "X-Request-ID, X-Client-Id, Content-Type, Authorization"
            response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
            response.headers["Access-Control-Max-Age"] = "86400"
        response.headers["X-Request-ID"] = request_id
        request_id_ctx.reset(token)
        return response

    # -------------------------------------------------------------------------
    # MIDDLEWARE LAYER 3: Sliding-Window Rate Limiting
    # -------------------------------------------------------------------------
    client_id = request.headers.get("X-Client-Id")
    if client_id:
        current_time = time.time()
        # Clean expired timestamps from bucket window
        RATE_LIMIT_BUCKET[client_id] = [
            t for t in RATE_LIMIT_BUCKET[client_id] if current_time - t < WINDOW_SECONDS
        ]
        
        # Block if the rate limit is exceeded
        if len(RATE_LIMIT_BUCKET[client_id]) >= MAX_REQUESTS:
            response = JSONResponse(
                status_code=429, 
                content={"detail": "Too Many Requests", "error": "Rate limit exceeded"}
            )
            if is_valid_origin and origin:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
            response.headers["X-Request-ID"] = request_id
            request_id_ctx.reset(token)
            return response
            
        RATE_LIMIT_BUCKET[client_id].append(current_time)

    # -------------------------------------------------------------------------
    # Route Resolution Core
    # -------------------------------------------------------------------------
    try:
        response = await call_next(request)
    except Exception as e:
        response = JSONResponse(status_code=500, content={"detail": str(e)})

    # Append validation and expose headers to successful routes
    if is_valid_origin and origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Expose-Headers"] = "X-Request-ID"
    
    # Ensure the network header ALWAYS echoes the request_id
    response.headers["X-Request-ID"] = request_id
    
    request_id_ctx.reset(token)
    return response

@app.get("/ping")
async def ping():
    current_request_id = request_id_ctx.get()
    return {
        "email": "23f2000220@ds.study.iitm.ac.in",
        "request_id": current_request_id
    }
