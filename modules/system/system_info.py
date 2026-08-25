import platform
import psutil
import os
from modules.system.shell import shell

class SystemInfo:
    """
    Provides detailed information about the host Linux system.
    """
    def get_distro(self):
        try:
            with open("/etc/os-release", "r") as f:
                return f.read()
        except Exception:
            return platform.platform()

    def get_uptime(self):
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
            return f"{uptime_seconds / 3600:.2f} hours"

    def get_cpu_info(self):
        return {
            "model": platform.processor(),
            "cores": psutil.cpu_count(logical=False),
            "threads": psutil.cpu_count(logical=True),
            "load": psutil.cpu_percent(interval=1)
        }

    def get_memory_info(self):
        mem = psutil.virtual_memory()
        return {
            "total": mem.total,
            "available": mem.available,
            "percent": mem.percent
        }

    def get_disk_info(self):
        return {p.mountpoint: psutil.disk_usage(p.mountpoint)._asdict() 
                for p in psutil.disk_partitions() if 'loop' not in p.device}

sys_info = SystemInfo()

# Tool definitions for registration
def get_system_info():
    return {
        "distro": sys_info.get_distro(),
        "uptime": sys_info.get_uptime(),
        "cpu": sys_info.get_cpu_info(),
        "memory": sys_info.get_memory_info(),
        "disks": sys_info.get_disk_info()
    }
