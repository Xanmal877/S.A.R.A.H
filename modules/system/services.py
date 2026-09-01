import logging

from modules.system.shell import shell

logger = logging.getLogger("SystemService")

class ServiceManager:
    """
    Manages systemd services.
    """
    def status(self, service_name: str):
        return shell.run_argv(["systemctl", "status", *service_name.split()])

    def start(self, service_name: str):
        return shell.run_argv(["systemctl", "start", *service_name.split()], use_sudo=True)

    def stop(self, service_name: str):
        return shell.run_argv(["systemctl", "stop", *service_name.split()], use_sudo=True)

    def restart(self, service_name: str):
        return shell.run_argv(["systemctl", "restart", *service_name.split()], use_sudo=True)

    def enable(self, service_name: str):
        return shell.run_argv(["systemctl", "enable", *service_name.split()], use_sudo=True)

    def disable(self, service_name: str):
        return shell.run_argv(["systemctl", "disable", *service_name.split()], use_sudo=True)

    def list_failed(self):
        return shell.run_argv(["systemctl", "--failed"])

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
