# -*- coding: utf-8 -*-
"""Configuração de logs locais rotativos para diagnóstico."""
import logging
import os
from logging.handlers import RotatingFileHandler


def configure_logging(base_dir):
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    root = logging.getLogger()
    if any(getattr(h, "_vas_handler", False) for h in root.handlers):
        return
    root.setLevel(logging.INFO)
    handler = RotatingFileHandler(os.path.join(log_dir, "avatar_studio.log"), maxBytes=1_500_000,
                                  backupCount=3, encoding="utf-8")
    handler._vas_handler = True
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
