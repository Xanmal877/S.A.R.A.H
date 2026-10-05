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

    async def execute(self, _tool_name, **kwargs):
        """
        Executes a tool by name with the provided arguments.
        Returns the result of the execution.

        The parameter is deliberately named ``_tool_name`` rather than
        ``tool_name``: the tool + args come straight from the model, so an
        argument literally named ``tool_name`` used to collide with the
        executor's own parameter and destroy the whole reasoning turn
        ("ToolExecutor.execute() got multiple values for argument 'tool_name'").
        With the underscore, such an argument is simply forwarded to the tool as
        a normal kwarg - where an unexpected one produces the tool's own clear
        error instead of taking down the loop.
        """
        tool_name = _tool_name
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
