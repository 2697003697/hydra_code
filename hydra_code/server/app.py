"""
FastAPI application for Hydra Code web server.
"""

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rich.console import Console

from ..config import Config, load_config
from .connection_manager import ConnectionManager
from .chat_bridge import ChatBridge
from .ngrok_tunnel import NgrokTunnel

console = Console()

# HTML template for mobile interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Hydra Code - Remote</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #f5f5f5;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 16px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .header h1 {
            font-size: 18px;
            font-weight: 600;
        }
        
        .status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #4ade80;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        
        .message {
            max-width: 85%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 15px;
            line-height: 1.5;
            word-wrap: break-word;
        }
        
        .message.user {
            align-self: flex-end;
            background: #667eea;
            color: white;
            border-bottom-right-radius: 4px;
        }
        
        .message.assistant {
            align-self: flex-start;
            background: white;
            color: #333;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .message.system {
            align-self: center;
            background: #e5e7eb;
            color: #6b7280;
            font-size: 12px;
            padding: 6px 12px;
            border-radius: 12px;
        }
        
        .input-container {
            background: white;
            padding: 12px 16px;
            border-top: 1px solid #e5e7eb;
            display: flex;
            gap: 12px;
            align-items: flex-end;
        }
        
        .input-wrapper {
            flex: 1;
            background: #f3f4f6;
            border-radius: 20px;
            padding: 8px 16px;
        }
        
        textarea {
            width: 100%;
            border: none;
            background: transparent;
            font-size: 15px;
            resize: none;
            outline: none;
            font-family: inherit;
            max-height: 120px;
        }
        
        .send-btn {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: #667eea;
            color: white;
            border: none;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: transform 0.2s;
        }
        
        .send-btn:active {
            transform: scale(0.95);
        }
        
        .send-btn:disabled {
            background: #9ca3af;
            cursor: not-allowed;
        }
        
        .typing {
            display: flex;
            gap: 4px;
            padding: 12px 16px;
        }
        
        .typing span {
            width: 8px;
            height: 8px;
            background: #9ca3af;
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out both;
        }
        
        .typing span:nth-child(1) { animation-delay: -0.32s; }
        .typing span:nth-child(2) { animation-delay: -0.16s; }
        
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
        }
        
        .toolbar {
            display: flex;
            gap: 8px;
            padding: 8px 16px;
            background: white;
            border-top: 1px solid #e5e7eb;
            overflow-x: auto;
        }
        
        .toolbar button {
            padding: 6px 12px;
            border: 1px solid #e5e7eb;
            background: white;
            border-radius: 16px;
            font-size: 13px;
            color: #374151;
            cursor: pointer;
            white-space: nowrap;
        }
        
        .toolbar button:active {
            background: #f3f4f6;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🐍 Hydra Code</h1>
        <div class="status">
            <span class="status-dot"></span>
            <span id="status-text">在线</span>
        </div>
    </div>
    
    <div class="toolbar">
        <button onclick="setMode('auto')">自动</button>
        <button onclick="setMode('fast')">快速</button>
        <button onclick="setMode('pro')">专业</button>
        <button onclick="setMode('leader')">Leader</button>
        <button onclick="chooseFile()">上传</button>
        <button onclick="downloadFile()">下载</button>
        <button onclick="explainLast()">解释</button>
        <button onclick="clearHistory()">清除</button>
    </div>
    
    <input type="file" id="file-input" style="display:none" />
    
    <div class="chat-container" id="chat-container">
        <div class="message system">已连接到 Hydra Code 服务器</div>
    </div>
    
    <div class="input-container">
        <div class="input-wrapper">
            <textarea id="message-input" placeholder="输入消息..." rows="1"></textarea>
        </div>
        <button class="send-btn" id="send-btn" onclick="sendMessage()">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
        </button>
    </div>
    
    <script>
        const ws = new WebSocket(`ws://${window.location.host}/ws`);
        const chatContainer = document.getElementById('chat-container');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const statusText = document.getElementById('status-text');
        const fileInput = document.getElementById('file-input');
        
        let isProcessing = false;
        
        ws.onopen = () => {
            statusText.textContent = '在线';
        };
        
        ws.onclose = () => {
            statusText.textContent = '离线';
            addMessage('system', '连接已断开，请刷新页面重试');
        };
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'status') {
                if (data.content === 'processing') {
                    showTyping();
                    isProcessing = true;
                    sendBtn.disabled = true;
                } else {
                    hideTyping();
                    isProcessing = false;
                    sendBtn.disabled = false;
                }
            } else if (data.type === 'file') {
                hideTyping();
                addMessage('system', data.content || '开始下载文件');
                if (data.metadata && data.metadata.url) {
                    triggerDownload(data.metadata.url);
                }
                isProcessing = false;
                sendBtn.disabled = false;
            } else {
                hideTyping();
                addMessage(data.type, data.content);
                isProcessing = false;
                sendBtn.disabled = false;
            }
        };
        
        function addMessage(type, content) {
            const div = document.createElement('div');
            div.className = `message ${type}`;
            div.textContent = content;
            chatContainer.appendChild(div);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function triggerDownload(url) {
            const link = document.createElement('a');
            link.href = url;
            link.download = '';
            document.body.appendChild(link);
            link.click();
            link.remove();
        }
        
        function showTyping() {
            hideTyping();
            const div = document.createElement('div');
            div.className = 'message assistant typing';
            div.id = 'typing-indicator';
            div.innerHTML = '<span></span><span></span><span></span>';
            chatContainer.appendChild(div);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function hideTyping() {
            const typing = document.getElementById('typing-indicator');
            if (typing) typing.remove();
        }
        
        function sendMessage() {
            const content = messageInput.value.trim();
            if (!content || isProcessing) return;
            
            ws.send(JSON.stringify({
                type: 'message',
                content: content
            }));
            
            messageInput.value = '';
            messageInput.rows = 1;
            isProcessing = true;
            sendBtn.disabled = true;
        }
        
        function setMode(mode) {
            ws.send(JSON.stringify({
                type: 'command',
                command: 'mode',
                args: { mode: mode }
            }));
        }
        
        function chooseFile() {
            fileInput.click();
        }
        
        async function handleFileSelect(event) {
            const file = event.target.files[0];
            if (!file) return;
            
            const targetPath = prompt('保存到服务器路径（可选，基于工作目录）', '');
            const formData = new FormData();
            formData.append('file', file);
            if (targetPath) {
                formData.append('target_path', targetPath);
            }
            
            addMessage('system', `开始上传: ${file.name}`);
            
            try {
                const response = await fetch('/api/files/upload', {
                    method: 'POST',
                    body: formData
                });
                
                let data = null;
                try {
                    data = await response.json();
                } catch (e) {
                    data = null;
                }
                
                if (response.ok && data && data.success) {
                    addMessage('system', `上传完成: ${data.path} (${data.size} bytes)`);
                } else {
                    const detail = data && (data.detail || data.error) ? (data.detail || data.error) : '上传失败';
                    addMessage('system', detail);
                }
            } catch (e) {
                addMessage('system', '上传失败');
            } finally {
                fileInput.value = '';
            }
        }
        
        function downloadFile() {
            const path = prompt('输入要下载的服务器路径（相对工作目录）', '');
            if (!path) return;
            const url = `/api/files/download?path=${encodeURIComponent(path)}`;
            window.open(url, '_blank');
            addMessage('system', `开始下载: ${path}`);
        }
        
        function clearHistory() {
            ws.send(JSON.stringify({
                type: 'command',
                command: 'clear'
            }));
            chatContainer.innerHTML = '<div class="message system">历史已清除</div>';
        }
        
        function explainLast() {
            const messages = chatContainer.querySelectorAll('.message.user');
            if (messages.length === 0) {
                addMessage('system', '没有历史消息可解释');
                return;
            }
            const lastUserMsg = messages[messages.length - 1].textContent;
            ws.send(JSON.stringify({
                type: 'command',
                command: 'explain',
                args: { message: lastUserMsg }
            }));
        }
        
        messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
        
        fileInput.addEventListener('change', handleFileSelect);
        
        messageInput.addEventListener('input', () => {
            messageInput.rows = Math.min(5, Math.max(1, messageInput.value.split('\\n').length));
        });
    </script>
</body>
</html>
"""


def create_app(config: Config, working_dir: str) -> FastAPI:
    """Create FastAPI application."""
    app = FastAPI(title="Hydra Code Remote")
    
    bridge = ChatBridge(config, working_dir)
    base_dir = Path(working_dir).resolve()
    
    def resolve_safe_path(relative_path: str) -> Path:
        target = (base_dir / relative_path).resolve()
        if base_dir not in target.parents and target != base_dir:
            raise HTTPException(status_code=403, detail="Invalid path")
        return target
    
    @app.on_event("startup")
    async def startup():
        await bridge.initialize()
    
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTML_TEMPLATE
    
    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "connections": bridge.manager.get_connection_count(),
            "mode": config.default_work_mode
        }
    
    @app.post("/api/files/upload")
    async def upload_file(file: UploadFile = File(...), target_path: Optional[str] = None):
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="Missing file")
        
        if target_path:
            target = resolve_safe_path(target_path)
            if target.exists() and target.is_dir():
                destination = target / file.filename
            elif str(target_path).endswith(("/", "\\")):
                destination = target / file.filename
            else:
                destination = target
        else:
            destination = base_dir / file.filename
        
        if base_dir not in destination.parents and destination != base_dir:
            raise HTTPException(status_code=403, detail="Invalid path")
        
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = await file.read()
        destination.write_bytes(content)
        
        return {
            "success": True,
            "path": str(destination.relative_to(base_dir)),
            "size": len(content),
        }
    
    @app.get("/api/files/download")
    async def download_file(path: str):
        if not path:
            raise HTTPException(status_code=400, detail="Missing path")
        
        target = resolve_safe_path(path)
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        
        return FileResponse(path=str(target), filename=target.name)
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        client_id = str(id(websocket))
        await bridge.manager.connect(websocket)
        
        try:
            while True:
                data = await websocket.receive_json()
                
                if data.get("type") == "message":
                    content = data.get("content", "").strip()
                    if content:
                        await bridge.handle_message(client_id, content)
                
                elif data.get("type") == "command":
                    command = data.get("command", "")
                    args = data.get("args", {})
                    await bridge.handle_command(client_id, command, args)
                    
        except WebSocketDisconnect:
            await bridge.manager.disconnect(websocket)
    
    return app


async def start_server(
    config: Config,
    working_dir: str,
    port: int = 8080,
    use_ngrok: bool = False,
    ngrok_auth: Optional[str] = None
):
    """Start the web server with optional ngrok tunnel."""
    from uvicorn import Config as UvicornConfig, Server
    
    app = create_app(config, working_dir)
    
    # Get local IP for display
    local_ip = NgrokTunnel.get_local_ip()
    tailscale_ips = NgrokTunnel.get_tailscale_ips() if NgrokTunnel.is_tailscale_running() else []
    
    console.print(f"\n[bold cyan]Starting Hydra Code Server...[/bold cyan]")
    console.print(f"[dim]Local:[/dim]   http://localhost:{port}")
    
    if local_ip != "127.0.0.1":
        console.print(f"[green]LAN:[/green]     http://{local_ip}:{port}")
        console.print(f"[dim]         同一WiFi下的手机/其他设备可访问此地址[/dim]")
    else:
        console.print(f"[yellow]LAN:[/yellow]     无法获取局域网IP")
    
    # Display Tailscale IPs if available
    if tailscale_ips:
        console.print(f"[cyan]Tailscale:[/cyan]")
        for ip in tailscale_ips:
            console.print(f"           http://{ip}:{port}")
        console.print(f"[dim]         远程设备通过Tailscale网络可访问此地址[/dim]")
    else:
        console.print(f"[dim]Tailscale:[/dim]  未检测到Tailscale运行")
        console.print(f"[dim]         如已安装Tailscale，请确保已登录并连接[/dim]")
    
    console.print("")
    
    # Start ngrok if requested
    tunnel = None
    if use_ngrok:
        try:
            tunnel = NgrokTunnel(auth_token=ngrok_auth)
            public_url = tunnel.start(port)
            console.print(f"[green]Public:[/green] {public_url}")
        except Exception as e:
            console.print(f"[red]Ngrok failed: {e}[/red]")
            console.print(f"[dim]Use --ngrok-auth with your token, or use LAN address instead[/dim]")
    
    console.print("")
    
    # Configure and start server
    uvicorn_config = UvicornConfig(
        app=app,
        host="0.0.0.0",
        port=port,
        log_level="warning"
    )
    server = Server(uvicorn_config)
    
    try:
        await server.serve()
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down server...[/yellow]")
        if tunnel:
            tunnel.stop()
