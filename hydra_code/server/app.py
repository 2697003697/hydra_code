"""
FastAPI 应用程序，用于 Hydra Code 网页服务器。
"""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rich.console import Console

from ..config import Config, load_config
from .connection_manager import ConnectionManager, Message
from .chat_bridge import ChatBridge
from .ngrok_tunnel import NgrokTunnel

console = Console()

# HTML template for mobile interface
HTML_TEMPLATE = r"""
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
            justify-content: space-between;
            align-items: center;
            flex-shrink: 0;
        }
        
        .header h1 {
            font-size: 18px;
            font-weight: 600;
        }
        
        .status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #10b981;
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
            color: #1f2937;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        
        .message.system {
            align-self: center;
            background: #e5e7eb;
            color: #6b7280;
            font-size: 13px;
            padding: 6px 12px;
            max-width: 90%;
        }
        
        .message pre {
            background: #1f2937;
            color: #e5e7eb;
            padding: 12px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 13px;
            margin: 8px 0;
        }
        
        .message code {
            background: #f3f4f6;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 13px;
            font-family: 'Courier New', monospace;
        }
        
        .message.assistant code {
            background: #f3f4f6;
            color: #1f2937;
        }
        
        .input-container {
            padding: 12px 16px;
            background: white;
            border-top: 1px solid #e5e7eb;
            display: flex;
            gap: 8px;
            flex-shrink: 0;
        }
        
        .input-wrapper {
            flex: 1;
            display: flex;
            align-items: center;
            background: #f3f4f6;
            border-radius: 20px;
            padding: 0 16px;
        }
        
        .input-wrapper textarea {
            flex: 1;
            border: none;
            background: transparent;
            padding: 10px 0;
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
            flex-shrink: 0;
        }
        
        .send-btn:disabled {
            background: #c7c7c7;
            cursor: not-allowed;
        }
        
        .toolbar {
            display: flex;
            gap: 8px;
            padding: 8px 16px;
            background: white;
            border-top: 1px solid #e5e7eb;
            overflow-x: auto;
            flex-shrink: 0;
            -webkit-overflow-scrolling: touch;
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
        <div class="status" id="status-indicator">
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
        let ws = null;
        const chatContainer = document.getElementById('chat-container');
        const messageInput = document.getElementById('message-input');
        const sendBtn = document.getElementById('send-btn');
        const statusText = document.getElementById('status-text');
        const statusIndicator = document.getElementById('status-indicator');
        const fileInput = document.getElementById('file-input');
        
        let isProcessing = false;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 5;
        let reconnectInterval = null;
        let isConnecting = false;
        
        function connectWebSocket() {
            // 防止重复连接
            if (isConnecting) {
                return;
            }
            
            // 如果已经有连接，不要重复创建
            if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
                return;
            }
            
            isConnecting = true;
            
            try {
                ws = new WebSocket(`ws://${window.location.host}/ws`);
            } catch (e) {
                console.error('WebSocket creation failed:', e);
                isConnecting = false;
                return;
            }
            
            ws.onopen = () => {
                statusText.textContent = '在线';
                statusIndicator.classList.remove('error');
                statusIndicator.classList.remove('loading');
                reconnectAttempts = 0;
                isConnecting = false;
                if (reconnectInterval) {
                    clearInterval(reconnectInterval);
                    reconnectInterval = null;
                }
            };
            
            ws.onclose = () => {
                statusText.textContent = '离线';
                statusIndicator.classList.remove('loading');
                statusIndicator.classList.add('error');
                isConnecting = false;
                
                // 避免重复创建重连定时器
                if (reconnectInterval) {
                    return;
                }
                
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectInterval = setInterval(() => {
                        reconnectAttempts++;
                        if (reconnectAttempts <= maxReconnectAttempts) {
                            addMessage('system', `连接已断开，尝试重连 (${reconnectAttempts}/${maxReconnectAttempts})...`);
                            connectWebSocket();
                        } else {
                            clearInterval(reconnectInterval);
                            reconnectInterval = null;
                            addMessage('system', '连接已断开，请刷新页面重试');
                        }
                    }, 2000);
                } else {
                    addMessage('system', '连接已断开，请刷新页面重试');
                }
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                isConnecting = false;
            };
            
            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                
                if (data.type === 'status') {
                    if (data.content === 'loading') {
                        showTyping();
                        isProcessing = true;
                        sendBtn.disabled = true;
                        statusIndicator.classList.add('loading');
                    } else if (data.content === 'idle') {
                        hideTyping();
                        isProcessing = false;
                        sendBtn.disabled = false;
                        statusIndicator.classList.remove('loading');
                        statusIndicator.classList.add('idle');
                    } else if (data.content === 'error') {
                        hideTyping();
                        isProcessing = false;
                        sendBtn.disabled = false;
                        statusIndicator.classList.remove('loading');
                        statusIndicator.classList.add('error');
                        addMessage('system', '⚠️ ' + (data.metadata?.message || '发生错误'));
                    } else {
                        hideTyping();
                        isProcessing = false;
                        sendBtn.disabled = false;
                    }
                } else if (data.type === 'system' && data.content && data.content.startsWith('[Error:')) {
                    hideTyping();
                    isProcessing = false;
                    sendBtn.disabled = false;
                    addMessage('system', '⚠️ ' + data.content);
                } else if (data.type === 'file') {
                    hideTyping();
                    addMessage('system', data.content || '开始下载文件');
                    if (data.metadata && data.metadata.url && data.metadata.is_download) {
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
        }
        
        function addMessage(type, content) {
            const div = document.createElement('div');
            div.className = `message ${type}`;
            div.innerHTML = formatContent(content);
            chatContainer.appendChild(div);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
        
        function formatContent(text) {
            if (!text) return '';
            
            let html = text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');
            
            html = html
                .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>')
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
                .replace(/\*([^*]+)\*/g, '<em>$1</em>')
                .replace(/^### (.+)$/gm, '<h3>$1</h3>')
                .replace(/^## (.+)$/gm, '<h2>$1</h2>')
                .replace(/^# (.+)$/gm, '<h1>$1</h1>')
                .replace(/^\* (.+)$/gm, '<li>$1</li>')
                .replace(/^- (.+)$/gm, '<li>$1</li>')
                .replace(/^(\d+)\. (.+)$/gm, '<li>$2</li>')
                .replace(/\n\n/g, '</p><p>')
                .replace(/\n/g, '<br>');
            
            return `<p>${html}</p>`;
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
            
            // 检查 WebSocket 连接状态
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                addMessage('system', '连接未建立，请稍后再试');
                return;
            }
            
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
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                addMessage('system', '连接未建立');
                return;
            }
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
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                addMessage('system', '连接未建立');
                return;
            }
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
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                addMessage('system', '连接未建立');
                return;
            }
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
        
        // Initialize connection
        connectWebSocket();
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
        
        # Write file asynchronously to avoid blocking
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, destination.write_bytes, content)
        
        # Return simple response, let frontend handle adding message to chat
        return {
            "success": True,
            "path": str(destination.relative_to(base_dir)),
            "size": len(content),
            "filename": file.filename,
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
                    await bridge.handle_message(websocket, data.get("content", ""))
                elif data.get("type") == "command":
                    command = data.get("command")
                    args = data.get("args", {})
                    
                    if command == "mode":
                        mode = args.get("mode", "auto")
                        await bridge.set_mode(mode)
                        await bridge.manager.send_personal_message(
                            websocket,
                            Message(
                                id=str(uuid.uuid4()),
                                type="system",
                                content=f"已切换到 {mode} 模式",
                                timestamp=datetime.now().isoformat()
                            )
                        )
                    elif command == "clear":
                        await bridge.clear_history()
                    elif command == "explain":
                        await bridge.explain_last_intent(websocket)
                        
        except WebSocketDisconnect:
            await bridge.manager.disconnect(websocket)
        except Exception as e:
            console.print(f"[red]WebSocket error: {e}[/red]")
            await bridge.manager.disconnect(websocket)
    
    return app
