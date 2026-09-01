import asyncio
import logging

from modules.tools.tool_registry import registry

logger = logging.getLogger("ToolExecutor")

class ToolExecutor:
    """
    Executes tools registered in the ToolRegistry.
    Handles both synchronous and asynchronous tools.
    """
    def __init__(self, agent=None):
        self.agent = agent

    async def execute(self, tool_name, **kwargs):
        """
        Executes a tool by name with the provided arguments.
        Returns the result of the execution.
        """
        tool_info = registry.get_tool(tool_name)
        if not tool_info:
            return f"Error: Tool '{tool_name}' not found in registry."

        func = tool_info["func"]
        
        try:
            logger.info(f"Executing tool: {tool_name} with args {kwargs}")
            if asyncio.iscoroutinefunction(func):
                result = await func(**kwargs)
            else:
                result = func(**kwargs)
            return result
        except Exception as e:
            logger.exception(f"Error executing tool {tool_name}: {e}")
            return f"Error executing {tool_name}: {e!s}"

# Global executor instance (will be linked to agent later)
executor = ToolExecutor()
