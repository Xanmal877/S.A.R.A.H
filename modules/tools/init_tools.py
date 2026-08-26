from modules.tools.tool_registry import registry
from modules.system.system_info import get_system_info
from modules.system.packages import install_package, remove_package, search_packages, update_system
from modules.system.services import service_status, start_service, stop_service, restart_service, list_failed_services
from modules.system.shell import shell
from modules.memory.memory_tools import store_memory, retrieve_memory, record_change, get_recent_changes
from modules.system.remote_shell import run_remote_command
from modules.system.clipboard import get_clipboard, set_clipboard
from modules.system.notifications import send_notification
from modules.system.media import media_play_pause, media_next, media_previous, media_status, list_media_players
from modules.system.journal import get_recent_logs
from modules.system.windows import list_windows
from modules.system.file_watcher import diff_directory, check_new_downloads
from modules.system.git_tools import git_status, git_log, git_diff, git_pull, git_commit
from modules.system.containers import list_containers, list_images, container_logs, start_container, stop_container, restart_container
from modules.system.remote_files import push_file_to_peer, pull_file_from_peer
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
    registry.register("browser_accessibility_tree", browser.accessibility_tree, "Returns the accessibility (ARIA) tree for the page or a selector - roles/names of what's on screen, without a screenshot. Args: selector (str, optional), max_chars (int, optional).")
    registry.register("browser_network_log", browser.network_log, "Returns recently observed network responses on the current page. Args: resource_type (str, optional filter), limit (int, optional).")
    registry.register("browser_clear_network_log", browser.clear_network_log, "Clears the recorded network log.")
    registry.register("browser_start_trace", browser.start_trace, "Starts a Playwright trace (screenshots/DOM/network) of the browser session for later debugging.")
    registry.register("browser_stop_trace", browser.stop_trace, "Stops the running trace and saves it as a .zip viewable at trace.playwright.dev. Args: path (str, optional).")

    # Desktop integration tools
    registry.register("get_clipboard", get_clipboard, "Reads the current text contents of the system clipboard.")
    registry.register("set_clipboard", set_clipboard, "Sets the system clipboard to the given text. Args: text (str).")
    registry.register("send_notification", send_notification, "Sends a desktop notification. Args: title (str), message (str, optional), urgency (str: low/normal/critical, optional).")
    registry.register("list_media_players", list_media_players, "Lists MPRIS media players currently visible (browser, phone via KDE Connect, etc.).")
    registry.register("media_play_pause", media_play_pause, "Toggles play/pause. Args: player (str, optional exact name from list_media_players; defaults to whichever player playerctl picks first).")
    registry.register("media_next", media_next, "Skips to the next track. Args: player (str, optional).")
    registry.register("media_previous", media_previous, "Goes to the previous track. Args: player (str, optional).")
    registry.register("media_status", media_status, "Reports what's currently playing. Args: player (str, optional).")
    registry.register("get_recent_logs", get_recent_logs, "Reads recent systemd journal entries. Args: lines (int), unit (str, optional), priority (str, optional).")
    registry.register("list_windows", list_windows, "Lists currently open windows (id, desktop, PID, host, title).")

    # File watching
    registry.register("diff_directory", diff_directory, "Compares a directory against its last recorded snapshot and reports new/removed/changed files, then updates the snapshot. Args: path (str, optional, defaults to ~/Downloads).")
    registry.register("check_new_downloads", check_new_downloads, "Checks ~/Downloads specifically for changes since the last check.")

    # Git tooling
    registry.register("git_status", git_status, "Gets short status + branch info for a git repo. Args: repo_path (str).")
    registry.register("git_log", git_log, "Gets recent commit log for a git repo. Args: repo_path (str), count (int, optional).")
    registry.register("git_diff", git_diff, "Gets a diffstat for a git repo. Args: repo_path (str), staged (bool, optional).")
    registry.register("git_pull", git_pull, "Pulls the current branch of a git repo. Args: repo_path (str).")
    registry.register("git_commit", git_commit, "Commits staged (or all, if add_all) changes locally - never pushes. Args: repo_path (str), message (str), add_all (bool, optional).")

    # Container controls (docker or podman, whichever is installed)
    registry.register("list_containers", list_containers, "Lists containers. Args: all (bool, optional, default True to include stopped).")
    registry.register("list_images", list_images, "Lists container images.")
    registry.register("container_logs", container_logs, "Gets recent logs for a container. Args: name (str), lines (int, optional).")
    registry.register("start_container", start_container, "Starts a stopped container. Args: name (str).")
    registry.register("stop_container", stop_container, "Stops a running container. Args: name (str).")
    registry.register("restart_container", restart_container, "Restarts a container. Args: name (str).")

    # Remote file transfer (rsync+SSH, hive-peer restricted - same trust boundary as run_remote_command)
    registry.register("push_file_to_peer", push_file_to_peer, "Copies a local file/directory to a hive peer over rsync+SSH. Args: host (str), local_path (str), remote_path (str).")
    registry.register("pull_file_from_peer", pull_file_from_peer, "Copies a file/directory from a hive peer to this machine over rsync+SSH. Args: host (str), remote_path (str), local_path (str).")

# Execute registration immediately on import
register_all_tools()
