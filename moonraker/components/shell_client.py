# interactive_terminal.py
from __future__ import annotations
import asyncio
import tornado.websocket
import json
import logging
import os
import pty
import termios
import fcntl
import struct
import signal
import select
import subprocess
from typing import TYPE_CHECKING, Dict, Any, Optional

if TYPE_CHECKING:
    from ..confighelper import ConfigHelper
    from ..server import Server
    from ..utils import IPAddress

class ShellHandler(tornado.websocket.WebSocketHandler):
    """Интерактивный терминал с PTY поддержкой для Moonraker"""
    
    def initialize(self, terminal_manager=None):
        self.server: Server = self.settings['server']
        self.process = None
        self.fd: Optional[int] = None
        self.read_task: Optional[asyncio.Task] = None
        self.session_id: int = id(self)
        self.manager: Optional[TerminalManager] = terminal_manager
        self._ip_addr: Optional[IPAddress] = None
        
    @property
    def ip_addr(self) -> Optional[IPAddress]:
        return self._ip_addr
        
    def check_origin(self, origin: str) -> bool:
        return True
        
    def open(self):
        self._ip_addr = self.request.remote_ip
        
        if self.manager:
            self.manager.add_session(self.session_id, self)
        
        logging.info(f"Terminal opened: ID={self.session_id}, IP={self._ip_addr}")
        self.start_interactive_shell()
    
    def start_interactive_shell(self):
        """Запуск интерактивного shell через subprocess с PTY"""
        try:
            import subprocess
            import pty
            
            master_fd, slave_fd = pty.openpty()
            
            self.process = subprocess.Popen(
                ['/bin/bash', '--login', '-i'],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env={
                    'TERM': 'xterm-256color',
                    'LANG': 'en_US.UTF-8',
                    'LC_ALL': 'en_US.UTF-8',
                    'PS1': '\\[\\033[01;32m\\]\\u@\\h\\[\\033[00m\\]:\\[\\033[01;34m\\]\\w\\[\\033[00m\\]\\$ ',
                    'HOME': os.environ.get('HOME', '/home/orangepi')
                },
                preexec_fn=os.setsid
            )
            
            os.close(slave_fd)
            self.fd = master_fd
            
            # Устанавливаем raw режим с эхо
            self.set_raw_mode()
            self.set_terminal_size(24, 80)
            self.read_task = asyncio.create_task(self.read_pty_output())
            
            self.write_message(json.dumps({
                'type': 'ready',
                'message': 'Terminal ready',
                'session_id': self.session_id
            }))
            
            logging.info(f"Shell started: PID={self.process.pid}, FD={self.fd}")
                
        except Exception as e:
            logging.exception("Failed to start shell")
            self.write_message(json.dumps({
                'type': 'error',
                'message': f'Failed to start shell: {str(e)}'
            }))
            self.close()
        
    def set_raw_mode(self):
        """Установка raw режима для PTY с правильной обработкой Enter"""
        if not self.fd:
            return
            
        try:
            attrs = termios.tcgetattr(self.fd)
            
            # Control modes (c_cflag)
            attrs[2] = attrs[2] & ~(termios.CSIZE | termios.PARENB)
            attrs[2] = attrs[2] | termios.CS8
            
            # Input modes (c_iflag)
            attrs[0] = attrs[0] & ~(termios.IGNBRK | termios.BRKINT | 
                                    termios.PARMRK | termios.ISTRIP)
            attrs[0] = attrs[0] & ~termios.IGNCR      # Не игнорировать CR
            attrs[0] = attrs[0] | termios.ICRNL       # Преобразовать CR -> NL
            attrs[0] = attrs[0] & ~termios.INLCR      # Не преобразовывать NL -> CR
            attrs[0] = attrs[0] & ~termios.IXON       # Отключить software flow control
            
            # Output modes (c_oflag)
            attrs[1] = attrs[1] & ~termios.OPOST      # Отключить постобработку вывода
            
            # Local modes (c_lflag)
            attrs[3] = attrs[3] & ~(termios.ICANON | termios.IEXTEN)
            attrs[3] = attrs[3] | termios.ISIG        # Включить обработку сигналов
            attrs[3] = attrs[3] | termios.ECHO        # Включить эхо
            attrs[3] = attrs[3] | termios.ECHOE       # Включить стирание
            attrs[3] = attrs[3] | termios.ECHOK       # Включить стирание строки
            attrs[3] = attrs[3] | termios.ECHONL      # Эхо NL даже если ECHO выключен
            
            # Control characters (c_cc)
            attrs[6][termios.VINTR] = 3    # Ctrl+C
            attrs[6][termios.VQUIT] = 28   # Ctrl+\
            attrs[6][termios.VERASE] = 127 # Backspace
            attrs[6][termios.VKILL] = 21   # Ctrl+U
            attrs[6][termios.VEOF] = 4     # Ctrl+D
            attrs[6][termios.VTIME] = 0
            attrs[6][termios.VMIN] = 1
            attrs[6][termios.VSTART] = 17  # Ctrl+Q
            attrs[6][termios.VSTOP] = 19   # Ctrl+S
            attrs[6][termios.VSUSP] = 26   # Ctrl+Z
            
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, attrs)
            
            logging.info("Raw mode configured with CR->NL conversion and signal handling")
            
        except Exception as e:
            logging.error(f"Failed to set raw mode: {e}")
    
    def set_terminal_size(self, rows: int, cols: int):
        """Установка размера терминала"""
        if not self.fd:
            return
            
        try:
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, winsize)
        except Exception as e:
            logging.debug(f"Failed to set terminal size: {e}")
    
    async def read_pty_output(self):
        """Асинхронное чтение вывода PTY"""
        loop = asyncio.get_running_loop()
        
        while self.fd and self.process and self.process.poll() is None:
            try:
                # Используем select для неблокирующего чтения
                rlist, _, _ = select.select([self.fd], [], [], 0.1)
                if rlist:
                    try:
                        data = await loop.run_in_executor(None, os.read, self.fd, 4096)
                        if data:
                            self.write_message(data, binary=True)
                        else:
                            # EOF - процесс завершен
                            logging.info(f"PTY EOF received")
                            break
                    except OSError as e:
                        if e.errno == 5:  # Input/output error
                            logging.info(f"PTY I/O error, process finished")
                            break
                        raise
            except Exception as e:
                logging.debug(f"PTY read error: {e}")
                break
            await asyncio.sleep(0.01)
        
        # Если вышли из цикла, закрываем терминал
        await self.close_terminal()
    
    async def on_message(self, message):
        """Обработка входящих сообщений"""
        if not self.fd or not self.process:
            return
        
        try:
            if isinstance(message, str):
                try:
                    data = json.loads(message)
                    msg_type = data.get('type', '')
                    
                    if msg_type == 'data':
                        cmd = data.get('data', '')
                        os.write(self.fd, cmd.encode())
                        
                    elif msg_type == 'resize':
                        rows = data.get('rows', 24)
                        cols = data.get('cols', 80)
                        self.set_terminal_size(rows, cols)
                        
                    elif msg_type == 'ping':
                        self.write_message(json.dumps({'type': 'pong'}))
                        
                    elif msg_type == 'close':
                        await self.close_terminal()
                        
                except json.JSONDecodeError:
                    os.write(self.fd, message.encode())
            else:
                os.write(self.fd, message)
                
        except OSError as e:
            logging.error(f"Write error: {e}")
            await self.close_terminal()
        except Exception as e:
            logging.exception(f"Unexpected error: {e}")
    
    async def close_terminal(self):
        """Закрытие терминала"""
        logging.info(f"Closing terminal: session_id={self.session_id}")
        
        if self.read_task and not self.read_task.done():
            self.read_task.cancel()
            try:
                await self.read_task
            except asyncio.CancelledError:
                pass
            self.read_task = None
        
        if self.process:
            try:
                self.process.terminate()
                await asyncio.sleep(0.1)
                if self.process.poll() is None:
                    self.process.kill()
                self.process.wait(timeout=1)
            except:
                pass
            self.process = None
        
        if self.fd:
            try:
                os.close(self.fd)
            except:
                pass
            self.fd = None
        
        try:
            self.write_message(json.dumps({
                'type': 'closed',
                'message': 'Terminal session closed'
            }))
        except:
            pass
    
    def on_close(self):
        """WebSocket закрыт"""
        logging.info(f"Terminal closed: ID={self.session_id}")
        
        if self.manager:
            self.manager.remove_session(self.session_id)
        
        asyncio.create_task(self.close_terminal())


