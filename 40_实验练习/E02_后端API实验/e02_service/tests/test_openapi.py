from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_openapi_contract_matches_e02_scope():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "E02 Task API"
    assert schema["info"]["version"] == "0.2.0"
    assert set(schema["paths"]) == {"/tasks", "/tasks/{task_id}", "/metrics"}

    create_responses = schema["paths"]["/tasks"]["post"]["responses"]
    assert {"201", "422"} <= set(create_responses)
    assert schema["components"]["schemas"]["TaskCreate"]["additionalProperties"] is False
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"
