import logging
from modules.system.shell import shell

logger = logging.getLogger("SystemService")

class ServiceManager:
    """
    Manages systemd services.
    """
    def status(self, service_name: str):
        return shell.run_command(f"systemctl status {service_name}")

    def start(self, service_name: str):
        return shell.run_command(f"systemctl start {service_name}", use_sudo=True)

    def stop(self, service_name: str):
        return shell.run_command(f"systemctl stop {service_name}", use_sudo=True)

    def restart(self, service_name: str):
        return shell.run_command(f"systemctl restart {service_name}", use_sudo=True)

    def enable(self, service_name: str):
        return shell.run_command(f"systemctl enable {service_name}", use_sudo=True)

    def disable(self, service_name: str):
        return shell.run_command(f"systemctl disable {service_name}", use_sudo=True)

    def list_failed(self):
        return shell.run_command("systemctl --failed")

service_manager = ServiceManager()

# Tool definitions
def service_status(service: str):
    return service_manager.status(service)

def start_service(service: str):
    return service_manager.start(service)

def stop_service(service: str):
    return service_manager.stop(service)

def restart_service(service: str):
    return service_manager.restart(service)

def list_failed_services():
    return service_manager.list_failed()
