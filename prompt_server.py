"""
HTTP server for receiving interactive prompts from Home Assistant
"""
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import utils

logger = utils.setup_logger()

class PromptHandler(BaseHTTPRequestHandler):
    """HTTP request handler for HA->GLaSSIST prompts."""
    
    def __init__(self, *args, conversation_manager=None, **kwargs):
        self.conversation_manager = conversation_manager
        super().__init__(*args, **kwargs)
    
    def do_POST(self):
        """Handle POST requests from Home Assistant."""
        try:
            # Read request data
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # Parse JSON
            request_data = json.loads(post_data.decode('utf-8'))
            logger.info(f"Received HA prompt request: {request_data}")
            logger.info(f"📨 Message: '{request_data.get('message', 'N/A')}', wait_for_response: {request_data.get('wait_for_response', True)}")
            
            # Validate required fields
            if 'message' not in request_data:
                self.send_error(400, "Missing 'message' field")
                return
            
            # Set defaults
            context = request_data.get('context', 'interactive_prompt')
            timeout = request_data.get('timeout', 10)
            wait_for_response = request_data.get('wait_for_response', True)  # Default to True
            use_ai_message = request_data.get('use_ai_message', False)  # Generate message via AI
            
            # Send immediate response to HA
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {"status": "accepted", "message": "Prompt will be processed"}
            self.wfile.write(json.dumps(response).encode())
            
            # Process prompt asynchronously
            if self.conversation_manager:
                threading.Thread(
                    target=self.conversation_manager.handle_interactive_prompt,
                    args=(request_data,),
                    daemon=True
                ).start()
            else:
                logger.error("No conversation manager available")
                
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in request: {e}")
            self.send_error(400, f"Invalid JSON: {e}")
        except Exception as e:
            logger.error(f"Error processing prompt request: {e}")
            self.send_error(500, f"Internal error: {e}")
    
    def do_GET(self):
        """Handle GET requests - health check."""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {
                "status": "ok", 
                "service": "GLaSSIST Prompt Server",
                "conversation_manager": self.conversation_manager is not None
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_error(404, "Not found")
    
    def log_message(self, format, *args):
        """Override to use our logger instead of stderr."""
        logger.info(f"HTTP: {format % args}")

class PromptServer:
    """HTTP server for receiving interactive prompts from Home Assistant."""
    
    def __init__(self, conversation_manager, port=8766):
        self.conversation_manager = conversation_manager
        self.port = port
        self.server = None
        self.thread = None
        self.running = False
    
    def start(self):
        """Start the HTTP server in a background thread."""
        if self.running:
            logger.warning("Prompt server already running")
            return True
        
        try:
            # Create handler class with conversation_manager
            def handler_factory(*args, **kwargs):
                return PromptHandler(*args, conversation_manager=self.conversation_manager, **kwargs)
            
            # Create and configure server
            self.server = HTTPServer(('0.0.0.0', self.port), handler_factory)
            
            # Start server in background thread
            self.thread = threading.Thread(target=self._run_server, daemon=True)
            self.thread.start()
            self.running = True
            
            logger.info(f"✅ Prompt server started on port {self.port}")
            logger.info(f"   HA can send prompts to: http://YOUR_IP:{self.port}/prompt")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start prompt server: {e}")
            return False
    
    def _run_server(self):
        """Run the HTTP server (internal method)."""
        try:
            logger.info(f"Prompt server listening on 0.0.0.0:{self.port}")
            self.server.serve_forever()
        except Exception as e:
            if self.running:  # Only log if we're supposed to be running
                logger.error(f"Prompt server error: {e}")
        finally:
            logger.info("Prompt server stopped")
    
    def stop(self):
        """Stop the HTTP server."""
        if not self.running:
            return
        
        logger.info("Stopping prompt server...")
        self.running = False
        
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception as e:
                logger.error(f"Error stopping prompt server: {e}")
        
        if self.thread and self.thread.is_alive():
            try:
                self.thread.join(timeout=5)
            except Exception as e:
                logger.error(f"Error joining prompt server thread: {e}")
        
        logger.info("Prompt server stopped")
    
    def get_info(self):
        """Get server information."""
        return {
            'running': self.running,
            'port': self.port,
            'conversation_manager': self.conversation_manager is not None
        }