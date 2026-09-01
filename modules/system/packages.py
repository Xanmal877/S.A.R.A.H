from modules.system.shell import shell


class PackageManager:
    """
    Handles package management for the system.
    Prioritizes pacman as the system is Arch-based (CachyOS).
    """
    def __init__(self):
        self.mgr = "pacman"

    def install(self, package_name: str):
        return shell.run_argv([self.mgr, "-S", "--noconfirm", *package_name.split()], use_sudo=True)

    def remove(self, package_name: str):
        return shell.run_argv([self.mgr, "-Rs", "--noconfirm", *package_name.split()], use_sudo=True)

    def search(self, query: str):
        return shell.run_argv([self.mgr, "-Ss", *query.split()])

    def update_system(self):
        return shell.run_argv([self.mgr, "-Syu", "--noconfirm"], use_sudo=True)

    def list_installed(self):
        return shell.run_argv([self.mgr, "-Q"])

pkg_manager = PackageManager()

# Tool definitions
def install_package(package: str):
    return pkg_manager.install(package)

def remove_package(package: str):
    return pkg_manager.remove(package)

def search_packages(query: str):
    return pkg_manager.search(query)

def update_system():
    return pkg_manager.update_system()
