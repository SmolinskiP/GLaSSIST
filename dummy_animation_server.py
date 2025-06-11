import utils

logger = utils.setup_logger()

class DummyAnimationServer:
    def __init__(self):
        """Initialize dummy server."""
        self.current_state = "hidden"
        self.voice_command_callback = None
        logger.info("Dummy animation server initialized (animations disabled)")
    
    def start(self):
        """Do nothing - no server to start."""
        logger.info("Animation server disabled - not starting WebSocket server")
    
    def stop(self):
        """Do nothing - no server to stop."""
        logger.info("Dummy animation server stopped")
    
    def set_voice_command_callback(self, callback):
        """Store callback but don't use it."""
        self.voice_command_callback = callback
    
    def change_state(self, new_state, error_message=None, success_message=None, **kwargs):
        """Just update current state without animations."""
        if new_state != self.current_state:
            logger.debug(f"State change: {self.current_state} -> {new_state}")
            self.current_state = new_state
            
            # Log messages for debugging
            if error_message:
                logger.info(f"Error: {error_message}")
            if success_message:
                logger.info(f"Success: {success_message}")
    
    def show_success(self, message="Success", duration=3.0):
        """Log success message instead of showing animation."""
        logger.info(f"{message}")
        self.change_state("success")
    
    def show_error(self, message="Error", duration=5.0):
        """Log error message instead of showing animation."""
        logger.error(f"{message}")
        self.change_state("error")
    
    def send_audio_data(self, audio_chunk, sample_rate=16000):
        """Do nothing - no animation to update."""
        pass
    
    def send_response_text(self, text):
        """Just log the response text."""
        logger.info(f"Response: {text}")
    
    def pause_wake_word_detection(self):
        """Dummy method for compatibility."""
        pass
    
    def resume_wake_word_detection(self):
        """Dummy method for compatibility."""
        pass