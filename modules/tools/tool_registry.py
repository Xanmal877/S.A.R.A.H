import logging

logger = logging.getLogger("ToolRegistry")

class ToolRegistry:
    """
    Central registry for Sarah's system tools.
    Allows dynamic registration and retrieval of tool functions.
    """
    def __init__(self):
        self._tools = {}

    def register(self, name, func, description=""):
        """Registers a tool function."""
        self._tools[name] = {
            "func": func,
            "description": description
        }
        logger.info(f"Registered tool: {name}")

    def get_tool(self, name):
        """Retrieves a tool by name."""
        return self._tools.get(name)

    def list_tools(self):
        """Returns a list of all registered tools and their descriptions."""
        return {name: info["description"] for name, info in self._tools.items()}

    def get_all_tools(self):
        """Returns all tool definitions."""
        return self._tools

# Global registry instance
registry = ToolRegistry()
