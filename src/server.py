from fastapi import FastAPI
from schemas import Conversa

from schemas import Session
import time

app = FastAPI()

sessions: dict[str, Session] = {}

@app.post('/message')
async def message(req: Conversa):
    print(f"[REQ] session={req.session_id[:8]} text={repr(req.text)}")
    t0 = time.time()
    if req.session_id not in sessions:
        sessions[req.session_id] = Session(session_id=req.session_id)
    reply = await sessions[req.session_id].step(req.text)
    print(f"[RES] {time.time() - t0:.1f}s reply={repr(reply[:60])}")
    return {"reply": reply}