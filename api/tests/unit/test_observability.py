from uuid import UUID


def test_each_request_gets_a_distinct_request_id(client):
    a = client.get("/health").headers["x-request-id"]
    b = client.get("/health").headers["x-request-id"]
    assert a and b and a != b


def test_inbound_request_id_is_honoured(client):
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"


def test_oversized_inbound_request_id_is_replaced(client):
    response = client.get("/health", headers={"X-Request-ID": "x" * 65})

    replacement = response.headers["x-request-id"]
    assert replacement != "x" * 65
    assert str(UUID(replacement)) == replacement
