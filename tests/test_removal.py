"""Entry deletion revokes only its own certificate and tolerates outages."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.scottibyte_incus import async_remove_entry
from custom_components.scottibyte_incus.api import certificate_fingerprint
from custom_components.scottibyte_incus.bootstrap import generate_certificate, write_credentials
from custom_components.scottibyte_incus.const import DOMAIN


@pytest.mark.asyncio
@pytest.mark.parametrize('offline', [False, True])
async def test_remove_own_trust_and_local_credentials(hass, tmp_path, offline):
    hass.config.config_dir = str(tmp_path)
    directory = Path(hass.config.path('.storage', DOMAIN, 'remove-test'))
    directory.mkdir(parents=True)
    cert, key = generate_certificate()
    write_credentials(directory/'client.crt', directory/'client.key', cert, key)
    (directory/'server.crt').write_text(cert)
    entry = SimpleNamespace(entry_id='remove-test', title='Lab', data={
        'credential_id': 'remove-test', 'host': '192.168.1.10', 'api_port': 8443})
    client = SimpleNamespace(request=AsyncMock(side_effect=OSError('offline') if offline else None), close=AsyncMock())
    with patch('custom_components.scottibyte_incus.IncusClient', return_value=client), patch(
        'custom_components.scottibyte_incus.persistent_notification.async_create') as notice:
        await async_remove_entry(hass, entry)
        client.request.assert_awaited_once_with('DELETE', f'/1.0/certificates/{certificate_fingerprint(cert)}', timeout=10)
        assert notice.called is offline
        client.close.assert_awaited_once()
    assert not directory.exists()
