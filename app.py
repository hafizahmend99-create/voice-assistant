import os
import base64
import asyncio
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from google import genai
from breeze_blue import BreezeBlue

app = FastAPI()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BREEZE_API_KEY = os.getenv("BREEZE_API_KEY")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")

if not GEMINI_API_KEY or not BREEZE_API_KEY:
    print("WARNING: API keys are not configured.")

gemini = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
breeze = BreezeBlue(api_key=BREEZE_API_KEY) if BREEZE_API_KEY else None


@lru_cache(maxsize=1)
def get_voice_id():
    result = breeze.voices.search(search="王洁")
    voices = result.get("voices", [])

    for voice in voices:
        if voice.get("name", "").strip() == "王洁":
            return voice["voice_id"]

    raise RuntimeError("找不到名为王洁的声音，请检查 Breeze 声音库。")


class ChatRequest(BaseModel):
    message: str
    history: list = []
    language: str = "zh-CN"


@app.get("/", response_class=HTMLResponse)
async def home():
    return HTML


@app.get("/health")
async def health():
    return {"status": "ok", "assistant": "Breeze Voice Assistant"}


@app.post("/api/chat")
async def chat(
    data: ChatRequest,
    x_app_password: str = Header(default="")
):
    if APP_PASSWORD and x_app_password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="密码错误")

    if not gemini or not breeze:
        raise HTTPException(status_code=500, detail="API密钥未配置")

    try:
        conversation = []

        for item in data.history[-12:]:
            role = "用户" if item.get("role") == "user" else "助手"
            conversation.append(f"{role}：{item.get('content', '')}")

        conversation.append(f"用户：{data.message}")

        language_instruction = (
            "请使用日语回答。" if data.language == "ja-JP"
            else "请使用中文回答。"
        )

        prompt = f"""
你是一个自然、亲切、聪明的私人语音助手。
你要像朋友一样与用户交流，不要像机器人一样说话。
回答尽量简洁自然，适合直接朗读。
{language_instruction}

以下是对话记录：
{chr(10).join(conversation)}

助手：
"""

        response = await asyncio.to_thread(
            gemini.models.generate_content,
            model="gemini-2.5-flash",
            contents=prompt
        )

        answer = response.text.strip()

        voice_id = await asyncio.to_thread(get_voice_id)

        audio = await asyncio.to_thread(
            breeze.text_to_speech.convert,
            voice_id=voice_id,
            text=answer,
            output_format="mp3"
        )

        return {
            "reply": answer,
            "audio": base64.b64encode(audio.content).decode("utf-8")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>我的语音助手</title>
<style>
*{box-sizing:border-box}
body{
 margin:0;background:#10131b;color:white;
 font-family:Arial,sans-serif;
 display:flex;justify-content:center;
 min-height:100vh;
}
main{width:100%;max-width:500px;padding:25px 20px}
h2{text-align:center;margin:25px 0 8px}
.sub{text-align:center;color:#999;font-size:13px}
#chat{
 margin-top:25px;height:48vh;overflow-y:auto;
 padding:12px;background:#191e29;border-radius:16px
}
.msg{padding:12px 15px;margin:10px 0;
 border-radius:14px;line-height:1.6;white-space:pre-wrap}
.user{background:#315b91;margin-left:35px}
.bot{background:#303747;margin-right:35px}
.controls{margin-top:25px;text-align:center}
button,select,input{
 border:0;border-radius:12px;padding:13px;
 font-size:16px;margin:5px
}
button{background:#597ee8;color:white}
#mic{width:130px;height:130px;border-radius:50%;
 font-size:38px;background:#597ee8;margin:20px}
#mic.active{background:#e34c62}
#status{text-align:center;color:#aaa;margin:15px}
#password{width:90%;background:#252c3a;color:white}
select{background:#252c3a;color:white}
</style>
</head>
<body>
<main>
<h2>🎙️ 我的语音助手</h2>
<div class="sub">BreezeBlue × Gemini · 王洁声音</div>

<div style="text-align:center;margin-top:15px">
<input id="password" type="password" placeholder="访问密码">
</div>

<div id="chat"></div>

<div class="controls">
<select id="language">
<option value="zh-CN">中文对话</option>
<option value="ja-JP">日语对话</option>
</select>
<br>
<button id="mic">🎤</button>
<div id="status">点击麦克风开始说话</div>
<button onclick="clearChat()">清空对话</button>
</div>
</main>

<script>
let history=[];
let busy=false;
let recognition=null;

const chatBox=document.getElementById("chat");
const statusBox=document.getElementById("status");
const mic=document.getElementById("mic");

function addMessage(role,text){
 const div=document.createElement("div");
 div.className="msg "+role;
 div.textContent=text;
 chatBox.appendChild(div);
 chatBox.scrollTop=chatBox.scrollHeight;
}

function clearChat(){
 history=[];
 chatBox.innerHTML="";
 statusBox.textContent="对话已清空";
}

async function sendMessage(text){
 if(busy)return;
 busy=true;
 mic.disabled=true;
 statusBox.textContent="AI正在思考并生成声音...";

 addMessage("user",text);

 try{
  const response=await fetch("/api/chat",{
   method:"POST",
   headers:{
    "Content-Type":"application/json",
    "x-app-password":document.getElementById("password").value
   },
   body:JSON.stringify({
    message:text,
    history:history,
    language:document.getElementById("language").value
   })
  });

  const data=await response.json();

  if(!response.ok)throw new Error(data.detail||"请求失败");

  addMessage("bot",data.reply);

  history.push({role:"user",content:text});
  history.push({role:"assistant",content:data.reply});
  history=history.slice(-12);

  const audio=new Audio(
   "data:audio/mpeg;base64,"+data.audio
  );

  statusBox.textContent="王洁正在回答...";

  await new Promise((resolve,reject)=>{
   audio.onended=resolve;
   audio.onerror=reject;
   audio.play().catch(reject);
  });

  statusBox.textContent="点击麦克风继续聊天";

 }catch(error){
  statusBox.textContent="错误："+error.message;
 }finally{
  busy=false;
  mic.disabled=false;
 }
}

const SpeechRecognition=
 window.SpeechRecognition||window.webkitSpeechRecognition;

if(SpeechRecognition){
 recognition=new SpeechRecognition();
 recognition.continuous=false;
 recognition.interimResults=false;

 recognition.onstart=()=>{
  mic.classList.add("active");
  statusBox.textContent="正在听你说话...";
 };

 recognition.onend=()=>{
  mic.classList.remove("active");
 };

 recognition.onresult=(event)=>{
  const text=event.results[0][0].transcript.trim();
  if(text)sendMessage(text);
 };

 recognition.onerror=(event)=>{
  statusBox.textContent="语音识别失败："+event.error;
 };
}else{
 statusBox.textContent="请使用支持语音识别的 Chrome 浏览器";
}

mic.onclick=()=>{
 if(!recognition){
  alert("当前浏览器不支持语音识别");
  return;
 }
 if(busy)return;
 recognition.lang=document.getElementById("language").value;
 try{recognition.start();}
 catch(e){statusBox.textContent="请稍后重试";}
};
</script>
</body>
</html>
"""
