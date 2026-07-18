from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def _walk_json(value):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _resolve_local_ref(document: dict, reference: str):
    assert reference.startswith("#/"), reference
    current = document
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        assert isinstance(current, dict) and part in current, reference
        current = current[part]
    return current


def test_openapi_contract_matches_e02_scope():
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "E02 Task API"
    assert schema["info"]["version"] == "0.3.0"
    assert set(schema["paths"]) == {
        "/tasks",
        "/tasks/{task_id}",
        "/metrics",
        "/livez",
        "/readyz",
    }

    create_responses = schema["paths"]["/tasks"]["post"]["responses"]
    assert {"200", "201", "409", "422", "429", "500", "503", "504"} <= set(
        create_responses
    )
    list_parameters = {
        parameter["name"]: parameter
        for parameter in schema["paths"]["/tasks"]["get"]["parameters"]
    }
    assert set(list_parameters) == {"limit", "cursor"}
    assert list_parameters["limit"]["schema"]["maximum"] == 100
    assert list_parameters["limit"]["schema"]["minimum"] == 1
    update = schema["paths"]["/tasks/{task_id}"]["patch"]
    assert any(
        parameter["name"] == "If-Match" and parameter["required"]
        for parameter in update["parameters"]
    )
    assert schema["components"]["schemas"]["TaskCreate"]["additionalProperties"] is False
    assert set(schema["components"]["schemas"]["TaskPage"]["required"]) == {
        "items",
        "next_cursor",
    }
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            for status_code, contract in operation["responses"].items():
                if int(status_code) < 400:
                    continue
                assert set(contract["content"]) == {"application/problem+json"}
                problem_schema = contract["content"]["application/problem+json"][
                    "schema"
                ]
                assert problem_schema["additionalProperties"] is False
    assert schema["components"]["securitySchemes"]["HTTPBearer"]["scheme"] == "bearer"


def test_every_openapi_local_reference_resolves_from_the_document_root():
    schema = client.get("/openapi.json").json()

    references = [
        node["$ref"]
        for node in _walk_json(schema)
        if isinstance(node, dict) and "$ref" in node
    ]

    assert references
    for reference in references:
        _resolve_local_ref(schema, reference)
