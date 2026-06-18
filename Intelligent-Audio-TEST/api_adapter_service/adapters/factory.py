# -*- coding: utf-8 -*-
"""Adapter factory — selects the appropriate adapter based on vendor config."""

from api_adapter_service.adapters.http_adapter import HttpAdapter
from api_adapter_service.adapters.mock_adapter import MockDialogAdapter
from api_adapter_service.utils.logger import logger


def select_adapter(vendor: str, vendor_config: dict, is_dialog: bool = False):
    """
    Select the appropriate adapter for a vendor.

    Args:
        vendor: Vendor identifier string
        vendor_config: Vendor-specific configuration dict
        is_dialog: Whether this is a dialog mode request

    Returns:
        An adapter instance with a send_request() method
    """
    protocol = vendor_config.get('protocol', '')

    if vendor == 'mock' or protocol == 'mock':
        if is_dialog:
            logger.info('Using MockDialogAdapter')
            return MockDialogAdapter(vendor_config)
        # For non-dialog mock, still use MockDialogAdapter since
        # this service primarily handles dialog mode
        return MockDialogAdapter(vendor_config)

    if protocol == 'http':
        logger.info(f'Using HttpAdapter for vendor={vendor}, base_url={vendor_config.get("base_url", "")}')
        return HttpAdapter(vendor_config)

    # Default: HttpAdapter (voice_llm primarily uses HTTP)
    logger.info(f'Defaulting to HttpAdapter for vendor={vendor}')
    return HttpAdapter(vendor_config)
