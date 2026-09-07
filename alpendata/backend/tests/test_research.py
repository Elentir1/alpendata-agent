import pytest
from fastapi import HTTPException

from alpendata_api.research import public_addresses, public_url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://127.0.0.1/a",
        "https://[::1]/",
        "https://169.254.169.254/latest/meta-data",
        "https://10.0.0.1/",
        "https://example.com:8443/",
        "https://user:password@example.com/",
        "https://example.com\\@127.0.0.1/",
        "https://example.com/\n",
    ],
)
def test_public_reader_refuses_private_or_ambiguous_destinations(url):
    with pytest.raises(HTTPException):
        public_url(url)


def test_public_reader_rejects_local_dns_and_normalizes_without_credentials():
    with pytest.raises(HTTPException):
        public_addresses("localhost")
    assert (
        public_url("https://example.com/é?q=résumé#section")
        == "https://example.com/%C3%A9?q=r%C3%A9sum%C3%A9"
    )
