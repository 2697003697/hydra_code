"""
Ngrok and Tailscale tunnel integration for remote access.
"""

import asyncio
import os
import socket
import subprocess
import re
from typing import Optional, List

from pyngrok import ngrok
from rich.console import Console

console = Console()


class NgrokTunnel:
    """Manages ngrok tunnel for exposing local server to internet."""

    def __init__(self, auth_token: Optional[str] = None):
        self.auth_token = auth_token
        self.tunnel = None
        self.public_url: Optional[str] = None

    def start(self, port: int) -> str:
        """Start ngrok tunnel to expose local port.

        Args:
            port: Local port to expose

        Returns:
            Public HTTPS URL
        """
        if self.auth_token:
            ngrok.set_auth_token(self.auth_token)

        # Kill any existing tunnels
        try:
            ngrok.kill()
        except Exception:
            pass

        # Create tunnel
        self.tunnel = ngrok.connect(port, "http")
        self.public_url = self.tunnel.public_url

        console.print(f"\n[green]✓ Ngrok tunnel established![/green]")
        console.print(f"[cyan]Public URL:[/cyan] {self.public_url}")
        console.print(f"[dim]Local: http://localhost:{port}[/dim]\n")

        return self.public_url

    def stop(self):
        """Stop ngrok tunnel."""
        if self.tunnel:
            try:
                ngrok.disconnect(self.tunnel.public_url)
            except Exception:
                pass
        ngrok.kill()
        self.tunnel = None
        self.public_url = None
        console.print("[yellow]Ngrok tunnel closed.[/yellow]")

    @staticmethod
    def get_tailscale_ips() -> List[str]:
        """Get Tailscale IP addresses.
        
        Returns:
            List of Tailscale IP addresses (e.g., ['100.x.x.x'])
        """
        ips = []
        
        # Method 1: Try tailscale ip command with common paths
        tailscale_paths = [
            "tailscale",
            r"C:\Program Files\Tailscale\tailscale.exe",
            os.path.expandvars(r"%ProgramFiles%\Tailscale\tailscale.exe"),
        ]
        
        for ts_path in tailscale_paths:
            try:
                result = subprocess.run(
                    [ts_path, "ip"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line.startswith('100.'):
                            ips.append(line.strip())
                    if ips:
                        break
            except Exception:
                continue
        
        # Method 2: Try reading Tailscale state file
        if not ips:
            try:
                tailscale_state = os.path.expandvars(r"%LOCALAPPDATA%\Tailscale\ipn\state.json")
                if os.path.exists(tailscale_state):
                    with open(tailscale_state, 'r', errors='ignore') as f:
                        content = f.read()
                        matches = re.findall(r'100\.\d+\.\d+\.\d+', content)
                        ips.extend(matches)
            except Exception:
                pass
        
        # Method 3: Check Windows network adapters
        if not ips:
            try:
                result = subprocess.run(
                    ["powershell", "-Command", "Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -like '100.*'} | Select-Object -ExpandProperty IPAddress"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip().startswith('100.'):
                            ips.append(line.strip())
            except Exception:
                pass
        
        return list(set(ips))
    
    @staticmethod
    def is_tailscale_running() -> bool:
        """Check if Tailscale is installed and running."""
        # Method 1: Check if tailscale process exists
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq tailscale.exe"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if "tailscale.exe" in result.stdout:
                return True
        except Exception:
            pass
        
        # Method 2: Try tailscale status
        tailscale_paths = [
            "tailscale",
            r"C:\Program Files\Tailscale\tailscale.exe",
        ]
        
        for ts_path in tailscale_paths:
            try:
                result = subprocess.run(
                    [ts_path, "status"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    return True
            except Exception:
                continue
        
        return False

    @staticmethod
    def get_local_ip() -> str:
        """Get local IP address for LAN access."""
        try:
            # Method 1: Try connecting to external host
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        
        try:
            # Method 2: Get all network interfaces
            import subprocess
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                encoding='gbk',  # Windows uses GBK
                errors='ignore'
            )
            output = result.stdout
            
            # Find IPv4 addresses
            import re
            # Pattern for Chinese Windows ipconfig output
            ipv4_pattern = r'IPv4.*?:\s*(\d+\.\d+\.\d+\.\d+)'
            matches = re.findall(ipv4_pattern, output)
            
            # Filter out loopback and virtual adapters
            for ip in matches:
                if not ip.startswith("127.") and not ip.startswith("169.254"):
                    return ip
        except Exception:
            pass
        
        try:
            # Method 3: Try hostname resolution
            hostname = socket.gethostname()
            ip = socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            pass
        
        return "127.0.0.1"
