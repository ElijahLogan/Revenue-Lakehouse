from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

DEFAULT_WATERMARK = "1970-01-01T00:00:00Z"

