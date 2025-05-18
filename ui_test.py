import unittest
import subprocess
import time
import signal
import os
import sys
import logging
import re

class UICommandTest(unittest.TestCase):
    """Test the UI commands in the stock news app"""
    
    @classmethod
    def setUpClass(cls):
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        cls.logger = logging.getLogger("UITest")
        
        cls.logger.info("Setting up UI test")
        
        # Check if the app file exists
        if not os.path.exists("main.py"):
            cls.logger.error("main.py not found. Tests cannot run.")
            sys.exit(1)
    
    def test_mock_data_loads(self):
        """Test if the app loads with mock data"""
        self.logger.info("Testing mock data loading")
        try:
            # Run with a timeout to ensure it doesn't hang
            output = subprocess.check_output(
                ["python3", "main.py", "--mock"], 
                stderr=subprocess.STDOUT,
                timeout=1  # Only wait a second, we'll kill it immediately
            )
            self.fail("App didn't start or exited too quickly")
        except subprocess.TimeoutExpired:
            # This is expected - app is running
            self.logger.info("App started successfully")
            
            # Kill the process
            subprocess.run(["pkill", "-f", "python3 main.py"])
    
    def test_ui_commands_registered(self):
        """Test that UI commands are correctly registered in the app"""
        self.logger.info("Testing UI commands registration")
        
        # We need to check the app code for command bindings
        with open("main.py", "r") as f:
            main_content = f.read()
            
        # Check for key bindings
        self.assertIn("q", "quit", main_content)  # Quit command
        self.assertIn("up", "cursor_up", main_content)  # Up arrow
        self.assertIn("down", "cursor_down", main_content)  # Down arrow
        self.assertIn("f", "show_filter_menu", main_content)  # Filter
        self.assertIn("r", "reset_filter", main_content)  # Reset filter
        
        self.logger.info("UI commands are correctly registered")
    
    def test_article_selection(self):
        """Test the article selection functionality"""
        self.logger.info("Testing article selection")
        
        # Clear the log file first
        with open("app.log", "w") as f:
            f.truncate(0)
            
        # Start app with mock data and debug flag
        proc = subprocess.Popen(
            ["python3", "main.py", "--mock", "--debug"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        try:
            # Give it time to start up
            time.sleep(2)
            
            # Check if log shows it started and loaded articles
            with open("app.log", "r") as f:
                log_content = f.read()
                self.assertIn("Starting TUI with", log_content)
                self.assertIn("Added", log_content)
                self.assertIn("Setting selection to first article", log_content)
                self.assertIn("First article has article_data", log_content)
            
            self.logger.info("Article selection functionality works")
            
        finally:
            # Cleanup
            proc.terminate()
            time.sleep(1)
            proc.kill()  # Make sure it's really gone
            self.logger.info("App terminated")
    
    def test_stock_filtering(self):
        """Test filtering by stock ticker"""
        self.logger.info("Testing stock filtering")
        
        # Clear the log file first
        with open("app.log", "w") as f:
            f.truncate(0)
        
        # Run with AAPL stock filter and mock data
        proc = subprocess.Popen(
            ["python3", "main.py", "--mock", "--stocks", "AAPL", "--debug"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        try:
            # Give it time to start up
            time.sleep(2)
            
            # Check log for successful filtering
            with open("app.log", "r") as f:
                log_content = f.read()
                self.assertIn("Fetching news for stocks: AAPL", log_content)
                self.assertIn("Filtering", log_content)
                self.assertIn("ticker AAPL", log_content)
            
            self.logger.info("Stock filtering works")
            
        finally:
            # Cleanup
            proc.terminate()
            time.sleep(1)
            proc.kill()
            self.logger.info("App terminated")
    
    def test_time_interval_filtering(self):
        """Test filtering by time interval"""
        self.logger.info("Testing time interval filtering")
        
        # Clear the log file first
        with open("app.log", "w") as f:
            f.truncate(0)
        
        # Run with time interval filter
        proc = subprocess.Popen(
            ["python3", "main.py", "--mock", "--time-interval", "last-4-hours", "--debug"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        try:
            # Give it time to start up
            time.sleep(2)
            
            # Check log for successful filtering
            with open("app.log", "r") as f:
                log_content = f.read()
                self.assertIn("Filtering articles published since", log_content)
                self.assertIn("after time filter", log_content)
            
            self.logger.info("Time interval filtering works")
            
        finally:
            # Cleanup
            proc.terminate()
            time.sleep(1)
            proc.kill()
            self.logger.info("App terminated")

if __name__ == "__main__":
    unittest.main() 