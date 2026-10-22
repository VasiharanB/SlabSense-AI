def test_health_is_fast_and_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app": "slabsense",
        "environment": "test",
    }