class TerminalManager:
    """Менеджер терминальных сессий"""
    
    def __init__(self, config: ConfigHelper):
        self.server = config.get_server()
        self.sessions: Dict[int, ShellHandler] = {}
        self.max_sessions = config.getint('max_terminal_sessions', 10)
        
        self._register_endpoints()
        self._register_websocket()
        
        logging.info(f"Terminal Manager initialized: max_sessions={self.max_sessions}")
    
    def _register_endpoints(self):
        from ..common import RequestType, TransportType
        
        self.server.register_endpoint(
            "/server/terminal/sessions",
            RequestType.GET,
            self._handle_sessions,
            transports=TransportType.HTTP,
            auth_required=False
        )
        
        self.server.register_endpoint(
            "/server/terminal/close",
            RequestType.POST,
            self._handle_close,
            transports=TransportType.HTTP,
            auth_required=False
        )
        
        self.server.register_endpoint(
            "/server/terminal/status",
            RequestType.GET,
            self._handle_status,
            transports=TransportType.HTTP,
            auth_required=False
        )
    
    def _register_websocket(self):
        try:
            app = self.server.lookup_component("application")
            if app:
                route_path = f"{app.route_prefix}/terminal/ws"
                app.mutable_router.add_handler(
                    route_path,
                    ShellHandler,
                    {'terminal_manager': self}
                )
                logging.info(f"Terminal WebSocket registered at {route_path}")
            else:
                logging.error("Application component not found")
        except Exception as e:
            logging.exception(f"Failed to register WebSocket: {e}")
    
    async def _handle_sessions(self, web_request) -> Dict[str, Any]:
        sessions_info = []
        for session_id, handler in self.sessions.items():
            sessions_info.append({
                'id': session_id,
                'ip_address': str(handler.ip_addr) if handler.ip_addr else None,
                'connected': handler.fd is not None,
                'pid': handler.process.pid if handler.process else None
            })
        
        return {
            'active_sessions': len(self.sessions),
            'max_sessions': self.max_sessions,
            'sessions': sessions_info
        }
    
    async def _handle_close(self, web_request) -> Dict[str, str]:
        session_id = web_request.get_int('session_id')
        
        if session_id in self.sessions:
            handler = self.sessions[session_id]
            await handler.close_terminal()
            handler.close()
            return {'status': 'closed', 'session_id': str(session_id)}
        else:
            return {'status': 'error', 'message': f'Session {session_id} not found'}
    
    async def _handle_status(self, web_request) -> Dict[str, Any]:
        return {
            'status': 'running',
            'active_sessions': len(self.sessions),
            'max_sessions': self.max_sessions,
            'websocket_path': '/terminal/ws'
        }
    
    def add_session(self, session_id: int, handler: ShellHandler):
        if len(self.sessions) >= self.max_sessions:
            oldest_id = next(iter(self.sessions))
            oldest_handler = self.sessions[oldest_id]
            asyncio.create_task(oldest_handler.close_terminal())
            oldest_handler.close()
            del self.sessions[oldest_id]
        
        self.sessions[session_id] = handler
    
    def remove_session(self, session_id: int):
        self.sessions.pop(session_id, None)
    
    async def close_all(self):
        logging.info(f"Closing all terminal sessions: {len(self.sessions)}")
        for session_id, handler in list(self.sessions.items()):
            try:
                await handler.close_terminal()
                handler.close()
            except Exception as e:
                logging.exception(f"Error closing session {session_id}: {e}")
        self.sessions.clear()


def load_component(config: ConfigHelper) -> TerminalManager:
    return TerminalManager(config)