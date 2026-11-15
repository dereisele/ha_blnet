"""Constants for the BLNET integration."""

DOMAIN = "blnet"

CONF_WEB_PORT = "web_port"
CONF_TA_PORT = "ta_port"
CONF_USE_WEB = "use_web"
CONF_USE_TA = "use_ta"
CONF_NODE = "can_node"

DEFAULT_WEB_PORT = 80
DEFAULT_TA_PORT = 40000
DEFAULT_SCAN_INTERVAL = 360
MIN_SCAN_INTERVAL = 10

# Domains of pyblnet's fetch() that are always sensors
SENSOR_DOMAINS = ("analog", "speed", "power", "energy")
