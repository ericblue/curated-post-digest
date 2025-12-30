#!/usr/bin/env python3
"""Format Claude CLI stream-json output into clean progress messages with spinner."""

import json
import sys
import threading
import time

# Spinner characters
SPINNER = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

class Spinner:
    def __init__(self):
        self.running = False
        self.thread = None
        self.message = "Working..."
        self.idx = 0

    def _spin(self):
        while self.running:
            char = SPINNER[self.idx % len(SPINNER)]
            # Clear line with ANSI escape code, then write new content
            sys.stdout.write(f'\r\033[K  {char} {self.message}')
            sys.stdout.flush()
            self.idx += 1
            time.sleep(0.1)

    def start(self, message="Working..."):
        self.message = message
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def update(self, message):
        self.message = message

    def stop(self, final_message=None):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        # Clear the line with ANSI escape code
        sys.stdout.write('\r\033[K')
        if final_message:
            print(final_message, flush=True)


def format_progress():
    spinner = Spinner()
    spinner.start("Initializing...")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        event_type = event.get("type")

        # Tool use events - show what Claude is doing
        if event_type == "assistant" and "message" in event:
            message = event["message"]
            if "content" in message:
                for block in message["content"]:
                    if block.get("type") == "tool_use":
                        tool_name = block.get("name", "")
                        tool_input = block.get("input", {})

                        if tool_name == "Read":
                            path = tool_input.get("file_path", "")
                            # Shorten path for display
                            short_path = path.split('/')[-1] if '/' in path else path
                            spinner.update(f"Reading {short_path}")
                        elif tool_name == "Write":
                            path = tool_input.get("file_path", "")
                            short_path = path.split('/')[-1] if '/' in path else path
                            spinner.update(f"Writing {short_path}")
                        elif tool_name == "Glob":
                            pattern = tool_input.get("pattern", "")
                            spinner.update(f"Searching {pattern}")
                        elif tool_name == "Grep":
                            pattern = tool_input.get("pattern", "")
                            spinner.update(f"Grep {pattern}")
                        elif tool_name == "Edit":
                            path = tool_input.get("file_path", "")
                            short_path = path.split('/')[-1] if '/' in path else path
                            spinner.update(f"Editing {short_path}")
                    elif block.get("type") == "text":
                        # Show that Claude is thinking/writing
                        text = block.get("text", "")
                        if len(text) > 50:
                            spinner.update("Generating report...")

        # Result event - show completion or error
        if event_type == "result":
            result = event.get("result", {})
            is_error = event.get("is_error", False)
            if isinstance(result, dict):
                is_error = is_error or result.get("is_error", False)
                error_msg = result.get("error", "Unknown error")
            else:
                error_msg = str(result) if is_error else ""
            if is_error:
                spinner.stop(f"  ✗ Error: {error_msg}")
            else:
                spinner.stop("  ✓ Complete")

        # Check for error events
        if event_type == "error":
            error_msg = event.get("error", {}).get("message", "Unknown error")
            spinner.stop(f"  ✗ Error: {error_msg}")

        # Check for tool errors in user messages (permission denied, etc.)
        if event_type == "user" and "message" in event:
            message = event["message"]
            if "content" in message:
                for block in message["content"]:
                    if block.get("type") == "tool_result" and block.get("is_error"):
                        error_content = block.get("content", "")
                        if error_content:
                            spinner.stop(f"  ✗ {error_content}")
                            spinner.start("Retrying...")

if __name__ == "__main__":
    format_progress()
