from modules.tools.tool_registry import registry
from modules.system.system_info import get_system_info
from modules.system.packages import install_package, remove_package, search_packages, update_system
from modules.system.services import service_status, start_service, stop_service, restart_service, list_failed_services
from modules.system.shell import shell
from modules.memory.memory_tools import store_memory, retrieve_memory, record_change, get_recent_changes
from modules.system.remote_shell import run_remote_command
from modules.audio.tts import tts
from modules.browser import browser
import json

async def speak(text: str):
    await tts.speak(text)
    return f"Spoke: {text}"

def run_command(command: str, use_sudo: bool = False):
    return shell.run_command(command, use_sudo=use_sudo)

def register_all_tools():
    """Registers all available system tools into the global registry."""
    registry.register("get_system_info", get_system_info, "Retrieves detailed system information (distro, uptime, CPU, RAM, Disks).")
    registry.register("install_package", install_package, "Installs a system package using the package manager (requires sudo).")
    registry.register("remove_package", remove_package, "Removes a system package (requires sudo).")
    registry.register("search_packages", search_packages, "Searches for a package in the repository.")
    registry.register("update_system", update_system, "Updates the entire system (requires sudo).")
    registry.register("service_status", service_status, "Gets the current status of a systemd service.")
    registry.register("start_service", start_service, "Starts a systemd service (requires sudo).")
    registry.register("stop_service", stop_service, "Stops a systemd service (requires sudo).")
    registry.register("restart_service", restart_service, "Restarts a systemd service (requires sudo).")
    registry.register("list_failed_services", list_failed_services, "Lists all failed systemd services.")
    registry.register("run_command", run_command, "Runs an arbitrary shell command. Args: command (str), use_sudo (bool).")
    registry.register("run_remote_command", run_remote_command, "Runs a shell command on a remote machine over SSH. The host must currently be a discovered hive peer. Args: host (str), command (str), use_sudo (bool).")
    registry.register("speak", speak, "Speaks text out loud through this machine's speakers via local TTS. Args: text (str).")

    # Memory tools
    registry.register("store_memory", store_memory, "Stores a piece of information in long-term memory. Args: key (str), value (str).")
    registry.register("retrieve_memory", retrieve_memory, "Retrieves a piece of information from long-term memory. Args: key (str).")
    registry.register("record_change", record_change, "Records a system change in the history log. Args: request (str), action (str), result (str).")
    registry.register("get_recent_changes", get_recent_changes, "Retrieves the last few changes made to the system.")

    # Browser tools (Playwright/Firefox, dedicated profile - see modules/browser/)
    registry.register("browser_navigate", browser.navigate, "Navigates Sarah's own browser to a URL. Args: url (str).")
    registry.register("browser_click", browser.click, "Clicks the first visible element whose text matches. Args: text (str).")
    registry.register("browser_type", browser.type_text, "Types text into the focused element, or into a CSS selector if given. Args: text (str), selector (str, optional).")
    registry.register("browser_read_page", browser.read_page, "Returns the visible text content of the current page.")
    registry.register("browser_screenshot", browser.screenshot, "Takes a screenshot of the current page. Args: path (str, optional).")

# Execute registration immediately on import
register_all_tools()
