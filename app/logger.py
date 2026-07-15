import logging
from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme

# Custom theme for sync styling
theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "download": "bold blue",
    "parse": "bold magenta",
    "sync": "bold cyan",
})

console = Console(theme=theme)

def setup_logger(name: str = "sync_service", level: str = "INFO") -> logging.Logger:
    """
    Sets up a logger with RichHandler.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)]
    )
    
    log = logging.getLogger(name)
    log.setLevel(numeric_level)
    return log

# Instantiate default logger
logger = setup_logger()
