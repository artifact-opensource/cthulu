from config_schema import Config

def load_config(path: str = "config.json") -> Config:
    """Load and validate configuration from a file."""
    return Config.load(path)
